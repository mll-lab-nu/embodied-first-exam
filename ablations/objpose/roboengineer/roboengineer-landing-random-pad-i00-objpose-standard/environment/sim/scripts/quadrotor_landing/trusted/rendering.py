"""Presentation-only MuJoCo scene. A separate model keeps physics untouched.

Camera framing is fixed in world coordinates. No state/score overlays or hidden
parameter annotations are added to the observation images. Rotor animation uses
only the already-public noisy RPM measurement.
"""

import os
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from ..public.model import POSITIONS, PAD_RADIUS, xml

CPU_QUALITY = os.environ.get("LANDING_RENDER_QUALITY") == "cpu"
STYLE = "flight-studio/1-cpu" if CPU_QUALITY else "flight-studio/1"
WIDTH, HEIGHT, FPS = 1280, 720, 25


def add(parent, kind, **attributes):
    def value(v):
        return " ".join(str(x) for x in v) if isinstance(v, (list, tuple, np.ndarray)) else str(v)

    return ET.SubElement(parent, kind, {k: value(v) for k, v in attributes.items()})


def scene_xml(pad):
    root = ET.fromstring(xml(pad))
    visual = root.find("visual")
    visual.clear()
    add(visual, "global", offwidth=WIDTH, offheight=HEIGHT, azimuth=135, elevation=-28)
    add(
        visual,
        "quality",
        shadowsize=1024 if CPU_QUALITY else 4096,
        offsamples=0 if CPU_QUALITY else 4,
        numslices=40,
        numstacks=16,
    )
    add(visual, "headlight", ambient=[0.14, 0.14, 0.16], diffuse=[0.15, 0.15, 0.15], specular=[0.1] * 3)
    add(visual, "map", znear=0.01, zfar=40, fogstart=12, fogend=25)
    add(visual, "rgba", fog=[0.82, 0.84, 0.86, 1], haze=[0.82, 0.84, 0.86, 1])
    asset = add(root, "asset")
    add(
        asset,
        "texture",
        name="studio_sky",
        type="skybox",
        builtin="gradient",
        rgb1=[0.76, 0.8, 0.84],
        rgb2=[0.91, 0.92, 0.93],
        width=512,
        height=2048,
    )
    for name, rgb, specular, shininess in [
        ("floor_finish", [0.57, 0.61, 0.63], 0.12, 0.15),
        ("wall_finish", [0.78, 0.8, 0.81], 0.1, 0.2),
        ("graphite", [0.045, 0.06, 0.072], 0.45, 0.55),
        ("carbon", [0.09, 0.11, 0.12], 0.35, 0.4),
        ("alloy", [0.57, 0.64, 0.68], 0.75, 0.75),
        ("ivory", [0.86, 0.89, 0.89], 0.6, 0.55),
        ("orange", [1, 0.28, 0.065], 0.45, 0.5),
        ("pad_surface", [0.055, 0.105, 0.125], 0.25, 0.3),
        ("paint", [0.88, 0.94, 0.93], 0.15, 0.2),
        ("teal", [0.03, 0.65, 0.59], 0.4, 0.4),
    ]:
        add(asset, "material", name=name, rgba=[*rgb, 1], specular=specular, shininess=shininess)
    world = root.find("worldbody")
    for light in list(world.findall("light")):
        world.remove(light)
    add(
        world,
        "light",
        name="key",
        pos=[-1, 1, 5],
        dir=[0.15, -0.2, -1],
        directional="true",
        ambient=[0, 0, 0],
        diffuse=[0.6, 0.57, 0.53],
        specular=[0.55] * 3,
        castshadow="true",
    )
    add(
        world,
        "light",
        name="fill",
        pos=[2, 1, 3],
        dir=[-1, -0.2, -1],
        directional="true",
        ambient=[0, 0, 0],
        diffuse=[0.20, 0.25, 0.3],
        specular=[0.25] * 3,
        castshadow="false",
    )
    add(
        world,
        "light",
        name="rim",
        pos=[0, -3, 3],
        dir=[0, 1, -0.7],
        directional="true",
        ambient=[0, 0, 0],
        diffuse=[0.20, 0.23, 0.26],
        specular=[0.4] * 3,
        castshadow="false",
    )
    key = world.find("light[@name='key']")
    key.set("directional", "false")
    key.set("cutoff", "80")
    key.set("exponent", "2")
    key.set("attenuation", "1 .04 .012")
    key.set("diffuse", ".9 .85 .80")
    add(
        world,
        "light",
        name="wall_wash",
        pos=[2, -2, 3],
        dir=[-1, 1, -0.2],
        directional="true",
        ambient=[0.03, 0.03, 0.03],
        diffuse=[0.65, 0.65, 0.63],
        specular=[0.1] * 3,
        castshadow="false",
    )
    floor = world.find("geom[@name='floor']")
    floor.set("size", "0 0 .1")
    floor.set("rgba", ".50 .54 .56 1")
    floor.set("material", "floor_finish")
    # Hide the original physical pad markings; a visually richer marking occupies the same surface.
    for geom in world.findall("geom"):
        if geom is not floor:
            geom.set("group", "3")
    quad = world.find("body[@name='quad']")
    for geom in quad.findall("geom"):
        geom.set("group", "3")
    for site in quad.findall("site"):
        site.set("rgba", "0 0 0 0")

    def shape(parent, kind, material, **attrs):
        return add(parent, "geom", type=kind, material=material, contype=0, conaffinity=0, group=2, density=0, **attrs)

    # Quiet architectural details provide depth and scale without a dominant grid.
    shape(world, "box", "wall_finish", pos=[0, 2.8, 1.7], size=[6, 0.06, 1.7])
    shape(world, "box", "wall_finish", pos=[-2.8, 0, 1.7], size=[0.06, 6, 1.7])
    for x in np.arange(-5, 6, 0.8):
        shape(world, "box", "alloy", pos=[x, 2.73, 1.7], size=[0.004, 0.002, 1.7], rgba=[0.54, 0.58, 0.6, 1])
    shape(world, "box", "alloy", pos=[0, 2.72, 0.04], size=[6, 0.025, 0.04])
    shape(world, "box", "alloy", pos=[-2.72, 0, 0.04], size=[0.025, 6, 0.04])
    shape(world, "box", "paint", pos=[0, 2.72, 1.60], size=[6, 0.005, 0.018])
    shape(world, "box", "teal", pos=[0, 2.715, 1.55], size=[6, 0.005, 0.008])
    # Thin arena boundary and perimeter measurement ticks.
    for sign in (-1, 1):
        shape(world, "box", "paint", pos=[sign * 2.2, 0, 0.002], size=[0.014, 2.2, 0.001])
        shape(world, "box", "paint", pos=[0, sign * 2.2, 0.002], size=[2.2, 0.014, 0.001])
    for x in np.arange(-2, 2.01, 0.25):
        length = 0.10 if np.isclose(x, round(x)) else 0.045
        for sign in (-1, 1):
            shape(world, "box", "paint", pos=[x, sign * (2.2 - length), 0.002], size=[0.006, length, 0.001])
    for x in np.arange(-2, 2.01, 1):
        for y in np.arange(-2, 2.01, 1):
            if np.linalg.norm(np.array([x, y]) - np.asarray(pad[:2])) > PAD_RADIUS + 0.08:
                shape(
                    world, "box", "paint", pos=[x, y, 0.0015], size=[0.035, 0.003, 0.0005], rgba=[0.69, 0.72, 0.73, 1]
                )
                shape(
                    world, "box", "paint", pos=[x, y, 0.0015], size=[0.003, 0.035, 0.0005], rgba=[0.69, 0.72, 0.73, 1]
                )

    # Pad stays at the task's commanded world pose. All geometry is visual only.
    px, py = pad[:2]
    shape(world, "cylinder", "pad_surface", pos=[px, py, 0.0015], size=[PAD_RADIUS, 0.001])

    def ring(radius, width, material, segments=96, dashed=False):
        for i in range(segments):
            if dashed and i % 4 == 3:
                continue
            a, b = 2 * np.pi * np.array([i, i + 1]) / segments
            shape(
                world,
                "capsule",
                material,
                fromto=[
                    px + radius * np.cos(a),
                    py + radius * np.sin(a),
                    0.003,
                    px + radius * np.cos(b),
                    py + radius * np.sin(b),
                    0.003,
                ],
                size=[width],
            )

    ring(0.428, 0.006, "orange", dashed=True)
    ring(0.355, 0.004, "paint")
    for x in (-0.115, 0.115):
        shape(world, "box", "paint", pos=[px + x, py, 0.004], size=[0.020, 0.155, 0.001])
    shape(world, "box", "paint", pos=[px, py, 0.004], size=[0.115, 0.019, 0.001])
    for angle in (0, np.pi / 2, np.pi, 3 * np.pi / 2):
        # Four approach marks outside the landing circle.
        r = 0.51
        shape(
            world,
            "box",
            "teal",
            pos=[px + r * np.cos(angle), py + r * np.sin(angle), 0.002],
            size=[0.035, 0.014, 0.001],
            euler=[0, 0, angle],
        )

    # Procedural airframe shell; calibrated rotor diameter/positions are preserved.
    shape(quad, "ellipsoid", "graphite", pos=[0, 0, 0], size=[0.096, 0.068, 0.025])
    shape(quad, "box", "alloy", pos=[0, 0, -0.018], size=[0.077, 0.052, 0.006])
    shape(quad, "ellipsoid", "ivory", pos=[0.012, 0, 0.014], size=[0.082, 0.058, 0.025])
    shape(quad, "ellipsoid", "orange", pos=[0.075, 0, 0.010], size=[0.021, 0.055, 0.018])
    shape(quad, "box", "graphite", pos=[-0.012, 0, 0.04], size=[0.047, 0.033, 0.011])
    for x in (-0.036, 0.010):
        shape(quad, "box", "carbon", pos=[x, 0, 0.052], size=[0.006, 0.035, 0.002])
    for y in np.linspace(-0.038, 0.038, 7):
        shape(quad, "box", "graphite", pos=[0.046, y, 0.035], size=[0.014, 0.002, 0.003])
    # Forward optical module and visible fasteners.
    shape(quad, "box", "graphite", pos=[0.093, 0, -0.002], size=[0.012, 0.026, 0.012])
    for y in (-0.016, 0.016):
        shape(quad, "cylinder", "alloy", pos=[0.107, y, -0.002], size=[0.007, 0.002], euler=[0, np.pi / 2, 0])
        shape(quad, "cylinder", "graphite", pos=[0.110, y, -0.002], size=[0.005, 0.002], euler=[0, np.pi / 2, 0])
    for x in (-0.06, 0.06):
        for y in (-0.047, 0.047):
            shape(quad, "sphere", "alloy", pos=[x, y, 0.027], size=[0.0025])
    for i, (x, y) in enumerate(POSITIONS):
        shape(quad, "capsule", "carbon", fromto=[0, 0, 0, x, y, 0], size=[0.012])
        shape(quad, "capsule", "alloy", fromto=[x * 0.38, y * 0.38, 0.008, x * 0.85, y * 0.85, 0.008], size=[0.003])
        shape(quad, "cylinder", "graphite", pos=[x, y, 0.004], size=[0.021, 0.015])
        shape(quad, "cylinder", "alloy", pos=[x, y, 0.017], size=[0.019, 0.004])
        shape(quad, "cylinder", "orange" if x > 0 else "teal", pos=[x, y, 0.021], size=[0.019, 0.0015])
        shape(quad, "ellipsoid", "carbon", name=f"visual_blade_{i}", pos=[x, y, 0.027], size=[0.115, 0.012, 0.0015])
        shape(quad, "cylinder", "alloy", pos=[x, y, 0.028], size=[0.006, 0.004])
        shape(quad, "capsule", "graphite", fromto=[x * 0.6, y * 0.6, -0.015, x * 0.6, y * 0.6, -0.08], size=[0.006])
        shape(quad, "sphere", "carbon", pos=[x * 0.6, y * 0.6, -0.08], size=[0.01])
        shape(quad, "sphere", "orange" if x > 0 else "teal", pos=[x * 0.9, y * 0.9, -0.01], size=[0.005])
    return ET.tostring(root, encoding="unicode")


