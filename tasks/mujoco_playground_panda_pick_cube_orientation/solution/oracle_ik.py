"""Scripted oracle for MuJoCo Playground's Panda tasks (privileged: reads object and target poses from the simulator).
7-DoF damped-least-squares IK on the `gripper` site with a posture term, gravity feedforward on the position targets.
PandaPickCubeOrientation: top-down grasp, lift, then move the gripper so that the box (held with the grasp's relative
pose) reaches the target position and orientation, with a final correction on the box's actual pose.
PandaOpenCabinet: approach the handle horizontally from the robot's side, close on it, pull it along its slide to the
target x (servoed on the handle's actual x). Writes the recorded (T, 8) targets."""
import json, os, sys
import numpy as np, mujoco
import rcb_panda as rp

DEBUG = os.environ.get("ORACLE_DEBUG") == "1"
OPEN, CLOSED = 0.04, 0.0


def quat_to_mat(q):
    m = np.zeros(9); mujoco.mju_quat2Mat(m, np.asarray(q, float)); return m.reshape(3, 3)


class Arm:
    def __init__(self, s):
        m = s.model; self.s = s
        self.j = [m.joint(f"joint{i}").id for i in range(1, 8)]; self.qa = np.array([m.jnt_qposadr[j] for j in self.j]); self.va = np.array([m.jnt_dofadr[j] for j in self.j])
        self.lo = m.jnt_range[self.j, 0]; self.hi = m.jnt_range[self.j, 1]; self.site = m.site("gripper").id
        self.scratch = mujoco.MjData(m); self.q = s.data.qpos[self.qa].copy(); self.q_rest = self.q.copy()

    def ik(self, pos, R, iters=120, w_rot=0.6, w_post=0.02):
        m, d = self.s.model, self.scratch; d.qpos[:] = self.s.data.qpos; q = self.q.copy()
        jp = np.zeros((3, m.nv)); jr = np.zeros((3, m.nv)); ep = np.zeros(3)
        for _ in range(iters):
            d.qpos[self.qa] = q; mujoco.mj_kinematics(m, d); mujoco.mj_comPos(m, d)
            x = d.site_xpos[self.site]; Rc = d.site_xmat[self.site].reshape(3, 3)
            ep = pos - x; er = 0.5 * sum(np.cross(Rc[:, i], R[:, i]) for i in range(3))
            if np.linalg.norm(ep) < 2e-4 and np.linalg.norm(er) < 2e-3: break
            mujoco.mj_jacSite(m, d, jp, jr, self.site); J = np.vstack([jp[:, self.va], w_rot * jr[:, self.va]])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), np.concatenate([ep, w_rot * er]))
            N = np.eye(7) - np.linalg.pinv(J) @ J; dq += N @ (w_post * (self.q_rest - q))
            q = np.clip(q + dq, self.lo, self.hi)
        self.q = q; return float(np.linalg.norm(ep))

    def cmd(self):
        m, d = self.s.model, self.scratch; d.qpos[:] = self.s.data.qpos; d.qpos[self.qa] = self.q; d.qvel[:] = 0.0
        mujoco.mj_forward(m, d); return self.q + d.qfrc_bias[self.va] / m.actuator_gainprm[:7, 0]


