"""
rcb_topogym.py — task-local tooling for TopoGym (Genesis 1.2.1 physics on CUDA, Nyx RGB): frozen instance / privileged
primitives / action recording / replay. Same shape as robot_coding_bench's rcb_robowits.py (fa59c1a6), so agents and
verifiers share one mental model across benchmarks.

Concepts
--------
instance   : one TopoGym scene = a task family's variation built from a fixed seed (task_id, variation_id, seed) plus the
             full simulator configuration, frozen in instance.json ("simulator"). `make-instance` writes it, so a task
             directory is self-contained: Session(instance=...) rebuilds the scene from the task's own copy. The state
             hash of the built scene (state_sha) is stored too. On load, `instance_exact` = hash equality and
             `instance_matches` = hash equality or every object / joint pose within tolerance.
trajectory : the (T, action_dim) JOINT_ABS actions handed to the simulator, one row per control step: per arm (the order
             of ACTION_LAYOUT) the arm joint targets (rad) and the gripper opening width (m, 0 = closed .. open width).
             The physics runs on the GPU (CUDA). Its contact solver is not bit-deterministic: repeated replays agree to
             ~1e-11 in the state but not bit for bit, so `deterministic` (state hashes equal) is reported and not
             required; every replay must complete the task (the same rule as robot_coding_bench's GPU backend).
episode end: a task's success predicate, or one of its failure predicates (e.g. touching the buzz wire), ends the
             simulated episode: later steps are recorded but no longer move the scene, and status()["episode_end"] says
             why. reset() starts again from the frozen state.
grasping   : a family may enable TopoGym's passive grasp assistance (instance.json simulator.grasp_assist; the rules are
             in robot_spec()["grippers"][...]["command"]); primitives()["object_in_hand"] says what a gripper holds.
budget     : there is no step budget: the agent's wall clock is the limit. MAX_STEPS only stops runaway trajectories.

CLI
---
  python rcb_topogym.py make-instance --task cube_pick_place --eval-index 0 --out instance.json
  python rcb_topogym.py run-oracle    --task cube_pick_place --instance instance.json --code oracle.py --out traj.npz
  python rcb_topogym.py replay        --task cube_pick_place --instance instance.json --traj traj.npz [--repeat 2] [--video replay.mp4]
  python rcb_topogym.py render        --task cube_pick_place --instance instance.json --traj traj.npz --out replay.mp4 [--every 2]
  python rcb_topogym.py selftest      --task cube_pick_place --eval-index 0 --code oracle.py --out-dir /tmp/selftest   # 3 fresh processes
  python rcb_topogym.py describe      --task cube_pick_place --instance instance.json   # cameras, robot, predicate (task generator)

Python (what the agent gets)
----------------------------
  from rcb_topogym import Session
  s = Session("cube_pick_place", instance="/app/instance.json")   # builds the scene and compiles kernels
  s.reset()                          # back to the frozen instance state (unlimited)
  p = s.primitives()                 # thin wrappers of the low-level action: move_ee, move_joints, set_gripper, hold, ...
  s.objects()                        # task objects: name -> position, orientation_wxyz, bounds, size, ...
  s.render_frame(cam)                # RGB (H, W, 3) uint8; s.render_grid(), s.render_video(actions, path); s.VIDEO_CAMERAS
  s.record_start(); ...; actions = s.record_stop()   # (T, action_dim) low-level actions, one row per control step
  s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end'}
  s.replay(actions)                  # resets, replays open-loop, returns status -> self-check
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""
from __future__ import annotations

import os

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

# Interaction log (the same contract as rcb_robowits.py): every Session appends one line per session start/reset/record/
# replay/exit, with the control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected
# with the artifacts) and to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl where that directory exists).
# The verifier reports it as self-reported cost (agent_sessions / agent_resets / agent_sim_steps). RCB_SESSION_LOG=""
# disables it (the verifier and the limited service do).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    if SESSION_LOG_KEEP and os.path.isdir(os.path.dirname(SESSION_LOG_KEEP)):
        try:
            with open(SESSION_LOG_KEEP, "a") as f:
                f.write(line)
        except OSError:
            pass


DEFAULT_BACKEND = "cuda"          # TopoGym's physics runs on the GPU; there is no CPU backend
MAX_STEPS = int(os.environ.get("RCB_MAX_STEPS", "200000"))   # runaway guard on a trajectory's length, not a budget

# --------------------------------------------------------------------------- task family registry
# One entry per family; `instances` lists (variation, seed) per eval index (i00 = eval index 0). `grasp_assist` is the
# passive grasp assistance of that family's instances: None = physical grasping only, "recommended" = the task's own
# recommended_grasp_assist(variation_id, seed) (topogym.tasks.<task>.common), or an explicit config.
# history_storage="segment": the simulator keeps a complete checkpoint of the episode's first tick only (this tooling runs no
# segments), which is all reset() needs; every other tick keeps a light record.
_COMMON = dict(control_mode="JOINT_ABS", max_physics_steps=None, history_storage="segment", enable_rgb=True, enable_depth=True,
               enable_privileged=True, compute_backend="cuda", render_backend="nyx")
TASKS: dict[str, dict] = {
    "cube_pick_place": dict(
        task_id="cube_pick_place", robot="panda_robotiq", fixture=True,
        text="Pick up the cube, hold it at least 5 cm above the table for at least 0.2 s, place it back at its original "
             "position, open the gripper, withdraw at least 5 cm and let it settle. Merely reaching or closing the "
             "gripper is not completion.",
        instances=[dict(variation_id="base", seed=0)],
        simulator=dict(physics_dt_s=0.025, solver_substeps=40, control_decimation=1),
        grasp_assist=dict(model="contact_weld_v1", targets=[dict(entity="cube", link="box_baselink", radius_m=0.04)])),
    "blanket_flatten": dict(
        task_id="blanket_flatten", robot="aloha",
        text="Unfold and spread the blanket flat on the table. Remove folds, rolls and self-overlaps so the fabric covers "
             "its unfolded footprint without excessive stretching. Release the blanket, withdraw the grippers and let it "
             "settle flat and still on the tabletop.",
        instances=[dict(variation_id="blanket_flatten_easy", seed=0)]),
    "buzz_wire_3d": dict(
        task_id="buzz_wire_3d", robot="panda_robotiq",
        text="Guide the handheld metal loop along the entire wire from its starting end to the finish, keeping the wire "
             "inside the loop opening throughout traversal. Do not let the metal loop touch the wire. Reaching the finish "
             "by taking the loop off the route is not completion. Place the tool on the finish support, release it, "
             "withdraw the gripper and let it settle.",
        instances=[dict(variation_id="buzz_wire_3d_easy", seed=0)], grasp_assist="recommended"),
    "cast_coil": dict(
        task_id="cast_coil", robot="aloha",
        text="Assemble the separated gold and silver Cast Coil pieces into their interlocking, alternating four-layer "
             "target configuration. Align both pieces fully; contact or grasping alone is not completion. Release both "
             "pieces, withdraw the grippers and leave the assembled puzzle stable on the table.",
        instances=[dict(variation_id="cast_coil_easy", seed=0)], grasp_assist="recommended"),
    "cast_keyhole": dict(
        task_id="cast_keyhole", robot="aloha",
        text="Separate the silver keyhole piece from the gold piece. Place the entire silver piece inside the green dashed "
             "goal area and hold it still briefly. Keep the gold piece outside the area on the puzzle/system side. "
             "Holding the target with the gripper is allowed.",
        instances=[dict(variation_id="cast_keyhole_easy", seed=0)], grasp_assist="recommended"),
    "fiber_bundling": dict(
        task_id="fiber_bundling", robot="panda_robotiq",
        text="Manipulate the thick sheath with the robot gripper to pass every fine fiber through the fixed copper ring, "
             "tip first and in tip-to-root material order, until all roots and the front sheath have passed and cleared "
             "the ring. The rear terminal stays anchored and must not pass through the ring. Any gripper contact with a "
             "fine fiber ends the task in failure. Avoid sharp bends and collisions; passing only the tips is not "
             "completion. Keep the completed configuration stable.",
        instances=[dict(variation_id="fiber_bundling_medium", seed=0)]),
    "hedgehog_in_cage": dict(
        task_id="hedgehog_in_cage", robot="panda_robotiq",
        text="Extract the spiked hedgehog ball from the cage. Place the whole ball, including every spike, inside the "
             "green dashed goal area and hold it still briefly. Keep all cage components outside the area on the "
             "puzzle/system side. Holding the target with the gripper is allowed.",
        instances=[dict(variation_id="hedgehog_in_cage_easy", seed=0)], grasp_assist="recommended"),
    "horseshoe_ring": dict(
        task_id="horseshoe_ring", robot="aloha",
        text="Free the removable ring from the horseshoes and chains. Place the entire ring inside the green dashed goal "
             "area and hold it still briefly. Keep the horseshoes and chains outside the area on the puzzle/system side. "
             "Holding the target with the gripper is allowed.",
        instances=[dict(variation_id="horseshoe_ring_easy", seed=0)], grasp_assist="recommended"),
    "interlocked_claws": dict(
        task_id="interlocked_claws", robot="aloha",
        text="Separate the brown claw piece from the other claw. Place the entire brown piece inside the green dashed goal "
             "area and hold it still briefly. Keep the other piece outside the area on the puzzle/system side. Holding "
             "the target with the gripper is allowed.",
        instances=[dict(variation_id="interlocked_claws_hard", seed=0)], grasp_assist="recommended"),
    "knot_untying": dict(
        task_id="knot_untying", robot="aloha",
        text="Untie the knot and spread the rope on the table so that nonadjacent rope segments have no crossings or "
             "overlaps when viewed from above. Do not stretch or damage the rope to bypass the knot. Release it, "
             "withdraw the grippers and leave the whole rope still on the tabletop.",
        instances=[dict(variation_id="knot_untying_easy", seed=0)]),
    "lock_picking": dict(
        task_id="lock_picking", robot="panda_robotiq",
        text="Insert the tabbed key through all three rotor plates and END. Keep the finite shaft through all four "
             "bores and the leading tab beyond END; normal wall contact and geometrically valid tilt are allowed. "
             "Respect the tab slots and rotor stops. Holding is allowed; preserve the completed insertion during confirmation.",
        instances=[dict(variation_id="lock_picking_medium", seed=0)],
        # Match the reference policy's handle grasp for all three current tiers.
        # Frozen instances retain their own simulator config, including legacy none.
        grasp_assist=dict(model="contact_weld_v1", stable_time_s=0.05,
            targets=[dict(entity="lock_key", link="key", center_m=(-0.495, 0., 0.), radius_m=0.032)])),
    "orbits": dict(
        task_id="orbits", robot="aloha",
        text="Free the complete cord and wooden handle from the fixed ring-and-post assembly. Place the entire cord and "
             "handle inside the green dashed goal area and hold them still briefly. Keep the rings, posts and other fixed "
             "components outside the area on the puzzle/system side. Holding the target is allowed; placing only the "
             "handle in the area is not completion.",
        instances=[dict(variation_id="orbits_reference85", seed=0)]),
    "rope_threading": dict(
        task_id="rope_threading", robot="aloha",
        text="Thread the rope through this instance's required rings in the specified material order and direction. "
             "Pass fully through each aperture without extra crossings, intersecting ring material, or damaging the rope. "
             "Keep the threaded rope still. The instance-specific success requirements specify the actual rings.",
        instances=[dict(variation_id="rope_threading_medium", seed=0)]),
    "slotted_post_ring": dict(
        task_id="slotted_post_ring", robot="aloha",
        text="Free the removable metal ring from the slotted post and cord assembly. Place the entire ring inside the "
             "green dashed goal area and hold it still briefly. Keep the post, cord, beads, discs and other puzzle "
             "components outside the area on the puzzle/system side. Holding the target with the gripper is allowed.",
        instances=[dict(variation_id="slotted_post_ring_hard", seed=0)]),
}
for _name, _t in TASKS.items():
    _t.setdefault("simulator", {}); _t.setdefault("grasp_assist", None); _t.setdefault("fixture", False)
    _t.update(simulator_name="topogym", image="topogym")


def simulator_config(task: str, eval_index: int | None = None, *, variation_id: str | None = None,
                     seed: int | None = None, task_parameters: dict | None = None) -> dict:
    """The full SimulatorConfig of eval index `eval_index` of `task`, as instance.json stores it."""
    spec = TASKS[task]
    if variation_id is not None or seed is not None:
        if variation_id is None or seed is None or eval_index is not None:
            raise ValueError("supply variation_id AND seed, or eval_index, exclusively")
        inst = dict(variation_id=variation_id, seed=seed)
    else:
        if eval_index is None or not 0 <= eval_index < len(spec["instances"]):
            raise ValueError(f"{task} has eval indices 0..{len(spec['instances']) - 1}")
        inst = spec["instances"][eval_index]
    from topogym.config.registry import variation_registration
    if spec["fixture"]:
        _register_cube()
    resolved = variation_registration(spec["task_id"], inst["variation_id"], inst["seed"])
    cfg = {**dict(task_id=spec["task_id"], robot_id=spec["robot"], variation_id=inst["variation_id"], seed=int(inst["seed"])),
           **_COMMON, **spec["simulator"]}
    assist = spec["grasp_assist"]
    if assist == "recommended":
        from dataclasses import asdict
        from importlib import import_module
        found = import_module(f"topogym.tasks.{spec['task_id']}.common").recommended_grasp_assist(
            resolved["variation_id"], int(inst["seed"]), task_parameters=task_parameters)
        assist = None if found is None else json.loads(json.dumps(asdict(found)))
    if assist:
        cfg["grasp_assist"] = assist
    if task_parameters:
        cfg["task_parameters"] = task_parameters
    from topogym.simulator.config import SimulatorConfig
    from topogym.utils.io import to_jsonable
    return to_jsonable(SimulatorConfig(**cfg))  # validate and freeze defaults before construction


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- small geometry helpers (numpy, wxyz)
def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = [float(v) for v in q]
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2; w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2; w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2; w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2; w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([w, x, y, z]); q = q / np.linalg.norm(q)
    return -q if q[0] < 0 else q


def rot_angle(Ra, Rb) -> float:
    c = (np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])   # OpenGL camera axes (x right, y up, z back) -> OpenCV (x right, y down, z forward)


def _r(a, nd: int = 7) -> list:
    """A matrix / vector as nested lists of floats rounded to `nd` decimals (JSON-ready)."""
    return np.round(np.asarray(a, dtype=np.float64), nd).tolist()


def _T(pos, quat_wxyz) -> np.ndarray:
    T = np.eye(4); T[:3, :3] = quat_to_mat(quat_wxyz); T[:3, 3] = np.asarray(pos, dtype=np.float64).reshape(3)
    return T


def _pose7(T) -> list:
    return [float(v) for v in np.r_[np.asarray(T)[:3, 3], mat_to_quat(np.asarray(T)[:3, :3])]]


def _np(x) -> np.ndarray:
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


# --------------------------------------------------------------------------- the infrastructure family: a cube
# Not one of the benchmark's 13 families: the example task that exercises the whole pipeline with a short solution
# (robot_coding_bench's robosuite example plays the same role). Registered in-process by Session.
def _cube_classes():
    from copy import deepcopy
    from dataclasses import replace
    from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec

    class CubeTransferTask(TaskDefinition):
        task_id = "cube_transfer"
        model_revision = "cube_transfer_v1"
        defaults = {"stable_duration_s": .5, "size_m": .04, "mass_kg": .05,
                    "start_xy": [-.10, -.10], "target_xy": [-.10, .10], "jitter_m": .005}

        def declare(self, asset_dir, table_height_m):
            self.table_z = table_height_m
            self.start = np.array([*self.config["start_xy"], table_height_m + self.config["size_m"] / 2])
            self.start[:2] += self.rng.uniform(-self.config["jitter_m"], self.config["jitter_m"], 2)
            self.target = np.array([*self.config["target_xy"], self.start[2]])
            self.lifted = self.transported = False
            self.peak_clearance = self.airborne_distance = 0.
            self.held_time_s = 0.
            self.held_once = False
            self._held_anchor = None
            side = self.config["size_m"]
            return TaskSpec((EntitySpec("cube", "box", None, position_m=tuple(self.start),
                material={"rho": self.config["mass_kg"] / side ** 3, "friction": 1.},
                morph_options={"size": (side, side, side)},
                surface={"color": (.85, .25, .12), "roughness": .6}),
                EntitySpec("target_marker", "box", None,
                    position_m=(self.target[0], self.target[1], table_height_m + .0005), fixed=True,
                    morph_options={"size": (.06, .06, .001), "collision": False},
                    surface={"color": (.18, .65, .30), "roughness": .8})))

        def evaluate_state(self, state):
            from scipy.spatial.transform import Rotation
            body = state["bodies"]["cube"]
            position = np.asarray(body["position_m"])
            q = np.asarray(body["quaternion_wxyz"])
            rotation = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
            half_z = np.abs(rotation[2]).sum() * self.config["size_m"] / 2        # a rotated cube's lowest corner
            clearance = float(position[2] - half_z - self.table_z)
            arm = state["articulations"]["robot"]
            hand = arm["links"]["hand"]
            hand_q = np.asarray(hand["quaternion_wxyz"])
            tcp = np.asarray(hand["position_m"]) + Rotation.from_quat(hand_q[[1, 2, 3, 0]]).apply([0, 0, .1029])
            fingers = [float(np.asarray(arm["joints"][name]["position"])[0]) for name in ("finger_joint1", "finger_joint2")]
            opened = max(abs(x) for x in fingers) < .08
            withdrawn = np.linalg.norm(tcp - position) >= .05
            speed = float(np.linalg.norm(body["linear_velocity_m_s"]))
            angular_speed = float(np.linalg.norm(body["angular_velocity_rad_s"]))
            error = float(np.linalg.norm(position[:2] - self.target[:2]))
            reached = (self.lifted and self.transported and opened and withdrawn and error <= .02
                       and abs(clearance) <= .003 and speed <= .01 and angular_speed <= .1)
            failure = "cube_fell" if position[2] < self.table_z - .05 else None
            metrics = dict(clearance_m=clearance, target_error_m=error, linear_speed_m_s=speed,
                           angular_speed_rad_s=angular_speed, gripper_open=opened, withdrawn=bool(withdrawn),
                           lifted=self.lifted, transported=self.transported,
                           peak_clearance_m=self.peak_clearance, airborne_distance_m=self.airborne_distance,
                           cube_position_m=position.tolist(), tcp_position_m=tcp.tolist(), fingers=fingers,
                           held_once=self.held_once, held_time_s=self.held_time_s,
                           relative_position_m=Rotation.from_quat(hand_q[[1, 2, 3, 0]]).inv().apply(position - tcp).tolist())
            return bool(reached), failure, metrics

        def update(self, state, physics_dt_s):
            _, _, metrics = self.evaluate_state(state)
            clearance = metrics["clearance_m"]
            relative = np.asarray(metrics["relative_position_m"])
            candidate = clearance >= .05 and not metrics["gripper_open"] and np.linalg.norm(relative) <= .07
            if candidate:
                if self._held_anchor is None or np.linalg.norm(relative - self._held_anchor) > .01:
                    self._held_anchor = relative.copy()
                    self.held_time_s = 0.
                else:
                    self.held_time_s += physics_dt_s
            else:
                self._held_anchor = None
                self.held_time_s = 0.
            held = self.held_time_s + 1e-12 >= .2
            self.held_once |= held
            self.peak_clearance = max(self.peak_clearance, clearance)
            self.lifted |= held
            if held:
                distance = float(np.linalg.norm(np.asarray(metrics["cube_position_m"])[:2] - self.start[:2]))
                self.airborne_distance = max(self.airborne_distance, distance)
                self.transported |= distance >= .15
            return super().update(state, physics_dt_s)

        def get_state(self):
            state = super().get_state()
            state["transfer"] = dict(lifted=self.lifted, transported=self.transported,
                                     peak_clearance=self.peak_clearance, airborne_distance=self.airborne_distance,
                                     held_time_s=self.held_time_s, held_once=self.held_once,
                                     _held_anchor=deepcopy(self._held_anchor))
            return state

        def set_state(self, state):
            super().set_state(state)
            for key, value in state["transfer"].items():
                setattr(self, key, deepcopy(value))

        def observe(self):
            return dict(cube_initial_position_m=self.start.tolist(), target_position_m=self.target.tolist(),
                        cube_size_m=self.config["size_m"], table_height_m=self.table_z)

    class CubePickPlaceTask(CubeTransferTask):
        """In place: lift the cube 5 cm for 0.2 s, put it back where it started, open, withdraw, settle."""
        task_id = "cube_pick_place"
        model_revision = "cube_pick_place_v1"

        def declare(self, asset_dir, table_height_m):
            spec = super().declare(asset_dir, table_height_m)
            self.target = self.start.copy()
            entities = tuple(replace(e, position_m=(*self.start[:2], table_height_m + .0005))
                             if e.name == "target_marker" else e for e in spec.entities)
            return replace(spec, entities=entities)

        def evaluate_state(self, state):
            _, failure, metrics = super().evaluate_state(state)
            reached = (self.lifted and self.held_once and metrics["gripper_open"] and metrics["withdrawn"]
                       and metrics["target_error_m"] <= .02 and abs(metrics["clearance_m"]) <= .003
                       and metrics["linear_speed_m_s"] <= .01 and metrics["angular_speed_rad_s"] <= .1)
            return bool(reached), failure, metrics

    return CubePickPlaceTask


CubePickPlaceTask = None      # resolved on first registration (needs topogym, which only the simulator images have)


def _register_cube() -> None:
    global CubePickPlaceTask
    from topogym.config import registry, variation_records
    from topogym.config.registry import TaskRegistration
    if "cube_pick_place" in registry._TASKS:
        return
    if CubePickPlaceTask is None:
        CubePickPlaceTask = _cube_classes()
    implementation = f"{Path(__file__).stem}:CubePickPlaceTask"
    sys.modules.setdefault(Path(__file__).stem, sys.modules[__name__])
    registry._TASKS["cube_pick_place"] = TaskRegistration("cube_pick_place", implementation, "rigid", "panda_robotiq")
    variation_records.RECORDS = (*variation_records.RECORDS, dict(task_id="cube_pick_place", variation_id="base", aliases=[],
        status="integrated", implementation=implementation, family_id="test", difficulty=None,
        model_revision="cube_pick_place_v1", reason=None, validation="test_only", pool="test"))


# --------------------------------------------------------------------------- the robot: layout, gripper widths, FK / IK
class _Robot:
    """Action layout, measured state and stateless kinematics of the TopoGym robot (Genesis FK on a fixed qpos template).
    Every group ("arm" for the Panda, "left" / "right" for ALOHA) is one arm: its arm joints then its gripper width."""

    def __init__(self, robot, timing):
        from topogym.robot.grasp_geometry import read_grasp_geometry
        self.robot, self.entity, self.timing = robot, robot.entity, timing
        self.groups = {g.name: g for g in robot.description.groups}
        self.arms = list(self.groups)
        self.template = _np(self.entity.get_qpos()).reshape(-1).astype(np.float64).copy()
        self.joint = {j.name: j for j in self.entity.joints if len(j.qs_idx_local) == 1}
        self.layout, self.arm_slice, self.grip_index, self.limits = [], {}, {}, []
        for g in self.groups.values():
            first = len(self.layout)
            self.layout += list(g.arm_joints); self.limits += [list(map(float, l)) for l in g.arm_limits_rad]
            self.arm_slice[g.name] = slice(first, len(self.layout))
            self.grip_index[g.name] = len(self.layout)
            self.layout.append(f"{g.name}_gripper"); self.limits.append(None)
        self.arm_joints = [n for g in self.groups.values() for n in g.arm_joints]
        self.tcp_frames = {name: f"{name}_tcp" for name in self.groups}
        self.hand_T_tcp = {name: _T(g.tcp_position_in_hand_m, g.tcp_orientation_in_hand_wxyz) for name, g in self.groups.items()}
        self.surfaces = {}
        home_fk = self._fk_full(self.template)
        for name, g in self.groups.items():
            geometry = read_grasp_geometry(robot, name)
            self.surfaces[name] = [(link, (np.c_[v, np.ones(len(v))] @ np.linalg.inv(home_fk[link]).T)[:, :3])
                                   for link, (v, _) in zip(g.grasp.finger_links, geometry["surfaces"])]
        # gripper opening width <-> native actuator coordinate: the nominal pad gap along the native travel (FK)
        self.width_table = {}
        self._grip_hold = {}             # arm -> (width, native) of the current gripper target (see command())
        for name, g in self.groups.items():
            cmds = np.linspace(g.grasp.open_position, g.grasp.closed_position, 33)
            widths = np.minimum.accumulate(np.array([self._nominal_opening(g, c) for c in cmds]))
            keep = np.r_[True, np.diff(widths) < -1e-7]
            self.width_table[name] = (widths[keep][::-1].copy(), cmds[keep][::-1].copy())    # increasing widths
            lo, hi = float(self.width_table[name][0][0]), float(self.width_table[name][0][-1])
            self.limits[self.grip_index[name]] = [round(max(0.0, lo), 6), round(hi, 6)]
        # limits as float32 values: actions are float32 rows, and a row at a limit must not read as beyond it. The model
        # (topogym/robot/joint_position.py validate_action) checks the EXACT limits and raises beyond them, so where
        # float32 rounds a limit outward (e.g. float32(3.14158) = 3.141580104827881) take the next float32 inside it
        # (fix 2026-09-30: a row at a limit, and every clipped row, raised "Joint target outside model limits").
        def inside(lo, hi):
            a, b = np.float32(lo), np.float32(hi)
            if float(a) < lo:
                a = np.nextafter(a, np.float32(np.inf))
            if float(b) > hi:
                b = np.nextafter(b, np.float32(-np.inf))
            return [float(a), float(b)]
        self.limits = [inside(*l) for l in self.limits]
        self.lo = np.array([l[0] for l in self.limits]); self.hi = np.array([l[1] for l in self.limits])
        # tool-frame axes: approach = hand origin -> TCP; closing = between the two finger pads (both in the TCP frame)
        self.axes = {}
        for name, g in self.groups.items():
            a = np.asarray(g.tcp_position_in_hand_m, dtype=np.float64)
            a = np.linalg.inv(self.hand_T_tcp[name][:3, :3]) @ (a / np.linalg.norm(a)) if np.linalg.norm(a) > 1e-9 else np.array([0, 0, 1.0])
            tcp_T = home_fk[g.hand_link] @ self.hand_T_tcp[name]
            pads = [(np.c_[s, np.ones(len(s))] @ home_fk[link].T)[:, :3].mean(axis=0) for link, s in self.surfaces[name]]
            c = np.linalg.inv(tcp_T[:3, :3]) @ (pads[1] - pads[0]); c = c - c.dot(a) * a
            self.axes[name] = (a / np.linalg.norm(a), c / np.linalg.norm(c))
        # kinematic links: every link whose pose does not depend on the fingers (q = the arm joints)
        moved = self._fk_full(self._with_fingers(self.template, {n: g.grasp.closed_position for n, g in self.groups.items()}))
        still = self._fk_full(self._with_fingers(self.template, {n: g.grasp.open_position for n, g in self.groups.items()}))
        self.links = [l.name for l in self.entity.links if np.allclose(moved[l.name], still[l.name], atol=1e-7)]
        self.links += list(self.tcp_frames.values())

    # -- gripper widths
    def _with_fingers(self, q_full, commands: dict) -> np.ndarray:
        q = np.asarray(q_full, dtype=np.float64).copy()
        for name, cmd in commands.items():
            for fj in self.groups[name].finger_joints:
                q[self.joint[fj].qs_idx_local[0]] = cmd
            if self.robot.description.robot_id == "panda_robotiq":
                # nominal parallel-pad pose of the Robotiq four-bar linkage: the passive joints follow the driver
                for side in ("left", "right"):
                    for suffix, sign in (("spring_link_joint", 1), ("follower_joint", -1), ("coupler_joint", -1)):
                        j = self.joint.get(f"r85_{side}_{suffix}")
                        if j is not None:
                            q[j.qs_idx_local[0]] = sign * cmd
        return q

    @staticmethod
    def _gap(a, b) -> float:
        d = b.mean(axis=0) - a.mean(axis=0); n = np.linalg.norm(d)
        if n < 1e-10:
            return 0.0
        d /= n
        return max(0.0, float((b @ d).min() - (a @ d).max()))

    def _nominal_opening(self, g, cmd) -> float:
        fk = self._fk_full(self._with_fingers(self.template, {g.name: cmd}))
        s = [(np.c_[v, np.ones(len(v))] @ fk[link].T)[:, :3] for link, v in self.surfaces[g.name]]
        return self._gap(*s)

    def width_to_native(self, arm, width) -> float:
        w, c = self.width_table[arm]
        return float(np.interp(float(width), w, c))

    def native_to_width(self, arm, native) -> float:
        w, c = self.width_table[arm]
        order = np.argsort(c)
        return float(np.interp(float(native), c[order], w[order]))

    # -- actions
    @property
    def action_dim(self) -> int:
        return len(self.layout)

    def clip(self, row) -> np.ndarray:
        return np.clip(np.asarray(row, dtype=np.float64), self.lo, self.hi)

    def command(self, row) -> dict:
        row = np.asarray(row, dtype=np.float64)
        out = {}
        for name, g in self.groups.items():
            width = float(row[self.grip_index[name]])
            last = self._grip_hold.get(name)
            # A row that keeps the gripper at the width read from its current native target keeps that native exactly. The
            # width table cannot represent every native value (it drops the closed-end plateau of the pad gap), and the grasp
            # manager reads a drop of the commanded closing fraction by more than its deadband as an opening intent: without
            # this, the first step after a closed initial target (interlocked_claws' pre-weld) un-closes the gripper.
            native = last[1] if last is not None and abs(width - last[0]) <= 1e-7 else self.width_to_native(name, width)
            self._grip_hold[name] = (width, native)
            out[name] = {"joint_position_rad": row[self.arm_slice[name]].tolist(), g.gripper_field: native}
        return self.robot.validate_action(out)

    def targets(self) -> np.ndarray:
        t = self.robot.capture_state().targets
        row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            row[self.arm_slice[name]] = t[name]["joint_position_rad"]
            native = float(t[name][g.gripper_field])
            row[self.grip_index[name]] = self.native_to_width(name, native)
            self._grip_hold[name] = (float(row[self.grip_index[name]]), native)
        return row

    # -- measured state
    def measured_full(self) -> np.ndarray:
        return _np(self.entity.get_qpos()).reshape(-1).astype(np.float64)

    def arm_q(self) -> np.ndarray:
        q = self.measured_full()
        return np.array([q[self.joint[n].qs_idx_local[0]] for n in self.arm_joints])

    def opening(self, arm) -> float:
        from topogym.robot.grasp_geometry import read_grasp_geometry
        a, b = [v for v, _ in read_grasp_geometry(self.robot, arm)["surfaces"]]
        return self._gap(a, b)

    def positions(self) -> np.ndarray:
        q = self.measured_full(); row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            row[self.arm_slice[name]] = [q[self.joint[n].qs_idx_local[0]] for n in g.arm_joints]
            row[self.grip_index[name]] = self.opening(name)
        return row

    def velocities(self) -> np.ndarray:
        v = _np(self.entity.get_dofs_velocity()).reshape(-1).astype(np.float64); q = self.measured_full()
        row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            row[self.arm_slice[name]] = [v[self.joint[n].dofs_idx_local[0]] for n in g.arm_joints]
            fj = self.joint[g.actuated_fingers[0]]; nq = q[fj.qs_idx_local[0]]
            slope = (self.native_to_width(name, nq + 1e-4) - self.native_to_width(name, nq - 1e-4)) / 2e-4
            row[self.grip_index[name]] = slope * v[fj.dofs_idx_local[0]]
        return row

    def efforts(self) -> np.ndarray:
        try:
            f = _np(self.entity.get_dofs_control_force()).reshape(-1).astype(np.float64)
        except Exception:  # noqa: BLE001 — a PD estimate when the solver does not expose the applied drive force
            f = None
        obs = self.robot.observe() if f is None else None
        row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            if f is not None:
                row[self.arm_slice[name]] = [f[self.joint[n].dofs_idx_local[0]] for n in g.arm_joints]
                row[self.grip_index[name]] = sum(f[self.joint[n].dofs_idx_local[0]] for n in g.actuated_fingers)
            else:
                m = obs[name]; n = len(g.arm_joints)
                e = np.asarray(g.kp[:n]) * (m["joint_position_target_rad"] - m["joint_position_rad"]) - np.asarray(g.kv[:n]) * m["joint_velocity_rad_s"]
                row[self.arm_slice[name]] = np.clip(e, -np.asarray(g.force[:n]), g.force[:n])
        return row

    def tcp(self, arm) -> tuple[np.ndarray, np.ndarray]:
        m = self.robot.observe()[arm]
        return np.asarray(m["tcp_position_world_m"], dtype=np.float64), np.asarray(m["tcp_orientation_wxyz"], dtype=np.float64)

    # -- kinematics (stateless: a fixed qpos template, never the simulator's state)
    def _fk_full(self, q_full) -> dict:
        from topogym.solvers.genesis_kinematics import GenesisFKSolver
        res = GenesisFKSolver(self.entity).solve(np.asarray(q_full, dtype=np.float64))
        P = np.asarray(res["position_world_m"]).reshape(-1, 3); Q = np.asarray(res["orientation_wxyz"]).reshape(-1, 4)
        out = {l.name: _T(P[l.idx_local], Q[l.idx_local]) for l in self.entity.links}
        for name, g in self.groups.items():
            out[self.tcp_frames[name]] = out[g.hand_link] @ self.hand_T_tcp[name]
        return out

    def q_full(self, q_arm) -> np.ndarray:
        q = self.template.copy()
        for n, v in zip(self.arm_joints, np.asarray(q_arm, dtype=np.float64).reshape(-1)):
            q[self.joint[n].qs_idx_local[0]] = v
        return q

    def fk(self, q_arm, links) -> dict:
        T = self._fk_full(self.q_full(q_arm))
        return {l: _pose7(T[l]) for l in links}

    def ik(self, targets: dict, seed, tol_p: float, tol_r: float, iters: int) -> tuple[np.ndarray, dict]:
        """Bounded least squares over the arm joints of the targeted arms (the other arms keep their seed)."""
        from scipy.optimize import least_squares
        from scipy.spatial.transform import Rotation
        seed = np.asarray(seed, dtype=np.float64).reshape(-1)
        bounds = np.array([self.limits[self.layout.index(n)] for n in self.arm_joints])
        frame_arm = {v: k for k, v in self.tcp_frames.items()}
        moving = [self.arm_joints.index(n) for f in targets for n in self.groups[frame_arm[f]].arm_joints]
        TT = {f: _T(p[:3], p[3:7]) for f, p in targets.items()}
        best = np.clip(seed, bounds[:, 0], bounds[:, 1])

        def residual(x):
            q = best.copy(); q[moving] = x
            got = self._fk_full(self.q_full(q))
            return np.concatenate([np.r_[got[f][:3, 3] - T[:3, 3], Rotation.from_matrix(T[:3, :3].T @ got[f][:3, :3]).as_rotvec()]
                                   for f, T in TT.items()])

        def solve(start):
            r = least_squares(residual, start, bounds=(bounds[moving, 0], bounds[moving, 1]), max_nfev=int(iters),
                              diff_step=1e-4, xtol=1e-10, ftol=1e-10, gtol=1e-10)
            e = residual(r.x).reshape(-1, 6)
            return r.x, {f: (float(np.linalg.norm(x[:3])), float(np.linalg.norm(x[3:]))) for f, x in zip(TT, e)}

        x, err = solve(best[moving])
        if any(e[0] > tol_p or e[1] > tol_r for e in err.values()):          # a local minimum: retry from the reset pose
            home = np.clip(np.array([self.template[self.joint[n].qs_idx_local[0]] for n in self.arm_joints]), bounds[:, 0], bounds[:, 1])
            x2, err2 = solve(home[moving])
            if sum(e[0] + e[1] for e in err2.values()) < sum(e[0] + e[1] for e in err.values()):
                x, err = x2, err2
        best[moving] = x
        return best, err


# --------------------------------------------------------------------------- canonical state hash
def _plain(v):
    from collections.abc import Mapping
    from dataclasses import asdict, is_dataclass
    if is_dataclass(v):
        return _plain(asdict(v))
    if isinstance(v, Mapping):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    if isinstance(v, np.ndarray):
        return _plain(v.tolist())
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, float):
        r = round(v, 12)                      # SI measurements at 12 decimals: last-bit reduction noise removed
        return 0.0 if r == 0 else r
    if isinstance(v, Path):
        return str(v)
    return v


class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, eval_index: int | None = None,
                 variation_id: str | None = None, seed: int | None = None, task_parameters: dict | None = None,
                 strict: bool = False, max_steps: int | None = None, backend: str = DEFAULT_BACKEND):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        if backend != "cuda":
            raise ValueError("TopoGym's physics runs on CUDA only")
        self.task, self.spec = task, dict(TASKS[task])
        inst = None
        if instance is not None:
            if any(x is not None for x in (eval_index, variation_id, seed, task_parameters)):
                raise ValueError("frozen instance cannot be combined with scene overrides")
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            eval_index = inst["eval_index"]
            cfg = dict(inst["simulator"])       # the frozen configuration: the task directory's own copy
            cfg["task_parameters"] = dict(cfg.get("task_parameters", {}))
            dependency = cfg["task_parameters"].get("initial_state_path")
            if dependency and not Path(dependency).is_absolute():
                cfg["task_parameters"]["initial_state_path"] = str(Path(instance).resolve().parent / dependency)
        else:
            cfg = simulator_config(task, eval_index, variation_id=variation_id, seed=seed, task_parameters=task_parameters)
        self.eval_index, self.max_steps, self.backend = eval_index, int(max_steps or MAX_STEPS), backend
        self.config = cfg
        if self.spec["fixture"]:
            _register_cube()
        from topogym.simulator.config import SimulatorConfig
        from topogym.simulator.env import Env
        t0 = time.time()
        _log(f"building {cfg['task_id']} / {cfg['variation_id']} (seed {cfg['seed']}, eval index {self.eval_index}) ...")
        self.env = Env(SimulatorConfig(**cfg))
        self.env.reset(seed=int(cfg["seed"]))
        if not self.spec["fixture"]:
            # The family catalog is only a short catalog label. Public goals
            # come from the selected instance, for both Session and limited SPEC.
            self.spec["text"] = self.env._task.public_instruction()
        self.robot = _Robot(self.env._robot, self.env.timing_spec)
        self.control_hz = 1.0 / float(self.env.timing_spec["control_dt_s"])
        self.physics_substeps = int(self.env.config.control_decimation)
        self.S0 = dict(self.env._info()["state_ref"])
        self._recording: list[np.ndarray] | None = None
        self._video: dict | None = None
        self.episode_done = False
        self.episode_end: str | None = None
        self.n_steps = 0
        self._resets = 0
        self._total_steps = 0
        self._reward = 0.0
        _slog("session_start", task=task, eval_index=self.eval_index)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self.n_steps))
        # Every episode -- live or replayed, in this process or a fresh one -- starts from a restore of the frozen state.
        self._restore()
        self.instance_sha = self.state_sha()
        expected = inst.get("state_sha") if inst else None
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            msg = f"instance state sha {self.instance_sha} != expected {expected}"
            if self.instance_matches:
                _log(f"WARNING: {msg}, but every object/joint pose matches within tolerance")
            else:
                if strict:
                    raise RuntimeError(msg + " and poses differ (asset / simulator drift?)")
                _log("WARNING:", msg, "and poses differ")
        _log(f"instance ready in {time.time() - t0:.0f}s; state_sha={self.instance_sha}; max_steps={self.max_steps}")

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2, joint_tol: float = 2e-3) -> bool:
        try:
            objs = self.objects()
            for name, ref in (inst.get("objects") or {}).items():
                cur = objs.get(name)
                if cur is None:
                    return False
                if np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                if "orientation_wxyz" not in cur or "orientation_wxyz" not in ref:   # particles / FEM: centroid only
                    continue
                q0, q1 = np.asarray(cur["orientation_wxyz"]), np.asarray(ref["orientation_wxyz"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            ref_q = inst.get("reset_joint_targets")
            if ref_q is not None and np.max(np.abs(self.joint_positions() - np.asarray(ref_q))) > joint_tol:
                return False
            return bool(inst.get("objects"))
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    # ---- state helpers
    def state_sha(self) -> str:
        """Hash of the measured state (world, robot, targets, task) with SI values rounded to 12 decimals and contacts
        in a canonical order; episode / branch identities excluded."""
        rec = _plain(self.env.tick_record())
        for k in ("episode_id", "branch_id", "state_id", "parent_state_id"):
            rec["state"].pop(k, None)
        contacts = rec.get("world", {}).get("contacts", {})
        if contacts and isinstance(contacts.get("link_a"), list):
            n = len(contacts["link_a"])
            if all(isinstance(v, list) and len(v) == n for v in contacts.values()):
                rows = [{k: v[i] for k, v in contacts.items()} for i in range(n)]
                rec["world"]["contacts"] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
        blob = json.dumps(rec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state (a restore of the first recorded tick; controller targets back to the
        reset pose)."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self.n_steps)
        self._resets += 1
        self._total_steps += self.n_steps
        self._restore()

    def _restore(self) -> None:
        self._recording = None
        self.episode_done = False
        self.episode_end = None
        self.n_steps = 0
        self._reward = 0.0
        self.env.privileged.rewind_to(self.S0)
        self._targets = self.robot.targets()

    @property
    def action_dim(self) -> int:
        return self.robot.action_dim

    @property
    def action_layout(self) -> list[str]:
        return list(self.robot.layout)

    def step(self, action) -> bool:
        """Apply one low-level action (ACTION_LAYOUT: per arm its joint targets, then its gripper width) for one control
        step. Out-of-limit values are clipped to the joint / gripper limits. Returns True once max_steps control steps
        have run (a runaway guard, not a budget); further steps raise. After the task's own episode end (success or a
        failure predicate) steps are still recorded but no longer move the scene."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != self.action_dim:
            raise ValueError(f"action must have {self.action_dim} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.episode_done:
            raise PrimitiveError(f"{self.max_steps} control steps reached (runaway guard); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.copy())
        target = self.robot.clip(a.astype(np.float64))
        if self.episode_end is None:
            _, reward, terminated, truncated, info = self.env.step(self.robot.command(target))
            self._reward = float(reward)
            if terminated or truncated:
                self.episode_end = "success" if info["task_success"] else (info.get("termination_reason") or "task_failed")
        self._targets = target
        self.n_steps += 1
        if self._video is not None and self.n_steps % self._video["every"] == 0:
            self._video_add()
        if self.n_steps >= self.max_steps:
            self.episode_done = True
        return self.episode_done

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current joint targets (what the robot does when a primitive is idle)."""
        return self._targets.copy()

    def success(self) -> bool:
        return bool(self.env.is_solved())

    def status(self) -> dict[str, Any]:
        return {"success": self.success(), "progress": round(self._reward, 4), "sim_steps": int(self.n_steps),
                "resets": self._resets, "state_sha": self.state_sha(), "episode_end": self.episode_end}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, self.action_dim), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=self.success())
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, topogym_task=self.config["task_id"],
                 variation_id=self.config["variation_id"], eval_index=-1 if self.eval_index is None else self.eval_index,
                 scene_seed=int(self.config["seed"]), instance_sha=self.instance_sha,
                 action_dim=self.action_dim, action_layout=np.array(self.action_layout), meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay after reset(): what the verifier does, twice, in its own process."""
        self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            if self.step(a):
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- rendering
    @property
    def VIDEO_CAMERAS(self) -> tuple[str, ...]:
        return tuple(self.env.sensor_frame().rgb)

    def render_frame(self, camera: str | None = None, size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 from one camera (Nyx; see VIDEO_CAMERAS); `size=(w, h)` resizes. Rendering does not
        touch the physics state."""
        frame = self.env.sensor_frame()
        img = np.ascontiguousarray(np.asarray(frame.rgb[camera or self.VIDEO_CAMERAS[0]])[..., :3]).astype(np.uint8)
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            from PIL import Image
            img = np.asarray(Image.fromarray(img).resize(tuple(size), Image.BILINEAR))
        return img

    def render_grid(self, cameras: tuple[str, ...] | None = None, cols: int = 3, size: tuple[int, int] = (424, 240)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in (cameras or self.VIDEO_CAMERAS)]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 2, fps: int = 15,
                     cameras: tuple[str, ...] | None = None, cols: int = 3, size: tuple[int, int] = (424, 240)) -> dict[str, Any]:
        """Replay `actions` from the frozen instance (reset() first) and write an MP4 of `cameras` tiled, one frame every
        `every` control steps (+ `<path>.last.png`). Returns the final status plus n_frames and the video path."""
        import imageio.v2 as imageio
        self.reset()
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1) as w:
            def grab() -> np.ndarray:
                nonlocal n
                f = self.render_grid(cameras, cols=cols, size=size); w.append_data(f); n += 1
                return f
            grab()
            for i, a in enumerate(np.asarray(actions, dtype=np.float32)):
                if self.step(a):
                    break
                if (i + 1) % every == 0:
                    grab()
            last = grab()
        imageio.imwrite(str(path.with_suffix(".last.png")), last)
        return {**self.status(), "n_frames": n, "video": str(path)}

    def start_video(self, path: str | Path, fps: int = 15, every: int | None = None) -> None:
        import imageio.v2 as imageio
        every = every or max(1, int(round(self.control_hz / fps)))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        w = imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1)
        self._video = {"path": str(path), "every": every, "writer": w, "last": None}
        self._video_add()

    def _video_add(self) -> None:
        f = self._video_frame(); self._video["writer"].append_data(f); self._video["last"] = f

    def _video_frame(self) -> np.ndarray:
        """The first camera at full size, the others stacked at the right, scaled to share its height."""
        from PIL import Image
        cams = self.VIDEO_CAMERAS
        main = self.render_frame(cams[0])
        if len(cams) == 1:
            return main
        H = main.shape[0]; h = H // (len(cams) - 1)
        side = []
        for c in cams[1:]:
            img = self.render_frame(c)
            side.append(np.asarray(Image.fromarray(img).resize((max(1, int(img.shape[1] * h / img.shape[0])), h), Image.BILINEAR)))
        wmax = max(s.shape[1] for s in side)
        side = [np.pad(s, ((0, 0), (0, wmax - s.shape[1]), (0, 0))) for s in side]
        col = np.concatenate(side, axis=0)
        col = np.pad(col, ((0, H - col.shape[0]), (0, 0), (0, 0)))
        out = np.ascontiguousarray(np.concatenate([main, col], axis=1))
        return out[: out.shape[0] // 2 * 2, : out.shape[1] // 2 * 2]      # even sizes for yuv420p

    def stop_video(self) -> str | None:
        if self._video is None:
            return None
        import imageio.v2 as imageio
        v, self._video = self._video, None
        v["writer"].close()
        imageio.imwrite(str(Path(v["path"]).with_suffix(".last.png")), v["last"])
        return v["path"]

    # ---- objects / robot state
    SCENE_PREFIXES = ("lab_", "table_frame")   # the shared lab scene around the table (walls, cabinets, table frame)

    def _entities(self) -> dict:
        """The task's own entities: every world entity except the robot, the table and the lab scene props."""
        return {n: e for n, e in self.env._world.entities.items()
                if n not in ("robot", "table", "floor", "ground", "plane") and not n.startswith(self.SCENE_PREFIXES)}

    def objects(self) -> dict[str, dict]:
        """Task objects by name -> position (world), orientation_wxyz, euler_xyz, bounds (AABB [[min],[max]]), size,
        velocity, fixed. Deformable objects (PBD cloth / rope particles, FEM meshes) have no orientation: they report
        material "particle" or "fem", the centroid of their particles / vertices as position, their AABB and mean
        velocity, and n_points."""
        from scipy.spatial.transform import Rotation
        ws = self.env._world.read_state()
        out = {}
        for n, ent in self._entities().items():
            if n in ws.get("fem", {}) or n in ws.get("particles", {}):
                kind = "fem" if n in ws.get("fem", {}) else "particle"
                d = ws[kind if kind == "fem" else "particles"][n]
                p = np.asarray(d.get("position_m") if isinstance(d, dict) and "position_m" in d else
                               (d.get("vertices_m") if isinstance(d, dict) else d), dtype=np.float64).reshape(-1, 3)
                v = np.asarray(d.get("velocity_m_s", np.zeros_like(p)) if isinstance(d, dict) else np.zeros_like(p), dtype=np.float64).reshape(-1, 3)
                out[n] = {"material": kind, "position": [round(float(x), 5) for x in p.mean(axis=0)],
                          "bounds": [[round(float(x), 5) for x in p.min(axis=0)], [round(float(x), 5) for x in p.max(axis=0)]],
                          "velocity": [round(float(x), 5) for x in (v.mean(axis=0) if len(v) else np.zeros(3))], "n_points": int(len(p))}
                continue
            b = ws.get("bodies", {}).get(n)
            if b is None:
                continue
            q = np.asarray(b["quaternion_wxyz"], dtype=np.float64)
            bounds = self.object_bounds(n)
            out[n] = {"position": [round(float(x), 5) for x in b["position_m"]], "orientation_wxyz": [round(float(x), 6) for x in q],
                      "euler_xyz": [round(float(x), 5) for x in Rotation.from_quat(q[[1, 2, 3, 0]]).as_euler("xyz")],
                      "bounds": [[round(float(x), 5) for x in row] for row in bounds],
                      "size": [round(float(x), 5) for x in bounds[1] - bounds[0]],
                      "velocity": [round(float(x), 5) for x in b["linear_velocity_m_s"]],
                      "fixed": bool(getattr(getattr(ent, "morph", None), "fixed", False))}
        return out

    def object_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of an object in the world frame; for a deformable object, (centroid, identity)."""
        o = self.objects().get(name)
        if o is None:
            raise KeyError(f"unknown object {name!r}; known: {list(self._entities())}")
        return np.asarray(o["position"], dtype=np.float64), np.asarray(o.get("orientation_wxyz", [1.0, 0.0, 0.0, 0.0]), dtype=np.float64)

    def object_bounds(self, name: str) -> np.ndarray:
        """Axis-aligned bounding box [[xmin,ymin,zmin],[xmax,ymax,zmax]] of an object (world frame)."""
        ent = self._entities().get(name)
        if ent is None:
            raise KeyError(f"unknown object {name!r}; known: {list(self._entities())}")
        if hasattr(ent, "get_AABB"):
            try:
                return _np(ent.get_AABB()).reshape(-1, 2, 3)[0].astype(np.float64)
            except Exception:  # noqa: BLE001 — a visual-only entity (a marker without collision geometry): its visual AABB
                return _np(ent.get_vAABB()).reshape(-1, 2, 3)[0].astype(np.float64)
        o = self.objects()[name]
        return np.asarray(o["bounds"], dtype=np.float64)

    def joint_positions(self) -> np.ndarray:
        """Current joint positions in action layout (gripper entries = measured opening width in metres)."""
        return self.robot.positions()

    def ee_pose(self, arm: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of the tool frame (TCP) of `arm` in the world frame."""
        return self.robot.tcp(arm)

    def gripper_width(self, arm: str) -> float:
        return float(self.robot.opening(arm))

    def joint_velocities(self) -> np.ndarray:
        """Measured joint velocities in action layout (rad/s; gripper entries = opening rate, m/s)."""
        return self.robot.velocities()

    def joint_efforts(self) -> np.ndarray:
        """The force each PD drive applied, in action layout (N m; gripper entries: the actuated finger drive)."""
        return self.robot.efforts()

    def object_in_hand(self, arm: str) -> str | None:
        """The object passive grasp assistance attached to `arm`'s gripper, or None (always None without assistance)."""
        g = self.env._world.read_state().get("grasp") or {}
        b = ((g.get("hands") or {}).get(arm) or {}).get("binding")
        return str(b["target"][0]) if b else None

    # ---- inverse kinematics on the robot's own model
    def ik(self, arm: str, pos, quat_wxyz) -> tuple[np.ndarray, float, float]:
        """Solve the arm joint targets of `arm` that put its TCP at world pose (pos, quat_wxyz), starting from the
        measured joints. Returns (q_arm, position_error_m, rotation_error_rad) of the (limit-clamped) solution; no
        exception on failure."""
        if arm not in self.robot.groups:
            raise ValueError(f"arm must be one of {self.robot.arms}")
        frame = self.robot.tcp_frames[arm]
        q, err = self.robot.ik({frame: np.r_[np.asarray(pos, dtype=np.float64), np.asarray(quat_wxyz, dtype=np.float64)]},
                               self.robot.arm_q(), 1e-4, 1e-3, 200)
        sl = [self.robot.arm_joints.index(n) for n in self.robot.groups[arm].arm_joints]
        return q[sl], err[frame][0], err[frame][1]

    # ---- cameras, depth, robot spec, stateless kinematics (the same data the limited service's /spec and /kinematics
    # serve). Nothing here steps physics or changes the simulator state.
    def _camera_contract(self) -> dict:
        if getattr(self, "_cams", None) is None:
            from topogym.config.scene import load_scene_config
            from topogym.sensors.camera_info import camera_contract
            self._cams = camera_contract(load_scene_config(self.env.config).env.cameras)
        return self._cams

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """Per camera, for the current state: intrinsic_cv (3x3), extrinsic_cv (3x4 world -> camera, OpenCV axes: x right, y
        down, z forward), cam2world_gl (4x4 camera -> world, OpenGL axes: x right, y up, z backward), image_size [W, H],
        mount ({"type": "static", ...} or {"type": "link", "parent_link", "link_T_cam_cv"}: world_T_cam = link pose @
        link_T_cam_cv), moves, depth_range_m. A pixel (u, v) sees u = fx X/Z + cx, v = fy Y/Z + cy."""
        frame = self.env.sensor_frame(); contract = self._camera_contract()
        out = {}
        for name in (cameras or self.VIDEO_CAMERAS):
            meta, c = frame.camera_metadata[name], contract[name]
            T_wc = np.asarray(meta["T_world_from_camera_cv"], dtype=np.float64)
            if c["motion"] == "fixed":
                mount = {"type": "static", "extrinsic_cv": _r(np.asarray(c["T_camera_cv_from_world"])[:3]),
                         "cam2world_gl": _r(np.asarray(c["T_world_from_camera_cv"]) @ GL2CV)}
            else:
                mount = {"type": "link", "parent_link": c["parent_link"], "link_T_cam_cv": _r(c["T_parent_link_from_camera_cv"])}
            out[name] = {"intrinsic_cv": _r(meta["K_px"]), "extrinsic_cv": _r(np.asarray(meta["T_camera_cv_from_world"])[:3]),
                         "cam2world_gl": _r(T_wc @ GL2CV), "image_size": [int(v) for v in meta["resolution_px"]],
                         "mount": mount, "moves": c["motion"] != "fixed",
                         "depth_range_m": [float(c["clipping_m"][0]), min(float(c["clipping_m"][1]), 65.535)]}
        return out

    def render_depth(self, camera: str | None = None, size: tuple[int, int] | None = None) -> np.ndarray:
        """z-depth (H, W) float32 in metres (distance along the camera's optical axis; Genesis geometry at the Nyx camera
        rig), pixel-aligned with render_frame(camera); 0 = no reading. `size=(w, h)` resizes (nearest neighbour).
        Rendering does not touch the physics state."""
        d = np.array(self.env.sensor_frame(depth=True).depth[camera or self.VIDEO_CAMERAS[0]], dtype=np.float32)
        if d.ndim == 3:
            d = d[..., 0]
        d[~np.isfinite(d) | (d <= 0) | (d > 65.535)] = 0.0
        if size is not None and (d.shape[1], d.shape[0]) != tuple(size):
            from PIL import Image
            d = np.asarray(Image.fromarray(d).resize(tuple(size), Image.NEAREST), dtype=np.float32)
        return d

    def kinematics_spec(self) -> dict:
        """What kinematics() answers: joint layout, frames, conventions (the limited service's spec["kinematics"])."""
        tips = list(self.robot.tcp_frames.values())
        return {"endpoint": "/kinematics", "stateless": True, "joint_names": list(self.robot.arm_joints), "frame": "world",
                "quaternion_order": "wxyz", "links": list(self.robot.links), "tcp_frames": tips, "ee_frames": tips, "ik_targets": tips,
                "ik": {"solver": "bounded least squares over the robot's Genesis forward kinematics, started from the seed "
                                 "(default: the reset pose)", "joints": "the arm joints of each arm whose TCP is a target; the other "
                                 "arms keep their seed", "collision": "none", "tol_pos_m": 0.002, "tol_rot_rad": 0.02, "max_iters": 200},
                "note": "q = the arm joints of every arm (the order of joint_names, as proprio); the finger joints do not move "
                        "any listed frame"}

    def kinematics(self, req: dict) -> dict:
        """Stateless FK / IK on the robot's kinematic model (never the simulator's state): the limited service's /kinematics.
        {"op": "fk", "q": arm joints, "links": [...]} -> {"ok", "op", "frame", "poses": {link: [x,y,z, qw,qx,qy,qz]}} (world);
        {"op": "ik", "targets": {"<arm>_tcp": [x,y,z, qw,qx,qy,qz], ...}, "seed": q, "tol_pos_m", "tol_rot_rad",
        "max_iters"} -> {"ok", "op", "frame", "q": q | None, "error": {frame: {"pos_m", "rot_rad"}}}."""
        spec = self.kinematics_spec(); n = len(self.robot.arm_joints)
        if req.get("base_pose") is not None:
            raise ValueError("base_pose: this robot's base is fixed (kinematics frame = world)")
        op = req.get("op")
        if op == "fk":
            q = np.asarray(req.get("q"), dtype=np.float64).reshape(-1)
            links = req.get("links") or spec["links"]
            if q.size != n or not np.all(np.isfinite(q)) or any(l not in spec["links"] for l in links):
                raise ValueError(f"fk needs q ({n} finite values) and links from {spec['links']}")
            return {"ok": True, "op": "fk", "frame": "world", "poses": self.robot.fk(q, links)}
        if op != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        tg = req.get("targets") or {}
        if not tg or any(f not in spec["ik_targets"] for f in tg):
            raise ValueError(f"ik targets must be frames from {spec['ik_targets']}")
        ik = spec["ik"]
        tol_p, tol_r = float(req.get("tol_pos_m", ik["tol_pos_m"])), float(req.get("tol_rot_rad", ik["tol_rot_rad"]))
        it = int(req.get("max_iters", ik["max_iters"]))
        home = np.array([self.robot.template[self.robot.joint[j].qs_idx_local[0]] for j in self.robot.arm_joints])
        seed = np.asarray(req["seed"], dtype=np.float64).reshape(-1) if req.get("seed") is not None else home
        if seed.size != n or not np.all(np.isfinite(seed)):
            raise ValueError(f"seed must be {n} finite values")
        targets = {f: np.asarray(p, dtype=np.float64).reshape(7) for f, p in tg.items()}
        for f in targets:
            targets[f][3:] /= max(1e-12, np.linalg.norm(targets[f][3:]))
        q, err = self.robot.ik(targets, seed, tol_p, tol_r, it)
        ok = all(e[0] <= tol_p and e[1] <= tol_r for e in err.values())
        return {"ok": bool(ok), "op": "ik", "frame": "world", "q": [float(v) for v in q],
                "error": {f: {"pos_m": e[0], "rot_rad": e[1]} for f, e in err.items()}}

    def grasp_rules(self) -> str:
        """The gripper's grasping rule in words (the `command` text of robot_spec()["grippers"])."""
        ga = self.env.config.grasp_assist
        if ga.model == "none":
            return ("physical grasping only (no assisted grasping): closing on an object squeezes it with the gripper's "
                    "PD force; friction holds it")
        parts = ", ".join(sorted({t.entity for t in ga.targets}))
        held = ("; the grippers start closed on their parts and may acquire after the same bilateral-contact confirmation without another close command"
                if getattr(ga, "initial_intent", "open") == "close" else "")
        return (f"assisted grasping ({ga.model}): a gripper whose command moves towards closed takes hold of a graspable "
                f"part ({parts}) once both fingers touch the same part inside its grasp region, the tool frame within "
                f"{ga.max_tcp_distance_m * 100:g} cm of it and the penetration at most {ga.max_penetration_m * 1000:g} mm, for "
                f"{ga.stable_time_s:g} s; the part then follows the gripper rigidly. Any command that opens the gripper (by more "
                f"than {ga.intent_deadband * 100:g} % of its travel) lets it go. A hold that breaks (the fingers open more than "
                f"{ga.max_finger_opening_fraction * 100:g} %, or the part drifts {ga.max_translation_error_m * 100:g} cm / "
                f"{ga.max_rotation_error_rad:g} rad from its held pose) is lost, and the gripper must open before it can take "
                "hold again. Two grippers never hold the same part; other objects are grasped physically (friction)" + held)

    def robot_spec(self) -> dict:
        """The robot's spec sheet (the limited service's spec["robot_spec"]): joints in order with their limits, grippers,
        controller and gains, tool frames. Only the robot: nothing about the scene."""
        r = self.robot; joints, gains, grip, tcp = [], {}, {}, {}
        home_fk = r._fk_full(r.template)
        for name, g in r.groups.items():
            for i, jn in enumerate(list(g.arm_joints) + list(g.actuated_fingers)):
                finger = i >= len(g.arm_joints)
                prismatic = finger and g.gripper_field.endswith("_m")
                lim = g.gripper_limits if finger else g.arm_limits_rad[i]
                joints.append({"name": jn, "type": "prismatic" if prismatic else "revolute", "unit": "m" if prismatic else "rad",
                               "position_limits": [round(float(lim[0]), 6), round(float(lim[1]), 6)], "velocity_limit": None,
                               "effort_limit": round(float(g.force[i]), 6), "group": f"gripper_{name}" if finger else f"arm_{name}",
                               "note": "velocity_limit: the simulation enforces none (the PD tracking sets the speed); effort_limit: "
                                       "the drive force clamp" + ("; the gripper action is the opening width, converted to this "
                                                                  "coordinate" if finger else "")})
                gains[jn] = {"stiffness": float(g.kp[i]), "damping": float(g.kv[i])}
            lo, hi = r.limits[r.grip_index[name]]
            grip[name] = {"joints": list(g.finger_joints), "opening_m": [lo, hi], "tcp_frame": r.tcp_frames[name],
                          "command": f"joint_position entry {name}_gripper (index {r.grip_index[name]}) and the ee_pose {name}_gripper "
                                     f"entry: the target opening width in metres, {lo:g} = closed .. {hi:g} = open (the nominal gap "
                                     f"between the finger pads), converted to the gripper's native drive coordinate; it switches at "
                                     f"the row (no interpolation). Grasping: {self.grasp_rules()}"}
            a, c = r.axes[name]
            tcp[r.tcp_frames[name]] = {"parent_link": g.hand_link, "link_T_frame": _r(r.hand_T_tcp[name]),
                                       "definition": f"the {name} gripper's tool frame (TCP): a fixed point near the closed finger pads; "
                                                     f"approach axis (hand -> fingertips) = local {_r(a, 3)}, finger-closing axis = local "
                                                     f"{_r(c, 3)}. The ee_pose action, the proprio tcp pose and the IK use this frame."}
        base = r.entity.links[0].name
        return {"name": self.env._robot.description.robot_id,
                "description": {"panda_robotiq": "a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base",
                                "aloha": "two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base"}.get(
                                    self.env._robot.description.robot_id, "fixed-base manipulator") + " (TopoGym, Genesis 1.2.1)",
                "base": {"type": "fixed", "pose": _pose7(home_fk[base]),
                         "note": f"world pose of the kinematic root link {base} (x y z qw qx qy qz)"},
                "joints": joints, "grippers": grip,
                "controller": {"type": "joint position PD per DoF (Genesis), gravity included in the simulation",
                               "control_hz": self.control_hz, "physics_hz": 1.0 / float(self.env.timing_spec["physics_dt_s"]),
                               "gains": gains,
                               "note": f"targets are applied at the {self.control_hz:g} Hz control rate and held over "
                                       f"{self.physics_substeps} physics step(s)"},
                "tcp": tcp}

    # ---- primitives for the agent: deliberately thin wrappers of the low-level action (joint targets, gripper width, IK
    # moves). Grasping, placing and every other skill are the agent's to build.
    def primitives(self) -> dict[str, Callable]:
        s = self
        r = s.robot

        def get_object_pose(name: str):
            """-> (position(3), quaternion wxyz(4)) of `name` in the world frame."""
            return s.object_pose(name)

        def get_object_bounds(name: str):
            """-> AABB [[xmin,ymin,zmin],[xmax,ymax,zmax]] of `name` (world frame)."""
            return s.object_bounds(name)

        def get_ee_pose(arm: str):
            """-> (position(3), quaternion wxyz(4)) of the TCP of `arm` (see s.robot.arms)."""
            return s.ee_pose(arm)

        def get_joint_targets():
            """-> the currently commanded joint targets (action layout)."""
            return s.hold_action()

        def hold(steps: int = 10):
            """Keep the current targets for `steps` control steps (lets objects settle)."""
            for _ in range(int(steps)):
                s.step(s.hold_action())

        def set_joint_targets(targets, steps: int = 1):
            """Command a full action row of joint targets for `steps` control steps (no interpolation)."""
            for _ in range(int(steps)):
                s.step(targets)

        def set_gripper(arm: str, width: float, steps: int = 15):
            """Command the gripper opening width of `arm` (m; see robot_spec()["grippers"]) and hold for `steps` steps."""
            t = s.hold_action(); t[r.grip_index[arm]] = float(np.clip(width, *r.limits[r.grip_index[arm]]))
            for _ in range(int(steps)):
                s.step(t)

        def open_gripper(arm: str, steps: int = 15):
            """Open the gripper of `arm` fully."""
            set_gripper(arm, r.limits[r.grip_index[arm]][1], steps)

        def close_gripper(arm: str, steps: int = 15):
            """Close the gripper of `arm` (width target 0; the PD controller squeezes whatever is between the fingers)."""
            set_gripper(arm, 0.0, steps)

        def move_joints(arm: str, q_arm, *, max_dq: float = 0.04, steps: int | None = None, settle: int = 0):
            """Interpolate the arm joint targets of `arm` linearly from the current targets to `q_arm` (rad), at most
            `max_dq` rad per control step (or exactly `steps` steps), then hold `settle` steps."""
            cur = s.hold_action(); goal = cur.copy(); goal[r.arm_slice[arm]] = np.asarray(q_arm, dtype=np.float64)
            n = int(steps) if steps else max(4, int(math.ceil(float(np.max(np.abs(goal - cur))) / max_dq)))
            for i in range(1, n + 1):
                s.step(cur + (goal - cur) * (i / n))
            for _ in range(int(settle)):
                s.step(goal)

        def move_ee(arm: str, pos, quat_wxyz=None, *, max_dq: float = 0.04, steps: int | None = None, settle: int = 0,
                    tol: float = 0.008, linear: int = 0):
            """Move the TCP of `arm` to world pose (pos, quat_wxyz; default: keep the current orientation). IK then joint
            interpolation (`max_dq` rad/step). `linear=k` splits the motion into k straight-line Cartesian waypoints (use for
            descents/lifts). Raises PrimitiveError if the IK residual exceeds `tol` metres. Returns the final TCP error (m)."""
            p1 = np.asarray(pos, dtype=np.float64)
            p0, q0 = s.ee_pose(arm)
            quat = np.asarray(quat_wxyz if quat_wxyz is not None else q0, dtype=np.float64)
            k = max(1, int(linear))
            for j in range(1, k + 1):
                pj = p0 + (p1 - p0) * (j / k) if k > 1 else p1
                q7, ep, er = s.ik(arm, pj, quat)
                if ep > tol or er > 0.2:
                    raise PrimitiveError(f"IK for {arm} arm at {np.round(pj, 3).tolist()} failed: residual {ep * 1000:.1f} mm / {math.degrees(er):.1f} deg")
                move_joints(arm, q7, max_dq=max_dq, steps=(steps if k == 1 else None), settle=(settle if j == k else 0))
            pe, _ = s.ee_pose(arm)
            return float(np.linalg.norm(pe - p1))

        def gripper_quat(closing_yaw: float, approach=(0.0, 0.0, -1.0), arm: str | None = None) -> np.ndarray:
            """TCP orientation (wxyz) whose fingers close along the horizontal direction `closing_yaw` (rad, world x->y)
            and whose approach axis (hand -> fingertips) points along `approach` (default straight down), for `arm`
            (default: the first arm). The TCP frame's own approach / closing axes are in robot_spec()["tcp"]."""
            a_l, c_l = r.axes[arm or r.arms[0]]
            c = np.array([math.cos(closing_yaw), math.sin(closing_yaw), 0.0])
            a = np.asarray(approach, dtype=np.float64); a = a - a.dot(c) * c
            if np.linalg.norm(a) < 1e-6:
                raise ValueError("approach direction must not be parallel to the closing direction")
            a = a / np.linalg.norm(a)
            W = np.stack([a, c, np.cross(a, c)], axis=1); L = np.stack([a_l, c_l, np.cross(a_l, c_l)], axis=1)
            return mat_to_quat(W @ L.T)

        def top_down_quat(closing_yaw: float, tilt: float = 0.0, arm: str | None = None) -> np.ndarray:
            """gripper_quat() for a vertical approach; `tilt` (rad, >0) leans the approach direction towards +x."""
            return gripper_quat(closing_yaw, np.array([math.sin(tilt), 0.0, -math.cos(tilt)]), arm)

        def object_in_hand(arm: str | None = None):
            """-> the object assisted grasping attached to `arm`'s gripper (default: the first arm), or None."""
            return s.object_in_hand(arm or r.arms[0])

        return {"get_object_pose": get_object_pose, "get_object_bounds": get_object_bounds, "get_ee_pose": get_ee_pose,
                "get_joint_targets": get_joint_targets, "hold": hold, "set_joint_targets": set_joint_targets,
                "set_gripper": set_gripper, "open_gripper": open_gripper, "close_gripper": close_gripper, "move_joints": move_joints,
                "move_ee": move_ee, "ik": s.ik, "top_down_quat": top_down_quat, "gripper_quat": gripper_quat,
                "object_in_hand": object_in_hand}

    def table_z(self) -> float | None:
        z = getattr(self.env._task, "table_z", None) or getattr(self.env._task, "table_height_m", None) or None
        if z is None:
            try:
                from topogym.config.scene import load_scene_config
                z = float(load_scene_config(self.env.config).env.table.height_m)
            except Exception:  # noqa: BLE001
                z = None
        return None if z is None else float(z)

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives in scope (also: session, objects, TASK, np, math, PrimitiveError)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "math": math, "session": self, "objects": self.objects,
                             "TASK": dict(self.spec, table_z=self.table_z(), arms=list(self.robot.arms)),
                             "PrimitiveError": PrimitiveError, **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"ok": False, "error": repr(exc)[:300]}

    def close(self) -> None:
        try:
            self.env.close()
        except Exception as exc:  # noqa: BLE001
            _log("close:", repr(exc)[:120])


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: (d[k].item() if d[k].shape == () else d[k]) for k in d.files}


def _source() -> dict:
    p = Path(os.environ.get("TOPOGYM_SOURCE", "/opt/topogym/SOURCE.json"))
    return json.loads(p.read_text()) if p.is_file() else {}


def success_enabled(task) -> bool:
    """Whether the image judges success for this task: the task's goal_complete switch. Since Jianwen's 2ec4b8d6 it is
    True by default in every family (an enable switch, not the episode's success state; topogym/tasks/base.py)."""
    return bool(getattr(task, "goal_complete", True))


def grasp_words(s: "Session") -> str:
    """The instance's grasping, from its frozen SimulatorConfig: his recommended / explicit assistance or physical."""
    ga = s.config.get("grasp_assist") or {}
    if ga.get("model", "none") == "none":
        return "physical grasping"
    source = s.spec["grasp_assist"]
    source = "his recommended" if source == "recommended" else "his explicit" if isinstance(source, dict) else "frozen"
    return f"{source} {ga['model']} grasp assistance"


def success_rule(s: "Session") -> str:
    """Provenance of this instance's success rule, recorded in instance.json and task.toml: his default success with the
    terminal revision, plus his qualification record where one matches this instance. Since 2ec4b8d6 a record is owner
    metadata only (terminal_metadata()["qualification"]); it never enables or disables success."""
    task = s.env._task
    if not success_enabled(task):
        return "not evaluable (goal_complete False)"
    meta = task.terminal_metadata()
    out = f"his default success (goal_complete True; terminal revision {meta.get('revision', task.terminal_revision)})"
    record = meta.get("qualification")
    if record:
        out += (f"; his qualification record for this variation matches, as metadata only (record profile: "
                f"{record.get('profile', 'not recorded')}{'; ' + record['scope'] if record.get('scope') else ''}); this "
                f"instance runs CUDA {float(s.config['physics_dt_s']) * 1000:g} ms ticks x {int(s.config['solver_substeps'])} "
                f"substeps with joint-position actions and {grasp_words(s)}, which the record does not cover")
    return out


def cmd_make_instance(a) -> None:
    params = json.loads(Path(a.task_parameters).read_text()) if a.task_parameters else None
    s = Session(a.task, eval_index=a.eval_index, variation_id=a.variation, seed=a.scene_seed, task_parameters=params)
    import genesis as gs
    from topogym.tasks.goal_description import TASK_IDS, describe_goal
    out = {"task": a.task, "topogym_task": s.config["task_id"], "variation_id": s.config["variation_id"], "seed": s.config["seed"],
           "eval_index": s.eval_index, "text": s.spec["text"], "simulator": s.config, "state_sha": s.instance_sha,
           "action_dim": s.action_dim, "action_layout": s.action_layout, "control_hz": s.control_hz, "backend": s.backend,
           "reset_joint_targets": [round(float(x), 6) for x in s.joint_positions()], "objects": s.objects(),
           "genesis_version": gs.__version__, "topogym_source": _source(),
           "resolved_variation_id": s.env._variation["variation_id"],
           "scene_variation": s.env._scene_variation,
           "effective_task_parameters": s.env._task.config,
           "public_goal": describe_goal(s.env._task) if s.env._task.task_id in TASK_IDS else None,
           "evaluable_for_task_success": success_enabled(s.env._task), "success_rule": success_rule(s)}
    # Package numeric Blanket state alongside each instance, including its hashes.
    dependency = s.config.get("task_parameters", {}).get("initial_state_path")
    if dependency:
        import shutil
        source = Path(dependency).resolve().parent
        target = Path(a.out).resolve().parent / "instance_assets" / "initial_state"
        if source != target:
            shutil.copytree(source, target, dirs_exist_ok=True)
        relative = "instance_assets/initial_state/" + Path(dependency).name
        out["simulator"]["task_parameters"]["initial_state_path"] = relative
        out["effective_task_parameters"]["initial_state_path"] = relative
    from topogym.utils.io import to_jsonable
    out = to_jsonable(out)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha}), flush=True)
    s.close()


