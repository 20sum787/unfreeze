"""Real local HTTP and Engine.IO transports with a recording MCU stand-in.

Run on a computer with python/requirements-common.txt installed. Exercises real
shipped browser control logic too when Node 22+ and python/web are present.
"""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import aiohttp
import socketio

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "python"))
from companion import Companion


class RecordingMCU:
    def __init__(self):
        self.calls = []

    def record(self, name, *args):
        self.calls.append((name, *args))
        return True

    def buzzer(self, hz, bpm): return self.record("buzzer", hz, bpm)
    def vibro(self, level, bpm): return self.record("vibro", level, bpm)
    def freeze_pulses(self, level, bpm): return self.record("freeze_pulses", level, bpm)
    def freeze_alarm(self): return self.record("freeze_alarm")
    def stop_buzzer(self): return self.record("stop_buzzer")
    def stop_vibro(self): return self.record("stop_vibro")


class CompanionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hw = RecordingMCU()
        self.s = Companion(self.hw, self.temp.name, bench_enabled=True)
        self.s.status(vision="test", buzzer=True, vibro=True)
        self.s.start("127.0.0.1", 0)
        self.host = f"http://127.0.0.1:{self.s.port}"
        self.http = aiohttp.ClientSession()
        self.token = None
        self.sock = None

    async def asyncTearDown(self):
        if self.sock and self.sock.connected:
            await self.sock.disconnect()
        await self.http.close()
        await asyncio.to_thread(self.s.close)
        self.temp.cleanup()

    async def call(self, method, path, payload=None, expect=200):
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        async with self.http.request(method, self.host + "/v1/" + path, json=payload, headers=headers) as r:
            self.assertEqual(r.status, expect, await r.text())
            return await r.json()

    def code(self):
        return (Path(self.temp.name) / "pairing-code.txt").read_text().strip()

    async def pair(self):
        pair = await self.call("POST", "pair", {"code": self.code()})
        self.token = pair["token"]
        return pair

    async def test_custom_hardware_tests(self):
        buzz = {"requestId":"buzz-test", "toneHz":440, "cadenceBpm":90}
        await self.call("POST", "buzzer/preview", buzz, 401)
        await self.pair()
        await self.call("POST", "buzzer/preview", {**buzz, "toneHz":3100}, 422)
        for _ in range(2):
            await self.call("POST", "buzzer/preview", buzz)
        self.assertEqual(self.hw.calls.count(("buzzer", 440, 90)), 1)
        await self.call("POST", "haptics/preview", {"requestId":"vib-test","levelPercent":35,"cadenceBpm":80})
        state = await self.call("POST", "buzzer/stop", {})
        self.assertIsNone(state["doorAudio"])
        self.assertEqual(state["hapticsOutput"]["output"], "vibro")
        await self.call("POST", "haptics/stop", {})
        await self.call("POST", "session/start", {})
        await self.call("POST", "buzzer/preview", buzz, 409)

    async def test_credential_and_settings(self):
        await self.call("GET", "state", expect=401)
        self.assertEqual(await self.call("GET", "health"), {"ok": True, "apiVersion": 1})
        self.s.status(hold_ms=5000, cue_revision=3)
        self.assertEqual(await self.call("GET", "build"),
                         {"appBuild":"freeze-pulse-alarm-v3","mcuFreezeHoldMs":5000,"mcuCueRevision":3})
        async with self.http.options(self.host + "/v1/settings", headers={"Origin":"http://127.0.0.1:8765"}) as r:
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:8765")
        async with self.http.get(self.host + "/v1/health", headers={"Origin":"https://example.org"}) as r:
            self.assertEqual(r.status, 403)
        async with self.http.get(self.host + "/preview/camera", allow_redirects=False) as r:
            self.assertEqual(r.headers["Location"], "http://127.0.0.1:4912/embed")
        async with self.http.get(self.host + "/preview") as r:
            self.assertEqual(r.status, 200)
            self.assertIn('src="/preview/camera"', await r.text())
        if (APP / "python/web/index.html").is_file():
            async with self.http.get(self.host + "/") as r:
                self.assertEqual(await r.read(), (APP/"python/web/index.html").read_bytes())
            async with self.http.get(self.host + "/platform.js") as r:
                self.assertEqual(await r.read(), (APP/"python/web/platform.js").read_bytes())
        async with self.http.options(self.host + "/socket.io/?EIO=4&transport=polling", headers={
                "Origin":"http://127.0.0.1:8765", "Access-Control-Request-Private-Network":"true"}) as r:
            self.assertEqual(r.headers["Access-Control-Allow-Private-Network"], "true")
        code = self.code()
        pair = await self.pair()
        await self.call("POST", "pair", {"code":code}, 401)
        edit = {"baseRevision": 1, "buzzer": {"toneHz": 1200}}
        result = await self.call("PUT", "settings", edit)
        self.assertEqual(result["settingsRevision"], 2)
        await self.call("PUT", "settings", edit, 409)
        await self.call("PUT", "settings", {"baseRevision":2,"haptics":{"levelPercent":42}}, 422)
        await self.pair()
        self.token = pair["token"]
        await self.call("GET", "settings", expect=401)
        self.assertEqual(json.loads((Path(self.temp.name)/"settings.json").read_text()), result)

    async def test_readonly_preview_alongside_controller(self):
        await self.pair()
        state = await self.call("POST", "session/start", {})
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as viewer:
            async with viewer.get(self.host + "/preview") as page:
                self.assertEqual(page.status, 200)
                html = await page.text()
                self.assertIn('<html lang="en">', html)
                self.assertIn("Camera and cue status", html)
            async with viewer.get(self.host + "/preview.js") as script:
                self.assertIn("Freeze pulses", await script.text())
            async def read():
                async with viewer.get(self.host + "/v1/preview/state") as r:
                    self.assertEqual(r.status, 200)
                    return await r.json()
            async with viewer.get(self.host + "/v1/preview/state") as r:
                self.assertEqual(r.status, 401)
            async with viewer.post(self.host + "/v1/preview/access", json={"code": self.code()}) as r:
                self.assertEqual(r.status, 200)
            async with viewer.post(self.host + "/v1/session/stop", json={}) as r:
                self.assertEqual(r.status, 401)
            self.assertEqual((await read())["session"], "ACTIVE")
            self.s.telemetry("motion-model", {"scores": {"freeze": .82}, "windowAgeMs": 20})
            for _ in range(20):
                if (await read())["freeze"] == .82:
                    break
                await asyncio.sleep(.01)
            self.assertEqual((await read())["freeze"], .82)
            await self.call("POST", "bench/event", {"type": "door.approach"})
            await self.call("POST", "bench/event", {"type": "motion.freeze"})
            outputs = await read()
            self.assertEqual(outputs["audio"]["output"], "buzzer")
            self.assertEqual(outputs["haptics"]["state"], "applied")
            self.assertEqual(outputs["haptics"]["reason"], "freeze pulses 5 s")
            self.assertIn(("freeze_pulses", 40, 90), self.hw.calls)
            self.s.freeze_alarm({"scores": {"freeze": .82}}, session_id=state["sessionId"])
            for _ in range(40):
                if (await read())["audio"]["reason"] == "sustained freeze":
                    break
                await asyncio.sleep(.01)
            self.assertEqual((await read())["audio"]["reason"], "sustained freeze")
            self.assertIn(("freeze_alarm",), self.hw.calls)
            await self.call("POST", "session/stop", {"sessionId": state["sessionId"]})
            self.assertIsNone((await read())["freeze"])
            self.assertIsNone((await read())["audio"])
            await self.call("POST", "session/start", {})
            self.assertIsNone((await read())["freeze"])

    async def test_wire_timeout_independent_outputs_and_stop(self):
        pair = await self.pair()
        preview = {"requestId":"preview-A","levelPercent":35,"cadenceBpm":80}
        await self.call("POST", "haptics/preview", preview)
        await self.call("POST", "haptics/preview", preview)
        await self.call("POST", "haptics/stop", {})
        self.assertEqual(self.hw.calls.count(("vibro", 35, 80)), 1)
        self.sock = client = socketio.AsyncClient()
        queue = asyncio.Queue()
        for name in ("status.snapshot", "debug.event", "cue.audio.offer", "cue.audio.cancel"):
            client.on(name, lambda body, name=name: queue.put_nowait((name, body)))
        async def until(name, predicate=lambda body:True):
            async with asyncio.timeout(4):
                while True:
                    event, body = await queue.get()
                    if event == name and predicate(body):
                        return body
        await client.connect(self.host, transports=["polling","websocket"])
        self.assertEqual(client.transport(), "websocket")
        await client.emit("client.hello", {**pair, "apiVersion":1})
        self.assertEqual((await until("status.snapshot"))["sessionState"], "IDLE")
        await client.emit("debug.subscribe", {})
        await client.emit("client.status", {"audioReady":True})
        await until("status.snapshot", lambda b:b["phoneAudioReady"])
        state = await self.call("POST", "session/start", {})
        await self.call("POST", "bench/event", {"type":"door.approach"})
        offer = await until("cue.audio.offer")
        await self.call("POST", "bench/event", {"type":"motion.prefreeze"})
        await until("cue.audio.cancel")
        await client.emit("cue.audio.started", offer)  # stale after fallback
        state = await self.call("GET", "state")
        self.assertEqual(state["doorAudio"]["output"], "buzzer")
        self.assertEqual(state["hapticsOutput"]["output"], "vibro")
        self.assertEqual(self.hw.calls.count(("buzzer",1000,90)),1)
        await client.disconnect()
        self.assertEqual((await self.call("GET","state"))["sessionState"],"ACTIVE")
        await self.call("POST","session/stop",{"sessionId":"stale"},409)
        stopped = await self.call("POST","session/stop",{"sessionId":state["sessionId"]})
        self.assertEqual(stopped["sessionState"],"IDLE")
        self.assertIn(("stop_buzzer",), self.hw.calls)
        self.assertIn(("stop_vibro",), self.hw.calls)
        self.s.door({},session_id=state["sessionId"])
        await asyncio.sleep(.08)
        self.assertIsNone((await self.call("GET","state"))["doorAudio"])

    async def test_missing_modules_and_persisted_pairing(self):
        await self.pair()
        await self.call("PUT", "settings", {"baseRevision": 1, "buzzer": {"toneHz": 1250}})
        boot = (await self.call("GET", "state"))["bootId"]
        await asyncio.to_thread(self.s.close)
        self.s = Companion(self.hw, self.temp.name)
        self.s.start("127.0.0.1", 0)
        self.host = f"http://127.0.0.1:{self.s.port}"
        new_state = await self.call("GET", "state")
        self.assertNotEqual(boot, new_state["bootId"])
        self.assertEqual(new_state["sessionState"], "IDLE")
        self.assertEqual((await self.call("GET", "settings"))["buzzer"]["toneHz"], 1250)
        self.assertFalse((await self.call("GET", "capabilities"))["hapticsSupported"])
        state = await self.call("POST", "session/start", {})
        await self.call("POST", "bench/event", {"type":"door.approach"}, 404)
        self.s.door({}, session_id=state["sessionId"])
        self.s.motion("freeze", {}, session_id=state["sessionId"])
        async with asyncio.timeout(2):
            while True:
                observed = await self.call("GET", "state")
                if observed["hapticsOutput"] and observed["doorAudio"]:
                    break
                await asyncio.sleep(.02)
        self.assertEqual(observed["doorAudio"]["state"], "failed")
        self.assertEqual(observed["hapticsOutput"]["state"], "failed")
        stopped = await self.call("POST", "session/stop", {"sessionId":state["sessionId"]})
        self.assertEqual(stopped["sessionState"], "IDLE")
        self.assertEqual(self.hw.calls, [])

    async def test_original_web_client(self):
        if not shutil.which("node") or not (APP/"python/web/controller.js").exists():
            self.skipTest("Needs Node 22+ and the bundled companion web source")
        proc = await asyncio.to_thread(subprocess.run, ["node", str(APP/"tests"/"web_wire.mjs"),
            self.host, self.code()], capture_output=True, text=True, timeout=12)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn(("buzzer",1000,90), self.hw.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
