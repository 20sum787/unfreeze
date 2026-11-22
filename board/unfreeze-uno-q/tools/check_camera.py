"""Check camera EIM and one packaged frame on the UNO Q without opening a camera."""
from array import array
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from eim import Eim

if __name__ == "__main__":
    model = Eim(ROOT/"models/door-v6.eim", timeout=30)
    try:
        p = model.info["model_parameters"]
        print(json.dumps({"project":model.info["project"], "labels":p["labels"],
                          "size":[p["image_input_width"],p["image_input_height"]]}))
        if p["labels"] != ["door"] or p["input_features_count"] != 192*192:
            sys.exit("Unexpected camera model")
        rgb = (ROOT/"tools/door-frame.rgb").read_bytes()
        if len(rgb) != 192*192*3:
            sys.exit("Bad fixture size")
        pixels = [int.from_bytes(rgb[i:i+3], "big") for i in range(0,len(rgb),3)]
        shm = model.info.get("features_shm")
        if shm:
            with (Path("/dev/shm")/shm["name"].lstrip("/")).open("r+b") as stream:
                stream.write(array("f", pixels).tobytes())
            reply = model.request({"classify_shm":{"elements":len(pixels)}})
        else:
            reply = model.request({"classify": pixels})
        boxes = reply["result"]["bounding_boxes"]
        print(json.dumps({"boxes":boxes,"timing":reply.get("timing")}))
        if not any(box.get("label") == "door" for box in boxes):
            sys.exit("EIM responded with no door box on this fixture. See camera diagnostic in README.")
    finally:
        model.close()
