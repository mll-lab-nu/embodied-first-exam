"""The Unitree G1 as a body that glides: built in memory from the unmodified vendored `g1_with_hands.xml`.

What is changed in memory (the file is never written to; `build` returns the list as a dict):

- the free joint of `pelvis` is replaced by three planar joints, `base_x`, `base_y` (slides) and `base_yaw` (a hinge
  about the vertical), each with a position actuator of the same name;
- the twelve leg joints and their actuators are deleted: the legs are part of the base in the standing posture (the
  file's `stand` keyframe has every leg joint at zero), and the pelvis hangs `clearance` higher than standing, so that
  the feet are that far above the floor and nothing presses on it;
- the waist joints are deleted too (`waist=()`), or the ones named in `waist` are kept with their actuators;
- the two three-finger hands are deleted (seven joints, seven actuators and the palm each) and the parallel gripper of
  `gripper_parallel` is mounted on each wrist (`left_gripper/...`, `right_gripper/...`); the wrist link's inertia,
  which in the file includes the palm, is replaced by that of the flange alone;
- cameras: `head` on `torso_link` in front of the face, looking ahead and down; `wrist_left` and `wrist_right` on the
  grippers;
- the shape on the chest that spells the maker's name (`logo_link`) is deleted, so that no picture shows it;
- the file's keyframe (it no longer fits) and its light are deleted; gravity compensation is switched on for the
  robot's bodies, as `robosafe.sim.world` does for every robot.

    model, changes = build()                 # compiled, standing on a floor of its own, with the bench's physics options
    spec, changes = make_spec()              # a mujoco.MjSpec to attach into a world: `world.attach(spec, frame=..., prefix="g1/")`
    ix = index(model)                        # where the base, the arms and the grippers are in the model

Nothing here walks. docs/MOTION.md 10.4 ("The gliding G1, measured") has the numbers; the robot's spec is
`robosafe.sim.robots.G1_GLIDE`, whose `extra["build"]` names `make_spec` (docs/MOTION.md 13).
"""
from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from . import gripper_parallel as _gripper  # noqa: E402

FILE = "unitree_g1/g1_with_hands.xml"
SIDES = ("left", "right")
ARM_JOINTS = ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow", "wrist_roll", "wrist_pitch", "wrist_yaw")
LEG_JOINTS = ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll")
WAIST_JOINTS = ("waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint")
HAND_JOINTS = ("thumb_0", "thumb_1", "thumb_2", "middle_0", "middle_1", "index_0", "index_1")
HAND_ROOTS = ("thumb_0", "middle_0", "index_0")           # the bodies a hand's three fingers begin at
BASE_JOINTS = ("base_x", "base_y", "base_yaw")

# Measured on the vendored model in its `stand` keyframe: the pelvis origin is this far above the lowest point of the
# feet (docs/MOTION.md 10.4 gives 0.7923; `tests/sim/test_g1_glide.py` measures it again).
PELVIS_STANDING = 0.79227
CLEARANCE = 0.005           # m: how far the feet hang above the floor
# The base servos: the gains of the TidyBot's own base joints (the planar trial of MOTION 10.4 was run with them), and
# a force limit, which that file does not have. CHOSEN: 1.5 times the 134 N that `drive_trial` needs at its start (1 m/s^2
# on 34 kg through a servo that lags), and four times the 5.1 N m of its turn (an arm held out with a load adds inertia).
BASE_KP = (1.0e6, 1.0e6, 5.0e4)
BASE_KV = (5.0e4, 5.0e4, 1.0e3)
BASE_FORCE = (200.0, 200.0, 20.0)       # N, N, N m
# Where a gripper sits on a wrist: its mounting face on the end of the wrist link (where the palm began), its +z along
# the forearm (the wrist link's +x), its closing direction across the wrist's pitch axis (-y), its camera side on the
# wrist's +z. The same on both sides, which makes the two hands mirror images (the gripper is symmetric in y).
MOUNT_POS = (0.0415, 0.0, 0.0)
MOUNT_QUAT = (0.0, math.sqrt(0.5), 0.0, math.sqrt(0.5))     # half a turn about (1, 0, 1): x_g = z_w, y_g = -y_w, z_g = x_w
# The wrist link without the palm: a flange. The file's inertia for the link (0.457 kg, centre of mass 0.089 m out, in
# the middle of the palm) is nearly all palm; what is left is CHOSEN, not measured.
WRIST_STUB = {"mass": 0.05, "pos": (0.012, 0.0, 0.0), "inertia": (2.5e-5, 2.5e-5, 2.5e-5)}
# The head camera in the frame of `torso_link`: 7 mm in front of the face, at eye height (1.24 m above the floor), looking
# ahead and 40 degrees down with 90 degrees of view: from 5 degrees above level down to 85 degrees below it, so that it
# sees the room ahead and, standing at a counter, the counter's top from its front edge on (docs/MOTION.md 10.4).
HEAD_CAMERA = {"body": "torso_link", "pos": (0.085, 0.0, 0.40), "down_deg": 40.0, "fovy": 90.0}


