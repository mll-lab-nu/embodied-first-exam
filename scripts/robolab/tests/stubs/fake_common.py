"""A numpy stand-in for an Isaac tooling Session: joints jump to their targets, the tool frame goes where ik_step was
asked to go. Enough for environment/sim/server.py to run unmodified on the CPU."""
import hashlib, json, os
import numpy as np
MAX_STEPS = int(os.environ.get("FAKE_MAX_STEPS", "100000"))


def cam_info(cams):
    return {c: {"intrinsic_cv": np.eye(3).tolist(), "extrinsic_cv": np.eye(4)[:3].tolist(), "cam2world_gl": np.eye(4).tolist(),
                "image_size": [32, 24], "mount": {"type": "static"}, "depth_range_m": [0.01, 10.0]} for c in cams}


class Base:
    DIM = 0
    def _init(self):
        self.n_steps = 0; self.episode_done = False; self._targets = np.zeros(self.DIM); self._rec = None
        self.kinematics_check = {"ok": True}; self.seed = 0; self.assets = {}; self.spec = {"text": "do the task"}
    def step(self, a):
        a = np.asarray(a, dtype=np.float32).reshape(-1); assert a.size == self.DIM and np.all(np.isfinite(a))
        if self.episode_done: raise RuntimeError("episode is over")
        if self._rec is not None: self._rec.append(a.copy())
        self._targets = a.astype(np.float64); self.n_steps += 1
        if self.n_steps >= MAX_STEPS: self.episode_done = True
        return self.episode_done
    def hold_action(self): return self._targets.copy()
    def state_sha(self): return hashlib.sha1(self._targets.tobytes() + str(self.n_steps).encode()).hexdigest()
    def record_start(self): self._rec = []
    def record_stop(self):
        r = np.stack(self._rec) if self._rec else np.zeros((0, self.DIM), np.float32); self._rec = None; return r
    def save_trajectory(self, acts, path, meta=None): np.savez(path, actions=acts, task="fake", meta=json.dumps(meta or {}))
    def camera_info(self, cams): return cam_info(cams)
    def render_depth(self, c): return np.ones((24, 32), np.float32)
    def robot_spec(self): return {"controller": {}}
    def kinematics(self, req): return {"ok": True}
