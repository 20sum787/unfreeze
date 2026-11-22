/** One foreground cue at a time. Session binding and local monotonic TTL survive async player callbacks. */
export class CueRouter {
  constructor(player, send, now = () => performance.now()) {
    this.player = player;
    this.send = send;
    this.now = now;
    this.seen = new Set();
  }
  bind(boot, session) {
    if (this.boot === boot && this.session === session) return;
    this.clear();
    this.boot = boot;
    this.session = session;
  }
  clear() {
    this.active = null;
    this.player.stop();
  }
  ended(key) {
    if (
      this.active?.key.cueId === key.cueId &&
      this.active.key.sessionId === key.sessionId
    )
      this.active = null;
  }
  async handle(name, key) {
    if (
      !this.boot ||
      !this.session ||
      key.sessionId !== this.session ||
      !key.cueId
    )
      return;
    const identity = JSON.stringify([this.boot, key.sessionId, key.cueId]);
    if (name === "cue.audio.offer") {
      if (this.seen.has(identity)) return;
      this.seen.add(identity);
      if (this.seen.size > 512)
        this.seen.delete(this.seen.values().next().value);
      if (this.active && this.active.stage !== "playing" && this.now() >= this.active.until)
        this.active = null;
      if (
        this.active ||
        !Number.isFinite(key.ttlMs) ||
        key.ttlMs <= 0 ||
        key.ttlMs > 2000
      ) {
        this.send("cue.audio.failed", key);
        return;
      }
      const cue = { key, stage: "offered", until: this.now() + key.ttlMs };
      this.active = cue;
      let ready = false;
      try {
        ready = await this.player.ready();
      } catch {
        /* Fail this offer below. */
      }
      if (this.active !== cue) return;
      if (ready && this.now() < cue.until) {
        cue.stage = "ready";
        this.send("cue.audio.ready", key);
      }
      else {
        this.active = null;
        this.send("cue.audio.failed", key);
      }
      return;
    }
    const cue = this.active;
    if (!cue || cue.key.cueId !== key.cueId) return;
    if (name === "cue.audio.cancel") {
      this.clear();
      return;
    }
    if (name !== "cue.audio.play" || cue.stage !== "ready") return;
    if (this.now() >= cue.until) {
      this.active = null;
      this.send("cue.audio.failed", key);
      return;
    }
    cue.stage = "playing";
    try {
      await this.player.play(key);
      if (this.active === cue) this.send("cue.audio.started", key);
    } catch {
      if (this.active === cue) {
        this.clear();
        this.send("cue.audio.failed", key);
      }
    }
  }
}
