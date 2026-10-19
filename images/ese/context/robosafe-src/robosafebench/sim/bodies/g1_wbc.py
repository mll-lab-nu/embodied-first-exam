"""The Unitree G1 that walks: BiGym 2.0's G1 with Dex1-1 grippers, its legs and waist driven by NVIDIA's GR00T-WBC.

The model is built in memory from the unmodified vendored `assets/third_party/bigym2/g1/g1_29dof_with_dex1_1.xml`
exactly as BiGym 2.0 (`bigym` 1.0.0 at 93ad4b3) builds it for its `groot_wbc_g1` backend (`bigym/robots/configs/g1.py`
`G1Dex1`, `bigym/robots/robot.py`, `bigym/robots/floating_base.py`, `bigym/loco/adapters/groot_wbc.py`,
`bigym/loco/lowerbody.py`; Apache-2.0). What that build does, and what is done here in the same order:

- the free joint of `pelvis` is replaced by six joints in BiGym's order: slides `pelvis_x`, `pelvis_y`, `pelvis_z`
  (limited to 0.35 to 1.20 m), hinges `pelvis_rx`, `pelvis_ry` (passive tilt) and `pelvis_rz` (yaw); none of them is
  driven or damped (BiGym adds position actuators for x, y, z, yaw and then sets their stiffness and the joints'
  damping to zero, `disable_skyhook`; they are left out here: they exert no force);
- the file's `motor` actuators of the twelve leg and three waist joints become position servos (BiGym appends them
  after the file's actuators); every servo of the legs, the waist, the arms and the fingers gets the gains of BiGym's
  tables: kp on the actuator, kv zero, the damping on the joint; armature 0.01 on the 15 joints of the controller,
  0.0036 / 0.00425 on the arms, 0.001 on the fingers;
- actuator force limits follow the joints' `actuatorfrcrange` (`actfrclimited` auto);
- sites `left_end_effector` and `right_end_effector` between each gripper's pads (0.148 m out on the wrist yaw link)
  (and, not in BiGym, `left_pinch` / `right_pinch` at the same points in the bench's tool frame);
- the file's ground plane and light are deleted (the world has its own floor and lights);
- physics options are those BiGym compiles for the G1 (`OPTIONS`; the file's plus `pin_contact_solver_options`).

Differences from BiGym 2.0, all outside the dynamics of the legs:
- the two shapes that spell the maker's name on the chest (`logo_link`, one drawn, one colliding) are deleted, as on
  the gliding G1, so that no picture shows it;
- the cameras are added by `robosafebench.sim.world` under the bench's names (`head`, `wrist_left`, `wrist_right`) at
  BiGym's mounts (`CAMERAS`; BiGym names them `head`, `left_wrist`, `right_wrist`). BiGym's eulers are radians, read
  under the robot file's compiler (`angle="radian"`); the world's scene is a fresh `MjSpec`, whose compiler reads
  degrees, so `add_cameras` converts them there (before 0.5.3 it did not: the head looked straight down, 89.4 degrees
  below the horizon, its picture turned a quarter, and the wrists' pictures were turned too). At BiGym's mounts the head
  looks ahead and about 60 degrees down (0.52 rad off straight down) and upright; each wrist camera looks along the
  hand, tilted 0.87 rad towards its back, upright (with the arms at the home posture they look ahead and up).

    spec, changes = make_spec()              # a mujoco.MjSpec to attach into a world under the prefix "g1/"
    model, changes = build()                 # compiled, standing on a floor of its own

The controller (the two ONNX policies) is `robosafebench.sim.wbc`; the robot's spec is `robosafebench.sim.robots.G1_WBC`.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

FILE = "bigym2/g1/g1_29dof_with_dex1_1.xml"
SIDES = ("left", "right")
LEG_JOINTS = tuple(f"{s}_{n}_joint" for s in SIDES for n in ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"))
WAIST_JOINTS = ("waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint")
ARM = ("shoulder_pitch_joint", "shoulder_roll_joint", "shoulder_yaw_joint", "elbow_joint", "wrist_roll_joint", "wrist_pitch_joint",
       "wrist_yaw_joint")
ARM_JOINTS = tuple(f"{s}_{n}" for s in SIDES for n in ARM)
LOWER_JOINTS = LEG_JOINTS + WAIST_JOINTS                # the 15 joints the controller drives, in its order
BODY_JOINTS = LOWER_JOINTS + ARM_JOINTS                 # the 29 joints it observes
FINGER_JOINTS = {s: (f"{s}_dex1_finger_joint_1", f"{s}_dex1_finger_joint_2") for s in SIDES}
# The floating base, BiGym's `G1_FLOATING_BASE` plus `G1_PASSIVE_TILT_DOFS`, in the order its joints are added.
BASE_JOINTS = ("pelvis_x", "pelvis_y", "pelvis_z", "pelvis_rx", "pelvis_ry", "pelvis_rz")
BASE_Z_RANGE = (0.35, 1.20)

# Gains (kp, kd): BiGym `G1_GROOT_WBC_JOINT_PD` (the policy's training gains), `G1_ARM_PD`, `G1_DEX1_HAND_PD`.
LOWER_PD = dict(zip(LOWER_JOINTS, zip((150, 150, 150, 200, 40, 40, 150, 150, 150, 200, 40, 40, 250, 250, 250),
                                      (2, 2, 2, 4, 2, 2, 2, 2, 2, 4, 2, 2, 5, 5, 5))))
ARM_PD = {f"{s}_{n}": g for s in SIDES for n, g in zip(ARM, ((150.0, 4.0), (150.0, 4.0), (150.0, 4.0), (100.0, 1.0),
                                                              (20.0, 2.0), (20.0, 2.0), (20.0, 2.0)))}
HAND_PD = {j: (2000.0, 30.0) for s in SIDES for j in FINGER_JOINTS[s]}
LOWER_ARMATURE = 0.01
ARM_ARMATURE = {j: (0.00425 if ("wrist_pitch" in j or "wrist_yaw" in j) else 0.003609725) for j in ARM_PD}
HAND_ARMATURE = 0.001
POSITION_KP = 150.0                                     # BiGym's uniform servo gain before the tables apply

# Dex1-1 finger travel: +0.0245 m open, -0.02 m closed (both joints together); BiGym's slew of 0.004 m per control step.
FINGER_OPEN, FINGER_CLOSED = 0.0245, -0.02
FINGER_SLEW = 0.004
EE_SITE_POS = (0.148, 0.0, 0.0)                         # the point between the pads on the wrist yaw link
PINCH_QUAT = (math.sqrt(0.5), 0.0, math.sqrt(0.5), 0.0)  # z_site = x_wrist (out of the hand), y_site = y_wrist

# The physics BiGym compiles for the G1: the robot file's options (timestep 1 ms, 50 iterations, elliptic cone,
# impratio 10) become the scene's, and `pin_contact_solver_options` sets Newton with two noslip iterations.
# (Measured on BiGym's compiled scene: the scene file's integrator is implicitfast; tolerance 1e-8 and the line search
# are MuJoCo's defaults.)
OPTIONS = {"timestep": 0.001, "iterations": 50, "solver": "newton", "cone": "elliptic", "impratio": 10.0, "noslip_iterations": 2,
           "integrator": "implicitfast", "tolerance": 1e-8, "ls_iterations": 50, "ls_tolerance": 0.01, "noslip_tolerance": 1e-6}

# BiGym's cameras (`G1Dex1._on_loaded`): body, position, euler (radians, MuJoCo's default sequence `xyz`, read under the
# G1 file's `<compiler angle="radian"/>`), fovy 60.
CAMERAS = {
    "head": ("torso_link", (0.12, 0.0, 0.37), (0.0, -0.52, -1.57)),
    "wrist_left": ("left_wrist_yaw_link", (0.12, 0.0, 0.04), (0.0, -0.87, -1.57)),
    "wrist_right": ("right_wrist_yaw_link", (0.12, 0.0, 0.04), (0.0, -0.87, -1.57)),
}
CAMERA_FOVY = 60.0


def third_party_dir() -> Path:
    from ...assets.paths import third_party_dir as asset_third_party_dir

    return asset_third_party_dir()


def apply_options(s: mujoco.MjSpec) -> None:
    """BiGym's physics for the G1 on a spec (the whole world it is part of takes them)."""
    o = s.option
    o.timestep = OPTIONS["timestep"]
    o.iterations = OPTIONS["iterations"]
    o.solver = mujoco.mjtSolver.mjSOL_NEWTON
    o.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    o.impratio = OPTIONS["impratio"]
    o.noslip_iterations = OPTIONS["noslip_iterations"]
    o.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    o.tolerance = OPTIONS["tolerance"]
    o.ls_iterations = OPTIONS["ls_iterations"]
    o.ls_tolerance = OPTIONS["ls_tolerance"]
    o.noslip_tolerance = OPTIONS["noslip_tolerance"]
    o.gravity = [0.0, 0.0, -9.81]


