"""pi0.5 through openpi's own policy (openpi 215abfb).

Entry point: ``openpi.policies.policy_config.create_trained_policy(train_config, checkpoint_dir)`` and
``Policy.infer(inputs, noise=...) -> {"actions": ...}``. Images are passed as ``camera_images`` gives them (ALOHA
frames center-cropped to 4:3); the policy letterboxes them to 224 x 224 itself (ResizeImages).

DROID: train config pi05_droid_jointpos_polaris + checkpoint pi05_droid_jointpos (policies/droid_policy.py).
  in   observation/exterior_image_1_left, observation/wrist_image_left: HWC uint8 RGB;
       observation/joint_position (7,) rad in the DROID convention (droid.py); observation/gripper_position (1,)
       in [0, 1], 1 = closed; prompt.
  out  (15, 8): absolute joint positions in rad (the policy adds the state back to its deltas) and the gripper
       position, 1 = closed. The official clients execute 8 steps at 15 Hz and binarize the gripper at 0.5
       (examples/droid/main.py), as done here.
ALOHA: train config pi05_aloha + checkpoint pi05_base, trossen norm stats (policies/aloha_policy.py).
  in   images {cam_high, cam_left_wrist, cam_right_wrist}: CHW uint8; state (14,) = [left 6 joints (rad,
       standard ALOHA convention), left gripper, right 6 joints, right gripper], gripper = ALOHA normalized
       finger position, encoded so that TopoGym's closed and open fingers read as pi's closed and open (gripper.py);
       prompt.
  out  (50, 14): absolute joints in rad and the ALOHA normalized gripper joint, decoded to TopoGym's opening
       through the same linkage (gripper.py). The official real-ALOHA client executes 25 steps at 50 Hz
       (examples/aloha_real/main.py).
Sampling noise (chunk_size x 32) comes from a NumPy generator seeded in reset().
"""
import os

os.environ.setdefault("XLA_PYTHON_CLIENT_MEM_FRACTION", "0.5")  # leave GPU memory to the simulator

import numpy as np
from openpi.policies import policy_config
from openpi.training import config as openpi_config

from vla.models.base import BaseVLA
from vla.models.droid import from_droid_joints, to_droid_joints
from vla.models.pi05.gripper import from_openpi_gripper, to_openpi_gripper
from vla.protocol import ActionChunk

ACTION_DIM = 32  # model action width before the output transforms slice it
ALOHA_GRIPPERS = [6, 13]  # [left 6 joints, left gripper, right 6 joints, right gripper]


class Pi05(BaseVLA):
    def load(self):
        train_config = openpi_config.get_config(self.config["model"]["train_config"])
        self.policy = policy_config.create_trained_policy(train_config, self.config["checkpoint"])
        self.rng = np.random.default_rng(0)

    def reset(self, seed):
        self.rng = np.random.default_rng(seed)

    def infer(self, obs):
        joint, images = obs.state["joint"], self.camera_images(obs)
        if self.spec.embodiment == "panda_robotiq":
            exterior, wrist = images
            inputs = {"observation/exterior_image_1_left": exterior, "observation/wrist_image_left": wrist,
                      "observation/joint_position": to_droid_joints(joint),
                      "observation/gripper_position": 1.0 - joint[7:]}
        else:
            slots = ("cam_high", "cam_left_wrist", "cam_right_wrist")
            state = np.array(joint)
            state[ALOHA_GRIPPERS] = to_openpi_gripper(joint[ALOHA_GRIPPERS])
            inputs = {"images": {slot: image.transpose(2, 0, 1) for slot, image in zip(slots, images)},
                      "state": state}
        noise = self.rng.standard_normal((self.spec.chunk_size, ACTION_DIM)).astype(np.float32)
        actions = np.array(self.policy.infer({**inputs, "prompt": obs.instruction}, noise=noise)["actions"])
        if self.spec.embodiment == "panda_robotiq":
            actions = np.c_[from_droid_joints(actions[:, :7]), actions[:, 7] <= 0.5]  # opening = not closed
        else:
            actions[:, ALOHA_GRIPPERS] = from_openpi_gripper(actions[:, ALOHA_GRIPPERS])
        return ActionChunk(actions.astype(np.float32))
