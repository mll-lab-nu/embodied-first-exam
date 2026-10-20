"""eai-standard/2.3 sim service for MyoSuite's standard-realtime tasks -- the adapter behind the shared realtime layer
(`python /srv/rcb_realtime.py`, which imports this module and calls build(); docs/protocol/README.md §4b,
docs/benchmarks/myosuite.md).

The simulator-specific half only: `MyoSuite` implements rcb_service.Sim (the contract documented in rcb_service.py) for
one frozen instance, on the benchmark's own tooling module rcb_myosuite.Session -- the same scene, action and success
rule as the standard twin's eai-standard/2.2 service (environment/sim/server.py of `-standard`). The protocol, the
clock, the plan, the episode, crash recovery and the finalize are rcb_realtime.py's and rcb_service.py's, unchanged
copies of the HumanoidBench sources (ci_checks/check-tooling-identity.sh).

Grading (owner, 2026-10-17): the verdict is the live episode's, judged by the layer from step(): the task's
rule as Session.step applies it to the steps this service ran (table_tennis: MyoChallenge's own success event; any hold
or track window of a family is part of that rule, so the episode only ends in success once it is complete). There is no
live_verdict(): nothing is left that a replay applied and the live run did not. Nothing is replayed to grade it; the
video is rendered from the trajectory after the verdict (render_video). `start_sha` is the frozen instance's recorded
state hash: the layer refuses a fresh episode whose scene does not start there (instance_mismatch, infrastructure).

What the agent gets is what the standard twin gives, minus the 2.2 additions the realtime layer does not serve
(`/kinematics`, per-frame camera poses, depth modes): the cameras (RGB, and depth on request from every camera that
rides on the world or the body), the body's own proprioception (joint positions and velocities, muscle activations and
lengths, the actuators' generalized force on each joint, and a free-standing body's root pose and velocity) and the
actuator commands. Nothing about objects, balls, opponents or goals leaves this process; a camera that rides on a body
of the scene gives images only (its pose would place that body).

Rendering: MuJoCo on the GPU (EGL) when the container can reach the NVIDIA driver, else OSMesa on the CPU. In
table_tennis an OSMesa frame takes 1.3 s and an EGL frame 5 ms; on a clock that does not stop, a render is time the
simulator thread cannot step, so the realtime twins reserve a GPU. The NVIDIA container toolkit mounts libEGL_nvidia
under NVIDIA_DRIVER_CAPABILITIES=graphics but, on some hosts, not its ICD manifest; this module writes one to /tmp and
points libglvnd at it (inert where the library is absent: libglvnd falls back to Mesa), then tries EGL in a throwaway
process, because MuJoCo binds its backend once per process at `import mujoco`.

Settings (environment/docker-compose.yaml): RCB_INSTANCE (the frozen instance), RCB_TASK_INFO (task.json: task text,
default camera), RCB_IMAGE_HW (the cameras' "H,W", default "480,640", the standard twin's), RCB_DATA, RCB_RESET_BUDGET,
RCB_WALL_CLOCK_S, RCB_SLOWDOWN (rcb_realtime / rcb_service), RCB_GL (auto: EGL when it works, else OSMesa).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _resolve_gl_backend() -> str:
    """MuJoCo's offscreen backend: RCB_GL (egl | osmesa) if set, else EGL if a probe process can open a context on the
    NVIDIA driver, else OSMesa. The image's own MUJOCO_GL (osmesa, for the CPU-only standard twin) is not a choice."""
    if os.environ.get("RCB_GL", "auto") in ("egl", "osmesa"):
        return os.environ["RCB_GL"]
    if not os.path.exists("/dev/nvidiactl"):
        return "osmesa"
    vendors = [p for d in ("/usr/share/glvnd/egl_vendor.d", "/etc/glvnd/egl_vendor.d") if os.path.isdir(d)
               for p in sorted(os.listdir(d))]
    if not any("nvidia" in v for v in vendors) and not os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"):
        os.makedirs("/tmp/rcb_egl", exist_ok=True)
        manifest = "/tmp/rcb_egl/10_nvidia.json"
        with open(manifest, "w") as f:
            f.write('{"file_format_version": "1.0.0", "ICD": {"library_path": "libEGL_nvidia.so.0"}}\n')
        mesa = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"
        os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"] = manifest + (f":{mesa}" if os.path.exists(mesa) else "")
    probe = ("import os; os.environ['MUJOCO_GL'] = os.environ['PYOPENGL_PLATFORM'] = 'egl'; import mujoco; "
             "c = mujoco.GLContext(8, 8); c.make_current(); import OpenGL.GL as g; "
             "r = g.glGetString(g.GL_RENDERER).decode(); c.free(); print(r)")
    try:
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
        ok = out.returncode == 0 and "llvmpipe" not in out.stdout.lower()   # Mesa's EGL renders on the CPU as well
    except (OSError, subprocess.SubprocessError):
        ok = False
    return "egl" if ok else "osmesa"


