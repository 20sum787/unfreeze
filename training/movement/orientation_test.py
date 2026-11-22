"""Replay the exact same observations under rigid rotations through the deployed v4 EIM."""
import itertools
import json
from pathlib import Path
import sys

import numpy as np

root = Path(__file__).resolve().parent
board = root.parents[1] / "board/unfreeze-uno-q"
sys.path.insert(0, str(board / "python"))
from eim import Eim

rotations = {}
for perm in itertools.permutations(range(3)):
    for signs in itertools.product((1, -1), repeat=3):
        matrix = np.eye(3)[list(perm)] * np.array(signs)[:, None]
        if np.linalg.det(matrix) > 0:
            label = ",".join(("-" if sign == -1 else "+") + "FVL"[col]
                             for sign, col in zip(signs, perm))
            rotations[label] = matrix
assert len(rotations) == 24
engine = Eim(sys.argv[1])
try:
    for name in ("freeze", "normal"):
        data = np.array(json.loads((board / "tools" / ("movement-" + name + ".json")).read_text())).reshape(-1, 3)
        scores = {}
        max_error = 0
        for label, matrix in rotations.items():
            rotated = data @ matrix.T
            scores[label] = engine.classify(rotated.ravel().tolist())["freeze"]
            recovered = rotated @ matrix
            assert np.array_equal(recovered, data)
        print(name, json.dumps(scores))
        print(">=0.75", sum(v >= 0.75 for v in scores.values()), ">=0.5", sum(v >= 0.5 for v in scores.values()))
        (root / (name + "-rotations.json")).write_text(json.dumps(scores, indent=2))
finally:
    engine.close()
