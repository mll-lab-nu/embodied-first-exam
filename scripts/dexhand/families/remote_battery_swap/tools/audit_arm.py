"""Authoring-only: replay a trajectory and audit the arm rig (arm/stand/parked-hand contacts, peak unsupported
fall speeds of the cells, remote/tray displacement and tilt, actuation)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "shared"))
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402
import arm_rig  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    actions, hand, _ = hands.read_trajectory(args.traj, widths={"sharpa": 58, "wuji": 54}, max_rows=6000,
                                             task="remote_battery_swap")
    s = Session(hand=hand)
    m, d = s.model, s.data
    arm = arm_rig.robot_body_ids(m)
    left = arm_rig.hand_body_ids(m, "left")
    owner = s.checker.geom_owner
    audit = {"arm_contacts": {}, "left_hand_contacts": {}, "peak_unsupported_fall_m_s": {"old_cell": 0.0, "new_cell": 0.0},
             "max_remote_disp_m": 0.0, "max_remote_tilt_deg": 0.0, "max_tray_disp_m": 0.0,
             "neq": int(m.neq), "nmocap": int(m.nmocap), "nu": int(m.nu),
             "non_robot_actuators": [m.actuator(i).name for i in range(m.nu)
                                     if owner[m.body(int(m.jnt_bodyid[m.actuator_trnid[i, 0]])).id] != "hand"
                                     and False]}
    s.reset()
    for k, row in enumerate(actions):
        s.step(row)
        for i in range(d.ncon):
            c = d.contact[i]
            b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
            for b, g_other in ((b1, c.geom2), (b2, c.geom1)):
                other = m.geom(int(g_other)).name or f"geom{int(g_other)}"
                if b in arm and int(m.geom_bodyid[g_other]) not in arm:
                    audit["arm_contacts"].setdefault(other, k)
                if b in left and int(m.geom_bodyid[g_other]) not in left:
                    audit["left_hand_contacts"].setdefault(other, k)
        f = s.features()
        audit["max_remote_disp_m"] = max(audit["max_remote_disp_m"], f["remote_displacement_m"])
        audit["max_remote_tilt_deg"] = max(audit["max_remote_tilt_deg"], f["remote_tilt_deg"])
        for name in ("old_cell", "new_cell"):
            touching = False
            bid = m.body(name).id
            for i in range(d.ncon):
                c = d.contact[i]
                if bid in (int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])):
                    touching = True
                    break
            if not touching:
                vz = float(d.qvel[s.checker.free_dof[name] + 2])
                audit["peak_unsupported_fall_m_s"][name] = max(audit["peak_unsupported_fall_m_s"][name], -vz)
        if s.done:
            break
    audit.update(success=s.success, reason=s.status()["reason"], steps=s.steps, state_sha=s.state_sha(), rows=len(actions))
    Path(args.out).write_text(json.dumps(audit, indent=1) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