def third_party_dir() -> Path:
    env = os.environ.get("ROBOSAFE_THIRD_PARTY")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "assets" / "third_party"


def _look_at(pos, target, up=(0.0, 0.0, 1.0)) -> list:
    pos, target, up = (np.asarray(v, dtype=np.float64) for v in (pos, target, up))
    f = (target - pos) / np.linalg.norm(target - pos)
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, np.stack([r, np.cross(r, f), -f], axis=1).flatten())
    return [float(v) for v in quat]


def make_spec(waist: tuple = (), clearance: float = CLEARANCE, hide_logo: bool = True, gravcomp: bool = True,
              gripper: _gripper.Dims = _gripper.DIMS, root: Path | None = None, cameras: bool = True):
    """The gliding G1 as a `mujoco.MjSpec` and the dict of what was changed. `waist`: the waist joints that stay
    (names of `WAIST_JOINTS`); the others are deleted, which fixes them at zero, the standing posture. `cameras=False`
    leaves the three cameras out: a `World` adds its own from the robot's spec, under the names its tools use."""
    unknown = set(waist) - set(WAIST_JOINTS)
    if unknown:
        raise ValueError(f"waist joints are {WAIST_JOINTS}, got {sorted(unknown)}")
    path = (root or third_party_dir() / "mujoco_menagerie") / FILE
    s = mujoco.MjSpec.from_file(str(path))
    changes: dict = {"file": FILE, "waist_kept": list(waist), "clearance": clearance}

    for k in list(s.keys):
        s.delete(k)
    lights = list(s.worldbody.lights)
    for light in lights:
        s.delete(light)
    changes["deleted_keyframes"] = ["stand"]
    changes["deleted_lights"] = len(lights)

    # joints that go: legs, the waist joints not kept, the hands; their actuators first
    gone = [f"{side}_{n}_joint" for side in SIDES for n in LEG_JOINTS]
    gone += [j for j in WAIST_JOINTS if j not in waist]
    hand = [f"{side}_hand_{n}_joint" for side in SIDES for n in HAND_JOINTS]
    for a in list(s.actuators):
        if a.target in gone or a.target in hand:
            s.delete(a)
    for name in gone:
        s.delete(s.joint(name))
    changes["deleted_leg_joints"] = [j for j in gone if j not in WAIST_JOINTS]
    changes["deleted_waist_joints"] = [j for j in WAIST_JOINTS if j not in waist]

    # the base: planar joints in place of the free joint, at standing height plus the clearance
    pelvis = s.body("pelvis")
    for j in list(pelvis.joints):
        if j.type == mujoco.mjtJoint.mjJNT_FREE:
            changes["deleted_free_joint"] = j.name
            s.delete(j)
    pelvis.pos = [0.0, 0.0, PELVIS_STANDING + clearance]
    for name, kind, axis in ((BASE_JOINTS[0], mujoco.mjtJoint.mjJNT_SLIDE, [1, 0, 0]), (BASE_JOINTS[1], mujoco.mjtJoint.mjJNT_SLIDE, [0, 1, 0]),
                             (BASE_JOINTS[2], mujoco.mjtJoint.mjJNT_HINGE, [0, 0, 1])):
        # the class the pelvis hands down gives every joint friction and an armature meant for the robot's motors
        pelvis.add_joint(name=name, type=kind, axis=axis, armature=0.0, frictionloss=0.0, damping=0.0)
    for name, kp, kv, f in zip(BASE_JOINTS, BASE_KP, BASE_KV, BASE_FORCE):
        s.add_actuator(name=name, target=name, trntype=mujoco.mjtTrn.mjTRN_JOINT, gaintype=mujoco.mjtGain.mjGAIN_FIXED,
                       biastype=mujoco.mjtBias.mjBIAS_AFFINE, gainprm=[kp] + [0.0] * 9, biasprm=[0.0, -kp, -kv] + [0.0] * 7,
                       forcelimited=True, forcerange=[-f, f])
    changes["base_joints"] = list(BASE_JOINTS)
    changes["base_servo"] = {"kp": list(BASE_KP), "kv": list(BASE_KV), "force_limit": list(BASE_FORCE)}
    changes["pelvis_height"] = PELVIS_STANDING + clearance

    # the hands: three finger chains and the palm per side go, a gripper comes
    changes["deleted_hand_bodies"], changes["deleted_palm_geoms"], changes["grippers"] = [], [], {}
    for side in SIDES:
        for n in HAND_ROOTS:
            body = s.body(f"{side}_hand_{n}_link")
            changes["deleted_hand_bodies"].append(body.name)
            s.delete(body)
        wrist = s.body(f"{side}_wrist_yaw_link")
        for g in list(wrist.geoms):
            if g.meshname == f"{side}_hand_palm_link":
                changes["deleted_palm_geoms"].append(f"{wrist.name}: {g.meshname} (group {g.group})")
                s.delete(g)
        wrist.mass = WRIST_STUB["mass"]
        wrist.ipos = list(WRIST_STUB["pos"])
        wrist.iquat = [1.0, 0.0, 0.0, 0.0]
        wrist.inertia = list(WRIST_STUB["inertia"])
        wrist.explicitinertial = True
        site = wrist.add_site(name=f"{side}_mount", pos=list(MOUNT_POS), quat=list(MOUNT_QUAT), size=[0.002, 0.002, 0.002], group=4)
        prefix = f"{side}_gripper/"
        s.attach(_gripper.spec(gripper), site=site, prefix=prefix)
        if cameras:
            cam = _gripper.wrist_camera(gripper)
            s.body(prefix + "palm").add_camera(name=f"wrist_{side}", pos=cam["pos"], quat=_look_at(cam["pos"], cam["target"], cam["up"]),
                                               fovy=cam["fovy"])
        changes["grippers"][side] = {"prefix": prefix, "on": wrist.name, "mount_pos": list(MOUNT_POS), "mount_quat": list(MOUNT_QUAT)}
    changes["deleted_hand_joints"] = hand
    changes["wrist_link_inertia"] = dict(WRIST_STUB)

    # the head camera; the maker's name
    torso = s.body(HEAD_CAMERA["body"])
    if cameras:
        p = np.array(HEAD_CAMERA["pos"])
        a = math.radians(HEAD_CAMERA["down_deg"])
        torso.add_camera(name="head", pos=list(p), quat=_look_at(p, p + np.array([math.cos(a), 0.0, -math.sin(a)])), fovy=HEAD_CAMERA["fovy"])
    changes["cameras"] = ["head", "wrist_left", "wrist_right"] if cameras else []
    changes["deleted_logo_geoms"] = 0
    if hide_logo:
        for g in list(torso.geoms):
            if g.meshname == "logo_link":
                s.delete(g)
                changes["deleted_logo_geoms"] += 1

    if gravcomp:
        for b in s.bodies:
            if b.name and b.name != "world":
                b.gravcomp = 1.0
    changes["gravcomp"] = gravcomp
    return s, changes


