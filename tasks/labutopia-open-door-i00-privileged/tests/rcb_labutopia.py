"""Robot Coding Bench tooling for the LabUtopia tasks (privileged mode, the verifier's replays and the standard-mode
service all use this one module).

LabUtopia (Rui-li023/LabUtopia, a chemistry laboratory with a Franka Panda on NVIDIA Isaac Sim) comes from the base
image, with its scripted solutions removed (images/labutopia/strip_solutions.py); this module imports what is left of
it from $LABUTOPIA_ROOT and adds what a task needs:

    from rcb_labutopia import Session
    s = Session(instance="/app/instance.json")       # one Session per process (Isaac Sim starts once)
    s.step(q, qd); s.status(); s.reset(); s.replay(actions); s.save_trajectory(actions, "/app/output/trajectory.npz")

- The scene is LabUtopia's own, built the way its main.py builds it: the Franka, the laboratory's USD stage, the task
  object of the family's config, then `task.reset()` with numpy's and Python's random generators seeded with the
  instance's seed (LabUtopia draws its placements from both), then SETTLE_STEPS physics steps without a command (the
  steps LabUtopia's loop runs before its first action). Every build checks the placements against the instance
  (`instance_ok`).
- One control step is one physics step (1/60 s), LabUtopia's own rate. A row is 18 numbers: a position target and a
  velocity target for each of the Franka's 9 joints (7 arm joints, 2 finger joints), which is what LabUtopia's
  controllers send (RMPflow gives both). The targets go to the joints' PD drives, then PhysX steps once, on the CPU.
- The verdict is the family's rule, a copy of the success check of LabUtopia's controller for that task (class
  docstrings below say where each number comes from), evaluated after every control step; the first step at which it
  is met ends the episode as a success.
- An episode lasts at most MAX_STEPS control steps (600 s of simulated time), a technical cap that bounds the grader's
  replays.
- Looking never changes the physics: rendering and state reads do not step the simulation, and a Session with its
  renderer (`cameras=True`) and one without end the same rows in the same state.
- Isaac Sim 6.1.0 runs code written for 5.1 (LabUtopia's) with three adjustments, all in `_compat()`.

A fresh process repeats an episode bit for bit; reset() inside a process returns to the start only to within about
1e-5 (PhysX keeps internal state), so the grader replays a trajectory in fresh processes, and so should you before you
hand one in:  python rcb_labutopia.py replay --instance I --traj T [--out O.json] [--video V.mp4]
Generator:    python rcb_labutopia.py facts --family F --seed S
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import importlib
import json
import math
import os
import random
import sys
import time

import numpy as np

ROOT = os.environ.get("LABUTOPIA_ROOT", "/opt/labutopia")
ASSETS = os.environ.get("NVIDIA_ASSETS", "/opt/nvidia-assets")  # a mirror of what would come from NVIDIA's asset server
ASSET_HOSTS = ("omniverse-content-production.s3-us-west-2.amazonaws.com", "omniverse-content-production.s3.us-west-2.amazonaws.com")
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
CONTROL_HZ = 60
CONTROL_DT = 1.0 / CONTROL_HZ  # one control step = one physics step (LabUtopia's physics and controller rate)
SETTLE_STEPS = 5  # physics steps before the first command, as in LabUtopia's loop (its tasks return no state before)
MAX_STEPS = 36_000  # an episode lasts at most 600 s of simulated time (a technical cap: it bounds the grader's replays)
HOLD_STEPS = 60  # LabUtopia's REQUIRED_SUCCESS_STEPS: a condition counts once it has held for 60 control steps (1 s)
W, H = 512, 512  # LabUtopia's cameras, which it records at 256 x 256
RENDERS = 5  # the RTX pipeline shows a state a few frames after it was reached: frames rendered before one is read
FIRST_FRAME_TIMEOUT_S = 3600
N_DOF = 9
N_ACT = 2 * N_DOF
VEL_LIMIT = 10.0  # a velocity target is clipped to +-10 (rad/s; m/s): far above what the joints can do
TARGET_MARGIN = 0.1  # rad: an arm joint's position target may pass the joint's limit by this much
FINGER_TARGET = 0.1  # m: a finger's position target lies in [-0.1, 0.1]; its travel is [0, 0.04]
ROBOT = "/World/Franka"
TCP = ROBOT + "/panda_hand/tool_center"  # LabUtopia's "gripper position": the point between the fingertips
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])
ARM_JOINTS = [f"panda_joint{i}" for i in range(1, 8)]
# family -> (LabUtopia's config, the rule's class below)
FAMILIES = {
    "pick": ("level1_pick", "PickRule"),
    "press": ("level1_press", "PressRule"),
    "open_door": ("level1_open_door", "OpenRule"),
    "open_drawer": ("level1_open_drawer", "OpenRule"),
    "place": ("level1_place", "PlaceRule"),
    "pour": ("level1_pour", "PourRule"),
    "shake": ("level1_shake", "ShakeRule"),
    "heat_liquid": ("level2_HeatLiquid", "HeatLiquidRule"),
    "open_close": ("level2_openclose", "OpenCloseRule"),
}
_APP = None
_RENDER = False
_SESSION = None


def _log(ev: dict) -> None:
    """The agent-side interaction log (self-reported cost; never evidence)."""
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), **ev}) + "\n")
    except OSError:
        pass


@contextlib.contextmanager
def _in_root():
    """LabUtopia names its stages and robot files by paths relative to its own directory."""
    cwd = os.getcwd()
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        yield
    finally:
        os.chdir(cwd)


def _start_app(render: bool = False):
    """Isaac Sim, headless, once per process. Without `render` the application gets no Vulkan device, so its RTX
    renderer never starts: it would prepare the whole stage for rendering when the stage is loaded (5 to 15 minutes
    the first time in a container), which a process that only steps physics does not need. PhysX is not affected:
    the same rows end in the same state either way."""
    global _APP, _RENDER
    if _APP is None:
        vulkan = {k: os.environ.get(k) for k in ("VK_DRIVER_FILES", "VK_ICD_FILENAMES")}
        if not render:
            os.environ.update({k: "/nonexistent" for k in vulkan})
        from isaacsim import SimulationApp

        args = ["--/rtx/raytracing/fractionalCutoutOpacity=true",  # LabUtopia's own launch setting (its glassware)
                "--/telemetry/enableAnonymousData=false"]  # Kit's usage telemetry to NVIDIA: off
        mirror = os.path.isdir(os.path.join(ASSETS, "Assets"))
        if mirror:  # the Franka from the image, not from NVIDIA's server
            args.append(f"--/persistent/isaac/asset_root/default={ASSETS}/Assets/Isaac/6.1")
        args += os.environ.get("RCB_KIT_ARGS", "").split()  # more Kit settings, for diagnostics (make_facts.py --rendered)
        _APP = SimulationApp({"headless": True, "disable_viewport_updates": True, "extra_args": args})
        _RENDER = bool(render)
        for k, v in vulkan.items():  # processes started from this one get the environment they would have had
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        if mirror:
            # LabUtopia's stages reference a cabinet and four materials by URL on NVIDIA's asset server: the image has
            # them, and the server's URLs are redirected there (nothing is fetched at run time).
            import omni.client

            for scheme in ("http", "https"):
                for host in ASSET_HOSTS:
                    omni.client.set_alias(f"{scheme}://{host}", ASSETS)
        _compat()
        # Isaac Sim's own exit handler ends the process with status 0, whatever happened: a script that dies with an
        # exception would look like one that worked. Registered after it, this runs before it.
        sys.excepthook = _excepthook
        atexit.register(_at_exit)
    elif render and not _RENDER:
        raise RuntimeError("Isaac Sim was started without its renderer in this process: start it with Session(..., cameras=True)")
    return _APP


_FAILED = []


def _excepthook(kind, value, tb) -> None:
    _FAILED.append(kind.__name__)
    sys.__excepthook__(kind, value, tb)


def _at_exit() -> None:
    if _FAILED:
        finish(1)


def _compat() -> None:
    """LabUtopia is written for Isaac Sim 5.1; what 6.1 needs to run it unchanged."""
    import omni.kit.commands
    from isaacsim.core.utils import extensions
    from pxr import Gf

    extensions.enable_extension("omni.physx.bundle")  # as LabUtopia's main.py
    # 1. The interfaces LabUtopia imports are deprecated extensions in 6.x, not loaded by default. A sibling extension
    #    (isaacsim.sensors.physics.nodes, ...) may have been imported first, which leaves a namespace package under the
    #    deprecated extension's name: drop it so that the package proper is imported.
    for ext in ("isaacsim.sensors.physics", "isaacsim.sensors.camera", "isaacsim.robot.manipulators",
                "isaacsim.robot_motion.motion_generation"):
        extensions.enable_extension(ext)
        mod = sys.modules.get(ext)
        if mod is not None and getattr(mod, "__file__", None) is None:
            del sys.modules[ext]
            importlib.import_module(ext)
    # 2. isaacsim.core.utils.semantics.add_update_semantics is gone (the labels API replaces it); LabUtopia imports it
    #    for its segmentation cameras, which no task here uses.
    import isaacsim.core.utils.semantics as sem

    if not hasattr(sem, "add_update_semantics"):
        def add_update_semantics(prim, semantic_label, type_label="class", suffix=""):
            sem.add_labels(prim, labels=[semantic_label], instance_name=type_label)

        sem.add_update_semantics = add_update_semantics
    # 3. ContactSensor: 5.1 creates a sensor under a rigid body whose colliders are child prims; 6.x refuses (its check
    #    runs even when the sensor prim does not exist yet). LabUtopia's Franka creates one on each finger and never
    #    reads them: the prim is created as 5.1 created it, without the Python wrapper.
    import isaacsim.sensors.physics as sp

    if not getattr(sp.ContactSensor, "_rcb", False):
        class ContactSensor(sp.ContactSensor):
            _rcb = True

            def __init__(self, prim_path, name="contact_sensor", frequency=None, dt=None, translation=None,
                         position=None, min_threshold=None, max_threshold=None, radius=None):
                try:
                    super().__init__(prim_path, name=name, frequency=frequency, dt=dt, translation=translation,
                                     position=position, min_threshold=min_threshold, max_threshold=max_threshold,
                                     radius=radius)
                except Exception as exc:  # noqa: BLE001
                    if "collision api" not in str(exc):
                        raise
                    omni.kit.commands.execute(
                        "IsaacSensorCreateContactSensor", path="/" + prim_path.split("/")[-1],
                        parent="/".join(prim_path.split("/")[:-1]), min_threshold=min_threshold or 0,
                        max_threshold=max_threshold or 100000, color=Gf.Vec4f(1, 1, 1, 1),
                        radius=-1 if radius is None else radius,
                        sensor_period=(1.0 / frequency) if frequency else (dt or CONTROL_DT),
                    )

        sp.ContactSensor = ContactSensor


# ----------------------------------------------------------------------------------------------- the rules
class _Rule:
    """A family's success rule. `start(s)` reads what the rule compares against at the frozen initial state (LabUtopia's
    controllers do the same at their first step); `update(s)` is called after every control step and returns True at
    the step at which the rule is met. Positions come from LabUtopia's own readers (`utils/object_utils.py`):
    `centre` is the centre of an object's bounding box, `origin` the position of a prim's frame, `hand` the point
    between the Franka's fingertips (LabUtopia's "gripper position")."""

    text = ""

    def __init__(self, s: "Session"):
        self.s = s
        self.hold = 0
        self.phase = ""

    def _held(self, ok: bool) -> bool:
        """LabUtopia's success counter: consecutive control steps with the condition true, 60 needed."""
        self.hold = self.hold + 1 if ok else 0
        return self.hold >= HOLD_STEPS

    def start(self) -> None:
        raise NotImplementedError

    def update(self) -> bool:
        raise NotImplementedError

    def values(self) -> dict:
        """What the rule looks at, at the current state (for an agent in privileged mode and for the docs)."""
        return {}

    def state(self) -> dict:
        return {"phase": self.phase, "hold": int(self.hold)}


