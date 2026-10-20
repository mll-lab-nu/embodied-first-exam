"""eai-standard/2.3 sim service for MuJoCo Playground's quadruped standard-realtime tasks -- the adapter behind the shared
realtime layer (`python /srv/rcb_realtime.py`, which imports this module and calls build(); docs/protocol/README.md §4b,
docs/benchmarks/mujoco-playground.md).

The simulator-specific half only: `Quadruped` implements rcb_service.Sim (the contract documented in rcb_service.py) for
one frozen instance, on the benchmark's own tooling module rcb_quadruped.Session -- the same scene, command schedule,
pushes, termination rule and success check as the standard twin's eai-standard/2.2 service
(environment/sim/server.py of `-standard`). The protocol, the clock, the plan, the episode, crash recovery and the
finalize are rcb_realtime.py's and rcb_service.py's, unchanged copies of the HumanoidBench sources
(ci_checks/check-tooling-identity.sh).

Grading: the live episode's verdict (owner, 2026-10-17; nothing is replayed): step() reports the task's
check on the live simulator after every control step (rcb_quadruped.Session.check(): getup's 25 upright steps and the
stands' 100-step hold are inside it; a joystick episode passes only at the horizon), which is the rule the replay of the
recorded episode applied, so no live_verdict() is needed. `start_sha` is the frozen instance's recorded state hash:
rcb_service refuses a fresh episode that does not start there (instance_mismatch, an infrastructure failure).

What the agent gets is what the standard twin gives, minus the 2.2 additions the realtime layer does not serve
(`/kinematics`, per-frame camera poses, depth modes, the `done` action): the cameras (RGB and depth), the robot's own
proprioception (joint positions, velocities and torques, the IMU's gyro, accelerometer, gravity direction and
velocimeter, the feet's contacts) with the joystick command in force (the standard twin's `meta["command_now"]`) and joint position targets (clipped to the actuator ranges and reported). The joystick
command schedule and, for gait tracking, the gait are in /spec, as in standard mode; nothing about the pushes is.

An episode ends as the standard twin's does: after the horizon (judged then: success or failure), when the robot meets
the environment's termination rule (a failure), at a getup / stand task's success, when the agent's time is up, or on a
simulator error.

Rendering: MuJoCo on the GPU (EGL) when the container reaches the NVIDIA driver, else OSMesa. On a clock that does not
stop a render is time the simulator thread cannot step. The image's NVIDIA EGL ICD manifest may be missing (the toolkit
mounts the library under NVIDIA_DRIVER_CAPABILITIES=graphics but not always the manifest); this module writes one to
/tmp and points libglvnd at it before rcb_quadruped probes EGL (RCB_GL=egl|osmesa forces one).

Settings (environment/docker-compose.yaml): RCB_INSTANCE (the frozen instance.json), RCB_DATA, RCB_RESET_BUDGET,
RCB_WALL_CLOCK_S, RCB_SLOWDOWN (rcb_realtime / rcb_service), RCB_GL.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _egl_manifest() -> None:
    """Make the NVIDIA EGL driver reachable for rcb_quadruped's own EGL probe (inert without it)."""
    gl = os.environ.get("RCB_GL", "auto")
    if gl in ("egl", "osmesa"):
        os.environ["RCB_MUJOCO_GL"] = gl
        return
    if not os.path.exists("/dev/nvidiactl") or os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
        return
    vendors = [p for d in ("/usr/share/glvnd/egl_vendor.d", "/etc/glvnd/egl_vendor.d") if os.path.isdir(d)
               for p in os.listdir(d)]
    if any("nvidia" in v for v in vendors):
        return
    os.makedirs("/tmp/rcb_egl", exist_ok=True)
    manifest = "/tmp/rcb_egl/10_nvidia.json"
    with open(manifest, "w") as f:
        f.write('{"file_format_version": "1.0.0", "ICD": {"library_path": "libEGL_nvidia.so.0"}}\n')
    mesa = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"
    os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"] = manifest + (f":{mesa}" if os.path.exists(mesa) else "")


_egl_manifest()
os.environ.pop("MUJOCO_GL", None)          # the image's default (osmesa) is not a choice: rcb_quadruped probes
os.environ.pop("PYOPENGL_PLATFORM", None)
os.environ["RCB_SESSION_LOG"] = ""
os.environ["RCB_AGENT_TRACE_DIR"] = ""
import rcb_quadruped as Q  # noqa: E402  (first: it picks the rendering backend before mujoco loads)
import mujoco  # noqa: E402

