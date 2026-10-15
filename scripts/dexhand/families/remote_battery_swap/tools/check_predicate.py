"""Authoring-only: predicate unit checks on hand-free test instances (custom initial poses, then passive settling).

Each case moves objects only in the instance definition (never during an episode) and lets physics settle with the
hand parked high; it reports the stage conditions the checker computes from simulator state.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import Session  # noqa: E402


def quat(yaw_deg, axis_x=True):
    r = Rotation.from_euler("z", yaw_deg, degrees=True) * Rotation.from_euler("y", 90 if axis_x else 0, degrees=True)
    q = r.as_quat()
    return [float(q[3]), float(q[0]), float(q[1]), float(q[2])]


def case(base, **edits):
    cfg = copy.deepcopy(base)
    for k, v in edits.items():
        cfg[k] = v
    s = Session(config=cfg)
    hold = s.hold_action()
    # the arm holds its start pose (hand 0.18 m above the table, clear of every object)
    for _ in range(60):
        s.step(hold)
    f = s.features()
    return {"conditions": f["conditions"], "slot_error_mm": [round(1000 * e, 2) for e in f["new_cell_slot_error_m"]],
            "axis_deg": round(f["new_cell_axis_angle_deg"], 1), "ribs": f["new_cell_on_ribs"],
            "old_tray_local_mm": [round(1000 * e, 1) for e in f["old_cell_tray_local_m"]], "failure": s.failure}


def main():
    base = json.loads((HERE / "task.json").read_text())
    remote = np.asarray(base["remote_pos"])
    slot = remote + np.asarray(base["slot_center_local"])
    tray = np.asarray(base["tray_pos"])
    in_tray = [float(tray[0]), float(tray[1]), float(tray[2] + 0.003 + 0.007 + 0.001)]
    seat = [float(slot[0]), float(slot[1]), float(slot[2] + 0.0005)]
    results = {
        "goal_state (old in tray, new seated + to gold)": case(base, old_cell_pos=in_tray, old_cell_quat=quat(0),
                                                                new_cell_pos=seat, new_cell_quat=quat(0)),
        "reversed_polarity (new seated, + to spring)": case(base, old_cell_pos=in_tray, old_cell_quat=quat(0),
                                                             new_cell_pos=seat, new_cell_quat=quat(180)),
        "new_cell_pressed_to_gold_contact": case(base, old_cell_pos=in_tray, old_cell_quat=quat(0),
                                                 new_cell_pos=[seat[0] + 0.0043, seat[1], seat[2] + 0.0005],
                                                 new_cell_quat=quat(0)),
        "new_cell_on_terminal_block (not in slot)": case(base, old_cell_pos=in_tray, old_cell_quat=quat(0),
                                                         new_cell_pos=[seat[0] + 0.02, seat[1], seat[2] + 0.012],
                                                         new_cell_quat=quat(0)),
        "new_cell_across_slot (yaw 30 deg)": case(base, old_cell_pos=in_tray, old_cell_quat=quat(0),
                                                  new_cell_pos=[seat[0], seat[1], seat[2] + 0.01],
                                                  new_cell_quat=quat(30)),
        "old_cell_on_tray_rim": case(base, old_cell_pos=[in_tray[0], in_tray[1] + 0.037, in_tray[2] + 0.012],
                                     old_cell_quat=quat(0), new_cell_pos=seat, new_cell_quat=quat(0)),
    }
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
