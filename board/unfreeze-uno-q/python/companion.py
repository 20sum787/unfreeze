"""Hotspot API for the shipped Unfreeze browser and Android companion (v1)."""
import asyncio
import json
import logging
import math
import secrets
import threading
import time
from pathlib import Path

from aiohttp import web
import socketio

from companion_settings import BoardFiles, Rejected
from cue_session import CueSession
from deployment_defaults import CAMERA_PORT, COMPANION_HOST, COMPANION_PORT


LOCAL_WEB = {"http://localhost:8765", "http://127.0.0.1:8765"}
CURRENT_SESSION = object()


def allowed_origin(origin, scheme, host):
    return not origin or origin in LOCAL_WEB or origin == f"{scheme}://{host}"


class Companion:
    def __init__(self, hardware, data_dir, *, bench_enabled=False, preview_port=CAMERA_PORT):
        self.files = BoardFiles(data_dir)
        self.bench_enabled = bench_enabled
        self.preview_port = preview_port
        self.viewer_token = secrets.token_urlsafe(32)
        self.freeze_sample = None
        self.io = socketio.AsyncServer(
            async_mode="aiohttp", async_handlers=False, logger=False, engineio_logger=False,
            max_http_buffer_size=32_768, ping_interval=5, ping_timeout=10,
            cors_allowed_origins=lambda origin, env: allowed_origin(
                origin, env["aiohttp.request"].scheme, env.get("HTTP_HOST")),
        )
        self.state = CueSession(hardware, self.files, self.io.emit)
        self.lock = asyncio.Lock()
        self.loop = None
        self.started = threading.Event()
        self.failure = None
        self.thread = None
        self.update_lock = threading.Lock()
        self.latest_updates = {}
        self._socket_handlers()

    def start(self, host=COMPANION_HOST, port=COMPANION_PORT):
        self.host, self.port = host, port
        self.thread = threading.Thread(target=self._thread_main, name="unfreeze-companion", daemon=True)
        self.thread.start()
        if not self.started.wait(10):
            raise RuntimeError("Companion service startup timed out")
        if self.failure:
            raise RuntimeError(f"Could not start companion on {host}:{port}") from self.failure
        print(f"Companion port {self.port}. Read current six-digit code locally in {self.files.root}/pairing-code.txt", flush=True)

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self.failure = exc
            logging.exception("Companion server exited")
        finally:
            self.loop = None
            self.started.set()

    async def _run(self):
        self.loop = asyncio.get_running_loop()
        self.finished = asyncio.Event()
        runner = web.AppRunner(self._app(), access_log=None, shutdown_timeout=1)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            if not self.port:
                self.port = runner.addresses[0][1]
            self.started.set()
            while not self.finished.is_set():
                async with self.lock:
                    await self.state.tick()
                    if time.monotonic() >= self.files.code_until:
                        self.files.rotate_code()
                await asyncio.sleep(0.04)
        finally:
            async with self.lock:
                try:
                    await self.state.stop()
                except Rejected as exc:
                    logging.warning("Shutdown: %s", exc)
                sid = self.state.controller
                self.state.controller = None
            if sid:
                await self.io.disconnect(sid)
            await self.io.shutdown()
            await runner.cleanup()

    def close(self):
        loop = self.loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self.finished.set)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(6)

    def session_token(self):
        return None if self.state.stop_fault else self.state.session

    def _dispatch(self, operation, *args, session_id=CURRENT_SESSION):
        loop = self.loop
        if not loop or not loop.is_running():
            return
        async def run():
            try:
                async with self.lock:
                    if session_id is CURRENT_SESSION or (session_id and session_id == self.session_token()):
                        await operation(*args)
            except Exception:
                logging.exception("Companion sensor callback failed")
        loop.call_soon_threadsafe(lambda: asyncio.create_task(run()))

    def door(self, data, origin="live", *, session_id=CURRENT_SESSION):
        self._dispatch(self.state.door, dict(data), origin, session_id=session_id)

    def continue_door_buzzer(self, session_id, observed):
        async def repeat():
            if session_id == self.session_token() and time.monotonic() - observed <= 0.5:
                await self.state.repeat_door_buzzer()
        self._latest("door_buzzer", repeat)

    def motion(self, kind, data, origin="live", *, session_id=CURRENT_SESSION):
        if kind not in ("prefreeze", "freeze"):
            raise ValueError("Expected prefreeze or freeze")
        self._dispatch(self.state.motion, kind, dict(data), origin, session_id=session_id)

    def freeze_alarm(self, data, *, session_id):
        self._dispatch(self.state.freeze_alarm, dict(data), session_id=session_id)

    def telemetry(self, source, data, origin="live"):
        session = self.session_token() if source == "motion-model" else None
        received = time.monotonic()
        async def publish():
            if source == "motion-model" and origin == "live" and session and session == self.session_token():
                score = data.get("scores", {}).get("freeze")
                age = data.get("windowAgeMs", 0)
                if type(score) in (float, int) and 0 <= score <= 1 and math.isfinite(age):
                    self.freeze_sample = (session, score, received - max(0, age) / 1000)
                else:
                    self.freeze_sample = None
            await self.state.event(source, source + ".telemetry", dict(data), origin, True)
        self._latest(("telemetry", source), publish)

    def _latest(self, key, operation):
        """Keep one pending update per sensor while the session lock or network is busy."""
        loop = self.loop
        if not loop or not loop.is_running():
            return
        with self.update_lock:
            scheduled = key in self.latest_updates
            self.latest_updates[key] = operation
        if scheduled:
            return

        async def deliver():
            with self.update_lock:
                pending = self.latest_updates.pop(key)
            await pending()
        self._dispatch(deliver)

    def status(self, vision=None, motion=None, buzzer=None, vibro=None, hold_ms=None, cue_revision=None):
        update = {"vision_status": vision, "motion_status": motion,
                  "buzzer_supported": buzzer, "vibro_supported": vibro, "mcu_hold_ms": hold_ms,
                  "mcu_cue_revision": cue_revision}
        update = {k: v for k, v in update.items() if v is not None}
        async def apply():
            changed = any(getattr(self.state, k) != v for k, v in update.items())
            for key, value in update.items():
                setattr(self.state, key, value)
            if changed:
                await self.state.publish()
        if self.thread is None:
            for key, value in update.items():
                setattr(self.state, key, value)
        else:
            self._latest(("status", tuple(sorted(update))), apply)

    def _app(self):
        @web.middleware
        async def api_policy(request, handler):
            if request.path == "/socket.io/" and request.method == "OPTIONS":
                origin = request.headers.get("Origin")
                if not allowed_origin(origin, request.scheme, request.host):
                    return web.Response(status=403)
                response = await handler(request)
                response.headers["Access-Control-Allow-Private-Network"] = "true"
                return response
            if not request.path.startswith("/v1/"):
                return await handler(request)
            origin = request.headers.get("Origin")
            if not allowed_origin(origin, request.scheme, request.host):
                return web.json_response({"error": "Origin not allowed"}, status=403)
            try:
                if request.method == "OPTIONS":
                    response = web.Response(status=204)
                else:
                    response = await handler(request)
            except Rejected as err:
                response = web.json_response({"error": str(err)}, status=err.status)
            except OSError:
                logging.exception("Board data storage failure")
                response = web.json_response({"error": "Board data unavailable"}, status=503)
            response.headers["Cache-Control"] = "no-store"
            if origin:
                response.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
                    "Access-Control-Allow-Headers": "Authorization,Content-Type",
                    "Access-Control-Allow-Private-Network": "true"})
            return response

        app = web.Application(middlewares=[api_policy], client_max_size=32_768)
        self.io.attach(app)
        app.router.add_route("*", "/v1/{path:.*}", self._rest)
        web_dir = Path(__file__).resolve().parent / "web"
        async def home(request):
            return web.FileResponse(web_dir / "index.html")
        async def camera_embed(request):
            raise web.HTTPFound(str(request.url.with_port(self.preview_port).with_path("/embed")))
        async def preview(request):
            return web.FileResponse(web_dir / "preview.html")
        app.router.add_get("/preview/camera", camera_embed)
        app.router.add_get("/preview", preview)
        if (web_dir / "index.html").is_file():
            app.router.add_get("/", home)
            app.router.add_static("/", web_dir, show_index=False)
        return app

    async def _rest(self, request):
        path = request.match_info["path"]
        route = request.method + " " + path
        if route == "GET health":
            return web.json_response({"ok": True, "apiVersion": 1})
        if route == "GET build":
            return web.json_response({"appBuild": "freeze-pulse-alarm-v3",
                                      "mcuFreezeHoldMs": self.state.mcu_hold_ms,
                                      "mcuCueRevision": self.state.mcu_cue_revision},
                                     headers={"Cache-Control": "no-store"})
        body = {}
        if request.method in ("PUT", "POST"):
            if request.content_type != "application/json":
                raise Rejected(415, "Send application/json")
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeError):
                raise Rejected(400, "Invalid JSON") from None
            if not isinstance(body, dict):
                raise Rejected(422, "Expected JSON object")
        disconnect_sid = None
        async with self.lock:
            if route == "POST preview/access":
                self.files.verify_code(body.get("code"))
                response = web.json_response({"ok": True})
                response.set_cookie("unfreeze_viewer", self.viewer_token, httponly=True,
                                    samesite="Strict", path="/v1/preview", secure=request.secure)
                return response
            if route == "GET preview/state":
                cookie = request.cookies.get("unfreeze_viewer", "")
                if not cookie.isascii() or not secrets.compare_digest(cookie, self.viewer_token):
                    raise Rejected(401, "Enter the board code to view status")
                snapshot = self.state.snapshot()
                sample = self.freeze_sample
                score = None
                if sample and sample[0] == self.session_token() and time.monotonic() - sample[2] <= 2:
                    score = sample[1]
                return web.json_response({
                    "freeze": score, "session": snapshot["sessionState"], "vision": snapshot["visionStatus"],
                    "audio": snapshot["doorAudio"], "haptics": snapshot["hapticsOutput"],
                    "phonePending": self.state.pending is not None,
                    "buzzerSupported": snapshot["buzzerSupported"], "hapticsSupported": snapshot["hapticsSupported"],
                })
            if route == "POST pair":
                result = self.files.pair(body.get("code"))
                disconnect_sid = self.state.controller
                await self.state.disconnected()
            else:
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or not self.files.matches(auth[7:]):
                    raise Rejected(401, "Pair with this board")
                result = await self._command(route, body)
        if disconnect_sid:
            await self.io.disconnect(disconnect_sid)
        return web.json_response(result)

    async def _command(self, route, body):
        s = self.state
        if route == "GET capabilities":
            return {**s.capabilities(), "benchInjection": self.bench_enabled}
        if route == "GET settings":
            return self.files.settings
        if route == "GET state":
            return s.snapshot()
        if route == "PUT settings":
            self.files.apply(body)  # effective at next hardware command; atomically persisted before ACK
            await s.publish()
            return self.files.settings
        if route == "POST session/start":
            await s.start()
        elif route == "POST session/stop":
            if s.session is not None and body.get("sessionId") != s.session:
                raise Rejected(409, "Session changed")
            await s.stop()
        elif route == "POST haptics/preview":
            await s.preview(body)
        elif route == "POST buzzer/preview":
            await s.preview(body, "buzzer")
        elif route == "POST buzzer/stop":
            await s.stop_buzzer_preview()
            await s.publish()
        elif route == "POST haptics/stop":
            await s.stop_haptics()
            await s.publish()
        elif route == "POST bench/event" and self.bench_enabled:
            if not self.session_token():
                raise Rejected(409, "Start a session before bench injection")
            kind = body.get("type")
            if kind == "door.approach":
                await s.door({"bench": True}, "simulated")
            elif kind in ("motion.freeze", "motion.prefreeze"):
                await s.motion(kind.split(".")[1], {"bench": True}, "simulated")
            else:
                raise Rejected(422, "Expected door.approach, motion.prefreeze, or motion.freeze")
        else:
            raise Rejected(404, "Unknown endpoint")
        return s.snapshot()

    def _socket_handlers(self):
        s = self.state
        @self.io.on("client.hello")
        async def hello(sid, data=None):
            data = data if isinstance(data, dict) else {}
            async with self.lock:
                valid = (type(data.get("apiVersion")) is int and data["apiVersion"] == 1
                         and data.get("deviceId") == self.files.credentials["deviceId"]
                         and self.files.matches(data.get("token"))
                         and s.controller in (None, sid))
                if valid:
                    s.controller = sid
                    logging.info("Companion controller connected")
                    await s.publish()
                    return
                await self.io.emit("auth.error", {"reason": "Unauthorized or controller busy"}, to=sid)
            await self.io.disconnect(sid)

        @self.io.on("disconnect")
        async def disconnect(sid, *reason):
            async with self.lock:
                if sid == s.controller:
                    logging.info("Companion controller disconnected")
                    await s.disconnected()

        def bind(name):
            async def handler(sid, body=None):
                async with self.lock:
                    if sid != s.controller or not isinstance(body, dict):
                        return
                    if name == "client.status":
                        ready = body.get("audioReady") is True
                        previous = s.snapshot()["phoneAudioReady"]
                        s.phone_ready_until = time.monotonic() + 6 if ready else 0
                        if previous != ready:
                            await s.publish()
                        if not ready and s.pending:
                            await s.fallback("phone no longer ready")
                    elif name in ("debug.subscribe", "debug.unsubscribe"):
                        s.debug = name == "debug.subscribe"
                    else:
                        await s.audio_reply(name, body)
            self.io.on(name, handler)
        for name in ("client.status", "debug.subscribe", "debug.unsubscribe", "cue.audio.ready",
                     "cue.audio.started", "cue.audio.failed"):
            bind(name)
