"""One notification per stable doorway in front of the chest camera."""
import math
import time
from deployment_defaults import DOOR_CONFIDENCE


class DoorGate:
    def __init__(self, cfg, clock=time.monotonic):
        self.clock = clock
        self.confidence = cfg.get("confidence", DOOR_CONFIDENCE)
        self.center = cfg["centerFraction"]
        self.frames = cfg["confirmFrames"]
        self.frame_gap = cfg["maxFrameGapSeconds"]
        self.departure = cfg["clearSeconds"]
        if not (0 <= self.confidence <= 1 and 0 <= self.center[0] < self.center[1] <= 1 and
                type(self.frames) is int and self.frames > 0 and self.departure > 0 and self.frame_gap > 0):
            raise ValueError("invalid door settings in runtime.json")
        self.reset()

    def reset(self):
        self.last = None
        self.clear_since = None
        self.center_x = None
        self.hits = 0
        self.latched = False

    def clear(self):
        self.hits = 0
        self.center_x = None
        if self.clear_since is None:
            self.clear_since = self.clock()
        if self.clock() - self.clear_since >= self.departure:
            self.latched = False

    @property
    def stable(self):
        return self.hits >= self.frames

    def update(self, box):
        x, _, w, _ = box["bbox"]
        center = (x + w / 2) / box["inputSize"][0]
        if (box["label"] != "door" or not math.isfinite(center) or box["confidence"] < self.confidence
                or not self.center[0] <= center <= self.center[1]):
            self.clear()
            return False
        now = self.clock()
        if self.clear_since is not None and now - self.clear_since >= self.departure:
            self.latched = False
        self.clear_since = None
        if self.last is None or now - self.last > self.frame_gap or (
                self.center_x is not None and abs(self.center_x - center) > 0.20):
            self.hits = 0
        self.last, self.center_x = now, center
        self.hits += 1
        if self.hits >= self.frames and not self.latched:
            self.latched = True
            return True
        return False