def build(waist: tuple = (), clearance: float = CLEARANCE, hide_logo: bool = True, gravcomp: bool = True, floor: bool = True,
          gripper: _gripper.Dims = _gripper.DIMS, extend=None):
    """The compiled model, standing at the origin on a floor of its own, with the bench's physics options; and the dict
    of what was changed. `extend(spec)` may add things to the world before it is compiled (a counter, a thing to pick up)."""
    s, changes = make_spec(waist, clearance, hide_logo, gravcomp, gripper)
    _gripper.bench_options(s)
    s.visual.global_.offwidth, s.visual.global_.offheight = 1280, 960
    s.visual.headlight.ambient = [0.30, 0.30, 0.30]
    s.visual.headlight.diffuse = [0.35, 0.35, 0.35]
    s.visual.headlight.specular = [0.0, 0.0, 0.0]
    if floor:
        s.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[5, 5, 0.1], rgba=[0.60, 0.58, 0.54, 1])
        s.worldbody.add_light(name="key", pos=[0.6, -1.0, 2.6], dir=[-0.2, 0.4, -1.0], diffuse=[0.45, 0.45, 0.45], specular=[0.05, 0.05, 0.05])
    if extend is not None:
        extend(s)
    m = s.compile()
    changes["counts"] = {"nq": m.nq, "nv": m.nv, "nu": m.nu, "bodies": m.nbody - 1, "joints": m.njnt}
    changes["total_mass"] = round(float(m.body_subtreemass[m.body("pelvis").id]), 4)
    return m, changes


