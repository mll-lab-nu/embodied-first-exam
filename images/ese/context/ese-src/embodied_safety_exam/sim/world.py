"""The bench world: a table, a robot arm with its hand standing on it (`robots.py`: a UR5e or a Franka FR3 with a Robotiq
2F-85), three cameras and the props of a scene.

Frame of the world ("bench frame"): origin on the table surface at the centre of the table, `+x` to the right and
`+y` to the back as seen from the `front` camera, `+z` up. Metres, radians, seconds.

A scene may be a room instead of a table (`scene["room"]`, see `normalise_room`): a floor, walls with doorways, a
fixed camera `room` high in a corner. Its frame has the origin on the floor in the middle of the room. A robot with a
driving base (`RobotSpec.base`: the TidyBot) stands on that floor; its control row begins with the three targets of
the base, and `World.arm()` is the view of its arm that the skills are given (docs/MOTION.md 12).

Time advances only in `World.step(row)`: one control row holds the arm's joint position targets and one gripper target
and is applied for one control period. Besides rows, a few calls write to the state, and each is logged with its tick
so that a record replays exactly (`ops`): `attach` / `detach` (what the hand holds), `set_mocap` (scripted bodies),
`set_ctrl` (actuators inside props), `fasten` / `unfasten`, `let_through`, `set_look`; since 0.5.1 `set_joint` and
`push` (scripted movers, `embodied_safety_exam.sim.movers`).
Everything read from the world (`observe`, `privileged`, the kinematics used by the skills) is computed on a scratch
copy of the simulation data, never on the live data, so reading does not change the trajectory. See `docs/MOTION.md`.
"""
from __future__ import annotations

import atexit
import contextlib
import copy
import hashlib
import json
import math
import os
import weakref
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from embodied_safety_exam.core import digest  # noqa: E402

from . import props as _props  # noqa: E402
from . import robots as _robots  # noqa: E402
from . import geom as _geom  # noqa: E402
from . import tf  # noqa: E402

PHYSICS_DT = 0.002          # s; see docs/MOTION.md for why
SUBSTEPS = 10
CONTROL_DT = PHYSICS_DT * SUBSTEPS   # 0.02 s: 50 control rows per simulated second
# For measurement only (0.5.1, docs/CONTRACTS.md "Timestep robustness"): `ESE_PHYSICS_DT=0.001` builds the next
# worlds with that physics step and as many substeps as keep the control period at 20 ms. Off by default; a world built
# with it is not the benchmark's world (every state hash differs), and a service, a task or an admission never sets it.
PHYSICS_DT_ENV = "ESE_PHYSICS_DT"


def physics_dt() -> tuple[float, int]:
    """(physics step, substeps per control row) of a world built now: the default, or the measurement override."""
    raw = os.environ.get(PHYSICS_DT_ENV, "").strip()
    if not raw:
        return PHYSICS_DT, SUBSTEPS
    dt = float(raw)
    n = int(round(CONTROL_DT / dt)) if dt > 0 else 0
    if n < 1 or abs(n * dt - CONTROL_DT) > 1e-12:
        raise ValueError(f"{PHYSICS_DT_ENV}={raw!r}: the physics step must divide the control period ({CONTROL_DT} s)")
    return CONTROL_DT / n, n
# The default robot's numbers, kept under their old names (a row of the UR5e has seven numbers). A world's own are
# `world.row_size`, `world.spec`.
ROW_SIZE = _robots.get(None).n + 1
GRIPPER_MAX = _robots.get(None).gripper_max     # rad: driver joint angle of the closed gripper (0 = open)
# Two named postures per robot (`robots.py`). `ready`: the tool straight down over the front half of the work area;
# grasps, presses and views are planned from here. `rest` (the home posture, where an episode starts and `home`
# returns to): the arm upright at the back of the table with the hand high and tipped forward, which hides none of
# the work area from the `front` and `top` cameras and lets the wrist camera overlook the table from the robot's
# side (docs/MOTION.md).
READY = _robots.get(None).ready
REST = _robots.get(None).home
HOME = REST

DEFAULT_SCENE = {
    # `type`: a robot of `robots.py`. Where it stands (`pos`, `yaw_deg`; default: on the table, 0.15 m from its back
    # edge) and its `home` and `ready` postures (joint values, or the names `rest` / `ready`) default to the robot's own.
    "robot": {"type": _robots.DEFAULT},
    "table": {"size": [1.40, 0.90], "height": 0.75},
    "objects": [],
    "cameras": {},              # extra or replaced cameras: {name: {"pos", "target", "fovy", "up"}}
    "image_size": [640, 480],
    # Whether the hand keeps account of what it holds (`held`): a thing it closed on is registered by `attach` and let go
    # of by `detach` or when nothing of the hand touches it any longer. False: nothing is registered, and what the hand
    # holds is read from the finger pads alone (families that grade the grip itself).
    "assist": True,
    # How a held thing is held. "contact" (the default since 0.5.0): by the fingers' contact forces and friction alone,
    # as a real gripper holds it; it slips or falls out when they do not suffice. "weld": the grasp assist of 0.0.1 to
    # 0.4.x, a weld between the hand and the thing (with its weight taken off); kept only to measure against.
    "grasp": "contact",
    # Whether the actions plan around what stands on the table (docs/MOTION.md 4). False: a carried thing travels
    # straight across with its underside 14 cm above where it is going, whatever stands in between, as the actions
    # did before they were hardened. For families whose hazard is what a careless carry meets on the way.
    "avoid": True,
    "gravity": 9.81,            # m/s^2, downwards
    "sensors": [],              # see embodied_safety_exam/sim/sensors.py
    # pairs [a, b]: `fasten(a, b)` can fix the free object a onto b (a cap screwed onto a bottle, a blade stuck in a
    # melon, a plug seated in a socket); a may be paired with several b
    "fasteners": [],
    # pairs [cap, bottle] (0.5.0): besides the weld of `fasteners` (which the pair must also be listed in), the cap can
    # be held on the bottle's axis and left free to turn about it (`hinge`): a screw cap that a hand turns while the
    # other hand holds the bottle still (`embodied_safety_exam.hazard.state.ScrewCap` decides when)
    "screws": [],
}


def third_party_dir() -> Path:
    from ..assets.paths import third_party_dir as asset_third_party_dir

    return asset_third_party_dir()


class RowRejected(ValueError):
    """A control row that was not applied (wrong shape, not finite, or too far from where the arm is)."""


class SimulationUnstable(RuntimeError):
    """The physics diverged. The world must not be used further."""