class PickRule(_Rule):
    """controllers/pick_controller.py `_check_success`: the object's centre more than 0.1 m above where it started,
    for 60 consecutive control steps."""

    text = "the object's centre is more than 0.10 m above where it started, for 60 consecutive control steps (1 s)"

    def start(self) -> None:
        self.obj = self.s.task.current_obj_path
        self.z0 = float(self.s.centre(self.obj)[2])

    def values(self) -> dict:
        return {"object": self.obj, "lift_m": float(self.s.centre(self.obj)[2]) - self.z0}

    def update(self) -> bool:
        return self._held(float(self.s.centre(self.obj)[2]) > self.z0 + 0.1)


class PressRule(_Rule):
    """controllers/press_controller.py `_check_success`: the target button's moving part beyond x = 0.405 m (it is
    placed at x = 0.40 and is pushed in along +x), for 60 consecutive control steps."""

    text = "the target button's cap is pushed in beyond x = 0.405 m (it starts at x = 0.40), for 60 consecutive control steps (1 s)"

    def start(self) -> None:
        self.button = str(self.s.cfg.sub_obj_path)

    def values(self) -> dict:
        return {"button": self.button, "x_m": float(self.s.origin(self.button)[0])}

    def update(self) -> bool:
        return self._held(float(self.s.origin(self.button)[0]) > 0.405)


class OpenRule(_Rule):
    """controllers/open_controller.py `_check_success`: the handle's centre more than 0.12 m from where it started and
    the hand more than 0.04 m from the handle (released), for 60 consecutive control steps."""

    text = ("the handle's centre is more than 0.12 m from where it started and the hand is more than 0.04 m from the "
            "handle's centre (the handle is released), for 60 consecutive control steps (1 s)")
    MOVE, AWAY = 0.12, 0.04

    def start(self) -> None:
        self.handle = self.s.task.current_sub_obj_path
        self.h0 = self.s.centre(self.handle)

    def values(self) -> dict:
        h = self.s.centre(self.handle)
        return {"handle": self.handle, "moved_m": float(np.linalg.norm(h - self.h0)), "hand_to_handle_m": float(np.linalg.norm(self.s.hand() - h))}

    def _cond(self) -> bool:
        h = self.s.centre(self.handle)
        return bool(np.linalg.norm(h - self.h0) > self.MOVE and np.linalg.norm(self.s.hand() - h) > self.AWAY)

    def update(self) -> bool:
        return self._held(self._cond())


