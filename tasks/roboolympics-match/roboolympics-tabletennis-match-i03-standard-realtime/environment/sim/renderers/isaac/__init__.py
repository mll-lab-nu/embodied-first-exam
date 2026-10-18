"""NVIDIA Isaac Sim 4.5 RTX path tracing (offline, for re-rendering): the export of renderers/export.py rendered by
scripts/olympiad/showcase/isaac/isaac_render.py in nvcr.io/nvidia/isaac-sim:4.5.0 (as root, as rerender.py runs it;
shader caches in SHOWCASE_ISAAC_CACHE, the first start compiles shaders for ~10 min)."""
from __future__ import annotations

import os
import subprocess

from ..export import SHOWCASE_TOOLS
from ..pathtrace import PathTracer

IMAGE = os.environ.get("SHOWCASE_ISAAC_IMAGE", "nvcr.io/nvidia/isaac-sim:4.5.0")
CACHE = os.environ.get("SHOWCASE_ISAAC_CACHE", os.path.expanduser("~/.cache/rcb-showcase-isaac"))
CACHES = (("kit", "/isaac-sim/kit/cache"), ("ov", "/root/.cache/ov"), ("glcache", "/root/.cache/nvidia/GLCache"),
          ("computecache", "/root/.nv/ComputeCache"), ("logs", "/root/.nvidia-omniverse/logs"),
          ("data", "/root/.local/share/ov/data"))


class IsaacRenderer(PathTracer):
    name = "isaac"
    title = "Isaac Sim RTX"
    image = IMAGE
    requirements = (f"Docker, an NVIDIA RTX GPU (driver >= 535.129) with the NVIDIA Container Toolkit, the image "
                    f"{IMAGE} (15 GB), ~20 GB free disk for caches, the NVIDIA Omniverse EULA (ACCEPT_EULA=Y); "
                    "mujoco in the calling process for the scene export")

    def __init__(self, scene, mode: str = "PathTracing", **opts):
        self.mode = mode
        super().__init__(scene, **opts)

    def trace(self, work, size):
        args = ["-e", "ACCEPT_EULA=Y", "-e", "PRIVACY_CONSENT=Y", "-e", "OMNI_KIT_ACCEPT_EULA=YES"]
        for sub, dst in CACHES:
            os.makedirs(os.path.join(CACHE, sub), exist_ok=True)
            args += ["-v", f"{os.path.join(CACHE, sub)}:{dst}:rw"]
        if os.path.exists("/usr/share/nvidia/nvoptix.bin"):
            args += ["-v", "/usr/share/nvidia/nvoptix.bin:/usr/share/nvidia/nvoptix.bin:ro"]
        args += ["-v", f"{work}:/s", "-v", f"{SHOWCASE_TOOLS}:/w:ro", "--entrypoint", "/isaac-sim/python.sh", self.image,
                 "/w/isaac/isaac_render.py", "/s/export", "/s/out", "--spp", str(self.samples), "--size", size,
                 "--mode", self.mode]
        try:
            self.docker(args, gpu=True, root=True)
        finally:                                             # Isaac writes as root
            subprocess.run(["docker", "run", "--rm", "--name", f"ro-renderer-isaac-chown-{os.getpid()}", "-v",
                            f"{work}:/s", "--entrypoint", "chown", self.image, "-R",
                            f"{os.getuid()}:{os.getgid()}", "/s"], capture_output=True)


RENDERER = IsaacRenderer
