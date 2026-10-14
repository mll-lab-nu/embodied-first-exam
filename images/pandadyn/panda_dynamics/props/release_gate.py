"""Visible, finite-force lifting shutter for pre-existing incoming balls."""

import numpy as np
import sapien
from .primitives import add_box, material
from .fixtures import DrivenFixture
from .mechanisms import quat_xyz


def release_gate(scene, name, origin):
    b = scene.create_articulation_builder()
    root = b.create_link_builder()
    root.set_name(name + "_base")
    add_box(root, [0.018, 0.014, 0.035], [0, 0.09, 0.02], density=500)
    link = b.create_link_builder(root)
    link.set_name(name)
    # The shutter sits between the lane side walls, so it lifts vertically;
    # 60 mm of travel clears a 32 mm ball sitting on the lane floor.
    axis = quat_xyz([0, -np.pi / 2, 0])
    link.set_joint_properties(
        "prismatic",
        [[0, 0.06]],
        sapien.Pose(q=axis),
        sapien.Pose(q=axis),
        friction=0,
        damping=0,
    )
    link.set_joint_name(name + "_motor")
    add_box(
        link,
        [0.005, 0.029, 0.025],
        [0, 0, 0.025],
        mat=material(0.3, 0.05),
        density=250,
        color=[0.80, 0.58, 0.21, 1],
    )
    b.initial_pose = sapien.Pose(origin)
    art = b.build(name=name + "_fixture", fix_root_link=True)
    return DrivenFixture(art, art.links[1], speed=0.22, force=3, kp=60, kd=6)
