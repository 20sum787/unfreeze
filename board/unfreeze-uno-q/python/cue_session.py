"""One bounded session, independent door-audio and movement-haptics channels.

Called under the transport's asyncio lock. Hardware methods send bounded MCU
commands and return a boolean acknowledgement. Sensor and socket callbacks
use the same serialized transition path.
"""
import asyncio
import logging
import time
import uuid
from collections import deque

from companion_settings import LEVELS, MODES, Rejected, in_range, validate_haptics


class CueSession:
    def __init__(self, hardware, files, emit):
        self.hw, self.files, self.emit = hardware, files, emit
        self.boot_id = uuid.uuid4().hex
        self.boot_time = time.monotonic()
        self.session = None
        self.expires = 0
        self.controller = None
        self.debug = False
        self.phone_ready_until = 0
        self.audio, self.haptics = None, None
        self.audio_until = self.haptics_until = 0
        self.pending = None
        self.door_buzzer_trigger = None
        self.next_door_buzz = 0
        self.buzzer_attempted = self.vibro_attempted = False
        self.event_seq = self.telemetry_seq = 0
        self.previews = deque(maxlen=128)
        self.stop_fault = None
        self.vision_status, self.motion_status = "starting", "research_unverified"
        self.buzzer_supported = self.vibro_supported = False
        self.mcu_hold_ms = None
        self.mcu_cue_revision = None

    def capabilities(self):
        return {"firmwareVersion": "unfreeze-uno-q-v1", "audioModes": list(MODES),
                "buzzerSupported": self.buzzer_supported, "hapticsSupported": self.vibro_supported,
                "buzzerLimits": {"toneHz": [200, 3000], "cadenceBpm": [45, 150]},
                "hapticsLimits": {"cadenceBpm": [45, 150], "levelsPercent": list(LEVELS)}}

    def snapshot(self):
        now = time.monotonic()
        return {"deviceId": self.files.credentials["deviceId"], "bootId": self.boot_id,
                "sessionState": "FAULT" if self.stop_fault else ("ACTIVE" if self.session else "IDLE"),
                "sessionId": self.session, "sessionExpiresInMs": max(0, round((self.expires - now) * 1000)),
                "settingsRevision": self.files.settings["settingsRevision"],
                "buzzerSupported": self.buzzer_supported, "hapticsSupported": self.vibro_supported,
                "phoneAudioReady": bool(self.controller and now < self.phone_ready_until),
                "faultCode": self.stop_fault, "visionStatus": self.vision_status,
                "motionStatus": self.motion_status, "doorAudio": self.audio, "hapticsOutput": self.haptics}

    async def send(self, name, payload):
        if self.controller is not None:
            await self.emit(name, payload, to=self.controller)

    async def publish(self):
        await self.send("status.snapshot", self.snapshot())

    async def event(self, source, kind, data, origin="live", telemetry=False):
        if telemetry:
            self.telemetry_seq += 1
            seq = self.telemetry_seq
        else:
            self.event_seq += 1
            seq = self.event_seq
        event_id = f"{self.boot_id}-{'t' if telemetry else 'e'}{seq}"
        if self.debug:
            await self.send("debug.telemetry" if telemetry else "debug.event", {
                "schemaVersion": 1, "seq": seq, "eventId": event_id, "bootId": self.boot_id,
                "sessionId": self.session, "boardUptimeMs": round((time.monotonic() - self.boot_time) * 1000),
                "source": source, "type": kind, "origin": origin, "data": data})
        return event_id

    async def report_output(self, channel, state, reason, cue, until):
        record = {"output": channel, "state": state, "reason": reason, "cueId": cue["key"]["cueId"],
                  "triggerEventId": cue["trigger"]}
        if channel == "vibro":
            self.haptics, self.haptics_until = record, until
        else:
            self.audio, self.audio_until = record, until
        await self.event("controller", "cue.output_changed", record, cue["origin"])
        await self.publish()

    async def hardware(self, method, *args):
        try:
            # The supplied bridge adapter bounds each call. Holding the state lock
            # orders Stop after a prior Start even if another client retries.
            return await asyncio.to_thread(getattr(self.hw, method), *args) is True
        except Exception:
            logging.exception("MCU operation %s failed", method)
            return False

    async def start(self):
        if self.stop_fault:
            raise Rejected(409, "Retry Stop before starting a session")
        if self.session is None:
            if self.audio:
                await self.stop_buzzer_preview()
            if self.haptics:
                await self.stop_haptics()
            self.session = uuid.uuid4().hex
            self.expires = time.monotonic() + 900
            await self.publish()

    async def stop_haptics(self):
        if self.haptics and self.vibro_attempted and not await self.hardware("stop_vibro"):
            raise Rejected(503, "MCU did not confirm stop_vibro")
        self.haptics = None
        self.vibro_attempted = False
        self.haptics_until = 0

    async def stop(self):
        self.door_buzzer_trigger = None
        if self.pending:
            await self.send("cue.audio.cancel", self.pending["key"])
        elif self.audio and self.audio["output"] == "phone_audio":
            await self.send("cue.audio.cancel", {"cueId": self.audio["cueId"], "sessionId": self.session})
        self.pending = None
        failures = []
        if self.audio and self.buzzer_attempted and not await self.hardware("stop_buzzer"):
            failures.append("buzzer")
        else:
            self.audio = None
            self.buzzer_attempted = False
        try:
            await self.stop_haptics()
        except Rejected:
            failures.append("vibro")
        self.expires = 0
        self.stop_fault = "stop_unconfirmed:" + ",".join(failures) if failures else None
        if not failures:
            self.session = None
        await self.publish()
        if failures:
            raise Rejected(503, self.stop_fault)

    def new_cue(self, trigger, origin):
        return {"key": {"sessionId": self.session, "cueId": uuid.uuid4().hex},
                "trigger": trigger, "origin": origin}

    async def door(self, data, origin):
        trigger = await self.event("camera", "door.approach", data, origin)
        if not self.session or self.stop_fault or self.audio or self.pending:
            return
        self.door_buzzer_trigger = None
        cue = self.new_cue(trigger, origin)
        cue.update(stage="offer", deadline=time.monotonic() + 0.300)
        self.pending = cue
        if self.files.settings["audio"]["mode"] == "phone_preferred" and self.snapshot()["phoneAudioReady"]:
            await self.send("cue.audio.offer", {**cue["key"], "ttlMs": 500})
        else:
            await self.fallback("board route or phone unavailable")

    async def fallback(self, reason):
        cue, self.pending = self.pending, None
        if not cue:
            return
        await self.send("cue.audio.cancel", cue["key"])
        if cue["origin"] == "live":
            self.door_buzzer_trigger = cue["trigger"]
        await self.play_door_buzzer(cue, reason)

    async def play_door_buzzer(self, cue, reason):
        setting = self.files.settings["buzzer"]
        bpm = setting["cadenceBpm"]
        self.next_door_buzz = time.monotonic() + 4 * 60 / bpm
        await self.buzz(cue, setting["toneHz"], bpm, reason)

    async def repeat_door_buzzer(self):
        if (not self.session or self.stop_fault or not self.door_buzzer_trigger or
                self.audio or self.pending or time.monotonic() < self.next_door_buzz):
            return
        cue = self.new_cue(self.door_buzzer_trigger, "live")
        await self.play_door_buzzer(cue, "door still in view")

    async def buzz(self, cue, tone, bpm, reason):
        self.buzzer_attempted = self.buzzer_supported
        accepted = self.buzzer_supported and await self.hardware("buzzer", tone, bpm)
        await self.report_output("buzzer", "applied" if accepted else "failed",
                                 reason if accepted else reason + "; MCU unavailable or rejected",
                                 cue, time.monotonic() + 3 * 60 / bpm + 0.1)
        return accepted

    async def stop_buzzer_preview(self):
        if self.session:
            raise Rejected(409, "Stop the session before testing the buzzer")
        if self.buzzer_attempted and not await self.hardware("stop_buzzer"):
            raise Rejected(503, "MCU did not confirm stop_buzzer")
        self.audio, self.audio_until, self.buzzer_attempted = None, 0, False

    async def audio_reply(self, name, body):
        cue = self.pending
        if not cue or body.get("sessionId") != self.session or body.get("cueId") != cue["key"]["cueId"]:
            return
        if time.monotonic() >= cue["deadline"]:
            await self.fallback("phone reply timed out")
        elif name == "cue.audio.failed":
            await self.fallback("phone playback unavailable")
        elif name == "cue.audio.ready" and cue["stage"] == "offer":
            cue.update(stage="play", deadline=time.monotonic() + 0.700)
            await self.send("cue.audio.play", cue["key"])
        elif name == "cue.audio.started" and cue["stage"] == "play":
            self.pending = None
            await self.report_output("phone_audio", "started", "playback confirmed", cue, time.monotonic() + 12)

    async def disconnected(self):
        self.controller, self.debug, self.phone_ready_until = None, False, 0
        if self.pending:
            await self.fallback("controller disconnected")
        elif self.audio and self.audio["output"] == "phone_audio":
            self.audio = None

    async def vibrate(self, cue, level, bpm):
        self.vibro_attempted = self.vibro_supported
        accepted = self.vibro_supported and await self.hardware("vibro", level, bpm)
        await self.report_output("vibro", "applied" if accepted else "failed",
                                 "MCU accepted" if accepted else "MCU unavailable or rejected", cue,
                                 time.monotonic() + 3 * 60 / bpm + 0.18)
        return accepted

    async def motion(self, kind, data, origin):
        trigger = await self.event("movement", "motion." + kind, data, origin)
        h = self.files.settings["haptics"]
        if not self.session or self.stop_fault or not h["enabled"]:
            return
        cue = self.new_cue(trigger, origin)
        if kind == "freeze":
            self.vibro_attempted = self.vibro_supported
            accepted = self.vibro_supported and await self.hardware("freeze_pulses", h["levelPercent"], h["cadenceBpm"])
            await self.report_output("vibro", "applied" if accepted else "failed",
                                     "freeze pulses 5 s" if accepted else "MCU did not confirm freeze pulses",
                                     cue, time.monotonic() + 5)
        elif not self.haptics:
            await self.vibrate(cue, h["levelPercent"], h["cadenceBpm"])

    async def freeze_alarm(self, data):
        if not self.session or self.stop_fault:
            return
        trigger = await self.event("movement", "motion.freeze_alarm", data)
        cue = self.new_cue(trigger, "live")
        if self.pending:
            await self.send("cue.audio.cancel", self.pending["key"])
            self.pending = None
        if self.audio and self.audio["output"] == "phone_audio":
            await self.send("cue.audio.cancel", {"sessionId": self.session, "cueId": self.audio["cueId"]})
        elif self.buzzer_attempted and not await self.hardware("stop_buzzer"):
            await self.report_output("buzzer", "failed", "could not interrupt door buzzer",
                                     cue, time.monotonic() + 2)
            return
        self.buzzer_attempted = self.buzzer_supported
        accepted = self.buzzer_supported and await self.hardware("freeze_alarm")
        await self.report_output("buzzer", "applied" if accepted else "failed",
                                 "sustained freeze" if accepted else "MCU did not confirm freeze alarm",
                                 cue, time.monotonic() + 5)

    async def preview(self, body, output="haptics"):
        req = body.get("requestId")
        if not isinstance(req, str) or not 0 < len(req) <= 120:
            raise Rejected(422, "Missing requestId")
        bpm = body.get("cadenceBpm")
        if output == "buzzer":
            if not in_range(body.get("toneHz"), 200, 3000) or not in_range(bpm, 45, 150):
                raise Rejected(422, "Unsupported buzzer pitch or cadence")
        else:
            validate_haptics(body.get("levelPercent"), bpm)
        if self.session or self.stop_fault:
            raise Rejected(409, "Preview is available only while idle")
        for request_id, ok in self.previews:
            if (output, req) == request_id:
                if not ok:
                    raise Rejected(503, "Previous preview was rejected")
                return
        if (self.audio if output == "buzzer" else self.haptics):
            raise Rejected(409, "A preview is already active")
        trigger = await self.event("app", output + ".preview", body)
        cue = self.new_cue(trigger, "live")
        cue["key"]["cueId"] = req
        if output == "buzzer":
            ok = await self.buzz(cue, body["toneHz"], bpm, "manual test")
        else:
            ok = await self.vibrate(cue, body["levelPercent"], bpm)
        self.previews.append(((output, req), ok))
        if not ok:
            raise Rejected(503, output + " unavailable or rejected")

    async def tick(self):
        now = time.monotonic()
        if self.session and self.expires and now >= self.expires:
            try:
                await self.stop()
            except Rejected:
                pass   # published FAULT; user can retry Stop
        if self.pending and now >= self.pending["deadline"]:
            await self.fallback("phone " + self.pending["stage"] + " timeout")
        changed = False
        if self.audio and now >= self.audio_until and not self.stop_fault:
            self.audio, changed = None, True
            self.buzzer_attempted = False
        if self.haptics and now >= self.haptics_until and not self.stop_fault:
            self.haptics, changed = None, True
            self.vibro_attempted = False
        if self.phone_ready_until and now >= self.phone_ready_until:
            self.phone_ready_until, changed = 0, True
        if changed:
            await self.publish()
