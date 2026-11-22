import test from "node:test";
import assert from "node:assert/strict";
import { Controller } from "../../board/unfreeze-uno-q/python/web/controller.js";
import { buzzerPreset, hapticsPreset } from "../../board/unfreeze-uno-q/python/web/cue-defaults.js";
import { DemoBoard } from "../../board/unfreeze-uno-q/python/web/demo.js";

function rig() {
  let time = 1000;
  const player = {
    ready: async () => false,
    play: async () => {},
    stop: () => {},
  };
  const c = new Controller(
    player,
    () => {},
    () => {},
    () => time,
  );
  return { c, step: (ms) => (time += ms) };
}
test("one demo session routes offline audio to the buzzer while motion drives Vibro independently", async () => {
  const { c } = rig();
  await c.connect("", "", true);
  c.diagnostics(true);
  await c.command("/v1/session/start");
  c.device.approach();
  c.device.risk();
  assert.equal(c.board.doorAudio.output, "buzzer");
  assert.equal(c.board.hapticsOutput.output, "vibro");
  assert.ok(c.logs.every((e) => e.origin === "simulated"));
  assert.ok(c.logs.some((e) => e.eventId === c.board.doorAudio.triggerEventId));
  await c.stop();
  assert.equal(c.board.sessionState, "IDLE");
  assert.equal(c.board.hapticsOutput, null);
  c.disconnect();
});
test("preview is idle-only, invalid settings do not advance revision, sessions expire", async () => {
  const { c, step } = rig();
  await c.connect("", "", true);
  c.draft.haptics.levelPercent = 99;
  assert.equal(await c.save(), false);
  assert.equal(c.settings.settingsRevision, 1);
  await c.command("/v1/session/start");
  assert.equal(
    await c.command("/v1/haptics/preview", { requestId: "preview" }),
    false,
  );
  step(900001);
  c.device.tick();
  assert.equal(c.board.sessionState, "IDLE");
  c.disconnect();
});
test("demo presets follow the board ranges and discrete vibration levels", async () => {
  const board = new DemoBoard();
  const defaults = await board.request("GET", "/v1/settings");
  assert.deepEqual(buzzerPreset(board.caps), defaults.buzzer);
  assert.deepEqual(hapticsPreset(board.caps), {
    levelPercent: defaults.haptics.levelPercent,
    cadenceBpm: defaults.haptics.cadenceBpm,
  });
  assert.deepEqual(buzzerPreset({
    buzzerSupported: true,
    buzzerLimits: { toneHz: [1200, 1800], cadenceBpm: [60, 80] },
  }), { toneHz: 1200, cadenceBpm: 80 });
  assert.deepEqual(hapticsPreset({
    hapticsSupported: true,
    hapticsLimits: { cadenceBpm: [95, 120], levelsPercent: [45, 35, 30] },
  }), { levelPercent: 35, cadenceBpm: 95 });
  assert.equal(hapticsPreset({ hapticsSupported: false }), null);
});
test("settings conflict retains draft, loads latest revision and lets user retry", async () => {
  const b = new DemoBoard();
  const c = new Controller(
    { stop() {}, ready: async () => false },
    async () => b,
    () => {},
  );
  await c.connect("host", "code", false);
  c.draft.buzzer.toneHz = 1200;
  b.settings.settingsRevision++;
  assert.equal(await c.save(), false);
  assert.equal(c.draft.buzzer.toneHz, 1200);
  assert.equal(c.settings.settingsRevision, 2);
  assert.equal(await c.save(), true);
  assert.equal(c.settings.buzzer.toneHz, 1200);
  c.disconnect();
});
test("a superseded connection cannot replace the current board", async () => {
  let release;
  const delayed = new Promise((r) => (release = r));
  const old = new DemoBoard();
  const c = new Controller(
    { stop() {}, ready: async () => false },
    () => delayed,
    () => {},
  );
  const first = c.connect("old", "", false);
  await c.connect("", "", true);
  const current = c.device;
  release(old);
  await first;
  assert.equal(c.device, current);
  c.disconnect();
});

test("actuator availability follows live snapshots after pairing", async () => {
  const c = new Controller({ stop() {}, ready: async () => false }, null, () => {});
  await c.connect("", "", true);
  for (const connected of [false, true]) {
    c.event("status.snapshot", { ...c.board, buzzerSupported: connected, hapticsSupported: connected });
    assert.equal(c.caps.buzzerSupported, connected);
    assert.equal(c.caps.hapticsSupported, connected);
    assert.ok(c.caps.hapticsLimits);
  }
  c.disconnect();
});
