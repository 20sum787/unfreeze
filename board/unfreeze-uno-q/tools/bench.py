"""Run over SSH from inside the App folder, while a companion session is active."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit one labelled bench event to this running UNO Q App")
    parser.add_argument("kind", choices=["door", "prefreeze", "freeze"])
    args = parser.parse_args()
    if not json.loads((ROOT / "python/runtime.json").read_text())["benchInjection"]:
        parser.error("Set benchInjection to true in python/runtime.json, then Stop and Run first")
    directory = ROOT / "data"
    if not directory.is_dir():
        parser.error("Start the App in App Lab first")
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as tmp:
        json.dump({"kind": args.kind, "created": time.time()}, tmp)
    os.replace(tmp.name, directory / "bench-request.json")
    print("Submitted. Watch the connected client's Debug events for origin=simulated.")
