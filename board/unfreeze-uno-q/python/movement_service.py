"""Poll the MCU independently of inference. Only the latest complete window is pending."""
import json
import logging
import queue
import threading
import time

from eim import Eim
from motion import MotionWindows, RiskGate, SustainedFreeze

log = logging.getLogger("movement")


class MovementService:
    def __init__(self, board, client, root):
        self.board, self.client = board, client
        self.root = root
        self.stop = threading.Event()
        self.inference_failed = threading.Event()
        self.pending = queue.Queue(maxsize=1)
        self.windows = None
        self.gate = None
        self.engine = None
        self.cfg = {}
        self.epoch = 0
        self.sensor_epoch = 0
        self.window_number = 0
        self.context = None
        self.poll_thread = None
        self.worker = None
        self.model_status = "IMU raw only · Movement EIM not configured"
        self.last_motion_status = None

    def start(self):
        try:
            self.cfg = json.loads((self.root / "python/motion.json").read_text(encoding="utf8"))
            if self.cfg["enabled"]:
                windows = MotionWindows(self.cfg)
                self.engine = Eim(self.root / self.cfg["modelFile"])
                windows.verify_model(self.engine.info["model_parameters"], self.engine.info.get("project"))
                self.gate = RiskGate(self.cfg)
                self.windows = windows
                self.model_status = ("model enabled · demo cueing" if windows.cues_enabled
                                     else "model enabled · scores only")
                if self.cfg.get("mountVerified") is not True:
                    self.model_status += " · unverified IMU mapping"
                self.worker = threading.Thread(target=self._infer, name="movement-inference", daemon=True)
                self.worker.start()
        except Exception as error:
            if self.engine:
                self.engine.close()
                self.engine = None
            self.model_status = f"IMU raw only · model error: {error}"
            log.warning("%s", self.model_status)
        self.poll_thread = threading.Thread(target=self._poll, name="movement-sampling", daemon=True)
        self.poll_thread.start()

    def _reset(self, sensor_gap=True):
        self.epoch += 1
        if sensor_gap:
            self.sensor_epoch += 1
        if self.windows:
            self.windows.reset()

    def _status(self, message, caps=None):
        if caps is not None:
            self.client.status(buzzer=caps["buzzer"], vibro=caps["vibro"], hold_ms=caps.get("holdMs", 0),
                               cue_revision=caps.get("cueRev", 0))
        if message != self.last_motion_status:
            self.last_motion_status = message
            self.client.status(motion=message)
            log.info("%s", message)

    def _sample(self, row, token, acquired):
        if not self.windows or self.stop.is_set() or self.inference_failed.is_set():
            return
        if not token:
            if self.context is not None:
                self._reset(sensor_gap=False)
            self.context = None
            return
        if token != self.context:
            self._reset(sensor_gap=False)
            self.context = token
        if self.windows.last and not self.windows.contiguous(row):
            self._reset()
        features = self.windows.add(row)
        if features is None:
            return
        self.window_number += 1
        item = (self.epoch, self.sensor_epoch, self.window_number, token, acquired, features)
        try:
            self.pending.put_nowait(item)
        except queue.Full:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                pass
            self.pending.put_nowait(item)

    def _poll(self):
        next_status, next_telemetry = 0.0, 0.0
        online = False
        last_sample = 0.0
        session_at_poll = None
        session_since = 0.0
        while not self.stop.is_set():
            try:
                now = time.monotonic()
                if now >= next_status:
                    caps = self.board.status()
                    host_status_time = time.monotonic()
                    online = bool(caps["imu"])
                    if self.windows and not self.inference_failed.is_set() and caps["hz"] != self.windows.hz:
                        if self.board.rpc("uf_rate", self.windows.hz) != 1:
                            raise ValueError("MCU rejected requested sample rate")
                        self._reset()
                    message = self.model_status if online else "Movement missing · check Wire1 / address"
                    if online and now - last_sample > 2:
                        message = "Movement present · waiting for fresh samples"
                    if not online:
                        self._reset()
                    self._status(message, caps)
                    next_status = now + 1
                if online:
                    # At 100 Hz two rows per RPC fit within the 256-byte Bridge message limit.
                    for _ in range(8):
                        rows, dropped = self.board.samples()
                        if rows:
                            received = time.monotonic()
                            if last_sample and received - last_sample > SustainedFreeze.grace:
                                self._reset()
                            last_sample = received
                            token = self.client.session_token()
                            if token != session_at_poll:
                                session_at_poll, session_since = token, last_sample
                            estimated_mcu = caps["mcuMs"] + round((last_sample - host_status_time)*1000)
                            for row in rows:
                                age_ms = ((estimated_mcu - row[1] + 2**31) % 2**32) - 2**31
                                acquired = last_sample - max(0, age_ms) / 1000
                                if -100 <= age_ms <= 400 and acquired >= session_since:
                                    self._sample(row, token, acquired)
                                else:
                                    self._reset()
                            if last_sample >= next_telemetry:
                                seq, stamp, *values = rows[-1]
                                self.client.telemetry("movement", dict(seq=seq, mcuMs=stamp,
                                    accelG=values[:3], gyroDps=values[3:], dropped=dropped,
                                    sampleRateHz=caps["hz"], imuAddress=caps.get("imuAddr"),
                                    missed=caps["missed"]))
                                next_telemetry = last_sample + 0.5
                        if len(rows) < 2:
                            break
                self.stop.wait(0.023 if online else 0.3)
            except Exception as error:
                self._reset()
                online = False
                next_status = 0
                self._status(f"MCU unavailable · {error}", {"buzzer": False, "vibro": False})
                self.stop.wait(1)

    def _infer(self):
        alarm = SustainedFreeze(self.cfg)
        previous = None
        previous_epoch = None
        previous_token = None
        try:
            while not self.stop.is_set():
                try:
                    epoch, sensor_epoch, number, token, started, features = self.pending.get(timeout=0.25)
                except queue.Empty:
                    continue
                if epoch != previous_epoch or previous != number - 1:
                    # Preserve an already-issued cue across gaps in the same session.
                    latch = self.gate.latched if previous and token == previous_token else False
                    self.gate.reset()
                    self.gate.latched = latch
                previous, previous_epoch, previous_token = number, epoch, token
                scores = self.engine.classify(features)
                age = time.monotonic() - started
                if (self.stop.is_set() or epoch != self.epoch or token != self.client.session_token()
                        or age > 1):
                    self.gate.streak = 0
                    continue
                # Continue classifying for an already established episode. Any window
                # overlapping motor activity or its settling interval cannot arm a new cue.
                mask_end = self.board.vibro_until
                clean = not mask_end or started - (self.windows.size-1)/self.windows.hz >= mask_end
                self.client.telemetry("motion-model", {"scores": scores, "windowAgeMs": round(age*1000),
                                      "vibroWindow": not clean,
                                      "enableLiveCues": self.windows.cues_enabled,
                                      "mountVerified": self.cfg.get("mountVerified") is True})
                if not clean:
                    self.gate.streak = 0
                kind = self.gate.classify(scores) if clean else None
                if (self.windows.cues_enabled and alarm.update(
                        scores, started, (token, sensor_epoch), allow_start=clean)):
                    self.client.freeze_alarm({"scores": scores, "vibroWindow": not clean}, session_id=token)
                if kind and self.windows.cues_enabled:
                    self.client.motion(kind, {"scores": scores, "mount": self.cfg["mount"]},
                                       session_id=token)
        except Exception as error:
            self.inference_failed.set()
            self.model_status = f"IMU raw only · inference error: {error}"
            log.exception("Movement EIM failed; raw sampling remains available")
        finally:
            self.engine.close()

    def close(self):
        self.stop.set()
        if self.poll_thread:
            self.poll_thread.join(1)
        if self.worker:
            self.worker.join(1)