def cmd_run_oracle(a) -> None:
    """Run the reference code on the frozen instance in this fresh process and record every low-level action."""
    s = Session(a.task, instance=a.instance, strict=True)
    code = open(a.code).read()
    t0 = time.time()
    s.record_start()
    r = s.exec_code(code)
    acts = s.record_stop()
    st = s.status()
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "exec": r, "wall_s": round(time.time() - t0, 1)})
    print(json.dumps({"traj": a.out, "n_actions": int(len(acts)), "exec": r, **st, "wall_s": round(time.time() - t0, 1)}), flush=True)
    s.close()


def cmd_replay(a) -> None:
    traj = _load_traj(a.traj)
    if str(traj.get("task")) != a.task:
        print(json.dumps({"error": f"trajectory task {traj.get('task')} != {a.task}"}), flush=True); sys.exit(2)
    s = Session(a.task, instance=a.instance, strict=a.strict)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    t0 = time.time()
    outs = [s.replay(acts) for _ in range(a.repeat)]
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "wall_s": round(time.time() - t0, 1)}
    if a.video:
        s.start_video(a.video, fps=a.fps); s.replay(acts); s.stop_video(); out["video"] = a.video
    print(json.dumps(out), flush=True)
    s.close()


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance)
    cams = tuple(a.cameras.split(",")) if a.cameras else None
    print(json.dumps(s.render_video(_load_traj(a.traj)["actions"], a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols)), flush=True)
    s.close()


