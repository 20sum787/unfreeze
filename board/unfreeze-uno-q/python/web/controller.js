import { CueRouter } from "./cues.js";
import { DemoBoard, structuredCopy } from "./demo.js";

export class Controller {
  constructor(audio, open, changed, now = () => performance.now()) {
    this.audio = audio;
    this.open = open;
    this.changed = changed;
    this.now = now;
    this.gen = 0;
    this.visible = true;
    this.debug = false;
    this.logs = [];
    this.message = "";
    this.status = "Disconnected";
    this.router = new CueRouter(
      audio,
      (name, key) =>
        this.device?.send(name, { sessionId: key.sessionId, cueId: key.cueId }),
      now,
    );
  }
  disconnect() {
    ++this.gen;
    this.router.bind(null, null);
    this.audio.stop();
    this.device?.close();
    this.device = null;
    this.online = false;
    this.demo = false;
    this.busy = false;
    this.board = null;
    this.settings = null;
    this.draft = null;
    this.caps = null;
    this.telemetry = null;
    this.lastSeq = null;
    this.logs = [];
    this.status = "Disconnected";
    this.message = "";
    this.changed();
  }
  async connect(host, code, demo) {
    this.disconnect();
    const gen = this.gen;
    this.busy = true;
    this.status = "Connecting";
    this.changed();
    try {
      const dev = demo ? new DemoBoard(this.now) : await this.open(host, code);
      if (gen !== this.gen) {
        dev.close();
        return;
      }
      this.device = dev;
      const [caps, settings, board] = await Promise.all(
        ["capabilities", "settings", "state"].map((k) =>
          dev.request("GET", "/v1/" + k),
        ),
      );
      if (gen !== this.gen) return;
      if (
        !Array.isArray(caps.audioModes) ||
        !settings.audio ||
        !Number.isInteger(settings.settingsRevision) ||
        !board.bootId
      )
        throw Error("Unexpected v1 configuration. Check the board contract.");
      this.caps = caps;
      this.settings = settings;
      this.draft = structuredCopy(settings);
      this.demo = demo;
      this.status = "Waiting for live state";
      this.snapshot(board);
      await dev.listen((name, b) => {
        if (gen === this.gen) this.event(name, b);
      });
    } catch (e) {
      if (gen === this.gen) {
        this.disconnect();
        this.message = errorText(e);
        this.changed();
      }
    } finally {
      if (gen === this.gen) {
        this.busy = false;
        this.changed();
      }
    }
  }
  snapshot(b) {
    this.board = b;
    if (this.caps && typeof b.buzzerSupported === "boolean" &&
        typeof b.hapticsSupported === "boolean" &&
        (b.buzzerSupported !== this.caps.buzzerSupported ||
         b.hapticsSupported !== this.caps.hapticsSupported)) {
      this.caps = { ...this.caps, buzzerSupported: b.buzzerSupported,
        hapticsSupported: b.hapticsSupported };
    }
    this.deadline = this.now() + (b.sessionExpiresInMs || 0);
    this.bind();
  }
  bind() {
    const b = this.board;
    const active = this.visible && this.online && b?.sessionState === "ACTIVE";
    this.router.bind(active ? b.bootId : null, active ? b.sessionId : null);
  }
  visibility(v) {
    this.visible = v;
    this.bind();
    if (!v) this.audio.stop();
    this.heartbeat();
  }
  async heartbeat() {
    const dev = this.device,
      gen = this.gen;
    if (!this.online || !dev) return;
    const ready = this.visible && (await this.audio.ready().catch(() => false));
    if (gen === this.gen && this.online)
      dev.send("client.status", { audioReady: this.visible && ready });
  }
  diagnostics(v) {
    this.debug = v;
    if (this.online)
      this.device.send(v ? "debug.subscribe" : "debug.unsubscribe", {});
  }
  record(e) {
    this.logs = [e, ...this.logs].slice(0, 100);
  }
  event(name, b) {
    if (!b || typeof b !== "object") return;
    if (name.startsWith("cue.audio.")) {
      if (this.online && this.visible)
        this.router.handle(name, b).catch((e) => this.report(e));
      return;
    }
    if (name === "status.snapshot") {
      if (!b.bootId || !b.sessionState) return;
      const fresh = !this.online;
      this.online = true;
      this.status = this.demo ? "Demo connected" : "Connected";
      this.snapshot(b);
      if (fresh) {
        this.heartbeat();
        this.diagnostics(this.debug);
      }
      if (
        this.settings &&
        (b.settingsRevision > this.settings.settingsRevision ||
          (fresh && this.hadGap))
      )
        this.refresh();
      this.hadGap = false;
    } else if (name.startsWith("transport.") || name === "auth.error") {
      this.online = false;
      this.bind();
      this.audio.stop();
      this.status =
        name === "transport.connect"
          ? "Authenticating"
          : name === "auth.error"
            ? "Pairing rejected"
            : "Reconnecting";
      this.hadGap = true;
      this.record({
        type: name,
        origin: "client",
        data: { status: this.status },
      });
    } else if (name === "debug.telemetry") {
      this.telemetry = b;
    } else if (name === "debug.event" && b.schemaVersion === 1) {
      const prev = this.lastSeq;
      if (prev?.boot === b.bootId && b.seq <= prev.seq) return;
      if (prev?.boot === b.bootId && b.seq > prev.seq + 1)
        this.record({
          type: "Sequence gap",
          origin: "client",
          data: { from: prev.seq, to: b.seq },
        });
      this.lastSeq = { boot: b.bootId, seq: b.seq };
      this.record(b);
    }
    this.changed();
  }
  report(e) {
    this.message = errorText(e);
    this.changed();
  }
  async refresh() {
    const dev = this.device;
    try {
      const fresh = await dev.request("GET", "/v1/settings");
      if (
        dev !== this.device ||
        fresh.settingsRevision < this.settings.settingsRevision
      )
        return;
      // Rebase untouched fields so retrying a conflict cannot undo another client's edits.
      const merged = structuredCopy(fresh);
      for (const group of ["audio", "buzzer", "haptics"]) {
        for (const field of Object.keys(this.draft[group])) {
          if (this.draft[group][field] !== this.settings[group][field])
            merged[group][field] = this.draft[group][field];
        }
      }
      this.draft = merged;
      this.settings = fresh;
      this.changed();
    } catch (e) {
      if (dev === this.device) this.report(e);
    }
  }
  async command(path, body = {}, method = "POST") {
    const dev = this.device;
    if (!this.online || this.busy || !dev) return false;
    this.busy = true;
    this.message = "";
    this.changed();
    try {
      await dev.request(method, path, body);
      const b = await dev.request("GET", "/v1/state");
      if (dev !== this.device) return false;
      this.snapshot(b);
      if (path === "/v1/settings") {
        const fresh = await dev.request("GET", "/v1/settings");
        if (dev !== this.device) return false;
        this.settings = fresh;
        this.draft = structuredCopy(fresh);
        this.message = "Settings saved · revision " + fresh.settingsRevision;
      }
      return true;
    } catch (e) {
      if (dev === this.device) {
        this.report(e);
        if (e.message === "HTTP 409") await this.refresh();
        try {
          const b = await dev.request("GET", "/v1/state");
          if (dev === this.device) this.snapshot(b);
        } catch {
          /* existing notice remains */
        }
      }
      return false;
    } finally {
      if (dev === this.device) {
        this.busy = false;
        this.changed();
      }
    }
  }
  save() {
    const { settingsRevision, ...fields } = this.draft;
    return this.command(
      "/v1/settings",
      { ...fields, baseRevision: this.settings.settingsRevision },
      "PUT",
    );
  }
  stop() {
    this.audio.stop();
    this.router.bind(null, null);
    if (!this.online) {
      this.message =
        "Phone audio stopped. Board stop unconfirmed. Reconnect or stop the App Lab app.";
      this.changed();
      return;
    }
    return this.command("/v1/session/stop", {
      sessionId: this.board.sessionId,
    });
  }
}
export function errorText(e) {
  return (
    {
      "HTTP 409":
        "Board state changed. Review the latest revision and your draft before retrying.",
      "HTTP 422":
        "The board rejected these settings. Check its supported values.",
      "HTTP 503": "The board could not apply the command.",
      "HTTP 401": "Pair again using the board code.",
      "HTTP 403": "This controller is not authorized.",
      "Failed to fetch":
        "Board unreachable. Check Wi-Fi, address, HTTPS and allowed browser origin.",
    }[e.message] ||
    e.message ||
    "Request failed."
  );
}