def index(m: mujoco.MjModel, prefix: str = "") -> dict:
    """Where the parts are in a compiled model (names with `prefix` when the body was attached into a world)."""
    def q(names):
        return np.array([int(m.jnt_qposadr[m.joint(prefix + n).id]) for n in names])

    def v(names):
        return np.array([int(m.jnt_dofadr[m.joint(prefix + n).id]) for n in names])

    def act(names):
        return np.array([m.actuator(prefix + n).id for n in names])

    ix: dict = {"base_q": q(BASE_JOINTS), "base_v": v(BASE_JOINTS), "base_act": act(BASE_JOINTS), "pelvis": m.body(prefix + "pelvis").id,
                "arms": {}}
    waist = [n for n in WAIST_JOINTS if mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, prefix + n) >= 0]
    ix["waist"] = waist
    ix["waist_q"], ix["waist_v"], ix["waist_act"] = q(waist), v(waist), act(waist)
    robot = set()
    root = ix["pelvis"]
    for b in range(1, m.nbody):
        k = b
        while k not in (0, root):
            k = int(m.body_parentid[k])
        if k == root:
            robot.add(b)
    ix["bodies"] = frozenset(robot)
    for side in SIDES:
        names = [f"{side}_{n}_joint" for n in ARM_JOINTS]
        g = prefix + f"{side}_gripper/"
        jid = [m.joint(prefix + n).id for n in names]
        fingers = [g + "finger_left", g + "finger_right"]
        palm = m.body(g + "palm").id
        hand = {palm, m.body(g + "finger_left").id, m.body(g + "finger_right").id}
        chain = set(hand)                       # the arm's own bodies, shoulder to fingers
        k = palm
        while m.body(k).name != prefix + "torso_link":
            chain.add(k)
            k = int(m.body_parentid[k])
        ix["arms"][side] = {
            "joints": names, "q": q(names), "v": v(names), "act": act(names), "range": np.array([m.jnt_range[j] for j in jid]),
            "grip_act": m.actuator(g + "grip").id, "finger_q": np.array([int(m.jnt_qposadr[m.joint(n).id]) for n in fingers]),
            "pinch": m.site(g + "pinch").id, "palm": palm, "hand_bodies": frozenset(hand), "bodies": frozenset(chain),
            "pads": {"left": m.geom(g + "pad_left").id, "right": m.geom(g + "pad_right").id},
            "camera": f"{prefix}wrist_{side}", "prefix": g,
        }
    return ix


# The file's own standing posture of the arms (its `stand` keyframe): upper arms down, forearms bent forward.
STAND = {"left": (0.2, 0.2, 0.0, 1.28, 0.0, 0.0, 0.0), "right": (0.2, -0.2, 0.0, 1.28, 0.0, 0.0, 0.0)}


def mirror(q) -> tuple:
    """A left arm's posture as the right arm's (and back): roll and yaw joints change sign, pitch joints do not."""
    sign = (1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0)
    return tuple(float(s) * float(v) for s, v in zip(sign, q))


def set_posture(m: mujoco.MjModel, d: mujoco.MjData, ix: dict, left=None, right=None, base=None, waist=None, ctrl: bool = True) -> None:
    """Put the arms (and the base, and the kept waist joints) where asked and, with `ctrl`, the servo targets too."""
    for side, q in (("left", left), ("right", right)):
        if q is not None:
            a = ix["arms"][side]
            d.qpos[a["q"]] = q
            if ctrl:
                d.ctrl[a["act"]] = q
    if base is not None:
        d.qpos[ix["base_q"]] = base
        if ctrl:
            d.ctrl[ix["base_act"]] = base
    if waist is not None:
        d.qpos[ix["waist_q"]] = waist
        if ctrl:
            d.ctrl[ix["waist_act"]] = waist


