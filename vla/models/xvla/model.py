"""X-VLA-0.9B RoboTwin2 checkpoint through its Hugging Face remote code (X-VLA 6bc2513, HF a157c58).

Entry point: ``AutoModel.from_pretrained(checkpoint, trust_remote_code=True)`` and
``model.generate_actions(input_ids, image_input, image_mask, domain_id, proprio, steps=10) -> (1, 30, 20)``,
with inputs prepared as the official server does (modeling_xvla.py ``act``): the processor squashes each
view to 224 x 224 (bicubic, ImageNet normalization) and tokenizes the instruction (BART, 50 tokens).
  views    head, left wrist, right wrist, in this order (the first view is fused with the text).
  proprio  (20,) measured pose of both arms in the action layout (frames.py); gripper dims are zeroed inside.
           From the second chunk on, the official RoboTwin client sends its last commanded target instead; the
           two differ by at most reach_tolerance_m whenever that target was reached.
  output   (30, 20) absolute link6 poses in the RoboTwin world and g in (0, 1), 1 = closed (after sigmoid).
One action per saved RoboTwin frame, 15 steps of 1/250 s (16.7 Hz); the official RoboTwin client executes
all 30 actions before the next inference. Sampling noise uses the global torch RNG, seeded in reset().
"""
from PIL import Image
import torch
from transformers import AutoModel, AutoProcessor

from vla.models.base import BaseVLA
from vla.models.xvla.frames import base_transform, from_xvla, to_xvla
from vla.protocol import ActionChunk


class XVLA(BaseVLA):
    def load(self):
        options = self.config["model"]
        source = dict(pretrained_model_name_or_path=self.config["checkpoint"], revision=options["revision"],
                      trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(**source)
        self.model = AutoModel.from_pretrained(**source, torch_dtype=torch.float32).to("cuda").eval()
        self.domain_id = torch.tensor([options["domain_id"]], device="cuda")
        self.transforms = [base_transform(options["topogym_bases"][arm], options["robotwin_bases"][arm])
                           for arm in ("left", "right")]
        self.tcp_offset = options["tcp_offset_m"]

    def reset(self, seed):
        torch.manual_seed(seed)

    def infer(self, obs):
        inputs = self.processor([Image.fromarray(image) for image in self.camera_images(obs)], obs.instruction)
        proprio = to_xvla(obs.state["ee"], self.transforms, self.tcp_offset)
        batch = {name: value.to("cuda") for name, value in inputs.items()}
        actions = self.model.generate_actions(**batch, domain_id=self.domain_id,
                                              proprio=torch.from_numpy(proprio[None]).to("cuda"), steps=10)
        return ActionChunk(from_xvla(actions[0].float().cpu().numpy(), self.transforms, self.tcp_offset))
