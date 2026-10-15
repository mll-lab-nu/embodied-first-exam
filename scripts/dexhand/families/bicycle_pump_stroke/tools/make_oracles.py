"""Authoring-only: regenerate the reference trajectories deterministically (Sharpa and Wuji).

python tools/make_oracles.py --out solution
writes solution/trajectory.npz (Sharpa Wave) and solution/wuji/trajectory.npz (Wuji Hand 2.2): the closed-loop
pumping controller of tools/controller.py recorded as open-loop rows, plus HOLD_ROWS rows holding the final targets
(slack after success; a replay ends at success anyway). Each archive is checked by an open-loop replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
from controller import Pumper  # noqa: E402
from runtime import Session  # noqa: E402

HOLD_ROWS = 100
PARAMS = {
    # Palm centroid offset from the wrist-stage frame and pressing heights measured for each hand (palm-down mount).
    "sharpa": {"palm_offset": [-0.0055, 0.0418], "press_world_z": 0.975, "top_world_z": 1.19,
               "grip": [0.3, 0, 0.3, 0, 0.3] + [0.9, 0, 0.9, 0.54] * 3 + [0, 0.9, 0, 0.9, 0.54]},
    "wuji": {"palm_offset": [0.001, 0.0576], "press_world_z": 0.962, "top_world_z": 1.185,
             "grip": [0.3, 0, 0.3, 0.3] + [0.9, 0, 0.9, 0.5] * 4},
}


def make(hand, path):
    session = Session(hand=hand)
    rows = Pumper(session, PARAMS[hand]).run()
    status = session.status()
    if not status["success"]:
        raise RuntimeError(f"{hand}: controller did not succeed: {status['reason']}")
    rows = np.vstack([rows, np.repeat(rows[-1:], HOLD_ROWS, axis=0)])
    path.parent.mkdir(parents=True, exist_ok=True)
    session.save_trajectory(rows, path)
    check = Session(hand=hand).replay(rows)
    if not check["success"]:
        raise RuntimeError(f"{hand}: open-loop replay failed: {check['reason']}")
    return {"hand": hand, "path": str(path), "rows": int(len(rows)), "success_step": int(check["steps"]),
            "slack_rows": int(len(rows) - check["steps"]), "stroke_controls": check["stroke_controls"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(HERE / "solution"))
    parser.add_argument("--hands", default="sharpa,wuji")
    args = parser.parse_args()
    out = Path(args.out)
    report = []
    for hand in args.hands.split(","):
        path = out / ("trajectory.npz" if hand == "sharpa" else f"{hand}/trajectory.npz")
        report.append(make(hand, path))
        print(json.dumps(report[-1]), flush=True)


if __name__ == "__main__":
    main()