class StudioRenderer:
    def __init__(self, pad):
        self.model = mujoco.MjModel.from_xml_string(scene_xml(pad))
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, HEIGHT, WIDTH)
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [0, 0, 0.55]
        self.camera.distance = 4.65
        self.camera.azimuth = 130
        self.camera.elevation = -28
        self.option = mujoco.MjvOption()
        self.option.geomgroup[3] = 0  # original collision geometry remains in the physics model
        self.option.sitegroup[:] = 0
        self.blades = {self.model.geom(f"visual_blade_{i}").id: i for i in range(4)}
        self.phase = np.array([0, 0.6, 1.2, 1.8])
        self.previous_t = 0.0

    def render(self, physics_data, observation):
        self.data.qpos[:] = physics_data.qpos
        self.data.qvel[:] = physics_data.qvel
        self.data.time = physics_data.time
        mujoco.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera=self.camera, scene_option=self.option)
        rpm = np.asarray(observation["rotor_rpm"])
        self.phase += 2 * np.pi * rpm / 60 * (observation["t"] - self.previous_t) * np.array([1, -1, 1, -1])
        self.previous_t = observation["t"]
        for geom in self.renderer.scene.geoms[: self.renderer.scene.ngeom]:
            if geom.objtype != mujoco.mjtObj.mjOBJ_GEOM:
                continue
            if geom.objid in self.blades:
                angle = self.phase[self.blades[geom.objid]]
                c, s = np.cos(angle), np.sin(angle)
                geom.mat[:] = geom.mat @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        return self.renderer.render()

    def close(self):
        self.renderer.close()