def add_cameras(s: mujoco.MjSpec, prefix: str = "") -> None:
    """BiGym's three cameras under the bench's names, on the bodies of a robot attached under `prefix`. A camera added
    to `s` is compiled under `s`'s own compiler: the robot file's (radians) in `make_spec`, but a fresh `MjSpec`'s
    (degrees, MuJoCo's default) in the world's scene, where the radians of `CAMERAS` are converted (0.5.3)."""
    seq = "".join(s.compiler.eulerseq)
    if seq != "xyz":
        raise ValueError(f"BiGym's camera eulers are in MuJoCo's default sequence 'xyz', the spec reads {seq!r}")
    unit = math.degrees if s.compiler.degree else float
    for name, (body, pos, euler) in CAMERAS.items():
        cam = s.body(prefix + body).add_camera(name=name, fovy=CAMERA_FOVY, pos=list(pos))
        cam.alt.type = mujoco.mjtOrientation.mjORIENTATION_EULER
        cam.alt.euler = [unit(v) for v in euler]


def make_spec(hide_logo: bool = True, root: Path | None = None, cameras: bool = False):
    """The walking G1 as a `mujoco.MjSpec` (no floor) and the dict of what was changed."""
    path = (root or third_party_dir()) / FILE
    s = mujoco.MjSpec.from_file(str(path))
    for asset in (*s.meshes, *s.textures, *s.hfields):      # BiGym's `scene.load`: an unnamed asset is named after its file
        if asset.file and not asset.name:
            asset.name = Path(asset.file).stem
    changes: dict = {"file": FILE}

    # G1Dex1._on_loaded: force limits by autolimits, the file's ground away, the end-effector sites
    s.default.joint.actfrclimited = mujoco.mjtLimited.mjLIMITED_AUTO
    for j in s.joints:
        j.actfrclimited = mujoco.mjtLimited.mjLIMITED_AUTO
    s.delete(s.geom("ground"))
    lights = list(s.worldbody.lights)
    for light in lights:
        s.delete(light)
    changes["deleted"] = ["geom ground", f"{len(lights)} light(s)"]
    for side in SIDES:
        s.body(f"{side}_wrist_yaw_link").add_site(name=f"{side}_end_effector", size=[0.01, 0.01, 0.01], pos=list(EE_SITE_POS), group=5)
        # the bench's tool frame at the same point (+z out of the hand along the forearm, +y the closing direction):
        # BiGym's site turned a quarter about its y axis
        s.body(f"{side}_wrist_yaw_link").add_site(name=f"{side}_pinch", size=[0.002, 0.002, 0.002], pos=list(EE_SITE_POS),
                                                  quat=list(PINCH_QUAT), group=5)

    # Robot._on_loaded: the pelvis loses its free joint and sits at the origin; the floating base's joints
    pelvis = s.body("pelvis")
    for j in list(pelvis.joints):
        s.delete(j)
    pelvis.pos = [0.0, 0.0, 0.0]
    pelvis.quat = [1.0, 0.0, 0.0, 0.0]
    for name in BASE_JOINTS:
        kind = mujoco.mjtJoint.mjJNT_SLIDE if name in ("pelvis_x", "pelvis_y", "pelvis_z") else mujoco.mjtJoint.mjJNT_HINGE
        axis = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[name[-1]]
        j = pelvis.add_joint(type=kind, name=name, axis=axis)
        if name == "pelvis_z":
            j.limited = mujoco.mjtLimited.mjLIMITED_TRUE
            j.range = list(BASE_Z_RANGE)
        else:
            j.limited = mujoco.mjtLimited.mjLIMITED_FALSE
    changes["base_joints"] = list(BASE_JOINTS)

    # motors of the legs and the waist become position servos, appended after the file's actuators
    for a in list(s.actuators):
        if a.biastype == mujoco.mjtBias.mjBIAS_NONE and a.target in LOWER_JOINTS:
            name, target = a.name or a.target, a.target
            rng = list(s.joint(target).range)
            s.delete(a)
            new = s.add_actuator(name=name, target=target, trntype=mujoco.mjtTrn.mjTRN_JOINT)
            new.set_to_position(kp=POSITION_KP)
            new.biasprm[2] = 0.0
            new.ctrlrange = rng
    # G1Dex1._apply_joint_pd_overrides: kp on the servo, kv zero, damping and armature on the joint
    pd = {**HAND_PD, **ARM_PD, **LOWER_PD}
    armature = {**ARM_ARMATURE, **{j: LOWER_ARMATURE for j in LOWER_JOINTS}}
    for a in s.actuators:
        j = s.joint(a.target)
        if j.name in armature:
            j.armature = float(armature[j.name])
        if j.name not in pd:
            continue
        kp, kd = pd[j.name]
        a.gainprm[0] = kp
        a.biasprm[1] = -kp
        a.biasprm[2] *= 0
        j.damping[0] = float(kd)
        if j.name in HAND_PD:
            j.armature = HAND_ARMATURE
    changes["servos"] = {"lower_body": len(LOWER_JOINTS), "arms": len(ARM_JOINTS), "fingers": len(HAND_PD)}

    changes["deleted_logo_geoms"] = 0
    if hide_logo:
        for g in list(s.body("torso_link").geoms):
            if g.meshname == "logo_link":
                s.delete(g)
                changes["deleted_logo_geoms"] += 1
    if cameras:
        add_cameras(s)
    apply_options(s)
    return s, changes


