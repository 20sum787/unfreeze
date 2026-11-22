"""One Movement model. All transforms are explicit, in Studio's interleaved axis order."""
from collections import deque
import math
from deployment_defaults import MOTION_CONFIDENCE


SOURCE_AXES = ("ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps")


class MotionWindows:
    def __init__(self, config):
        self.cfg = config
        self.hz = config["sampleRateHz"]
        self.size = config["windowSamples"]
        self.hop = config["hopSamples"]
        axes = config["axes"]
        if type(self.hz) is not int or self.hz not in (25, 50, 64, 100):
            raise ValueError("sampleRateHz must match training and one of 25, 50, 64, 100")
        if not (type(self.size) is int and 1 <= self.size <= 4096 and
                type(self.hop) is int and 1 <= self.hop <= self.size):
            raise ValueError("invalid windowSamples or hopSamples")
        if not 1 <= len(axes) <= 6 or not config["mount"]:
            raise ValueError("set the training axes and mount")
        self.transforms = []
        for axis in axes:
            factor = float(axis["scale"])
            if not math.isfinite(factor) or factor == 0:
                raise ValueError("invalid axis scale")
            self.transforms.append((SOURCE_AXES.index(axis["source"]) + 2, factor))
        if not config["riskLabels"] or set(config["riskLabels"].values()) - {"prefreeze", "freeze"}:
            raise ValueError("map exact Studio labels to prefreeze or freeze")
        if not config["normalLabels"] or set(config["normalLabels"]) & set(config["riskLabels"]):
            raise ValueError("specify separate normal labels to rearm")
        minimum = config.get("minimumScore", MOTION_CONFIDENCE)
        if not (0 < minimum <= 1 and 0 < config.get("riskMinimumScore", minimum) <= 1) or any(type(config[k]) is not int or config[k] < 1
                    for k in ("confirmWindows", "clearWindows")):
            raise ValueError("invalid motion decision thresholds")
        self.buffer = deque(maxlen=self.size)
        self.reset()

    @property
    def cues_enabled(self):
        return self.cfg["enableLiveCues"] is True and (
            self.cfg.get("mountVerified") is True or self.cfg.get("allowUnverifiedMountForDemo") is True)

    def verify_model(self, params, project=None):
        for key, value in self.cfg.get("project", {}).items():
            if (project or {}).get(key) != value:
                raise ValueError(f"Movement EIM project field {key} differs from motion.json")
        if (params["model_type"] != "classification" or
                params["axis_count"] != len(self.transforms) or
                params["input_features_count"] != self.size * len(self.transforms) or
                not math.isclose(params["frequency"], self.hz, rel_tol=0.005)):
            raise ValueError("EIM type/axis count/window/frequency differs from motion.json")
        known = set(self.cfg["normalLabels"]) | set(self.cfg["riskLabels"])
        if known - set(params["labels"]):
            raise ValueError(f"label mapping mismatch; EIM labels = {params['labels']}")

    def reset(self):
        self.buffer.clear()
        self.last = None
        self.remaining = self.size

    def contiguous(self, row):
        seq, stamp = row[:2]
        last_seq, last_stamp = self.last
        delta = (stamp - last_stamp) & 0xFFFFFFFF
        return ((seq - last_seq) & 0xFFFFFFFF) == 1 and 0.5 <= delta * self.hz / 1000 <= 1.5

    def add(self, row):
        seq, stamp = row[:2]
        if self.last is not None and not self.contiguous(row):
            self.reset()
        self.last = seq, stamp
        self.buffer.append(tuple(row[index] * scale for index, scale in self.transforms))
        self.remaining -= 1
        if self.remaining == 0:
            self.remaining = self.hop
            return [value for sample in self.buffer for value in sample]
        return None


class RiskGate:
    def __init__(self, config):
        self.config = config
        self.minimum_score = config.get("minimumScore", MOTION_CONFIDENCE)
        self.risk_minimum_score = config.get("riskMinimumScore", self.minimum_score)
        self.reset()

    def reset(self):
        self.latched = False
        self.label = None
        self.streak = 0

    def classify(self, scores):
        label = max(scores, key=scores.get)
        kind = self.config["riskLabels"].get(label)
        threshold = self.risk_minimum_score if kind else self.minimum_score
        if not threshold <= scores[label] <= 1:
            self.streak = 0
            return None
        if label != self.label:
            self.streak = 0
        self.label = label
        self.streak += 1
        if label in self.config["normalLabels"] and self.streak >= self.config["clearWindows"]:
            self.latched = False
        if (kind and self.streak >= self.config["confirmWindows"] and
                (not self.latched or (kind == "freeze" and self.latched == "prefreeze"))):
            self.latched = kind
            return kind
        return None


class SustainedFreeze:
    """One alarm per episode. Use acquisition time and fresh classification windows."""
    duration = 5.0
    grace = 1.0

    def __init__(self, config):
        self.labels = {key for key, value in config["riskLabels"].items() if value == "freeze"}
        self.minimum = config.get("riskMinimumScore", config.get("minimumScore", MOTION_CONFIDENCE))
        self.context = None
        self.reset()

    def reset(self):
        self.start = self.last = self.low_since = None
        self.fired = False
        self.history = deque()

    def update(self, scores, at, context, *, allow_start=True):
        if context != self.context:
            self.reset()
            self.context = context
        if self.last is not None and (at <= self.last or at - self.last > self.grace):
            self.reset()
        if self.low_since is not None and at - self.low_since >= self.grace:
            self.reset()
        self.last = at
        label = max(scores, key=scores.get) if scores else None
        high = label in self.labels and self.minimum <= scores[label] <= 1
        if high:
            if self.start is None:
                if not allow_start:
                    return False
                self.start = at
            self.low_since = None
        elif self.start is not None:
            if self.low_since is None:
                self.low_since = at
        if self.start is None:
            return False
        self.history.append((at, high))
        while self.history and self.history[0][0] < at - self.duration:
            self.history.popleft()
        if (high and not self.fired and at - self.start >= self.duration
                and sum(hit for _, hit in self.history) >= 0.75 * len(self.history)):
            self.fired = True
            return True
        return False
