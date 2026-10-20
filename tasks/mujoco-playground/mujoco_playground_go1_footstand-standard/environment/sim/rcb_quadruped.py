"""rcb_quadruped — MuJoCo Playground's quadruped locomotion tasks in plain MuJoCo for Embodied First Exam.

Scenes = MuJoCo Playground's `locomotion/<robot>/xmls` (Apache-2.0, @4057c14) with the robots from MuJoCo Menagerie
(@1b86ece, the commit Playground pins), assembled the way Playground's `get_assets()` does; joint drive gains as
Playground's environments set them. Physics on the CPU (bit-exact replay); control 50 Hz.

The instance (instance.json) freezes one episode as Playground's own `reset` draws it with a seed: the robot's start
state and, for the joystick tasks, the command schedule Playground's command process draws over the episode. Playground
only has shaped RL rewards and a termination rule; success is defined here from them (see `check`):

  joystick  every control step of the schedule is executed (T = horizon), the robot never meets Playground's termination
            rule (the trunk's up axis pointing below the horizon), and in every command segment, after its first
            SETTLE_STEPS steps, the mean planar velocity error |v_xy - cmd_xy| (the IMU's velocimeter, trunk frame) is at
            most LIN_TOL m/s and the mean yaw-rate error |w_z - cmd_wz| (the IMU's gyro) at most YAW_TOL rad/s.
  getup     the trajectory ends with HOLD_STEPS control steps in a row in which the trunk is upright (tilt at most
            TILT_MAX_DEG) and the IMU at least `min_imu_height` m above the floor, within the horizon (Go1: 0.22 m; it
            stands at 0.255-0.26 m with Playground's gains, Playground's reward aims at 0.275 m, lying down is below 0.15 m).

trajectory = (T, 12) joint position targets (rad), one row per control step (1/50 s), in the actuator order
`s.joint_names`; values outside the actuator ranges are clipped (MuJoCo clamps them anyway).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


def _pick_gl() -> None:
    """Rendering backend: EGL (GPU) if it works here, else OSMesa (CPU); checked once, before mujoco is imported."""
    if os.environ.get("RCB_MUJOCO_GL"):
        os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = os.environ["RCB_MUJOCO_GL"]
        return
    if os.environ.get("_RCB_GL_CHECKED"):
        return
    import subprocess
    probe = ("import mujoco; m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom size=\\'.1\\'/></worldbody></mujoco>'); "
             "d = mujoco.MjData(m); mujoco.mj_forward(m, d); r = mujoco.Renderer(m, 240, 320); r.update_scene(d); r.render(); r.render()")
    try:
        ok = subprocess.run([sys.executable, "-c", probe], env={**os.environ, "MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl"},
                            capture_output=True, timeout=60).returncode == 0
    except Exception:
        ok = False
    gl = "egl" if ok else "osmesa"
    os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = gl
    os.environ["_RCB_GL_CHECKED"] = gl


_pick_gl()

ROOT = Path(os.environ.get("RCB_MJ_ROOT", "/opt/rcb_mj"))
CONTROL_DT = 0.02
N = 12
# joystick success
SETTLE_STEPS = 25          # the first 0.5 s of every command segment is not scored (the gait changes over)
LIN_TOL = 0.2              # m/s, mean |v_xy - cmd_xy| per segment
YAW_TOL = 0.3              # rad/s, mean |w_z - cmd_wz| per segment
# getup success
HOLD_STEPS = 25            # 0.5 s
TILT_MAX_DEG = 10.0
# gait tracking success
GAIT_TOL = 0.05            # m, mean (after each segment's first SETTLE_STEPS) of the feet's RMS height error to the gait's curve
# hand/footstand success
POSE_HOLD_STEPS = 100      # 2 s
FRONT_LEG_GEOMS = ["fl_calf1", "fl_calf2", "fr_calf1", "fr_calf2", "fl_thigh1", "fl_thigh2", "fl_thigh3", "fr_thigh1",
                   "fr_thigh2", "fr_thigh3", "fl_hip", "fr_hip"]   # handstand.py's termination contacts (both tasks)
HIND_LEG_GEOMS = [g.replace("fl_", "rl_").replace("fr_", "rr_") for g in FRONT_LEG_GEOMS]   # the list Footstand sets up

GO1_FALL = "its trunk's up axis pointing below the horizon"
SPOT_FALL = "its trunk tilted by more than about 32 deg (the up axis's z component below 0.85)"

ROBOTS = {
    "go1": {
        "name": "Unitree Go1",
        "assets": [("playground/locomotion/go1/xmls", "*.xml"), ("playground/locomotion/go1/xmls/assets", "*"),
                   ("menagerie/unitree_go1", "*.xml"), ("menagerie/unitree_go1/assets", "*")],
        "imu": "imu", "feet": ["FR", "FL", "RR", "RL"], "root": "trunk", "cameras": ["track", "side", "back", "top"],
        "joint_text": "FR, FL, RR, RL legs; per leg hip (abduction), thigh (hip pitch), calf (knee)",
    },
    "spot": {
        "name": "Boston Dynamics Spot",
        "assets": [("playground/locomotion/spot/xmls", "*.xml"), ("menagerie/boston_dynamics_spot", "*.xml"),
                   ("menagerie/boston_dynamics_spot/assets", "*")],
        "imu": "imu", "feet": ["FL", "FR", "HL", "HR"], "root": "body", "cameras": ["track", "side", "back", "top"],
        "joint_text": "FL, FR, HL, HR legs; per leg hx (abduction), hy (hip pitch), kn (knee)",
    },
    "barkour": {
        "name": "Google Barkour vB",
        "assets": [("menagerie/google_barkour_vb", "*.xml"), ("menagerie/google_barkour_vb/assets", "*")],
        "imu": "imu_frame", "feet": ["foot_front_left", "foot_hind_left", "foot_front_right", "foot_hind_right"],
        "root": "torso", "cameras": ["track", "realsense/rgb"],
        "joint_text": "front-left, hind-left, front-right, hind-right legs; per leg abduction, hip, knee",
    },
}
ENVS = {
    "Go1JoystickFlatTerrain": {"robot": "go1", "kind": "joystick", "horizon": 1000, "kp": 35.0, "kd": 0.5, "term_text": GO1_FALL,
                               "xml": "playground/locomotion/go1/xmls/scene_mjx_feetonly_flat_terrain.xml"},
    "Go1JoystickRoughTerrain": {"robot": "go1", "kind": "joystick", "horizon": 1000, "kp": 35.0, "kd": 0.5, "term_text": GO1_FALL,
                                "xml": "playground/locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml"},
    "Go1Getup": {"robot": "go1", "kind": "getup", "horizon": 300, "kp": 35.0, "kd": 0.5, "settle_s": 0.5,
                 "z_des": 0.275, "min_imu_height": 0.22,
                 "xml": "playground/locomotion/go1/xmls/scene_mjx_fullcollisions_flat_terrain.xml"},
    "Go1Handstand": {"robot": "go1", "kind": "stand_on_two", "horizon": 500, "kp": 35.0, "kd": 0.5,
                     "forward": [0.0, 0.0, -1.0], "air_feet": ["RR", "RL"], "fwd_tol_deg": 30.0, "min_imu_height": 0.40,
                     "xml": "playground/locomotion/go1/xmls/scene_mjx_flat_terrain.xml"},
    "Go1Footstand": {"robot": "go1", "kind": "stand_on_two", "horizon": 500, "kp": 35.0, "kd": 0.5,
                     "forward": [0.0, 0.0, 1.0], "air_feet": ["FR", "FL"], "fwd_tol_deg": 30.0, "min_imu_height": 0.40,
                     "hind_leg_contact": True,
                     "xml": "playground/locomotion/go1/xmls/scene_mjx_flat_terrain.xml"},
    "SpotGetup": {"robot": "spot", "kind": "getup", "horizon": 300, "kp": 400.0, "kd": 20.0, "settle_s": 0.5,
                  "z_des": 0.46, "min_imu_height": 0.40,
                  "xml": "playground/locomotion/spot/xmls/scene_mjx_flat_terrain.xml"},
    # Spot's joystick termination: upvector z < 0.85; the feet-only XML's actuator kv (20) stays, as in Playground
    "SpotFlatTerrainJoystick": {"robot": "spot", "kind": "joystick", "horizon": 1000, "kp": 300.0, "kd": 1.0, "up_z_min": 0.85,
                                "term_text": SPOT_FALL,
                                "xml": "playground/locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml"},
    "SpotJoystickGaitTracking": {"robot": "spot", "kind": "joystick", "horizon": 1000, "kp": 400.0, "kd": 10.0,
                                 "up_z_min": 0.85, "gait": True, "term_text": SPOT_FALL,
                                 "xml": "playground/locomotion/spot/xmls/scene_mjx_feetonly_flat_terrain.xml"},
    # Barkour: Playground loads Menagerie's scene as is (2 ms timestep) and takes 5 substeps, so a control step is
    # 10 ms of simulated time; its termination adds a joint box and a torso height; random pushes on the torso.
    "BarkourJoystick": {"robot": "barkour", "kind": "joystick", "horizon": 1000, "kp": 35.0, "kd": 0.5239, "up_z_min": 0.0,
                        "control_dt": 0.01, "joint_box": [[-0.7, -1.0, 0.05], [0.52, 2.1, 2.1]], "torso_min_z": 0.18,
                        "kicks": True, "xml": "menagerie/google_barkour_vb/scene_mjx.xml",
                        "term_text": "its trunk's up axis pointing below the horizon, a joint outside its box (abduction "
                                     "[-0.7, 0.52], hip [-1.0, 2.1], knee [0.05, 2.1] rad) or the torso lower than 0.18 m"},
}

_LOGDIR = "/logs/agent/rcb" if os.path.isdir("/logs/agent") else "/app/output"
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", f"{_LOGDIR}/rcb_session_log.jsonl")
TRACE_DIR = os.environ.get("RCB_AGENT_TRACE_DIR", f"{_LOGDIR}/rcb_trace")
TRACE_MAX_FILES = 300
TRACE_MAX_BYTES = 400 * 1024 * 1024


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n")
    except OSError:
        pass


def load_model(env: str):
    """The scene as Playground builds it: its XML with an asset dict of bare file names, then its gains."""
    import mujoco
    e = ENVS[env]
    assets = {}
    for d, pat in ROBOTS[e["robot"]]["assets"]:
        for f in sorted((ROOT / d).glob(pat)):
            if f.is_file():
                assets[f.name] = f.read_bytes()
    if e["robot"] == "barkour":   # barkour/joystick.py: Menagerie's scene + a foot-floor contact sensor per foot
        spec = mujoco.MjSpec.from_file(str(ROOT / e["xml"]), assets=assets)
        for g in ROBOTS["barkour"]["feet"]:
            spec.add_sensor(name=f"{g}_floor_found", type=mujoco.mjtSensor.mjSENS_CONTACT, objtype=mujoco.mjtObj.mjOBJ_GEOM,
                            objname=g, reftype=mujoco.mjtObj.mjOBJ_GEOM, refname="floor", intprm=[1, 1, 1],
                            datatype=mujoco.mjtDataType.mjDATATYPE_REAL, needstage=mujoco.mjtStage.mjSTAGE_ACC, dim=1)
        m = spec.compile()
    else:
        m = mujoco.MjModel.from_xml_string((ROOT / e["xml"]).read_text(), assets)
    m.dof_damping[6:] = e["kd"]                        # go1/base.py, spot/base.py: Kd as joint damping, Kp as the gain
    m.actuator_gainprm[:, 0] = e["kp"]
    m.actuator_biasprm[:, 1] = -e["kp"]
    return m


def gait_rz(phi, swing_height):
    """mujoco_playground/_src/gait.py get_rz: a foot's target height over its phase (cubic Bezier up, then down)."""
    x = (np.asarray(phi) + np.pi) / (2 * np.pi)
    bez = lambda y0, y1, t: y0 + (y1 - y0) * (t ** 3 + 3 * (t ** 2 * (1 - t)))  # noqa: E731
    return np.where(x <= 0.5, bez(0.0, swing_height, 2 * x), bez(swing_height, 0.0, 2 * x - 1))


