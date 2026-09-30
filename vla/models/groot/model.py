"""GR00T N1.7 DROID checkpoint through Isaac-GR00T's own policy (Isaac-GR00T 51d4c89).

Entry point: ``Gr00tPolicy(embodiment_tag, model_path, device=...)`` and
``policy.get_action(observation) -> (action, info)`` (gr00t/policy/gr00t_policy.py).
  video     exterior_image_1_left, wrist_image_left: (1, 1, H, W, 3) uint8 RGB. The DROID checkpoint uses the
            current frame only (processor_config video delta_indices [0]). Frames are resized to the DROID
            training size first, as the validated RoboLab sim client does (cv2 INTER_AREA).
  state     joint_position (1, 1, 7) rad; gripper_position (1, 1, 1) closure in [0, 1], 1 = closed;
            eef_9d (1, 1, 9) from the repo's compute_eef_9d of the Franka flange pose (franka.py).
  language  annotation.language.language_instruction: [[text]], lowercased without punctuation inside.
  action    joint_position (1, 40, 7) absolute rad (the processor adds the input state back to its deltas);
            gripper_position (1, 40, 1) closure; both official clients binarize it at 0.5, as done here.
The RoboLab sim run executes 8 of 40 steps at 15 Hz. The backbone nvidia/Cosmos-Reason2-2B is a gated
Hugging Face repository. Sampling noise uses the global torch RNG, seeded in reset().
"""
import cv2
from gr00t.data.state_action.droid_frame import compute_eef_9d
from gr00t.policy import Gr00tPolicy
from huggingface_hub import snapshot_download
import numpy as np
import torch

from vla.models.base import BaseVLA
from vla.models.groot.franka import droid_cartesian
from vla.protocol import ActionChunk


class Groot(BaseVLA):
    def load(self):
        options = self.config["model"]
        path = snapshot_download(self.config["checkpoint"], revision=options["revision"])
        self.policy = Gr00tPolicy(embodiment_tag=options["embodiment_tag"], model_path=path, device="cuda:0")
        self.height, self.width = options["image_hw"]

    def reset(self, seed):
        torch.manual_seed(seed)

    def infer(self, obs):
        joint = obs.state["joint"]
        video = {key: cv2.resize(obs.images[camera], (self.width, self.height), interpolation=cv2.INTER_AREA)[None, None]
                 for key, camera in zip(("exterior_image_1_left", "wrist_image_left"), self.spec.cameras)}
        state = {"eef_9d": compute_eef_9d(droid_cartesian(joint[:7])).astype(np.float32)[None, None],
                 "gripper_position": np.float32([[[1.0 - joint[7]]]]), "joint_position": joint[None, None, :7]}
        language = {"annotation.language.language_instruction": [[obs.instruction]]}
        action, _ = self.policy.get_action({"video": video, "state": state, "language": language})
        closed = action["gripper_position"][0, :, 0] > 0.5
        return ActionChunk(np.c_[action["joint_position"][0], ~closed].astype(np.float32))