def cmd_describe(a) -> None:
    """What the task generator writes into instruction.md / README.md: cameras, robot, kinematics, the success predicate's
    source, the table height; one JSON line."""
    import inspect
    s = Session(a.task, instance=a.instance)
    t = s.env._task
    from topogym.tasks.goal_description import TASK_IDS, describe_goal
    public_goal = describe_goal(t) if t.task_id in TASK_IDS else None
    try:
        predicate = inspect.getsource(type(t).evaluate_state)
    except (OSError, TypeError):
        predicate = None
    t0 = time.time()
    for _ in range(3):
        s.step(s.hold_action())
    sec_per_step = (time.time() - t0) / 3
    s.reset()
    out = {"sec_per_step": round(sec_per_step, 3), "cameras": s.camera_info(), "robot_spec": s.robot_spec(), "kinematics": s.kinematics_spec(), "arms": list(s.robot.arms),
           "action_layout": s.action_layout, "limits": s.robot.limits, "control_hz": s.control_hz, "physics_substeps": s.physics_substeps,
           "table_z": s.table_z(), "objects": s.objects(), "predicate": predicate, "task_class": type(t).__name__,
           "task_module": "rcb_topogym" if type(t).__module__ == "__main__" else type(t).__module__, "stable_duration_s": float(t.config.get("stable_duration_s", 0.5)),
           "grasp_rules": s.grasp_rules(), "grasp_assist": s.config.get("grasp_assist"),
           "public_goal": public_goal}
    print(json.dumps(out), flush=True)
    s.close()