def trapezoid(t: float, distance: float, vmax: float, amax: float) -> float:
    """Where a move of `distance` (m or rad) is after `t` seconds: accelerate at `amax`, cruise at `vmax`, brake."""
    sign, distance = (1.0 if distance >= 0 else -1.0), abs(distance)
    ta = vmax / amax
    da = 0.5 * amax * ta * ta
    if 2.0 * da > distance:
        ta = math.sqrt(distance / amax)
        da, tc = distance / 2.0, 0.0
    else:
        tc = (distance - 2.0 * da) / vmax
    if t <= 0.0:
        return 0.0
    if t < ta:
        return sign * 0.5 * amax * t * t
    if t < ta + tc:
        return sign * (da + amax * ta * (t - ta))
    if t < 2.0 * ta + tc:
        r = 2.0 * ta + tc - t
        return sign * (distance - 0.5 * amax * r * r)
    return sign * distance


def drive_trial(m: mujoco.MjModel, ix: dict, left=None, right=None, stand: float = 5.0, distance: float = 1.0, turn: float = math.pi / 2.0,
                speed: tuple = (0.5, 1.0), accel: tuple = (1.0, 2.0)) -> dict:
    """Stand for `stand` seconds, drive `distance` forward, turn by `turn`, stand one second; the arms held where they
    are put (default: the file's standing posture). Returns what moved that should not have, and the base's forces."""
    d = mujoco.MjData(m)
    set_posture(m, d, ix, left=STAND["left"] if left is None else left, right=STAND["right"] if right is None else right)
    mujoco.mj_forward(m, d)
    dt = m.opt.timestep
    floor = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    held = np.concatenate([ix["arms"][s]["q"] for s in SIDES] + [ix["waist_q"]]).astype(int)
    held_ref = d.qpos[held].copy()
    pelvis = ix["pelvis"]
    z0, up0 = float(d.xpos[pelvis][2]), d.xmat[pelvis].reshape(3, 3)[:, 2].copy()
    t_drive = 2.0 * speed[0] / accel[0] + max(0.0, abs(distance) - speed[0] ** 2 / accel[0]) / speed[0] + 0.7
    t_turn = 2.0 * speed[1] / accel[1] + max(0.0, abs(turn) - speed[1] ** 2 / accel[1]) / speed[1] + 0.7
    out: dict = {}
    for phase, dur in (("stand", stand), ("drive", t_drive), ("turn", t_turn), ("rest", 1.0)):
        n = int(round(dur / dt))
        lag = np.zeros(3)
        force = np.zeros(3)
        arm_err = tilt = dz = 0.0
        touch = 0
        start = d.qpos[ix["base_q"]].copy()
        for k in range(n):
            t = (k + 1) * dt
            x = trapezoid(t, distance, *[speed[0], accel[0]]) if phase == "drive" else (distance if phase in ("turn", "rest") else 0.0)
            yaw = trapezoid(t, turn, *[speed[1], accel[1]]) if phase == "turn" else (turn if phase == "rest" else 0.0)
            target = np.array([x, 0.0, yaw])
            d.ctrl[ix["base_act"]] = target
            mujoco.mj_step(m, d)
            lag = np.maximum(lag, np.abs(d.qpos[ix["base_q"]] - target))
            force = np.maximum(force, np.abs(d.actuator_force[ix["base_act"]]))
            arm_err = max(arm_err, float(np.max(np.abs(d.qpos[held] - held_ref))))
            tilt = max(tilt, float(np.degrees(np.arccos(min(1.0, float(d.xmat[pelvis].reshape(3, 3)[:, 2] @ up0))))))
            dz = max(dz, abs(float(d.xpos[pelvis][2]) - z0))
            if floor >= 0 and any(floor in (int(c.geom1), int(c.geom2)) for c in d.contact[:d.ncon]):
                touch += 1
        out[phase] = {"seconds": round(dur, 2), "base_moved": [float(v) for v in np.round(d.qpos[ix["base_q"]] - start, 6)],
                      "base_lag_max": [float(v) for v in np.round(lag, 5)], "base_force_max": [float(v) for v in np.round(force, 1)],
                      "held_joint_error_max_rad": round(arm_err, 5), "pelvis_tilt_max_deg": round(tilt, 6), "pelvis_height_change_max_m": round(dz, 9),
                      "ticks_touching_floor": touch}
    out["end_base"] = [float(v) for v in np.round(d.qpos[ix["base_q"]], 5)]
    out["finite"] = bool(np.all(np.isfinite(d.qpos)))
    return out
