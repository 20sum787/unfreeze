import { Controller, errorText } from "./controller.js";
import { buzzerPreset, hapticsPreset } from "./cue-defaults.js";
import { structuredCopy } from "./demo.js";
import {
  checkHealth,
  forgetPairing,
  makeAudio,
  normalize,
  onEnded,
  openDevice,
  platform,
  rpc,
  tracks,
} from "./platform.js";

const el = (id) => document.getElementById(id);
const all = (selector) => [...document.querySelectorAll(selector)];
const text = (id, value) => {
  el(id).textContent = value;
};
if (platform === "Android") {
  document.querySelector('a[href="/preview"]').addEventListener("click", async (event) => {
    event.preventDefault();
    try {
      await rpc("camera.preview", {host: el("host").value});
    } catch (error) {
      app.report(error);
    }
  });
  text(
    "network-setup",
    "Turn on this phone’s Wi-Fi hotspot, then connect the UNO Q to it.",
  );
}
const audio = makeAudio();
const app = new Controller(audio, openDevice, render);
const outputPresets = [
  { id: "buzzer-defaults", group: "buzzer", values: buzzerPreset },
  { id: "vibro-defaults", group: "haptics", values: hapticsPreset },
];
onEnded((key) => app.router.ended(key));
const prefsKey = "unfreeze.preferences.v1";
let prefs;
try {
  prefs = JSON.parse(localStorage.getItem(prefsKey) || "{}") || {};
} catch {
  prefs = {};
}
prefs.track = tracks.some((t) => t.id === prefs.track) ? prefs.track : "piano";
prefs.volume = Number.isFinite(prefs.volume)
  ? Math.min(1, Math.max(0, prefs.volume))
  : 0.65;
const usbForward = ["127.0.0.1", "localhost"].includes(location.hostname) && location.port === "17000";
if (usbForward) el("host").defaultValue = location.host;
el("host").value = usbForward ? location.host : prefs.host || el("host").defaultValue;
el("track").replaceChildren(
  ...tracks.map((t) => new Option(t.name + " · " + t.bpm + " BPM", t.id)),
);
el("track").value = prefs.track;
el("volume").value = Math.round(prefs.volume * 100);
function store() {
  localStorage.setItem(prefsKey, JSON.stringify(prefs));
}
let page = "session",
  paused = false,
  latestLog,
  lastSettings,
  lastCaps,
  previewId;
