"""Run over SSH in the imported app (host Debian). Uses only the Python standard library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from sync_config import ROOT, sync


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def camera_paths(root, fix):
    manifest = root / "app.yaml"
    text = manifest.read_text(encoding="utf-8")
    if not json.loads((root / "python/runtime.json").read_bytes())["cameraEnabled"]:
        return
    for key, path in (("CUSTOM_MODEL_PATH", root / "models"),
                      ("EI_V_OBJ_DETECTION_MODEL", root / "models/door-v6.eim")):
        pattern = re.compile(r"(?m)^(\s*" + key + r":)[^\n]*$")
        updated, n = pattern.subn(lambda m: m[1] + " " + json.dumps(str(path), ensure_ascii=False), text)
        if n != 1:
            raise ValueError(f"Expected exactly one {key} in app.yaml")
        text = updated
    if text == manifest.read_text(encoding="utf-8"):
        return
    if not fix:
        raise ValueError("Camera path differs. On board host run: python3 tools/preflight.py --fix-paths")
    if sys.platform != "linux" or root == Path("/app"):
        raise ValueError("Fix paths over SSH in the imported app on the UNO Q Debian host")
    fd, tmpname = tempfile.mkstemp(prefix=".app-yaml-", dir=root)
    temp = Path(tmpname)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        temp.chmod(stat.S_IMODE(manifest.stat().st_mode))
        temp.replace(manifest)
    finally:
        temp.unlink(missing_ok=True)
    print("Updated camera paths in", manifest)


def check(root, fix=False):
    settings = sync(root)
    models = json.loads((root / "models/checksums.json").read_bytes())
    camera = json.loads((root / "python/runtime.json").read_bytes())["cameraEnabled"]
    for name, sha in models.items():
        if name == "door-v6.eim" and not camera:
            continue
        path = root / "models" / name
        if digest(path) != sha:
            raise ValueError(f"Model SHA-256 mismatch: {path}")
        if sys.platform == "linux" and not os.access(path, os.X_OK):
            raise ValueError(f"Missing execute permission. Run chmod +x '{path}'")
        print("Verified model", name)
    wheels = root / "wheels/companion"
    for line in (wheels / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        sha, name = line.split()
        if digest(wheels / name) != sha:
            raise ValueError(f"Dependency checksum mismatch: {name}")
    camera_paths(root, fix)
    print("App files OK; companion port", settings["COMPANION_PORT"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-paths", action="store_true", help="Set the two camera paths to this imported directory")
    try:
        check(ROOT, parser.parse_args().fix_paths)
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"Preflight failed: {exc}")
