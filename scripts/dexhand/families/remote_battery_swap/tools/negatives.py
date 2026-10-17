"""Authoring-only: controller-made negative episodes on the arm rig (each saved as an ordinary trajectory archive).

* ``force_door_without_tab``: the index pad pushes the thumb tab's front edge toward -x without pressing it down
  (the latch hook stays in front of the stop: the door must not open).
* ``release_3cm_above_tray``: the oracle controller opens the pinch with the gray cell 3 cm above the tray floor.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import demo  # noqa: E402
from runtime import Session  # noqa: E402


def force_door(out):
    s = Session()
    c = demo.Controller(s, log=lambda *a: None)
    c.hold(25, "settle")
    tab = demo.tab_point(c, 0.0)
    R = demo.yaw_rotation(c.remote_yaw(), 0.75)
    axis = {"index": np.array([0.35, 0.0, -0.94]) / np.linalg.norm([0.35, 0.0, -0.94])}
    edge = tab + np.array([0.009 + 0.0081 + 0.001, 0.0, -0.0015])  # pad beside the tab's +x face, above the door
    var = c.WRIST + c.ACT["index"]
    q_pre, _, _ = c.solve({"index": edge + [0, 0, 0.015]}, demo.base_seed(c), var, R_hand=R, rot_weight=0.2,
                          avoid=("remote",), allow=("index",), pad=True, tip_axis=axis)
    q_edge, _, _ = c.solve({"index": edge}, q_pre, var, R_hand=R, rot_weight=0.2, allow=("index",), pad=True,
                           tip_axis=axis)
    c.execute(c.at_pose(q_pre, dp=(0, 0, 0.08)), 70, "above")
    c.execute(q_pre, 50, "over the tab edge")
    c.execute(q_edge, 40, "finger at the tab edge")
    for k in range(6):
        q_edge = c.at_pose(q_edge, dp=(-0.006, 0, 0))
        c.execute(q_edge, 25, "push the door by the tab edge")
    c.hold(20, "hold")
    s.save_trajectory(np.asarray(s.actions), out)
    st = s.status()
    st["cover_slide_m"] = float(s.data.qpos[s.checker.cover_qadr])
    return st


def release_high(out):
    summary = demo.make_demo(out, slack_rows=0, log=lambda *a: None, tray_kw={"release_clearance": 0.03})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in (("force_door_without_tab", force_door),
                     ("release_3cm_above_tray", release_high)):
        if args.only and name not in args.only:
            continue
        st = fn(out / f"{name}.npz")
        print(name, {k: st.get(k) for k in ("success", "reason", "steps", "stage", "failure_detail", "cover_slide_m")})


if __name__ == "__main__":
    main()
