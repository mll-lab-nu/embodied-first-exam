"""CPU-only software video utility for the nominal and deployment simulators."""

import os
import json
from pathlib import Path
import subprocess

import mujoco
import numpy as np


class Video:
    def __init__(self, model, path, center, *, curve=None):
        if os.environ.get("MUJOCO_GL") != "osmesa":
            raise RuntimeError("Video requires MUJOCO_GL=osmesa before importing MuJoCo")
        from mujoco import gl_context

        if gl_context.GLContext.__module__ != "mujoco.osmesa":
            raise RuntimeError("MuJoCo was initialized with a non-OSMesa context")
        self.model = model
        self.visual_style = os.environ.get("NEURALFLY_VISUAL_STYLE", "primitive")
        if self.visual_style not in ("primitive", "skydio-x2/1"):
            raise ValueError("Unknown Neural Fly visual profile")
        self.visual_data = None
        if self.visual_style == "skydio-x2/1":
            try:
                from .neuralfly_visual import COMMIT, FILES, render_model
            except ImportError:
                from neuralfly_visual import COMMIT, FILES, render_model
            model = render_model()
            self.visual_data = mujoco.MjData(model)
            Path(path).with_suffix(".visual.json").write_text(
                json.dumps(
                    {
                        "profile": self.visual_style,
                        "source_commit": COMMIT,
                        "asset_sha256": FILES,
                        "description": "Skydio appearance; Neural Fly surrogate physics unchanged",
                        "resolution": [960, 720],
                        "fps": 10,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        self.render_model = model
        width, height = (960, 720) if self.visual_data is not None else (640, 480)
        model.vis.global_.offwidth, model.vis.global_.offheight = width, height
        model.vis.quality.offsamples = 0
        model.vis.quality.shadowsize = 256
        self.renderer = mujoco.Renderer(model, height, width)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = center
        self.camera.distance = 6
        self.camera.azimuth = 110
        self.camera.elevation = -18
        self.center = np.asarray(center)
        self.curve = curve
        self.writer = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{width}x{height}",
                "-r",
                "10",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            stdin=subprocess.PIPE,
        )

    def frame(self, data):
        visual_data = getattr(self, "visual_data", None)
        if visual_data is not None:
            # Copy pose only. Never step or write back to the physical model/data.
            visual_data.qpos[:] = data.qpos
            visual_data.time = data.time
            mujoco.mj_forward(self.render_model, visual_data)
            data = visual_data
        self.renderer.update_scene(data, camera=self.camera)
        scene = self.renderer.scene
        # Static world-body sites are cached by MuJoCo. Render the current public
        # target explicitly rather than trusting a stale data.site_xpos value.
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(
            geom,
            mujoco.mjtGeom.mjGEOM_SPHERE,
            np.full(3, 0.055),
            self.model.site_pos[0],
            np.eye(3).ravel(),
            np.array([1.0, 0.6, 0.1, 1.0]),
        )
        geom.emission = 0.5
        scene.ngeom += 1
        # World-frame public reference curve; contains no private-state overlays.
        curve = getattr(self, "curve", None)
        if curve is None:
            curve = [
                self.center + [1.25 * np.sin(a), 0.0, 0.75 * np.sin(2 * a)]
                for a in np.linspace(0.0, 2 * np.pi, 100, endpoint=False)
            ]
        for pos in curve:
            geom = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(
                geom,
                mujoco.mjtGeom.mjGEOM_SPHERE,
                np.full(3, 0.012),
                pos,
                np.eye(3).ravel(),
                np.array([0.2, 0.7, 0.65, 0.65]),
            )
            scene.ngeom += 1
        self.writer.stdin.write(self.renderer.render().tobytes())

    def close(self):
        self.renderer.close()
        self.writer.stdin.close()
        try:
            code = self.writer.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.writer.kill()
            self.writer.wait()
            raise
        if code:
            raise RuntimeError("Video encoding failed")
