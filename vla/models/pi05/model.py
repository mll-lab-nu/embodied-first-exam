"""pi0.5 through openpi's own policy (openpi 215abfb).

Entry point: ``openpi.policies.policy_config.create_trained_policy(train_config, checkpoint_dir)`` and
``Policy.infer(inputs, noise=...) -> {"actions": ...}``. Images are passed at native resolution; the policy
letterboxes them to 224 x 224 itself (ResizeImages).

DROID: train config pi05_droid_jointpos_polaris + checkpoint pi05_droid_jointpos (policies/droid_policy.py).
  in   observation/exterior_image_1_left, observation/wrist_image_left: HWC uint8 RGB;
       observation/joint_position (7,) rad; observation/gripper_position (1,) in [0, 1], 1 = closed; prompt.
  out  (15, 8): absolute joint positions in rad (the policy adds the state back to its deltas) and the gripper
       position, 1 = closed. The official clients execute 8 steps at 15 Hz and binarize the gripper at 0.5
       (examples/droid/main.py), as done here.
ALOHA: train config pi05_aloha + checkpoint pi05_base, trossen norm stats (policies/aloha_policy.py).
  in   images {cam_high, cam_left_wrist, cam_right_wrist}: CHW uint8; state (14,) = [left 6 joints (rad,
       standard ALOHA convention), left gripper, right 6 joints, right gripper], gripper = normalized finger
       position, 0 = closed, 1 = open; prompt.
  out  (50, 14): absolute joints in rad and the normalized gripper joint, 0 = closed, 1 = open. The official
       real-ALOHA client executes 25 steps at 50 Hz (examples/aloha_real/main.py).
Sampling noise (chunk_size x 32) comes from a NumPy generator seeded in reset().
"""
import os

os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.5")  # leave GPU memory to the simulator

import numpy as np
from openpi.policies import policy_config
from openpi.training import config as openpi_config

from vla.models.base import BaseVLA
from vla.protocol import ActionChunk

ACTION_DIM = 32  # model action width before the output transforms slice it


class Pi05(BaseVLA):
    def load(self):
        train_config = openpi_config.get_config(self.config["model"]["train_config"])
        self.policy = policy_config.create_trained_policy(train_config, self.config["checkpoint"])
        self.rng = np.random.default_rng(0)

    def reset(self, seed):
        self.rng = np.random.default_rng(seed)

    def infer(self, obs):
        joint = obs.state["joint"]
        if self.spec.embodiment == "panda_robotiq":
            exterior, wrist = self.spec.cameras
            inputs = {"observation/exterior_image_1_left": obs.images[exterior],
                      "observation/wrist_image_left": obs.images[wrist],
                      "observation/joint_position": joint[:7], "observation/gripper_position": 1.0 - joint[7:]}
        else:
            slots = ("cam_high", "cam_left_wrist", "cam_right_wrist")
            inputs = {"images": {slot: obs.images[camera].transpose(2, 0, 1)
                                 for slot, camera in zip(slots, self.spec.cameras)}, "state": joint}
        noise = self.rng.standard_normal((self.spec.chunk_size, ACTION_DIM)).astype(np.float32)
        actions = np.asarray(self.policy.infer({**inputs, "prompt": obs.instruction}, noise=noise)["actions"])
        if self.spec.embodiment == "panda_robotiq":
            actions = np.c_[actions[:, :7], actions[:, 7] <= 0.5]  # opening = not closed
        return ActionChunk(actions.astype(np.float32))