def build(hide_logo: bool = True, floor: bool = True, cameras: bool = True, extend=None):
    """The compiled model on a floor of its own (BiGym's floor: a plane at z = 0), and the dict of what was changed."""
    s, changes = make_spec(hide_logo=hide_logo, cameras=cameras)
    s.visual.global_.offwidth, s.visual.global_.offheight = 1280, 960
    if floor:
        s.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[10, 10, 0.1], rgba=[0.60, 0.58, 0.54, 1])
        s.worldbody.add_light(name="key", pos=[0.6, -1.0, 2.6], dir=[-0.2, 0.4, -1.0], diffuse=[0.6, 0.6, 0.6])
    if extend is not None:
        extend(s)
    m = s.compile()
    changes["counts"] = {"nq": m.nq, "nv": m.nv, "nu": m.nu}
    changes["total_mass"] = round(float(m.body_subtreemass[m.body("pelvis").id]), 4)
    return m, changes


def finger_target(ctrl: float) -> float:
    """The finger joints' position for a gripper command (0 open, 1 closed), as BiGym interpolates it."""
    c = float(np.clip(ctrl, 0.0, 1.0))
    return float(np.interp(c, (0.0, 1.0), (FINGER_OPEN, FINGER_CLOSED)))


def gripper_state(q1: float, q2: float) -> float:
    """BiGym's gripper reading: 0 open, 1 closed, from the mean of the two finger joints."""
    return float(np.interp(0.5 * (float(q1) + float(q2)), (FINGER_CLOSED, FINGER_OPEN), (1.0, 0.0)))