from rcb_service import main  # noqa: E402

GL_BACKEND = os.environ.get("MUJOCO_GL", "?")
CAM_W, CAM_H = 320, 240                    # the standard twin's
GL2CV = np.diag([1.0, -1.0, -1.0])


class Quadruped:
    """One frozen quadruped instance behind the rcb_service.Sim contract (see the module docstring)."""

    def __init__(self, instance: str):
        self.instance = instance
        self.s = Q.Session(instance, check_hash=False)            # the start is checked by the layer (start_sha), as a give-up
        self.start_sha = str(self.s.inst.get("state_sha") or "")  # the frozen instance's recorded t = 0 state hash
        m = self.m = self.s.model
        self.control_dt = float(self.s.control_dt)
        self.max_control_steps = int(self.s.horizon)
        self.raw_dim = Q.N
        self.cameras = tuple(self.s.cameras)
        self.depth_cameras = self.cameras
        feet = self.s.robot["feet"]
        j = self.s.joint_names
        self.proprio_layout = (list(j) + [f"{n}_vel" for n in j] + [f"{n}_effort" for n in j]
                               + ["gyro_x", "gyro_y", "gyro_z", "acc_x", "acc_y", "acc_z", "gravity_x", "gravity_y",
                                  "gravity_z", "linvel_x", "linvel_y", "linvel_z"] + [f"{f}_contact" for f in feet] + ["cmd_vx", "cmd_vy", "cmd_wz"])
        self._renderer = None
        self._depth = None
        self.cmd = self.s.targets.copy()
        self.images([self.cameras[0]], False)                     # warms up the GL context

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        s, m = self.s, self.m
        limits = dict(zip(s.joint_names, np.stack([s.lower, s.upper], axis=1).round(4).tolist()))
        sched = [] if s.commands is None else [
            {"from_s": round(int(c["start_step"]) * self.control_dt, 2), "from_step": int(c["start_step"]),
             "vx_mps": round(c["vx"], 4), "vy_mps": round(c["vy"], 4), "wz_radps": round(c["wz"], 4)}
            for c in s.inst["commands"]]
        episode = {
            "joystick": f"an episode lasts {s.horizon} control steps (the {s.horizon * self.control_dt:g} s command "
                        f"schedule) and is judged then; it ends early as a failure when the robot meets its termination "
                        f"rule ({s.spec.get('term_text')}), or when your time is up",
            "getup": f"an episode ends the moment the robot has stood upright for {Q.HOLD_STEPS} control steps in a row "
                     f"(success), after {s.horizon} control steps, or when your time is up",
            "stand_on_two": f"an episode ends the moment the pose has been held for {Q.POSE_HOLD_STEPS} control steps in "
                            f"a row (success), when the robot meets the termination rule (a failure), after {s.horizon} "
                            "control steps, or when your time is up",
        }[s.kind]
        cams = {}
        for c in self.cameras:
            i = m.camera(c).id
            f = 0.5 * CAM_H / math.tan(math.radians(float(m.cam_fovy[i])) / 2)
            follows = int(m.cam_mode[i]) != 0
            cams[c] = {"hw": [CAM_H, CAM_W], "intrinsic_cv": [[f, 0.0, CAM_W / 2], [0.0, f, CAM_H / 2], [0.0, 0.0, 1.0]],
                       "fovy_deg": round(float(m.cam_fovy[i]), 2),
                       "mounted": ("follows the robot's centre of mass at a fixed offset; it does not turn with the robot"
                                   if follows else "fixed to the robot's head: moves and turns with it")}
        out = {
            "simulator": "MuJoCo 3.3.7 (MuJoCo Playground's scene, plain MuJoCo on the CPU)",
            "robot": s.robot["name"],
            "task_text": s.inst["text"],
            "episode": episode,
            "action_types": {"joint_position": {
                "dim": Q.N, "layout": list(s.joint_names), "lower": s.lower.tolist(), "upper": s.upper.tolist(),
                "units": "rad",
                "semantics": "absolute targets of the 12 joint position actuators, one per control step; rows dt apart "
                             "(a whole multiple of control_dt), `hold` or `linear` between rows; values outside the "
                             "limits are clipped and reported"}},
            "cameras": cams,
            "proprio": {"joint_pos": "measured joint positions (rad), in the action's order",
                        "*_vel": "measured joint velocities (rad/s)", "*_effort": "actuator torques (N m)",
                        "gyro_*": "angular velocity of the trunk, IMU frame (rad/s)",
                        "acc_*": "specific force at the IMU, IMU frame (m/s^2; +9.81 up at rest)",
                        "gravity_*": "unit vector of gravity's direction in the IMU frame ([0, 0, -1] when level)",
                        "linvel_*": "linear velocity of the trunk at the IMU, IMU frame (m/s; the IMU's velocimeter)",
                        "*_contact": "1 when the foot touches the ground, else 0",
                        "cmd_*": "the joystick command in force at the next control step (vx, vy in m/s in the robot's "
                                 "own frame, yaw rate in rad/s; 0 without a schedule): command_schedule's row"},
            "command_schedule": sched,
            "world": {"frame": "z up; the robot starts where the episode puts it (no world coordinates are given)",
                      "up": "+z", "units": {"length": "m", "angle": "rad", "time": "s"}},
            "robot_spec": {"name": s.robot["name"], "joints": list(s.joint_names), "joint_limits": limits,
                           "joint_order": s.robot["joint_text"], "home_pose": dict(zip(s.joint_names, s.home.tolist())),
                           "feet": list(s.robot["feet"]),
                           "controller": {"type": "joint position actuators (PD)",
                                          "kp_nm_per_rad": float(m.actuator_gainprm[0, 0]),
                                          "kd_nms_per_rad": float(m.dof_damping[6] - m.actuator_biasprm[0, 2])},
                           "physics_substeps": int(s.substeps)},
            "depth": {"cameras": list(self.cameras), "units": "z-depth in metres, pixel for pixel with the camera's "
                      "image; noise-free"},
            "gl_backend": GL_BACKEND,
        }
        if s.gait:
            out["gait"] = {k: s.gait[k] for k in ("name", "frequency_hz", "foot_height_m", "phase0", "phase_dt")} | {
                "feet": list(s.robot["feet"]),
                "rule": "foot i's target height at control step t is get_rz(wrap(phase0[i] + t * phase_dt)) with "
                        "Playground's gait.get_rz (a cubic Bezier from 0 up to foot_height_m over the first half of the "
                        "phase, then down); phases in rad, wrapped to [-pi, pi)"}
        return out

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.m, CAM_H, CAM_W)
        r, rgb, dep = self._renderer, {}, {}
        for c in cameras:
            r.update_scene(self.s.data, camera=c)
            rgb[c] = r.render().copy()
            if depth and c in self.depth_cameras:
                r.enable_depth_rendering()
                r.update_scene(self.s.data, camera=c)
                z = np.asarray(r.render(), dtype=np.float32).copy()
                r.disable_depth_rendering()
                dep[c] = np.where(np.isfinite(z) & (z > 0), z, 0.0).astype(np.float32)
        return rgb, dep

    def proprio(self) -> np.ndarray:
        s, d = self.s, self.s.data
        return np.concatenate([d.qpos[7:], d.qvel[6:], d.actuator_force, s.sensor("gyro"), s.sensor("accelerometer"),
                               s.gravity(), s.sensor("local_linvel"), s.foot_contacts(), s.command_now()]).astype(np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        lo, hi = self.s.lower, self.s.upper
        out = np.clip(rows, lo, hi)
        report = [{"row": int(i), "index": int(j), "reason": f"outside [{lo[j]:.4g}, {hi[j]:.4g}]"}
                  for i, j in np.argwhere(out != rows)]
        return out, report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return "joint_position", self.cmd

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        chk = self.s.step(row)
        self.cmd = np.asarray(row, dtype=np.float64).copy()
        s = self.s
        fell = s.kind in ("joystick", "stand_on_two") and s.fell_at is not None
        success = bool(chk["success"]) and (s.kind != "joystick" or s.done)
        return bool(fell or s.done or success), success, {}

    def reset(self) -> None:
        self.s.reset()
        self.cmd = self.s.targets.copy()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """The episode's video, after the verdict: one pass over the rows from the frozen start on this simulator."""
        self.s.render_video(rows, path)


def build() -> Quadruped:
    return Quadruped(os.environ.get("RCB_INSTANCE", os.path.join(HERE, "instance.json")))


if __name__ == "__main__":
    main(build)