GL_BACKEND = _resolve_gl_backend()
os.environ["MUJOCO_GL"] = os.environ["PYOPENGL_PLATFORM"] = GL_BACKEND
os.environ["RCB_SESSION_LOG"] = ""
import rcb_myosuite as M  # noqa: E402  (after the backend: it only sets a default)
import mujoco  # noqa: E402

M.SESSION_LOG = ""           # the sidecar's Session is not the agent's interaction log
from rcb_service import main  # noqa: E402

ROBOT = {
    "hand": ("MyoHand", "a musculoskeletal model of a human forearm and hand (MyoSuite)"),
    "arm": ("MyoArm", "a musculoskeletal model of a human shoulder, arm and hand (MyoSuite)"),
    "body": ("MyoArm with torso", "a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides "
                                  "on the floor (MyoSuite)"),
    "bimanual": ("MyoArm + MPL", "a musculoskeletal right arm and hand (MyoSuite's MyoArm) next to a motorized "
                                 "prosthetic left arm (the Modular Prosthetic Limb)"),
    "legs": ("MyoLegs", "a free-standing musculoskeletal model of a human torso and both legs (MyoSuite)"),
    "osl": ("MyoLeg + OSL", "a free-standing musculoskeletal model of a human with the right leg's muscles and an "
                            "Open-Source Leg knee-ankle prosthesis on the left (MyoSuite)"),
}
MUSCLE_TEXT = (
    "muscles: one real number a per muscle; excitation u = 1 / (1 + exp(-5 (a - 0.5))), a not clipped (a = -1: u ~ "
    "0.0006, 0.5: 0.5, 1: 0.92, 2: 0.9994); activations follow excitations with a first-order delay (~10 ms up, ~40 ms "
    "down); muscles only pull, one can cross several joints, and its force depends on its length and velocity")
GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])
CAM_MODES = {0: "fixed", 1: "track", 2: "trackcom", 3: "targetbody", 4: "targetbodycom"}
NO_POSE = ("not published: this camera rides on a body of the scene that is not yours, so its pose would be that "
           "body's position; it gives images only")


