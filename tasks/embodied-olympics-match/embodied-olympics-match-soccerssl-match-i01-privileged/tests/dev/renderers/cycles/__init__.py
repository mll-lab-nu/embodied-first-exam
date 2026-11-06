"""Blender 4.2 Cycles path tracing (offline, for re-rendering): the export of renderers/export.py traced by
scripts/olympiad/showcase/blender/cycles_render.py in the rcb-showcase-blender image. device = OPTIX (default) or
CUDA (GPU), or CPU (slow, no GPU needed)."""
from __future__ import annotations

import os

from ..export import SHOWCASE_TOOLS
from ..pathtrace import PathTracer

IMAGE = os.environ.get("SHOWCASE_BLENDER_IMAGE", "rcb-showcase-blender:4.2.23")


class CyclesRenderer(PathTracer):
    name = "cycles"
    title = "Blender Cycles"
    image = IMAGE
    requirements = (f"Docker, the image {IMAGE} (docker build -t {IMAGE} scripts/olympiad/showcase/blender; 1.8 GB) "
                    "and an NVIDIA GPU with the NVIDIA Container Toolkit (device=CPU works without one, slowly); "
                    "mujoco in the calling process for the scene export")

    def __init__(self, scene, device: str = "OPTIX", **opts):
        self.device = device
        super().__init__(scene, **opts)
        if device == "CPU":
            self.needs_gpu = False

    def gpu_optional(self):
        return self.device == "CPU"

    def trace(self, work, size):
        self.docker(["-v", f"{work}:/s", "-v", f"{SHOWCASE_TOOLS}:/w:ro", self.image, "blender", "-b",
                     "--factory-startup", "-P", "/w/blender/cycles_render.py", "--", "/s/export", "/s/out",
                     "--samples", str(self.samples), "--size", size, "--device", self.device],
                    gpu=self.device != "CPU")


RENDERER = CyclesRenderer
