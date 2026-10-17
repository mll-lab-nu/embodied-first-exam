"""A stand-in for rcb_myosuite.py (copied next to the service by test_standard_server.py): what the standard service
calls, on stub_mujoco's toy model. Control at 50 Hz; images are small (the tests count frames, they do not look at
them). The episode succeeds at a row whose first command is above 50 (a stand-in for the task's rule, window included);
the frozen instance's recorded hash is the start's, unless RCB_STUB_START_MISMATCH is set (an image that no longer
builds the frozen start)."""
import hashlib
import json
import os
import types

import numpy as np

import mujoco

SESSION_LOG = ""
BODY = {"obj_hold": "hand"}
IMAGE = (6, 8)                                     # every rendered frame, whatever size is asked for


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
    def __init__(self, task, instance=None):
        self.task, self.env_id = task, "stub-v0"
        self.nu = int(np.load(instance, allow_pickle=False)["model__actuator_ctrlrange"].shape[0])
        self.model = mujoco.Model(self.nu)
        self.data = mujoco.Data(self.model)
        self.dt, self.rule, self.hold_steps, self.track_steps = 0.02, "hold", 5, None
        self.base = types.SimpleNamespace(frame_skip=10, robot=types.SimpleNamespace(mj_data=self.data))
        self._renderer = _Renderer()
        self.reset()
        self.instance_sha = "0" * 16 if os.environ.get("RCB_STUB_START_MISMATCH") else self.state_sha()
        self.instance_exact = self.instance_sha == self.state_sha()

    def reset(self):
        self.data.qpos[:] = 0
        mujoco.mj_kinematics(self.model, self.data)
        self.steps, self.done, self.success, self.reason = 0, False, False, None

    def step(self, action) -> bool:
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        self.data.qpos[:5] = np.clip(self.data.qpos[:5] + 0.01 * np.clip(a[:5], -100, 100), -1.5, 1.5)
        self.data.qpos[5] += 0.001                 # the ball moves
        mujoco.mj_kinematics(self.model, self.data)
        self.steps += 1
        if a[0] > 50:
            self.done, self.success, self.reason = True, True, "success"
        return not self.done

    def rest_action(self):
        return np.zeros(self.nu)

    def cameras(self):
        return list(self.model.cams)

    def actuators(self):
        return [{"index": i, "name": f"m{i}", "kind": "muscle", "command": "excitation"} for i in range(self.nu)]

    def joints(self):
        m = self.model
        return [{"index": j, "name": m.joints[j], "qpos_adr": j, "dof_adr": j, "range": m.jnt_range[j].tolist(),
                 "qpos": float(self.data.qpos[j])} for j in range(m.njnt)]

    def render_frame(self, camera=None, size=None):
        return np.zeros(IMAGE + (3,), np.uint8)

    def state_sha(self) -> str:
        return hashlib.sha1(self.data.qpos.tobytes() + bytes([int(self.done)])).hexdigest()[:16]

    def save_trajectory(self, actions, path, meta=None):
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), task=self.task, meta=json.dumps(meta or {}))


if __name__ == "__main__":   # `rcb_myosuite.py replay ...`: a grading replay; the standard collect hook must run none
    open(os.path.join(os.environ.get("RCB_DATA", "."), "REPLAYED"), "a").write(" ".join(os.sys.argv[1:]) + "\n")