def schedule_of(inst: dict, horizon: int) -> np.ndarray:
    """(horizon, 3) command (vx, vy, wz) per control step from the instance's segments."""
    out = np.zeros((horizon, 3))
    seg = inst["commands"]
    for i, s in enumerate(seg):
        a = int(s["start_step"]); b = int(seg[i + 1]["start_step"]) if i + 1 < len(seg) else horizon
        out[a:b] = [s["vx"], s["vy"], s["wz"]]
    return out


class Session:
    def __init__(self, instance: str | Path = "/app/instance.json", enable_render: bool = False, check_hash: bool = True):
        import mujoco
        self.mj = mujoco
        self.inst = json.load(open(instance))
        self.env = self.inst["env"]
        self.spec = ENVS[self.env]
        self.robot = ROBOTS[self.spec["robot"]]
        self.kind = self.spec["kind"]
        self.horizon = int(self.spec["horizon"])
        self.model = load_model(self.env)
        self.data = mujoco.MjData(self.model)
        m = self.model
        self.control_dt = float(self.spec.get("control_dt", CONTROL_DT))
        self.substeps = int(round(self.control_dt / m.opt.timestep))
        self.joint_names = [m.joint(m.actuator_trnid[i, 0]).name for i in range(m.nu)]
        self.lower = m.actuator_ctrlrange[:, 0].copy()
        self.upper = m.actuator_ctrlrange[:, 1].copy()
        self.home = m.keyframe("home").qpos[7:].copy()
        self._imu = m.site(self.robot["imu"]).id
        self._sens = {m.sensor(i).name: (m.sensor_adr[i], m.sensor_dim[i]) for i in range(m.nsensor)}
        self.cameras = list(self.robot["cameras"])
        self.commands = schedule_of(self.inst, self.horizon) if self.kind == "joystick" else None
        self._root = m.body(self.robot["root"]).id
        self._root_mass = float(m.body_subtreemass[self._root])
        self.kicks = self.inst.get("kicks", []) if self.spec.get("kicks") else []
        self.gait = self.inst.get("gait") if self.spec.get("gait") else None
        self._feet_sites = np.array([m.site(f).id for f in self.robot["feet"]])
        self._floor = m.geom("floor").id
        self._hind_ids = {m.geom(g).id for g in HIND_LEG_GEOMS} if self.spec.get("hind_leg_contact") else set()
        self._renderer = None
        self.enable_render = enable_render
        self._trace: list | None = None
        self.resets = 0
        self.total_steps = 0
        _slog("session_start", env=self.env, seed=self.inst.get("seed"))
        import atexit
        atexit.register(lambda: (self._trace_dump(), _slog("session_end", resets=self.resets,
                                                           sim_steps=self.total_steps * self.substeps)))
        self.reset()
        self.instance_ok = self.state_sha() == self.inst.get("state_sha")
        if check_hash and self.inst.get("state_sha") and not self.instance_ok:
            raise RuntimeError(f"initial state hash {self.state_sha()} != instance {self.inst['state_sha']}")

    # ------------------------------------------------------------------------------------------------ episode
    def reset(self) -> None:
        """The frozen start state (t = 0): Playground's reset draw, then (getup) its 0.5 s settle with the joints held."""
        self._trace_dump()
        m, d = self.model, self.data
        self.mj.mj_resetData(m, d)
        d.qpos[:] = self.inst["qpos0"]
        d.qvel[:] = self.inst["qvel0"]
        d.ctrl[:] = self.inst["qpos0"][7:]
        self.mj.mj_forward(m, d)
        if self.spec.get("settle_s"):
            self.mj.mj_step(m, d, nstep=int(self.spec["settle_s"] / m.opt.timestep))
            d.time = 0.0
        self.targets = d.ctrl.copy()
        self.steps = 0
        self.resets += 1
        self.fell_at = None
        self.log: list[tuple] = []        # per control step: (lin_err, yaw_err, tilt_deg, imu_height, up_z)
        self.gait_log: list[float] = []   # gait tracking, per control step: RMS of the feet's height errors (m)
        self.pose_log: list[tuple] = []   # stand_on_two, per control step: (forward axis to target, deg; air feet down)
        self._trace = [] if TRACE_DIR else None
        _slog("reset", n=self.resets)

    def step(self, targets) -> dict[str, Any]:
        if self.steps >= self.horizon:
            raise RuntimeError(f"the episode is over: {self.horizon} control steps")
        tg = np.asarray(targets, dtype=np.float64).reshape(N)
        if not np.all(np.isfinite(tg)):
            raise ValueError("targets contain NaN/inf")
        tg = np.clip(tg, self.lower, self.upper)
        cmd = self.commands[self.steps] if self.commands is not None else np.zeros(3)
        self.targets = tg
        self.data.ctrl[:] = tg
        if self.kicks:
            self.data.xfrc_applied[self._root, :3] = self.push_force(self.steps)
        self.mj.mj_step(self.model, self.data, nstep=self.substeps)
        self.steps += 1
        self.total_steps += 1
        v, w = self.sensor("local_linvel"), self.sensor("gyro")
        up_z = float(self.data.site_xmat[self._imu][8])
        tilt = float(np.degrees(np.arccos(np.clip(up_z, -1.0, 1.0))))
        self.log.append((float(np.linalg.norm(v[:2] - cmd[:2])), float(abs(w[2] - cmd[2])), tilt,
                         float(self.data.site_xpos[self._imu][2]), up_z))
        if self.kind == "stand_on_two":
            fwd = self.data.site_xmat[self._imu].reshape(3, 3)[:, 0]
            ang = float(np.degrees(np.arccos(np.clip(fwd @ np.asarray(self.spec["forward"]), -1.0, 1.0))))
            air_down = any(self.sensor(f"{f}_floor_found")[0] > 0 for f in self.spec["air_feet"])
            self.pose_log.append((ang, air_down))
            bad = up_z < -0.25 or any(self.sensor(f"{g}_floor_found")[0] > 0 for g in FRONT_LEG_GEOMS)
            if self.spec.get("hind_leg_contact") and not bad:
                bad = self._touches_floor(self._hind_ids)
            if bad and self.fell_at is None:
                self.fell_at = self.steps                  # handstand.py's termination: upvector z < -0.25 or a front-leg contact
        elif self.fell_at is None and self.terminated(up_z):
            self.fell_at = self.steps                      # the environment's own termination rule
        if self.gait:
            ph = np.fmod(np.asarray(self.gait["phase0"]) + (self.steps - 1) * self.gait["phase_dt"] + np.pi, 2 * np.pi) - np.pi
            err = self.data.site_xpos[self._feet_sites][:, 2] - gait_rz(ph, self.gait["foot_height_m"])
            self.gait_log.append(float(np.sqrt(np.mean(err ** 2))))
        if self._trace is not None:
            self._trace.append(tg.astype(np.float32))
        return self.check()

    def _touches_floor(self, geoms: set) -> bool:
        d, fl = self.data, self._floor
        return any((c.geom1 == fl and c.geom2 in geoms) or (c.geom2 == fl and c.geom1 in geoms) for c in d.contact[:d.ncon])

    def terminated(self, up_z: float) -> bool:
        """Playground's termination rule of a joystick environment: the trunk's up axis below up_z_min (Go1 0, Spot
        0.85), and for Barkour also a joint outside its box or the torso below 0.18 m."""
        if up_z < self.spec.get("up_z_min", 0.0):
            return True
        if "joint_box" in self.spec:
            lo, hi = (np.tile(b, 4) for b in self.spec["joint_box"])
            q = self.data.qpos[7:]
            if np.any(q < lo) or np.any(q > hi):
                return True
        if "torso_min_z" in self.spec and self.data.xpos[self._root][2] < self.spec["torso_min_z"]:
            return True
        return False

    def push_force(self, t: int) -> np.ndarray:
        """barkour/joystick.py's kick at control step t: 0.5 sin(pi i / dur) * torso mass * v / (dur * 0.02 s) along
        the kick's direction, i = t - start (zero outside a kick)."""
        f = np.zeros(3)
        for k in self.kicks:
            i = t - int(k["start_step"])
            dur = int(k["duration_steps"])
            if 0 <= i < dur:
                u = 0.5 * np.sin(np.pi * i / dur)
                f[:2] += u * self._root_mass * k["velocity_mps"] / (dur * CONTROL_DT) * np.asarray(k["direction_xy"])
        return f

    def check(self) -> dict[str, Any]:
        """Success so far, judged on the steps executed (the grader judges the whole trajectory)."""
        L = np.array(self.log).reshape(-1, 5)
        out: dict[str, Any] = {"steps": self.steps, "horizon": self.horizon, "time_s": round(self.steps * self.control_dt, 2)}
        if self.kind == "joystick":
            segs = []
            for i, s in enumerate(self.inst["commands"]):
                a = int(s["start_step"]) + SETTLE_STEPS
                b = min(int(self.inst["commands"][i + 1]["start_step"]) if i + 1 < len(self.inst["commands"]) else self.horizon,
                        self.steps)
                if b > a:
                    segs.append({"segment": i, "lin_err": round(float(L[a:b, 0].mean()), 4),
                                 "yaw_err": round(float(L[a:b, 1].mean()), 4)})
            if self.gait:
                G = np.asarray(self.gait_log)
                for g in segs:
                    s0 = self.inst["commands"][g["segment"]]
                    a = int(s0["start_step"]) + SETTLE_STEPS
                    nxt = self.inst["commands"][g["segment"] + 1]["start_step"] if g["segment"] + 1 < len(self.inst["commands"]) else self.horizon
                    g["gait_err"] = round(float(G[a:min(int(nxt), self.steps)].mean()), 4)
            ok_track = all(g["lin_err"] <= LIN_TOL and g["yaw_err"] <= YAW_TOL and g.get("gait_err", 0.0) <= GAIT_TOL
                           for g in segs)
            out.update(success=bool(self.steps == self.horizon and self.fell_at is None and ok_track),
                       fell_at=self.fell_at, tracking_ok=bool(ok_track), segments=segs,
                       worst_lin_err=max([g["lin_err"] for g in segs], default=None),
                       worst_yaw_err=max([g["yaw_err"] for g in segs], default=None),
                       **({"worst_gait_err": max([g["gait_err"] for g in segs], default=None)} if self.gait else {}))
        elif self.kind == "stand_on_two":
            P = np.array(self.pose_log, dtype=float).reshape(-1, 2)
            n = POSE_HOLD_STEPS
            held = (len(P) >= n and self.fell_at is None and bool(np.all(P[-n:, 0] <= self.spec["fwd_tol_deg"]))
                    and bool(np.all(L[-n:, 3] >= self.spec["min_imu_height"])) and not bool(P[-n:, 1].any()))
            out.update(success=bool(held), fell_at=self.fell_at,
                       pose_angle_deg=round(float(P[-1, 0]), 2) if len(P) else None,
                       imu_height=round(float(L[-1, 3]), 4) if len(L) else None,
                       min_imu_height=self.spec["min_imu_height"])
        else:
            last = L[-HOLD_STEPS:]
            held = (len(last) == HOLD_STEPS and bool(np.all(last[:, 2] <= TILT_MAX_DEG))
                    and bool(np.all(last[:, 3] >= self.spec["min_imu_height"])))
            out.update(success=bool(held), tilt_deg=round(float(L[-1, 2]), 2) if len(L) else None,
                       imu_height=round(float(L[-1, 3]), 4) if len(L) else None,
                       min_imu_height=self.spec["min_imu_height"])
        return out

    @property
    def done(self) -> bool:
        return self.steps >= self.horizon

    # ------------------------------------------------------------------------------------------------ reading
    def sensor(self, name: str) -> np.ndarray:
        a, n = self._sens[name]
        return self.data.sensordata[a:a + n].copy()

    def gravity(self) -> np.ndarray:
        """Gravity's direction in the IMU frame ([0, 0, -1] when level), as Playground's Go1 computes it."""
        return self.data.site_xmat[self._imu].reshape(3, 3).T @ np.array([0.0, 0.0, -1.0])

    def foot_contacts(self) -> np.ndarray:
        return np.array([self.sensor(f"{f}_floor_found")[0] > 0 for f in self.robot["feet"]], dtype=np.float64)

    def command_now(self) -> np.ndarray:
        if self.commands is None:
            return np.zeros(3)
        return self.commands[min(self.steps, self.horizon - 1)].copy()

    def state(self) -> dict[str, Any]:
        d = self.data
        return {"qpos": d.qpos.copy(), "qvel": d.qvel.copy(), "targets": self.targets.copy(),
                "local_linvel": self.sensor("local_linvel"), "gyro": self.sensor("gyro"), "gravity": self.gravity(),
                "accelerometer": self.sensor("accelerometer"), "imu_pos": d.site_xpos[self._imu].copy(),
                "imu_mat": d.site_xmat[self._imu].reshape(3, 3).copy(), "foot_contacts": self.foot_contacts(),
                "feet_pos": np.array([d.site_xpos[self.model.site(f).id] for f in self.robot["feet"]]),
                "command": self.command_now(), **self.check()}

    def state_sha(self) -> str:
        return hashlib.sha1(np.concatenate([self.data.qpos, self.data.qvel]).tobytes()).hexdigest()[:12]

    # ------------------------------------------------------------------------------------------------ trajectories
    def save_trajectory(self, actions, path: str | Path = "/app/output/trajectory.npz", meta: dict | None = None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=np.asarray(actions, dtype=np.float64), env=self.env, seed=self.inst.get("seed"),
                 action_layout=f"12 joint position targets (rad) per control step (1/50 s): {', '.join(self.joint_names)}",
                 meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != N:
            raise ValueError(f"actions must be (T, {N}), got {A.shape}")
        if len(A) > self.horizon:
            raise ValueError(f"trajectory longer than the {self.horizon}-step episode")
        self.reset()
        self._trace = None
        for row in A:
            self.step(row)
        r = self.check()
        _slog("replay", n_actions=int(len(A)), success=r["success"])
        return {**r, "state_sha": self.state_sha()}

    # ------------------------------------------------------------------------------------------------ pictures
    def render(self, camera: str = "track", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        if self._renderer is None or self._renderer.width != size[0] or self._renderer.height != size[1]:
            self._renderer = self.mj.Renderer(self.model, size[1], size[0])
        self._renderer.update_scene(self.data, camera=camera)
        return self._renderer.render().copy()

    def render_grid(self, size=(320, 240)) -> np.ndarray:
        """The robot's first two cameras side by side (Go1, Spot: `track` and `side`)."""
        return np.concatenate([self.render(c, size) for c in self.cameras[:2]], axis=1)

    def render_video(self, actions, path: str | Path, every: int | None = None, fps: int = 25) -> dict[str, Any]:
        """Replay `actions` from t = 0 and write an mp4 of at most ~150 frames (CPU rendering takes ~0.2 s a view)."""
        import imageio.v2 as imageio
        A = np.asarray(actions, dtype=np.float64)[:self.horizon]
        every = every or max(2, -(-len(A) // 150))
        fps = max(5, min(fps, round(1 / (every * self.control_dt))))
        self.reset()
        self._trace = None
        frames = [self.render_grid()]
        for i, row in enumerate(A):
            self.step(row)
            if (i + 1) % every == 0:
                frames.append(self.render_grid())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        imageio.imwrite(str(path.with_suffix(".last.png")), frames[-1])
        return {**self.check(), "n_frames": len(frames), "video": str(path)}

    def _trace_dump(self) -> None:
        tr = self._trace
        self._trace = None
        if not tr or not TRACE_DIR:
            return
        try:
            os.makedirs(TRACE_DIR, exist_ok=True)
            ents = [e for e in os.scandir(TRACE_DIR) if e.name.endswith(".npz")]
            if len(ents) >= TRACE_MAX_FILES or sum(e.stat().st_size for e in ents) >= TRACE_MAX_BYTES:
                return
            np.savez_compressed(os.path.join(TRACE_DIR, f"{os.getpid()}_{self.resets:05d}.npz"), actions=np.stack(tr),
                                success=self.check()["success"], t_end=time.time())
        except Exception:
            pass


def main(argv: list[str]) -> int:
    """CLI: `replay --instance I --traj T [--out J] [--video V]` (one fresh-process replay, the grader's), or `info I`."""
    import argparse
    ap = argparse.ArgumentParser(prog="rcb_quadruped.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--instance", default="/app/instance.json")
    r.add_argument("--traj", default="/app/output/trajectory.npz")
    r.add_argument("--out")
    r.add_argument("--video")
    i = sub.add_parser("info")
    i.add_argument("instance", nargs="?", default="/app/instance.json")
    a = ap.parse_args(argv)
    if a.cmd == "info":
        s = Session(a.instance)
        print(json.dumps({"env": s.env, "seed": s.inst.get("seed"), "state_sha": s.state_sha(), "horizon": s.horizon}))
        return 0
    os.environ["RCB_AGENT_TRACE_DIR"] = ""
    s = Session(a.instance, check_hash=False)
    out: dict[str, Any] = {"instance_ok": bool(s.instance_ok)}
    try:
        A = np.asarray(np.load(a.traj, allow_pickle=False)["actions"], dtype=np.float64)
        out.update(s.replay(A), n_actions=int(len(A)))
    except Exception as exc:  # a malformed trajectory is the agent's 0, reported as such
        out.update(success=False, bad_trajectory=1, error=repr(exc)[:300])
    if a.video and not out.get("bad_trajectory"):
        try:
            s.render_video(A, a.video)
            out["video"] = True
        except Exception as exc:
            out["video"] = False
            out["video_error"] = repr(exc)[:300]
    if a.out:
        Path(a.out).write_text(json.dumps(out))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
