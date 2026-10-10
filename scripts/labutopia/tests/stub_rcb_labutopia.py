"""Stand-in for rcb_labutopia (no Isaac Sim): just enough of Session for shared/standard/server.py to start and step."""
import hashlib, json, os
import numpy as np
W = H = 32
N_DOF, N_ACT, CONTROL_HZ, CONTROL_DT, MAX_STEPS = 9, 18, 60, 1.0 / 60, 36_000
ARM_JOINTS = [f"panda_joint{k}" for k in range(1, 8)]
SESSION_LOG = ""
NAMES = ARM_JOINTS + ["panda_finger_joint1", "panda_finger_joint2"]


class Session:
    def __init__(self, family=None, instance=None, cameras=False):
        self.family = json.load(open(instance))["family"]
        self.dt, self.steps, self.done, self.success, self.reason = CONTROL_DT, 0, False, False, None
        self.rule_name, self.instance_ok, self.start_exact, self.build_s = "stub", True, True, 0.1
        self.cmd = np.zeros(N_ACT); self.q = np.zeros(N_DOF)
        self.succeed_at = int(os.environ.get("STUB_SUCCESS_AT", "1000000000"))
    def cameras(self): return ["camera_1", "wrist_cam"]
    def default_cameras(self): return ["camera_1"]
    def render_frame(self, c, size=(H, W)): return np.zeros((size[0], size[1], 3), dtype=np.uint8)
    def render_depth(self, c, size=(H, W)): return np.ones(size, dtype=np.float32)
    def robot_spec(self):
        return {"name": "stub arm", "base": {"type": "fixed"},
                "joints": [{"name": n, "unit": "rad" if k < 7 else "m", "position_limits": [-3.0, 3.0]} for k, n in enumerate(NAMES)]}
    def action_limits(self): return np.stack([np.full(N_ACT, -10.0), np.full(N_ACT, 10.0)], axis=1)
    def camera_info(self, c, size=(H, W)):
        return {"intrinsic_cv": np.eye(3).tolist(), "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist(), "image_size": [W, H]}
    def camera_range(self, c): return [0.01, 10.0]
    def camera_mount(self, c):
        return {"type": "static"} if c != "wrist_cam" else {"type": "link", "parent_link": "panda_hand", "link_T_cam_cv": np.eye(4).tolist()}
    def fk(self, q, links): return {n: [0, 0, 0, 1, 0, 0, 0] for n in links}
    def ik(self, targets, **kw): return {"q": [0.0] * 7, "ok": True, "error": {}}
    def joint_positions(self): return self.q.copy()
    def joint_velocities(self): return np.zeros(N_DOF)
    def gripper_opening(self): return 0.08
    def tcp_pose(self): return np.array([0, 0, 0, 1, 0, 0, 0], dtype=np.float64)
    def joint_efforts(self): return np.zeros(N_DOF)
    def command(self): return self.cmd.copy()
    def _row(self, q, qd=None):
        a = np.asarray(q, dtype=np.float64).reshape(-1)
        return a if a.shape[0] == N_ACT else np.concatenate([a, np.zeros(N_DOF) if qd is None else np.asarray(qd, dtype=np.float64)])
    def step(self, q, qd=None, n=1):
        a = self._row(q, qd)
        if self.done: return False
        self.cmd, self.q = a.copy(), a[:N_DOF].copy(); self.steps += 1
        if self.steps >= self.succeed_at: self.done, self.success, self.reason = True, True, "success"
        return not self.done
    def state_sha(self): return hashlib.sha256(self.q.tobytes() + str(self.steps).encode()).hexdigest()[:16]
    def save_trajectory(self, A, path, meta=None): np.savez_compressed(path, actions=np.asarray(A), task=self.family, meta=json.dumps(meta or {}))
    def close(self): pass
