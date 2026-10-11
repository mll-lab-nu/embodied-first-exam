"""A stand-in for rcb_dexjoco.py (copied next to the service by test_standard_server.py): what the standard service
calls, on stub_mujoco's toy model. The object `link_19` drifts 1 mm in x per control step, so its pose is a function of
the episode; images are small (the tests count frames, they do not look at them)."""
import hashlib
import json

import numpy as np

import mujoco

SESSION_LOG = ""
IMAGE = (6, 8)                                     # every rendered frame, whatever size is asked for


def blas_threads() -> dict:
    return {"visible_cpus": 8, "openblas_num_threads_env": 4, "blas_threads": 4, "threads_ok": 1}


def threads_message(t: dict) -> str:
    return "stub"


def quat_slerp(a, b, t: float) -> np.ndarray:
    q = np.asarray(a, float) + t * (np.asarray(b, float) - np.asarray(a, float))
    return q / np.linalg.norm(q)


class _Renderer:
    def __init__(self):
        self.depth = False

    def enable_depth_rendering(self):
        self.depth = True

    def disable_depth_rendering(self):
        self.depth = False

    def update_scene(self, data, camera=None):
        pass

    def render(self):
        return np.full(IMAGE, 1.25, np.float32) if self.depth else np.zeros(IMAGE + (3,), np.uint8)


class Session:
    def __init__(self, task, instance=None, image_size=(480, 640)):
        self.task, self.bimanual, self.action_dim = task, True, 46
        self.model = mujoco.Model()
        self.data = mujoco.Data(self.model)
        self._renderer = _Renderer()
        self.steps, self.done, self.success, self.reason = 0, False, False, None
        self.instance_sha, self.instance_exact = "stub", True

    def arms(self):
        return mujoco.ARMS

    def cameras(self):
        return list(self.model.cams)

    def default_camera(self):
        return "front"

    def _hand_ctrl_ids(self, arm):
        return np.asarray(self.model.hand_act[arm])

    def hand_limits(self, arm="right"):
        return self.model.actuator_ctrlrange[self._hand_ctrl_ids(arm)].copy()

    def _arm_target(self, arm):
        i = mujoco.ARMS.index(arm)
        return np.concatenate([self.data.mocap_pos[i], self.data.mocap_quat[i], self.data.ctrl[self._hand_ctrl_ids(arm)]])

    def hold_action(self):
        return np.concatenate([self._arm_target(a) for a in self.arms()])

    def step(self, action) -> bool:
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        for k, arm in enumerate(self.arms()):
            self.data.mocap_pos[k], self.data.mocap_quat[k] = a[23 * k: 23 * k + 3], a[23 * k + 3: 23 * k + 7]
            self.data.ctrl[self._hand_ctrl_ids(arm)] = a[23 * k + 7: 23 * k + 23]
        self.data.qpos[-7] += 0.001                # the object moves
        mujoco.mj_kinematics(self.model, self.data)
        self.steps += 1
        return True

    def render_frame(self, camera=None, size=None):
        return np.zeros(IMAGE + (3,), np.uint8)

    def state_sha(self) -> str:
        return hashlib.sha1(self.data.qpos.tobytes() + self.data.mocap_pos.tobytes() + self.data.ctrl.tobytes()).hexdigest()[:16]

    def save_trajectory(self, actions, path, meta=None, *, max_rows=None):
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=self.task, meta=json.dumps(meta or {}))
