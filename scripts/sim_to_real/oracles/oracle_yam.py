"""Reference solutions for the sim_to_real YAM tasks (solution/ only; never in the agent's image).

A scripted controller on the privileged tooling: damped-least-squares IK on each arm's `grasp_site` (position and full
orientation, the arm has 6 joints), Cartesian waypoints interpolated in joint space, the rate limit applied by
`Session.step`. Grasps come from each object's mesh (grasp centre and the finger axis across its narrowest horizontal
side); the approach tilts away from the base (0-45 degrees) where a vertical approach is out of the YAM's workspace.
Writes the applied targets of one successful run.

    python oracle_yam.py <instance.json> <out_targets.npy>
"""

from __future__ import annotations

import json
import sys

import numpy as np
import rcb_yam as ry

DOWN = np.array([0.0, 0.0, -1.0])


def frame(approach, fingers) -> np.ndarray:
    """grasp_site orientation: z = approach direction, y = finger slide axis."""
    z = np.asarray(approach, float) / np.linalg.norm(approach)
    y = np.asarray(fingers, float) - np.dot(fingers, z) * z
    y /= np.linalg.norm(y)
    return np.c_[np.cross(y, z), y, z]


class Arm:
    def __init__(self, s: ry.Session, side: str):
        import mujoco

        self.mj, self.s, self.side = mujoco, s, side
        self.m = s.model
        self.d = mujoco.MjData(self.m)
        self.site = self.m.site(f"{side}/grasp_site").id
        self.cols = slice(0, 6) if side == "left" else slice(7, 13)
        self.grip_col = 6 if side == "left" else 13
        self.qadr = np.array([s._qadr[f"{side}/{j}"] for j in ry.ARM_JOINTS])
        self.dof = np.array([self.m.jnt_dofadr[self.m.joint(f"{side}/{j}").id] for j in ry.ARM_JOINTS])
        self.lo = self.m.jnt_range[[self.m.joint(f"{side}/{j}").id for j in ry.ARM_JOINTS], 0]
        self.hi = self.m.jnt_range[[self.m.joint(f"{side}/{j}").id for j in ry.ARM_JOINTS], 1]

    def fk(self, q):
        self.d.qpos[self.qadr] = q
        self.mj.mj_kinematics(self.m, self.d)
        self.mj.mj_comPos(self.m, self.d)
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def ik(self, pos, R, q0, iters=300) -> np.ndarray:
        q = np.array(q0, float)
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        for _ in range(iters):
            p, Rc = self.fk(q)
            ep = pos - p
            er = 0.5 * sum(np.cross(Rc[:, i], R[:, i]) for i in range(3))
            e = np.r_[ep, 0.3 * er]
            if np.linalg.norm(ep) < 2e-4 and np.linalg.norm(er) < 2e-3:
                break
            self.mj.mj_jacSite(self.m, self.d, jp, jr, self.site)
            J = np.r_[jp[:, self.dof], 0.3 * jr[:, self.dof]]
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
            q = np.clip(q + np.clip(dq, -0.2, 0.2), self.lo, self.hi)
        p, Rc = self.fk(q)
        err = np.linalg.norm(pos - p)
        if err > 2e-3:
            raise RuntimeError(f"{self.side} IK failed: {err:.4f} m from {pos}")
        return q


