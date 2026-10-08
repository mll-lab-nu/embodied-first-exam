"""Reference solutions for the sim_to_real YAM tasks (solution/ only; never in the agent's image).

A scripted controller on the privileged tooling: damped-least-squares IK on each arm's `grasp_site` (position and full
orientation, the arm has 6 joints), Cartesian waypoints interpolated in joint space, the rate limit applied by
`Session.step`. Writes the applied targets of one successful run.

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


def finger_axis(yaw, ref=np.pi / 2):
    """A horizontal axis normal to a box face with this yaw, the one closest to ref."""
    c = [yaw + k * np.pi / 2 for k in range(-4, 5)]
    t = min(c, key=lambda a: abs(np.angle(np.exp(1j * (a - ref)))))
    return np.array([np.cos(t), np.sin(t), 0.0])


def yaw_of(quat_wxyz):
    w, x, y, z = quat_wxyz
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


TRANSIT_Z = 0.10


def cube_stack_three(r: Runner):
    """Left arm: green onto blue, then red onto green; top-down grasps."""
    side = "left"
    r.grip(side, 0.032, 1)
    for name, below in (("cube_green", "cube_blue"), ("cube_red", "cube_green")):
        o = r.s.state()["objects"][name]
        p, R = o["pos"], frame(DOWN, finger_axis(yaw_of(o["quat_wxyz"])))
        r.joints({side: r.solve(side, np.r_[p[:2], TRANSIT_Z], R)}, 60)
        r.line(side, np.r_[p[:2], p[2] + 0.001], R, 40)
        r.settle(10)
        r.grip(side, -0.005, 25)
        r.line(side, np.r_[p[:2], TRANSIT_Z + 0.04], R, 30)
        u = r.s.state()["objects"][below]
        Ru = frame(DOWN, finger_axis(yaw_of(u["quat_wxyz"])))
        top = u["pos"][2] + 2 * ry.CUBE_HALF + 0.001  # the grasp site sits 1 mm above the held cube's centre
        r.joints({side: r.solve(side, np.r_[u["pos"][:2], TRANSIT_Z + 0.04], Ru)}, 50)
        r.settle(10)
        r.line(side, np.r_[u["pos"][:2], top + 0.004], Ru, 40)
        r.settle(15)
        r.grip(side, 0.032, 20)
        r.line(side, np.r_[u["pos"][:2], TRANSIT_Z + 0.04], Ru, 30)
    r.joints({side: np.zeros(6)}, 80)
    r.grip(side, ry.HOME_GRIPPER, 1)
    r.settle(40)


def handover_to_bin(r: Runner):
    """Left: top-down grasp near the block's top, carry it to the handover point between the arms. Right: waits beside
    that point, grasps the block lower down from behind (approach +x), left lets go and slides out, right carries the
    block over the bin and lets go above it. Both grippers close along y at the handover, which keeps the left wrist
    camera clear of the right gripper (the arms must never touch)."""
    st = r.s.state()
    bp, byaw = st["objects"]["block"]["pos"], yaw_of(st["objects"]["block"]["quat_wxyz"])
    binp = st["bin"]["pos"]
    hz = ry.BLOCK_HALF[2]
    H = np.array([0.28, -0.305, 0.115])  # block centre at the handover
    Rl = frame(DOWN, finger_axis(byaw))
    Rl_h = frame(DOWN, [0, 1, 0])
    Rr = frame([1, 0, 0], [0, 1, 0])
    g = np.r_[H[:2], H[2] - 0.01]
    r.grip("left", 0.035, 1)
    r.grip("right", 0.035, 1)
    r.joints(
        {
            "left": r.solve("left", np.r_[bp[:2], bp[2] + hz + 0.06], Rl),
            "right": r.solve("right", g - [0.08, 0, 0], Rr),
        },
        70,
    )
    r.line("left", np.r_[bp[:2], bp[2] + 0.035], Rl, 40)
    r.settle(10)
    r.grip("left", -0.005, 25)
    r.line("left", np.r_[bp[:2], bp[2] + 0.035 + 0.08], Rl, 30)
    r.joints({"left": r.solve("left", H + [0, 0, 0.035], Rl_h)}, 70)
    r.settle(20)
    blk = r.s.state()["objects"]["block"]["pos"]
    g = np.r_[blk[:2], blk[2] - 0.01]
    r.line("right", g - [0.08, 0, 0], Rr, 20)
    r.line("right", g, Rr, 40)
    r.settle(10)
    r.grip("right", -0.005, 25)
    r.grip("left", 0.035, 20)
    pl, _ = r.arm["left"].fk(r.q("left"))
    r.line("left", pl + [0, 0.08, 0.01], Rl_h, 25)
    r.joints({"left": np.zeros(6)}, 80)
    pr, _ = r.arm["right"].fk(r.q("right"))
    r.line("right", pr + [0, 0, 0.04], Rr, 20)
    drop = np.r_[binp[:2], 0.145]  # block bottom ~4 cm above the rim
    r.joints({"right": r.solve("right", drop + [0, 0, 0.02], Rr)}, 90)
    r.line("right", drop, Rr, 20)
    r.settle(15)
    r.grip("right", 0.04, 25)
    r.line("right", drop + [-0.06, 0, 0.04], Rr, 25)
    r.joints({"right": np.zeros(6)}, 80)
    r.settle(60)


def main(inst_path: str, out: str) -> None:
    r = Runner(inst_path)
    {"cube_stack_three": cube_stack_three, "handover_to_bin": handover_to_bin}[r.s.family](r)
    A = r.s.record_stop()
    live = r.s.check()
    rep = r.s.replay(A)
    print(json.dumps({"live": live, "replay": {k: v for k, v in rep.items()}, "steps": len(A)}, default=str))
    np.save(out, A)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
