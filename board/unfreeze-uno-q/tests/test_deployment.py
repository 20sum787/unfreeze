import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "python"))
from companion import Companion
from preflight import camera_paths
from sync_config import sync


class Deployment(unittest.TestCase):
    def test_deployment_settings_in_sync(self):
        self.assertGreater(sync(ROOT)["COMPANION_PORT"], 0)

    def test_duplicate_import_repair_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "python").mkdir()
            (root / "python/runtime.json").write_text(json.dumps({"cameraEnabled": True}))
            (root / "app.yaml").write_text('bricks:\n  - arduino:video_object_detection:\n'
                                            '      variables:\n        CUSTOM_MODEL_PATH: "/old/models"\n'
                                            '        EI_V_OBJ_DETECTION_MODEL: "/old/models/door-v6.eim"\n')
            with self.assertRaisesRegex(ValueError, "path differs"):
                camera_paths(root, False)
            with patch("sys.platform", "linux"):
                camera_paths(root, True)
            before = (root / "app.yaml").read_bytes()
            camera_paths(root, False)
            self.assertEqual((root / "app.yaml").read_bytes(), before)


class Backpressure(unittest.IsolatedAsyncioTestCase):
    async def test_busy_session_keeps_latest_telemetry_per_source(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Companion(None, Path(folder))
            app.loop = asyncio.get_running_loop()
            delivered = []
            async def receive(*args):
                delivered.append((args[0], args[2]["seq"]))
            app.state.event = receive
            async with app.lock:
                for i in range(100):
                    app.telemetry("movement", {"seq": i})
                    app.telemetry("camera", {"seq": i})
                await asyncio.sleep(0)
                self.assertEqual(len(app.latest_updates), 2)
            for _ in range(3):
                await asyncio.sleep(0)
            self.assertCountEqual(delivered, [("movement", 99), ("camera", 99)])
