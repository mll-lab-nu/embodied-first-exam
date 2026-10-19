"""The gliding G1's numbers that a `RobotSpec` has no field for.

The robot's spec is `robosafebench.sim.robots.G1_GLIDE` (type `g1_glide`); it began as a draft in this module and was moved
there when the body became a robot of the world (docs/MOTION.md 13). What is left here is what the spec does not
carry and the measurements of docs/MOTION.md 10.4 rest on: the arm's joint limits and torque limits, the servo gains,
the gripper's numbers, the body's box at rest, how near furniture it stands, and what it reaches. Every number is
measured on the model `g1_glide.build()` returns (`tests/sim/test_g1_spec.py` compares them with the model again)
except where a comment says CHOSEN.

How the names work. The body is one model, attached into the world once under the prefix `g1/`. Both arms are in it:
the joints of the left arm are `g1/left_shoulder_pitch_joint` and so on, its hand's parts `g1/left_gripper/palm`,
`g1/left_gripper/pinch`. So an arm's prefix is `g1/left_` and its hand's `g1/left_gripper/`
(`RobotSpec.extra["arm_prefixes"]`). An arm's bodies are found by walking the tree (`world._arm_index`): the legs'
names begin with `left_` too.
"""
from __future__ import annotations

from . import g1_glide as G
from . import gripper_parallel as P
from .g1_measure import POSTURES

_D = P.DIMS

MEASURED: dict = {
    # left arm, rad; the right arm's by `g1_glide.mirror`
    "arm_ranges": ((-3.0892, 2.6704), (-1.5882, 2.2515), (-2.618, 2.618), (-1.0472, 2.0944), (-1.97222, 1.97222),
                   (-1.61443, 1.61443), (-1.61443, 1.61443)),
    "arm_force_limits": (25.0, 25.0, 25.0, 25.0, 25.0, 5.0, 5.0),       # N m, the file's
    "arm_kp": 500.0, "arm_damping_ratio": 1.0,                           # the file's
    "gripper": {"module": "robosafebench.sim.bodies.gripper_parallel", "opening": _D.opening, "grip_force": _D.grip_force, "mass": _D.mass,
                "mount": {"body": "<side>_wrist_yaw_link", "pos": G.MOUNT_POS, "quat": G.MOUNT_QUAT}},
    # the base's servos (the spec carries their lead, kv / kp, and their force caps)
    "base_kp": G.BASE_KP, "base_kv": G.BASE_KV,
    "pelvis_standing": G.PELVIS_STANDING,                                # the pelvis origin above the floor, standing; a room adds the clearance
    # the body's box about the pelvis axis in the robot's frame (x ahead, y to its left): rectangles round the collision
    # shapes' boxes, arms at rest; `radius` is the farthest any of it is from the axis. (The spec's footprint is the
    # outline of everything that is drawn, as a polygon: the drawn toes reach 12 mm further than the colliding ones.)
    "box": {"x": (-0.08, 0.13), "y": (-0.32, 0.32), "radius": 0.32, "without_arms": {"x": (-0.08, 0.13), "y": (-0.19, 0.19)},
            "height_above_standing": 1.33 - G.CLEARANCE},
    # how near a counter or table the pelvis axis may come, and how near it has to (MOTION 10.4)
    "stand_off": {"nearest": {"counter": 0.13, "table_top_on_legs": 0.07}, "used": 0.15, "farthest_useful": 0.30},
    "postures": {"carry": POSTURES["carry"]},   # the hand level before the chest, for something that must stay upright
    "waist": {"kept": (), "note": "all three waist joints deleted; `make_spec(waist=(\"waist_pitch_joint\",))` keeps one"},
    # heights of the pinch point above the floor that some posture reaches, waist fixed, the feet 5 mm above the floor
    # (2 cm steps ahead of the shoulder); in a room the feet hang `robots.G1_FLOOR_CLEARANCE` above it and these are
    # 22 mm more
    "reach": {"hand_down_height": (0.60, 1.14), "hand_level_height": (0.78, 1.32), "floor": False},
}


def spec():
    """The robot's spec (`robosafebench.sim.robots.G1_GLIDE`)."""
    from .. import robots
    return robots.G1_GLIDE


def row_layout() -> tuple:
    """The control row of this body: base targets, the left arm's joints, the right arm's, the two gripper targets."""
    return (("base", 3), ("left arm", 7), ("right arm", 7), ("left gripper", 1), ("right gripper", 1))
