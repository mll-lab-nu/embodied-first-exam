"""eai-standard/2.3 sim service for RoboCasa365's standard-realtime tasks -- the adapter behind the shared realtime layer
(`python /srv/rcb_realtime.py`, which imports this module and calls build(); docs/PROTOCOL.md §4b,
docs/benchmarks/robocasa365.md "Standard-realtime").

The simulator-specific half only: `RoboCasa` implements rcb_service.Sim (the contract documented in rcb_service.py) for
one frozen instance on the benchmark's own tooling module, casa_tool.Session -- the same scene, native controller
command, success check (`_check_success`, twice per control step) and replay as the standard twin's service
(environment/sim/server_casa.py of `-standard`) and the privileged verifier. The protocol, the clock, the plan, the
episode, crash recovery and the finalize are rcb_realtime.py's and rcb_service.py's, unchanged copies of the
HumanoidBench sources (ci_checks/check-tooling-identity.sh).

What the agent gets is what the standard twin gives: the robot's cameras (RGB and depth, 320 x 240, OSMesa on the CPU as
in the standard twin), the robot's own joints, end-effector positions and last command, and the task's instruction. The
cameras ride on the robot, so each camera's current pose is part of every proprioception row (`cam_<camera>_*`: the
camera-to-world pose, OpenGL axes, as the standard twin's `cam2world_gl`); their intrinsics are in /spec. Never an
object's pose, the scene layout or the success check.

The episode: the standard twin grades the state after the last control step of an episode that runs until the agent's
time is up. On a clock that does not stop such an episode would be as long as the agent's time and its replay longer
than the verifier's; here an episode ends at the first control step after which the success check holds (the privileged
rule applied to the trajectory up to that step), after max_control_steps (the privileged deliverable's cap, 3000 steps =
150 s of robot time), when the agent's time is up, or on a simulator error; the agent has resets (rcb_service).

Settings (environment/docker-compose.yaml): RCB_INSTANCE (the frozen instance), RCB_MAX_CONTROL_STEPS (3000), RCB_DATA,
RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_SLOWDOWN (rcb_realtime / rcb_service).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import casa_tool  # noqa: E402  (imports mujoco with the image's backend: OSMesa, as the standard twin)
import mujoco  # noqa: E402
from rcb_service import main  # noqa: E402

ACTION_NAME = {12: "ee_delta", 13: "joint_position", 24: "ee_pose"}
W, H = 320, 240
CAM_COLS = ("x", "y", "z", "r00", "r01", "r02", "r10", "r11", "r12", "r20", "r21", "r22")


class RoboCasa:
    """One frozen RoboCasa365 instance behind the rcb_service.Sim contract (see the module docstring)."""

    def __init__(self, instance: str, max_control_steps: int = casa_tool.MAX_STEPS):
        self.instance = instance
        self.s = casa_tool.Session(instance, enable_render=True)
        spec = self.s.action_spec
        self.atype = ACTION_NAME[int(spec["dim"])]
        self.raw_dim = int(spec["dim"])
        self.control_dt = float(self.s.control_dt)
        self.max_control_steps = int(max_control_steps)
        self.cameras = tuple(self.s.camera_views)
        self.depth_cameras = self.cameras
        self.proprio_layout = list(self.s.proprio_layout) + [f"cam_{c}_{k}" for c in self.cameras for k in CAM_COLS]
        self._depth = None                      # (model it was made for, renderer)
        self._warm()

    def _warm(self) -> None:
        """Make the cameras' renderer now (an OSMesa context takes about 2 s): its first frame must not be taken from a
        running clock. casa_tool.Session.reset() rebuilds the scene and its renderers, so this runs after every reset."""
        self.s.render(self.cameras[0], (W, H))

    # ------------------------------------------------------------------ cameras
    def _cam_id(self, cam: str) -> int:
        return self.s.model.camera(self.s.camera_views[cam]["camera"]).id

    def _cam2world(self, cam: str) -> np.ndarray:
        """The camera-to-world pose (OpenGL axes: x right, y up, looking along -z) the image is rendered from."""
        i, d = self._cam_id(cam), self.s.data
        return np.column_stack([np.asarray(d.cam_xmat[i], float).reshape(3, 3), np.asarray(d.cam_xpos[i], float)])

    def _depth_renderer(self):
        m = self.s.model
        if self._depth is None or self._depth[0] is not m:     # a reset rebuilds the environment (a new model)
            if self._depth is not None:
                self._depth[1].close()
            r = mujoco.Renderer(m, H, W)
            r.enable_depth_rendering()
            self._depth = (m, r)
        return self._depth[1]

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        a = self.s.action_spec
        fovy = {c: float(self.s.model.cam_fovy[self._cam_id(c)]) for c in self.cameras}
        f = {c: 0.5 * H / np.tan(np.deg2rad(fovy[c]) / 2) for c in self.cameras}
        return {
            "simulator": "robosuite 1.5.2 / RoboCasa365 (MuJoCo 3.3.1, CPU)",
            "robot": "franka-panda-omron: a Franka Panda arm on an Omron mobile base with a torso lift",
            "task_text": self.s.inst.get("text", ""),
            "episode": (f"an episode ends at the first control step after which the task's success check holds "
                        f"(success), after {self.max_control_steps} control steps (failed), when your time is up, or "
                        "on a simulator error"),
            "action_types": {self.atype: {
                "dim": self.raw_dim, "layout": list(a["names"]), "lower": list(a["lower"]), "upper": list(a["upper"]),
                "units": [c["unit"] for c in a["channels"]], "kinds": [c["kind"] for c in a["channels"]],
                "parts": a["parts"], "frame": a["frame"],
                **{k: a[k] for k in ("grip", "hybrid_mode") if k in a},
                "semantics": ("the robot's native composite-controller command (robosuite), one row per control step; "
                              "kinds: delta = motion per control step (0 holds still), absolute = target, grip / mode "
                              "= held setting; rows dt apart, `linear` (default: a straight line from the command in "
                              "force) or `hold`; clipped to [lower, upper] (reported in meta.clipped)")}},
            "cameras": {c: {"hw": [H, W], "fovy_deg": fovy[c], "intrinsic_cv": [[f[c], 0, W / 2], [0, f[c], H / 2], [0, 0, 1]],
                            "mounted": "on the robot: it moves with the base, torso or arm; its current pose is in "
                                       f"every proprioception row (cam_{c}_x .. cam_{c}_r22)"}
                        for c in self.cameras},
            "proprio": {"joints": "<joint>_pos (rad or m), <joint>_vel: the robot's own joints (arm, gripper, mobile "
                                  "base, torso)",
                        "eef": "eef_<arm>_x/y/z: the end effector's position, world frame (m)",
                        "cmd": "cmd_<channel>: the command in force (the last row executed, clipped)",
                        "camera": "cam_<camera>_x/y/z, _r00.._r22: each camera's pose, camera-to-world: position (m) and "
                                  "the rotation matrix row by row, OpenGL axes (x right, y up, looking along -z)"},
            "world": {"frame": "metres, z up; no positions of the scene are given", "up": "+z"},
            "depth": {"cameras": list(self.cameras), "units": "z-depth in metres along the camera axis, pixel for "
                      "pixel with the camera's image; noise-free"},
        }

    def interpolable(self, typ: str) -> bool:
        return True

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        rgb = {c: self.s.render(c, (W, H)) for c in cameras}
        dep = {}
        if depth:
            r = self._depth_renderer()
            for c in cameras:
                r.update_scene(self.s.data, camera=self._cam_id(c), scene_option=casa_tool.scene_option())
                z = np.asarray(r.render(), dtype=np.float32).copy()
                dep[c] = np.where(np.isfinite(z) & (z > 0), z, 0.0).astype(np.float32)
        return rgb, dep

    def proprio(self) -> np.ndarray:
        poses = [self._cam2world(c) for c in self.cameras]          # each: position, then the rotation row by row
        cams = [np.concatenate([T[:, 3], T[:, :3].reshape(-1)]) for T in poses]
        return np.concatenate([np.asarray(self.s.proprio(), np.float64), *cams]).astype(np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        rows = np.asarray(rows, dtype=np.float64)
        out = np.clip(rows, self.s.lower, self.s.upper)
        report = [{"row": int(i), "index": int(j), "reason": "outside [lower, upper]"} for i, j in np.argwhere(out != rows)]
        return out, report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, typ: str) -> np.ndarray:
        return np.asarray(self.s.targets, dtype=np.float64).copy()

    def hold(self) -> tuple[str, np.ndarray]:
        return self.atype, self.s.hold_targets()          # delta channels zero: the robot holds still

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        self.s.step(row)
        return False, bool(self.s.success), {}

    def reset(self) -> None:
        self.s.reset()                                     # rebuilds the scene from the frozen instance (seconds)
        self._warm()

    def state_sha(self) -> str:
        return self.s.state_sha()

    def verify(self, rows: np.ndarray) -> dict:
        """The recorded episode from the frozen instance in a fresh casa_tool session (as the standard twin's service)."""
        fresh = casa_tool.Session(self.instance)
        try:
            r = fresh.replay(np.asarray(rows, dtype=np.float64).reshape(-1, self.raw_dim))
            return {"success": bool(r["success"]) and not r["initial_success"], "state_sha": r["state_sha"]}
        finally:
            fresh.close()

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        a = np.asarray(rows, dtype=np.float64).reshape(-1, self.raw_dim)
        np.savez(path, actions=a, instance_sha=np.array(self.s.instance_sha), meta=np.array(json.dumps(meta)))

    def render_video(self, rows: np.ndarray, path: str) -> None:
        self.s.render_video(np.asarray(rows, dtype=np.float64).reshape(-1, self.raw_dim), path)


def build() -> RoboCasa:
    env = os.environ.get
    return RoboCasa(env("RCB_INSTANCE", os.path.join(HERE, "instance.npz")),
                    int(env("RCB_MAX_CONTROL_STEPS") or casa_tool.MAX_STEPS))


if __name__ == "__main__":
    main(build)
