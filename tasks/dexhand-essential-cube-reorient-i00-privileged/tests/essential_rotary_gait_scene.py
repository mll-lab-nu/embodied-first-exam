"""A real rotary encoder cap on an original bench-controller housing."""

import math
import xml.etree.ElementTree as ET

from essential_assets import asset_path
from essential_rotary_multi import reset, features, reset_history, snapshot


def _node(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {key: " ".join(map(str, value))
        if isinstance(value, (list, tuple)) else str(value)
        for key, value in attrs.items()})


def build(world, spec):
    """Build one passive hinge, with no hidden long contact drum."""
    p = spec["parameters"]
    center = p["initial_position"]
    rotor = _node(world, "body", name="task_rotor", pos=center)
    _node(rotor, "joint", name="turn", type="hinge", axis=(0, 1, 0),
          limited="false", damping=p.get("bearing_damping", 0.0007),
          frictionloss=p.get("bearing_frictionloss", 0.001), armature=0.00001)
    quat = (math.sqrt(0.5), math.sqrt(0.5), 0, 0)
    _node(rotor, "geom", name="task_rotor", type="mesh", mesh="encoder_collision",
          quat=quat, density="500", friction="1.2 0.008 0.0002", rgba="0 0 0 0")
    _node(rotor, "geom", name="encoder_cap_visual", type="mesh", mesh="encoder_visual",
          quat=quat, material="encoder_polymer", density="0", contype="0", conaffinity="0")
    # A flush inlaid index is a visual cue; it adds no grip tooth or lever.
    _node(rotor, "geom", name="encoder_index", type="box", size=(0.001, 0.0001, 0.006),
          pos=(0, -0.0076, 0.017), rgba=(0.91, 0.69, 0.25, 1),
          density="0", contype="0", conaffinity="0")
    front = 0.035
    _node(world, "geom", name="encoder_stationary_shaft", type="cylinder",
          size=(0.003, (front - center[1] - 0.0075) / 2), quat=quat,
          pos=(center[0], (front + center[1] + 0.0075) / 2, center[2]),
          rgba=(0.45, 0.47, 0.50, 1))
    _node(world, "geom", name="encoder_controller_case", type="box",
          size=(0.07, 0.025, 0.05), pos=(center[0] + 0.015, front + 0.025, center[2]),
          rgba=(0, 0, 0, 0))
    _node(world, "geom", name="encoder_controller_case_visual", type="mesh",
          mesh="encoder_case_visual", pos=(center[0] + 0.015, front + 0.025, center[2]),
          material="encoder_case_material", density="0", contype="0", conaffinity="0")
    _node(world, "geom", name="encoder_controller_panel", type="box",
          size=(0.069, 0.001, 0.049), pos=(center[0] + 0.015, front - 0.001, center[2]),
          rgba=(0, 0, 0, 0))
    _node(world, "geom", name="encoder_controller_panel_visual", type="mesh",
          mesh="encoder_panel_visual", pos=(center[0] + 0.015, front - 0.001, center[2]),
          material="encoder_panel_material", density="0", contype="0", conaffinity="0")
    _node(world, "geom", name="encoder_controller_display", type="box",
          size=(0.025, 0.001, 0.012), pos=(center[0] + 0.045, front - 0.0021, center[2] + 0.029),
          rgba=(0.025, 0.07, 0.09, 1))
    for dx in (-0.050, 0.080):
        for dz in (-0.042, 0.042):
            _node(world, "geom", name=f"controller_screw_{dx}_{dz}", type="cylinder",
                  size=(0.002, 0.001), pos=(center[0] + dx, front - 0.0021, center[2] + dz),
                  quat=quat, rgba=(0.25, 0.28, 0.31, 1))
    bottom = center[2] - 0.05
    for side in (-1, 1):
        _node(world, "geom", name=f"controller_mount_post_{side}", type="cylinder",
              size=(0.006, (bottom - 0.11) / 2),
              pos=(center[0] + 0.015 + side * 0.04, front + 0.025, (bottom + 0.11) / 2),
              rgba=(0.25, 0.28, 0.31, 1))
    _node(world, "geom", name="controller_mount_base", type="box",
          size=(0.08, 0.037, 0.005), pos=(center[0] + 0.015, front + 0.025, 0.105),
          rgba=(0.25, 0.28, 0.31, 1))
    return {"turn": 0.0}


def configure(source, spec):
    asset = source.find("asset")
    if asset is None:
        asset = ET.SubElement(source, "asset")
    _node(asset, "mesh", name="encoder_visual", file=asset_path(spec, "encoder_knob_visual.obj"))
    _node(asset, "mesh", name="encoder_collision", file=asset_path(spec, "encoder_knob_collision_convex.obj"))
    _node(asset, "mesh", name="encoder_case_visual", file=asset_path(spec, "controller_case_visual.obj"))
    _node(asset, "mesh", name="encoder_panel_visual", file=asset_path(spec, "controller_panel_visual.obj"))
    _node(asset, "texture", name="encoder_panel_texture", type="2d",
          file=asset_path(spec, "controller_panel.png"))
    _node(asset, "material", name="encoder_case_material", rgba=(0.22, 0.27, 0.32, 1),
          specular="0.2", shininess="0.15")
    _node(asset, "material", name="encoder_panel_material", texture="encoder_panel_texture",
          specular="0.15", shininess="0.1")
    _node(asset, "material", name="encoder_polymer", rgba=(0.055, 0.065, 0.075, 1),
          specular="0.35", shininess="0.25")
