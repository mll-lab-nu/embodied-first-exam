"""Wuji Hand 2.2 solution for DexHand `paper_half_fold` (privileged mode): scripted, motor targets only.

Strategy (all rows are wrist-stage + Wuji finger position targets; nothing else acts on the paper):
  A. Retreat from the reset pose, roll the hand palm up (fingers toward -x, thumb tucked low and clear of the palm),
     drop below the table top outside the table and slide the four fingertip pads under the 25 mm overhang.
  B. Flip: rotate the whole hand rigidly about the fold line (world -y axis through x = 0.08 m, z = 0.3012 m) by
     2.95 rad. The fingertip pads stay at a fixed place on the underside of the free half, so the free half turns
     about its fold line without slipping, and the fold-line hinges yield plastically (permanent crease).
  C. Lift 12 mm, move the fingertips 5 cm toward the fold line and press lightly on the folded stack.
  D. Lift 6 cm straight up and hold still while the released fold is checked (100 samples).

Usage (host or inside the task image, with the task's tooling importable):
    python wuji_gen.py --out /app/output/trajectory.npz   (regenerates ../solution/wuji/trajectory.npz byte for byte)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

try:
    from rcb_dexhand import Session
except ImportError:  # authoring checkout: runtime.py on PYTHONPATH
    from runtime import Session

FOLD_X, FOLD_Z = 0.08, 0.3012
TIP_BODIES = ["index_finger", "middle_finger", "ring_finger", "pinky"]

PARAMS = dict(rz=3.13, thumb=[-1.1, -0.9, 0.0, 0.0], flex=[0.3, 0.33, 0.3, 0.25], tip_x=0.139, tip_z=0.2995,
              n_a1=30, n_a2=50, n_a3=40, n_a4=30, n_a5=20, theta_max=2.95, n_b=150,
              lift_c=0.012, press_dx=0.05, press_depth=0.002, n_c1=20, n_c2=40, n_c3=30, n_c4=40,
              lift_d=0.06, n_d1=40, n_hold=130)


def Ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


class Planner:
    """Kinematics on a scratch MjData (never the episode's data)."""

    def __init__(self, session, P):
        self.s, self.P = session, P
        self.m = session.model
        self.d = mujoco.MjData(self.m)
        self.lo, self.hi = self.m.actuator_ctrlrange.T
        m = self.m
        self.tip_geoms = []
        for g in range(m.ngeom):
            name = m.geom(g).name or ""
            if (m.geom_contype[g] and m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and any(t in name for t in TIP_BODIES)
                    and ("tip" in name or "distal" in name)):
                mid = m.geom_dataid[g]
                a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
                self.tip_geoms.append((g, m.mesh_vert[a:a + n].copy()))

    def fingers(self):
        f = np.zeros(20)
        f[0:4] = self.P["thumb"]
        for i in range(4):  # index, middle, ring, little: MCP flexion only, straight PIP/DIP, no abduction
            f[4 + 4 * i] = self.P["flex"][i]
        return f

    def tip_vertices(self, q):
        self.d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, self.d)
        out = []
        for g, v in self.tip_geoms:
            R = self.d.geom_xmat[g].reshape(3, 3)
            out.append(v @ R.T + self.d.geom_xpos[g])
        return np.concatenate(out)

    def base_pose(self):
        """theta = 0: palm up, fingers toward -x, fingertip tops at tip_z, fingertip front at tip_x, centred on y = 0."""
        P = self.P
        q = np.zeros(self.s.action_dim)
        q[3:6] = [0.0, 0.0, P["rz"]]
        q[6:] = self.fingers()
        q[:3] = [0.3, 0.0, 0.25]
        tips = self.tip_vertices(q)
        q[0] += P["tip_x"] - tips[:, 0].min()
        q[1] += -0.5 * (tips[:, 1].min() + tips[:, 1].max())
        q[2] += P["tip_z"] - tips[:, 2].max()
        return q

    @staticmethod
    def rotated(q0, theta):
        """The hand of q0 rotated rigidly by theta about the fold line (rx = 0, so only ry and the position change)."""
        q = q0.copy()
        A = np.array([FOLD_X, q0[1], FOLD_Z])
        q[:3] = A + Ry(-theta) @ (q0[:3] - A)
        q[4] = q0[4] - theta
        return q


def lerp(a, b, n):
    return [a + (b - a) * t for t in np.linspace(0, 1, n + 1)[1:]]


def build(session, P=PARAMS) -> np.ndarray:
    pl = Planner(session, P)
    start = session.hold_action().copy()
    q0 = pl.base_pose()
    rows = []
    # A: retreat (+x, up), reorient palm up, descend outside the table, slide under the overhang, touch.
    a1 = start.copy(); a1[0] = q0[0] + 0.06; a1[2] = start[2] + 0.04
    rows += lerp(start, a1, P["n_a1"])
    a2 = q0.copy(); a2[0] = q0[0] + 0.06; a2[2] = a1[2]
    rows += lerp(a1, a2, P["n_a2"])
    a3 = q0.copy(); a3[0] = q0[0] + 0.035; a3[2] = q0[2] - 0.012
    rows += lerp(a2, a3, P["n_a3"])
    a4 = q0.copy(); a4[2] = q0[2] - 0.012
    rows += lerp(a3, a4, P["n_a4"])
    rows += lerp(a4, q0, P["n_a5"])
    # B: flip about the fold line with a smooth (cosine) angle profile.
    for th in P["theta_max"] * (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, P["n_b"] + 1)[1:])):
        rows.append(pl.rotated(q0, th))
    qb = rows[-1].copy()
    # C: lift, move over the crease, light press, dwell.
    c1 = qb.copy(); c1[2] += P["lift_c"]
    rows += lerp(qb, c1, P["n_c1"])
    c2 = c1.copy(); c2[0] += P["press_dx"]
    rows += lerp(c1, c2, P["n_c2"])
    c3 = c2.copy(); c3[2] -= P["lift_c"] + P["press_depth"]
    rows += lerp(c2, c3, P["n_c3"])
    rows += [c3.copy() for _ in range(P["n_c4"])]
    # D: lift away and hold.
    d1 = c3.copy(); d1[2] += P["lift_d"]
    rows += lerp(c3, d1, P["n_d1"])
    rows += [d1.copy() for _ in range(P["n_hold"])]
    return np.clip(np.asarray(rows, dtype=np.float64), pl.lo, pl.hi)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/app/output/trajectory.npz"))
    args = parser.parse_args()
    s = Session("paper_half_fold", hand="wuji")
    rows = build(s)
    status = s.replay(rows)  # check in this process before saving
    args.out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(rows, args.out)
    print(json.dumps({"rows": int(len(rows)), "width": int(rows.shape[1]), "status": status}, indent=1))


if __name__ == "__main__":
    main()
