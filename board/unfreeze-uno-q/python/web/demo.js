import { cueDefaults } from "./cue-defaults.js";

/** An in-memory protocol peer for development. No command reaches hardware. */
export class DemoBoard {
  constructor(now = () => performance.now()) {
    this.now = now;
    this.seq = 0;
    this.id = 0;
    this.boot = "demo-" + Date.now();
    this.timers = new Set();
    this.settings = {
      settingsRevision: 1,
      audio: { mode: "phone_preferred" },
      buzzer: { ...cueDefaults.buzzer },
      haptics: { enabled: true, ...cueDefaults.haptics },
    };
    this.caps = {
      firmwareVersion: "demo-v1",
      audioModes: ["phone_preferred", "board_only"],
      buzzerSupported: true,
      hapticsSupported: true,
      buzzerLimits: { toneHz: [200, 3000], cadenceBpm: [45, 150] },
      hapticsLimits: {
        cadenceBpm: [45, 150],
        levelsPercent: [25, 30, 35, 40, 45, 50],
      },
    };
    this.reset();
  }
  reset() {
    this.session = null;
    this.expiry = 0;
    this.door = null;
    this.vibro = null;
    this.pending = null;
    this.previewId = null;
    for (const t of this.timers) clearTimeout(t);
    this.timers.clear();
  }
  later(ms, fn) {
    const t = setTimeout(() => {
      this.timers.delete(t);
      fn();
    }, ms);
    this.timers.add(t);
  }
  tick() {
    if (this.session && this.now() >= this.expiry) {
      this.reset();
      this.publish();
    }
  }
  snapshot() {
    return {
      deviceId: "UNO Q · demo",
      bootId: this.boot,
      sessionId: this.session,
      sessionState: this.session ? "ACTIVE" : "IDLE",
      sessionExpiresInMs: Math.max(0, this.expiry - this.now()),
      settingsRevision: this.settings.settingsRevision,
      phoneAudioReady: !!this.ready,
      faultCode: null,
      visionStatus: "simulated",
      motionStatus: "research_unverified",
      doorAudio: this.door,
      hapticsOutput: this.vibro,
    };
  }
  publish() {
    this.listener?.("status.snapshot", this.snapshot());
  }
  listen(fn) {
    this.listener = fn;
    this.publish();
  }
  close() {
    this.listener = null;
    this.reset();
  }
  debug(type, source, data) {
    const seq = ++this.seq;
    const e = {
      schemaVersion: 1,
      bootId: this.boot,
      sessionId: this.session,
      seq,
      eventId: "event-" + seq,
      boardUptimeMs: Math.round(this.now()),
      origin: "simulated",
      type,
      source,
      data,
    };
    if (this.subscribed) this.listener?.("debug.event", e);
    return e.eventId;
  }
  output(kind, state, reason, cueId, triggerEventId) {
    const output = { output: kind, state, reason, cueId, triggerEventId };
    const prop = kind === "vibro" ? "vibro" : "door";
    this[prop] = output;
    this.debug("cue.output_changed", "controller", output);
    this.publish();
    this.later(kind === "phone_audio" ? 12_000 : 3000, () => {
      if (this[prop] === output) {
        this[prop] = null;
        this.publish();
      }
    });
  }
  risk() {
    if (!this.session || this.vibro) return;
    const id = this.debug("motion.risk", "movement", {
      confidence: 0.87,
      motionStatus: "research_unverified",
    });
    if (this.settings.haptics.enabled)
      this.output("vibro", "applied", "simulated risk", "v-" + ++this.id, id);
  }
  approach() {
    if (!this.session || this.pending || this.door) return;
    const trigger = this.debug("door.approach", "camera", {
      bboxPx: [52, 10, 90, 161],
      inputSize: [192, 192],
      confidence: 0.91,
    });
    const key = { sessionId: this.session, cueId: "a-" + ++this.id };
    this.pending = { key, trigger, stage: "offer" };
    if (this.settings.audio.mode === "board_only" || !this.ready) {
      this.fallback("board route");
      return;
    }
    this.listener?.("cue.audio.offer", { ...key, ttlMs: 500 });
    this.later(300, () => {
      if (this.pending?.key === key && this.pending.stage === "offer")
        this.fallback("ready timeout");
    });
  }
  fallback(reason) {
    const p = this.pending;
    if (!p) return;
    this.pending = null;
    this.listener?.("cue.audio.cancel", p.key);
    this.output("buzzer", "applied", reason, p.key.cueId, p.trigger);
  }
  send(name, b) {
    switch (name) {
      case "client.status":
        this.ready = b.audioReady;
        return;
      case "debug.subscribe":
        this.subscribed = true;
        return;
      case "debug.unsubscribe":
        this.subscribed = false;
        return;
    }
    const p = this.pending;
    if (!p || b.cueId !== p.key.cueId || b.sessionId !== this.session) return;
    if (name === "cue.audio.ready" && p.stage === "offer") {
      p.stage = "play";
      this.listener?.("cue.audio.play", p.key);
      this.later(700, () => {
        if (this.pending === p) this.fallback("play timeout");
      });
    } else if (name === "cue.audio.started" && p.stage === "play") {
      this.pending = null;
      this.output(
        "phone_audio",
        "started",
        "playback confirmed",
        b.cueId,
        p.trigger,
      );
    } else if (name === "cue.audio.failed") this.fallback("audio unavailable");
  }
  async request(method, path, b = {}) {
    this.tick();
    switch (method + " " + path) {
      case "GET /v1/state":
        return this.snapshot();
      case "GET /v1/settings":
        return structuredCopy(this.settings);
      case "GET /v1/capabilities":
        return structuredCopy(this.caps);
      case "POST /v1/session/start":
        if (!this.session) {
          this.session = "session-" + ++this.id;
          this.expiry = this.now() + 900000;
        }
        break;
      case "POST /v1/session/stop":
        if (this.session && b.sessionId !== this.session)
          throw Error("HTTP 409");
        this.reset();
        break;
      case "PUT /v1/settings": {
        if (b.baseRevision !== this.settings.settingsRevision)
          throw Error("HTTP 409");
        const between = (n, [min, max]) =>
          Number.isInteger(n) && n >= min && n <= max;
        if (
          !this.caps.audioModes.includes(b.audio?.mode) ||
          !between(b.buzzer?.toneHz, this.caps.buzzerLimits.toneHz) ||
          !between(b.buzzer?.cadenceBpm, this.caps.buzzerLimits.cadenceBpm) ||
          !between(b.haptics?.cadenceBpm, this.caps.hapticsLimits.cadenceBpm) ||
          !this.caps.hapticsLimits.levelsPercent.includes(
            b.haptics.levelPercent,
          ) ||
          typeof b.haptics.enabled !== "boolean"
        )
          throw Error("HTTP 422");
        this.settings = structuredCopy({
          settingsRevision: b.baseRevision + 1,
          audio: b.audio,
          buzzer: b.buzzer,
          haptics: b.haptics,
        });
        break;
      }
      case "POST /v1/buzzer/preview":
        if (this.session || this.door) throw Error("HTTP 409");
        this.output("buzzer", "applied", "manual test", b.requestId, this.debug("buzzer.preview", "app", b));
        break;
      case "POST /v1/buzzer/stop":
        if (this.session) throw Error("HTTP 409");
        this.door = null;
        break;
      case "POST /v1/haptics/preview":
        if (this.session) throw Error("HTTP 409");
        if (this.previewId !== b.requestId) {
          this.previewId = b.requestId;
          this.output(
            "vibro",
            "applied",
            "manual preview",
            b.requestId,
            this.debug("haptics.preview", "app", b),
          );
        }
        break;
      case "POST /v1/haptics/stop":
        this.vibro = null;
        break;
      default:
        throw Error("HTTP 404");
    }
    this.publish();
    return this.snapshot();
  }
}
export const structuredCopy = (obj) => JSON.parse(JSON.stringify(obj));
