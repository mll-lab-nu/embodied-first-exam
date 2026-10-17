#!/usr/bin/env python3
"""Authoring only (not shipped): count active contacts per geom pair over every physics substep of a trajectory.

Categories: robot self-contacts (any two geoms of the Marvin subtree `base_link`: stand, torso, arms, flanges and both
hands; contacts between two geoms of the same hand are listed separately), arm-link / stand / parked-hand contacts with
anything outside the robot (furniture or task objects), and active-hand contacts with furniture (allowed: fingers or
palm on the desk). The physics is stepped exactly like runtime.Session.step (same ctrl, same substeps).

  python tools/robot_contacts_audit.py --traj solution/trajectory.npz --out robot_contacts.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import mujoco

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.append(str(HERE.parents[1] / "shared"))

from runtime import Session  # noqa: E402
from replay import load_trajectory  # noqa: E402
from check_robot_furniture import subtree  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, hand, _ = load_trajectory(a.traj)
    s = Session(hand=hand)
    m, d = s.model, s.data
    robot = subtree(m, m.body("base_link").id)
    right = subtree(m, m.body("wrist_stage").id)
    left_root = [b for b in robot if m.body(b).name in ("left_hand_mount", "left_hand_C_MC")]
    left = subtree(m, left_root[0]) if left_root else set()
    static = {0}

    def kind(b):
        if b in right:
            return "right_hand"
        if b in left:
            return "left_hand"
        if b in robot:
            return "arm_or_stand"
        if b in static:
            return "furniture"
        return "object"

    def gname(g):
        return m.geom(g).name or f"{m.body(int(m.geom_bodyid[g])).name}/geom{g}"

    counts = {"robot_self": {}, "same_hand": {}, "arm_stand_vs_outside": {}, "hand_vs_furniture": {}, "hand_vs_objects": {}}
    episode = s.replay(rows)
    n_controls = s.steps  # the graded episode ends here (success or failure)
    s.reset()
    lo, hi = m.actuator_ctrlrange.T
    substeps = 0
    for k, row in enumerate(rows):
        d.ctrl[:] = np.clip(row, lo, hi)
        for _ in range(s.substeps):
            mujoco.mj_step(m, d)
            substeps += 1
            for i in range(d.ncon):
                c = d.contact[i]
                if c.efc_address < 0:
                    continue
                b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
                k1, k2 = kind(b1), kind(b2)
                pair = " | ".join(sorted((gname(c.geom1), gname(c.geom2))))
                if b1 in robot and b2 in robot:
                    cat = "same_hand" if (k1 == k2 and k1.endswith("hand")) else "robot_self"
                elif "arm_or_stand" in (k1, k2) or "left_hand" in (k1, k2):
                    cat = "arm_stand_vs_outside"
                elif "right_hand" in (k1, k2) and "furniture" in (k1, k2):
                    cat = "hand_vs_furniture"
                elif "right_hand" in (k1, k2) and "object" in (k1, k2):
                    cat = "hand_vs_objects"
                else:
                    continue
                counts[cat][pair] = counts[cat].get(pair, 0) + 1
        if k + 1 >= n_controls:
            break
    report = {"hand": hand, "episode": episode["reason"], "controls": k + 1, "substeps": substeps,
              "robot_self_contacts": sum(counts["robot_self"].values()),
              "arm_stand_parked_hand_vs_furniture_or_objects": sum(counts["arm_stand_vs_outside"].values()),
              "same_hand_contacts": sum(counts["same_hand"].values()),
              "active_hand_vs_furniture_substeps": sum(counts["hand_vs_furniture"].values()),
              "active_hand_vs_objects_contacts (sanity: the oracle works through contact)": sum(counts["hand_vs_objects"].values()),
              "pairs": {k_: dict(sorted(v.items(), key=lambda t: -t[1])[:10]) for k_, v in counts.items()}}
    Path(a.out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k_: v for k_, v in report.items() if k_ != "pairs"}, indent=1))
    print(json.dumps(report["pairs"], indent=1)[:1500])


if __name__ == "__main__":
    main()
