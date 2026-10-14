"""Robots: what the world, the inverse kinematics, the skills and the actions need to know about an arm and its hand.

A `RobotSpec` names the model files (MuJoCo Menagerie, vendored under `assets/third_party/`), the joints and actuators
of the arm, the gripper and its opening table, the tool site, where the arm stands and the postures it rests and
plans in. `World` builds the model from the spec named by the scene (`{"robot": {"type": "fr3_2f85"}}`; default
`ur5e_2f85`); nothing else in `robosafe.sim` names a robot.

Adding a robot: vendor its model unmodified, write a spec here, and run `python -m robosafe.sim eval --robot <type>`
(docs/MOTION.md says what the numbers of the existing robots are and how the FR3 was tuned).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

PI = math.pi


@dataclass(frozen=True)
class RobotSpec:
    type: str
    # model files, relative to assets/third_party/mujoco_menagerie, and the prefixes their names get in the world
    arm_file: str
    arm_prefix: str
    hand_file: str
    hand_prefix: str
    attach_site: str                    # site of the arm model (without prefix) the hand is attached to
    # the arm
    arm_joints: tuple
    arm_actuators: tuple
    vel_limits: tuple                   # rad/s per joint, for planned motion
    acc_limits: tuple                   # rad/s^2 per joint
    lead: float                         # s: kv / kp of the arm's position servos (velocity feed-forward, see motion.py)
    # the hand
    gripper_actuator: str
    gripper_max: float                  # rad: driver joint angle of the closed gripper (0 = open)
    gripper_ctrl_max: float             # actuator control value of the closed gripper
    driver_joints: tuple
    opening_table: tuple                # ((gripper target in rad, free distance between the pads in m), ...), open first
    tip_reach_closed: float             # m: how far the closed fingertips reach past the pinch point
    tool_site: str                      # the pinch point: +z out of the hand, +y the closing direction
    pads: dict                          # {"left": (geom, ...), "right": (...)}, names without prefix
    hand_body: str                      # the body an assisted grasp is welded to and the wrist camera is fixed to
    mount_body: str                     # the body below the flange: the force-torque sensor sits here
    # where it stands and how it holds itself
    base_pos: tuple                     # bench frame
    base_yaw_deg: float
    pedestal: tuple                     # half extents (x, y) of the block under the base
    home: tuple                         # the rest posture: an episode starts here and `home` returns here
    ready: tuple                        # tool straight down over the work area: top grasps are planned from here
    ready_side: tuple                   # tool level, pointing away from the robot
    ready_side_low: tuple               # the same, lower (for things that stand low)
    ready_alt: tuple                    # the ready posture's mirror image in the arm's other shoulder configuration, or ()
    wrist_camera: dict                  # {"pos", "target", "up", "fovy"} in the frame of `hand_body`
    # how a load is carried level: "parallel" (three parallel joints, the wrist undoing the turn of the other two; a
    # matrix from (pan, lift, elbow) to joint rates) or "general" (any arm: position and tilt of the tool held by
    # damped least squares)
    carry: str = "general"
    carry_matrix: tuple = ()
    payload: float = 3.0                # kg: heavier things are not picked up
    # The gripper's servo, changed in memory from the model's own (empty: as the model has it): "force", the most the
    # actuator pushes with (in the actuator's own units: N on the 2F-85's tendon, N on the YAM's finger); "kp", "kv":
    # its position and velocity gains, as for a position actuator (N per unit of what it drives). The control value
    # a gripper target maps to is unchanged (`gripper_ctrl_max`): the same command closes the hand, with this force.
    grip_servo: dict = field(default_factory=dict)
    nullspace: float = 0.0              # redundant arms: how strongly the solver pulls towards the seed posture
    notes: str = ""
    # What a robot that is not "one arm file, the 2F-85 on its flange" needs (all optional):
    #   "lead": kv / kp per joint, where the servos of one arm differ
    #   "gripper_ctrl_open": the actuator control value of the open gripper (default 0; `gripper_ctrl_max` is the closed one)
    #   "driver_map": ((scale, offset), ...) per driver joint: scale * q + offset is the gripper position in the units of
    #       the gripper target (0 open, `gripper_max` closed), for fingers that are not measured in those units
    #   "tip_reach": how far the fingertips reach past the pinch point at any opening (default: the 2F-85's table)
    #   "hand_root": the body of the arm model the hand begins at, when the hand is part of the arm file (`hand_file` "")
    #   "sites": {name: {"body", "pos", "quat"}} and "geom_names": {body: {index: name}}: sites added to, and names
    #       given to shapes of, the model in memory (a vendored file is never edited)
    #   "mirror": the sign of each joint in the posture of an arm mounted as a mirror image (see `arms`)
    #   "drop_lights": leave out the lights the arm's model file brings along
    #   "look_distances": the distances from the point at which `look` tries to hold the pinch point, in order
    #   "pour_angles": smaller angles `pour` settles for when the arm cannot tip a vessel as far as asked
    #   "pour_turns": the tipping directions `pour` tries, in its own order (default: `actions.POUR_TURNS`)
    #   "cross_low": transfers may lower the hand before crossing (an arm whose reach shrinks with height)
    #   "place_aims": how often `place` aims again after a carry that turned the load (default 2)
    #   "slant": a transfer to a lower place may go there on one straight line where up, across and down has no solution
    #   "joint_ranges": {joint: (lo, hi)} for joints the model leaves without a limit (the solver needs one)
    #   "level_handles": a handle that sticks out sideways may also be taken with a level hand from its outer end
    #   "build": "module:function" and "build_args": the model is made by that function (it returns a `mujoco.MjSpec`,
    #       or that and a dict of what it changed) instead of being read from `arm_file`
    #   "arm_prefixes": {arm: (arm prefix, hand prefix)} and "model_prefix": every arm of `arms` is part of ONE model,
    #       which is attached once under `model_prefix`; an arm's joints and its hand's parts are found under its two
    #       prefixes (without this, each arm is its own copy of the model under "<name>/")
    #   "armature": {joint: kg m^2} for joints whose model has no rotor inertia (see `TIDYBOT`)
    #   "span": the shoulder, elbow and wrist joints of an arm with a spherical wrist: a pose whose wrist is further
    #       from the shoulder than the arm is long is not solved for (`skills._in_span`)
    #   "look_round": {"steep": elevations `look` from above may fall back to, from the robot's own side; "towards_front":
    #       the angles by which a view from the left or right may be brought round towards that side; "flat": lower
    #       elevations a view from a side may also take} for an arm that cannot hold its hand all round a thing
    #   "tipped_grasps": the angles from the vertical (degrees, in the order tried) at which a grasp from above may be
    #       taken by a hand that cannot point straight down where the thing is (`actions._tipped`)
    extra: dict = field(default_factory=dict)
    # A robot with several arms: ((name, base position, base yaw in degrees, mirrored), ...). Every arm is this spec;
    # the names of an arm's parts get the prefix "<name>/" and a mirrored arm takes the postures with `extra["mirror"]`
    # applied. Empty: one arm, standing at `base_pos`.
    arms: tuple = ()
    # A robot that drives: its arm stands on a base that moves on three planar joints (docs/MOTION.md 12). Empty: the
    # robot is bolted down. Keys:
    #   "joints", "actuators": the x slide, the y slide and the turn about the vertical, in that order (names without
    #       prefix); the control row of such a robot begins with their three targets
    #   "body": the base's body; "vel_limits", "acc_limits" (m/s, m/s, rad/s and per s), "slow": the factor of the slow gait
    #   "lead": kv / kp of the three servos; "force": the most each servo may push with (N, N, N m; set in memory)
    #   "footprint": the outline of the base on the floor, a polygon [[x, y], ...] in the base's frame (it need not
    #       be a circle; the planner uses the circle round it, the hazard layer the polygon)
    #   "clearance": how far the underside is above the floor; "height": the tallest the robot stands
    #   "head": the camera `head` and the mast it sits on, added in memory: {"pos", "pitch_deg", "fovy", "mast": radius}
    #       (in the frame of "body": default the base's; without "mast" none is drawn: the body has a head of its own)
    #   "carry": where the pinch point is held while the base drives with something in the hand, in the base's frame:
    #       [(forward, height), ...] in order of preference; or (forward, height, sideways), sideways being to the
    #       arm's own side (a robot whose arms hang beside its body)
    #   "reach": beyond this distance from the base's vertical no arm tool tries (m)
    #   "standoff": how far from a spot the base's middle stands to work there (m); "dock_gap": how near its outline
    #       comes to furniture it is sent to; "figure_standoff": how far its middle stays from a person or an animal
    #       it is sent to. They belong to the body: an arm that is short has to stand nearer (base.py has defaults)
    #   "close_up": a body that works only closed up to furniture: of the places to stand before a thing it takes the
    #       one from which a straight run at the thing brings it nearest
    #   "hand_offset": a body whose hands work beside its middle: with one hand about to work at the spot it was sent
    #       to, the base steps this far sideways once it has closed up, so that the spot is before that hand; "hand":
    #       the arm it takes a loose thing with when both hands are free and the call does not say
    #   "standoff_down": the same as "standoff" for a hand that points down, where that works at another distance:
    #       with something held from above, before a thing that can only be taken from above, and before a thing on
    #       something lower than "level_above" (the least height of a surface at which the level hand works)
    base: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.arm_joints)

    @property
    def prefixes(self) -> tuple:
        return (self.arm_prefix, self.hand_prefix)

    def mirrored(self) -> "RobotSpec":
        """This arm as its mirror image (the right arm of a pair): the same model, its named postures reflected."""
        sign = self.extra["mirror"]

        def flip(q):
            return tuple(float(s) * float(v) for s, v in zip(sign, q))

        return replace(self, home=flip(self.home), ready=flip(self.ready), ready_side=flip(self.ready_side),
                       ready_side_low=flip(self.ready_side_low), ready_alt=flip(self.ready_alt) if self.ready_alt else ())


# How the finger pads of every hand meet what they hold (set in memory on the shapes `RobotSpec.pads` names; a spec may
# replace any of it with `extra["pad_contact"]`). The pads take precedence over what they touch (`priority`), so these
# are the numbers of every grasp. Chosen for silicone or rubber pads on dry plastic, glass, metal and cardboard:
#   friction: sliding 1.0 (rubber on such surfaces: about 0.6 to 1.2), torsional 0.005 m (a patch of about 7.5 mm
#     radius under even pressure: 2/3 of the radius times the sliding coefficient), rolling 0.0001 m;
#   condim 6: the pad resists twisting about its normal and rolling, which a contact point without them (condim 3,
#     the model's own) cannot: a bottle held by its handle swung about the line between the pads;
#   solref: the model's own (time constant 4 ms, critically damped); solimp: the impedance rises to 0.9999 within
#     1 mm of penetration (the model's 0.99): with `world.IMPRATIO` this keeps a held thing from creeping in the hand.
# docs/MOTION.md 14 has the measurements these were chosen by.
PAD_CONTACT = {"friction": (1.0, 0.005, 0.0001), "condim": 6, "solref": (0.004, 1.0), "solimp": (0.99, 0.9999, 0.001, 0.5, 2.0),
               "priority": 1}

# The 2F-85 model's pads press with about 8.8 N each per unit of the finger tendon's force limit (`grip_servo["force"]`):
# about 44 N at the model's own 5, and 88 to 91 N at the 10 set below (measured on a 40 mm block, UR5e, control
# interface). `control.gripper_facts` states the limit from this.
PAD_N_PER_SERVO_FORCE_2F85 = 8.8

# the Robotiq 2F-85 as modelled in MuJoCo Menagerie; measured on the model (free distance between the pads against the
# driver joint target)
_2F85 = dict(
    hand_file="robotiq_2f85/2f85.xml", hand_prefix="2f85/",
    gripper_actuator="fingers_actuator", gripper_max=0.8, gripper_ctrl_max=255.0,
    driver_joints=("right_driver_joint", "left_driver_joint"),
    opening_table=((0.0, 0.0852), (0.2, 0.0657), (0.4, 0.0440), (0.6, 0.0209), (0.7824, 0.0004)),
    tip_reach_closed=0.0177,
    tool_site="pinch", pads={"left": ("left_pad1", "left_pad2"), "right": ("right_pad1", "right_pad2")},
    hand_body="base", mount_body="base_mount",
    # The model caps the tendon force at 5 (about 44 N on each pad). Twice that, about 88 N on each pad, is a
    # setting of the real gripper (20 to 235 N), and the least at which a pot (0.85 kg) held by its handle or the
    # 1.3 kg bottle by its handle stay put under a carry (docs/MOTION.md 14).
    grip_servo={"force": 10.0},
    # beside the palm, looking past the fingertips along the tool axis
    wrist_camera={"pos": [0.085, 0.0, 0.045], "target": [0.0, 0.0, 0.30], "up": [1.0, 0.0, 0.0], "fovy": 62.0},
)

UR5E_READY = (-PI / 2, -PI / 2, PI / 2, -PI / 2, -PI / 2, 0.0)

UR5E_2F85 = RobotSpec(
    type="ur5e_2f85",
    arm_file="universal_robots_ur5e/ur5e.xml", arm_prefix="ur5e/", attach_site="attachment_site",
    arm_joints=("shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"),
    arm_actuators=("shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"),
    vel_limits=(1.5, 1.5, 1.5, 2.0, 2.0, 2.0), acc_limits=(4.0, 4.0, 4.0, 6.0, 6.0, 6.0), lead=0.2,
    base_pos=(0.0, 0.30, 0.0), base_yaw_deg=180.0, pedestal=(0.10, 0.10),
    # rest: the arm upright at the back of the table, the hand high and tipped forward. It hides none of the work area
    # from the `front` and `top` cameras, and the wrist camera overlooks the table from the robot's side.
    home=(-PI / 2, -2.40, 1.60, -1.37, -PI / 2, 0.0),
    ready=UR5E_READY,
    # wrist_1 turned back a quarter turn: the tool is level and points away from the robot, the wrist's last link
    # 0.1 m under the tool axis
    ready_side=(UR5E_READY[0], UR5E_READY[1], UR5E_READY[2], UR5E_READY[3] - PI / 2.0, UR5E_READY[4], UR5E_READY[5]),
    # wrist_1 turned the other way and wrist_2 by half a turn: level, 0.2 m lower, the wrist over the tool axis
    ready_side_low=(UR5E_READY[0], UR5E_READY[1], UR5E_READY[2], UR5E_READY[3] + PI / 2.0, UR5E_READY[4] + PI, UR5E_READY[5]),
    # the same hand over the other half of the table, elbow and shoulder on the other side: tried when something tall
    # stands where the arm would be
    ready_alt=(PI / 2, -PI / 2, -PI / 2, -PI / 2, PI / 2, 0.0),
    # shoulder pan; shoulder lift with wrist_1 turned back by as much; elbow likewise
    carry="parallel",
    carry_matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, -1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    payload=3.0,
    **_2F85,
)

# Franka Research 3 with the same hand. Its base frame looks along +x, so it is turned to face the front of the table.
# Joint 4 bends the elbow (always negative), joint 6 the wrist; with joints 1, 3, 5 at zero the arm lies in one
# vertical plane and joints 2, 4, 6 are parallel, as lift, elbow and wrist_1 are on the UR5e.
FR3_READY = (0.0, -0.2097, 0.0, -2.1622, 0.0, 1.9524, PI / 2)     # pinch point at (0, -0.19, 0.33), fingers closing along x

FR3_2F85 = RobotSpec(
    type="fr3_2f85",
    arm_file="franka_fr3/fr3.xml", arm_prefix="fr3/", attach_site="attachment_site",
    arm_joints=tuple(f"fr3_joint{i}" for i in range(1, 8)),
    arm_actuators=tuple(f"fr3_joint{i}" for i in range(1, 8)),
    vel_limits=(1.5, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0), acc_limits=(4.0, 4.0, 4.0, 4.0, 6.0, 6.0, 6.0), lead=0.1,
    base_pos=(0.0, 0.30, 0.0), base_yaw_deg=-90.0, pedestal=(0.12, 0.12),
    # rest: upright at the back, the hand at (0, 0.06, 0.64) tipped 28 degrees forward; hides none of the work area
    home=(0.0, -1.10, 0.0, -2.10, 0.0, 1.50, PI / 2),
    ready=FR3_READY,
    # A level hand pointing away from the robot needs joint 6 within 0.2 rad of its upper limit (4.62): the FR3's wrist
    # is built to point down. These two are as low as that allows (pinch point at 0.32 m and 0.28 m).
    ready_side=(0.0, 0.4913, 0.0, -2.3413, 0.0, 4.4033, PI / 2),
    ready_side_low=(0.0, 0.6627, 0.0, -2.1629, 0.0, 4.3964, PI / 2),
    ready_alt=(),
    carry="general",
    payload=3.0,
    nullspace=0.05,
    # A fact of this body, not a defect: with the hand straight down at table height (pinch point 0.02 to 0.14 m) the
    # FR3 cannot work closer than 0.28 m to the vertical through its base (`near_reach_m`; 0.25 m at 0.20 m, 0.20 m at
    # 0.30 m), because the elbow (joint 4, -3.07 rad) is folded to its end there. With the base at y = 0.30 that is
    # the strip y > 0.02 around x = 0 at the back of the work area. A family whose placement needs the hand there is
    # left out of the FR3 (c_knife_handover: its board lies there); docs/CONTRACTS.md, the cross-body subset.
    # `bump_yaw_deg`: the admission's bump into a bystander (verify/bump.py) holds the hand down at the yaw of this
    # arm's ready posture, not at 0, which is a quarter turn from it and runs the flange joint (+-3.03 rad) to its end
    # on one half of the table. Only the FR3 has these keys; every other robot is bumped as before.
    extra={"near_reach_m": 0.28, "bump_yaw_deg": 90.0},
    **_2F85,
)

# Two I2RT YAM arms (MuJoCo Menagerie `i2rt_yam/yam.xml`: six joints and the `linear_3507` parallel gripper in one
# file). Joints 2, 3 and 4 are parallel (lift, elbow, wrist pitch; joints 3 and 4 turn the other way round from
# joint 2), joint 5 swings the hand sideways, joint 6 rolls it. The gripper's two fingers slide; its pads sit 44 mm to
# one side of the axis of joint 6. The model names neither the pads nor a pinch point: both are added in memory.
YAM_PINCH = (0.0, -0.044, 0.1288)       # in the frame of link_6: between the pads, 17.7 mm short of their ends
YAM_BIMANUAL = RobotSpec(
    type="yam_bimanual",
    arm_file="i2rt_yam/yam.xml", arm_prefix="yam/", attach_site="",
    hand_file="", hand_prefix="yam/",
    arm_joints=tuple(f"joint{i}" for i in range(1, 7)),
    arm_actuators=tuple(f"joint{i}" for i in range(1, 7)),
    vel_limits=(1.5, 1.5, 1.5, 2.0, 2.0, 2.0), acc_limits=(4.0, 4.0, 4.0, 6.0, 6.0, 6.0), lead=0.0625,
    # the gripper target is in the units of the 2F-85's (0 open, 0.8 closed) so that the skills' rates and thresholds
    # hold; the actuator takes the left finger's position in metres (0.0375 open, 0 closed)
    gripper_actuator="gripper", gripper_max=0.8, gripper_ctrl_max=0.0,
    driver_joints=("left_finger", "right_finger"),
    opening_table=((0.0, 0.0758), (0.8, 0.0008)),
    tip_reach_closed=0.0177,
    tool_site="pinch", pads={"left": ("left_pad",), "right": ("right_pad",)},
    hand_body="link_6", mount_body="link_6",
    # `base_pos` is the middle between the two arms (what "the robot's place" means where one number is wanted);
    # each arm stands on a riser 0.15 m high (docs/MOTION.md 11 says why), see `arms` below
    base_pos=(0.0, 0.26, 0.15), base_yaw_deg=-90.0, pedestal=(0.05, 0.05),
    # the postures of the left arm (the right arm's are their mirror images)
    # rest: upright at the back, the hand at 0.51 m tipped 40 degrees forward; hides none of the work area
    home=(0.0, 1.0, 1.8, -1.498, 0.0, 0.0),
    # the hand straight down 0.27 m in front of the base, 0.27 m above the table, fingers closing along x
    ready=(0.0, 1.73, 1.4638, -1.3046, 0.0, 0.0),
    # the hand level, pointing away from the robot, 0.42 m in front of the base at 0.31 m; and 0.52 m in front at
    # 0.175 m: joint 4 bends 90 degrees either way and no further, so a level hand is low only far from the base
    ready_side=(0.0, 1.4518, 0.5136, 0.9383, 0.0, 0.0),
    ready_side_low=(0.0, 2.2788, 0.8336, 1.4452, 0.0, 0.0),
    ready_alt=(),
    # beside the gripper's body on the side away from the pads, looking past the fingertips at the point 0.155 m
    # beyond the pinch point (the same offsets as on the 2F-85)
    wrist_camera={"pos": [0.0, 0.085, 0.045], "target": [0.0, -0.044, 0.2838], "up": [0.0, 1.0, 0.0], "fovy": 62.0},
    carry="parallel",
    carry_matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, -1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    payload=2.0,
    # The model's finger servo pushes with at most 100 N/m x 37 mm, about 4 N: it holds nothing heavier than a card by
    # friction. The real gripper is driven by a DM4310 motor (3 N m rated) through a linear gear; its force is not
    # published. 40 N on each finger, a stiffer servo that reaches it within 13 mm of travel, and damping near
    # critical for the finger's 0.22 kg (docs/MOTION.md 14).
    grip_servo={"force": 40.0, "kp": 3000.0, "kv": 50.0},
    extra={
        "lead": (0.0625, 0.0625, 0.0625, 0.025, 0.1, 0.1),
        "gripper_ctrl_open": 0.0375,
        "driver_map": ((-0.8 / 0.0375, 0.8), (0.8 / 0.0375, 0.8)),
        "tip_reach": 0.0177,
        "hand_root": "link_6",
        "geom_names": {"lf_down": {3: "left_pad"}, "rf_down": {3: "right_pad"}},
        # +z out of the hand, +y the direction the fingers close along, +x towards the side the wrist camera is on
        "sites": {"pinch": {"body": "link_6", "pos": list(YAM_PINCH), "quat": [0.7071067811865476, 0.0, 0.0, 0.7071067811865476]}},
        "mirror": (-1.0, 1.0, 1.0, 1.0, -1.0, -1.0),
        # how far from a point the pinch point is held to look at it: nearer than the other robots' 0.19 m where the
        # hand cannot be raised that far above the point
        "look_distances": (0.19, 0.25, 0.14, 0.10),
        # joint 4 stops the hand before a vessel held by its rim is tipped 110 degrees: these are tried then (past
        # level, so that a vessel still empties)
        "pour_angles": (100.0, 93.0),
        # a hand pointing down reaches 0.49 m at the height of the table and 0.40 m at 0.27 m above it: a transfer
        # may come down before it crosses
        "cross_low": True,
        "drop_lights": True,            # the model's own spotlight (one per arm) would light the bench differently from the other robots
    },
    arms=(("left", (-0.26, 0.26, 0.15), -90.0, False), ("right", (0.26, 0.26, 0.15), -90.0, True)),
)

# The Stanford TidyBot (MuJoCo Menagerie `stanford_tidybot/tidybot.xml`): a holonomic base on three planar joints, a
# Kinova Gen3 with seven joints and a Robotiq 2F-85, all in one file. What the file lacks is added in memory and never
# written back (docs/MOTION.md 10.4 and 12): limits for joints 1, 3, 5 and 7, which turn without one; a tool site at
# the true pinch point with the bench's axes (the file's `pinch_site` is 23.8 mm short of where the pads meet and has
# the closing direction on x); a lead per joint (two servo gains); force caps on the base's servos; a camera `head` on
# a mast at the rear left corner of the base (the model has none that sees more than the floor).
_TWO_TURNS = (-2.0 * PI, 2.0 * PI)
# Rest: the arm folded over the base, the pinch point 0.26 m ahead of the base's vertical and 0.72 m up, the hand tipped
# 60 degrees down. Nothing reaches beyond the base's own outline (0.284 m), and the wrist camera overlooks the floor
# from 0.3 to 1.5 m ahead of the base, which the head camera does not see nearer than a metre. (The file's `retract`
# keeps the arm as close; its hand points straight down at the base's own top.)
TIDYBOT_HOME = (0.0, -0.5239, PI, -2.0743, 0.0, -1.0677, PI / 2)
TIDYBOT = RobotSpec(
    type="tidybot",
    arm_file="stanford_tidybot/tidybot.xml", arm_prefix="tidybot/", attach_site="",
    arm_joints=tuple(f"joint_{i}" for i in range(1, 8)),
    arm_actuators=tuple(f"joint_{i}" for i in range(1, 8)),
    vel_limits=(1.5, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0), acc_limits=(4.0, 4.0, 4.0, 4.0, 6.0, 6.0, 6.0), lead=0.05,
    **{**_2F85, "hand_file": "", "hand_prefix": "tidybot/", "mount_body": "base"},
    base_pos=(0.0, 0.0, 0.0), base_yaw_deg=0.0, pedestal=(0.0, 0.0),
    home=TIDYBOT_HOME,
    # With joints 1 and 5 at zero and joint 3 at half a turn the arm lies in the vertical plane through the base's
    # heading, and joints 2, 4 and 6 are parallel. Ready: the hand straight down 0.40 m ahead of the base's vertical
    # and 0.85 m above the floor, the fingers closing across. (A hand pointing down cannot be held higher than about
    # 1.0 m: the shoulder is 0.62 m above the floor. docs/MOTION.md 12.)
    ready=(0.0, 0.2840, PI, -0.8298, 0.0, -2.0278, PI / 2),
    # the hand level and pointing ahead: 0.50 m ahead at 1.00 m (the elbow up and behind), and 0.60 m ahead at 0.60 m
    # (the elbow up and ahead), for things that stand low
    ready_side=(0.0, -0.3043, PI, -1.9427, 0.0, 0.0676, PI / 2),
    ready_side_low=(0.0, 0.7963, PI, -2.3872, 0.0, 1.6127, PI / 2),
    ready_alt=(),
    carry="general", payload=3.0, nullspace=0.05,
    extra={
        "lead": (0.05, 0.05, 0.05, 0.05, 0.1, 0.1, 0.1),
        "hand_root": "base",
        "sites": {"pinch": {"body": "base", "pos": [0.0, 0.0, 0.145], "quat": [1.0, 0.0, 0.0, 0.0]}},
        "joint_ranges": {"joint_1": _TWO_TURNS, "joint_3": _TWO_TURNS, "joint_5": _TWO_TURNS, "joint_7": _TWO_TURNS},
        # The file gives the Gen3's joints no rotor inertia. The last joint then turns nothing but the hand (0.001 kg m^2
        # about the tool axis), and the grasp weld of a thing whose mass centre is off that axis (a bottle or a kettle
        # held by its handle: 0.009 kg m^2 and more about it) is unstable against so light a body: the thing swings
        # in the hand until the wrist servos saturate, and no lift arrives (docs/MOTION.md 12.5). The three wrist
        # joints get what the bench arms' files give theirs (UR5e 0.1, FR3 0.074); 0.0005 on joint 7 already ends it.
        "armature": {"joint_5": 0.1, "joint_6": 0.1, "joint_7": 0.1},
        # The Gen3's wrist servos give more under a load than the bench arms' (leads 0.1 rad on joints 5 to 7). Held by
        # contact since 0.5.0 (no weld), a bottle held by its handle slides in the hand as it is turned to pour (39 mm
        # in tests/sim/test_sim_room_arm.py), and back upright the arm comes to rest 5.2 mrad off target on joint 7
        # with the bottle's weight further out: at rest, carrying a load, as `skills._settle` accepts on the bench arms
        # up to 3 mrad. 8 mrad (0.46 degree) here.
        "settle_pos_loaded": 8.0e-3,
        # ... and the bottle has turned 15 degrees in the fingers by then: `actions.pour` stands it up again
        "stand_up_after_pour": True,
        # the hand points straight down only up to 0.87 m above the floor: a pan on a counter is taken by its handle, level
        "level_handles": True,
        # ... and takes from a slant what has a grasp from above only (a cube, an apple, a knife, a tray, a basket): at
        # 0.60 m from a thing the hand reaches it tipped by 45 degrees or more on a 0.75 m surface and by 60 or more
        # on a 0.90 m one (docs/MOTION.md 12.6)
        "tipped_grasps": (55.0, 70.0, 40.0, 90.0),
        "span": ("joint_2", "joint_4", "joint_6"),
        # ... and looks from where it can: square from a side only at things that stand low
        "look_round": {"steep": (75.0, 60.0), "towards_front": (30.0, 50.0), "flat": (15.0,)},
        "look_distances": (0.19, 0.25, 0.14),
        # A level hand at the height of a table cannot be pitched down far, but it can be rolled: a vessel is tipped
        # sideways first (the last joint alone), then the other ways. A tall vessel on a 0.90 m surface cannot be
        # swung past level about its lip at all (the hand would have to rise to 1.4 m): it is tipped less far.
        "pour_turns": (90.0, -90.0, 65.0, -65.0, 115.0, -115.0, 0.0, 25.0, -25.0, 180.0, 155.0, -155.0),
        "pour_angles": (110.0, 100.0, 93.0),
        "slant": True,
        "place_aims": 6,
    },
    base={
        "joints": ("joint_x", "joint_y", "joint_th"), "actuators": ("joint_x", "joint_y", "joint_th"), "body": "base_link",
        "vel_limits": (0.5, 0.5, 1.0), "acc_limits": (1.0, 1.0, 2.0), "slow": 0.5,
        "lead": (0.05, 0.05, 0.02), "force": (400.0, 400.0, 150.0),
        # the base is a square of 0.482 m with its corners cut: everything of it is within 0.284 m of its vertical
        "footprint": ((0.241, 0.150), (0.150, 0.241), (-0.150, 0.241), (-0.241, 0.150),
                      (-0.241, -0.150), (-0.150, -0.241), (0.150, -0.241), (0.241, -0.150)),
        "clearance": 0.027, "height": 1.30,
        "head": {"pos": (-0.20, 0.18, 1.25), "pitch_deg": 15.0, "fovy": 60.0, "mast": 0.012},
        # (the first places suit a hand that points down; a level hand needs room behind it and is held further ahead)
        "carry": ((0.24, 0.80), (0.30, 0.80), (0.24, 0.95), (0.36, 0.90), (0.30, 0.65), (0.45, 0.90), (0.50, 1.00)),
        "reach": 1.0,
        # a level hand works at 0.75 m between 0.55 and 0.90 m from the base's vertical and at 0.90 m between 0.30 and 0.80 m
        "standoff": 0.60, "dock_gap": 0.04, "figure_standoff": 0.90,
    },
)

# The Unitree G1 gliding on a planar base, a parallel gripper drawn by our code on each wrist (docs/MOTION.md 10.4 "The
# gliding G1, measured" and 13). Its model is not a file attached as it is: `bodies.g1_glide.make_spec` builds it in
# memory from the unmodified vendored `unitree_g1/g1_with_hands.xml` (planar joints for the free joint, the legs and
# the waist fixed, the two three-finger hands replaced by `bodies.gripper_parallel`, the maker's name left off the
# chest). One model holds the base and both arms, so the arms have prefixes of their own inside it. Every number is
# measured on that model (`tests/sim/test_g1_spec.py` compares them again) except where 10.4 says CHOSEN.
# The body hangs with its feet 27 mm above the floor, the height of the TidyBot's underside: what lies flat and is
# lower than 22 mm (a rug, a cord, a door sill, the mat of the dock) passes under a base in the rooms (`base.FLAT`).
# (The stand-alone measurements of 10.4 were made at 5 mm; every height there is 22 mm lower than in a room.)
G1_FLOOR_CLEARANCE = 0.027
G1_ARM = ("shoulder_pitch_joint", "shoulder_roll_joint", "shoulder_yaw_joint", "elbow_joint", "wrist_roll_joint", "wrist_pitch_joint",
          "wrist_yaw_joint")
G1_GLIDE = RobotSpec(
    type="g1_glide",
    arm_file="unitree_g1/g1_with_hands.xml", arm_prefix="g1/left_", attach_site="",
    hand_file="", hand_prefix="g1/left_gripper/",
    arm_joints=G1_ARM, arm_actuators=G1_ARM,                    # the file names an actuator after its joint
    # the bench's planned limits (the file gives no speed limits); kv / kp of the file's servos with the gripper mounted
    vel_limits=(1.5, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0), acc_limits=(4.0, 4.0, 4.0, 4.0, 6.0, 6.0, 6.0), lead=0.0390,
    # the gripper target is in the units of the 2F-85's (0 open, 0.8 closed); the actuator takes the sum of the two
    # fingers' travel in metres (0 open, 0.0846 closed)
    gripper_actuator="grip", gripper_max=0.8, gripper_ctrl_max=0.0846,
    driver_joints=("finger_left", "finger_right"),
    opening_table=((0.0, 0.085), (0.2, 0.06385), (0.4, 0.0427), (0.6, 0.02155), (0.8, 0.0004)),
    tip_reach_closed=0.0177,
    tool_site="pinch", pads={"left": ("pad_left",), "right": ("pad_right",)},
    hand_body="palm", mount_body="palm",
    # a room robot stands where the scene puts it: the pelvis axis on the floor and the way it faces
    base_pos=(0.0, 0.0, 0.0), base_yaw_deg=0.0, pedestal=(0.0, 0.0),
    # The postures of the left arm (the right arm's are their mirror images), found by search (10.4 and 13). Rest: the
    # forearm raised, the hand beside the shoulder at 1.24 m with its fingers up; nothing of the robot is in the head
    # camera's picture, nothing of the arm is lower than 0.97 m or further ahead than the toes, and the straight
    # lines in joint space to the three postures below are free with a counter or a table right before the feet.
    # (Not the file's standing posture, the hand beside the thigh: from there every way to a working posture swings
    # the hand through the place where a counter stands that the robot has closed up to. docs/MOTION.md 13.)
    home=(0.25, 0.68, 0.43, -0.79, -0.68, -0.90, -0.18),
    # the hand straight down 0.25 m ahead of the pelvis axis and 0.15 m to the side, 1.04 m up (the elbow above the
    # shoulder: the only way this arm points down at that height), the fingers closing sideways
    ready=(-2.1052, 1.1484, -2.0361, 0.1527, -0.3605, -1.0992, -1.3178),
    # the hand level and pointing ahead, 0.35 m ahead and 0.15 m to the side, at 1.07 m and at 0.99 m
    ready_side=(-0.9849, 1.3346, -1.2715, -0.6119, 1.7911, 0.2651, -1.0687),
    ready_side_low=(-0.5923, 1.0827, -1.1664, -0.3584, -1.0043, -0.3433, 0.9914),
    ready_alt=(),
    # the drawn gripper's camera: beside the housing, looking past the fingertips (`gripper_parallel.wrist_camera`)
    wrist_camera={"pos": [0.044, 0.0, 0.0535], "target": [0.0, 0.0, 0.2723], "up": [1.0, 0.0, 0.0], "fovy": 62.0},
    # seven joints and no three parallel ones: position and tilt of the tool are held by the solver. A level hand holds
    # 2.0 kg in the worst posture found by the file's own torque limits (the wrist's 5 N m); `pick` refuses above it.
    carry="general", payload=2.0, nullspace=0.05,
    extra={
        "lead": (0.0390, 0.0292, 0.0263, 0.0245, 0.0095, 0.0135, 0.0115),
        "gripper_ctrl_open": 0.0,
        "driver_map": ((0.8 / 0.0423, 0.0), (0.8 / 0.0423, 0.0)),
        "tip_reach": 0.0177,
        "hand_root": "palm",
        "mirror": (1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0),      # roll and yaw joints change sign, pitch joints do not
        # a hand pointing down gets no higher than 1.06 to 1.16 m, 0.16 to 0.26 m above a 0.90 m counter: the pinch
        # point cannot always be held 0.19 m from a thing there
        "look_distances": (0.19, 0.25, 0.14, 0.10),
        "cross_low": True,                      # the hand reaches further ahead low than high
        "level_handles": True,                  # a pan on a counter is taken by its handle with a level hand
        "build": "robosafe.sim.bodies.g1_glide:make_spec",
        "build_args": {"waist": (), "clearance": G1_FLOOR_CLEARANCE, "hide_logo": True, "cameras": False},
        "model_prefix": "g1/",
        "arm_prefixes": {"left": ("g1/left_", "g1/left_gripper/"), "right": ("g1/right_", "g1/right_gripper/")},
    },
    # both arms hang on the one body, which stands where the base's joints put it
    arms=(("left", (0.0, 0.0, 0.0), 0.0, False), ("right", (0.0, 0.0, 0.0), 0.0, True)),
    base={
        "joints": ("base_x", "base_y", "base_yaw"), "actuators": ("base_x", "base_y", "base_yaw"), "body": "pelvis",
        # CHOSEN: the TidyBot's limits and gains (the planar trial of 10.4 was driven with them); the force caps are
        # 1.5 times the peak of that drive and four times that of its turn
        "vel_limits": (0.5, 0.5, 1.0), "acc_limits": (1.0, 1.0, 2.0), "slow": 0.5,
        "lead": (0.05, 0.05, 0.02), "force": (200.0, 200.0, 20.0),
        # The outline on the floor with the arms at rest, about the pelvis axis (x ahead, y to the robot's left): the
        # toes 0.145 m ahead, the raised forearms 0.31 m to either side, the heels and the back 0.076 m behind. Not a
        # circle: 0.62 m wide and 0.22 m deep. The planner uses the circle round it (0.31 m), the hazard layer the polygon.
        "footprint": ((0.145, 0.122), (0.121, 0.280), (0.012, 0.309), (-0.031, 0.309), (-0.052, 0.303), (-0.068, 0.288), (-0.076, 0.266),
                      (-0.076, -0.266), (-0.068, -0.288), (-0.052, -0.303), (-0.031, -0.309), (0.012, -0.309), (0.121, -0.280), (0.145, -0.122)),
        "clearance": G1_FLOOR_CLEARANCE, "height": 1.36,
        # the head camera of 10.4: on the trunk, 7 mm in front of the face and 1.26 m above the floor, looking ahead
        # and 40 degrees down with 90 degrees of view (a counter the robot stands at is in the picture from its edge)
        "head": {"body": "torso_link", "pos": (0.085, 0.0, 0.40), "pitch_deg": 40.0, "fovy": 90.0},
        # (forward, height, to the arm's own side): before the chest, high enough for what the hand holds to pass over
        # a counter the body closes up to
        "carry": ((0.26, 1.05, 0.12), (0.30, 1.05, 0.15), (0.25, 1.08, 0.15), (0.22, 1.02, 0.20), (0.35, 1.05, 0.15), (0.26, 0.97, 0.12)),
        "reach": 0.65,
        # This body works close up, and at two distances (docs/MOTION.md 13): the shared actions take a thing with a
        # level hand when it is 0.37 to 0.47 m ahead of the pelvis axis and from above when it is 0.23 to 0.33 m
        # ahead. It closes up until its middle is that far from the spot, or its shapes 2 cm from the furniture
        # (a level hand comes no lower than 0.80 m: on a table 0.75 m high things are taken from above)
        "standoff": 0.42, "standoff_down": 0.25, "level_above": 0.85, "dock_gap": 0.01, "figure_standoff": 0.90,
        # The shoulders are 0.10 m to either side, and a hand works best a little inside its own shoulder: with a
        # thing 0.04 to 0.10 m to the hand's side of the body's middle every pick of the lateral scan succeeded (13)
        "hand_offset": 0.07, "hand": "right", "close_up": True,
    },
)

ROBOTS: dict[str, RobotSpec] = {s.type: s for s in (UR5E_2F85, FR3_2F85, YAM_BIMANUAL, TIDYBOT, G1_GLIDE)}
DEFAULT = "ur5e_2f85"


def get(robot_type: str | None) -> RobotSpec:
    key = robot_type or DEFAULT
    if key not in ROBOTS:
        raise KeyError(f"unknown robot type {key!r}; robots: {sorted(ROBOTS)}")
    return ROBOTS[key]