class OpenCloseRule(_Rule):
    """controllers/openclose_controller.py, for a drawer (`operate_type: drawer`, the config's): `_check_open_success`
    (the handle more than 0.13 m from where it started, the hand more than 0.04 m from it) for 60 consecutive control
    steps; then, measured from where the handle is at that moment, `_check_close_success` (the handle more than 0.13 m
    from there, the hand more than 0.04 m from it) for 60 consecutive control steps. Two differences. LabUtopia moves
    on to its second check when its scripted opening has ended; here it starts at the step the first is met. And
    LabUtopia's second check does not look at the direction, so a drawer pulled a further 0.13 m out would pass it;
    here the handle also has to be nearer to where it started than it was at that moment (it has come back)."""

    text = ("first the handle's centre is more than 0.13 m from where it started with the hand more than 0.04 m from "
            "it, for 60 consecutive control steps (opened and released); then, measured from where the handle is at "
            "that moment, the handle is more than 0.13 m from there and nearer to where it started than it was, with "
            "the hand more than 0.04 m from it, for 60 consecutive control steps (closed and released)")

    def start(self) -> None:
        kind = str(self.s.cfg.task.get("operate_type", "door"))
        if kind != "drawer":
            raise RuntimeError(f"OpenCloseRule is written for a drawer, the config says {kind!r}")
        self.handle = self.s.task.current_sub_obj_path
        self.h0 = self.s.centre(self.handle)
        self.ref = self.h0
        self.phase = "open"

    def values(self) -> dict:
        h = self.s.centre(self.handle)
        return {"handle": self.handle, "phase": self.phase, "moved_m": float(np.linalg.norm(h - self.ref)),
                "from_start_m": float(np.linalg.norm(h - self.h0)), "hand_to_handle_m": float(np.linalg.norm(self.s.hand() - h))}

    def update(self) -> bool:
        h = self.s.centre(self.handle)
        ok = bool(np.linalg.norm(h - self.ref) > 0.13 and np.linalg.norm(self.s.hand() - h) > 0.04)
        if self.phase == "open":
            if self._held(ok):
                self.phase, self.hold, self.ref = "close", 0, h
            return False
        return self._held(ok and bool(np.linalg.norm(h - self.h0) < np.linalg.norm(self.ref - self.h0)))


class PlaceRule(_Rule):
    """controllers/place_controller.py `_check_phase_success`: the object lifted more than 0.1 m above where it
    started; then its centre within 0.05 m (horizontally) of the target's centre and within 0.05 m of its initial
    height. LabUtopia evaluates the second check once its scripted placing has ended (the gripper open, the hand
    withdrawn). Here it has to hold for 60 consecutive control steps with the hand more than 0.05 m from the object's
    centre, the release condition of controllers/pickplace_controller.py `is_success`."""

    text = ("the object's centre has been more than 0.10 m above where it started; after that it is within 0.05 m "
            "(horizontally) of the target's centre and within 0.05 m of its initial height, with the hand more than "
            "0.05 m from the object's centre (released), for 60 consecutive control steps (1 s)")

    def start(self) -> None:
        self.obj, self.target = self.s.task.source_obj, self.s.task.target_obj
        self.z0 = float(self.s.centre(self.obj)[2])
        self.phase = "pick"

    def values(self) -> dict:
        c, t = self.s.centre(self.obj), self.s.centre(self.target)
        return {"object": self.obj, "target": self.target, "phase": self.phase, "lift_m": float(c[2] - self.z0),
                "horizontal_distance_m": float(np.linalg.norm(c[:2] - t[:2])), "hand_to_object_m": float(np.linalg.norm(self.s.hand() - c))}

    def update(self) -> bool:
        c = self.s.centre(self.obj)
        if self.phase == "pick":
            if c[2] > self.z0 + 0.1:
                self.phase = "place"
            return False
        t = self.s.centre(self.target)
        return self._held(bool(np.linalg.norm(c[:2] - t[:2]) < 0.05 and abs(c[2] - self.z0) < 0.05
                               and np.linalg.norm(self.s.hand() - c) > 0.05))


class PourRule(_Rule):
    """controllers/pour_controller.py `_check_phase_success`, step for step. Picking: the container's centre more than
    0.12 m above where it started. Pouring, counted only at steps at which the container's centre is within the pour
    distance of the target's centre (horizontally; LabUtopia's `get_pour_threshold` of the container + 0.05 m): the
    container turned more than 50 degrees from its orientation at the first pouring step; then back to within 30
    degrees of it; then, more than 0.05 m above where it started, 84 control steps (LabUtopia adds 0.012 to a timer
    per step until it reaches 1.0)."""

    text = ("the container's centre has been more than 0.12 m above where it started; then, counted only while its "
            "centre is within the pour distance of the target container's centre (horizontally), it has been turned "
            "more than 50 degrees, then brought back to within 30 degrees of its orientation before the turn, and then "
            "stays more than 0.05 m above where it started for 84 control steps (1.4 s)")

    def start(self) -> None:
        from utils.task_utils import TaskUtils

        self.tu = TaskUtils.get_instance()
        self.obj, self.target = self.s.task.current_obj_path, str(self.s.task.target_path)
        self.name = self.obj.split("/")[-1]
        self.z0 = float(self.s.centre(self.obj)[2])
        self.phase, self.q0, self.poured, self.returned, self.timer = "pick", None, False, False, 0.0

    def _quat(self):
        return np.asarray(self.s.objects.get_transform_quat(object_path=self.obj + "/mesh"), dtype=np.float64)

    def _reach(self) -> float:
        return float(self.tu.get_pour_threshold(self.name, self.s.size(self.obj)) + 0.05)

    def values(self) -> dict:
        c, t, q = self.s.centre(self.obj), self.s.centre(self.target), self._quat()
        q0 = q if self.q0 is None else self.q0
        if np.dot(q0, q) < 0:
            q = -q
        from scipy.spatial.transform import Rotation as R

        ang = float(np.degrees(np.linalg.norm((R.from_quat(q0).inv() * R.from_quat(q)).as_rotvec())))
        return {"container": self.obj, "target": self.target, "phase": self.phase, "lift_m": float(c[2] - self.z0),
                "horizontal_distance_m": float(np.linalg.norm(c[:2] - t[:2])), "pour_distance_m": self._reach(),
                "turned_deg": ang, "poured": bool(self.poured), "returned": bool(self.returned), "timer": round(self.timer, 3)}

    def state(self) -> dict:
        return {"phase": self.phase, "poured": bool(self.poured), "returned": bool(self.returned),
                "timer": round(self.timer, 6), "q0": None if self.q0 is None else [float(v) for v in self.q0]}

    def update(self) -> bool:
        c = self.s.centre(self.obj)
        if self.phase == "pick":
            if c[2] > self.z0 + 0.12:
                self.phase = "pour"
            return False
        q = self._quat()
        if self.q0 is None:
            self.q0 = q
            return False
        if np.linalg.norm(c[:2] - self.s.centre(self.target)[:2]) > self._reach():
            return False
        if not self.poured:
            self.poured = bool(self.tu.check_rotation_angle(self.q0, q, threshold_degrees=50))
            return False
        if not self.returned:
            if not self.tu.check_rotation_angle(self.q0, q, threshold_degrees=30):
                self.returned, self.timer = True, 0.0
            return False
        if c[2] > self.z0 + 0.05:
            self.timer += 0.012
            return self.timer >= 1.0
        return False


class ShakeRule(_Rule):
    """controllers/shake_controller.py `is_success`, step for step; nothing is counted at a step at which the beaker's
    centre is less than 0.05 m above where it started. Five times: the centre gets 0.05 m or more (horizontally) from
    where it was when this count began. Then the centre stays within 0.01 m in x and in y over 60 control steps.
    LabUtopia starts counting when its scripted pick has ended; here counting starts with the episode."""

    text = ("counted only while the beaker's centre is at least 0.05 m above where it started: five times in a row "
            "the centre moves 0.05 m or more (horizontally) from where it was when that count began; after the fifth, "
            "the centre stays within 0.01 m in x and in y over 60 control steps (1 s)")

    def start(self) -> None:
        self.obj = str(self.s.task.source_beaker)
        self.z0 = float(self.s.centre(self.obj)[2])
        self.count, self.anchor, self.window = 0, None, []

    def values(self) -> dict:
        c = self.s.centre(self.obj)
        return {"beaker": self.obj, "lift_m": float(c[2] - self.z0), "moves_counted": int(self.count), "still_steps": len(self.window)}

    def state(self) -> dict:
        return {"count": int(self.count), "anchor": None if self.anchor is None else [float(v) for v in self.anchor],
                "window": len(self.window), "window_sum": float(np.sum(self.window)) if self.window else 0.0}

    def update(self) -> bool:
        c = self.s.centre(self.obj)
        if c[2] - self.z0 < 0.05:
            return False
        xy = np.array(c[:2], dtype=np.float64)
        if self.count < 5:
            if self.anchor is None:
                self.anchor = xy
            elif np.linalg.norm(xy - self.anchor) >= 0.05:
                self.count += 1
                self.anchor = None
            return False
        self.window.append(xy)
        if len(self.window) >= HOLD_STEPS:
            arr = np.array(self.window)
            if np.all(arr.max(axis=0) - arr.min(axis=0) <= 0.01):
                return True
            self.window.pop(0)
        return False