class MyoSuite:
    """One frozen MyoSuite instance behind the rcb_service.Sim contract (see the module docstring)."""

    def __init__(self, instance: str, task_info: dict, image_hw: tuple[int, int] = (480, 640)):
        self.instance = instance
        self.task = str(np.load(instance, allow_pickle=False)["task"])
        self.info = task_info
        self.s = M.Session(self.task, instance=instance)
        self.start_sha = self.s.instance_sha                       # the frozen instance's recorded start (the layer checks it)
        m = self.m = self.s.model
        self.H, self.W = image_hw
        self.control_dt = float(self.s.dt)
        self.max_control_steps = int(self.s.max_steps)          # a runaway guard: the task's own rule ends an episode
        self.nu = self.raw_dim = int(self.s.nu)
        acts = self.s.actuators()
        self.layout = [a["name"] for a in acts]
        self.mus_idx = [a["index"] for a in acts if a["kind"] == "muscle"]
        self.muscles = [acts[i]["name"] for i in self.mus_idx]
        self.other = [a for a in acts if a["kind"] != "muscle"]
        self.atype = "muscle" if not self.other else "actuators"
        self.act_adr = np.array([int(m.actuator_actadr[i]) for i in self.mus_idx], dtype=int)
        # the body's own joints (the key's hinge and the OBJ* joints are object state, never sent; free joints of balls,
        # objects and paddles are not in S.joints(); a free-standing body's root is reported on its own)
        limb = [j for j in self.s.joints() if j["name"] != "keyjoint" and not j["name"].startswith("OBJ")]
        self.j_names = [j["name"] for j in limb]
        self.j_q = np.array([j["qpos_adr"] for j in limb], dtype=int)
        self.j_v = np.array([j["dof_adr"] for j in limb], dtype=int)
        self.j_id = [m.joint(n).id for n in self.j_names]
        root = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "root")
        self.root = root if root >= 0 and int(m.jnt_type[root]) == 0 else None
        self.own_joints = set(self.j_id) | ({self.root} if self.root is not None else set())
        self.cameras = tuple(self.s.cameras())
        self.scene_cams = {c for c in self.cameras if self._scene_camera(c)}
        self.depth_cameras = tuple(c for c in self.cameras if c not in self.scene_cams)
        self.proprio_layout = ([f"q_{n}" for n in self.j_names] + [f"qd_{n}" for n in self.j_names]
                               + [f"act_{n}" for n in self.muscles] + [f"len_{n}" for n in self.muscles]
                               + [f"effort_{n}" for n in self.j_names]
                               + (["root_x", "root_y", "root_z", "root_qw", "root_qx", "root_qy", "root_qz",
                                   "root_vx", "root_vy", "root_vz", "root_wx", "root_wy", "root_wz"]
                                  if self.root is not None else []))
        self._depth_on = False
        self.render_frame(self.cameras[0])                          # warms up the GL context
        self.cmd = self.s.rest_action()

    # ------------------------------------------------------------------ what the agent may know
    def _own_body(self, b: int) -> bool:
        """A body fixed in the world or moved by the body's own joints alone; a mocap body (the opponent, goal markers)
        or one behind any other joint (objects, balls, the paddle) is scene state."""
        m = self.m
        while b > 0:
            if int(m.body_mocapid[b]) >= 0:
                return False
            first = int(m.body_jntadr[b])
            if any(j not in self.own_joints for j in range(first, first + int(m.body_jntnum[b]))):
                return False
            b = int(m.body_parentid[b])
        return True

    def _scene_camera(self, cam: str) -> bool:
        m, i = self.m, self.m.camera(cam).id
        bodies = [int(m.cam_bodyid[i])] + ([int(m.cam_targetbodyid[i])] if int(m.cam_mode[i]) in (3, 4) else [])
        return not all(self._own_body(b) for b in bodies if b >= 0)

    def _intrinsic(self, cam: str) -> list:
        f = 0.5 * self.H / math.tan(math.radians(float(self.m.cam_fovy[self.m.camera(cam).id])) / 2)
        return [[f, 0.0, self.W / 2], [0.0, f, self.H / 2], [0.0, 0.0, 1.0]]

    def _cam_T_gl(self, cam: str) -> np.ndarray:
        i, d = self.m.camera(cam).id, self.s.data
        T = np.eye(4)
        T[:3, :3] = d.cam_xmat[i].reshape(3, 3)                    # MuJoCo cameras: OpenGL axes (x right, y up, z back)
        T[:3, 3] = d.cam_xpos[i]
        return T

    def _camera_fact(self, cam: str) -> dict:
        m, i = self.m, self.m.camera(cam).id
        out = {"hw": [self.H, self.W], "intrinsic_cv": self._intrinsic(cam),
               "fovy_deg": round(float(m.cam_fovy[i]), 2)}
        if cam in self.scene_cams:
            return {**out, "mounted": "on a body of the scene that is not yours (it moves with it): images only",
                    "pose": NO_POSE}
        body, mode = m.body(int(m.cam_bodyid[i])).name, int(m.cam_mode[i])
        if mode != 0:
            return {**out, "mounted": f"tracking ({CAM_MODES.get(mode, mode)}) the body {body}: it follows that body's "
                                      "position (or its subtree's centre of mass) without turning with it"}
        if body == "world":
            ext = np.linalg.inv(self._cam_T_gl(cam) @ GL2CV)[:3, :]
            return {**out, "mounted": "static", "extrinsic_cv": ext.round(6).tolist(),
                    "pose_note": "extrinsic_cv: world -> camera, OpenCV axes (x right, y down, z forward)"}
        b = m.body(body).id
        Tb = np.eye(4)
        Tb[:3, :3] = self.s.data.xmat[b].reshape(3, 3)
        Tb[:3, 3] = self.s.data.xpos[b]
        link_T_cam = np.linalg.inv(Tb) @ self._cam_T_gl(cam) @ GL2CV
        return {**out, "mounted": f"fixed to the body {body}: it moves with it",
                "link": body, "link_T_cam_cv": link_T_cam.round(6).tolist()}

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        m, robot = self.m, ROBOT[M.BODY[self.task]]
        lo = [float(m.jnt_range[j, 0]) if m.jnt_limited[j] else None for j in self.j_id]
        hi = [float(m.jnt_range[j, 1]) if m.jnt_limited[j] else None for j in self.j_id]
        action = {"dim": self.nu, "layout": self.layout, "lower": None, "upper": None,
                  "units": MUSCLE_TEXT + ("; the other actuators: see `actuators`" if self.other else ""),
                  "semantics": "one row per control step, every actuator in `layout` order; rows dt apart (a whole "
                               "multiple of control_dt), `linear` (default: a straight line from the command in force) "
                               "or `hold` between rows; nothing is clipped by the service (MuJoCo clips the non-muscle "
                               "controls to their ranges)"}
        if self.other:
            action["actuators"] = [{k: a[k] for k in ("index", "name", "kind", "command")} for a in self.other]
        return {
            "simulator": "MyoSuite 2.12.2 on MuJoCo 3.6.0 (CPU physics)",
            "robot": f"{robot[0]}: {robot[1]}, {len(self.muscles)} muscles"
                     + (f" and {len(self.other)} other actuators" if self.other else ""),
            "task_text": self.info["task_text"],
            "episode": "an episode ends at the task's own success event or failure (see task_text), when your time is "
                       "up, or on a simulator error",
            "action_types": {self.atype: action},
            "cameras": {c: self._camera_fact(c) for c in self.cameras},
            "default_camera": self.info["default_cameras"][0],
            "proprio": {
                "groups": {"q_*": "joint positions of the body (rad; m for sliding joints)",
                           "qd_*": "joint velocities (rad/s; m/s)",
                           "act_*": "muscle activations in [0, 1] (they follow the excitations with a first-order delay)",
                           "len_*": "muscle-tendon lengths (m)",
                           "effort_*": "generalized force of all actuators on each joint (N m; N)",
                           **({"root_*": "the free-standing root (the pelvis) in the world frame: position (m), wxyz "
                                         "quaternion, linear (m/s, world axes) and angular velocity (rad/s, its own axes)"}
                              if self.root is not None else {})}},
            "static": {"muscles": self.muscles},
            "world": {"frame": "MyoSuite's world frame, z up (no positions of the scene are given)", "up": "+z",
                      "units": {"length": "m", "angle": "rad", "time": "s"}, "quaternion_order": "wxyz"},
            "robot_spec": {
                "name": robot[0],
                "joints": [{"name": n, "type": "prismatic" if int(m.jnt_type[j]) == 2 else "revolute",
                            "position_limits": [lo[k], hi[k]] if lo[k] is not None else None}
                           for k, (n, j) in enumerate(zip(self.j_names, self.j_id))],
                "controller": "muscle actuators (MuJoCo muscle model); no joint-level controller"
                              + ("; plus the non-muscle actuators in action_types" if self.other else ""),
                "physics_hz": round(1.0 / self.control_dt * int(self.s.base.frame_skip), 3),
            },
            "depth": {"cameras": list(self.depth_cameras), "units": "z-depth in metres, pixel for pixel with the "
                      "camera's image; noise-free"} if self.depth_cameras else None,
            "gl_backend": GL_BACKEND,
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def render_frame(self, cam: str) -> np.ndarray:
        if self._depth_on:
            self.s._renderer.disable_depth_rendering()
            self._depth_on = False
        return self.s.render_frame(cam, (self.H, self.W))

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb = {c: self.render_frame(c) for c in cameras}
        dep = {}
        if depth:
            r = self.s._renderer                                   # the same renderer (a second context reads garbage
            for c in cameras:                                      # under OSMesa)
                if c in self.depth_cameras:
                    r.enable_depth_rendering()
                    self._depth_on = True
                    r.update_scene(self.s.data, camera=c)
                    z = np.asarray(r.render(), dtype=np.float32).copy()
                    dep[c] = np.where(np.isfinite(z) & (z > 0), z, 0.0).astype(np.float32)
            if self._depth_on:
                r.disable_depth_rendering()
                self._depth_on = False
        return rgb, dep

    def proprio(self) -> np.ndarray:
        d, phys = self.s.data, self.s.base.robot.mj_data
        # joint_effort from the physics, not the mirror: MyoSuite steps its robot wrapper's own MjData and refreshes
        # S.data from qpos / qvel / act only (the standard twin's server.py, 2026-10-09)
        parts = [d.qpos[self.j_q], d.qvel[self.j_v], d.act[self.act_adr], d.actuator_length[self.mus_idx],
                 phys.qfrc_actuator[self.j_v]]
        if self.root is not None:
            qa, va = int(self.m.jnt_qposadr[self.root]), int(self.m.jnt_dofadr[self.root])
            parts += [d.qpos[qa:qa + 7], d.qvel[va:va + 6]]
        return np.concatenate(parts).astype(np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        return np.asarray(rows, dtype=np.float64), []               # as the standard twin: nothing clipped here

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return self.atype, self.cmd

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        running = self.s.step(row)
        self.cmd = np.asarray(row, dtype=np.float64).copy()
        return (not running), bool(self.s.success), ({} if running else {"why": self.s.reason})

    def reset(self) -> None:
        self.s.reset()
        self.cmd = self.s.rest_action()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        self.s.save_trajectory(rows, path, meta)

    def render_video(self, rows: np.ndarray, path: str) -> None:
        """The episode's video, after the verdict (it decides nothing): the rows replayed on this service's session."""
        import imageio.v2 as imageio
        cam = self.info["default_cameras"][0]
        self.s.render_video(rows, path, cameras=[cam], every=2, fps=25, size=(240, 320))
        imageio.imwrite(os.path.splitext(path)[0] + ".last.png", self.s.render_frame(cam, (self.H, self.W)))


def build() -> MyoSuite:
    env = os.environ.get
    hw = [int(v) for v in env("RCB_IMAGE_HW", "480,640").split(",")]
    info = json.load(open(env("RCB_TASK_INFO", os.path.join(HERE, "task.json"))))
    return MyoSuite(env("RCB_INSTANCE", os.path.join(HERE, "instance.npz")), info, (hw[0], hw[1]))


if __name__ == "__main__":
    main(build)
