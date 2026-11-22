"""Local board configuration. Keep secrets and settings out of the app export."""
import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path


LEVELS = (25, 30, 35, 40, 45, 50)
MODES = ("phone_preferred", "board_only")
DEFAULTS = {"settingsRevision": 1, "audio": {"mode": "phone_preferred"},
            "buzzer": {"toneHz": 1000, "cadenceBpm": 90},
            "haptics": {"enabled": True, "levelPercent": 40, "cadenceBpm": 90}}


class Rejected(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status


def in_range(value, low, high):
    return type(value) is int and low <= value <= high


def validate_haptics(level, bpm):
    if type(level) is not int or level not in LEVELS or not in_range(bpm, 45, 150):
        raise Rejected(422, "Unsupported vibration level or cadence")


def validate(settings):
    try:
        audio, buzzer, haptics = (settings[key] for key in ("audio", "buzzer", "haptics"))
        valid = (type(settings["settingsRevision"]) is int and settings["settingsRevision"] >= 1
                 and audio["mode"] in MODES and in_range(buzzer["toneHz"], 200, 3000)
                 and in_range(buzzer["cadenceBpm"], 45, 150) and type(haptics["enabled"]) is bool)
        validate_haptics(haptics["levelPercent"], haptics["cadenceBpm"])
    except (KeyError, TypeError) as exc:
        raise Rejected(422, "Incomplete settings") from exc
    if not valid:
        raise Rejected(422, "Unsupported settings")


def write_private(path, value):
    # Same directory makes os.replace atomic. mkstemp uses user-only permissions on Linux.
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


class BoardFiles:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.credentials = self.read("identity.json", {"deviceId": "unoq-" + uuid.uuid4().hex[:12], "hash": ""})
        if not isinstance(self.credentials, dict) or not isinstance(self.credentials.get("deviceId"), str):
            raise ValueError("Invalid identity.json in " + str(self.root))
        self.write("identity.json", self.credentials)
        self.settings = self.read("settings.json", copy.deepcopy(DEFAULTS))
        try:
            validate(self.settings)
        except Rejected:
            logging.warning("Invalid settings.json; using demo defaults until next Apply settings")
            self.settings = copy.deepcopy(DEFAULTS)
        try:
            self.fixed_code = (self.root / "pairing-code.fixed").read_text(encoding="ascii").strip()
        except FileNotFoundError:
            self.fixed_code = None
        if self.fixed_code is not None and (len(self.fixed_code) != 6 or not self.fixed_code.isdecimal()):
            raise ValueError("pairing-code.fixed must contain six ASCII digits")
        self.retry_after = 0.0
        self.rotate_code()

    def read(self, name, default):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (UnicodeError, ValueError):
            logging.warning("Unreadable %s in data directory; using fresh values", name)
            return default

    def write(self, name, obj):
        write_private(self.root / name, json.dumps(obj))

    def rotate_code(self):
        self.code = self.fixed_code or str(secrets.randbelow(1_000_000)).zfill(6)
        self.code_until = float("inf") if self.fixed_code else time.monotonic() + 600
        self.bad_codes = 0
        write_private(self.root / "pairing-code.txt", self.code + "\n")

    def verify_code(self, code):
        if time.monotonic() < self.retry_after:
            raise Rejected(429, "Wait 30 seconds before trying to pair again")
        if time.monotonic() >= self.code_until:
            self.rotate_code()
        if not isinstance(code, str) or not code.isascii() or not hmac.compare_digest(code, self.code):
            self.bad_codes += 1
            if self.bad_codes >= 8:
                if self.fixed_code:
                    self.bad_codes = 0
                    self.retry_after = time.monotonic() + 30
                else:
                    self.rotate_code()
            raise Rejected(401, "Check the current local pairing code")
        self.bad_codes = 0

    def pair(self, code):
        self.verify_code(code)
        token = secrets.token_urlsafe(32)
        credential = {"deviceId": self.credentials["deviceId"], "hash": self.digest(token)}
        if not self.fixed_code:
            self.rotate_code()
        self.write("identity.json", credential)
        self.credentials = credential
        return {"deviceId": credential["deviceId"], "token": token}

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def matches(self, token):
        digest = self.credentials.get("hash")
        return bool(isinstance(digest, str) and digest and isinstance(token, str)
                    and hmac.compare_digest(self.digest(token), digest))

    def apply(self, patch):
        revision = self.settings["settingsRevision"]
        if type(patch.get("baseRevision")) is not int or patch["baseRevision"] != revision:
            raise Rejected(409, "Settings revision changed")
        candidate = copy.deepcopy(self.settings)
        groups = set(patch) - {"baseRevision"}
        if not groups or not groups <= {"audio", "buzzer", "haptics"}:
            raise Rejected(422, "Unknown settings group")
        for group in groups:
            fields = patch[group]
            if not isinstance(fields, dict) or not set(fields) <= set(DEFAULTS[group]):
                raise Rejected(422, "Unknown settings field")
            candidate[group].update(fields)
        candidate["settingsRevision"] += 1
        validate(candidate)
        self.write("settings.json", candidate)
        self.settings = candidate
