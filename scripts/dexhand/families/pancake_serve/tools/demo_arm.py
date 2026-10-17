"""Authoring only: the wave-2 turner-pose servo (tools/demo.py) driving the right Marvin arm through IK.

Every control the desired pose of the hand mount ("wrist_stage", rigidly carrying the hand) is computed from the
MEASURED mount->turner transform so that the blade reaches the scripted waypoint (as in demo.py); damped
least-squares IK plus a joint integral (shared/arm_ik.py) turns it into right-arm joint targets; the fingers keep the
reset grasp targets; the left arm stays parked. Rows are rounded to float32 before they are executed and recorded.

    python tools/demo_arm.py --out solution/trajectory.npz [--params '{...}']
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
for _parent in HERE.parents:
    if (_parent / "shared/arm_ik.py").is_file():
        sys.path.append(str(_parent / "shared"))
        break

import arm_ik  # noqa: E402
import arm_rig  # noqa: E402
import demo  # noqa: E402


class ArmController(demo.Controller):
    def __init__(self, session, params=None):
        self.s = session
        self.p = dict(params or {})
        m = session.model
        self.turner = m.body("turner").id
        self.stage_body = m.body("wrist_stage").id
        self.lay = arm_rig.layout(m)
        self.ik = arm_ik.ArmIK(m, "right", body="wrist_stage")
        self.lo, self.hi = m.actuator_ctrlrange.T
        self.row = session.initial_targets.copy()
        self.prev_q = self.row[self.lay["arm"]["right"]].copy()
        self.bias = np.zeros(7)
        self.ki = self.p.get("ki_arm", 0.25)
        self.prev = None
        self.rows, self.phases = [], []
        self.max_err = 0.0

    def wrist_targets(self, tip, R_des):
        d = self.s.data
        Rw = d.xmat[self.stage_body].reshape(3, 3)
        Rt = d.xmat[self.turner].reshape(3, 3)
        R_wt = Rw.T @ Rt
        p_wt = Rw.T @ (d.xpos[self.turner] - d.xpos[self.stage_body])
        p_turner = tip - R_des @ demo.TIP_LOCAL
        R_wrist = R_des @ R_wt.T
        return p_turner - R_wrist @ p_wt, R_wrist

    def command(self, target, phase):
        d = self.s.data
        pos, R = target
        sl = self.lay["arm"]["right"]
        q_meas = d.qpos[self.ik.qadr].copy()
        q_star, ep, er = self.ik.solve(pos, R, q0=self.prev_q - self.bias, qpos=d.qpos)
        self.max_err = max(self.max_err, ep)
        self.bias = np.clip(self.bias + self.ki * (q_star - q_meas), -0.25, 0.25)
        self.row[sl] = np.clip(q_star + self.bias, self.lo[sl], self.hi[sl])
        self.prev_q = self.row[sl].copy()
        row = np.clip(np.clip(self.row, self.lo, self.hi).astype(np.float32).astype(np.float64), self.lo, self.hi)
        self.s.step(row)
        self.rows.append(row)
        self.phases.append(phase)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--phases")
    args = parser.parse_args()
    demo.Controller = ArmController
    status, c = demo.run(json.loads(args.params), args.out, verbose=True, phases_out=args.phases)
    print(json.dumps({k: status[k] for k in ("success", "reason", "stage", "steps", "failure_detail")}, default=str))
    print("max IK pos err", round(c.max_err, 4), "rows", len(c.rows))


if __name__ == "__main__":
    main()