class HeatLiquidRule(_Rule):
    """controllers/placepress_controller.py `_check_phase_success`, in its order. The beaker's centre above z = 0.82 m;
    then the beaker on the heater's plate (its centre at or below z = 0.86 m and within 0.05 m in x and in y of the
    plate's frame); then the same with the heater's button pressed (the button's frame below z = 0.761 m). LabUtopia
    evaluates each check when the scripted motion of that phase has ended; here each is taken at the first step at
    which it holds."""

    text = ("the beaker's centre has been above z = 0.82 m; after that the beaker is on the heater's plate (its centre "
            "at or below z = 0.86 m and within 0.05 m in x and in y of the plate's centre); and, with the beaker "
            "there, the heater's button is pressed (the button below z = 0.761 m)")

    def start(self) -> None:
        t = self.s.task
        self.obj, self.plate, self.button = str(t.source_beaker), str(t.target_sub_plat), str(t.button)
        self.phase = "pick"

    def _on_plate(self, c) -> bool:
        p = self.s.origin(self.plate)
        return bool(c[2] <= 0.86 and abs(c[0] - p[0]) < 0.05 and abs(c[1] - p[1]) < 0.05)

    def values(self) -> dict:
        c, p = self.s.centre(self.obj), self.s.origin(self.plate)
        return {"beaker": self.obj, "plate": self.plate, "button": self.button, "phase": self.phase,
                "beaker_z_m": float(c[2]), "dx_m": float(c[0] - p[0]), "dy_m": float(c[1] - p[1]),
                "button_z_m": float(self.s.origin(self.button)[2])}

    def update(self) -> bool:
        c = self.s.centre(self.obj)
        if self.phase == "pick":
            if c[2] > 0.82:
                self.phase = "place"
            return False
        if self.phase == "place":
            if self._on_plate(c):
                self.phase = "press"
            return False
        return bool(self._on_plate(c) and self.s.origin(self.button)[2] < 0.761)


RULES = {c.__name__: c for c in (PickRule, PressRule, OpenRule, OpenCloseRule, PlaceRule, PourRule, ShakeRule, HeatLiquidRule)}


# ----------------------------------------------------------------------------------------------- kinematics
def _quat_to_mat(q) -> np.ndarray:
    w, x, y, z = (float(v) for v in q)
    n = math.sqrt(w * w + x * x + y * y + z * z)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _mat_to_quat(R) -> np.ndarray:
    """wxyz, w >= 0."""
    m = np.asarray(R, dtype=np.float64)
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return -q if q[0] < 0 else q


def _T(p, R) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, p
    return T


def _pose7(T) -> list:
    return [*(float(v) for v in T[:3, 3]), *(float(v) for v in _mat_to_quat(T[:3, :3]))]


def _rotvec(R) -> np.ndarray:
    """Rotation vector of a rotation matrix."""
    c = max(-1.0, min(1.0, (np.trace(R) - 1.0) / 2.0))
    ang = math.acos(c)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    if ang < 1e-9:
        return v / 2.0
    if abs(ang - math.pi) < 1e-6:  # near a half turn: the axis from the diagonal
        a = np.sqrt(np.maximum((np.diag(R) + 1.0) / 2.0, 0.0))
        a = a * np.where(v < 0, -1.0, 1.0) if np.linalg.norm(v) > 1e-9 else a
        return a / max(np.linalg.norm(a), 1e-12) * ang
    return v / (2.0 * math.sin(ang)) * ang


class Arm:
    """The Franka's kinematics as a chain read from the stage (the seven revolute joints of the articulation, the fixed
    joint to the hand, and the frames on the hand): numpy only, the simulation is never touched."""

    def __init__(self, stage, xf_world):
        from pxr import UsdPhysics

        def frame(pos, rot) -> np.ndarray:
            q = [rot.GetReal(), *rot.GetImaginary()] if rot is not None else [1, 0, 0, 0]
            return _T([float(v) for v in (pos or (0, 0, 0))], _quat_to_mat(q))

        self.joints = []
        for i in range(1, 8):
            prim = stage.GetPrimAtPath(f"{ROBOT}/panda_link{i - 1}/panda_joint{i}")
            j = UsdPhysics.RevoluteJoint(prim)
            axis = {"X": 0, "Y": 1, "Z": 2}[str(j.GetAxisAttr().Get())]
            self.joints.append((frame(j.GetLocalPos0Attr().Get(), j.GetLocalRot0Attr().Get()),
                                np.linalg.inv(frame(j.GetLocalPos1Attr().Get(), j.GetLocalRot1Attr().Get())), axis))
        self.lo = np.radians([float(UsdPhysics.RevoluteJoint(stage.GetPrimAtPath(f"{ROBOT}/panda_link{i - 1}/panda_joint{i}")).GetLowerLimitAttr().Get()) for i in range(1, 8)])
        self.hi = np.radians([float(UsdPhysics.RevoluteJoint(stage.GetPrimAtPath(f"{ROBOT}/panda_link{i - 1}/panda_joint{i}")).GetUpperLimitAttr().Get()) for i in range(1, 8)])
        fj = UsdPhysics.Joint(stage.GetPrimAtPath(f"{ROBOT}/panda_link7/panda_hand_joint"))
        self.link7_T_hand = frame(fj.GetLocalPos0Attr().Get(), fj.GetLocalRot0Attr().Get()) @ np.linalg.inv(
            frame(fj.GetLocalPos1Attr().Get(), fj.GetLocalRot1Attr().Get()))
        self.base = xf_world(f"{ROBOT}/panda_link0")  # the arm is fixed to the bench
        hand = xf_world(f"{ROBOT}/panda_hand")
        self.hand_T = {"tcp": np.linalg.inv(hand) @ xf_world(TCP), "panda_hand": np.eye(4)}

    def chain(self, q) -> list:
        """World transforms of panda_link1..7 for seven joint positions."""
        T, out = self.base.copy(), []
        for (A, Binv, axis), qi in zip(self.joints, q):
            c, s = math.cos(qi), math.sin(qi)
            Rq = np.eye(4)
            i, j = (axis + 1) % 3, (axis + 2) % 3
            Rq[i, i], Rq[i, j], Rq[j, i], Rq[j, j] = c, -s, s, c
            T = T @ A @ Rq @ Binv
            out.append(T)
        return out

    def fk(self, q, frame: str = "tcp") -> np.ndarray:
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        if q.shape[0] != 7 or not np.all(np.isfinite(q)):
            raise ValueError("q is 7 finite joint positions (panda_joint1..7)")
        return self.chain(q)[-1] @ self.link7_T_hand @ self.hand_T[frame]

    def jacobian(self, q, frame: str = "tcp") -> np.ndarray:
        """6 x 7 geometric Jacobian of the frame's origin (world frame): linear rows, then angular rows."""
        links = self.chain(q)
        p = (links[-1] @ self.link7_T_hand @ self.hand_T[frame])[:3, 3]
        J = np.zeros((6, 7))
        T = self.base
        for k, (A, _Binv, axis) in enumerate(self.joints):
            Tj = T @ A  # the joint's frame before its rotation
            z = Tj[:3, axis]
            J[:3, k] = np.cross(z, p - Tj[:3, 3])
            J[3:, k] = z
            T = links[k]
        return J

    def ik(self, target, seed, frame: str = "tcp", tol_pos_m: float = 1e-3, tol_rot_rad: float = 1e-2, max_iters: int = 300) -> dict:
        """Damped least squares within the joint limits, no collision check. target: x y z + wxyz quaternion (world)."""
        tgt = np.asarray(target, dtype=np.float64).reshape(-1)
        q = np.clip(np.asarray(seed, dtype=np.float64).reshape(-1).copy(), self.lo, self.hi)
        Rt = _quat_to_mat(tgt[3:7])
        use_rot = tol_rot_rad < 3.1

        def err(qa):
            T = self.fk(qa, frame)
            return tgt[:3] - T[:3, 3], _rotvec(Rt @ T[:3, :3].T)

        lam = 1e-3
        e_p, e_r = err(q)
        for _ in range(int(max_iters)):
            if np.linalg.norm(e_p) < tol_pos_m and (not use_rot or np.linalg.norm(e_r) < tol_rot_rad):
                break
            J = self.jacobian(q, frame)
            J = J if use_rot else J[:3]
            e = np.concatenate([e_p, e_r]) if use_rot else e_p
            dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(len(e)), e)
            n = np.linalg.norm(dq)
            if n > 0.3:
                dq *= 0.3 / n
            qn = np.clip(q + dq, self.lo, self.hi)
            n_p, n_r = err(qn)
            if np.linalg.norm(np.concatenate([n_p, n_r]) if use_rot else n_p) < np.linalg.norm(e):
                q, e_p, e_r, lam = qn, n_p, n_r, max(lam / 2, 1e-7)
            else:
                lam = min(lam * 4, 1e3)
                if lam >= 1e3:
                    break
        ep, er = float(np.linalg.norm(e_p)), float(np.linalg.norm(e_r))
        return {"ok": bool(ep < tol_pos_m and (not use_rot or er < tol_rot_rad)), "q": q.tolist(), "error": (ep, er)}


