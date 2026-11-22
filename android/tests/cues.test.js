import test from "node:test";
import assert from "node:assert/strict";
import { CueRouter } from "../../board/unfreeze-uno-q/python/web/cues.js";

function rig() {
  let now = 100,
    plays = 0,
    stops = 0;
  const sent = [];
  const player = {
    ready: async () => true,
    play: async () => {
      plays++;
    },
    stop: () => {
      stops++;
    },
  };
  const router = new CueRouter(
    player,
    (name, key) => sent.push([name, key.cueId]),
    () => now,
  );
  router.bind("boot", "s");
  return {
    router,
    sent,
    player,
    advance: (n) => (now += n),
    plays: () => plays,
    stops: () => stops,
  };
}
const key = { sessionId: "s", cueId: "one", ttlMs: 500 };
test("play arriving before readiness cannot start a track", async () => {
  const r = rig();
  let resolve;
  r.player.ready = () => new Promise(done => { resolve = done; });
  const offer = r.router.handle("cue.audio.offer", key);
  await r.router.handle("cue.audio.play", key);
  assert.equal(r.plays(), 0);
  resolve(true);
  await offer;
  await r.router.handle("cue.audio.play", key);
  assert.equal(r.plays(), 1);
});
test("an offer is silent; two play messages start a single track", async () => {
  const r = rig();
  await r.router.handle("cue.audio.offer", key);
  assert.equal(r.plays(), 0);
  await r.router.handle("cue.audio.play", key);
  await r.router.handle("cue.audio.play", key);
  assert.equal(r.plays(), 1);
  assert.deepEqual(
    r.sent.map((v) => v[0]),
    ["cue.audio.ready", "cue.audio.started"],
  );
});
test("late playback and wrong-session cancellation are ignored", async () => {
  const r = rig();
  await r.router.handle("cue.audio.offer", key);
  r.advance(501);
  await r.router.handle("cue.audio.play", key);
  assert.equal(r.plays(), 0);
  await r.router.handle("cue.audio.offer", { ...key, cueId: "two" });
  await r.router.handle("cue.audio.play", { ...key, cueId: "two" });
  const before = r.stops();
  await r.router.handle("cue.audio.cancel", { sessionId: "old", cueId: "two" });
  assert.equal(r.stops(), before);
});
