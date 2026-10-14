"""CPU-only software video utility for the nominal and deployment simulators."""

import os
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
        model.vis.quality.offsamples = 0
        model.vis.quality.shadowsize = 256
        self.renderer = mujoco.Renderer(model, 480, 640)
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
                "640x480",
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
