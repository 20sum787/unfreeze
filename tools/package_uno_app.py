"""Create fresh import archives from the same reviewed App Lab source and validate their contents."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "board/unfreeze-uno-q"
sys.path.insert(0, str(SOURCE / "tools"))
from sync_config import sync
HW_MANIFEST = """name: Unfreeze Hardware Check
icon: 🔧
description: Movement, Buzzer, Vibro and companion without the camera service.
ports:
  - {port}
bricks: []
"""


def package(hardware_only):
    settings = sync(SOURCE)
    approved_models = json.loads((SOURCE / "models/checksums.json").read_bytes())
    folder = "unfreeze-uno-q-hardware" if hardware_only else SOURCE.name
    name = "Unfreeze-UNO-Q-hardware-only.zip" if hardware_only else "Unfreeze-UNO-Q-AppLab.zip"
    target = ROOT / "dist" / name
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target.with_suffix(".tmp"), "w") as archive:
        for path in sorted(SOURCE.rglob("*")):
            rel = path.relative_to(SOURCE)
            if not path.is_file() or any(s in ("__pycache__", ".cache", "data", ".git", "build", ".build",
                                               ".pio", "dist", ".idea", ".vscode", ".venv") for s in rel.parts):
                continue
            if (path.suffix in (".pyc", ".elf", ".hex", ".bin", ".map", ".su", ".log") or
                    path.name.startswith((".env", ".app-yaml-"))):
                continue
            if hardware_only and rel.as_posix() in ("models/door-v6.eim", "tools/check_camera.py",
                                                    "tools/door-frame.rgb", "tests/test_camera_adapter.py"):
                continue
            body = path.read_bytes()
            if hardware_only and rel.as_posix() == "app.yaml":
                body = HW_MANIFEST.format(port=settings["COMPANION_PORT"]).encode()
            if hardware_only and rel.as_posix() == "python/runtime.json":
                cfg = json.loads(body)
                cfg["cameraEnabled"] = False
                body = (json.dumps(cfg, indent=2) + "\n").encode()
            info = zipfile.ZipInfo(f"{folder}/{rel.as_posix()}")
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == ".eim" else 0o100644) << 16
            info.compress_type = zipfile.ZIP_STORED if path.suffix == ".whl" else zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    with zipfile.ZipFile(target.with_suffix(".tmp")) as archive:
        assert archive.testzip() is None
        entries = archive.namelist()
        assert all(n.startswith(folder + "/") for n in entries)
        assert not any("/data/" in n for n in entries)
        for needed in ("sketch/sketch.yaml", "sketch/sketch.ino", "app.yaml", "python/main.py",
                       "python/web/vendor/socket.io-4.8.1.min.js", "python/requirements.txt",
                       "python/requirements-common.txt", "tools/movement-freeze.json", "tools/movement-normal.json",
                       "tools/preflight.py", "sketch/config.h", "QUICKSTART_CHECKLIST.md", "HARDWARE.md",
                       "MEMORY_AUDIT.md", "models/checksums.json"):
            assert f"{folder}/{needed}" in entries, needed
        assert len([n for n in entries if "/wheels/companion/" in n and n.endswith(".whl")]) == 15
        movement = folder + "/models/movement.eim"
        assert archive.getinfo(movement).external_attr >> 16 == 0o100755
        assert hashlib.sha256(archive.read(movement)).hexdigest() == approved_models["movement.eim"]
        if not hardware_only:
            path = folder + "/models/door-v6.eim"
            assert archive.getinfo(path).external_attr >> 16 == 0o100755
            assert hashlib.sha256(archive.read(path)).hexdigest() == approved_models["door-v6.eim"]
    target.with_suffix(".tmp").replace(target)
    print(name, len(entries), target.stat().st_size, hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    package(False)
    package(True)
