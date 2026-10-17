"""Shared part of the offline path-traced renderers (cycles, isaac): preflight (Docker, image, GPU), the showcase
model with its same-scene check, export (export.py), one container run per camera group, PNG read-back and the
re-render tag on every frame. These renderers are for re-rendering recorded matches (realtime = False); they run on
a host with Docker and an NVIDIA GPU, and need mujoco in the calling process for the export."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile

import numpy as np

from .base import Renderer, RendererUnavailable, Scene, as_cameras
from .export import SHOWCASE_TOOLS, export
from .label import label_text, stamp


def image_present(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def gpu_present(gpu) -> bool:
    if gpu is None or shutil.which("nvidia-smi") is None:
        return False
    r = subprocess.run(["nvidia-smi", "-i", str(gpu), "--query-gpu=name", "--format=csv,noheader"],
                       capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


class PathTracer(Renderer):
    realtime = False
    needs_gpu = True
    image = ""
    requirements = ""
    title = ""

    def __init__(self, scene: Scene, gpu="0", samples: int = 64, stamp: bool = True, **opts):
        super().__init__(scene, **opts)
        self.gpu = None if gpu in (None, "none") else str(gpu)
        self.samples, self.stamp = int(samples), bool(stamp)
        self.label = label_text(self.title, presentation=scene.match is not None and not scene.players)
        self.preflight()
        from .mujoco_showcase import ShowcaseRenderer
        self._model = ShowcaseRenderer(scene, n_cams=1).m        # raises unless it is the same scene

    def needs(self):
        return [] if self.gpu_optional() else [("gpu", gpu_present(self.gpu), "an NVIDIA GPU (gpu=<index>)")]

    def gpu_optional(self) -> bool:
        return False

    def preflight(self):
        if os.environ.get("RO_RENDERER_OFFLINE") == "1":
            raise RendererUnavailable(self.name, "disabled on this host (RO_RENDERER_OFFLINE=1)", self.requirements)
        if shutil.which("docker") is None or subprocess.run(["docker", "version"], capture_output=True).returncode:
            raise RendererUnavailable(self.name, "Docker is not available here", self.requirements)
        if not image_present(self.image):
            raise RendererUnavailable(self.name, f"missing image {self.image}", self.requirements)
        for what, ok, text in self.needs():
            if not ok:
                raise RendererUnavailable(self.name, f"no {text}", self.requirements)
        if not os.path.isdir(SHOWCASE_TOOLS):
            raise RendererUnavailable(self.name, "scripts/olympiad/showcase is missing", self.requirements)

    def render(self, state, cameras):
        cams = as_cameras(cameras)
        out = [None] * len(cams)
        groups = {}
        for i, c in enumerate(cams):
            groups.setdefault((c.width, c.height, c.fovy_deg), []).append(i)
        for (w, h, _), idx in groups.items():
            work = tempfile.mkdtemp(prefix=f"ro-{self.name}-")
            try:
                export(self._model, [(state, cams[i]) for i in idx], os.path.join(work, "export"), self.name)
                self.trace(work, f"{w}x{h}")
                files = sorted(glob.glob(os.path.join(work, "out", "frame_*.png")))
                if len(files) != len(idx):
                    raise RuntimeError(f"{self.name}: {len(files)} frames for {len(idx)} cameras")
                from PIL import Image
                for i, f in zip(idx, files):
                    img = np.asarray(Image.open(f).convert("RGB"))
                    out[i] = stamp(img, self.label) if self.stamp else img
            finally:
                shutil.rmtree(work, ignore_errors=True)
        return out

    def trace(self, work: str, size: str):
        raise NotImplementedError

    def docker(self, args, gpu=True, root=False):
        c = ["docker", "run", "--rm", "--name", f"ro-renderer-{self.name}-{os.getpid()}", "--network", "none"]
        if not root:
            c += ["--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
        if gpu and self.gpu is not None:
            c += ["--gpus", f"device={self.gpu}", "-e", "NVIDIA_DRIVER_CAPABILITIES=all"]
        subprocess.run(c + args, check=True, capture_output=True)
