"""Scripted oracle for AlohaHandOver (privileged: reads the box pose and the target from the simulator).
Left arm: top-down grasp of the box's upper half, lift to Playground's handover point (0, 0, 0.24). Right arm: horizontal
grasp of the box's lower half, approaching along -x. Then the left gripper opens and backs off, and the right arm
carries the box to the target (servoed on the box's actual position). DLS IK with gravity feedforward, as in the peg
oracle. Writes the recorded (T, 14) targets."""
import json, os, sys
import numpy as np, mujoco
import rcb_aloha as ra

DEBUG = os.environ.get("ORACLE_DEBUG") == "1"
ARM = ("waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate")
OPEN, CLOSED = 0.037, 0.002


class Arm:
    def __init__(self, s, side):
        m = s.model; self.s = s
        self.j = [m.joint(f"{side}/{n}").id for n in ARM]; self.qa = np.array([m.jnt_qposadr[j] for j in self.j]); self.va = np.array([m.jnt_dofadr[j] for j in self.j])
        self.lo = m.jnt_range[self.j, 0]; self.hi = m.jnt_range[self.j, 1]; self.site = m.site(f"{side}/gripper").id
        self.ai = 0 if side == "left" else 7; self.scratch = mujoco.MjData(m); self.q = s.data.qpos[self.qa].copy()

    def ik(self, pos, R, iters=100, w_rot=0.5):
        m, d = self.s.model, self.scratch; d.qpos[:] = self.s.data.qpos; q = self.q.copy()
        jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv)); ep = np.zeros(3)
        for _ in range(iters):
            d.qpos[self.qa] = q; mujoco.mj_kinematics(m, d); mujoco.mj_comPos(m, d)
            x = d.site_xpos[self.site]; Rc = d.site_xmat[self.site].reshape(3, 3)
            ep = pos - x; er = 0.5 * sum(np.cross(Rc[:, i], R[:, i]) for i in range(3))
            if np.linalg.norm(ep) < 2e-4 and np.linalg.norm(er) < 2e-3: break
            mujoco.mj_jacSite(m, d, jp, jr, self.site); J = np.vstack([jp[:, self.va], w_rot * jr[:, self.va]])
            q = np.clip(q + J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), np.concatenate([ep, w_rot * er])), self.lo, self.hi)
        self.q = q; return float(np.linalg.norm(ep))

    def cmd(self):
        m, d = self.s.model, self.scratch; d.qpos[:] = self.s.data.qpos; d.qpos[self.qa] = self.q; d.qvel[:] = 0.0
        mujoco.mj_forward(m, d); return self.q + d.qfrc_bias[self.va] / m.actuator_gainprm[self.ai:self.ai + 6, 0]


def main(inst_path, out):
    s = ra.Session(inst_path); s.record_start(); L, R = Arm(s, "left"), Arm(s, "right")
    down_l = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)             # left: site x = (0,0,-1) (down), y = +world y
    horiz_r = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, 1]], float)          # right: site x = -world x (towards the box), y = -world y
    tg = s.targets.copy(); grip = {"l": OPEN, "r": OPEN}
    home = {"l": s.state()["sites"]["left/gripper"].copy(), "r": s.state()["sites"]["right/gripper"].copy()}

    def move(pl, pr, n, gl=None, gr=None):
        st = s.state(); p0l, p0r = st["sites"]["left/gripper"].copy(), st["sites"]["right/gripper"].copy()
        if gl is not None: grip["l"] = gl
        if gr is not None: grip["r"] = gr
        for k in range(1, n + 1):
            a = k / n; a = a * a * (3 - 2 * a)
            if pl is not None: L.ik(p0l + a * (np.asarray(pl) - p0l), down_l)
            if pr is not None: R.ik(p0r + a * (np.asarray(pr) - p0r), horiz_r)
            tg[0:6] = L.cmd(); tg[7:13] = R.cmd(); tg[6] = grip["l"]; tg[13] = grip["r"]; s.step(tg)
        if DEBUG:
            st = s.state(); print(f"t={s.steps * ra.CONTROL_DT:5.2f} box {np.round(st['box_pos'], 3)} {st['success']} right_holds={st['right_holds']} left_touches={st['left_touches']} d={st['box_to_target_m']}", flush=True)

    box = s.state()["box_pos"].copy()
    top = box + np.array([0.0, 0.0, 0.012])                                   # left grasps the upper half
    move(top + [0, 0, 0.10], None, 60, gl=OPEN)
    move(top, None, 40)
    move(top, None, 40, gl=CLOSED)
    hand = np.array([0.0, 0.0, 0.24]); off_l = s.state()["sites"]["left/gripper"] - s.state()["box_pos"]
    move(hand + off_l, None, 70)
    box = s.state()["box_pos"].copy(); low = box + np.array([0.0, 0.0, -0.016])  # right grasps the lower half, from +x
    move(None, low + [0.10, 0, 0], 60, gr=OPEN)
    move(None, low + [0.004, 0, 0], 50)
    move(None, None, 40, gr=CLOSED)
    move(s.state()["sites"]["left/gripper"], None, 30, gl=OPEN)               # left lets go ...
    move(s.state()["sites"]["left/gripper"] + [-0.10, 0, 0.06], None, 50)     # ... and backs off
    tgt = s.target_pos
    for _ in range(3):                                                        # carry, then correct on the box's actual position
        st = s.state(); err = tgt - st["box_pos"]
        move(None, st["sites"]["right/gripper"] + err, 60)
    move(None, None, 30)
    A = s.record_stop(); np.save(out, A); live = s.check(); rp = s.replay(A)
    print(json.dumps({"live": live, "replay": rp, "n": len(A)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
