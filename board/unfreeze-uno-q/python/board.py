"""One lock per Bridge call. The MCU owns deadlines, the bus and the sample ring."""
import inspect
import json
import math
import threading
import time
from deployment_defaults import BRIDGE_TIMEOUT_MS


class Hardware:
    def __init__(self, bridge_call):
        self.call = bridge_call
        self.lock = threading.Lock()
        self.supports_timeout = "timeout" in inspect.signature(bridge_call).parameters
        self.vibro_until = 0.0

    def rpc(self, name, *args):
        with self.lock:
            if self.supports_timeout:
                return self.call(name, *args, timeout=BRIDGE_TIMEOUT_MS / 1000)
            return self.call(name, *args)

    def status(self):
        data = json.loads(self.rpc("uf_status"))
        if data.get("version") != 1:
            raise ValueError("unexpected sketch protocol; expected version 1")
        return data

    def samples(self):
        data = json.loads(self.rpc("uf_samples"))
        rows = data["rows"]
        for row in rows:
            if (len(row) != 8 or type(row[0]) is not int or type(row[1]) is not int or
                    not all(math.isfinite(x) for x in row[2:])):
                raise ValueError("malformed Movement sample")
        return rows, data["dropped"]

    def buzzer(self, tone_hz, bpm):
        return self.rpc("uf_buzzer", int(tone_hz), int(bpm)) == 1

    def vibro(self, level_percent, bpm):
        accepted = self.rpc("uf_vibro", int(level_percent), int(bpm)) == 1
        if accepted:
            self.vibro_until = time.monotonic() + 3 * 60 / bpm + 0.18 + 0.5
        return accepted

    def stop_buzzer(self):
        return self.rpc("uf_stop", 2) == 1

    def freeze_pulses(self, level_percent, bpm):
        duration_ms = self.rpc("uf_freeze_pulses", int(level_percent), int(bpm))
        if type(duration_ms) is not int or duration_ms != 5000:
            return False
        self.vibro_until = time.monotonic() + duration_ms / 1000 + 0.5
        return True

    def freeze_alarm(self):
        return self.rpc("uf_freeze_alarm") == 5000

    def stop_vibro(self):
        return self.rpc("uf_stop", 1) == 1