class Runner:
    def __init__(self, inst_path: str):
        self.s = ry.Session(inst_path)
        self.arm = {k: Arm(self.s, k) for k in ("left", "right")}
        self.cmd = self.s.targets.copy()
        self.rng = np.random.default_rng(0)
        self.s.record_start()

    def q(self, side):
        return self.cmd[self.arm[side].cols].copy()

    def solve(self, side, pos, R, near=None):
        """IK from the current command first, else from seeded random starts; the solution nearest `near`."""
        a = self.arm[side]
        near = self.q(side) if near is None else near
        sols = []
        for q0 in [near] + [self.rng.uniform(a.lo, a.hi) for _ in range(60)]:
            try:
                sols.append(a.ik(np.asarray(pos, float), R, q0))
            except RuntimeError:
                continue
            if len(sols) >= 8:
                break
        if not sols:
            raise RuntimeError(f"{side}: no IK solution for {pos}")
        return min(sols, key=lambda q: np.linalg.norm(q - near))

    def hold(self, n):
        for _ in range(n):
            self.s.step(self.cmd)

    def joints(self, moves: dict, n: int):
        """Move the named arms to joint goals over n control steps (linear in joint space), then let them catch up."""
        start = {k: self.q(k) for k in moves}
        for i in range(1, n + 1):
            for k, qg in moves.items():
                self.cmd[self.arm[k].cols] = start[k] + (qg - start[k]) * i / n
            self.s.step(self.cmd)
        self.settle(0)

    def line(self, side, pos, R, n):
        """Straight Cartesian line of the grasp site to pos (orientation R) in n steps, IK at every step."""
        a = self.arm[side]
        p0, _ = a.fk(self.q(side))
        q = self.q(side)
        for i in range(1, n + 1):
            q = a.ik(p0 + (np.asarray(pos) - p0) * i / n, R, q)
            self.cmd[a.cols] = q
            self.s.step(self.cmd)
        self.settle(0)

    def grip(self, side, g, n=15):
        self.cmd[self.arm[side].grip_col] = g
        self.hold(n)

    def settle(self, n=25):
        """Wait until the applied targets have caught up with the command (rate limit), then n more steps."""
        while np.max(np.abs(self.s.targets - self.cmd)) > 1e-9:
            self.s.step(self.cmd)
        self.hold(n)


def yaw_of(quat_wxyz):
    w, x, y, z = quat_wxyz
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def quat_mat(q):
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


# Per object: the local axis the fingers close along, and where to grasp (local z: "center" or "top-<m>").
GRASP = {
    "banana": ("x", "mid"),
    "lemon": ("y", "center"),
    "orange": ("x", "center"),
    "tomato_soup_can": ("x", "top-0.025"),
    "foam_brick": ("x", "top-0.02"),
    "spam_can": ("y", "top-0.025"),
    "marker": ("x", "center"),
}
TILTS = np.radians([0, 10, 20, 30, 40, 50])


def _verts(name):
    pts = [
        list(map(float, ln.split()[1:4]))
        for ln in open(ry.ASSETS / "objects" / name / "visual.obj")
        if ln.startswith("v ")
    ]
    return np.array(pts)


