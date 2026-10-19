"""Headless rendering through EGL."""
from __future__ import annotations

import os

os.environ.setdefault("MUJOCO_GL", "egl")       # must be set before mujoco is first imported

import numpy as np


def load(xml_or_model):
    import mujoco

    if isinstance(xml_or_model, str):
        if xml_or_model.lstrip().startswith("<"):
            return mujoco.MjModel.from_xml_string(xml_or_model)
        return mujoco.MjModel.from_xml_path(xml_or_model)
    return xml_or_model


def render(xml_or_model, camera: str | int = "overview", width: int = 640, height: int = 480, data=None) -> np.ndarray:
    """Render one RGB frame as a uint8 array of shape (height, width, 3).

    `xml_or_model` is an MJCF string, a path to an MJCF file, or a compiled `mujoco.MjModel`. Without `data` the model
    is drawn in its initial configuration. Display textures are read from the model at every call, so a display
    repainted with `embodied_safety_exam.assets.display.paint` shows its new text.
    """
    import mujoco

    backend = os.environ.get("MUJOCO_GL", "")
    if backend != "egl":
        raise RuntimeError(f"embodied_safety_exam.assets.render needs MUJOCO_GL=egl (found {backend!r}); set it before importing mujoco")
    model = load(xml_or_model)
    if data is None:
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
    model.vis.global_.offwidth = max(int(model.vis.global_.offwidth), int(width))
    model.vis.global_.offheight = max(int(model.vis.global_.offheight), int(height))
    renderer = mujoco.Renderer(model, int(height), int(width))
    try:
        renderer.update_scene(data, camera)
        return renderer.render().copy()
    finally:
        renderer.close()
