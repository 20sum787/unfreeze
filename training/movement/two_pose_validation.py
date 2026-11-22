"""Synthetic two-pose geometry test with actual v4 EIM replay.

Convention for this numerical experiment: F, up, and their cross product.
The device's physical handedness/sign convention needs an independent check.
"""
import json
from pathlib import Path
import sys

import numpy as np

root = Path(__file__).resolve().parent
board = root.parents[1] / "board/unfreeze-uno-q"
sys.path.insert(0, str(board / "python"))
from eim import Eim


def recover(upright, lean):
    vertical = upright / np.linalg.norm(upright)
    projection = lean - np.dot(lean, vertical) * vertical
    if np.linalg.norm(projection) < 0.1:
        raise ValueError("Insufficient difference between poses")
    forward = -projection / np.linalg.norm(projection)
    return np.column_stack((forward, vertical, np.cross(forward, vertical)))


rng = np.random.default_rng(245)
windows = {name: np.array(json.loads((board / "tools" / ("movement-" + name + ".json")).read_text())).reshape(-1, 3)
           for name in ("freeze", "normal")}
upright = np.array([0., 1., 0.])
pitch = np.deg2rad(25)
lean = np.array([-np.sin(pitch), np.cos(pitch), 0.])
engine = Eim(sys.argv[1])
try:
    refs = {key: engine.classify(rows.ravel().tolist())["freeze"] for key, rows in windows.items()}
    max_axis_err, max_score_err = 0., 0.
    for _ in range(40):
        mat, _tri = np.linalg.qr(rng.normal(size=(3, 3)))
        mat = mat @ np.diag(np.sign(np.diag(_tri)))
        if np.linalg.det(mat) < 0:
            mat[:, 0] *= -1
        estimated = recover(mat @ upright, mat @ lean)
        for key, rows in windows.items():
            recovered = (rows @ mat.T) @ estimated
            max_axis_err = max(max_axis_err, float(np.max(np.abs(recovered - rows))))
            score = engine.classify(recovered.ravel().tolist())["freeze"]
            max_score_err = max(max_score_err, abs(score - refs[key]))
    print(f"40 arbitrary fixed mounts, 2 windows: max axis error={max_axis_err}, max score error={max_score_err}")
    assert max_axis_err < 1e-12 and max_score_err < 1e-5
finally:
    engine.close()
