"""Exercise the same classification stream adapter as the board, with a scripted runner."""
import base64
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "python"))
import camera_adapter as camera


def hello():
    return {"type": "hello", "project": {"id": 1170197, "deploy_version": 6},
            "modelParameters": {"model_type": "object_detection", "labels": ["door"],
                                "image_input_width": 192, "image_input_height": 192,
                                "image_channel_count": 3, "image_resize_mode": "fit-longest"}}


def preview(width, height):
    jpeg = io.BytesIO()
    Image.new("RGB", (width, height)).save(jpeg, "JPEG")
    return {"type": "camera-preview", "image": "data:image/jpeg;base64," +
            base64.b64encode(jpeg.getvalue()).decode("ascii")}


def box(x=0, y=0, width=1280, height=720, value=0.9, label="door"):
    return dict(x=x, y=y, width=width, height=height, value=value, label=label)


class Stream(unittest.TestCase):
    def test_model_artifact(self):
        data = (APP / "models/door-v6.eim").read_bytes()
        self.assertEqual(data[:6], b"\x7fELF\x02\x01")
        self.assertEqual(int.from_bytes(data[18:20], "little"), 183)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "f6154c9fe7fd07954b9ed76aaeacd0c6940872f3643fd0dba360570fb9a94a4a")

    def test_wrong_model(self):
        packet = hello()
        packet["project"]["deploy_version"] = 3
        with self.assertRaisesRegex(ValueError, "Unexpected model"):
            camera.check_model(packet)

    def test_geometries_and_invalid_candidates(self):
        for size, expected in [((1280,720), [0,42,192,108]), ((480,640), [24,0,144,192]),
                               ((192,192), [0,0,192,192])]:
            with self.subTest(size=size):
                boxes = [box(width=size[0], height=size[1]), box(value=0.4), box(value=1.8),
                         box(value=float("nan")), box(label="chair"), box(width=-1), "malformed"]
                self.assertEqual(camera.strongest_door(boxes, size)["bbox"], expected)

    def test_full_callback_stream_and_background(self):
        seen, clear = [], []
        observer = camera.CameraObserver(None, seen.append, lambda: clear.append(True), lambda msg: None)
        class ScriptedSocket:
            packets = iter([hello(), preview(640, 480),
                            {"type": "classification", "result": {"bounding_boxes": [
                                box(100, 100, 100, 160, .55), box(200, 100, 200, 250, .95)]}},
                            {"type": "classification", "result": {"bounding_boxes": []}}])
            def recv(self, timeout):
                packet = next(self.packets, None)
                if packet is None:
                    observer.stopped.set()
                    raise TimeoutError()
                return json.dumps(packet)
            def send(self, message):
                assert json.loads(message)["enabled"] is True
        observer._read(ScriptedSocket())
        self.assertEqual(seen[0]["bbox"], [60,54,60,75])
        self.assertEqual(seen[0]["confidence"], .95)
        self.assertEqual(clear, [True])

    def test_stalled_runner_clears_gate_once(self):
        cleared, status = [], []
        observer = camera.CameraObserver(None, None, lambda: cleared.append(True), status.append)
        class StalledSocket:
            calls = 0
            def recv(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps(hello())
                if self.calls == 4:
                    observer.stopped.set()
                raise TimeoutError()
            def send(self, message):
                pass
        with patch.object(camera.time, "monotonic", side_effect=[0,5,6,7]):
            observer._read(StalledSocket())
        self.assertEqual(cleared, [True])
        self.assertIn("fresh camera", status[-1])


if __name__ == "__main__":
    unittest.main()
