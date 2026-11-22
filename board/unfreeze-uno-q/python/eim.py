"""Small client for Edge Impulse's Linux JSON protocol, used for the Movement classifier."""
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class Eim:
    def __init__(self, executable, *, command_prefix=(), timeout=3):
        self.temp = tempfile.TemporaryDirectory(prefix="uf-eim-")
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.process = None
        self.serial = 0
        self.socket.settimeout(timeout)
        endpoint = str(Path(self.temp.name) / "runner.sock")
        try:
            # Inherit stderr for App Lab diagnostics. Never capture an undrained pipe.
            self.process = subprocess.Popen([*command_prefix, str(executable), endpoint],
                                            stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 12
            while True:
                if self.process.poll() is not None:
                    raise RuntimeError(f"EIM exited at startup ({self.process.returncode})")
                try:
                    self.socket.connect(endpoint)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("EIM socket startup timeout")
                    time.sleep(0.05)
            self.info = self.request({"hello": 1})
        except BaseException:
            self.close()
            raise

    def request(self, message):
        self.serial += 1
        payload = dict(message, id=self.serial)
        self.socket.sendall(json.dumps(payload, separators=(",", ":"), allow_nan=False).encode())
        buf = bytearray()
        while len(buf) < 1_048_576:
            chunk = self.socket.recv(8192)
            if not chunk:
                raise ConnectionError("EIM closed its socket")
            buf.extend(chunk)
            if buf.endswith(b"\0"):
                reply = json.loads(buf[:-1])
                if reply.get("id") != self.serial or not reply.get("success"):
                    raise ValueError(f"EIM rejected request: {reply.get('error', 'unexpected id')}")
                return reply
        raise ValueError("EIM reply exceeds limit")

    def classify(self, features):
        return self.request({"classify": features})["result"]["classification"]

    def close(self):
        self.socket.close()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.temp.cleanup()