# ----------------------------------------------------------------------------------------------- the session
class Session:
    def __init__(self, family: str | None = None, instance: str = "/app/instance.json", cameras: bool = False):
        """`cameras=True` starts Isaac Sim with its RTX renderer and makes the task's cameras: needed for render_frame,
        and slow the first time in a container (the renderer prepares the whole stage once: 5 to 15 minutes). Without
        it the Session only simulates, and starts in about a minute the first time, about 20 s later."""
        global _SESSION
        if _SESSION is not None:
            raise RuntimeError("one Session per process: Isaac Sim holds one stage (use reset(), or a new process)")
        self.instance = json.load(open(instance))
        self.family = family or self.instance["family"]
        if self.family != self.instance["family"] or self.family not in FAMILIES:
            raise ValueError(f"family {self.family!r} does not match the instance ({self.instance['family']!r})")
        self.config, rule = FAMILIES[self.family]
        self.seed = int(self.instance["seed"])
        self.dt = CONTROL_DT
        self.rule_name = "first"
        self.resets = -1
        self.total_steps = 0
        self._rec = None
        self._render_key = None
        self._want_cameras = bool(cameras)
        self.first_frame_s = None
        self._stop_at_success = True  # False only while a reference is recorded (make_facts.py compares the verdicts)
        t0 = time.time()
        self.app = _start_app(render=bool(cameras))
        self._build()
        self.rule = RULES[rule](self)
        self._reset_task()
        self.arm = Arm(self.stage, self._xf)
        self.build_s = round(time.time() - t0, 1)
        self.placement_sha = self._placement_sha()
        self.init_sha = self.state_sha()
        self.instance_ok = bool(self.placement_sha == self.instance.get("placement_sha"))
        self.start_exact = bool(self.init_sha == self.instance.get("init_sha"))
        _SESSION = self
        atexit.register(self.close)
        _log({"ev": "session_start", "family": self.family, "instance_ok": self.instance_ok, "build_s": self.build_s})

    # ------------------------------------------------------------------------------------------- the scene
    def _build(self) -> None:
        """LabUtopia's main.py, up to the first reset."""
        import omni.usd
        from omegaconf import OmegaConf
        from pxr import UsdPhysics

        with _in_root():
            from isaacsim.core.api import World
            from isaacsim.core.utils.stage import add_reference_to_stage

            from factories.robot_factory import create_robot
            from factories.task_factory import create_task
            from utils.object_utils import ObjectUtils

            cfg = OmegaConf.load(os.path.join(ROOT, "config", f"{self.config}.yaml"))
            self.camera_cfgs = list(cfg.cameras)
            cfg.cameras = []  # the Session makes the cameras itself: LabUtopia's task object then renders nothing
            cfg.multi_run = {"run_dir": "/tmp/labutopia_run"}
            cfg.hydra = {}
            self.cfg = cfg
            self.world = World(stage_units_in_meters=1.0, physics_prim_path="/physicsScene", backend="numpy")
            self.robot = create_robot(cfg.robot.type, position=np.array(cfg.robot.position))
            self.stage = omni.usd.get_context().get_stage()
            add_reference_to_stage(usd_path=os.path.abspath(cfg.usd_path), prim_path="/World")
            self.objects = ObjectUtils.get_instance(self.stage)
            state = (np.random.get_state(), random.getstate())
            np.random.seed(self.seed)
            random.seed(self.seed)
            self.task = create_task(cfg.task_type, cfg=cfg, world=self.world, stage=self.stage, robot=self.robot)
            np.random.set_state(state[0])
            random.setstate(state[1])
        assert abs(float(self.world.get_physics_dt()) - CONTROL_DT) < 1e-12, self.world.get_physics_dt()
        self._bodies = sorted((p for p in self.stage.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)), key=lambda p: str(p.GetPath()))
        self._cams = {}
        self._cam_names = ["wrist_cam" if str(c.prim_path).startswith(ROBOT + "/") else str(c.name) for c in self.camera_cfgs]

    def _reset_task(self) -> None:
        """LabUtopia's own reset with the instance's seed, then the steps its loop runs before the first command."""
        state = (np.random.get_state(), random.getstate())  # the caller's random streams are kept
        np.random.seed(self.seed)
        random.seed(self.seed)
        with _in_root():
            self.task.reset()
        np.random.set_state(state[0])
        random.setstate(state[1])
        self.ctrl = self.robot.get_articulation_controller()
        if self.resets < 0:
            assert list(self.robot.dof_names) == ARM_JOINTS + ["panda_finger_joint1", "panda_finger_joint2"], self.robot.dof_names
            dp = self.robot.dof_properties
            self.q_lo, self.q_hi = np.array(dp["lower"], dtype=np.float64), np.array(dp["upper"], dtype=np.float64)
            self._kp, self._kd = np.array(dp["stiffness"], dtype=np.float64), np.array(dp["damping"], dtype=np.float64)
            self._max_effort = np.array(dp["maxEffort"], dtype=np.float64)
            # A target may lie beyond a joint's range (the joint stops at its limit, the drive keeps pushing): LabUtopia's
            # controllers close the fingers with targets down to -0.08 m, open them with 0.05 m, and RMPflow's arm
            # targets pass a limit by a few mrad.
            lo, hi = self.q_lo - TARGET_MARGIN, self.q_hi + TARGET_MARGIN
            lo[7:], hi[7:] = -FINGER_TARGET, FINGER_TARGET
            self.a_lo = np.concatenate([lo, np.full(N_DOF, -VEL_LIMIT)])
            self.a_hi = np.concatenate([hi, np.full(N_DOF, VEL_LIMIT)])
        if self._want_cameras and not self._cams:
            self._make_cameras()
        for _ in range(SETTLE_STEPS):
            self.world.step(render=False)
        self.resets += 1
        self.steps = 0
        self.done = False
        self.success = False
        self.reason = None
        self._render_key = None
        self.first_success_step = None
        self.rule.hold, self.rule.phase = 0, ""
        self.rule.start()

    def reset(self) -> None:
        """Back to the initial state (LabUtopia's reset with the instance's seed). Inside one process this repeats the
        start only to within about 1e-5: the grader replays in fresh processes, see `replay` in the module docstring."""
        self._reset_task()
        if self._rec is not None:
            self._rec = []
        _log({"ev": "reset"})

    # ------------------------------------------------------------------------------------------- episode
    def _row(self, q, qd=None) -> np.ndarray:
        q = np.asarray(q, dtype=np.float64).reshape(-1)
        if q.shape[0] == N_ACT and qd is None:
            q, qd = q[:N_DOF], q[N_DOF:]
        qd = np.zeros(N_DOF) if qd is None else np.asarray(qd, dtype=np.float64).reshape(-1)
        if q.shape[0] != N_DOF or qd.shape[0] != N_DOF or not (np.all(np.isfinite(q)) and np.all(np.isfinite(qd))):
            raise ValueError(f"an action is {N_DOF} position targets and {N_DOF} velocity targets (finite numbers)")
        return np.clip(np.concatenate([q, qd]), self.a_lo, self.a_hi).astype(np.float32).astype(np.float64)

    def step(self, q, qd=None, n: int = 1) -> bool:
        """One control step (1/60 s): position targets `q` (9: panda_joint1..7, then the two finger joints) and
        velocity targets `qd` (9, zeros when omitted) to the joints' drives, or one row of 18 (q, then qd); or `n`
        steps holding them. Targets are stored as float32 (PhysX's own precision) and clipped to action_limits().
        Returns False once the episode is over (then nothing is executed until reset())."""
        from isaacsim.core.utils.types import ArticulationAction

        a = self._row(q, qd)
        if self.done:
            return False
        for _ in range(int(n)):
            self.ctrl.apply_action(ArticulationAction(joint_positions=a[:N_DOF], joint_velocities=a[N_DOF:]))
            self.world.step(render=False)
            self.steps += 1
            self.total_steps += 1
            if self._rec is not None:
                self._rec.append(a.copy())
            self._judge()
            if not self.done and self.steps >= MAX_STEPS:
                self.done, self.reason = True, "max_control_steps"
            if self.done:
                break
        return not self.done

    def _judge(self) -> None:
        if self.rule.update():
            if self.first_success_step is None:
                self.first_success_step = int(self.steps)
            if self._stop_at_success:
                self.done, self.success, self.reason = True, True, "success"

    def command(self) -> np.ndarray:
        """The 18 targets in effect: positions, then velocities (after reset: LabUtopia's initial targets)."""
        a = self.robot.get_applied_action()
        qd = np.zeros(N_DOF) if a.joint_velocities is None else np.asarray(a.joint_velocities, dtype=np.float64)
        return np.concatenate([np.asarray(a.joint_positions, dtype=np.float64), qd])

    def action_limits(self) -> np.ndarray:
        """(18, 2): the range of each entry of an action row. Position targets: an arm joint's limits widened by 0.1 rad,
        [-0.1, 0.1] m for a finger (its travel is [0, 0.04]: a target below where the finger stops on an object
        squeezes it, a drive pushing with 400 N/m of error up to 7.2 N); velocity targets: +-10."""
        return np.stack([self.a_lo, self.a_hi], axis=1)

    def status(self) -> dict:
        return {
            "family": self.family,
            "rule": self.rule_name,
            "success": bool(self.success),
            "done": bool(self.done),
            "reason": self.reason,
            "score": 1.0 if self.success else 0.0,
            "steps": int(self.steps),
            "sim_time_s": round(self.steps * CONTROL_DT, 6),
            "resets": int(self.resets),
            "state_sha": self.state_sha(),
            "instance_ok": bool(self.instance_ok),
            "placement_sha": self.placement_sha,
            "init_sha": self.init_sha,
            "start_exact": bool(self.start_exact),
            "rule_state": self.rule.state(),
            "build_s": self.build_s,
            "first_frame_s": self.first_frame_s,
        }

    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rows = np.asarray(self._rec or [], dtype=np.float64).reshape(-1, N_ACT)
        self._rec = None
        _log({"ev": "record", "rows": int(len(rows))})
        return rows

    def _rows(self, actions) -> np.ndarray:
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N_ACT or not np.all(np.isfinite(A)):
            raise ValueError(f"a trajectory is a finite (T, {N_ACT}) array (9 position targets, then 9 velocity targets), got {A.shape}")
        return A

    def replay(self, actions, video: str | None = None, cameras=None, fps: int = 20) -> dict:
        """Reset, then execute the rows open-loop, one per control step, until the episode ends or the rows do; returns
        status(). In a process that has not stepped before, this is what the grader does."""
        A = self._rows(actions)
        rec, self._rec = self._rec, None
        if self.steps or self.resets:
            self._reset_task()
        frames, every = [], max(int(round(CONTROL_HZ / fps)), -(-len(A) // 1500), 1)
        cams = list(cameras or self.cameras()) if video else []
        for k, row in enumerate(A):
            if video and k % every == 0:
                frames.append(np.hstack([self.render_frame(c) for c in cams]))
            if not self.step(row):
                break
        out = self.status()
        if video:
            frames.append(np.hstack([self.render_frame(c) for c in cams]))
            out["video"] = _write_video(video, frames, fps)
        self._rec = rec
        _log({"ev": "replay", "rows": int(len(A)), "success": out["success"]})
        return out

    def save_trajectory(self, actions, path: str, meta: dict | None = None) -> None:
        A = self._rows(actions)
        if len(A) > MAX_STEPS:
            raise ValueError(f"a trajectory has at most {MAX_STEPS} rows ({MAX_STEPS * CONTROL_DT:g} s of simulated time), got {len(A)}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez_compressed(path, actions=A, task=self.family, meta=json.dumps(meta or {}))

    def render_video(self, actions, path: str, cameras=None, fps: int = 20) -> dict:
        return self.replay(actions, video=path, cameras=cameras, fps=fps)

    # ------------------------------------------------------------------------------------------- state
    def _xf(self, path: str) -> np.ndarray:
        """World transform (4 x 4, column vectors) of a prim."""
        from pxr import Usd, UsdGeom

        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            raise KeyError(f"no prim at {path}")
        return np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=np.float64).T

    def centre(self, path: str) -> np.ndarray:
        """Centre of an object's bounding box in the world frame (LabUtopia's `get_geometry_center`)."""
        c = self.objects.get_geometry_center(object_path=path)
        if c is None:
            raise KeyError(f"no prim at {path}")
        return np.asarray(c, dtype=np.float64)

    def size(self, path: str) -> np.ndarray:
        """Extent of an object's world-aligned bounding box (LabUtopia's `get_object_size`)."""
        return np.asarray(self.objects.get_object_size(object_path=path), dtype=np.float64)

    def origin(self, path: str) -> np.ndarray:
        """Position of a prim's frame in the world frame (LabUtopia's `get_object_xform_position`)."""
        return self._xf(path)[:3, 3].copy()

    def pose(self, path: str) -> list:
        """x y z + wxyz quaternion of a prim's frame in the world frame."""
        T = self._xf(path)
        R = T[:3, :3] / np.linalg.norm(T[:3, :3], axis=0)  # without the prim's scale
        return [*(float(v) for v in T[:3, 3]), *(float(v) for v in _mat_to_quat(R))]

    def hand(self) -> np.ndarray:
        """The point between the fingertips (LabUtopia's "gripper position")."""
        return self.origin(TCP)

    def tcp_pose(self) -> list:
        return self.pose(TCP)

    def gripper_opening(self) -> float:
        """Metres between the fingers (0 .. 0.08)."""
        q = self.robot.get_joint_positions()
        return float(q[7] + q[8])

    def joint_positions(self) -> np.ndarray:
        return np.asarray(self.robot.get_joint_positions(), dtype=np.float64)

    def joint_velocities(self) -> np.ndarray:
        return np.asarray(self.robot.get_joint_velocities(), dtype=np.float64)

    def joint_efforts(self) -> np.ndarray:
        """What each joint's drive asks for, by the drive's own law: stiffness x (position target - q) + damping x
        (velocity target - qdot), limited to the joint's effort limit (N m; N for the fingers). It grows when the arm
        or a finger pushes on something. The second finger has no drive (it mirrors the first): 0."""
        c = self.command()
        e = self._kp * (c[:N_DOF] - self.joint_positions()) + self._kd * (c[N_DOF:] - self.joint_velocities())
        return np.clip(e, -self._max_effort, self._max_effort)

    def rigid_bodies(self) -> list:
        """Paths of every rigid body of the scene (the robot's links included)."""
        return [str(p.GetPath()) for p in self._bodies]

    def _placement_sha(self) -> str:
        """Hash of where LabUtopia's reset put things: the authored position of every prim directly under /World. A
        function of the config and the seed alone (no physics), so it is the same on every host."""
        from pxr import UsdGeom

        h = hashlib.sha256(json.dumps([self.config, self.seed]).encode())
        for prim in sorted(self.stage.GetPrimAtPath("/World").GetChildren(), key=lambda p: str(p.GetPath())):
            if not prim.IsA(UsdGeom.Xformable) or prim.IsA(UsdGeom.Camera) or str(prim.GetPath()) == ROBOT:
                continue
            ops = UsdGeom.Xformable(prim).GetOrderedXformOps()
            v = ops[0].Get() if ops else None
            try:
                vals = [float(x) for x in v]
            except TypeError:
                vals = []
            h.update(str(prim.GetPath()).encode())
            h.update(np.asarray(vals, dtype=np.float64).tobytes())
        return h.hexdigest()[:16]

    def state_vector(self) -> np.ndarray:
        """The simulation state as numbers: the robot's joint positions, velocities and targets, then every rigid
        body's world transform and its linear and angular velocity."""
        from pxr import Usd, UsdGeom

        v = [self.joint_positions(), self.joint_velocities(), self.command()]
        for p in self._bodies:
            m = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            v.append(np.array([m[i][j] for i in range(4) for j in range(3)], dtype=np.float64))
            for name in ("physics:velocity", "physics:angularVelocity"):
                a = p.GetAttribute(name).Get() if p.HasAttribute(name) else None
                v.append(np.zeros(3) if a is None else np.array([a[0], a[1], a[2]], dtype=np.float64))
        return np.concatenate(v)

    def state_sha(self) -> str:
        """Hash of the simulation state (state_vector()) and of the verdict's own state."""
        h = hashlib.sha256(self.state_vector().tobytes())
        h.update(json.dumps({"steps": int(self.steps), "success": bool(self.success), "rule": self.rule.state()}, sort_keys=True).encode())
        return h.hexdigest()[:16]

    def state(self) -> dict:
        """Privileged view of the current state. `s.task` (LabUtopia's task object), `s.cfg` (its config), `s.stage`
        (the USD stage), `s.world`, `s.robot` and `s.objects` (LabUtopia's ObjectUtils) are yours to read as well;
        only recorded actions are replayed."""
        return {
            "time_s": round(self.steps * CONTROL_DT, 6),
            "joint_positions": self.joint_positions(), "joint_velocities": self.joint_velocities(),
            "command": self.command(), "tcp_pose": self.tcp_pose(), "gripper_opening": self.gripper_opening(),
            "rule": self.rule.values(), "success": bool(self.success), "done": bool(self.done),
        }

    # ------------------------------------------------------------------------------------------- the robot
    def fk(self, q, links=None) -> dict:
        """{frame: [x, y, z, qw, qx, qy, qz]} (world frame) for seven arm joint positions; frames: "tcp" (the point
        between the fingertips) and "panda_hand" (the link the wrist camera is on). Stateless."""
        return {n: _pose7(self.arm.fk(q, n)) for n in (links or ["tcp", "panda_hand"])}

    def ik(self, targets: dict, seed=None, tol_pos_m: float = 1e-3, tol_rot_rad: float = 1e-2, max_iters: int = 300) -> dict:
        """Arm joint positions that put a frame at `targets` ({"tcp": [x, y, z, qw, qx, qy, qz]}, world frame): damped
        least squares on the seven joints within their limits, no collision check; `tol_rot_rad` >= 3.1 ignores
        orientation. Returns {"ok", "q", "error": {frame: (pos_m, rot_rad)}}."""
        (frame, target), = targets.items()
        r = self.arm.ik(target, self.joint_positions()[:7] if seed is None else seed, frame, tol_pos_m, tol_rot_rad, max_iters)
        return {"ok": r["ok"], "q": r["q"], "error": {frame: r["error"]}}

    def robot_spec(self) -> dict:
        """The robot's spec sheet (nothing about the scene)."""
        dp = self.robot.dof_properties
        names = list(self.robot.dof_names)
        joints = []
        for k, n in enumerate(names):
            arm = k < 7
            joints.append({
                "name": n, "type": "revolute" if arm else "prismatic", "unit": "rad" if arm else "m",
                "position_limits": [float(dp["lower"][k]), float(dp["upper"][k])],
                "velocity_limit": float(dp["maxVelocity"][k]) if k < 8 else float(dp["maxVelocity"][7]),
                "effort_limit": float(dp["maxEffort"][k]) if k < 8 else float(dp["maxEffort"][7]),
                "group": "arm" if arm else "gripper",
                "note": "position drive" if k < 8 else "mirrors panda_finger_joint1 (a mimic joint): its targets are ignored",
            })
        hand_T_tcp = self.arm.hand_T["tcp"]
        return {
            "name": "Franka Panda (7 joints) with its parallel gripper",
            "description": "one arm fixed to the laboratory bench",
            "base": {"type": "fixed", "link": "panda_link0", "pose": _pose7(self.arm.base),
                     "note": "x y z + wxyz quaternion of the base link in the world frame"},
            "joints": joints,
            "grippers": {"gripper": {
                "joints": names[7:], "opening_m": [0.0, 0.08],
                "command": {"entries": ["q_panda_finger_joint1", "q_panda_finger_joint2"], "index": [7, 8],
                            "range": [-FINGER_TARGET, FINGER_TARGET], "unit": "m",
                            "rule": "each finger's distance from the centre line: 0.04 is fully open, 0 closed; the fingers stop on what they hold, and a target below that point squeezes (the drive's stiffness times the distance, at most its effort limit)"},
                "tcp_frame": "tcp",
            }},
            "controller": {
                "type": "joint drives: effort = stiffness * (position target - q) + damping * (velocity target - qdot), limited to effort_limit",
                "control_hz": CONTROL_HZ, "physics_hz": CONTROL_HZ,
                "gains": {n: {"stiffness": float(dp["stiffness"][k]), "damping": float(dp["damping"][k])} for k, n in enumerate(names)},
                "note": "stiffness per rad (N m / rad) for the arm, per m (N / m) for the fingers",
            },
            "tcp": {"tcp": {"parent_link": "panda_hand", "link_T_frame": hand_T_tcp.tolist(),
                            "definition": "the point between the fingertips (LabUtopia's gripper position)"}},
        }

    # ------------------------------------------------------------------------------------------- cameras
    def _make_cameras(self) -> None:
        """The cameras of LabUtopia's config for this task (two fixed ones and the one on the hand, as configured)."""
        from isaacsim.sensors.camera import Camera

        for cc in self.camera_cfgs:
            path = str(cc.prim_path)
            wrist = path.startswith(ROBOT + "/")
            name = "wrist_cam" if wrist else str(cc.name)
            if self.stage.GetPrimAtPath(path).IsValid():
                cam = Camera(prim_path=path, name=f"rcb_{name}", frequency=CONTROL_HZ, resolution=(W, H))
            else:
                cam = Camera(prim_path=path, translation=np.array(cc.translation), name=f"rcb_{name}", frequency=CONTROL_HZ, resolution=(W, H))
                cam.set_local_pose(orientation=np.array(cc.orientation), camera_axes="usd")
                cam.set_focal_length(cc.focal_length)
            clip = list(cc.clipping_range) if hasattr(cc, "clipping_range") else [0.1, 10.0]
            cam.set_clipping_range(near_distance=clip[0], far_distance=clip[1])
            cam.initialize()
            cam.add_distance_to_image_plane_to_frame()
            self._cams[name] = (cam, path, wrist, clip)
        self._first_frames()

    def _first_frames(self) -> None:
        """Render until every camera has an image and a depth map. The renderer takes a few frames to deliver the first
        ones, and minutes when it has not seen the stage in this container before (it compiles its shaders and
        prepares the stage; meanwhile a render call returns nothing)."""
        t0 = told = time.time()
        while True:
            self.world.render()
            ready = True
            for cam, _path, _wrist, _clip in self._cams.values():
                for img in (cam.get_rgba(), cam.get_depth()):
                    ready = ready and img is not None and getattr(img, "ndim", 0) >= 2 and img.size > 0
            if ready:
                break
            now = time.time()
            if now - t0 > FIRST_FRAME_TIMEOUT_S:
                raise RuntimeError(f"the renderer delivered no camera frame within {FIRST_FRAME_TIMEOUT_S} s")
            if now - told > 60:
                told = now
                print(f"rcb_labutopia: waiting for the renderer's first frames ({now - t0:.0f} s; the first time in a "
                      "container takes 5 to 15 minutes)", file=sys.stderr, flush=True)
            time.sleep(0.05)
        for _ in range(RENDERS):
            self.world.render()
        self.first_frame_s = round(time.time() - t0, 1)

    def cameras(self) -> list:
        return list(self._cam_names)

    def _cam(self, camera: str):
        if not _RENDER:
            raise RuntimeError("this Session has no renderer: use Session(..., cameras=True) in a new process")
        if not self._cams:
            self._make_cameras()
        return self._cams[camera]

    def default_cameras(self) -> list:
        return self.cameras()

    def _render(self) -> None:
        key = (self.resets, self.steps)
        if self._render_key != key:
            for _ in range(RENDERS):
                self.world.render()
            self._render_key = key

    def render_frame(self, camera: str, size=(H, W), depth: bool = False) -> np.ndarray:
        """RGB uint8 (512, 512, 3) of a camera at the current state, or its z-depth in metres (float32, 0 where
        nothing is within the camera's range) with depth=True. Does not step the simulation."""
        if tuple(size) != (H, W):
            raise ValueError(f"the cameras render at {(H, W)}")
        cam = self._cam(camera)[0]
        self._render()
        img = cam.get_depth() if depth else cam.get_rgba()
        if depth:
            d = np.asarray(img, dtype=np.float32).copy()
            d[~np.isfinite(d) | (d >= self._cam(camera)[3][1])] = 0.0
            return d
        return np.ascontiguousarray(np.asarray(img)[..., :3].astype(np.uint8))

    def render_depth(self, camera: str, size=(H, W)) -> np.ndarray:
        return self.render_frame(camera, size, depth=True)

    def camera_info(self, camera: str, size=(H, W)) -> dict:
        """Intrinsics (OpenCV), world -> camera (OpenCV axes) and camera -> world (OpenGL axes) at the current state."""
        cam, path, _wrist, _clip = self._cam(camera)
        T = self._xf(path)
        c2w = _T(T[:3, 3], T[:3, :3] / np.linalg.norm(T[:3, :3], axis=0))  # a USD camera looks along -z, y up
        return {
            "intrinsic_cv": np.asarray(cam.get_intrinsics_matrix(), dtype=np.float64).tolist(),
            "extrinsic_cv": np.linalg.inv(c2w @ GL2CV)[:3, :].tolist(),
            "cam2world_gl": c2w.tolist(),
            "image_size": [W, H],
        }

    def camera_range(self, camera: str) -> list:
        """[near, far] in metres: what a camera's depth map covers (0 outside)."""
        clip = self._cam(camera)[3]
        return [float(clip[0]), float(clip[1])]

    def camera_mount(self, camera: str) -> dict:
        _cam, path, wrist, _clip = self._cam(camera)
        info = self.camera_info(camera)
        if not wrist:
            return {"type": "static", "extrinsic_cv": info["extrinsic_cv"], "cam2world_gl": info["cam2world_gl"]}
        hand = self._xf(ROBOT + "/panda_hand")
        return {"type": "link", "parent_link": "panda_hand",
                "link_T_cam_cv": (np.linalg.inv(hand) @ np.asarray(info["cam2world_gl"]) @ GL2CV).tolist()}

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        _log({"ev": "session_end", "sim_steps": int(self.total_steps), "resets": int(max(self.resets, 0))})


def _write_video(path: str, frames: list, fps: int) -> bool:
    try:
        import imageio.v2 as imageio

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with imageio.get_writer(path, fps=fps, codec="libx264", quality=6, macro_block_size=None) as w:
            for f in frames:
                h, wd = f.shape[0] // 2 * 2, f.shape[1] // 2 * 2
                w.append_data(f[:h, :wd])
        return os.path.getsize(path) > 0
    except Exception as exc:  # noqa: BLE001 -- a video never decides anything
        print(f"video not written: {exc!r}", file=sys.stderr)
        return False


def finish(code: int = 0) -> None:
    """Leave the process. Kit's own shutdown can abort after a short run, and it would be the exit status: flush, then
    leave without it."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def facts(family: str, seed: int) -> dict:
    """What an instance file records about `family` at `seed` (run inside the image by the generator)."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"family": family, "seed": seed}, f)
    global SESSION_LOG
    SESSION_LOG = ""
    s = Session(family, instance=f.name)
    os.unlink(f.name)
    config, rule = FAMILIES[family]
    return {
        "benchmark": "labutopia", "family": family, "seed": int(seed), "rule": s.rule_name,
        "upstream": {"repo": "Rui-li023/LabUtopia", "commit": open("/opt/labutopia-commit").read().strip()
                     if os.path.exists("/opt/labutopia-commit") else None, "config": config, "task_type": str(s.cfg.task_type),
                     "controller_type": str(s.cfg.controller_type), "stage": str(s.cfg.usd_path)},
        "control_dt": CONTROL_DT, "placement_sha": s.placement_sha, "init_sha": s.init_sha,
        "n_action": N_ACT, "dof_names": list(s.robot.dof_names),
        "action_limits": s.action_limits().tolist(),
        "cameras": s.cameras(),
        "initial_command": [float(v) for v in s.command()],
        "initial_joint_positions": [float(v) for v in s.joint_positions()],
        "rule_class": rule, "rule_text": s.rule.text, "rule_values": s.rule.values(),
        "rigid_bodies": len(s.rigid_bodies()), "build_s": s.build_s,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a trajectory from the frozen instance in this fresh process (what the grader does)")
    r.add_argument("--instance", default="/app/instance.json")
    r.add_argument("--task", "--family", dest="family", default=None)
    r.add_argument("--traj", default="/app/output/trajectory.npz")
    r.add_argument("--out", default=None)
    r.add_argument("--video", default=None)
    f = sub.add_parser("facts", help="hashes and layout of a family at a seed (generator)")
    f.add_argument("--family", required=True)
    f.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "facts":
        print("FACTS " + json.dumps(facts(a.family, a.seed)), flush=True)
        finish(0)
    d = np.load(a.traj, allow_pickle=False)
    acts = np.asarray(d["actions"], dtype=np.float64)
    s = Session(a.family, instance=a.instance, cameras=bool(a.video))  # cameras before the first step, when rendering
    out = s.replay(acts, video=a.video)
    print("RESULT " + json.dumps(out), flush=True)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(out, fh)
    s.close()
    finish(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