def main(inst_path, out):
    s = rp.Session(inst_path); s.record_start(); arm = Arm(s); tg = s.targets.copy(); g = {"v": OPEN}

    def move(pos, R, n, grip=None, settle=0):
        if grip is not None: g["v"] = grip
        p0 = s.state()["gripper_pos"].copy(); R0 = s.state()["gripper_mat"].copy()
        for k in range(1, n + settle + 1):
            a = min(1.0, k / n); a = a * a * (3 - 2 * a)
            Ri = R if a >= 1 else _slerp_mat(R0, R, a)
            arm.ik(p0 + a * (np.asarray(pos) - p0), Ri); tg[:7] = arm.cmd(); tg[7] = g["v"]; s.step(tg)
        if DEBUG: st = s.state(); print(f"t={s.steps * rp.CONTROL_DT:5.2f} grip {st['gripper_pos'].round(3)} obj {st['object_pos'].round(3)} {s.check()}", flush=True)

    if s.env == "PandaPickCubeOrientation":
        down = s.state()["gripper_mat"].copy(); down[:, 2] = [0, 0, -1]; down = _orthonormal(down)
        box = s.state()["object_pos"].copy(); grasp = box + np.array([0.0, 0.0, 0.0])
        move(grasp + [0, 0, 0.12], down, 60, grip=OPEN); move(grasp, down, 40); move(grasp, down, 1, grip=CLOSED, settle=35)
        st = s.state(); Rb = quat_to_mat(st["object_quat_wxyz"]); Rg = st["gripper_mat"]
        rel_R = Rb.T @ Rg; rel_p = Rb.T @ (st["gripper_pos"] - st["object_pos"])       # gripper pose in the box frame
        move(st["gripper_pos"] + [0, 0, 0.15], Rg, 50)
        Rt = quat_to_mat(s.target_quat); want = s.target_pos
        for _ in range(3):
            st = s.state(); Rb = quat_to_mat(st["object_quat_wxyz"]); Rg = st["gripper_mat"]
            rel_R = Rb.T @ Rg; rel_p = Rb.T @ (st["gripper_pos"] - st["object_pos"])
            move(want + Rt @ rel_p, Rt @ rel_R, 70)
        move(s.state()["gripper_pos"], s.state()["gripper_mat"], 1, settle=30)
    else:
        h = s.state()["object_pos"].copy()
        # first to Playground's `home` arm posture (joint space), which also becomes the IK's rest posture
        q_home = np.array([0, 0.3, 0, -1.57079, 0, 2.0, -0.7853]); q0 = arm.q.copy(); arm.q_rest = q_home
        for k in range(1, 61):
            a = k / 60; a = a * a * (3 - 2 * a); arm.q = q0 + a * (q_home - q0); tg[:7] = arm.cmd(); tg[7] = OPEN; s.step(tg)
        # approach along +x (site z), fingers closing across the bar's 2 cm height (site y = world z)
        R_h = np.column_stack([[0, 1, 0], [0, 0, 1], [1, 0, 0]]).astype(float)
        move(h + [-0.12, 0, 0], R_h, 80, grip=OPEN); move(h + [0.0, 0, 0], R_h, 50); move(h + [0.0, 0, 0], R_h, 1, grip=CLOSED, settle=35)
        st = s.state(); off = st["gripper_pos"][0] - st["object_pos"][0]
        want = np.array([s.target_pos[0] + off, h[1], h[2]])
        move(want, R_h, 120)
        for _ in range(2):
            st = s.state(); want = want + np.array([s.target_pos[0] - st["object_pos"][0], 0, 0]); move(want, R_h, 40)
        move(s.state()["gripper_pos"], R_h, 1, settle=30)
    A = s.record_stop(); np.save(out, A); live = s.check(); rp_ = s.replay(A)
    print(json.dumps({"live": live, "replay": rp_, "n": len(A)}))


def _orthonormal(R):
    z = R[:, 2] / np.linalg.norm(R[:, 2]); x = R[:, 0] - np.dot(R[:, 0], z) * z; x /= np.linalg.norm(x); return np.column_stack([x, np.cross(z, x), z])


def _slerp_mat(R0, R1, a):
    q0 = np.zeros(4); q1 = np.zeros(4); mujoco.mju_mat2Quat(q0, R0.reshape(-1)); mujoco.mju_mat2Quat(q1, R1.reshape(-1))
    if np.dot(q0, q1) < 0: q1 = -q1
    q = (1 - a) * q0 + a * q1; q /= np.linalg.norm(q); return quat_to_mat(q)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