def cmd_selftest(a) -> None:
    """Evidence in 3 fresh processes: make-instance, run-oracle, replay --repeat 2 (replays succeed; hashes reported)."""
    here, out = Path(__file__).resolve(), Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    inst, traj = out / "instance.json", out / "trajectory.npz"

    def run(*args):
        cmd = [sys.executable, str(here), *map(str, args)]
        _log("selftest>", " ".join(cmd[2:]))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=open(out / "selftest.stderr.log", "ab"), text=True)
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {"error": f"no json output (rc={p.returncode})"}

    r0 = run("make-instance", "--task", a.task, "--eval-index", a.eval_index, "--out", inst)
    r1 = run("run-oracle", "--task", a.task, "--instance", inst, "--code", a.code, "--out", traj)
    r2 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--repeat", 2, "--strict")
    ok = bool(r1.get("success")) and bool(r2.get("all_success")) and bool(r2.get("instance_matches"))
    print(json.dumps({"make_instance": r0, "oracle": r1, "replay": r2, "PASS": ok}, indent=1), flush=True)
    sys.exit(0 if ok else 1)


def cmd_smoke(a) -> None:
    """Short real build/action/reset/replay and RGB evidence; no solvability claim."""
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    s = Session(a.task, instance=a.instance, strict=True)
    from topogym.recording.segment import SegmentMedia, save_rgb
    media = None
    try:
        s.record_start()
        save_rgb(out, "initial_rgb", s.env.sensor_frame())
        media = SegmentMedia(out, 0, s.env.sensor_frame())
        for _ in range(3):
            s.step(s.hold_action())
            if not np.isfinite(s.joint_positions()).all():
                raise ValueError("non-finite robot state")
            media.append(s.env.sensor_frame())
        recording = media.finish(); media = None
        actions = s.record_stop()
        s.save_trajectory(actions, str(out / "trajectory.npz"))
        status = s.status()
        if status.get("episode_end") not in (None, "success"):
            raise ValueError(f"short hold ended with {status['episode_end']}")
        result = dict(passed=True, scope="short_build_action_reset_rgb", control_steps=len(actions),
                      instance_matches=s.instance_matches, status=status, replay=s.replay(actions),
                      evaluable_for_task_success=bool(getattr(s.env._task, "goal_complete", False)), recording=recording)
        (out / "smoke.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        if media is not None:
            media.abort()
        s.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--eval-index", type=int)
    q.add_argument("--variation"); q.add_argument("--scene-seed", type=int); q.add_argument("--task-parameters")
    q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=2); q.add_argument("--video", default=None); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--strict", action="store_true", help="fail if the rebuilt frozen scene does not match instance.json (poses within tolerance)"); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=2); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--cameras", default=None); q.add_argument("--cols", type=int, default=3); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("describe"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.set_defaults(fn=cmd_describe)
    q = sub.add_parser("smoke"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_smoke)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="cube_pick_place"); q.add_argument("--eval-index", type=int, default=0)
    q.add_argument("--code", required=True); q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