async function unlock() {
  await audio.unlock();
  await app.heartbeat();
}
function act(id, fn) {
  el(id).addEventListener("click", async () => {
    try {
      await fn();
    } catch (e) {
      app.report(e);
    }
  });
}
function go(target, historyMode = true) {
  if (
    !["session", "device", "sound", "vibration", "diagnostics"].includes(target)
  )
    target = "session";
  page = target;
  for (const section of all("main>section"))
    section.hidden = section.id !== page;
  for (const btn of all("[data-page]"))
    btn.setAttribute(
      "aria-current",
      btn.dataset.page === page ? "page" : "false",
    );
  app.diagnostics(page === "diagnostics" || app.demo);
  if (historyMode && location.hash !== "#" + page)
    history.pushState(null, "", "#" + page);
  render();
}
for (const btn of all("[data-page]")) btn.onclick = () => go(btn.dataset.page);
window.addEventListener("popstate", () => go(location.hash.slice(1), false));
window.unfreezeBack = () => {
  if (page === "session") return false;
  go("session");
  return true;
};
function options(id, items, current, label = String) {
  const select = el(id);
  select.replaceChildren(...items.map((v) => new Option(label(v), v)));
  if (current != null) select.value = current;
}
function range(id, limits, value) {
  const n = el(id);
  if (limits) {
    n.min = limits[0];
    n.max = limits[1];
  }
  n.value = value ?? "";
}
function renderSettings() {
  const d = app.draft,
    c = app.caps;
  if (c !== lastCaps || d !== lastSettings) {
    options("mode", c?.audioModes || [], d?.audio.mode, (v) =>
      v === "phone_preferred" ? "Phone preferred" : "Board Buzzer",
    );
    options(
      "level",
      c?.hapticsLimits?.levelsPercent || [],
      d?.haptics.levelPercent,
      (v) => v + "%",
    );
    range("pitch", c?.buzzerLimits?.toneHz, d?.buzzer.toneHz);
    range("buzz-bpm", c?.buzzerLimits?.cadenceBpm, d?.buzzer.cadenceBpm);
    range("vib-bpm", c?.hapticsLimits?.cadenceBpm, d?.haptics.cadenceBpm);
    el("enabled").checked = !!d?.haptics.enabled;
    lastCaps = c;
    lastSettings = d;
  }
  for (const id of [
    "mode",
    "pitch",
    "buzz-bpm",
    "level",
    "vib-bpm",
    "enabled",
  ]) {
    const supported = ["pitch", "buzz-bpm"].includes(id)
      ? c?.buzzerSupported
      : id === "mode"
        ? true
        : c?.hapticsSupported;
    el(id).disabled = !d || !app.online || !supported || app.busy;
  }
  const edited = d && JSON.stringify(d) !== JSON.stringify(app.settings);
  for (const b of all(".save,.reset"))
    b.disabled = !app.online || !edited || app.busy;
  for (const { id, values } of outputPresets)
    el(id).disabled = !d || !app.online || app.busy || !values(c);
  for (const p of all(".revision"))
    p.textContent = d
      ? "Applied revision " +
        app.settings.settingsRevision +
        (edited ? " · Unsaved changes" : "")
      : "Connect a device to edit board settings.";
  el("preview").disabled =
    !app.online ||
    !c?.hapticsSupported ||
    app.board?.sessionState !== "IDLE" ||
    app.busy;
  el("stop-vib").disabled = !app.online || !c?.hapticsSupported || app.busy;
  const idle = app.online && app.board?.sessionState === "IDLE" && !app.busy;
  el("test-buzz").disabled = el("quick-buzz").disabled = !idle || !c?.buzzerSupported || !!app.board?.doorAudio;
  el("quick-vib").disabled = el("preview").disabled || !!app.board?.hapticsOutput;
  el("stop-buzz").disabled = !idle || !app.board?.doorAudio;
  el("stop-tests").disabled = !idle || !(app.board?.doorAudio || app.board?.hapticsOutput);
}
function safeDetail(object) {
  return JSON.stringify(
    object,
    (key, v) =>
      /token|pass(word)?|pairingcode|authorization|secret/i.test(key)
        ? "[redacted]"
        : v,
    2,
  ).slice(0, 6000);
}
function renderLog() {
  if (paused || page !== "diagnostics") return;
  text(
    "telemetry",
    app.telemetry ? safeDetail(app.telemetry) : "Waiting for telemetry.",
  );
  if (app.logs === latestLog) return;
  latestLog = app.logs;
  const expanded = new Set(
    all("#timeline details[open]").map((d) => d.dataset.id),
  );
  el("events-empty").hidden = app.logs.length > 0;
  el("timeline").replaceChildren(
    ...app.logs.map((e) => {
      const d = document.createElement("details"),
        title = document.createElement("summary"),
        origin = document.createElement("small"),
        detail = document.createElement("pre");
      d.dataset.id = [e.bootId, e.sessionId, e.eventId].join("/");
      d.open = expanded.has(d.dataset.id);
      title.textContent = e.type + " ";
      origin.textContent = " · " + e.origin;
      title.append(origin);
      detail.textContent = safeDetail(e);
      d.append(title, detail);
      return d;
    }),
  );
}
function timeLabel() {
  const s = Math.max(0, Math.ceil((app.deadline - app.now()) / 1000));
  return (
    String(Math.floor(s / 60)).padStart(2, "0") +
    ":" +
    String(s % 60).padStart(2, "0")
  );
}
function render() {
  const b = app.board,
    active = b?.sessionState === "ACTIVE";
  text("link-state", app.status);
  el("link-state").classList.toggle("online", !!app.online);
  text("notice", app.message || "");
  el("notice").hidden = !app.message;
  text(
    "phase",
    !app.online
      ? b
        ? "Connection lost"
        : "Disconnected"
      : {
          IDLE: "Ready",
          ACTIVE: "Active",
          STOPPING: "Stopping",
          FAULT: "Fault",
        }[b?.sessionState] || "Connecting",
  );
  text(
    "session-device",
    b
      ? [
          b.deviceId,
          b.faultCode || (app.demo ? "Simulated session" : "Wearable session"),
        ].join(" · ")
      : "Pair a UNO Q or open the demo to begin.",
  );
  text("remaining", active && app.online ? timeLabel() : "—");
  const output = (x) =>
    x ? [x.output, x.state, x.reason].filter(Boolean).join(" · ") : "Idle";
  text("door", output(b?.doorAudio));
  text("haptic", output(b?.hapticsOutput));
  text("vision", "Camera · " + (b?.visionStatus || "unknown"));
  text("motion", "Movement · " + (b?.motionStatus || "unknown"));
  text("diag-vision", b?.visionStatus || "Unknown");
  text("diag-motion", b?.motionStatus || "Unknown");
  text(
    "board-id",
    b
      ? "Device · " +
          b.deviceId +
          " / " +
          (app.caps?.firmwareVersion || "unknown firmware")
      : "",
  );
  el("start").disabled = !app.online || app.busy || b?.sessionState !== "IDLE";
  el("stop").disabled =
    !b ||
    (app.online && (app.busy || (!active && b?.sessionState !== "FAULT")));
  el("open-device").hidden = !!app.online;
  el("sim-tools").hidden = !app.demo;
  el("demo-door").disabled = el("demo-risk").disabled = !active;
  el("connect").disabled = el("demo").disabled = app.busy;
  el("disconnect").disabled = !app.device && !app.busy;
  renderSettings();
  renderLog();
}
function edit(group, key, value) {
  if (app.draft) {
    app.draft[group][key] = value;
    previewId = null;
    render();
  }
}
for (const [id, section, key] of [
  ["pitch", "buzzer", "toneHz"],
  ["buzz-bpm", "buzzer", "cadenceBpm"],
  ["vib-bpm", "haptics", "cadenceBpm"],
]) {
  el(id).oninput = (e) =>
    edit(section, key, e.target.value === "" ? null : Number(e.target.value));
}
el("mode").onchange = (e) => edit("audio", "mode", e.target.value);
el("level").onchange = (e) =>
  edit("haptics", "levelPercent", Number(e.target.value));