class Planner:
    def __init__(self, r: Runner):
        self.r, self.s = r, r.s
        self.base = {"left": np.zeros(3), "right": ry.RIGHT_BASE.copy()}

    def grasp(self, name):
        """World grasp point, finger axis, and the held object's bottom below the grasp point."""
        o = self.s.state()["objects"][name]
        R, p = quat_mat(o["quat_wxyz"]), o["pos"]
        v = _verts(name)
        ax, where = GRASP[name]
        if where == "mid":  # a banana: the mid cross-section, not the bbox centre (it is curved)
            sel = v[np.abs(v[:, 1] - np.median(v[:, 1])) < 0.012]
            c = sel.mean(0)
        else:
            c = (v.min(0) + v.max(0)) / 2
            if where.startswith("top"):
                c[2] = v[:, 2].max() - float(where[4:])
        g = p + R @ c
        f = R[:, "xyz".index(ax)].copy()
        f[2] = 0
        f /= np.linalg.norm(f)
        bottom = (p + (R @ v.T).T)[:, 2].min()
        return g, f, g[2] - bottom

    def frames(self, side, pos, fingers):
        """Candidate orientations at pos: approach tilted away from the base by each of TILTS."""
        d = np.asarray(pos)[:2] - self.base[side][:2]
        d /= np.linalg.norm(d)
        f = np.asarray(fingers, float)
        if f @ np.array([-d[1], d[0], 0]) < 0:  # fingers' sign closest to the arm's natural wrist roll
            f = -f
        return [frame([np.sin(t) * d[0], np.sin(t) * d[1], -np.cos(t)], f) for t in TILTS]

    def reach(self, side, pts, fingers, near=None):
        """One orientation that reaches every point of pts; returns (R, [q per point])."""
        last = None
        for R in self.frames(side, pts[0], fingers):
            try:
                qs, q = [], near
                for p in pts:
                    q = self.r.solve(side, p, R, near=q)
                    qs.append(q)
                return R, qs
            except RuntimeError as e:
                last = e
        raise RuntimeError(f"{side}: cannot reach {pts[0]} ({last})")

    def pick(self, side, name, lift=0.10):
        r = self.r
        g, f, h = self.grasp(name)
        R, (q_pre, _) = self.reach(side, [g + [0, 0, 0.08], g], f)
        r.grip(side, 0.045, 1)
        r.joints({side: q_pre}, 50)
        r.settle(5)
        r.line(side, g, R, 35)
        r.settle(8)
        r.grip(side, -0.005, 22)
        try:
            r.line(side, g + [0, 0, lift], R, 30)
        except RuntimeError:
            _, (q,) = self.reach(side, [g + [0, 0, lift]], f)
            r.joints({side: q}, 30)
        return R, h

    def place(self, side, xy, bottom_z, h, fingers, settle=10):
        r = self.r
        tgt = np.r_[xy, bottom_z + h]
        R, (q_above, _) = self.reach(side, [tgt + [0, 0, 0.05], tgt], fingers)
        r.joints({side: q_above}, 55)
        r.settle(5)
        r.line(side, tgt, R, 20)
        r.settle(settle)
        r.grip(side, 0.045, 20)
        self.retreat(side, R, fingers)

    def retreat(self, side, R, fingers, dz=0.06):
        """Straight up by dz; if that leaves the workspace, to the same point with another tilt."""
        r = self.r
        p, _ = r.arm[side].fk(r.q(side))
        try:
            r.line(side, p + [0, 0, dz], R, 20)
        except RuntimeError:
            _, (q,) = self.reach(side, [p + [0, 0, dz]], fingers)
            r.joints({side: q}, 25)

    def home(self, side, n=70):
        self.r.joints({side: np.zeros(6)}, n)


def fruits_in_bowl(r: Runner):
    P = Planner(r)
    for name in ("banana", "lemon"):
        _, h = P.pick("left", name)
        bowl = r.s.state()["objects"]["bowl"]["pos"]
        f = P.grasp(name)[1]
        P.place("left", bowl[:2], 0.055 + 0.02, h, f)
    P.home("left")
    r.settle(60)


def pack_tote(r: Runner):
    P = Planner(r)
    tote = r.s.state()["objects"]["tote"]
    c = tote["pos"]
    rim = 0.105 + 0.025
    slots = {"left": [(-0.06, 0.075), (0.06, 0.075)], "right": [(-0.06, -0.075), (0.06, -0.075)]}  # world-frame offsets
    for side, names in (("left", ("tomato_soup_can", "foam_brick")), ("right", ("spam_can", "marker"))):
        for name, (dx, dy) in zip(names, slots[side]):
            _, h = P.pick(side, name, lift=0.12)
            f = P.grasp(name)[1]
            P.place(side, c[:2] + [dx, dy], rim, h, f)
        P.home(side)
    r.settle(60)


def main(inst_path: str, out: str) -> None:
    r = Runner(inst_path)
    {"fruits_in_bowl": fruits_in_bowl, "pack_tote": pack_tote}[r.s.family](r)
    A = r.s.record_stop()
    live = r.s.check()
    rep = r.s.replay(A)
    print(json.dumps({"live": live, "replay": rep, "steps": len(A)}, default=str))
    np.save(out, A)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
