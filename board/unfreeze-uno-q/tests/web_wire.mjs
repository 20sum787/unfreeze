// Actual shipped web modules over a real WebSocket. Audio hardware is a stand-in.
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { strict as assert } from "node:assert";
import { setTimeout as sleep } from "node:timers/promises";
import { Controller } from "../python/web/controller.js";

const [host, code] = process.argv.slice(2);
const context = vm.createContext({WebSocket, URL, setTimeout, clearTimeout, console, performance});
context.self = context;
vm.runInContext(readFileSync(new URL("../python/web/vendor/socket.io-4.8.1.min.js", import.meta.url), "utf8"), context);
// Node has a WebSocket but no XMLHttpRequest. test_companion.py also exercises
// the default polling + upgrade path over real HTTP.
globalThis.window = {io: (url, options) => context.io(url, {...options, transports:["websocket"]})};
const storage = new Map();
globalThis.sessionStorage = {getItem:k=>storage.get(k), setItem:(k,v)=>storage.set(k,v)};
const {openDevice} = await import("../python/web/platform.js");
let starts = 0;
const audio = {stop(){}, async ready(){return true;}, async play(){ starts++; }};
const app = new Controller(audio, openDevice, ()=>{});
async function until(test) {
  for (let i=0;i<100;i++) { if(test()) return; await sleep(25); }
  throw Error("Expected state not reached: " + JSON.stringify([app.status,app.board,app.logs,app.message]));
}
try {
  await app.connect(host,code,false);
  await until(()=>app.online && app.board.phoneAudioReady);
  app.diagnostics(true);
  assert.equal(await app.command("/v1/session/start"),true);
  await app.device.request("POST","/v1/bench/event",{type:"door.approach"});
  await until(()=>app.board.doorAudio?.state==="started");
  assert.equal(starts,1);
  assert.equal(app.board.doorAudio.output,"phone_audio");
  assert.equal(app.logs.find(e=>e.type==="door.approach")?.origin,"simulated");
  assert.equal(await app.stop(),true);
  assert.equal(app.board.sessionState,"IDLE");
} finally {
  app.disconnect();
}
