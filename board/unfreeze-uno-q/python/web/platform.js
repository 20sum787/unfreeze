const native = window.UnfreezeNative;
const pending = new Map();
let sequence = 0;
let notifyNative = () => {};
let ended = () => {};
export const platform = native ? "Android" : "Browser";
export function onEnded(fn) {
  ended = fn;
}
export function rpc(op, args = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(Error("Android request timed out"));
    }, 12000);
    pending.set(id, { resolve, reject, timer });
    native.postMessage(JSON.stringify({ id, op, args }));
  });
}
window.unfreezeReceive = (raw) => {
  const m = JSON.parse(raw);
  if (m.signal === "audio.end") {
    ended(m.body);
    return;
  }
  if (m.signal === "foreground") {
    window.dispatchEvent(
      new CustomEvent("devicevisibility", { detail: m.body }),
    );
    return;
  }
  if (m.signal) {
    notifyNative(m);
    return;
  }
  const waiter = pending.get(m.id);
  if (!waiter) return;
  pending.delete(m.id);
  clearTimeout(waiter.timer);
  if (m.ok) waiter.resolve(m.value);
  else waiter.reject(Error(String(m.value)));
};

export function normalize(address) {
  const text = address.trim();
  if (!text) throw Error("Enter a board address and port.");
  const url = new URL(text.includes("://") ? text : "http://" + text);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    url.username ||
    url.password
  )
    throw Error("Enter only the board address and port.");
  return url.origin;
}
export async function checkHealth(host) {
  if (native) return rpc("health", { host });
  const health = await http(host, "GET", "/v1/health");
  if (health.apiVersion !== 1 || !health.ok)
    throw Error("Unsupported board API version.");
}
async function http(host, method, path, body, token) {
  const headers = {};
  if (body != null) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = "Bearer " + token;
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 4500);
  try {
    const r = await fetch(host + path, {
      method,
      headers,
      body: body == null ? undefined : JSON.stringify(body),
      redirect: "error",
      credentials: "omit",
      cache: "no-store",
      signal: abort.signal,
    });
    if (!r.ok) throw Error("HTTP " + r.status);
    return r.status === 204 ? {} : await r.json();
  } finally {
    clearTimeout(timer);
  }
}
const savedKey = "unfreeze.lan.v1";
export async function forgetPairing() {
  if (native) await rpc("forget");
  else sessionStorage.removeItem(savedKey);
}
export async function openDevice(address, code) {
  const host = normalize(address);
  if (native) {
    const channel = await rpc("open", { host, code });
    return {
      request: (method, path, body) =>
        rpc("request", { channel, method, path, body }),
      listen(fn) {
        notifyNative = (m) => {
          if (m.channel === channel) fn(m.signal, m.body);
        };
        return rpc("listen", { channel });
      },
      send: (name, body) =>
        rpc("send", { channel, name, body }).catch(() => {}),
      close: () => rpc("close", { channel }).catch(() => {}),
    };
  }
  await checkHealth(host);
  let pair = JSON.parse(sessionStorage.getItem(savedKey) || "null");
  if (code) {
    const result = await http(host, "POST", "/v1/pair", { code });
    if (!result.deviceId || !result.token)
      throw Error("Invalid pairing response.");
    pair = { host, deviceId: result.deviceId, token: result.token };
    sessionStorage.setItem(savedKey, JSON.stringify(pair));
  }
  if (pair?.host !== host)
    throw Error("Enter the pairing code for this board.");
  let socket;
  return {
    request: (method, path, body) => http(host, method, path, body, pair.token),
    listen(fn) {
      socket = window.io(host, { forceNew: true, autoConnect: false });
      socket.on("connect", () => {
        fn("transport.connect", {});
        socket.emit("client.hello", {
          token: pair.token,
          deviceId: pair.deviceId,
          apiVersion: 1,
        });
      });
      socket.on("disconnect", () => fn("transport.disconnect", {}));
      socket.on("connect_error", () => fn("transport.error", {}));
      for (const name of [
        "auth.error",
        "status.snapshot",
        "cue.audio.offer",
        "cue.audio.play",
        "cue.audio.cancel",
        "debug.event",
        "debug.telemetry",
      ])
        socket.on(name, (data) => fn(name, data));
      socket.connect();
    },
    send: (name, body) => {
      if (socket?.connected) socket.emit(name, body);
    },
    close: () => {
      socket?.removeAllListeners();
      socket?.disconnect();
    },
  };
}

export const tracks = [
  { id: "piano", name: "Piano", bpm: 90 },
  { id: "marimba", name: "Marimba", bpm: 100 },
  { id: "woodblock", name: "Woodblock", bpm: 85 },
  { id: "soft-drums", name: "Soft Drums", bpm: 90 },
  { id: "bass-pulse", name: "Bass Pulse", bpm: 105 },
  { id: "hand-percussion", name: "Hand Percussion", bpm: 110 },
];
export function makeAudio() {
  if (native)
    return {
      select: (track, volume) => rpc("audio.select", { track, volume }),
      unlock: async () => true,
      ready: () => rpc("audio.ready"),
      play: (key) => rpc("audio.play", key),
      stop: () => rpc("audio.stop").catch(() => {}),
      audition: () => rpc("audio.audition"),
    };
  let context,
    source,
    gainNode,
    buffer,
    loading,
    selected,
    gain = 0.65,
    activeKey;
  const cache = new Map();
  async function load(track) {
    if (!context) return;
    if (!cache.has(track))
      cache.set(
        track,
        (async () => {
          const response = await fetch("./tracks/" + track + ".wav");
          if (!response.ok) throw Error("Audio track unavailable");
          return context.decodeAudioData(await response.arrayBuffer());
        })().catch((e) => {
          cache.delete(track);
          throw e;
        }),
      );
    const decoded = await cache.get(track);
    if (selected === track) buffer = decoded;
  }
  function stop() {
    activeKey = null;
    if (source) {
      source.onended = null;
      try {
        source.stop();
      } catch {}
      source.disconnect();
      source = null;
    }
  }
  async function play(key) {
    if (context?.state !== "running" || !buffer || gain <= 0)
      throw Error("Enable audio on this device.");
    stop();
    activeKey = key;
    source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(gainNode);
    source.onended = () => {
      source?.disconnect();
      source = null;
      if (activeKey) ended(activeKey);
      activeKey = null;
    };
    source.start();
    // Resolve after the rendering clock advances beyond the scheduled start.
    const start = context.currentTime;
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 10));
      if (
        context.state === "running" &&
        context.currentTime > start &&
        activeKey === key
      )
        return;
    }
    throw Error("Audio output did not start.");
  }
  return {
    async select(track, volume) {
      gain = volume;
      if (gainNode) gainNode.gain.value = volume;
      if (selected !== track) {
        stop();
        buffer = null;
        selected = track;
        loading = load(track);
        await loading;
      }
    },
    async unlock() {
      context ??= new AudioContext();
      if (!gainNode) {
        gainNode = context.createGain();
        gainNode.gain.value = gain;
        gainNode.connect(context.destination);
      }
      await context.resume();
      await load(selected || "piano");
    },
    ready: async () => context?.state === "running" && !!buffer && gain > 0,
    play,
    stop,
    audition: () => play(null),
  };
}
