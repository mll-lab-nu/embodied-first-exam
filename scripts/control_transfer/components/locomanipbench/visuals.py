"""Render-only public desired poses. No simulator state is exposed by overlays."""

import numpy as np
import mujoco

REVISION = "target-frames-v1"
COLORS = ((0.92, 0.12, 0.12, 1), (0.1, 0.75, 0.25, 1), (0.12, 0.4, 1, 1))


def style(model):
    """Change only appearance; keep floor height, contacts and all physics intact."""
    model.vis.rgba.haze[:] = [0.74, 0.73, 0.71, 1]
    floor = model.geom("floor").id
    material = model.geom_matid[floor]
    model.mat_texid[material, :] = -1
    model.mat_rgba[material] = [0.72, 0.70, 0.66, 1]
    model.mat_reflectance[material] = 0
    model.mat_specular[material] = 0.08
    model.mat_shininess[material] = 0.15
    # Neutral backdrop instead of the source asset's blue gradient.
    for i in range(model.ntex):
        if model.tex_type[i] == mujoco.mjtTexture.mjTEXTURE_SKYBOX:
            start = model.tex_adr[i]
            size = model.tex_width[i] * model.tex_height[i] * model.tex_nchannel[i]
            model.tex_data[start : start + size] = 190
    for name in ("left_goal", "right_goal", "base_goal"):
        model.site_rgba[model.site(name).id, 3] = 0


def targets(scene, target, floor_z):
    def geom(kind, size, pos, color, label=""):
        if scene.ngeom >= scene.maxgeom:
            raise RuntimeError("Target visualization exceeds scene capacity")
        g = scene.geoms[scene.ngeom]
        scene.ngeom += 1
        mujoco.mjv_initGeom(
            g,
            kind,
            np.asarray(size, dtype=float),
            np.asarray(pos, dtype=float),
            np.eye(3).ravel(),
            np.asarray(color, dtype=np.float32),
        )
        g.category = mujoco.mjtCatBit.mjCAT_DECOR
        g.label = label
        g.objid = -1
        g.segid = -1
        g.emission = 0.3
        return g

    def arrow(a, b, color, width=0.014):
        g = geom(mujoco.mjtGeom.mjGEOM_CAPSULE, [0, 0, 0], a, color)
        mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, width, np.asarray(a), np.asarray(b))
        geom(mujoco.mjtGeom.mjGEOM_SPHERE, [width * 1.6] * 3, b, color)

    for label, (p, r) in zip(("L", "R"), target[1]):
        geom(mujoco.mjtGeom.mjGEOM_SPHERE, [0.018] * 3, p, (1, 0.85, 0.25, 1), label)
        for k, color in enumerate(COLORS):
            arrow(p, p + 0.24 * r[:, k], color)
    base = np.array([target[0][0], target[0][1], floor_z + 0.012])
    yaw = target[0][2]
    for a, b in zip(np.linspace(0, 2 * np.pi, 41)[:-1], np.linspace(0, 2 * np.pi, 41)[1:]):
        g = geom(mujoco.mjtGeom.mjGEOM_CAPSULE, [0, 0, 0], base, (0.85, 0.53, 0.04, 1))
        mujoco.mjv_connector(
            g,
            mujoco.mjtGeom.mjGEOM_CAPSULE,
            0.008,
            base + 0.43 * np.array([np.cos(a), np.sin(a), 0]),
            base + 0.43 * np.array([np.cos(b), np.sin(b), 0]),
        )
    direction = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    tip = base + [0, 0, 0.018] + 0.68 * direction
    arrow(base + [0, 0, 0.018], tip, (0.85, 0.53, 0.04, 1), 0.014)
    for sign in (-1, 1):
        side = np.array([-direction[1], direction[0], 0])
        arrow(tip - 0.12 * direction + sign * 0.08 * side, tip, (0.85, 0.53, 0.04, 1), 0.01)
    # Cross marks the exact desired planar origin.
    for direction in (np.array([0.08, 0, 0]), np.array([0, 0.08, 0])):
        g = geom(mujoco.mjtGeom.mjGEOM_CAPSULE, [0, 0, 0], base, (0.35, 0.24, 0.04, 1))
        mujoco.mjv_connector(
            g, mujoco.mjtGeom.mjGEOM_CAPSULE, 0.007, base - direction + [0, 0, 0.012], base + direction + [0, 0, 0.012]
        )