def _look_at(pos, target, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Quaternion of a MuJoCo camera (looks along its -z, +y up) at `pos` looking at `target`."""
    f = tf.unit(np.asarray(target, dtype=np.float64) - np.asarray(pos, dtype=np.float64))
    right = tf.unit(np.cross(f, np.asarray(up, dtype=np.float64)))
    return tf.quat_from_axes(x=right, y=np.cross(right, f))


GRASP_MODES = ("contact", "weld")
IMPRATIO = 100.0
# A held thing that no part of the hand has touched for this many control periods has been lost (it slipped out or fell):
# the hand no longer holds it (`World.lost`). 0.1 s: a contact that flickers while the fingers settle does not count.
LOST_TICKS = 5
# ... and one whose point that was at the pinch point when it was taken is now this far from it has slipped out of the
# grip, though it may still touch a finger (a can that slid down between the fingers onto the table). A thing that
# only turns about the pinch (a bucket held by its rim) has not.
LOST_SLIP = 0.03


ROOM_DEFAULTS = {"height": 2.60, "thickness": 0.10, "outer": True, "walls": [], "doors": [], "cameras": "room", "camera": None}
ROOM_CAMERAS = ("room", "onboard")      # the camera condition: with the fixed camera `room`, or with the robot's own only


def normalise_room(room: dict) -> dict:
    """`scene["room"]`: {"size": [x, y]} is a room of that size about the origin, its floor at z = 0, with four walls
    (`"outer": False` leaves them out). `walls`: further walls (inner walls, the walls of other rooms), each
    {"from": [x, y], "to": [x, y]} along its centre line, with `height` and `thickness` if they differ. `doors`:
    doorways {"at": [x, y], "width", "height"} cut through whichever walls run through that point (the leaf and its
    frame are an ordinary object, `room_door`). `camera`: the fixed
    camera `room` ({"pos", "target", "fovy"}; default: high in the corner at +x, +y, looking across the floor).
    `cameras`: the camera condition, `room` (the fixed camera, the robot's head and wrist) or `onboard` (head and
    wrist only); the fixed camera is built either way, so that the two conditions are the same physics."""
    out = copy.deepcopy(ROOM_DEFAULTS)
    unknown = set(room) - set(out) - {"size"}
    if unknown:
        raise ValueError(f"unknown room keys: {sorted(unknown)}")
    out.update(copy.deepcopy(room))
    if "size" not in room or len(room["size"]) != 2:
        raise ValueError("a room has a `size`: [x, y] in metres")
    out["size"] = [float(v) for v in room["size"]]
    if out["cameras"] not in ROOM_CAMERAS:
        raise ValueError(f"the camera condition of a room is one of {ROOM_CAMERAS}, got {out['cameras']!r}")
    sx, sy = out["size"]
    if out["camera"] is None:
        out["camera"] = {"pos": [sx / 2.0 - 0.12, sy / 2.0 - 0.12, min(out["height"] - 0.25, 2.35)],
                         "target": [-0.10 * sx, -0.12 * sy, 0.0], "fovy": 72.0}
    return out


def room_walls(room: dict) -> list[dict]:
    """The boxes that make up the walls of a (normalised) room: [{"name", "pos", "half", "yaw"}]. A doorway leaves a
    gap from the floor to its height and a lintel above."""
    t0, h0 = float(room["thickness"]), float(room["height"])
    sx, sy = room["size"]
    walls = []
    if room["outer"]:                       # centre lines half a thickness outside the room: its inner faces are at +-size / 2
        ox, oy = sx / 2.0 + t0 / 2.0, sy / 2.0 + t0 / 2.0
        walls += [{"from": [-ox, -oy], "to": [ox, -oy]}, {"from": [ox, -oy], "to": [ox, oy]},
                  {"from": [ox, oy], "to": [-ox, oy]}, {"from": [-ox, oy], "to": [-ox, -oy]}]
    walls += list(room["walls"])
    boxes = []
    for i, w in enumerate(walls):
        a, b = np.asarray(w["from"], dtype=np.float64), np.asarray(w["to"], dtype=np.float64)
        t, h = float(w.get("thickness", t0)), float(w.get("height", h0))
        length = float(np.linalg.norm(b - a))
        if length < 1e-6:
            raise ValueError(f"wall {i} has no length")
        along = (b - a) / length
        yaw = math.atan2(along[1], along[0])
        gaps = []
        for d in room["doors"]:
            at = np.asarray(d["at"], dtype=np.float64)
            s_ = float((at - a) @ along)
            off = float(np.linalg.norm(at - (a + along * s_)))
            if off <= t / 2.0 + 0.05 and -1e-6 <= s_ <= length + 1e-6:
                half = float(d.get("width", 0.90)) / 2.0
                gaps.append((max(s_ - half, -t / 2.0), min(s_ + half, length + t / 2.0), float(d.get("height", 2.03))))
        gaps.sort()
        at_s, k = -t / 2.0, 0                    # a wall reaches half a thickness past each end, so that corners close

        def box(s0, s1, z0, z1, tag):
            if s1 - s0 > 1e-6 and z1 - z0 > 1e-6:
                c = a + along * ((s0 + s1) / 2.0)
                boxes.append({"name": f"wall_{i}_{tag}", "pos": [float(c[0]), float(c[1]), (z0 + z1) / 2.0],
                              "half": [(s1 - s0) / 2.0, t / 2.0, (z1 - z0) / 2.0], "yaw": yaw})

        for g0, g1, gh in gaps:
            box(at_s, g0, 0.0, h, str(k))
            box(g0, g1, gh, h, f"l{k}")
            # the frame of the doorway, so that it shows as one: two jambs inside the ends of the wall and a head over
            # the opening, a centimetre proud of both faces. Drawn only; they take nothing from the opening.
            for tag, s0, s1, z0, z1 in ((f"t{k}a", g0 - 0.05, g0, 0.0, gh), (f"t{k}b", g1, g1 + 0.05, 0.0, gh), (f"t{k}c", g0 - 0.05, g1 + 0.05, gh, gh + 0.06)):
                c = a + along * ((s0 + s1) / 2.0)
                boxes.append({"name": f"wall_{i}_{tag}", "pos": [float(c[0]), float(c[1]), (z0 + z1) / 2.0],
                              "half": [(s1 - s0) / 2.0, t / 2.0 + 0.012, (z1 - z0) / 2.0], "yaw": yaw, "trim": True})
            at_s, k = g1, k + 1
        box(at_s, length + t / 2.0, 0.0, h, str(k))
    return boxes


def _wrap_angle(a: float) -> float:
    return (float(a) + math.pi) % (2.0 * math.pi) - math.pi


def static_owner(name: str) -> str:
    """Who a shape of the world itself belongs to, by its name: `table` (its legs too), `floor`, `pedestal`, `wall`."""
    return "wall" if name.startswith("wall_") else name.split("_leg")[0]


def normalise_scene(scene: dict | None) -> dict:
    """Fill in the defaults and return plain JSON data (what goes into a record)."""
    s = copy.deepcopy(DEFAULT_SCENE)
    scene = scene or {}
    if "room" in scene:                     # a room instead of the table: one or the other
        if "table" in scene:
            raise ValueError("a scene has a `table` or a `room`, not both")
        del s["table"]
        s["room"] = normalise_room(scene["room"])
    for key in ("robot", "table"):
        if key in s:
            s[key].update(copy.deepcopy(scene.get(key, {})))
    spec = _robots.get(s["robot"].get("type"))
    postures = {"rest": spec.home, "ready": spec.ready}
    for key, default in (("pos", list(spec.base_pos)), ("yaw_deg", spec.base_yaw_deg), ("home", list(spec.home)), ("ready", list(spec.ready))):
        s["robot"].setdefault(key, default)
    for key in ("home", "ready"):
        if isinstance(s["robot"][key], str):
            if s["robot"][key] not in postures:
                raise ValueError(f"unknown posture {s['robot'][key]!r}; named postures: {sorted(postures)}")
            s["robot"][key] = list(postures[s["robot"][key]])
        if len(s["robot"][key]) != spec.n:
            raise ValueError(f"the {key} posture of {spec.type} has {spec.n} joint values, got {len(s['robot'][key])}")
    if spec.arms and "arm_prefixes" not in spec.extra:      # several arms, each standing somewhere: where; `home` and `ready` are one arm's (mirrored for a mirrored arm)
        given = s["robot"].get("arms") or {}
        if set(given) - {a[0] for a in spec.arms}:
            raise ValueError(f"{spec.type} has the arms {[a[0] for a in spec.arms]}, got {sorted(given)}")
        s["robot"]["arms"] = {name: {"pos": list(given.get(name, {}).get("pos", pos)), "yaw_deg": float(given.get(name, {}).get("yaw_deg", yaw))}
                              for name, pos, yaw, _ in spec.arms}
    s["objects"] = copy.deepcopy(list(scene.get("objects", [])))
    s["cameras"] = copy.deepcopy(dict(scene.get("cameras", {})))
    s["image_size"] = [int(v) for v in scene.get("image_size", s["image_size"])]
    s["assist"] = bool(scene.get("assist", True))
    s["grasp"] = str(scene.get("grasp", "contact"))
    if s["grasp"] not in GRASP_MODES:
        raise ValueError(f"`grasp` is one of {GRASP_MODES}, got {s['grasp']!r}")
    s["avoid"] = bool(scene.get("avoid", True))
    s["sensors"] = copy.deepcopy(list(scene.get("sensors", [])))
    s["fasteners"] = [[str(a), str(b)] for a, b in scene.get("fasteners", [])]
    s["screws"] = [[str(a), str(b)] for a, b in scene.get("screws", [])]
    for pair in s["screws"]:
        if pair not in s["fasteners"]:
            s["fasteners"].append(list(pair))
    s["gravity"] = float(scene.get("gravity", s["gravity"]))
    if not 0.0 <= s["gravity"] <= 100.0:
        raise ValueError("gravity is a downward acceleration in m/s^2, between 0 and 100")
    sensor_names = [x.get("name") for x in s["sensors"]]
    if len(set(sensor_names)) != len(sensor_names):
        raise ValueError("sensor names must be unique")
    unknown = set(scene) - set(s)
    if unknown:
        raise ValueError(f"unknown scene keys: {sorted(unknown)}")
    names = [o["name"] for o in s["objects"]]
    if len(set(names)) != len(names):
        raise ValueError("object names must be unique")
    for n in names:
        if "/" in n or n in ("robot", "table", "floor", "pedestal", "world", "wall"):
            raise ValueError(f"bad object name {n!r}")
    return json.loads(json.dumps(s))


_SITE_CACHE: dict[str, dict[str, tf.Pose]] = {}


def _prop_sites(prop: _props.Prop) -> dict[str, tf.Pose]:
    """Poses of a prop's sites in the prop frame (compiled once per distinct prop)."""
    key = prop.path or hashlib.sha256(prop.xml.encode()).hexdigest()
    if key not in _SITE_CACHE:
        spec = mujoco.MjSpec.from_file(prop.path) if prop.path else mujoco.MjSpec.from_string(prop.xml)
        m = spec.compile()
        d = mujoco.MjData(m)
        mujoco.mj_kinematics(m, d)
        out = {}
        for i in range(m.nsite):
            out[m.site(i).name] = (d.site_xpos[i].copy(), tf.mat_to_quat(d.site_xmat[i].reshape(3, 3)))
        _SITE_CACHE[key] = out
    return _SITE_CACHE[key]


def _mounts(scene: dict) -> list[dict]:
    """The arms of a (normalised) scene's robot, in the order of the control row: for each its name ("" when the
    robot has one arm), its spec, the prefixes of its parts' names, where it stands and its postures."""
    r = scene["robot"]
    spec = _robots.get(r["type"])
    if not spec.arms:
        return [{"name": "", "spec": spec, "arm_prefix": spec.arm_prefix, "hand_prefix": spec.hand_prefix, "pos": r["pos"],
                 "yaw_deg": r["yaw_deg"], "home": r["home"], "ready": r["ready"], "model_prefix": spec.arm_prefix, "mirrored": False}]
    # Every arm its own copy of the model under "<name>/", standing where the scene puts it; or all arms part of one
    # model (`extra["arm_prefixes"]`), which stands where the scene puts the robot.
    one = spec.extra.get("arm_prefixes")
    out = []
    for name, _, _, mirrored in spec.arms:
        sp = spec.mirrored() if mirrored else spec
        sign = spec.extra["mirror"] if mirrored else (1.0,) * spec.n
        ap, hp = one[name] if one else (name + "/", name + "/")
        at = r if one else r["arms"][name]
        # the scene's postures are those of an arm that is not mirrored; a scene that leaves them alone gets the spec's
        out.append({"name": name, "spec": sp, "arm_prefix": ap, "hand_prefix": hp,
                    "pos": at["pos"], "yaw_deg": at["yaw_deg"],
                    "home": [float(a) * float(b) for a, b in zip(sign, r["home"])],
                    "ready": [float(a) * float(b) for a, b in zip(sign, r["ready"])],
                    "model_prefix": spec.extra["model_prefix"] if one else ap, "mirrored": bool(mirrored)})
    return out


def _robot_model(rs) -> "mujoco.MjSpec":
    """The model of a robot (of one arm of it, where every arm is a copy): read from the vendored file, or made by the
    function the spec names (`extra["build"]`: "module:function", called with `extra["build_args"]`)."""
    made = rs.extra.get("build")
    if not made:
        return mujoco.MjSpec.from_file(str(third_party_dir() / "mujoco_menagerie" / rs.arm_file))
    import importlib
    module, _, function = made.partition(":")
    out = getattr(importlib.import_module(module), function)(**dict(rs.extra.get("build_args", {})))
    return out[0] if isinstance(out, tuple) else out


def _subtree(m: "mujoco.MjModel", root: int) -> list:
    """A body and everything that hangs on it (a body's parent comes before it)."""
    out = {int(root)}
    for b in range(int(root) + 1, m.nbody):
        if int(m.body_parentid[b]) in out:
            out.add(b)
    return sorted(out)


def row_size(scene: dict) -> int:
    """How many numbers a control row of this (normalised) scene's robot has: the joint targets of every arm, then one
    gripper target per arm."""
    spec = _robots.get(scene["robot"]["type"])
    if spec.extra.get("controller") == "groot_wbc":     # the walking G1: a `whole_body` command (`WHOLE_BODY_LAYOUT`)
        return len(WHOLE_BODY_HEAD) + sum(m["spec"].n + 1 for m in _mounts(scene))
    return sum(m["spec"].n + 1 for m in _mounts(scene)) + len(spec.base.get("joints", ()))


# The walking G1's control row, BiGym 2.0's command at 50 Hz (`embodied_safety_exam.sim.wbc`): the walking velocity ahead and to
# the left (m/s), the pelvis height (m), the turning rate (rad/s, + to the left), the torso pitch (rad, + leans
# forward), the 14 arm joint targets (left arm first, rad) and the two grippers (0 open .. 1 closed).
WHOLE_BODY_HEAD = ("vx", "vy", "height", "wz", "pitch")


_LIVE: "weakref.WeakSet" = weakref.WeakSet()
# sideways directions for the second ray of `World.raycast`: generic, so that it lies in no plane of symmetry of a shape
_RAY_SIDE = tf.unit(np.array([0.5377, 0.3091, 0.7844]))
_RAY_SIDE_ALT = tf.unit(np.array([-0.2113, 0.8650, 0.4551]))
_RAY_SKIP_GROUP = 5         # a geom group no ray test includes: where a geom a ray has to look past is put meanwhile


@atexit.register
def _close_all() -> None:          # renderers must be closed before the interpreter tears the GL context down
    for w in list(_LIVE):
        try:
            w.close()
        except Exception:
            pass


class World:
    static_owner = staticmethod(static_owner)
    # The most the pinch point may move (m/s) while a skill runs; None: as fast as the skill moves it. Set for the length
    # of one tool call (`speed="slow"`, `episode.HAND_SLOW`) and read by `skills._track`; not part of the state.
    hand_speed_limit: float | None = None

    def __init__(self, scene: dict | None = None, image_size: tuple[int, int] | None = None,
                 max_target_lead: float | None = 1.0, *, asset_profile: str | None = None):
        """`scene`: {"robot": {"pos", "yaw_deg", "home"}, "table": {...}, "objects": [{"name", "kind", "params",
        "pos", "quat" | "yaw_deg"} | {"name", "kind", "params", "at": "<object>/<site>"}]}.

        `max_target_lead`: a row whose arm target is further than this (rad) from the measured joint position is
        rejected instead of applied (None switches the check off).
        """
        from embodied_safety_exam.assets import catalog as _catalog
        self.asset_profile = _catalog.asset_profile(asset_profile)
        self.visual_assets = _catalog.visual_provenance(self.asset_profile)
        self.scene = normalise_scene(scene)
        self.physics_dt, self.substeps = physics_dt()     # (0.002, 10) unless the measurement override is set
        self.spec = _robots.get(self.scene["robot"]["type"])
        # One entry per arm. With one arm (every robot but `yam_bimanual`) the world itself has the single-arm interface
        # the skills use; with several, `arm(name)` returns a view that has it (`Arm`, below), and the world's own
        # joint arrays are the arms' one after the other, as in the control row.
        self._mounts = _mounts(self.scene)
        self.arm_names = tuple(m["name"] for m in self._mounts) if len(self._mounts) > 1 else ()
        # A base that drives (`RobotSpec.base`): its three targets come first in the control row, and the skills are
        # given `arm()`, a view with a row of the arm alone, as on a robot with several arms.
        self.base = dict(self.spec.base) if self.spec.base else None
        self._nb = len(self.base["joints"]) if self.base else 0
        self.row_size = row_size(self.scene)
        self.room = self.scene.get("room")
        self.wrist_camera = "wrist" if not self.arm_names else f"wrist_{self.arm_names[0]}"
        fixed = ("front", "top") if self.room is None else (("room",) if self.room["cameras"] == "room" else ())
        # 0.5.1, the TidyBot under the control interface (`scene["robot"]["onboard"] == "own"`): the robot's own two
        # cameras as its model has them (TidyBot++: `base` on the base, `wrist` on the Gen3's bracelet link, KinDER's
        # robot_base and robot_wrist), no mast and no camera of ours
        self.own_cameras = bool(self.base) and self.scene["robot"].get("onboard") == "own"
        if self.own_cameras:
            self.cameras = fixed + ("base", "wrist")
        else:
            self.cameras = fixed + (("head",) if self.base else ()) + (("wrist",) if not self.arm_names else tuple(f"wrist_{a}" for a in self.arm_names))
        self.acting = self._mounts[0]["name"]      # the arm that was last given a row of its own (see `Arm.step`)
        self._held_by: dict[str, str | None] = {m["name"]: None for m in self._mounts}
        self._arms: dict[str, "Arm"] = {}
        self.lead = self.spec.extra.get("lead", self.spec.lead)     # s: kv / kp of the arm servos (one number, or one per joint)
        if not isinstance(self.lead, float):
            self.lead = np.array(self.lead, dtype=np.float64)
        image_size = image_size or self.scene["image_size"]
        self.image_size = (int(image_size[0]), int(image_size[1]))
        self.assist = bool(self.scene.get("assist", True))
        self.grasp = self.scene["grasp"]
        self._untouched: dict[str, int] = {m["name"]: 0 for m in self._mounts}     # control periods a held thing went untouched
        self._held_at: dict[str, np.ndarray] = {}     # the point of each held thing (its own frame) that was at the pinch point
        self.lost: list[list] = []            # [tick, arm, object]: a held thing the hand lost (slipped out, fell)
        self.avoid = bool(self.scene.get("avoid", True))
        self.looks: dict[str, list] = {}      # geom name -> rgba set by the hazard layer (a picture, not physics)
        self.max_target_lead = max_target_lead
        self.objects: dict[str, dict] = {}
        self.model = self._build()
        # physics steps per control row: ten of 2 ms; the walking G1's physics has steps of 1 ms, twenty to a row
        self.physics_dt = float(self.model.opt.timestep)
        self.substeps = int(round(CONTROL_DT / self.physics_dt))
        self.data = mujoco.MjData(self.model)
        self._scratch = mujoco.MjData(self.model)
        self._scratch_tick = -1
        self._renderer = None
        self._ik = None
        self.sensors: dict = {}
        self._sensor_list: list = []
        self._index()
        self._rows: list[np.ndarray] = []
        self._ops: list[list] = []            # what was done to the world between rows: [tick, name, arguments...]
        self.tick = 0
        # start: arm at home, gripper open, targets equal to the positions
        self.home = np.array(self.scene["robot"]["home"], dtype=np.float64)
        self.ready = np.array(self.scene["robot"]["ready"], dtype=np.float64)
        self.ready_alt = np.array(self.spec.ready_alt, dtype=np.float64) if self.spec.ready_alt else None
        if self.arm_names:
            self.data.qpos[self._arm_qadr] = np.concatenate([np.array(m["home"], dtype=np.float64) for m in self._mounts])
        else:
            self.data.qpos[self._arm_qadr] = self.home
        if self.base:                                   # the base stands where the scene puts the robot
            r = self.scene["robot"]
            self.data.qpos[self._base_qadr] = [float(r["pos"][0]), float(r["pos"][1]), math.radians(float(r["yaw_deg"]))]
        for o in self.scene["objects"]:                 # actuators inside props hold a fixed target
            for act, value in sorted(o.get("ctrl", {}).items()):
                try:
                    a = self.model.actuator(f"{o['name']}/{act}")
                except KeyError:
                    raise KeyError(f"object {o['name']!r} has no actuator {act!r}") from None
                self.data.ctrl[a.id] = float(value)
        for o in self.scene["objects"]:                 # joints inside props may start away from zero
            for joint, value in sorted(o.get("joints", {}).items()):
                try:
                    j = self.model.joint(f"{o['name']}/{joint}")
                except KeyError:
                    raise KeyError(f"object {o['name']!r} has no joint {joint!r}") from None
                self.data.qpos[int(j.qposadr[0])] = float(value)
        for ix in self._ix.values():                    # fingers that are not open at zero start open
            if ix["_drv_map"] is not None:
                self.data.qpos[ix["_drv_qadr"]] = -ix["_drv_map"][:, 1] / ix["_drv_map"][:, 0]
        from .motion import Limits
        self.limits = Limits(np.array(self.spec.vel_limits, dtype=np.float64), np.array(self.spec.acc_limits, dtype=np.float64))
        if self.arm_names:
            self.target = np.concatenate([self.data.qpos[self._base_qadr] if self.base else [], self.data.qpos[self._arm_qadr], np.zeros(len(self._mounts))])
        elif self.base:
            self.target = np.concatenate([self.data.qpos[self._base_qadr], self.home, [0.0]])
        else:
            self.target = np.concatenate([self.home, [0.0]])
        self.wbc = None                                 # the walking G1's controller (`wbc.Controller`)
        self.fell_at: int | None = None                 # the tick at which the walking G1 was first found fallen
        if self.spec.extra.get("controller") == "groot_wbc":
            self._start_whole_body()
        else:
            self._apply(self.target)
        for spec in self.scene["sensors"]:
            self.add_sensor(spec)
        _LIVE.add(self)

    # ---- the walking G1 (`robots.G1_WBC`, docs/MOTION.md 14) -----------------------------------------------------------
    def _start_whole_body(self) -> None:
        """BiGym 2.0's reset of the G1 where the scene puts it: the pelvis 0.74 m up, the legs at the controller's
        default angles, the arms at the home posture, the fingers open; then `wbc.WARMUP_STEPS` control steps of
        standing still (BiGym's warm-up), which are not rows of the record. The clock starts at zero after them."""
        from . import wbc as _wbc
        from .bodies import g1_wbc as _g1
        m, d = self.model, self.data
        pre = self._mounts[0]["model_prefix"]
        self.wbc = _wbc.Controller(m, pre)
        self._wbc_arm_ctrl = np.array([m.actuator(pre + j).id for j in _g1.ARM_JOINTS], dtype=np.int64)
        self._wbc_fingers = {s_: [(m.actuator(pre + j).id, int(m.jnt_qposadr[m.joint(pre + j).id])) for j in _g1.FINGER_JOINTS[s_]]
                             for s_ in _g1.SIDES}
        self._finger_slew: dict[int, float] = {}
        import collections
        self._walk_track = collections.deque(maxlen=self.WALK_WINDOW + 1)     # (tick, base pose): the mean speed
        z = int(m.jnt_qposadr[m.joint(pre + "pelvis_z").id])
        d.qpos[z] = _wbc.INIT_PELVIS_Z + 0.01
        mujoco.mj_forward(m, d)
        d.qpos[z] = _wbc.INIT_PELVIS_Z
        for i, j in enumerate(_g1.LOWER_JOINTS):
            d.qpos[int(m.jnt_qposadr[m.joint(pre + j).id])] = float(_wbc.DEFAULT_ANGLES[i])
            d.ctrl[m.actuator(pre + j).id] = float(_wbc.DEFAULT_ANGLES[i])
        mujoco.mj_forward(m, d)
        home = np.concatenate([np.array(mt["home"], dtype=np.float64) for mt in self._mounts])
        self.target = np.concatenate([[0.0, 0.0, _wbc.INIT_PELVIS_Z, 0.0, 0.0], home, [0.0, 0.0]])
        for _ in range(_wbc.WARMUP_STEPS):
            self._whole_body_step(self.target)
        d.time = 0.0
        self.tick = 0
        self._walk_track.clear()
        self._walk_track.append((0, d.qpos[self._base_qadr].copy()))

    def _whole_body_step(self, row: np.ndarray) -> None:
        """One control step of the walking G1 (BiGym's order): the command latched, the policy run on the state as it
        is, the 15 targets of the legs and the waist, the 14 of the arms and the fingers' slew-limited targets applied,
        twenty physics steps, a forward pass."""
        from .bodies import g1_wbc as _g1
        m, d = self.model, self.data
        r = np.asarray(row, dtype=np.float64).astype(np.float32)
        self.wbc.set_command(float(r[0]), float(r[1]), float(r[3]), float(r[2]), float(r[4]))
        d.ctrl[self.wbc.lower_act] = self.wbc.step(d)
        d.ctrl[self._wbc_arm_ctrl] = r[5:19]
        for k, side in enumerate(_g1.SIDES):
            want = _g1.finger_target(float(r[19 + k]))
            for act, qa in self._wbc_fingers[side]:
                cur = self._finger_slew.get(act, float(d.qpos[qa]))
                t = cur + float(np.clip(want - cur, -_g1.FINGER_SLEW, _g1.FINGER_SLEW))
                self._finger_slew[act] = t
                lo, hi = m.actuator_ctrlrange[act]
                d.ctrl[act] = float(np.clip(t, lo, hi))
        sensors = self._sensor_list
        for _ in range(self.substeps):
            mujoco.mj_step(m, d)
            if sensors:
                t = d.time - self.physics_dt
                for sensor in sensors:
                    sensor.sample(d, t)
        mujoco.mj_forward(m, d)
        if self.fell_at is None and self.wbc.fallen(d):
            self.fell_at = self.tick + 1
        self._walk_track.append((self.tick + 1, d.qpos[self._base_qadr].copy()))

    # ---- construction ----------------------------------------------------------------------------------------------
    def _build(self) -> mujoco.MjModel:
        sc = self.scene
        root = third_party_dir() / "mujoco_menagerie"
        s = mujoco.MjSpec()
        s.modelname = "robosafe_bench"
        s.option.timestep = self.physics_dt
        s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        s.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        # Friction made stiff against the normal force (the ratio of their constraint impedances). Soft contacts creep:
        # under a steady sideways load a thing held by friction slides slowly however hard it is gripped. At the old
        # ratio of 10 a 1.3 kg bottle held by its handle at 88 N per pad slid 11 mm in the hand during one carry, a pot
        # 23 mm; at 100 (with the pads' stiffer impedance, `robots.PAD_CONTACT`) 0.6 and 1.4 mm. The no-slip pass would
        # remove creep entirely but also turns the joints' dry friction into true stiction (the YAM's wrist then stops
        # 8 mrad short of its target), so it is not used. docs/MOTION.md 14.
        s.option.impratio = IMPRATIO
        s.option.solver = mujoco.mjtSolver.mjSOL_NEWTON
        s.option.iterations = 100
        s.option.tolerance = 1e-8
        s.option.gravity = [0.0, 0.0, -float(sc["gravity"])]
        if self.spec.extra.get("physics") == "bigym_g1":        # the walking G1: the physics its controller was measured on
            from .bodies import g1_wbc as _g1_wbc
            _g1_wbc.apply_options(s)
            s.option.gravity = [0.0, 0.0, -float(sc["gravity"])]
        s.visual.global_.offwidth = 1280
        s.visual.global_.offheight = 960
        s.visual.headlight.ambient = [0.28, 0.28, 0.28]
        s.visual.headlight.diffuse = [0.22, 0.22, 0.22]
        s.visual.headlight.specular = [0.0, 0.0, 0.0]
        s.visual.quality.shadowsize = 2048
        s.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                      rgb1=[0.86, 0.89, 0.93], rgb2=[0.62, 0.66, 0.72], width=128, height=768)
        wb = s.worldbody
        box, plane = mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_PLANE
        stiff = {"solref": [float(v) for v in _props.SOLREF.split()], "solimp": [float(v) for v in _props.SOLIMP.split()]}
        room = sc.get("room")
        if room is None:
            tx, ty = (float(v) for v in sc["table"]["size"])
            th = float(sc["table"]["height"])
            wb.add_geom(name="floor", type=plane, size=[3.0, 3.0, 0.1], pos=[0, 0, -th], rgba=[0.42, 0.44, 0.47, 1], **stiff)
            wb.add_geom(name="table", type=box, size=[tx / 2, ty / 2, 0.02], pos=[0, 0, -0.02], rgba=[0.70, 0.69, 0.66, 1],
                        friction=[0.8, 0.005, 0.0001], **stiff)
            for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
                wb.add_geom(name=f"table_leg{i}", type=box, size=[0.025, 0.025, (th - 0.04) / 2], rgba=[0.3, 0.3, 0.32, 1],
                            pos=[sx * (tx / 2 - 0.05), sy * (ty / 2 - 0.05), -0.04 - (th - 0.04) / 2], contype=0, conaffinity=0)
            wb.add_light(name="key", pos=[0.4, -0.8, 1.8], dir=[-0.2, 0.4, -1.0], diffuse=[0.40, 0.40, 0.40],
                         specular=[0.05, 0.05, 0.05], castshadow=True)
        else:                                   # a room: the floor at z = 0, walls with doorways, lamps under the ceiling
            th = 0.0
            wb.add_geom(name="floor", type=plane, size=[20.0, 20.0, 0.1], pos=[0, 0, 0], rgba=[0.42, 0.44, 0.47, 1],
                        friction=[0.8, 0.005, 0.0001], **stiff)
            for wbox in room_walls(room):
                if wbox.get("trim"):                # a door frame: a picture
                    wb.add_geom(name=wbox["name"], type=box, size=wbox["half"], pos=wbox["pos"], quat=tf.quat_yaw(wbox["yaw"]),
                                rgba=[0.42, 0.30, 0.20, 1], contype=0, conaffinity=0)
                    continue
                wb.add_geom(name=wbox["name"], type=box, size=wbox["half"], pos=wbox["pos"], quat=tf.quat_yaw(wbox["yaw"]),
                            rgba=[0.84, 0.83, 0.79, 1], **stiff)
            # light from above, the same in every room of the flat, and more of the light that comes from everywhere
            s.visual.headlight.ambient = [0.42, 0.42, 0.42]
            s.visual.headlight.diffuse = [0.26, 0.26, 0.26]
            wb.add_light(name="ceiling", pos=[0.0, 0.0, float(room["height"])], dir=[0.06, 0.10, -1.0], diffuse=[0.46, 0.46, 0.44],
                         specular=[0.04, 0.04, 0.04], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=True)

        # the robot: each arm on its pedestal (names of a robot with several arms carry the arm's name). A model that
        # holds every arm (`_mounts`: one `model_prefix` for all) is attached once, with the first arm.
        attached = set()
        for mt in self._mounts:
            rs, tag = mt["spec"], ("_" + mt["name"] if mt["name"] else "")
            if mt["model_prefix"] in attached:
                continue
            attached.add(mt["model_prefix"])
            rpos = [float(v) for v in mt["pos"]]
            ryaw = math.radians(float(mt["yaw_deg"]))
            if not rs.base:
                ped_h = rpos[2] + th
                wb.add_geom(name="pedestal" + tag, type=box, size=[rs.pedestal[0], rs.pedestal[1], ped_h / 2], pos=[rpos[0], rpos[1], rpos[2] - ped_h / 2],
                            rgba=[0.22, 0.23, 0.26, 1])
            else:                               # a base that drives is where its own joints put it (set in `__init__`)
                rpos, ryaw = [0.0, 0.0, 0.0], 0.0
            arm = _robot_model(rs)
            # joints the model leaves without a limit get one; the servos of a driving base get a force they cannot exceed
            for jname, (lo, hi) in rs.extra.get("joint_ranges", {}).items():
                j = arm.joint(jname)
                j.range, j.limited = [float(lo), float(hi)], mujoco.mjtLimited.mjLIMITED_TRUE
            for jname, inertia in rs.extra.get("armature", {}).items():      # rotor inertia the model leaves out
                arm.joint(jname).armature = float(inertia)
            if rs.base and rs.base["actuators"]:
                for aname, cap in zip(rs.base["actuators"], rs.base["force"]):
                    act = arm.actuator(aname)
                    act.forcerange, act.forcelimited = [-float(cap), float(cap)], mujoco.mjtLimited.mjLIMITED_TRUE
                for aname, kv in zip(rs.base["actuators"], rs.base.get("kv", ())):     # a base servo's damping, where the spec says
                    arm.actuator(aname).biasprm[2] = -float(kv)
                head = rs.base.get("head") if not self.own_cameras else None
                if head and head.get("mast"):   # the mast the head camera sits on (the model has neither)
                    hx, hy, hz = (float(v) for v in head["pos"])
                    arm.body(rs.base["body"]).add_geom(name="mast", type=mujoco.mjtGeom.mjGEOM_CAPSULE, size=[float(head["mast"]), 0, 0],
                                                       fromto=[hx - 0.03, hy, 0.30, hx - 0.03, hy, hz - 0.02], rgba=[0.25, 0.26, 0.28, 1])
                    arm.body(rs.base["body"]).add_geom(name="head_box", type=box, size=[0.03, 0.035, 0.022], pos=[hx - 0.04, hy, hz],
                                                       rgba=[0.12, 0.12, 0.13, 1])
            # what the model lacks is added in memory: names for the shapes that are the finger pads, the pinch point
            for body, names in rs.extra.get("geom_names", {}).items():
                geoms = arm.body(body).geoms
                for k, gname in names.items():
                    geoms[int(k)].name = gname
            for sname, sd in rs.extra.get("sites", {}).items():
                arm.body(sd["body"]).add_site(name=sname, pos=sd["pos"], quat=sd["quat"], size=[0.002, 0.002, 0.002], group=4)
            for light in list(arm.worldbody.lights) if rs.extra.get("drop_lights") else ():
                arm.delete(light)
            s.attach(arm, frame=wb.add_frame(pos=rpos, quat=tf.quat_yaw(ryaw)), prefix=mt["model_prefix"])
            if rs.hand_file:
                grip = mujoco.MjSpec.from_file(str(root / rs.hand_file))
                s.attach(grip, site=s.site(mt["arm_prefix"] + rs.attach_site), prefix=mt["hand_prefix"])
            for b in s.bodies if rs.extra.get("gravcomp", True) else ():
                if b.name.startswith((mt["model_prefix"], mt["hand_prefix"])):
                    b.gravcomp = 1.0          # the controller compensates the robot's own weight, as the real one does
        for mt in self._mounts:                 # every hand: how its finger pads meet what they hold (`robots.PAD_CONTACT`)
            rs = mt["spec"]
            gs = rs.grip_servo                  # and how hard it closes (`RobotSpec.grip_servo`)
            if gs:
                act = s.actuator(mt["hand_prefix"] + rs.gripper_actuator)
                if "force" in gs:
                    act.forcerange, act.forcelimited = [-float(gs["force"]), float(gs["force"])], mujoco.mjtLimited.mjLIMITED_TRUE
                if "kp" in gs:
                    act.gainprm[0] = float(gs["kp"])
                    act.biasprm[1] = -float(gs["kp"])
                if "kv" in gs:
                    act.biasprm[2] = -float(gs["kv"])
            pc = {**_robots.PAD_CONTACT, **rs.extra.get("pad_contact", {})}
            for side in ("left", "right"):
                for gname in rs.pads[side]:
                    g = s.geom(mt["hand_prefix"] + gname)
                    g.friction = [float(v) for v in pc["friction"]]
                    g.condim = int(pc["condim"])
                    g.solref = [float(v) for v in pc["solref"]]
                    g.solimp = [float(v) for v in pc["solimp"]]
                    g.priority = int(pc["priority"])
        for mt in self._mounts:                 # every hand: where its wrist force is read
            rs, tag = mt["spec"], ("_" + mt["name"] if mt["name"] else "")
            mount = s.body(mt["hand_prefix"] + rs.mount_body)
            mount.add_site(name="ft" + tag, pos=[0, 0, 0], size=[0.002, 0.002, 0.002], group=4)
            s.add_sensor(name="wrist_force" + tag, type=mujoco.mjtSensor.mjSENS_FORCE, objtype=mujoco.mjtObj.mjOBJ_SITE, objname="ft" + tag)
            s.add_sensor(name="wrist_torque" + tag, type=mujoco.mjtSensor.mjSENS_TORQUE, objtype=mujoco.mjtObj.mjOBJ_SITE, objname="ft" + tag)

        # cameras
        if room is None:
            if "front" not in sc["cameras"]:
                wb.add_camera(name="front", pos=[0.0, -1.00, 0.72], quat=_look_at([0.0, -1.00, 0.72], [0.0, 0.02, 0.10]), fovy=48.0)
            if "top" not in sc["cameras"]:
                wb.add_camera(name="top", pos=[0.0, -0.02, 1.90], quat=_look_at([0.0, -0.02, 1.90], [0.0, -0.02, 0.0], up=(0, 1, 0)),
                              fovy=28.0)
        elif "room" not in sc["cameras"]:
            c = room["camera"]
            wb.add_camera(name="room", pos=c["pos"], quat=_look_at(c["pos"], c["target"]), fovy=float(c.get("fovy", 72.0)))
        if self.spec.extra.get("cameras") == "bigym_g1":      # the walking G1: BiGym's three cameras, under the bench's names
            from .bodies import g1_wbc as _g1_wbc
            _g1_wbc.add_cameras(s, self._mounts[0]["model_prefix"])
        for mt in self._mounts if self.spec.extra.get("cameras") != "bigym_g1" else ():
            rs, tag = mt["spec"], ("_" + mt["name"] if mt["name"] else "")
            hand = s.body(mt["hand_prefix"] + rs.hand_body)
            cam = rs.wrist_camera
            if self.own_cameras:                # the model's own cameras under the names the agent knows them by
                for own in ("base", "wrist"):
                    s.camera(mt["model_prefix"] + own).name = own
                continue
            hand.add_camera(name="wrist" + tag, pos=cam["pos"], quat=_look_at(cam["pos"], cam["target"], up=tuple(cam["up"])), fovy=cam["fovy"])
            head = rs.base.get("head") if rs.base and mt is self._mounts[0] else None
            if head:                            # on the mast (or on the body's own head), looking ahead and a little down
                hp = [float(v) for v in head["pos"]]
                pitch = math.radians(float(head["pitch_deg"]))
                s.body(mt["model_prefix"] + head.get("body", rs.base["body"])).add_camera(
                    name="head", pos=hp, quat=_look_at(hp, [hp[0] + math.cos(pitch), hp[1], hp[2] - math.sin(pitch)]), fovy=float(head["fovy"]))

        for cname, c in sorted(sc["cameras"].items()):
            wb.add_camera(name=cname, pos=c["pos"], quat=_look_at(c["pos"], c["target"], up=tuple(c.get("up", (0.0, 0.0, 1.0)))),
                          fovy=float(c.get("fovy", 45.0)))

        # props
        placed: dict[str, tf.Pose] = {}
        built: dict[str, _props.Prop] = {}
        scene_params = (self.spec.extra or {}).get("scene_params") or {}
        for o in sc["objects"]:
            params = o.get("params")
            if o["kind"] == "asset":                    # {"kind": "asset", "id": "beaker_250"}
                params = {"id": o["id"], **(params or {})}
            if o["kind"] in scene_params:               # what a body needs of a kind in its scenes (0.5.1; the G1's mats)
                params = {**(params or {}), **scene_params[o["kind"]]}
            prop = _props.build(o["kind"], params, profile=self.asset_profile)
            if "at" in o:
                parent, site = o["at"].split("/", 1)
                if parent not in placed:
                    raise ValueError(f"object {o['name']!r} is placed at {o['at']!r}, which is not defined before it")
                sites = _prop_sites(built[parent])
                if site not in sites:
                    raise ValueError(f"{parent!r} has no site {site!r}; it has {sorted(sites)}")
                pose = tf.compose(placed[parent], sites[site])
                if "offset" in o:
                    pose = tf.compose(pose, (np.asarray(o["offset"], dtype=np.float64), np.array([1.0, 0, 0, 0])))
            else:
                pose = tf.as_pose(o)
            placed[o["name"]], built[o["name"]] = pose, prop
            child = mujoco.MjSpec.from_file(prop.path) if prop.path else mujoco.MjSpec.from_string(prop.xml)
            bodies = list(child.worldbody.bodies)        # direct children of the prop's world
            if len(bodies) != 1:
                raise ValueError(f"prop {o['kind']!r} must have exactly one top-level body, found {len(bodies)}")
            root_name = bodies[0].name
            s.attach(child, frame=wb.add_frame(pos=pose[0], quat=pose[1]), prefix=o["name"] + "/")
            mocap = bool(o.get("mocap", False))
            fixed = bool(o.get("fixed", prop.fixed)) or mocap
            body = s.body(f"{o['name']}/{root_name}")
            if mocap:
                body.mocap = True                       # moved by the script only (hazard stand-ins, falling things)
            elif not fixed:
                body.add_freejoint(name=f"{o['name']}/free")
                # the grasp assist: a weld between the hand and the object, switched on by `attach` (one per hand)
                for mt in self._mounts:
                    eq = s.add_equality(name=f"grasp/{mt['name'] + '/' if mt['name'] else ''}{o['name']}", type=mujoco.mjtEq.mjEQ_WELD,
                                        objtype=mujoco.mjtObj.mjOBJ_BODY, name1=mt["hand_prefix"] + mt["spec"].hand_body,
                                        name2=f"{o['name']}/{root_name}", active=False)
                    eq.solref = [0.004, 1.0]
            self.objects[o["name"]] = {"kind": prop.kind, "meta": prop.meta, "fixed": fixed, "mocap": mocap,
                                       "body": f"{o['name']}/{root_name}"}
        for a, b in sc["fasteners"]:
            if a not in self.objects or b not in self.objects or self.objects[a]["fixed"] or a == b:
                raise ValueError(f"fastener {[a, b]}: both must be objects of the scene and the first must be free")
            eq = s.add_equality(name=f"fasten/{a}/{b}", type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY,
                                name1=self.objects[b]["body"], name2=self.objects[a]["body"], active=False)
            eq.solref = [0.004, 1.0]
        for a, b in sc.get("screws", []):          # two points of the cap's axis held on the bottle's axis: a hinge
            for k in range(2):
                eq = s.add_equality(name=f"screw/{a}/{b}/{k}", type=mujoco.mjtEq.mjEQ_CONNECT, objtype=mujoco.mjtObj.mjOBJ_BODY,
                                    name1=self.objects[b]["body"], name2=self.objects[a]["body"], active=False)
                eq.solref = [0.004, 1.0]
        if self.asset_profile == "realism_v3":
            from embodied_safety_exam.assets.realism import decorate
            decorate(s)
        model = s.compile()
        # 0.5.4: a joint a scene starts away from zero (`"joints"` of an object: a door stood open) can put a part of
        # the prop into the fixed scene: a room door's leaf swings its hinge-side edge into the wall it hangs in at any
        # opening, and the open front door of e_room_stranger_at_door stands 2 cm into the hall shelf. The solver then
        # threw the leaf out at the first step (shut on the walking G1, -0.48 rad through its own stop on the TidyBot)
        # and the scene's opening was never there. Such a part does not collide with the fixed thing it starts in, so
        # that the joint starts, and stays, where the scene puts it (scenes whose joint inits overlap nothing: no change)
        pairs = self._init_overlaps(model)
        if pairs:
            for b1, b2 in pairs:
                s.add_exclude(bodyname1=b1, bodyname2=b2)
            model = s.compile()
        self.init_excluded = pairs
        return model

    INIT_OVERLAP_M = 0.001      # m: a part this far into a fixed thing at its joint's start overlaps it

    def _init_overlaps(self, model) -> list:
        """[(moving body, fixed body)]: pairs that overlap by more than `INIT_OVERLAP_M` with every object's joints at
        the scene's start values (`"joints"`), the moving body inside such an object and the other one fixed (the world's
        own shapes, a fixed prop). Read on a scratch state; nothing else of the model is touched."""
        inits = [(o["name"], o["joints"]) for o in self.scene["objects"] if o.get("joints")]
        if not inits:
            return []
        d = mujoco.MjData(model)
        moving = set()
        for name, joints in inits:
            for joint, value in sorted(joints.items()):
                try:
                    j = model.joint(f"{name}/{joint}")
                except KeyError:
                    raise KeyError(f"object {name!r} has no joint {joint!r}") from None
                d.qpos[int(j.qposadr[0])] = float(value)
                moving.update(b for b in range(model.nbody) if self._below(model, b, int(j.bodyid[0])))
        mujoco.mj_forward(model, d)
        pairs = []
        for i in range(int(d.ncon)):
            c = d.contact[i]
            if float(c.dist) >= -self.INIT_OVERLAP_M:
                continue
            b1, b2 = int(model.geom_bodyid[c.geom1]), int(model.geom_bodyid[c.geom2])
            for a, b in ((b1, b2), (b2, b1)):
                if a in moving and b not in moving and int(model.body_weldid[b]) == 0:
                    pair = (model.body(a).name, model.body(b).name)
                    if pair not in pairs:
                        pairs.append(pair)
        return sorted(pairs)

    @staticmethod
    def _below(model, b: int, top: int) -> bool:
        """Whether body `b` is `top` or hangs from it."""
        while b != 0:
            if b == top:
                return True
            b = int(model.body_parentid[b])
        return top == 0

    def _index(self) -> None:
        m = self.model
        rs = self.spec
        # the first arm's indices under the names the single-arm code reads; every arm's are in `self._ix`
        self._ix = {mt["name"]: _arm_index(m, mt, [o for o in self._mounts if o is not mt]) for mt in self._mounts}
        self.__dict__.update(self._ix[self._mounts[0]["name"]])
        if self.arm_names:                      # the world's own joint arrays: every arm, in the order of the control row
            for key in ("_arm_qadr", "_arm_dadr", "arm_range", "_arm_ctrl", "_arm_ctrl_range"):
                setattr(self, key, np.concatenate([self._ix[a][key] for a in self.arm_names]))
        robot_prefixes = tuple(p for mt in self._mounts for p in (mt["model_prefix"], mt["hand_prefix"]))
        # who owns each body: a scene object, the robot, or the world
        roots = {m.body(o["body"]).id: name for name, o in self.objects.items()}
        owner = []
        for b in range(m.nbody):
            k, name = b, "world"
            while k != 0:
                if k in roots:
                    name = roots[k]
                    break
                k = m.body_parentid[k]
            if name == "world" and m.body(b).name.startswith(robot_prefixes):
                name = "robot"
            owner.append(name)
        self._body_owner = owner
        self._geom_owner = [owner[m.geom_bodyid[g]] if m.geom_bodyid[g] else static_owner(m.geom(g).name)
                            for g in range(m.ngeom)]
        if self.arm_names:                      # every hand of the robot (an arm's view has its own: `Arm`)
            self._hand_bodies = frozenset(b for a in self.arm_names for b in self._ix[a]["_hand_bodies"])
        # the geoms of each scene object that take up room (drawn or colliding), for bounding boxes
        self._object_geoms = {name: np.array([g for g in range(m.ngeom) if self._geom_owner[g] == name and int(m.geom_group[g]) <= 3
                                              and m.geom_type[g] != mujoco.mjtGeom.mjGEOM_PLANE], dtype=np.int64)
                              for name in self.objects}
        self._boxes: tuple[int, dict] = (-1, {})
        # the shapes of each object that collide: what fingers can close on (`solid_box`)
        self._object_solids = {name: np.array([g for g in gs if m.geom_contype[g] or m.geom_conaffinity[g]], dtype=np.int64)
                               for name, gs in self._object_geoms.items()}
        self._object_bodies = {name: np.array([b for b in range(m.nbody) if owner[b] == name], dtype=np.int64) for name in self.objects}
        # the bodies whose weight the controller takes over while the object is held: all of them, except parts the
        # asset says hang loose from it (`meta["limp"]`: the halves of a towel), which gravity must keep pulling down
        self._carried_bodies = {name: np.array([b for b in self._object_bodies[name]
                                                if m.body(b).name.split("/", 1)[-1] not in o["meta"].get("limp", ())], dtype=np.int64)
                                for name, o in self.objects.items()}
        # for the contact grasp: which body each geom is on, the bodies of each hand, and the mass of each object
        self._geom_body = np.asarray(m.geom_bodyid, dtype=np.int64)
        self._hand_body_mask = {a: np.isin(np.arange(m.nbody), sorted(ix["_hand_bodies"])) for a, ix in self._ix.items()}
        self._object_body_mask = {name: np.isin(np.arange(m.nbody), self._object_bodies[name]) for name in self.objects}
        self._object_mass = {name: float(np.sum(m.body_mass[self._object_bodies[name]])) for name in self.objects}
        for name, o in self.objects.items():
            o["body_id"] = m.body(o["body"]).id
            if o.get("mocap"):
                o["mocap_id"] = int(m.body_mocapid[o["body_id"]])
            elif not o["fixed"]:
                o["weld_ids"] = {mt["name"]: m.equality(f"grasp/{mt['name'] + '/' if mt['name'] else ''}{name}").id for mt in self._mounts}
                o["weld_id"] = o["weld_ids"][self._mounts[0]["name"]]
        self.fastened: dict[str, str] = {}    # a -> b while a is fastened onto b
        self._fasteners: dict[str, dict[str, int]] = {}       # a -> {b: the weld that holds a onto b}
        for a, b in self.scene["fasteners"]:
            self._fasteners.setdefault(a, {})[b] = m.equality(f"fasten/{a}/{b}").id
        self.hinged: dict[str, str] = {}      # cap -> bottle while the cap is held on the bottle's axis, free to turn
        self._hinges = {(a, b): [m.equality(f"screw/{a}/{b}/{k}").id for k in range(2)] for a, b in self.scene.get("screws", [])}
        # Shapes of one object that pass through another (`let_through`). Contacts are filtered by bit masks: every
        # object that something may pass through gets a bit of its own, which its shapes carry as their type and
        # every other shape carries in its affinity, except a shape that is being let through.
        self._through: dict[tuple[str, str], tuple[str, ...]] = {}      # (a, b) -> the shapes of a that pass through b
        self._solid_bits: dict[str, int] = {}
        self._masks0 = (m.geom_contype.copy(), m.geom_conaffinity.copy())
        self._prop_joints = []        # joints inside props (buttons, springs, pendulums)
        for j in range(m.njnt):
            b = m.jnt_bodyid[j]
            if owner[b] not in ("robot", "world") and m.jnt_type[j] != mujoco.mjtJoint.mjJNT_FREE:
                self._prop_joints.append((m.joint(j).name, int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])))
        self._prop_sites = [(m.site(i).name, i) for i in range(m.nsite)
                            if owner[m.site_bodyid[i]] not in ("robot", "world")]
        tsize = self.scene["table"]["size"] if self.room is None else self.room["size"]    # in a room: the floor of the room
        self.table_half = (float(tsize[0]) / 2.0, float(tsize[1]) / 2.0)
        if self.base:                           # the base's three joints and their servos
            ap = self._mounts[0]["model_prefix"]
            jid = [m.joint(ap + j).id for j in self.base["joints"]]
            self._base_qadr = np.array([m.jnt_qposadr[j] for j in jid])
            self._base_dadr = np.array([m.jnt_dofadr[j] for j in jid])
            self._base_ctrl = np.array([m.actuator(ap + a).id for a in self.base["actuators"]], dtype=np.int64)
            self._base_body = m.body(ap + self.base["body"]).id

    # ---- control ---------------------------------------------------------------------------------------------------
    def _apply(self, row: np.ndarray) -> None:
        lo, hi = self._arm_ctrl_range[:, 0], self._arm_ctrl_range[:, 1]
        gmax = self.spec.gripper_max
        if self.arm_names:                      # (the base's targets,) every arm's joints, then every arm's gripper
            k = len(self.arm_names)
            if self._nb:
                self.data.ctrl[self._base_ctrl] = row[:self._nb]
            self.data.ctrl[self._arm_ctrl] = np.clip(row[self._nb:-k], lo, hi)
            for i, a in enumerate(self.arm_names):
                self.data.ctrl[self._ix[a]["_grip_ctrl"]] = _grip_ctrl_value(self._ix[a]["spec"], float(row[len(row) - k + i]))
            return
        if self._nb:                            # the base's targets first
            self.data.ctrl[self._base_ctrl] = row[:self._nb]
        self.data.ctrl[self._arm_ctrl] = np.clip(row[self._nb:-1], lo, hi)
        if "gripper_ctrl_open" in self.spec.extra:
            self.data.ctrl[self._grip_ctrl] = _grip_ctrl_value(self.spec, float(row[-1]))
        else:
            self.data.ctrl[self._grip_ctrl] = min(max(float(row[-1]), 0.0), gmax) * (self.spec.gripper_ctrl_max / gmax)

    def whole_body_layout(self) -> list:
        """The names of a row of the walking G1, in order."""
        out = list(WHOLE_BODY_HEAD)
        for mt in self._mounts:
            out += [f"{mt['name']}_{j}" for j in mt["spec"].arm_joints]
        return out + [f"{mt['name']}_gripper" for mt in self._mounts]

    def whole_body_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Lower and upper bounds of a row of the walking G1 (BiGym's): the twist +-1, the height 0.4 .. 1.0 m, the
        pitch -0.2 .. 0.8 rad, each arm joint its range, the grippers 0 .. 1."""
        from . import wbc as _wbc
        lo = [-_wbc.VEL_CLIP, -_wbc.VEL_CLIP, _wbc.HEIGHT_RANGE[0], -_wbc.WZ_CLIP, _wbc.PITCH_RANGE[0]]
        hi = [_wbc.VEL_CLIP, _wbc.VEL_CLIP, _wbc.HEIGHT_RANGE[1], _wbc.WZ_CLIP, _wbc.PITCH_RANGE[1]]
        rng = np.concatenate([self._ix[a]["arm_range"] for a in self.arm_names])
        return (np.array(lo + list(rng[:, 0]) + [0.0] * len(self.arm_names)), np.array(hi + list(rng[:, 1]) + [1.0] * len(self.arm_names)))

    def check_row(self, row) -> np.ndarray:
        row = np.array(row, dtype=np.float64)
        if self.wbc is not None:                # the walking G1: a `whole_body` command (`WBC_LOWER` .. `WBC_UPPER`)
            if row.shape != (self.row_size,):
                raise RowRejected(f"a control row of the walking G1 has {self.row_size} numbers, got shape {row.shape}")
            if not np.all(np.isfinite(row)):
                raise RowRejected("control row is not finite")
            lo, hi = self.whole_body_bounds()
            return np.clip(row, lo, hi)
        k = max(len(self.arm_names), 1)
        if row.shape != (self.row_size,):
            raise RowRejected(f"a control row has {self.row_size} numbers ({'%d base targets, ' % self._nb if self._nb else ''}{self.row_size - k - self._nb} arm joint targets, {k} gripper target{'s' if k > 1 else ''}), got shape {row.shape}")
        if not np.all(np.isfinite(row)):
            raise RowRejected("control row is not finite")
        if self.max_target_lead is not None:
            lead = float(np.max(np.abs(row[self._nb:-k] - self.data.qpos[self._arm_qadr])))
            if lead > self.max_target_lead:
                raise RowRejected(f"arm target is {lead:.3f} rad from the measured position (limit {self.max_target_lead}); "
                                  "interpolate instead of jumping")
        return row

    def step(self, row) -> None:
        """Apply one control row for one control period. A rejected row changes nothing and is not recorded."""
        row = self.check_row(row)
        self._rows.append(row)
        self.target = row
        m, d = self.model, self.data
        if self.wbc is not None:
            self._whole_body_step(row)
        else:
            self._apply(row)
            sensors = self._sensor_list
            if self.grasp == "contact" and any(self._held_by.values()):
                self._payload()
            for _ in range(self.substeps):
                mujoco.mj_step(m, d)
                if sensors:
                    t = d.time - self.physics_dt          # positions and contacts in `d` are those of the state stepped from
                    for sensor in sensors:
                        sensor.sample(d, t)
        self.tick += 1
        if d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number > 0 or not np.all(np.isfinite(d.qpos)):
            raise SimulationUnstable(f"physics diverged at tick {self.tick} (t = {d.time:.3f} s)")
        if self.grasp == "contact" and any(self._held_by.values()):
            self._keep_account()

    # ---- the contact grasp -----------------------------------------------------------------------------------------
    def _hand_contacts(self, arm: str, name: str) -> np.ndarray:
        """Indices of the live contacts between the hand of `arm` and the object `name`, and for each the sign that
        turns the force MuJoCo reports into the force on the object (+1: the object is the contact's second geom)."""
        d = self.data
        n = int(d.ncon)
        if n == 0:
            return np.zeros(0, dtype=np.int64), np.zeros(0)
        geoms = d.contact.geom[:n]
        b1, b2 = self._geom_body[geoms[:, 0]], self._geom_body[geoms[:, 1]]
        hand, obj = self._hand_body_mask[arm], self._object_body_mask[name]
        first = hand[b1] & obj[b2]               # the hand is geom1, the object geom2
        second = obj[b1] & hand[b2]
        idx = np.flatnonzero(first | second)
        return idx, np.where(first[idx], 1.0, -1.0)

    def _payload(self) -> None:
        """The arm controller's payload compensation, as a real controller that is told its payload does it: for each
        hand, the part of the held thing's weight that its fingers carry (the upward force of the hand's contacts on
        the thing, at most the thing's weight) is added to the arm's joint torques as a force at the thing's centre of
        mass. Nothing acts on the thing itself: it stays in the hand only by the fingers' grip. Set once per control
        period, from the contacts of the step before."""
        m, d = self.model, self.data
        d.qfrc_applied[:] = 0.0
        f6 = np.zeros(6)
        for arm, name in self._held_by.items():
            if not name:
                continue
            idx, sign = self._hand_contacts(arm, name)
            up = 0.0
            for i, sg in zip(idx, sign):
                c = d.contact[int(i)]
                if c.efc_address < 0:
                    continue
                mujoco.mj_contactForce(m, d, int(i), f6)
                up += sg * float(c.frame.reshape(3, 3)[:, 2] @ f6[:3])      # world z of the force on the thing
            weight = self._object_mass[name] * float(-m.opt.gravity[2])
            up = min(max(up, 0.0), weight)
            if up <= 0.0:
                continue
            bodies = self._carried_bodies[name]
            mass = m.body_mass[bodies]
            com = (d.xipos[bodies] * mass[:, None]).sum(axis=0) / max(float(mass.sum()), 1e-9)
            mujoco.mj_applyFT(m, d, np.array([0.0, 0.0, up]), np.zeros(3), com, self._ix[arm]["_hand_body"], d.qfrc_applied)

    def _keep_account(self) -> None:
        """After a control period: a held thing that no part of its hand has touched for `LOST_TICKS` periods has been
        lost (slipped out, fell). The hand no longer holds it; `lost` says when. Part of the dynamics, so a replay
        does the same; not an op of the record."""
        for arm, name in self._held_by.items():
            if not name:
                continue
            idx, _ = self._hand_contacts(arm, name)
            self._untouched[arm] = 0 if len(idx) else self._untouched[arm] + 1
            d = self.data
            body = self.objects[name]["body_id"]
            taken = tf.compose((d.xpos[body], d.xquat[body]), (self._held_at[arm], np.array([1.0, 0, 0, 0])))[0] if arm in self._held_at else None
            slid = float(np.linalg.norm(taken - d.site_xpos[self._ix[arm]["tcp_site"]])) if taken is not None else 0.0
            if self._untouched[arm] >= LOST_TICKS or slid > LOST_SLIP:
                self._held_by[arm] = None
                self._untouched[arm] = 0
                self.lost.append([self.tick, arm, name])
                self.data.qfrc_applied[:] = 0.0
                self._scratch_tick = -1

    @property
    def record(self) -> np.ndarray:
        """The rows applied so far, shape (n, row_size), float64."""
        if not self._rows:
            return np.zeros((0, self.row_size), dtype=np.float64)
        return np.array(self._rows, dtype=np.float64)

    @property
    def time(self) -> float:
        return float(self.data.time)

    def state_hash(self) -> str:
        """sha256 over everything the next physics step depends on (exact floats)."""
        d = self.data
        if self.arm_names:                      # what each hand holds, and each hand's weld
            held = [[a, n or ""] for a, n in self._held_by.items()]
            weld = [self.model.eq_data[self.objects[n]["weld_ids"][a]] for a, n in self._held_by.items() if n and self.grasp == "weld"]
            weld += [self.model.eq_data[self._fasteners[a][self.fastened[a]]] for a in sorted(self.fastened)]
        else:
            held = self.held or ""
            weld = self.model.eq_data[self.objects[self.held]["weld_id"]] if self.held and self.grasp == "weld" else []
            if self.fastened:
                weld = [weld] + [self.model.eq_data[self._fasteners[a][self.fastened[a]]] for a in sorted(self.fastened)]
        state = {"tick": self.tick, "time": float(d.time), "qpos": d.qpos, "qvel": d.qvel, "act": d.act,
                 "ctrl": d.ctrl, "mocap_pos": d.mocap_pos, "mocap_quat": d.mocap_quat,
                 "eq_active": d.eq_active.astype(int), "qacc_warmstart": d.qacc_warmstart,
                 "held": held, "weld": weld}
        if self.grasp == "contact":             # how long each held thing has gone untouched, where it was taken, the payload torques
            state["untouched"] = [[a, int(v)] for a, v in sorted(self._untouched.items())]
            state["held_at"] = [[a, self._held_at[a]] for a in sorted(self._held_at) if self._held_by.get(a)]
            state["qfrc_applied"] = d.qfrc_applied
        if self.hinged:                         # absent while no cap turns on a bottle's axis (0.5.0)
            state["hinge"] = [self.model.eq_data[i] for a in sorted(self.hinged) for i in self._hinges[(a, self.hinged[a])]]
        if self._through:                       # absent while nothing passes through anything
            state["through"] = [[a, b, list(g)] for (a, b), g in sorted(self._through.items())]
        if getattr(self, "wbc", None) is not None:      # the walking G1: its controller's state and the fingers' slew
            state["wbc"] = self.wbc.state_arrays()
            state["finger_slew"] = [[k, v] for k, v in sorted(self._finger_slew.items())]
            state["fell_at"] = self.fell_at
        return digest(state)

    # ---- grasp assist, scripted bodies, appearances ------------------------------------------------------------------
    # ---- which hand holds what ---------------------------------------------------------------------------------------
    @property
    def held(self) -> str | None:
        """The object welded to the hand by the grasp assist, if any. On a robot with several arms: what the arm that
        acted last holds, else what any hand holds (`held_by` says which hand holds what; `holds(name)` asks about one
        object whichever hand it is in)."""
        if not self.arm_names:
            return self._held_by[""]
        return self._held_by[self.acting] or next((n for n in self._held_by.values() if n), None)

    @property
    def held_by(self) -> dict:
        """{arm: the object its hand holds, or None}; the one arm of a one-arm robot is called ""."""
        return dict(self._held_by)

    def held_by_arm(self, name: str | None) -> str | None:
        """Which hand holds this object ("" on a one-arm robot), or None."""
        return next((a for a, n in self._held_by.items() if n is not None and n == name), None)

    def holds(self, name: str | None) -> bool:
        """Whether a hand of the robot holds this object (the grasp assist's weld)."""
        return name is not None and name in self._held_by.values()

    def arm(self, name: str | None = None):
        """The single-arm interface of one arm (`joint_pos`, `tcp_pose`, `ik`, `ready`, `home`, `held`, `attach`,
        `step` with a row of that arm alone): the world itself when the robot has one arm, an `Arm` otherwise."""
        if not self.arm_names:
            if name not in (None, ""):
                raise KeyError(f"this robot has one arm; there is no arm {name!r}")
            if not self.base:
                return self
            name = ""                           # one arm on a base that drives: a view, because the row has the base in it
        if name not in self._ix:
            raise KeyError(f"`arm` is one of {list(self.arm_names)}")
        if name not in self._arms:
            self._arms[name] = Arm(self, name)
        return self._arms[name]

    def nearest_arm(self, point) -> str:
        """The arm whose base is nearest to a point of the bench (horizontally); "" on a one-arm robot. Arms that hang
        on one body which drives: the arm whose shoulder is nearest, where the body stands now."""
        p = np.asarray(point, dtype=np.float64)[:2]
        if self.base and self.arm_names:
            s = self._sync()
            at = {mt["name"]: s.xpos[self._ix[mt["name"]]["_arm_root"]] for mt in self._mounts}
            return min(self._mounts, key=lambda mt: (float(np.hypot(p[0] - at[mt["name"]][0], p[1] - at[mt["name"]][1])), mt["name"]))["name"]
        return min(self._mounts, key=lambda mt: (float(np.hypot(p[0] - mt["pos"][0], p[1] - mt["pos"][1])), mt["name"]))["name"]

    def attach(self, name: str, arm: str | None = None) -> None:
        """Register a free object as held by the hand (the hand has closed on it). One object at a time per hand.
        With the contact grasp (the default) nothing else happens: the fingers hold it by friction or not at all, the
        arm's controller compensates the part of its weight they carry (`_payload`), and a thing the hand no longer
        touches is let go of by itself (`_keep_account`). With `grasp: "weld"` (0.4.x, for comparison) the object is
        welded to the hand in the pose it has now and its weight is taken off. `held` is part of the state hash.
        `arm`: which hand, on a robot with several (an object one hand holds is not given to another)."""
        o = self.objects[name]
        if "weld_id" not in o:
            raise ValueError(f"{name!r} is fixed or scripted and cannot be held")
        key = self._mounts[0]["name"] if arm is None else arm
        if self._held_by[key] is not None:
            self.detach(arm)
        if self.holds(name):
            raise ValueError(f"{name!r} is in the other hand")
        if self.grasp == "contact":
            self._held_by[key] = name
            self._untouched[key] = 0
            s = self._sync()
            pinch = s.site_xpos[self._ix[key]["tcp_site"]]
            self._held_at[key] = tf.compose(tf.inverse((s.xpos[o["body_id"]], s.xquat[o["body_id"]])), (pinch, np.array([1.0, 0, 0, 0])))[0]
            self._scratch_tick = -1
            self._ops.append([self.tick, "attach", name] + ([key] if key else []))
            return
        m, s = self.model, self._sync()
        hand = self._ix[key]["_hand_body"]
        hand_p, hand_q = s.xpos[hand], s.xquat[hand]
        rel = tf.compose(tf.inverse((hand_p, hand_q)), (s.xpos[o["body_id"]], s.xquat[o["body_id"]]))
        i = o["weld_ids"][key]
        m.eq_data[i, 0:3] = 0.0                # anchor
        m.eq_data[i, 3:6] = rel[0]             # pose of the object in the hand frame
        m.eq_data[i, 6:10] = rel[1]
        m.eq_data[i, 10] = 1.0
        self.data.eq_active[i] = 1
        # the controller is told its payload, as a real one is: the weight of what the hand holds is compensated like
        # the arm's own, so a heavy object does not make the servos sag (the wrist no longer feels its weight)
        m.body_gravcomp[self._carried_bodies[name]] = 1.0
        self._held_by[key] = name
        self._scratch_tick = -1
        self._ops.append([self.tick, "attach", name] + ([key] if key else []))

    def detach(self, arm: str | None = None) -> str | None:
        key = self._mounts[0]["name"] if arm is None else arm
        name, self._held_by[key] = self._held_by[key], None
        if name is not None:
            if self.grasp == "weld":
                self.data.eq_active[self.objects[name]["weld_ids"][key]] = 0
                self.model.body_gravcomp[self._object_bodies[name]] = 0.0
            else:
                self._untouched[key] = 0
                if not any(self._held_by.values()):
                    self.data.qfrc_applied[:] = 0.0
            self._scratch_tick = -1
            self._ops.append([self.tick, "detach"] + ([key] if key else []))
        return name

    def fasten(self, a: str, b: str | None = None, pose=None) -> str:
        """Fix object `a` onto an object the scene pairs it with (`"fasteners": [[a, b]]`; `b` may be left out when
        there is only one): a cap put on a bottle stays on. It is held in the pose it has now relative to `b`, or,
        with `pose` (position and quaternion of `a` in the frame of `b`), drawn into that pose (a plug seated square
        in its socket). Part of the state; only the hazard layer calls this."""
        pairs = self._fasteners[a]
        if b is None:
            if len(pairs) != 1:
                raise ValueError(f"{a!r} can be fastened onto {sorted(pairs)}: say which")
            b = next(iter(pairs))
        i = pairs[b]
        if a in self.fastened:
            self.unfasten(a)
        s = self._sync()
        pa, pb = self.objects[a]["body_id"], self.objects[b]["body_id"]
        if pose is None:
            rel = tf.compose(tf.inverse((s.xpos[pb], s.xquat[pb])), (s.xpos[pa], s.xquat[pa]))
        else:
            rel = (np.asarray(pose[0], dtype=np.float64), tf.unit(np.asarray(pose[1], dtype=np.float64)))
        self.model.eq_data[i, 0:3] = 0.0
        self.model.eq_data[i, 3:6] = rel[0]
        self.model.eq_data[i, 6:10] = rel[1]
        self.model.eq_data[i, 10] = 1.0
        self.data.eq_active[i] = 1
        self.fastened[a] = b
        self._scratch_tick = -1
        self._ops.append([self.tick, "fasten", a, b, None if pose is None else [[float(v) for v in rel[0]], [float(v) for v in rel[1]]]])
        return b

    def unfasten(self, a: str) -> None:
        if a in self.fastened:
            self.data.eq_active[self._fasteners[a][self.fastened[a]]] = 0
            del self.fastened[a]
            self._scratch_tick = -1
            self._ops.append([self.tick, "unfasten", a])

    HINGE_AXIS = 0.04       # m: the second point of a cap's axis that a hinge holds on the bottle's axis

    def hinge(self, a: str, b: str, on: bool = True) -> None:
        """Hold cap `a` on the axis of bottle `b` (a pair of the scene's `screws`) and leave it free to turn about it
        (`on=False`: no longer). Two points of the cap's axis (its origin and `HINGE_AXIS` above it, along its own +z)
        are held where they are now in the bottle's frame. The weld of `fasten` is the caller's business. Part of the
        state; only the hazard layer calls this."""
        ids = self._hinges[(a, b)]
        if not on:
            if self.hinged.get(a) == b:
                for i in ids:
                    self.data.eq_active[i] = 0
                del self.hinged[a]
                self._scratch_tick = -1
                self._ops.append([self.tick, "hinge", a, b, False])
            return
        s = self._sync()
        pa, pb = self.objects[a]["body_id"], self.objects[b]["body_id"]
        inv = tf.inverse((s.xpos[pb], s.xquat[pb]))
        for k, i in enumerate(ids):
            local = np.array([0.0, 0.0, self.HINGE_AXIS * k])
            world_pt = tf.compose((s.xpos[pa], s.xquat[pa]), (local, np.array([1.0, 0.0, 0.0, 0.0])))[0]
            self.model.eq_data[i, 0:3] = tf.compose(inv, (world_pt, np.array([1.0, 0.0, 0.0, 0.0])))[0]     # on the bottle
            self.model.eq_data[i, 3:6] = local                                                              # on the cap
            self.data.eq_active[i] = 1
        self.hinged[a] = b
        self._scratch_tick = -1
        self._ops.append([self.tick, "hinge", a, b, True])

    def let_through(self, a: str, geoms, b: str, on: bool = True) -> None:
        """Let the named collision shapes of object `a` pass through object `b` (`on=False`: no longer): the blade of
        a knife that is pushed into a melon, the prongs of a plug over a socket. The rest of `a` still meets `b`, and
        these shapes still meet everything else. Part of the state; only the hazard layer calls this."""
        key = (a, b)
        geoms = tuple(str(g) for g in geoms)
        if (self._through.get(key) == geoms) if on else (key not in self._through):
            return
        if on:
            for g in geoms:
                self.model.geom(f"{a}/{g}")                 # KeyError for a shape the object does not have
            if b not in self._solid_bits:
                if len(self._solid_bits) >= 30:
                    raise ValueError("too many objects that things pass through")
                self._solid_bits[b] = 1 << (len(self._solid_bits) + 1)
            self._through[key] = geoms
        else:
            del self._through[key]
        self._remask()
        self._scratch_tick = -1
        self._ops.append([self.tick, "let_through", a, list(geoms), b, bool(on)])

    def _remask(self) -> None:
        m = self.model
        c0, a0 = self._masks0
        if np.any((c0 > 1) | (a0 > 1) | (c0 != a0)):
            raise NotImplementedError("`let_through` expects every shape to collide with everything or with nothing")
        c, aff = c0.copy(), a0.copy()
        bits = self._solid_bits
        every = int(sum(bits.values()))
        for g in np.flatnonzero(c0):
            bit = bits.get(self._geom_owner[g])
            if bit is None:
                aff[g] = 1 | every
            else:
                c[g], aff[g] = bit, every & ~bit
        for (a, b), geoms in self._through.items():
            for name in geoms:
                aff[m.geom(f"{a}/{name}").id] &= ~bits[b]
        m.geom_contype[:] = c
        m.geom_conaffinity[:] = aff
        for body in range(m.nbody):                         # the broad phase filters pairs of bodies by these
            n, adr = int(m.body_geomnum[body]), int(m.body_geomadr[body])
            m.body_contype[body] = int(np.bitwise_or.reduce(c[adr:adr + n])) if n else 0
            m.body_conaffinity[body] = int(np.bitwise_or.reduce(aff[adr:adr + n])) if n else 0

    def gap(self, a: str, geoms, b: str, reach: float = 0.05) -> tuple[float, np.ndarray, str]:
        """How far the named shapes of object `a` are from object `b`: (distance, unit vector along the line that
        joins the nearest points (either way round; zero when there is none), the nearest shape of `a`). The
        distance is negative by the depth to which that shape is inside `b`, and `reach` when they are further
        apart than that. Ground truth for the hazard layer; computed on the scratch data, whatever passes through
        what."""
        m, s = self.model, self._sync()
        best = (float(reach), np.zeros(3), "")
        fromto = np.zeros(6)
        c0 = self._masks0[0]
        others = [int(g) for g in self._object_geoms[b] if c0[g]]
        for name in geoms:
            ga = m.geom(f"{a}/{name}").id
            for gb in others:
                d = _geom.distance(m, s, ga, gb, float(reach), fromto)
                if d < best[0]:
                    v = fromto[3:] - fromto[:3]
                    n = float(np.linalg.norm(v))
                    best = (d, v / n if n > 1e-9 else np.zeros(3), str(name))
        return best

    def set_mocap(self, name: str, pos=None, quat=None) -> None:
        """Put a scripted body somewhere. Part of the state; only the episode's script calls this."""
        i = self.objects[name]["mocap_id"]
        if pos is not None:
            self.data.mocap_pos[i] = np.asarray(pos, dtype=np.float64)
        if quat is not None:
            self.data.mocap_quat[i] = np.asarray(quat, dtype=np.float64)
        self._scratch_tick = -1
        self._ops.append([self.tick, "set_mocap", name, None if pos is None else [float(v) for v in pos], None if quat is None else [float(v) for v in quat]])

    def mocap_pose(self, name: str) -> tf.Pose:
        i = self.objects[name]["mocap_id"]
        return (self.data.mocap_pos[i].copy(), self.data.mocap_quat[i].copy())

    def set_joint(self, obj: str, joint: str, value: float, vel: float = 0.0) -> None:
        """Set a joint inside a prop (a scripted slide or hinge: `embodied_safety_exam.sim.movers`, 0.5.1): its position and
        velocity. Part of the state; only the episode's script calls this."""
        j = self.model.joint(f"{obj}/{joint}")
        self.data.qpos[int(j.qposadr[0])] = float(value)
        self.data.qvel[int(j.dofadr[0])] = float(vel)
        self._scratch_tick = -1
        self._ops.append([self.tick, "set_joint", obj, joint, float(value), float(vel)])

    def push(self, name: str, lin, ang=None) -> None:
        """Give a free object a velocity at this tick and leave the rest to the physics (a thing that rolls, a thing
        knocked: `embodied_safety_exam.sim.movers`, 0.5.1). `lin`: m/s in the bench frame; `ang`: rad/s in the bench frame (None:
        no spin), turned into the free joint's local frame. Part of the state (qvel); logged as the op `push`."""
        b = self.objects[name]["body_id"]
        jid = int(self.model.body_jntadr[b])
        if jid < 0 or int(self.model.jnt_type[jid]) != int(mujoco.mjtJoint.mjJNT_FREE):
            raise ValueError(f"{name!r} has no free joint")
        a, qa = int(self.model.jnt_dofadr[jid]), int(self.model.jnt_qposadr[jid])
        self.data.qvel[a:a + 3] = np.asarray(lin, dtype=np.float64)
        w = np.zeros(3) if ang is None else np.asarray(ang, dtype=np.float64)
        self.data.qvel[a + 3:a + 6] = tf.rotate(tf.quat_conj(self.data.qpos[qa + 3:qa + 7]), w)
        self._scratch_tick = -1
        self._ops.append([self.tick, "push", name, [float(v) for v in lin], None if ang is None else [float(v) for v in ang]])

    def set_ctrl(self, obj: str, actuator: str, value: float) -> None:
        """Set the target of an actuator inside a prop (a door's servo). Part of the state."""
        self.data.ctrl[self.model.actuator(f"{obj}/{actuator}").id] = float(value)
        self._ops.append([self.tick, "set_ctrl", obj, actuator, float(value)])

    def camera_pose(self, camera: str) -> tuple[np.ndarray, np.ndarray]:
        """Where a camera is and the unit direction it looks along (bench frame). Ground truth for scripts and rules
        that depend on what a camera can see (a label that faces away)."""
        s = self._sync()
        cid = self.model.camera(camera).id
        return s.cam_xpos[cid].copy(), -s.cam_xmat[cid].reshape(3, 3)[:, 2].copy()

    def set_look(self, geom: str, rgba) -> None:
        """Change how a geom is drawn (a glowing coil, a lamp, smoke). A picture only: physics never reads it."""
        self.model.geom(geom).rgba = [float(v) for v in rgba]
        self.looks[geom] = [float(v) for v in rgba]
        self._ops.append([self.tick, "set_look", geom, [float(v) for v in rgba]])

    # ---- pointing: from a pixel to a place in the scene --------------------------------------------------------------
    def pixel_ray(self, camera: str, u: float, v: float, size: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Origin and unit direction (bench frame) of the ray through pixel (u, v) of a camera image: `u` is the
        column, `v` the row, origin at the top left corner, of an image of `size` (default: the world's image size)."""
        w, h = size or self.image_size
        m, s = self.model, self._sync()
        cid = m.camera(camera).id
        f = 0.5 * h / math.tan(math.radians(float(m.cam_fovy[cid])) / 2.0)
        d_cam = np.array([(float(u) + 0.5 - w / 2.0) / f, -(float(v) + 0.5 - h / 2.0) / f, -1.0])
        rot = s.cam_xmat[cid].reshape(3, 3)
        return s.cam_xpos[cid].copy(), tf.unit(rot @ d_cam)

    def _first_hit(self, origin: np.ndarray, direction: np.ndarray, exclude_robot: bool) -> tuple | None:
        """The first drawn thing along a ray (invisible geoms and, if asked, the robot skipped): (geom, point,
        distance from the origin).

        A geom that is skipped is left out of the test and the same ray is cast again. (Casting on from a little
        behind the skipped surface lost whatever lay within that little: the undrawn contents of an empty vessel lie
        on its floor, so a ray into a beaker or a basin went through the floor and met the table under it.)"""
        m, s = self.model, self._sync()
        geomid = np.zeros(1, dtype=np.int32)
        groups = np.array([1, 1, 1, 0, 0, 0], dtype=np.uint8)          # what the cameras draw; not collision-only shapes
        skipped: list[tuple[int, int]] = []
        try:
            for _ in range(256):
                dist = mujoco.mj_ray(m, s, origin, direction, groups, 1, -1, geomid)
                if dist < 0 or geomid[0] < 0:
                    return None
                g = int(geomid[0])
                if float(m.geom_rgba[g][3]) < 0.05 or (exclude_robot and self._geom_owner[g] == "robot"):   # invisible, or asked to look past the arm
                    skipped.append((g, int(m.geom_group[g])))
                    m.geom_group[g] = _RAY_SKIP_GROUP               # out of the ray test until this call returns
                    continue
                return g, origin + direction * dist, float(dist)
            return None
        finally:
            for g, group in skipped:
                m.geom_group[g] = group

    def raycast(self, origin, direction, exclude_robot: bool = False) -> dict | None:
        """The first thing a ray meets among what is drawn: {"object", "geom", "point", "distance"} or None.
        `object` is a scene object's name, or `robot`, `table`, `floor`, `pedestal`.

        MuJoCo's ray test against a mesh is not watertight: a ray that runs exactly through an edge shared by two
        triangles can miss both (a vertical ray over the axis of a turned shape does). So a second ray is cast a
        micrometre to the side, and when it meets something more than 0.1 mm nearer, that is the answer."""
        m = self.model
        origin = np.asarray(origin, dtype=np.float64)
        direction = tf.unit(np.asarray(direction, dtype=np.float64))
        hit = self._first_hit(origin, direction, exclude_robot)
        side = tf.unit(np.cross(direction, _RAY_SIDE if abs(float(direction @ _RAY_SIDE)) < 0.9 else _RAY_SIDE_ALT))
        other = self._first_hit(origin + 1e-6 * side, direction, exclude_robot)
        if other is not None and (hit is None or other[2] < hit[2] - 1e-4):
            hit = other
        if hit is None:
            return None
        g, point, dist = hit
        return {"object": self._geom_owner[g], "geom": m.geom(g).name, "point": point, "distance": dist,
                "body": m.body(int(m.geom_bodyid[g])).name}

    def point_at(self, camera: str, u: float, v: float, size: tuple[int, int] | None = None, exclude_robot: bool = False) -> dict | None:
        """What the agent points at when it names pixel (u, v) of a camera image."""
        o, d = self.pixel_ray(camera, u, v, size)
        return self.raycast(o, d, exclude_robot=exclude_robot)

    def project(self, camera: str, point, size: tuple[int, int] | None = None) -> tuple[float, float] | None:
        """Pixel (u, v) at which a point of the scene appears in a camera image, or None if it is behind the camera.
        Ground truth for reference solutions and tests; not available to agents."""
        w, h = size or self.image_size
        m, s = self.model, self._sync()
        cid = m.camera(camera).id
        p = s.cam_xmat[cid].reshape(3, 3).T @ (np.asarray(point, dtype=np.float64) - s.cam_xpos[cid])
        if p[2] >= -1e-6:
            return None
        f = 0.5 * h / math.tan(math.radians(float(m.cam_fovy[cid])) / 2.0)
        return (float(w / 2.0 + f * p[0] / -p[2] - 0.5), float(h / 2.0 - f * p[1] / -p[2] - 0.5))

    # ---- records ---------------------------------------------------------------------------------------------------
    def save_record(self, path) -> dict:
        rows = self.record
        rec = {"format": "embodied_safety_exam.sim.record/1", "scene": self.scene, "control_dt": CONTROL_DT, "physics_dt": self.physics_dt,
               "max_target_lead": self.max_target_lead, "n_rows": int(rows.shape[0]), "visual_assets": dict(self.visual_assets),
               "rows_sha256": hashlib.sha256(np.ascontiguousarray(rows, dtype="<f8").tobytes()).hexdigest(),
               "rows": [[float(x) for x in r] for r in rows], "ops": self._ops, "state_hash": self.state_hash()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(rec))
        return rec

    @classmethod
    def replay(cls, record: dict | str | os.PathLike) -> "World":
        """Rebuild the world of a record and apply its rows, and between them what else was done to the world
        (`ops`). The caller compares `state_hash()`."""
        rec = record if isinstance(record, dict) else json.loads(Path(record).read_text())
        rows = np.array(rec["rows"], dtype=np.float64).reshape(-1, row_size(normalise_scene(rec["scene"])))
        got = hashlib.sha256(np.ascontiguousarray(rows, dtype="<f8").tobytes()).hexdigest()
        if got != rec["rows_sha256"]:
            raise ValueError("the rows of the record do not match their checksum")
        visual = rec.get("visual_assets")
        profile = visual["asset_profile"] if visual is not None else "native"
        w = cls(rec["scene"], max_target_lead=rec.get("max_target_lead"), asset_profile=profile)
        if visual is not None and visual != w.visual_assets:
            raise RuntimeError("The record's visual asset identity differs from the installed profile")
        ops = list(rec.get("ops") or [])       # grasp assist, scripted bodies, actuators of props, appearances
        k = 0
        for i in range(len(rows) + 1):
            while k < len(ops) and ops[k][0] <= i:
                getattr(w, ops[k][1])(*ops[k][2:])
                k += 1
            if i < len(rows):
                w.step(rows[i])
        return w

    # ---- reading (always from the scratch copy) --------------------------------------------------------------------
    def snapshot_view(self) -> dict:
        """The state the cameras show now, to resolve later what a picture of now showed (0.5.1, realtime: a pixel
        names what the agent's last picture showed there, though the world has moved on since)."""
        d = self.data
        return {"tick": self.tick, "time": float(d.time), "qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "act": d.act.copy(),
                "ctrl": d.ctrl.copy(), "mocap_pos": d.mocap_pos.copy(), "mocap_quat": d.mocap_quat.copy(),
                "eq_active": d.eq_active.copy()}

    @contextlib.contextmanager
    def seen(self, snap: dict | None):
        """Inside the block, reading the scene (rays, camera poses, boxes) reads it as it was at `snap`; nothing live
        changes. None: as it is now."""
        if snap is None or snap["tick"] == self.tick:
            yield
            return
        s = self._scratch
        s.time = snap["time"]
        for k in ("qpos", "qvel", "act", "ctrl", "mocap_pos", "mocap_quat", "eq_active"):
            getattr(s, k)[:] = snap[k]
        mujoco.mj_forward(self.model, s)
        self._scratch_tick = self.tick          # `_sync` takes the scratch data as current while the block runs
        try:
            yield
        finally:
            self._scratch_tick = None           # the next read syncs to the live state again

    def _sync(self) -> mujoco.MjData:
        """Copy the state into the scratch data and run the forward pass there, once per tick."""
        if self._scratch_tick != self.tick:
            d, s = self.data, self._scratch
            s.time = d.time
            s.qpos[:] = d.qpos
            s.qvel[:] = d.qvel
            s.act[:] = d.act
            s.ctrl[:] = d.ctrl
            s.mocap_pos[:] = d.mocap_pos
            s.mocap_quat[:] = d.mocap_quat
            s.eq_active[:] = d.eq_active
            s.qacc_warmstart[:] = d.qacc_warmstart
            s.qfrc_applied[:] = d.qfrc_applied
            mujoco.mj_forward(self.model, s)
            self._scratch_tick = self.tick
        return self._scratch

    def base_pose(self) -> np.ndarray:
        """Where the base stands: (x, y, yaw) in the frame of the room. Only a robot that drives has one."""
        if not self.base:
            raise ValueError(f"{self.spec.type} has no driving base")
        return self.data.qpos[self._base_qadr].copy()

    WALK_WINDOW = 25            # ticks (0.5 s): the walking G1's speed is its pelvis's mean over this long

    def base_vel(self) -> np.ndarray:
        """How fast the base moves: (vx, vy, yaw rate). On the walking G1 the mean over the last `WALK_WINDOW` ticks
        (0.5 s): a pelvis that walks sways and surges with every step (at 0.25 m/s walked its own speed peaks at 0.34),
        and the speed of a walking body is the speed at which it gets somewhere."""
        if not self.base:
            raise ValueError(f"{self.spec.type} has no driving base")
        if self.wbc is not None and len(self._walk_track) >= 2:
            (t0, p0), (t1, p1) = self._walk_track[0], self._walk_track[-1]
            dt = (t1 - t0) * CONTROL_DT
            return np.array([(p1[0] - p0[0]) / dt, (p1[1] - p0[1]) / dt, _wrap_angle(p1[2] - p0[2]) / dt])
        return self.data.qvel[self._base_dadr].copy()

    def footprint(self, pose=None) -> np.ndarray:
        """The outline of the base on the floor (a polygon, one row per corner), where it stands or at `pose`."""
        x, y, yaw = self.base_pose() if pose is None else pose
        c, s_ = math.cos(yaw), math.sin(yaw)
        pts = np.asarray(self.base["footprint"], dtype=np.float64)
        return np.stack([x + c * pts[:, 0] - s_ * pts[:, 1], y + s_ * pts[:, 0] + c * pts[:, 1]], axis=1)

    @property
    def joint_pos(self) -> np.ndarray:
        return self.data.qpos[self._arm_qadr].copy()

    @property
    def joint_vel(self) -> np.ndarray:
        return self.data.qvel[self._arm_dadr].copy()

    @property
    def gripper_pos(self) -> float:
        """Mean driver joint angle (rad): 0 open, about 0.8 closed on nothing. (A hand whose fingers are not measured
        that way gives its position in the same units: `RobotSpec.extra["driver_map"]`.)"""
        if self._drv_map is not None:
            return float(np.mean(self._drv_map[:, 0] * self.data.qpos[self._drv_qadr] + self._drv_map[:, 1]))
        return float(np.mean(self.data.qpos[self._drv_qadr]))

    @property
    def gripper_vel(self) -> float:
        if self._drv_map is not None:
            return float(np.mean(self._drv_map[:, 0] * self.data.qvel[self._drv_dadr]))
        return float(np.mean(self.data.qvel[self._drv_dadr]))

    def gripper_opening(self) -> float:
        """Free distance between the two finger pads (m)."""
        s = self._sync()
        a = s.geom_xpos[self._pads["left"][0]]
        b = s.geom_xpos[self._pads["right"][0]]
        y = s.site_xmat[self.tcp_site].reshape(3, 3)[:, 1]
        return float(abs(np.dot(a - b, y)) - 2.0 * self._pad_half_thickness)

    @property
    def ik(self):
        """The inverse-kinematics solver of this world (it has its own scratch data)."""
        if self._ik is None:
            from .ik import IK
            self._ik = IK(self)
        return self._ik

    def tcp_pose(self) -> tf.Pose:
        """Pose of the tool centre point (the pinch point between the pads) from the joint positions.

        Tool frame: `+z` out of the gripper (the approach direction), `+y` the direction the fingers close along.
        """
        s = self._sync()
        return (s.site_xpos[self.tcp_site].copy(), tf.mat_to_quat(s.site_xmat[self.tcp_site].reshape(3, 3)))

    def pad_forces(self) -> np.ndarray:
        """Normal force on the left and right finger pads (N), as a tactile pad would report it."""
        s = self._sync()
        out = np.zeros(2)
        f6 = np.zeros(6)
        for i in range(s.ncon):
            c = s.contact[i]
            for g in (c.geom1, c.geom2):
                side = self._pad_side.get(int(g))
                if side is not None and c.efc_address >= 0:
                    mujoco.mj_contactForce(self.model, s, i, f6)
                    out[0 if side == "left" else 1] += f6[0]
        return out

    def geom_owner(self, geom: int) -> str:
        """Who a geom belongs to: a scene object's name, `robot`, `table`, `floor` or `pedestal`."""
        return self._geom_owner[int(geom)]

    def add_sensor(self, spec: dict):
        """Add a sensor (see `embodied_safety_exam.sim.sensors`). It records from now on; it is not part of the state hash."""
        from . import sensors as _sensors
        if spec.get("name") in self.sensors:
            raise ValueError(f"duplicate sensor {spec.get('name')!r}")
        sensor = _sensors.build(self, spec)
        self.sensors[sensor.name] = sensor
        self._sensor_list.append(sensor)
        return sensor

    def carried_load(self) -> float:
        """Weight hanging on the gripper (N), from the wrist force: the vertical force at the flange minus the
        gripper's own weight. About m g for a held object at rest, zero when what it holds is fully supported from
        below, negative when the hand presses down. Only meaningful while the arm is not accelerating."""
        s = self._sync()
        force = s.sensordata[self._sens_force:self._sens_force + 3]
        # the sensor gives the force that holds the gripper up, in the flange frame; its world z component is the
        # weight of everything below the flange
        return float(s.site_xmat[self._ft_site].reshape(3, 3)[2] @ force) + self._hand_mass * float(self.model.opt.gravity[2])

    def wrist_wrench(self) -> tuple[np.ndarray, np.ndarray]:
        """Force and torque at the tool flange in the flange frame (N, N m), gripper weight included."""
        s = self._sync()
        return (s.sensordata[self._sens_force:self._sens_force + 3].copy(),
                s.sensordata[self._sens_torque:self._sens_torque + 3].copy())

    def render(self, camera: str, size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB image (h, w, 3) uint8 from a named camera (`front`, `top`, `wrist`)."""
        w, h = size or self.image_size
        if self._renderer is None or (self._renderer.width, self._renderer.height) != (w, h):
            if self._renderer is not None:
                self._renderer.close()
            try:
                self._renderer = mujoco.Renderer(self.model, height=h, width=w)
            except Exception as e:
                raise RuntimeError("cannot create an off-screen renderer: MUJOCO_GL must be set (egl) before mujoco is "
                                   f"first imported; import embodied_safety_exam.sim first or export MUJOCO_GL=egl ({e})") from e
        self._renderer.update_scene(self._sync(), camera=camera)
        return self._renderer.render().copy()

    def segment(self, camera: str) -> np.ndarray:
        """Which geom each pixel of a camera's picture shows (0.5.4, the mark `looked`): an int32 array (h, w) of geom
        ids, -1 where nothing is drawn (the sky, the background). The picture `render(camera)` gives, drawn by the same
        renderer with MuJoCo's segmentation colours (ids for colours, no lighting, no textures); the renderer's flags are
        put back after, so the next RGB picture is the same as it would have been. A picture only: physics and the
        state hash never read it. (A second renderer of its own is not used: under OSMesa a renderer made for a second
        model in the same process draws its segmentation pass in ordinary colours.)"""
        if self._renderer is None or (self._renderer.width, self._renderer.height) != tuple(self.image_size):
            self.render(camera)                                    # makes the renderer at the picture's size
        r = self._renderer
        r.update_scene(self._sync(), camera=camera)
        flags = r.scene.flags
        keep = flags.copy()
        flags[mujoco.mjtRndFlag.mjRND_SEGMENT] = 1
        flags[mujoco.mjtRndFlag.mjRND_IDCOLOR] = 1
        try:
            img = r.render()
        finally:
            np.copyto(flags, keep)
        seg = img[..., 0].astype(np.int32) | (img[..., 1].astype(np.int32) << 8) | (img[..., 2].astype(np.int32) << 16)
        scene = r.scene
        n = int(scene.ngeom)
        lut = np.full(n + 1, -1, dtype=np.int32)              # segmentation colour (scene index + 1) -> geom id
        geom = int(mujoco.mjtObj.mjOBJ_GEOM)
        for k in range(n):
            g = scene.geoms[k]
            if g.segid >= 0 and g.objtype == geom and g.segid + 1 <= n:
                lut[g.segid + 1] = g.objid
        seg[(seg < 0) | (seg > n)] = 0
        return lut[seg]

    def render_detail(self, point, zoom: float = 3.0, camera: str = "wrist", size: tuple[int, int] | None = None) -> np.ndarray:
        """What a camera sees of a point through a longer lens: an image from where the camera is, aimed at `point`,
        with the field of view divided by `zoom`. (The wrist camera after `look` is about 0.4 m from what it looks
        at: a label is some 60 pixels wide in its image and cannot be read; at three times that it can.)"""
        w, h = size or self.image_size
        self.render(camera, size)                                  # makes sure the renderer exists at this size
        s = self._sync()
        cid = self.model.camera(camera).id
        eye = s.cam_xpos[cid].copy()
        frame = tf.detail_camera_frame(eye, s.cam_xmat[cid].reshape(3, 3), point)
        if frame is None:
            return self.render(camera, size)
        dist, azimuth, elevation, _ = frame
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = np.asarray(point, dtype=np.float64)
        cam.distance = dist
        cam.azimuth = azimuth
        cam.elevation = elevation
        keep = float(self.model.vis.global_.fovy)
        fovy = float(self.model.cam_fovy[cid])
        self.model.vis.global_.fovy = 2.0 * math.degrees(math.atan(math.tan(math.radians(fovy) / 2.0) / float(zoom)))
        try:
            self._renderer.update_scene(s, camera=cam)
            return self._renderer.render().copy()
        finally:
            self.model.vis.global_.fovy = keep

    def observe(self, images: bool = True, cameras: tuple[str, ...] | None = None) -> dict:
        """What the agent may see: camera images and the robot's own sensors. Nothing about the objects. (On a robot
        with several arms the joints are every arm's and the hand's readings the first arm's; `arm(name).observe()`
        gives one arm's.)"""
        cameras = self.cameras if cameras is None else cameras
        force, torque = self.wrist_wrench()
        obs = {"time": self.time, "tick": self.tick, "joint_pos": self.joint_pos, "joint_vel": self.joint_vel,
               "gripper_pos": self.gripper_pos, "gripper_opening": self.gripper_opening(),
               "wrist_force": force, "wrist_torque": torque, "pad_force": self.pad_forces()}
        if images:
            obs["images"] = {c: self.render(c) for c in cameras}
        return obs

    def privileged(self) -> dict:
        """Ground truth for the hazard layer, the verifier and tests: object poses, prop joints and sites, contacts."""
        m, s = self.model, self._sync()
        objects = {}
        vel = np.zeros(6)
        for name, o in self.objects.items():
            b = o["body_id"]
            mujoco.mj_objectVelocity(m, s, mujoco.mjtObj.mjOBJ_BODY, b, vel, 0)
            objects[name] = {"pos": s.xpos[b].copy(), "quat": s.xquat[b].copy(), "angvel": vel[:3].copy(),
                             "linvel": vel[3:].copy(), "kind": o["kind"]}
        sites = {name: (s.site_xpos[i].copy(), tf.mat_to_quat(s.site_xmat[i].reshape(3, 3))) for name, i in self._prop_sites}
        joints = {name: {"pos": float(s.qpos[qa]), "vel": float(s.qvel[da])} for name, qa, da in self._prop_joints}
        contacts = []
        f6 = np.zeros(6)
        for i in range(s.ncon):
            c = s.contact[i]
            if c.efc_address < 0:
                continue
            mujoco.mj_contactForce(m, s, i, f6)
            b1, b2 = int(m.geom_bodyid[c.geom1]), int(m.geom_bodyid[c.geom2])
            g1, g2 = m.geom(int(c.geom1)).name, m.geom(int(c.geom2)).name
            o1 = self._body_owner[b1] if b1 else (static_owner(g1) if g1 else "world")
            o2 = self._body_owner[b2] if b2 else (static_owner(g2) if g2 else "world")
            contacts.append({"a": o1, "b": o2, "geom_a": g1, "geom_b": g2, "body_a": m.body(b1).name,
                             "body_b": m.body(b2).name, "force": float(f6[0]), "pos": c.pos.copy(), "dist": float(c.dist)})
        out = {"time": self.time, "tick": self.tick, "objects": objects, "sites": sites, "joints": joints,
               "contacts": contacts, "tcp": self.tcp_pose(), "gripper_target": float(self.target[-1]),
               "table_half": self.table_half}
        if self.base:                           # where the base is and how fast it moves; the outline it covers on the floor
            out["base"] = {"pose": s.qpos[self._base_qadr].copy(), "vel": self.base_vel() if self.wbc is not None else s.qvel[self._base_dadr].copy(),
                           "footprint": self.footprint()}
        if self.arm_names:                      # `tcp` is the hand of the arm that acted last; `tcps` has every hand
            out["tcps"] = {a: self.arm(a).tcp_pose() for a in self.arm_names}
            out["arm"] = self.acting
            out["tcp"] = out["tcps"][self.acting]
            out["gripper_target"] = float(self.arm(self.acting).target[-1])
        return out

    def locate(self, name: str) -> tf.Pose:
        """Pose of an object (`tube1`) or of one of its sites (`tube1/grip_0`).

        This stands in for perception: the skills use it to know where to go. It is ground truth, so it is not part
        of `observe()`; an agent working from images has to estimate these poses and pass them to the skills.
        """
        m, s = self.model, self._sync()
        if name in self.objects:
            b = self.objects[name]["body_id"]
            return (s.xpos[b].copy(), s.xquat[b].copy())
        try:
            i = m.site(name).id
        except KeyError:
            raise KeyError(f"no object or site called {name!r}") from None
        return (s.site_xpos[i].copy(), tf.mat_to_quat(s.site_xmat[i].reshape(3, 3)))

    def solid_box(self, name: str, near=None, radius: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Like `box`, of the shapes of the object that collide only: what a hand can touch. A candle's flame, the
        plant in a flower pot are drawn and not solid; a grasp is placed on what is solid. With `near` (a point of the
        bench) only the shapes whose bounding boxes come within `radius` of it horizontally (the rim of a bucket where
        the fingers go, not its handle above the middle). Ground truth, like `box`."""
        m, s = self.model, self._sync()
        gs = self._object_solids[name]
        if not len(gs):
            return self.box(name)
        rot = s.geom_xmat[gs].reshape(-1, 3, 3)
        centre = s.geom_xpos[gs] + np.einsum("nij,nj->ni", rot, m.geom_aabb[gs, :3])
        half = np.einsum("nij,nj->ni", np.abs(rot), m.geom_aabb[gs, 3:])
        lo, hi = centre - half, centre + half
        if near is not None:
            p = np.asarray(near, dtype=np.float64)[:2]
            gap = np.hypot(np.maximum(np.maximum(lo[:, 0] - p[0], p[0] - hi[:, 0]), 0.0),
                           np.maximum(np.maximum(lo[:, 1] - p[1], p[1] - hi[:, 1]), 0.0))
            keep = gap <= radius
            if not np.any(keep):
                return self.box(name)
            lo, hi = lo[keep], hi[keep]
        return lo.min(axis=0), hi.max(axis=0)

    def box(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """Lowest and highest corner of an object's bounding box in the bench frame, where it is now. Like `locate`
        a stand-in for perception; the actions use it to pass over things and to know how far a load hangs down."""
        if self._boxes[0] != self.tick or self._scratch_tick != self.tick:
            m, s = self.model, self._sync()
            rot = s.geom_xmat.reshape(-1, 3, 3)
            centre = s.geom_xpos + np.einsum("nij,nj->ni", rot, m.geom_aabb[:, :3])
            half = np.einsum("nij,nj->ni", np.abs(rot), m.geom_aabb[:, 3:])
            boxes = {}
            for n, gs in self._object_geoms.items():
                if len(gs):
                    boxes[n] = ((centre[gs] - half[gs]).min(axis=0), (centre[gs] + half[gs]).max(axis=0))
                else:
                    p = s.xpos[self.objects[n]["body_id"]].copy()
                    boxes[n] = (p, p.copy())
            self._boxes = (self.tick, boxes)
        return self._boxes[1][name]

    def ground(self, point) -> float:
        """The height of what a point is over: on the bench the table top (0); in a room the top of the furniture
        under it (things that are fixed), or the floor. The actions count their own heights (how high the hand rises
        before it swings round, how low a view may be) from here."""
        if self.room is None:
            return 0.0
        start = np.asarray(point, dtype=np.float64) + np.array([0.0, 0.0, 0.02])
        for _ in range(8):
            hit = self.raycast(start, [0.0, 0.0, -1.0], exclude_robot=True)
            if hit is None:
                return 0.0
            o = hit["object"]
            if o in self.objects and not self.objects[o]["fixed"]:       # a loose thing: what it stands on
                start = np.asarray(hit["point"], dtype=np.float64) - np.array([0.0, 0.0, 1e-3])
                continue
            return max(float(hit["point"][2]), 0.0)
        return 0.0

    def show_liquid(self, name: str, level_mm: float, rgba=None) -> float:
        """Draw the fill level of a generated vessel or tube (`embodied_safety_exam.assets.liquid.show`) for the cameras. A picture
        only: it changes a drawn geom of the model, nothing the physics uses. Returns the level drawn."""
        from embodied_safety_exam.assets import liquid as _liquid
        level = _liquid.show(self.model, self._scratch, name, level_mm, rgba)
        self._scratch_tick = -1                         # the next look is computed afresh
        return level

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


def _grip_ctrl_value(spec, target: float) -> float:
    """The gripper actuator's control value for a gripper target (0 open, `gripper_max` closed)."""
    f = min(max(float(target), 0.0), spec.gripper_max) / spec.gripper_max
    lo = float(spec.extra.get("gripper_ctrl_open", 0.0))
    return lo + f * (spec.gripper_ctrl_max - lo)


def _arm_index(m: mujoco.MjModel, mt: dict, others=()) -> dict:
    """Where one arm and its hand are in the model: the attributes the single-arm code reads (`World._index` puts the
    first arm's on the world, `Arm` each arm's on its view). `others`: the robot's other arms (their mounts)."""
    rs, ap, hp = mt["spec"], mt["arm_prefix"], mt["hand_prefix"]
    tag = "_" + mt["name"] if mt["name"] else ""
    ix: dict = {"spec": rs}
    jid = [m.joint(ap + j).id for j in rs.arm_joints]
    ix["_arm_qadr"] = np.array([m.jnt_qposadr[j] for j in jid])
    ix["_arm_dadr"] = np.array([m.jnt_dofadr[j] for j in jid])
    ix["arm_range"] = np.array([m.jnt_range[j] for j in jid])
    ix["_arm_ctrl"] = np.array([m.actuator(ap + a).id for a in rs.arm_actuators])
    # (an actuator the model gives no control range takes any target: its joint's range is what limits it)
    ix["_arm_ctrl_range"] = np.array([m.actuator_ctrlrange[a] if m.actuator_ctrllimited[a] else (-np.inf, np.inf) for a in ix["_arm_ctrl"]])
    ix["_grip_ctrl"] = m.actuator(hp + rs.gripper_actuator).id
    drivers = [m.joint(hp + j).id for j in rs.driver_joints]
    ix["_drv_qadr"] = np.array([m.jnt_qposadr[j] for j in drivers])
    ix["_drv_dadr"] = np.array([m.jnt_dofadr[j] for j in drivers])
    ix["_drv_map"] = np.array(rs.extra["driver_map"], dtype=np.float64) if "driver_map" in rs.extra else None
    ix["tcp_site"] = m.site(hp + rs.tool_site).id
    pads = {side: [m.geom(hp + g).id for g in rs.pads[side]] for side in ("left", "right")}
    ix["_pads"] = pads
    ix["_pad_names"] = {m.geom(g).name: side for side, gs in pads.items() for g in gs}
    ix["_pad_side"] = {g: side for side, gs in pads.items() for g in gs}
    ix["_pad_half_thickness"] = float(m.geom_size[pads["left"][0]][1])
    ix["_sens_force"] = m.sensor_adr[m.sensor("wrist_force" + tag).id]
    ix["_sens_torque"] = m.sensor_adr[m.sensor("wrist_torque" + tag).id]
    ix["_hand_mass"] = float(m.body_subtreemass[m.body(hp + rs.mount_body).id])
    ix["_ft_site"] = m.site("ft" + tag).id
    ix["_hand_body"] = m.body(hp + rs.hand_body).id
    if rs.hand_file:
        ix["_hand_bodies"] = frozenset(b for b in range(m.nbody) if m.body(b).name.startswith(hp))
    else:                                       # the hand is part of the arm's model: the body it begins at, and what hangs on it
        root = m.body(hp + rs.extra["hand_root"]).id
        hand = {root}
        for b in range(root + 1, m.nbody):      # a body's parent comes before it
            if int(m.body_parentid[b]) in hand:
                hand.add(b)
        ix["_hand_bodies"] = frozenset(hand)
    # The arm's own bodies, found by walking the tree (names say nothing: on a body with legs a leg's name may begin
    # as its arm's does). From the body the arm's first joint moves, up for as long as nothing of another arm hangs
    # on the same body: for an arm that is a model of its own that is all of it, pedestal link and base included;
    # for one of several arms of one body it is the arm from the shoulder down, and the trunk, the legs and the
    # base are the robot's but no arm's.
    first = lambda mount: int(m.jnt_bodyid[m.joint(mount["arm_prefix"] + mount["spec"].arm_joints[0]).id])
    foreign = {first(o) for o in others}
    root = first(mt)
    while int(m.body_parentid[root]) != 0 and not foreign & set(_subtree(m, int(m.body_parentid[root]))):
        root = int(m.body_parentid[root])
    ix["_arm_root"] = root
    ix["_arm_bodies"] = frozenset(_subtree(m, root))
    return ix


class Arm:
    """One arm of a robot that has several, with the interface the skills and the actions use of a one-arm world:
    `joint_pos`, `tcp_pose`, `ik`, `home`, `ready`, `held`, `attach`, `target` and `step` with a row of this arm alone
    (its joint targets and its gripper target; the other arms keep the targets they have). Everything that is not an
    arm's own (objects, cameras, the clock, `locate`, `privileged`) is the world's. To this arm the other arms are
    things in the scene: its collision tests report them as `other_arm`."""

    def __init__(self, world: "World", name: str):
        self.world, self.name = world, name
        mt = next(m for m in world._mounts if m["name"] == name)
        self.__dict__.update(world._ix[name])               # the arm's own indices, under the names `World` uses
        self.row_size = self.spec.n + 1
        self.arm_names = ()
        self.wrist_camera = f"wrist_{name}" if name else "wrist"
        self.home = np.array(mt["home"], dtype=np.float64)
        self.ready = np.array(mt["ready"], dtype=np.float64)
        self.ready_alt = np.array(self.spec.ready_alt, dtype=np.float64) if self.spec.ready_alt else None
        self.lead = world.lead
        self.limits = world.limits
        self._scene = {**world.scene, "robot": {**world.scene["robot"], "pos": list(mt["pos"]), "yaw_deg": mt["yaw_deg"],
                                                "home": list(mt["home"]), "ready": list(mt["ready"])}}
        k = world.arm_names.index(name) if world.arm_names else 0
        n0 = world._nb + sum(world._ix[a]["spec"].n for a in world.arm_names[:k])
        self._cols = np.arange(n0, n0 + self.spec.n)        # this arm's joints in the world's row ...
        self._gcol = world.row_size - max(len(world.arm_names), 1) + k      # ... and its gripper
        # the other arms are things in the scene; what is no arm's (a trunk, legs, a base) is this arm's own robot
        theirs = frozenset(b for a, ix in world._ix.items() if a != name for b in ix["_arm_bodies"])
        self._body_owner = [("other_arm" if (o == "robot" and b in theirs) else o) for b, o in enumerate(world._body_owner)]
        self.side = -1.0 if mt.get("mirrored") else 1.0     # which way "to its own side" is: +1 to the robot's left
        self._ik = None
        self._off_line_cache = None

    def __getattr__(self, key):                 # everything that is not an arm's own
        return getattr(self.world, key)

    @property
    def scene(self) -> dict:
        """The world's scene with this arm's own place as the robot's. On a base that drives that place is where the
        base stands now (the skills read it to tell which side of a thing is the robot's); for one of several arms
        that hang beside a body, the spot of the floor under its shoulder, which is where its reach begins."""
        if not self.world.base:
            return self._scene
        x, y, yaw = self.world.base_pose()
        if self.world.arm_names:
            x, y = self.world._sync().xpos[self._arm_root][:2]
        return {**self._scene, "robot": {**self._scene["robot"], "pos": [float(x), float(y), 0.0], "yaw_deg": math.degrees(float(yaw))}}

    # the arm's own readings: the world's code, on this arm's indices
    joint_pos = World.joint_pos
    joint_vel = World.joint_vel
    gripper_pos = World.gripper_pos
    gripper_vel = World.gripper_vel
    gripper_opening = World.gripper_opening
    tcp_pose = World.tcp_pose
    pad_forces = World.pad_forces
    carried_load = World.carried_load
    wrist_wrench = World.wrist_wrench
    ik = World.ik

    @property
    def target(self) -> np.ndarray:
        t = self.world.target
        return np.concatenate([t[self._cols], [t[self._gcol]]])

    @property
    def held(self) -> str | None:
        return self.world._held_by[self.name]

    def others_hold(self) -> tuple:
        """What the other hands hold."""
        return tuple(n for a, n in self.world._held_by.items() if a != self.name and n)

    def step(self, row) -> None:
        """Apply a row of this arm (joint targets, gripper target) for one control period; the other arms keep theirs."""
        row = np.asarray(row, dtype=np.float64)
        if row.shape == (self.world.row_size,):             # a row of the whole robot (the base driving): as it is
            self.world.step(row)
            return
        if row.shape != (self.row_size,):
            raise RowRejected(f"a row of one arm has {self.row_size} numbers, got shape {row.shape}")
        full = self.world.target.copy()
        full[self._cols] = row[:-1]
        full[self._gcol] = row[-1]
        self.world.acting = self.name
        self.world.step(full)

    def whole(self, row) -> np.ndarray:
        """A row of this arm as a row of the whole robot (the other arms and the base keeping their targets)."""
        row = np.asarray(row, dtype=np.float64)
        if row.shape == (self.world.row_size,):
            return row
        full = self.world.target.copy()
        full[self._cols] = row[:-1]
        full[self._gcol] = row[-1]
        return full

    def attach(self, name: str) -> None:
        self.world.attach(name, self.name)

    def detach(self) -> str | None:
        return self.world.detach(self.name)

    def arm(self, name: str | None = None):
        return self if name in (None, self.name) else self.world.arm(name)

    def observe(self, images: bool = True, cameras: tuple[str, ...] | None = None) -> dict:
        force, torque = self.wrist_wrench()
        obs = {"time": self.time, "tick": self.tick, "joint_pos": self.joint_pos, "joint_vel": self.joint_vel,
               "gripper_pos": self.gripper_pos, "gripper_opening": self.gripper_opening(),
               "wrist_force": force, "wrist_torque": torque, "pad_force": self.pad_forces()}
        if images:
            mine = tuple(c for c in self.world.cameras if not c.startswith("wrist")) + (self.wrist_camera,)
            obs["images"] = {c: self.world.render(c) for c in (mine if cameras is None else cameras)}
        return obs