el("enabled").onchange = (e) => edit("haptics", "enabled", e.target.checked);
function validDraft(fields = ["pitch", "buzz-bpm", "vib-bpm"]) {
  for (const id of fields) {
    const field = el(id);
    if (!field.disabled && (!field.value || !field.checkValidity())) {
      app.report(
        Error(
          "Enter " +
            field.parentElement.firstChild.textContent.trim() +
            " between " +
            field.min +
            " and " +
            field.max +
            ".",
        ),
      );
      return false;
    }
  }
  return true;
}
for (const b of all(".save"))
  b.onclick = () => {
    if (validDraft()) app.save();
  };
for (const b of all(".reset"))
  b.onclick = () => {
    app.draft = structuredCopy(app.settings);
    previewId = null;
    render();
  };
for (const { id, group, values } of outputPresets)
  act(id, () => {
    app.draft = {
      ...app.draft,
      [group]: { ...app.draft[group], ...values(app.caps) },
    };
    previewId = null;
    render();
  });
act("open-device", () => go("device"));
act("health", async () => {
  await checkHealth(normalize(el("host").value));
  app.message = "Board reachable · API v1";
  render();
});
act("connect", async () => {
  const host = normalize(el("host").value),
    code = el("code").value.trim();
  el("code").value = "";
  await unlock().catch(() => {});
  await app.connect(host, code, false);
  if (app.device) {
    prefs.host = host;
    store();
    go("session");
  }
});
act("demo", async () => {
  await unlock().catch(() => {});
  await app.connect("", "", true);
  if (app.device) go("session");
});
act("disconnect", () => app.disconnect());
act("forget", async () => {
  app.disconnect();
  await forgetPairing();
  prefs.host = "";
  el("host").value = el("host").defaultValue;
  el("code").value = "";
  store();
  app.message = "Pairing removed.";
  render();
});
act("start", async () => {
  await unlock().catch(() => {});
  await app.command("/v1/session/start");
});
act("stop", () => app.stop());
act("demo-door", () => app.device?.approach?.());
act("demo-risk", () => app.device?.risk?.());
act("preview", async () => {
  if (!validDraft(["vib-bpm"])) return;
  previewId ??= Date.now() + "-" + Math.random().toString(36).slice(2);
  if (
    await app.command("/v1/haptics/preview", {
      requestId: previewId,
      levelPercent: app.draft.haptics.levelPercent,
      cadenceBpm: app.draft.haptics.cadenceBpm,
    })
  )
    previewId = null;
});
act("stop-vib", () => app.command("/v1/haptics/stop"));
act("quick-vib", () => el("preview").click());
act("quick-buzz", () => el("test-buzz").click());
act("test-buzz", async () => {
  if (!validDraft(["pitch", "buzz-bpm"])) return;
  await app.command("/v1/buzzer/preview", {
    ...app.draft.buzzer,
    requestId: Date.now() + "-" + Math.random().toString(36).slice(2),
  });
});
act("stop-buzz", () => app.command("/v1/buzzer/stop"));
act("stop-tests", () => app.stop());
async function configAudio() {
  if (prefs.track !== el("track").value) app.router.clear();
  prefs.track = el("track").value;
  prefs.volume = Number(el("volume").value) / 100;
  store();
  text("volume-text", Math.round(prefs.volume * 100) + "%");
  await audio.select(prefs.track, prefs.volume);
  if (app.online) await app.heartbeat();
}
el("track").onchange = () => configAudio().catch((e) => app.report(e));
el("volume").oninput = () => configAudio().catch((e) => app.report(e));
act("audition", async () => {
  if (app.router.active) throw Error("A wearable cue is already active.");
  await unlock();
  await audio.audition();
});
act("quiet", () => {
  app.router.clear();
});
act("pause", () => {
  paused = !paused;
  text("pause", paused ? "Resume updates" : "Pause updates");
  renderLog();
});
document.addEventListener("visibilitychange", () =>
  app.visibility(!document.hidden),
);
window.addEventListener("devicevisibility", (e) => app.visibility(e.detail));
window.addEventListener("pagehide", () => app.visibility(false));
window.addEventListener("pageshow", () => app.visibility(!document.hidden));
setInterval(() => {
  app.device?.tick?.();
  if (app.board?.sessionState === "ACTIVE")
    text("remaining", app.online ? timeLabel() : "—");
}, 500);
setInterval(() => app.heartbeat(), 2000);
configAudio().catch((e) => app.report(e));
go(location.hash.slice(1), false);
