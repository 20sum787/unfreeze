"""Compare one Studio raw-feature window with this board's exact Movement EIM."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from eim import Eim
from motion import MotionWindows

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("features", type=Path, help="Studio raw features, comma-separated or JSON array")
    parser.add_argument("--expected-label", help="Optional Studio winning label to compare")
    args = parser.parse_args()
    cfg = json.loads((ROOT/"python/motion.json").read_text())
    windows = MotionWindows(cfg)
    model = Eim(ROOT/cfg["modelFile"])
    try:
        windows.verify_model(model.info["model_parameters"], model.info.get("project"))
        text = args.features.read_text(encoding="utf-8-sig").strip()
        values = json.loads(text) if text.startswith("[") else text.split(",")
        features = [float(value) for value in values]
        if len(features) != model.info["model_parameters"]["input_features_count"]:
            parser.error("Raw features length differs from EIM")
        scores = model.classify(features)
        winner = max(scores, key=scores.get)
        print(json.dumps({"project":model.info["project"], "scores":scores, "winner":winner}))
        if args.expected_label and winner != args.expected_label:
            sys.exit("Studio label mismatch; check model version, preprocessing and axis order")
    finally:
        model.close()
