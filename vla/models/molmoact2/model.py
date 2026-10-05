"""MolmoAct2-DROID through its Hugging Face remote code (molmoact2 66b87e6, HF d8c1abd).

Entry point: ``AutoModelForImageTextToText.from_pretrained(path, trust_remote_code=True)`` and
``model.predict_action(processor=..., images, task, state, norm_tag="franka_droid",
inference_action_mode="continuous", ...)`` as in examples/droid/host_server_droid.py.
  images  exterior 1, exterior 2, wrist: HWC uint8 RGB, the three slots of the checkpoint (norm_stats
          camera_keys); resized to the DROID training size first, as the official DROID client does.
  state   (8,) [q1..q7 rad in the DROID convention (droid.py), gripper closure in [0, 1], 1 = closed];
          normalized and tokenized inside.
  task    the instruction; lowercased and stripped inside (normalize_language=True).
  output  (1, 15, 8): absolute joint positions (rad, clipped inside to the DROID 1-99 % range) and a continuous
          gripper command, 1 = closed; the official client clips it to [0, 1] and executes all 15 steps at 15 Hz.
Weights run in bf16 (about 10 GiB). Sampling noise comes from a CUDA generator seeded in reset().
"""
from huggingface_hub import snapshot_download
import numpy as np
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor

from vla.models.base import BaseVLA
from vla.models.droid import from_droid_joints, to_droid_joints
from vla.protocol import ActionChunk


class MolmoAct2(BaseVLA):
    def load(self):
        options = self.config["model"]
        path = snapshot_download(self.config["checkpoint"], revision=options["revision"])
        # extra_special_tokens={} works around the tokenizer config on transformers 4.57 (official server).
        self.processor = AutoProcessor.from_pretrained(path, trust_remote_code=True, extra_special_tokens={})
        self.model = AutoModelForImageTextToText.from_pretrained(
            path, trust_remote_code=True, dtype=torch.bfloat16).to("cuda").eval()
        self.generator = torch.Generator("cuda").manual_seed(0)

    def reset(self, seed):
        self.generator = torch.Generator("cuda").manual_seed(seed)

    def infer(self, obs):
        joint = obs.state["joint"]
        with torch.inference_mode():
            out = self.model.predict_action(
                processor=self.processor, task=obs.instruction,
                images=self.camera_images(obs),
                state=np.r_[to_droid_joints(joint), 1.0 - joint[7]].astype(np.float32), norm_tag="franka_droid",
                inference_action_mode="continuous", enable_depth_reasoning=False, num_steps=10,
                generator=self.generator, normalize_language=True, enable_cuda_graph=False)
        actions = out.actions[0].float().cpu().numpy()
        return ActionChunk(np.c_[from_droid_joints(actions[:, :7]), 1.0 - np.clip(actions[:, 7], 0.0, 1.0)]
                           .astype(np.float32))
