import assert from "node:assert/strict";
import http from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { Server } from "socket.io";
import { DemoBoard } from "../../board/unfreeze-uno-q/python/web/demo.js";

const webRoot = fileURLToPath(new URL("../../board/unfreeze-uno-q/python/web/", import.meta.url));
const site = http.createServer(async (req, res) => {
  const pathname = new URL(req.url, "http://localhost").pathname;
  const file = path.resolve(
    webRoot,
    "." + (pathname === "/" ? "/index.html" : pathname),
  );
  try {
    assert.ok(file.startsWith(path.resolve(webRoot) + path.sep));
    const bytes = await readFile(file);
    const types = {
      ".js": "text/javascript",
      ".html": "text/html",
      ".css": "text/css",
      ".wav": "audio/wav",
    };
    res
      .writeHead(200, {
        "Content-Type": types[path.extname(file)] || "application/octet-stream",
      })
      .end(bytes);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => site.listen(0, "127.0.0.1", r));
const origin = "http://127.0.0.1:" + site.address().port;
const board = new DemoBoard(),
  replies = [];
const httpd = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Authorization,Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204).end();
    return;
  }
  let input = "";
  for await (const piece of req) input += piece;
  const b = input ? JSON.parse(input) : {};
  let data;
  try {
    if (req.url === "/v1/health") data = { ok: true, apiVersion: 1 };
    else if (req.url === "/v1/pair" && b.code === "246810")
      data = { deviceId: "bench", token: "fixture-only" };
    else if (req.headers.authorization === "Bearer fixture-only")
      data = await board.request(req.method, req.url, b);
    else {
      res.writeHead(401).end();
      return;
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(data));
  } catch {
    res.writeHead(422).end();
  }
});
const io = new Server(httpd, { cors: { origin } });
io.on("connection", (s) => {
  s.on("client.hello", (b) => {
    if (b.token !== "fixture-only") return;
    board.listen((n, b) => s.emit(n, b));
    for (const n of [
      "client.status",
      "debug.subscribe",
      "debug.unsubscribe",
      "cue.audio.ready",
      "cue.audio.started",
      "cue.audio.failed",
    ])
      s.on(n, (b) => {
        replies.push(n);
        board.send(n, b);
      });
  });
});
await new Promise((r) => httpd.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-proxy-server"],
});
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  // The CI host has no physical audio endpoint. Use Chromium's silent rendering sink.
  await page.addInitScript(() => {
    const Real = window.AudioContext;
    window.AudioContext = class extends Real {
      constructor(options) {
        super({ ...options, sinkId: { type: "none" } });
      }
    };
  });
  const errors = [];
  page.on("pageerror", (e) => {
    errors.push(e.message);
    console.log("pageerror", e.message);
  });
  page.setDefaultTimeout(7000);
  await page.goto(origin);
  await page.click("#open-device");
  await page.click("#demo");
  await page.click("#start");
  await page.waitForFunction(
    () => document.querySelector("#phase").textContent === "Active",
  );
  await page.click("#demo-door");
  await page.waitForFunction(() =>
    document.querySelector("#door").textContent.includes("phone_audio"),
  );
  await page.click("#demo-risk");
  await page.waitForFunction(() =>
    document.querySelector("#haptic").textContent.includes("vibro"),
  );
  await page.click("[data-page=diagnostics]");
  assert.match(await page.locator("#timeline").innerText(), /simulated/);
  await page.click("[data-page=vibration]");
  await page.fill("#vib-bpm", "104");
  await page.click("#vibration .save");
  await page.waitForFunction(() =>
    document
      .querySelector("#vibration .revision")
      .textContent.includes("revision 2"),
  );
  await page.click("[data-page=sound]");
  await page.selectOption("#track", "marimba");
  await page.click("#audition");
  await page.click("#quiet");
  await page.click("[data-page=session]");
  await page.click("#stop");
  await page.click("[data-page=vibration]");
  await page.click("#preview");
  await page.click("#stop-vib");
  for (const width of [390, 1100]) {
    await page.setViewportSize({ width, height: 820 });
    for (const tab of [
      "session",
      "device",
      "sound",
      "vibration",
      "diagnostics",
    ]) {
      await page.click("[data-page=" + tab + "]");
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
        tab + " horizontal overflow",
      );
    }
  }
  await page.click("[data-page=device]");
  await page.click("#disconnect");
  await page.fill("#host", "127.0.0.1:" + httpd.address().port);
  await page.fill("#code", "246810");
  await page.click("#connect");
  await page.waitForFunction(
    () => document.querySelector("#link-state").textContent === "Connected",
  );
  await page.click("#start");
  await page.waitForFunction(
    () => document.querySelector("#phase").textContent === "Active",
  );
  board.approach();
  await page.waitForFunction(() =>
    document.querySelector("#door").textContent.includes("phone_audio"),
  );
  assert.ok(
    replies.includes("cue.audio.ready") &&
      replies.includes("cue.audio.started"),
  );
  const seen = replies.filter((n) => n === "cue.audio.started").length;
  for (const s of io.sockets.sockets.values()) s.conn.close();
  await page.waitForFunction(
    () => document.querySelector("#link-state").textContent === "Reconnecting",
  );
  await page.waitForFunction(
    () => document.querySelector("#link-state").textContent === "Connected",
  );
  assert.equal(replies.filter((n) => n === "cue.audio.started").length, seen);
  await page.click("#stop");
  await page.waitForFunction(
    () => document.querySelector("#phase").textContent === "Ready",
  );
  await page.reload();
  await page.click("[data-page=sound]");
  assert.equal(await page.inputValue("#track"), "marimba");
  assert.deepEqual(errors, []);
  console.log(
    "PASS: five responsive pages, demo, audio, revisioned settings, preview, live HTTP/Socket.IO fixture, reconnect and preferences.",
  );
} finally {
  await browser.close();
  board.close();
  await io.close();
  httpd.close();
  site.close();
}
