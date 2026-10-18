# FROZEN COPY for the reference solution only (solution/, never in the agent image): the task tooling as it was when
# the oracle was written, with its task-level primitives (navigation on a traversability map with the furniture painted
# in, grasp, place_inside, ...). The agent's tooling (environment/rcb_behavior.py) keeps only thin wrappers of the
# low-level action; instance loading and stepping are the same in both, so the trajectory this copy records replays
# with the agent's tooling (the verifier). solve.sh runs it next to the robot config it loads.
"""
rcb_behavior.py — task-local tooling for BEHAVIOR-1K (OmniGibson 3.9.2, the 2026 BEHAVIOR Challenge version):
frozen challenge instance / privileged primitives / action recording / fresh-process deterministic replay.
Same shape as the robosuite example's rcb_traj.py so agents and verifiers share one mental model.

Concepts
--------
instance   : a 2026 BEHAVIOR Challenge task instance (task name + instance id, e.g. picking_up_trash / 301) loaded through
             the official evaluator (omnigibson.eval.evaluator.Evaluator): scene template + task-relevant object states +
             robot start pose, settled for 25 physics steps. The frozen initial state is what Evaluator.reset() yields right
             after load_task_instance(); its sha1 over og.sim.dump_state(serialized=True) is stored in instance.json and
             checked whenever the instance is loaded again (dataset / simulator drift => mismatch).
trajectory : the (T, A) low-level robot actions handed to env.step, one row per control step (30 Hz control, 120 Hz
             physics), A = robot.action_dim = 25 with the primitives controller config (base 3, trunk 4, left arm 7,
             left gripper 2, right arm 7, right gripper 2; see robot.controller_action_idx). Replaying them open-loop from
             the frozen instance in a FRESH process reproduces the final state bit-exactly (measured on CPU PhysX).
             In-process reset() is only approximate (~1e-6): the first replay in a process (no reset needed) is exact,
             later ones drift, so the verifier replays in two fresh processes (the `replay` CLI).
budget     : there is no step budget: the agent's wall clock is the limit. The challenge's timeout termination is lifted to
             MAX_STEPS, which only stops runaway trajectories; the episode still ends the moment the BDDL goal holds.

CLI
---
  python rcb_behavior.py make-instance --task picking_up_trash --instance-id 301 --robot-config r1pro_primitives_eval.yaml --out instance.json
  python rcb_behavior.py run-oracle    --task picking_up_trash --instance instance.json --code oracle.py --out traj.npz
  python rcb_behavior.py replay        --task picking_up_trash --instance instance.json --traj traj.npz [--video replay.mp4] [--strict]
  python rcb_behavior.py selftest      --task picking_up_trash --instance-id 301 --code oracle.py --out-dir /tmp/selftest   # 4 fresh processes

Python (what the agent gets)
----------------------------
  from rcb_behavior import Session
  s = Session("picking_up_trash", instance="/app/instance.json")   # ~3 min: launches Isaac Sim + loads the scene
  s.reset()                          # back to the frozen instance state (approximate in-process; fresh process is exact)
  p = s.primitives()                 # dict of callables: grasp, place_inside, navigate_to_object, move_hand, ... (docstrings!)
  s.objects()                        # task objects: BDDL name -> category, position
  s.record_start(); ...; actions = s.record_stop()   # (T, 25) low-level actions, one row per env step
  s.status()                         # {'success': bool, 'q_score': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
  s.replay(actions)                  # the first replay in a process is exact; the CLI `replay` (fresh process) is the grader's view
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""
from __future__ import annotations

import os
os.environ.setdefault("OMNIGIBSON_HEADLESS", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")  # before torch initialises CUDA

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

# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# It records the agent's whole debugging history, not just the trajectory it hands in (the verifier reports it as
# cost: agent_sessions / agent_resets / agent_sim_steps). Set RCB_SESSION_LOG="" to disable (the verifier does).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
MAX_STEPS = 200_000        # no step budget (the wall clock is); this only stops a runaway trajectory (~1.9 h of sim time)


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- task family registry
TASKS: dict[str, dict] = {
    "picking_up_trash": dict(
        challenge_task="picking_up_trash",
        scene="house_double_floor_lower",
        text="Put the three cans of soda from the living room inside the trash can in the kitchen.",
        cans=["can__of__soda.n.01_1", "can__of__soda.n.01_2", "can__of__soda.n.01_3"],
        trash="ashcan.n.01_1",
        simulator="behavior", robot="r1pro", image="behavior",
    ),
    "putting_shoes_on_rack": dict(
        challenge_task="putting_shoes_on_rack",
        scene="house_double_floor_lower",
        text="Put the two pairs of shoes (two gym shoes, two sandals) on the hall tree in the corridor: every shoe must "
             "touch the hall tree and not the floor, and the two shoes of each pair must be next to each other.",
        gym_shoes=["gym_shoe.n.01_1", "gym_shoe.n.01_2"],
        sandals=["sandal.n.01_1", "sandal.n.01_2"],
        rack="hallstand.n.01_1",
        movable=["gym_shoe.n.01_1", "gym_shoe.n.01_2", "sandal.n.01_1", "sandal.n.01_2"],  # picked up: never base obstacles
        simulator="behavior", robot="r1pro", image="behavior",
    ),
}

TOP_DOWN_XYZW = (1.0, 0.0, 0.0, 0.0)  # end effector pointing straight down (what _sample_grasp_pose returns)

ACTION_LAYOUT = ("robot.action_dim = 25 with r1pro_primitives_eval.yaml: base (3, holonomic base joints x,y,rz as position "
                 "targets in the robot frame), trunk (4), arm_left (7), gripper_left (2), arm_right (7), gripper_right (2); "
                 "all position-mode JointControllers with absolute targets; see robot.controller_action_idx. One row per env "
                 "step (30 Hz control, 120 Hz physics). Quaternions everywhere are XYZW (OmniGibson convention), poses are in "
                 "the world frame.")


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


def _sha_of_text(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:12]


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- warp / Isaac quirks
def _import_warp_early() -> None:
    """Bind the pip `warp` package and its `warp.torch` submodule before Isaac Sim's bundled omni.warp (1.8.2) is started:
    otherwise cuRobo can end up calling a mixed, uninitialised warp (measured: 'NoneType has no attribute cuda_devices')."""
    try:
        import warp  # noqa: F401
        import warp.torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _log("warp pre-import skipped:", repr(exc))


def ensure_warp_runtime() -> None:
    """After the Evaluator is built, the `warp` package may expose Isaac's own warp.context with runtime None; initialise it."""
    try:
        pkg = sys.modules.get("warp")
        for ctx in {id(c): c for c in [getattr(pkg, "context", None), sys.modules.get("warp.context")] if c is not None}.values():
            if getattr(ctx, "runtime", None) is None:
                ctx.init()
                _log("warp runtime initialised for", getattr(ctx, "__file__", "?"))
    except Exception as exc:  # noqa: BLE001
        _log("ensure_warp_runtime failed:", repr(exc))


# --------------------------------------------------------------------------- evaluator wrappers (hydra targets)
try:  # only importable inside the simulator image; the module must still import on a bare host for --help / selftest.
    from omnigibson.envs import EnvironmentWrapper as _EnvWrapper
    from omnigibson.eval.utils.eval_utils import set_sensor_modalities as _set_modalities

    class TinyCamWrapper(_EnvWrapper):
        """Keeps the robot cameras the evaluator expects, but renders 16x16 RGB only (rendering is ~40% of step cost)."""

        def __init__(self, env, size: int | None = None):
            # 16x16 by default (rendering is ~40% of step cost); standard mode raises it with RCB_CAM_SIZE,
            # because there the agent has nothing to work from but these images.
            size = int(os.environ.get("RCB_CAM_SIZE", size or 16))
            super().__init__(env=env)
            robot = env.robots[0]
            for name, sensor in robot.sensors.items():
                if not hasattr(sensor, "image_height") or not hasattr(sensor, "image_width"):
                    continue
                _set_modalities(sensor, {"rgb"})
                sensor.image_height = size
                sensor.image_width = size
                space = sensor.load_observation_space()
                if env.observation_space is not None:
                    env.observation_space.spaces[robot.name].spaces[name] = space
except Exception:  # noqa: BLE001
    TinyCamWrapper = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- session
class _QueuePolicy:
    """LocalPolicy adapter: Evaluator.step() asks policy.forward(obs); we hand it the action Session.step() was given."""

    def __init__(self, robot):
        self.robot, self.next = robot, None

    def act(self, obs):
        a = self.next
        self.next = None
        return a if a is not None else self.robot.q_to_action(self.robot.get_joint_positions())

    def reset(self):
        self.next = None


class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, instance_id: int | None = None,
                 mode: str = "public_test", robot_config: str | Path | None = None, cameras: str = "tiny",
                 strict: bool = False):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task, self.spec = task, TASKS[task]
        _import_warp_early()
        import torch as th
        import omnigibson as og
        from omnigibson.macros import gm
        from omegaconf import OmegaConf
        gm.HEADLESS = True
        from omnigibson.eval.utils.eval_utils import DEFAULT_EVAL_SEED, seed_everything
        from omnigibson.eval.evaluator import Evaluator, resolve_instance_ids
        self.th, self.og = th, og

        inst = None
        if instance is not None:
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            instance_id = int(inst["instance_id"]); mode = inst.get("mode", mode)
            if robot_config is None and inst.get("robot_config"):
                # bare file name: next to the instance file (tests/ copy for the verifier), else next to this module
                cand = [Path(instance).parent / inst["robot_config"], Path(__file__).parent / Path(inst["robot_config"]).name]
                robot_config = next((c for c in cand if c.exists()), cand[0])
        if instance_id is None:
            raise ValueError("need instance=path or instance_id=<challenge instance id>")
        if robot_config is None:
            robot_config = Path(__file__).parent / "r1pro_primitives_eval.yaml"
        self.robot_config_path = Path(robot_config)
        self.robot_config_sha = _sha_of_text(self.robot_config_path.read_text())
        self.instance_id, self.mode, self.cameras = int(instance_id), mode, cameras

        seed = seed_everything(DEFAULT_EVAL_SEED)
        wrapper = "omnigibson.eval.wrappers.DefaultWrapper" if cameras == "default" else f"{__name__}.TinyCamWrapper"
        cfg = OmegaConf.create({
            "env_wrapper": {"_target_": wrapper}, "policy_name": "local",
            "model": {"_target_": "omnigibson.eval.policies.LocalPolicy", "action_dim": None},
            "headless": True, "partial_scene_load": True, "max_steps": None, "write_video": False,
            "mode": mode, "seed": seed, "task": {"name": self.spec["challenge_task"]},
            "robot": OmegaConf.to_container(OmegaConf.load(str(self.robot_config_path)), resolve=True),
        })
        t0 = time.time()
        _log(f"building evaluator for {task} (instance {self.instance_id}, cameras={cameras}); ~3 min ...")
        self.ev = Evaluator(cfg)
        ensure_warp_runtime()
        self.env = self.ev.env
        self.robot = self.env.robots[0]
        self.action_dim = int(self.robot.action_dim)
        self._policy = _QueuePolicy(self.robot)
        self.ev.policy.policy = self._policy
        self._recording: list | None = None
        self.episode_done = False  # set when env.step reports terminated/truncated; primitives stop stepping then
        self._prim = None
        self._grip_cmd = None       # the gripper part of the last action sent (keep_grip)
        self._stepped = False       # anything stepped since the instance was loaded / reset (replay)
        self._names_by_obj: dict[int, str] = {}
        self._resets = 0
        self._total_steps = 0
        self._end_logged = False
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        self.challenge_max_steps = int(getattr(tc.get("timeout"), "_max_steps", 0)) or None
        self._lift_timeout()
        _slog("session_start", task=task, instance_id=self.instance_id)
        import atexit
        atexit.register(self._log_end)
        _log(f"evaluator ready in {time.time() - t0:.0f}s; action_dim={self.action_dim}")

        # load the frozen instance: fresh reset -> instance TRO state + robot pose -> settle -> reset (official recipe)
        self.ev.reset()
        self.ev.load_task_instance(self.instance_id)
        self.ev.reset()
        self._lift_timeout()
        self.S0 = self._flat_state()
        self.instance_sha = self._sha(self.S0)
        expected = inst.get("state_sha") if inst else None
        # exact sha (bit-reproducible on one host), else every task object's pose within tolerance (another host may change
        # the last bits; a wrong dataset / simulator / robot config moves objects by millimetres or more)
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            if self.instance_matches:
                _log(f"WARNING: state sha {self.instance_sha} != {expected} but every object pose matches within tolerance (different host?)")
            else:
                msg = f"instance state sha {self.instance_sha} != expected {expected} and poses differ (dataset/simulator/robot-config drift?)"
                if strict:
                    raise RuntimeError(msg)
                _log("WARNING:", msg)
        _log(f"instance {self.instance_id} loaded; state_sha={self.instance_sha}; max_steps={self.max_steps}")

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2) -> bool:
        try:
            objs = self.objects()
            ref_objs = inst.get("objects") or {}
            for name, ref in ref_objs.items():
                cur = objs.get(name)
                if cur is None or np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                q0, q1 = np.asarray(cur["orientation_xyzw"]), np.asarray(ref["orientation_xyzw"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            return bool(ref_objs)
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    # ---- state helpers
    def _flat_state(self):
        st = self.og.sim.dump_state(serialized=True)
        if isinstance(st, dict):
            st = self.th.cat([self.th.as_tensor(v).flatten() for v in st.values()])
        return self.th.as_tensor(st).detach().cpu().contiguous()

    @staticmethod
    def _sha(t) -> str:
        return hashlib.sha1(t.numpy().tobytes()).hexdigest()[:16]

    def state_sha(self) -> str:
        return self._sha(self._flat_state())

    def _lift_timeout(self) -> None:
        """No step budget: the challenge's timeout termination goes up to the runaway guard MAX_STEPS (the BDDL goal
        still ends the episode the moment it holds)."""
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        if tc.get("timeout") is not None:
            tc["timeout"]._max_steps = MAX_STEPS

    @property
    def max_steps(self) -> int | None:
        tc = getattr(self.env.task, "_termination_conditions", {}) or {}
        return int(getattr(tc.get("timeout"), "_max_steps", 0)) or None

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state. In-process this is approximate (a few 1e-6 differences after
        load_state); a fresh process reproduces the instance exactly, which is what the verifier does."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=int(self.env.episode_steps))
        self._resets += 1
        self._total_steps += int(self.env.episode_steps)
        self._recording = None
        self.episode_done = False
        self._grip_cmd = None
        self._stepped = False
        self._policy.reset()
        self.ev.reset()
        self._lift_timeout()
        self.og.sim.load_state(self.S0.clone(), serialized=True)

    def step(self, action) -> tuple[bool, bool]:
        """Apply one low-level action (robot.action_dim,) for one control step. Returns (terminated, truncated)."""
        a = self.th.as_tensor(np.asarray(action, dtype=np.float32)).flatten()
        if a.numel() != self.action_dim:
            raise ValueError(f"action must have {self.action_dim} entries, got {a.numel()}")
        if self.episode_done:
            raise PrimitiveError("episode is over (success or timeout); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.clone())
        self._stepped = True
        if self._prim is not None:   # what keep_grip() holds the gripper at
            self._grip_cmd = a[self.robot.controller_action_idx[f"gripper_{self._prim.arm}"]].clone()
        self._policy.next = a
        terminated, truncated = self.ev.step()
        if terminated or truncated:
            self.episode_done = True
        return terminated, truncated

    def hold_action(self):
        """The action that holds the current joint targets (what the robot does when a primitive is idle). It is built
        from the MEASURED joint positions: while a gripper holds a wide object, pass it through keep_grip()."""
        return self.robot.q_to_action(self.robot.get_joint_positions())

    def keep_grip(self, action):
        """`action` with the primitives' arm's gripper entries replaced by the last gripper command step() sent.
        Motions built from MEASURED joint positions (hold_action(), every motion helper, upstream settle) otherwise
        re-command the gripper to where its fingers happen to be, and assisted grasping goes by that command: a shoe
        held across its 11.5 cm width keeps the 12.7 cm gripper almost open, so the command drifts to the open limit
        and the shoe is released mid-drive; after a release the fingers sit just below the limit, so the command reads
        "closing" and the gripper grabs the shoe it just let go (then drags it off the seat as the base backs away).
        Only close_gripper() / open_gripper() (and upstream place_on_top) change the gripper command."""
        a = self.th.as_tensor(np.asarray(action, dtype=np.float32)).flatten().clone()
        if self._prim is None or self._grip_cmd is None:
            return a
        a[self.robot.controller_action_idx[f"gripper_{self._prim.arm}"]] = self._grip_cmd.to(a.dtype)
        return a

    def status(self) -> dict[str, Any]:
        out = {"success": bool(self.env.task.success), "sim_steps": int(self.env.episode_steps), "resets": self._resets,
               "state_sha": self.state_sha(), "q_score": None}
        try:
            for m in self.ev.metrics:
                agg = m.aggregate(self.env)
                if isinstance(agg, dict) and "q_score" in agg:
                    out["q_score"] = float(agg["q_score"].get("final", 0.0))
        except Exception as exc:  # noqa: BLE001
            out["q_score_error"] = repr(exc)[:120]
        return out

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = self.th.stack(self._recording).numpy() if self._recording else np.zeros((0, self.action_dim), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=bool(self.env.task.success))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, instance_id=self.instance_id,
                 instance_sha=self.instance_sha, action_dim=self.action_dim, action_layout=ACTION_LAYOUT,
                 robot_config_sha=self.robot_config_sha, meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay from the frozen initial state. In a session that has not stepped since the instance was
        loaded (the CLI `replay`, the verifier) the actions run from the loaded state itself, which reproduces a fresh
        process that ran them right after loading bit-exactly (measured: an oracle's live run and a fresh replay end on
        the same state sha). Otherwise reset() first, which is approximate: an in-process reset leaves PhysX's hidden
        solver/contact state different, and a replay after it drifts (putting_shoes_on_rack: q_score 1.0 live, 0.9)."""
        if self._stepped:
            self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            terminated, truncated = self.step(a)
            if terminated or truncated:
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- video (needs cameras="default" for a watchable resolution)
    def start_video(self, path: str | Path, fps: int = 30) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.ev.start_recording(str(path), rate=fps)

    def stop_video(self) -> None:
        self.ev.stop_recording()

    # ---- objects
    def _scope(self):
        return self.env.task.object_scope

    def get_object(self, name: str):
        ent = self._scope()[name]
        return getattr(ent, "wrapped_obj", ent)

    def objects(self) -> dict[str, dict]:
        """Task-relevant objects by BDDL name -> {category, position, orientation_xyzw}."""
        out = {}
        for name, ent in self._scope().items():
            obj = getattr(ent, "wrapped_obj", ent)
            if obj is None or not hasattr(obj, "get_position_orientation") or name.startswith("agent") or obj is self.robot:
                continue
            try:
                pos, quat = obj.get_position_orientation()
                out[name] = {"category": getattr(obj, "category", "?"), "position": [round(float(x), 4) for x in pos],
                             "orientation_xyzw": [round(float(x), 4) for x in quat]}
            except Exception:  # noqa: BLE001
                continue
        return out

    def _name_of(self, obj) -> str | None:
        for name, ent in self._scope().items():
            if getattr(ent, "wrapped_obj", ent) is obj:
                return name
        return None

    # ---- primitives
    def _primitives_engine(self):
        if self._prim is None:
            from omnigibson.action_primitives.starter_semantic_action_primitives import StarterSemanticActionPrimitives
            from omnigibson.action_primitives.curobo import CuRoboMotionGenerator
            ensure_warp_runtime()
            t0 = time.time()
            env = getattr(self.env, "env", self.env)
            prim = StarterSemanticActionPrimitives(env, self.robot, enable_head_tracking=False,
                                                   task_relevant_objects_only=True, skip_curobo_initilization=True)
            # low-memory cuRobo (fits a 16 GB GPU next to Isaac): batch 1, no CUDA graphs, 128 IK seeds
            prim._motion_generator = CuRoboMotionGenerator(
                self.robot, batch_size=1, use_cuda_graph=False, collision_activation_distance=0.02,
                motion_cfg_kwargs={"num_ik_seeds": 128, "num_trajopt_seeds": 2, "num_graph_seeds": 2})
            try:  # fail faster: the upstream default is 100 planning attempts per motion
                sys.modules[type(prim).__module__].m.MAX_PLANNING_ATTEMPTS = 30
            except Exception as exc:  # noqa: BLE001
                _log("could not lower MAX_PLANNING_ATTEMPTS:", repr(exc)[:80])
            self._prim = prim
            # the gripper starts open: hold it at an explicit open command (as open_gripper() sends) until a primitive
            # closes it, so assisted grasping is not "applying" on whatever brushes the fingers (keep_grip)
            ji = self.robot.gripper_control_idx[prim.arm]
            q = self.robot.get_joint_positions().clone()
            q[ji] = self.robot.joint_upper_limits[ji] + 0.02
            self._grip_cmd = self.th.as_tensor(self.robot.q_to_action(q)).flatten()[
                self.robot.controller_action_idx[f"gripper_{prim.arm}"]].clone()
            _log(f"primitives + cuRobo ready in {time.time() - t0:.0f}s")
        return self._prim

    def _run(self, gen, max_steps: int = 3000, label: str = "", keep_grip: bool = True) -> int:
        """Feed a primitive generator into env.step; returns the number of env steps taken. `keep_grip` holds a grasped
        object's gripper closed (see keep_grip); only a primitive that releases the object itself turns it off."""
        n = 0
        for act in gen:
            if act is None:
                act = self.hold_action()
            if keep_grip:
                act = self.keep_grip(act)
            terminated, truncated = self.step(act)
            n += 1
            if terminated or truncated:
                raise PrimitiveError(f"{label or 'primitive'}: episode ended after {self.env.episode_steps} steps "
                                     f"({'success' if terminated else 'timeout'}); reset() to continue")
            if n >= max_steps:
                raise PrimitiveError(f"{label or 'primitive'}: exceeded {max_steps} env steps")
        return n

    def primitives(self) -> dict[str, Callable]:
        """Privileged primitives (state-based perception allowed, tier=privileged). All poses world-frame, quats XYZW."""
        th, s = self.th, self
        prim = self._primitives_engine()
        from omnigibson.action_primitives.curobo import CuRoboEmbodimentSelection as Emb
        from omnigibson.action_primitives.starter_semantic_action_primitives import StarterSemanticActionPrimitiveSet as P

        def _yaw(quat_xyzw) -> float:
            x, y, z, w = [float(v) for v in quat_xyzw]
            return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

        def get_object_pose(name: str):
            """(position(3), quaternion_xyzw(4)) of a task object in the world frame."""
            pos, quat = s.get_object(name).get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def get_object_bbox(name: str):
            """Axis-aligned bounding box (center(3), extent(3)) of a task object in the world frame."""
            obj = s.get_object(name)
            if hasattr(obj, "aabb_center") and hasattr(obj, "aabb_extent"):
                c, e = obj.aabb_center, obj.aabb_extent
            else:
                lo, hi = obj.aabb
                c, e = (lo + hi) / 2, hi - lo
            return th.as_tensor(c).cpu().numpy().astype(float), th.as_tensor(e).cpu().numpy().astype(float)

        def get_robot_pose():
            """(position(3), quaternion_xyzw(4)) of the robot base in the world frame."""
            pos, quat = s.robot.get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def get_eef_pose(arm: str | None = None):
            """(position(3), quaternion_xyzw(4)) of the end effector (default arm) in the world frame."""
            arm = arm or s.robot.default_arm
            r = s.robot
            if hasattr(r, "get_eef_position") and hasattr(r, "get_eef_orientation"):
                pos, quat = r.get_eef_position(arm), r.get_eef_orientation(arm)
            elif hasattr(r, "get_eef_pose"):
                pos, quat = r.get_eef_pose(arm)
            else:
                pos, quat = r.eef_links[arm].get_position_orientation()
            return pos.cpu().numpy().astype(float), quat.cpu().numpy().astype(float)

        def object_in_hand():
            """BDDL name of the object currently held by the default arm, or None."""
            obj = prim._get_obj_in_hand()
            return s._name_of(obj) if obj is not None else None

        def settle(max_steps: int = 600) -> int:
            """Hold still until the robot has settled. Returns env steps used."""
            return s._run(prim._settle_robot(), max_steps, "settle")

        def _safe_settle(max_steps: int = 300) -> int:
            try:
                return settle(max_steps)
            except PrimitiveError:
                return max_steps

        def hold(n: int = 10) -> int:
            """Hold the current joint targets for n control steps."""
            for _ in range(n):
                s.step(s.keep_grip(s.hold_action()))
            return n

        def open_gripper(max_steps: int = 150) -> int:
            """Open the default arm's gripper and release any assisted-grasped object. Finger targets are commanded slightly
            beyond the upper joint limit: the assisted-grasp release only triggers when the commanded position is not below
            the limit, and float rounding of an exact limit command can keep the object attached forever."""
            idx = s.robot.gripper_control_idx[prim.arm]
            upper = s.robot.joint_upper_limits[idx]
            n = 0
            for k in range(max_steps):
                q = s.robot.get_joint_positions().clone(); q[idx] = upper + 0.02
                s.step(s.robot.q_to_action(q)); n += 1
                if k >= 12 and prim._get_obj_in_hand() is None:
                    break
            if prim._get_obj_in_hand() is not None:
                raise PrimitiveError("open_gripper: object still attached after opening")
            return n

        def close_gripper(max_steps: int = 400) -> int:
            """Close the default arm's gripper (assisted grasping attaches a touched object)."""
            return s._run(prim._execute_grasp(), max_steps, "close_gripper", keep_grip=False)

        def _wrap(a: float) -> float:
            return (a + math.pi) % (2 * math.pi) - math.pi

        def _base_pose():
            pos, quat = s.robot.get_position_orientation()
            return float(pos[0]), float(pos[1]), _yaw(quat)

        def _base_joint_targets(x: float, y: float, yaw: float):
            """World-frame 2D base pose -> values of the virtual base joints (x, y, rz). The joints live in the robot's
            root frame (where the robot was spawned), not the world frame, and the rz joint is unwrapped, so the target is
            expressed as a delta from the current joint values: world delta rotated into the root frame, yaw delta added."""
            wx, wy, wyaw = _base_pose()
            j = s.robot.get_joint_positions()[s.robot.base_control_idx]
            jx, jy, jyaw = float(j[0]), float(j[1]), float(j[2])
            ryaw = _wrap(wyaw - jyaw)  # root frame yaw relative to the world
            c, si = math.cos(ryaw), math.sin(ryaw)
            dx, dy = x - wx, y - wy
            return jx + c * dx + si * dy, jy - si * dx + c * dy, jyaw + _wrap(yaw - wyaw)

        def _drive_to(x: float, y: float, yaw: float | None, tol_pos: float, tol_yaw: float, step: float = 0.03,
                      yaw_step: float = 0.06, max_steps: int = 400, label: str = "drive") -> int:
            """Position-mode base follower: turn toward the goal first (in place), then translate toward (x, y) in the world
            frame at ~step per control step, finally turn to `yaw` if given. The turn-first rule measured best on the
            challenge scene (a pure holonomic slide drove into furniture the traversability map does not know about).
            No obstacle awareness: use it on traversability-map waypoints or short final legs. Stops early when no
            progress is made for 90 steps."""
            n, best, stall = 0, float("inf"), 0
            bidx = s.robot.base_control_idx
            d = err = float("inf")
            turn_sign = 0.0  # fixed once the goal heading is (nearly) opposite: otherwise the wrapped error flips sign every step
            while n < max_steps:
                cx, cy, cyaw = _base_pose()
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy)
                want_yaw = math.atan2(dy, dx) if d > tol_pos else (yaw if yaw is not None else cyaw)
                err = _wrap(want_yaw - cyaw)
                if abs(err) > 2.6:
                    turn_sign = turn_sign or (1.0 if err >= 0 else -1.0)
                    err = turn_sign * abs(err)
                elif abs(err) < 1.5:
                    turn_sign = 0.0
                if d <= tol_pos and (yaw is None or abs(err) <= tol_yaw):
                    return n
                metric = d + 0.3 * abs(err)
                if metric < best - 1e-3:
                    best, stall = metric, 0
                else:
                    stall += 1
                    if stall > 45:
                        raise PrimitiveError(f"{label}: base stopped making progress toward ({x:.2f}, {y:.2f}) "
                                             f"(residual {d:.2f} m, {abs(err):.2f} rad) — obstacle?")
                move = min(step, d) if d > tol_pos and abs(err) < 0.5 else 0.0  # turn first, then translate
                ang = math.atan2(dy, dx) if d > 1e-6 else cyaw
                tx, ty = cx + move * math.cos(ang), cy + move * math.sin(ang)
                tyaw = cyaw + max(-yaw_step, min(yaw_step, err))
                q = s.robot.get_joint_positions().clone()
                q[bidx] = th.tensor(_base_joint_targets(tx, ty, tyaw), dtype=q.dtype)
                s.step(s.keep_grip(s.robot.q_to_action(q)))
                n += 1
            raise PrimitiveError(f"{label}: base did not reach ({x:.2f}, {y:.2f}) within {max_steps} steps "
                                 f"(residual {d:.2f} m, {abs(err):.2f} rad)")

        _obstacle_cache: list = []

        def _obstacle_boxes() -> list:
            """World AABBs of scene objects that can block the base but are absent from the traversability map (movable
            furniture, appliances, doors): every object except structure, the robot and the task objects. Cached."""
            if _obstacle_cache:
                return _obstacle_cache[0]
            skip = {"floors", "walls", "ceilings", "roof", "carpet", "rug", "mat", "picture", "window", "light", "ceiling_lamp",
                    "wall_mounted_light", "electric_switch", "curtain", "blind", "painting", "wall_clock", "mirror"}
            task_names = set(s.spec.get("cans", [])) | set(s.spec.get("movable", [])) | {s.spec.get("trash")}
            boxes = []
            for obj in s.env.scene.objects:
                if obj is s.robot or getattr(obj, "visual_only", False) or getattr(obj, "category", "") in skip or s._name_of(obj) in task_names:
                    continue
                try:
                    lo, hi = obj.aabb
                    lo = th.as_tensor(lo).cpu().numpy().astype(float); hi = th.as_tensor(hi).cpu().numpy().astype(float)
                except Exception:  # noqa: BLE001
                    continue
                if hi[2] < 0.08 or lo[2] > 1.4 or (hi[0] - lo[0]) > 8 or (hi[1] - lo[1]) > 8:
                    continue  # flat on the floor, above the robot, or room-sized
                boxes.append((lo, hi))
            _obstacle_cache.append(boxes)
            _log(f"base planning: {len(boxes)} obstacle boxes from scene objects")
            return boxes

        def _paint_obstacles(m) -> None:
            """Mark the footprints of _obstacle_boxes() as blocked in the map tensor m (before erosion)."""
            tm = s.env.scene.trav_map
            H, W = int(m.shape[0]), int(m.shape[1])
            for lo, hi in _obstacle_boxes():
                rc = th.stack([th.as_tensor(tm.world_to_map(th.tensor([x, y]))).flatten() for x in (lo[0], hi[0]) for y in (lo[1], hi[1])]).cpu().numpy().astype(int)
                r0, r1 = max(0, int(rc[:, 0].min())), min(H, int(rc[:, 0].max()) + 1)
                c0, c1 = max(0, int(rc[:, 1].min())), min(W, int(rc[:, 1].max()) + 1)
                if r1 > r0 and c1 > c0:
                    m[r0:r1, c0:c1] = 0

        def back_up(dist: float = 0.3, max_steps: int = 150) -> int:
            """Translate straight backwards by `dist` metres without turning (unsticks a base pressed against an obstacle)."""
            bx, by, byaw = _base_pose()
            gx, gy = bx - dist * math.cos(byaw), by - dist * math.sin(byaw)
            n, best, stall = 0, float("inf"), 0
            while n < max_steps:
                cx, cy, cyaw = _base_pose()
                d = math.hypot(gx - cx, gy - cy)
                if d < 0.05:
                    break
                if d < best - 1e-3:
                    best, stall = d, 0
                else:
                    stall += 1
                    if stall > 45:
                        break
                step = min(0.03, d)
                q = s.robot.get_joint_positions().clone()
                q[s.robot.base_control_idx] = th.tensor(_base_joint_targets(cx - step * math.cos(byaw), cy - step * math.sin(byaw), byaw), dtype=q.dtype)
                s.step(s.keep_grip(s.robot.q_to_action(q))); n += 1
            return n

        def _eroded_map(clearance: float, obstacles: bool, container: str | None = None, goal=None):
            """Traversability map (torch, >0 free) with furniture footprints painted, then free space shrunk by `clearance`
            metres on every side (cv2 kernel = 2*ceil(clearance/res)+1, so the parameter IS the clearance, unlike the upstream
            default_erosion_radius which shrinks by only about half its value). `container` (the object we deliver to) is
            painted as well, and a disc of 0.3 m around `goal` is re-freed afterwards so the standoff pose stays reachable."""
            import cv2
            tm = s.env.scene.trav_map
            m = th.clone(tm.floor_map[0])
            if obstacles:
                _paint_obstacles(m)
            if container is not None:
                try:
                    lo, hi = get_object_bbox(container)[0] - get_object_bbox(container)[1] / 2, get_object_bbox(container)[0] + get_object_bbox(container)[1] / 2
                    rc = th.stack([th.as_tensor(tm.world_to_map(th.tensor([float(px), float(py)]))).flatten() for px in (lo[0], hi[0]) for py in (lo[1], hi[1])]).cpu().numpy().astype(int)
                    m[max(0, rc[:, 0].min()):rc[:, 0].max() + 1, max(0, rc[:, 1].min()):rc[:, 1].max() + 1] = 0
                except Exception as exc:  # noqa: BLE001
                    _log("container footprint skipped:", repr(exc)[:60])
            k = 2 * int(math.ceil(clearance / tm.map_resolution)) + 1
            m = th.tensor(cv2.erode(m.cpu().numpy(), np.ones((k, k), dtype=np.uint8)))
            if goal is not None:
                g = [int(v) for v in th.as_tensor(tm.world_to_map(th.tensor([float(goal[0]), float(goal[1])]))).flatten().tolist()]
                r = int(math.ceil(0.3 / tm.map_resolution)); free = th.clone(tm.floor_map[0])
                if obstacles:
                    _paint_obstacles(free)
                for dr in range(-r, r + 1):
                    for dc in range(-r, r + 1):
                        rr, cc = g[0] + dr, g[1] + dc
                        if dr * dr + dc * dc <= r * r and 0 <= rr < m.shape[0] and 0 <= cc < m.shape[1] and free[rr, cc] > 0:
                            m[rr, cc] = free[rr, cc]
            return m

        def _visible(m, a, b) -> bool:
            """Whether the straight map segment a->b (row, col cells) stays in free cells."""
            n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
            for i in range(n + 1):
                t = i / max(1, n); r, c = int(round(a[0] + t * (b[0] - a[0]))), int(round(a[1] + t * (b[1] - a[1])))
                if not (0 <= r < m.shape[0] and 0 <= c < m.shape[1]) or m[r, c] <= 0:
                    return False
            return True

        def plan_base_path(x: float, y: float, spacing: float = 0.45, erosions=(0.35, 0.3, 0.25, 0.2), obstacles: bool = True,
                           container: str | None = None) -> list:
            """Collision-free 2D waypoints from the robot to (x, y) on the scene's traversability map. `erosions` are the
            clearances (metres, largest first) tried until A* finds a path; with `obstacles` the footprints of the scene's
            movable furniture (absent from the map) are blocked first; `container` is blocked too except around the goal.
            Start/goal pixels are snapped to the nearest free cell. Waypoints are pruned by line of sight on the eroded map
            (a straight segment between consecutive waypoints never cuts a corner) and are at most ~spacing metres apart.
            Raises PrimitiveError when no path exists at all."""
            cx, cy, _ = _base_pose()
            tm = s.env.scene.trav_map
            mp = sys.modules[type(tm).__module__]
            astar = getattr(mp, "astar", None)
            if astar is None:
                from omnigibson.utils.motion_planning_utils import astar  # noqa: F401

            def snap(m, px):
                if m[px[0], px[1]] > 0:
                    return px
                for r in range(1, 12):
                    for dx in range(-r, r + 1):
                        for dy in (-r, r):
                            for q in ((px[0] + dx, px[1] + dy), (px[0] + dy, px[1] + dx)):
                                if 0 <= q[0] < m.shape[0] and 0 <= q[1] < m.shape[1] and m[q[0], q[1]] > 0:
                                    return q
                return px

            src = tuple(int(v) for v in tm.world_to_map(th.tensor([cx, cy])).tolist())
            dst = tuple(int(v) for v in tm.world_to_map(th.tensor([x, y])).tolist())
            path_map, m = None, None
            for er in erosions:
                m = _eroded_map(er, obstacles, container=container, goal=(x, y))
                path_map = astar(m, snap(m, src), snap(m, dst))
                if path_map is not None:
                    _log(f"plan_base_path: path with clearance {er} m{' + furniture' if obstacles else ''}, {len(path_map)} cells")
                    break
            if path_map is None:
                raise PrimitiveError(f"plan_base_path: no traversable path to ({x:.2f}, {y:.2f})")
            cells = [tuple(int(v) for v in c) for c in th.as_tensor(path_map).tolist()]
            keep, i = [], 0  # line-of-sight pruning on the eroded map, capped at `spacing`
            max_cells = max(1, int(spacing / tm.map_resolution))
            while i < len(cells) - 1:
                j = len(cells) - 1
                while j > i + 1 and (j - i > max_cells or not _visible(m, cells[i], cells[j])):
                    j -= 1
                keep.append(cells[j]); i = j
            pts = [(float(w[0]), float(w[1])) for w in tm.map_to_world(th.as_tensor(keep))] if keep else []
            if not pts or math.hypot(pts[-1][0] - x, pts[-1][1] - y) > 0.05:
                pts.append((x, y))
            return pts

        def navigate_to_pose(x: float, y: float, yaw: float, tol_pos: float = 0.06, tol_yaw: float = 0.12,
                             attempts: int = 2, max_steps: int = 2500, far: float = 1.0, container: str | None = None) -> int:
            """Drive the holonomic base to the world-frame 2D pose (x, y, yaw[rad]). Long legs follow traversability-map
            waypoints with the base follower (robust, obstacle-free path); the last metre is planned with cuRobo (base
            embodiment, collision-aware) and falls back to the follower if planning fails. Returns env steps."""
            total = 0
            cx, cy, _ = _base_pose()
            if math.hypot(x - cx, y - cy) > far:
                configs = (((0.4, 0.35, 0.3), True), ((0.25, 0.2), True), ((0.35, 0.25, 0.15), False))
                for erosions, obst in configs:
                    try:
                        wps = plan_base_path(x, y, erosions=erosions, obstacles=obst, container=container)
                    except PrimitiveError as exc:
                        _log(f"navigate_to_pose: {str(exc)[:90]}; trying the next planner config"); continue
                    _log(f"navigate_to_pose: {len(wps)} waypoints over {math.hypot(x - cx, y - cy):.2f} m (clearance {erosions[0]}.., furniture={obst})")
                    try:
                        for wx, wy in wps[:-1]:
                            total += _drive_to(wx, wy, None, tol_pos=0.15, tol_yaw=0.5, label="waypoint")
                        break
                    except PrimitiveError as exc:
                        _log(f"navigate_to_pose: {str(exc)[:90]}; backing up and re-planning")
                        total += back_up(0.3)  # the body is pressed against whatever stopped it: free it before turning
                else:
                    raise PrimitiveError("navigate_to_pose: waypoint following failed (blocked path)")
            err_pos = err_yaw = float("inf")
            for k in range(attempts):
                try:
                    pose3d = prim._get_robot_pose_from_2d_pose(th.tensor([x, y, yaw], dtype=th.float32))
                    link = s.robot.base_footprint_link_name
                    q_traj = prim._plan_joint_motion({link: pose3d[0]}, {link: pose3d[1]}, embodiment_selection=Emb.BASE)
                    total += s._run(prim._execute_motion_plan(q_traj, low_precision=True, ignore_failure=True), max_steps, "navigate_to_pose")
                except Exception as exc:  # noqa: BLE001  (cuRobo could not plan the final leg -> follower)
                    _log(f"navigate_to_pose: cuRobo final leg failed ({type(exc).__name__}: {str(exc)[:80]}); using the follower")
                    total += _drive_to(x, y, yaw, tol_pos=tol_pos, tol_yaw=tol_yaw, label="final leg")
                try:
                    total += s._run(prim._settle_robot(), 200, "navigate_to_pose/settle")
                except PrimitiveError:
                    pass  # still swaying a little is fine here
                cx, cy, cyaw = _base_pose()
                err_pos, err_yaw = math.hypot(cx - x, cy - y), abs(_wrap(cyaw - yaw))
                if err_pos <= tol_pos and err_yaw <= tol_yaw:
                    return total
                _log(f"navigate_to_pose attempt {k}: residual {err_pos:.3f} m / {err_yaw:.3f} rad")
            total += _drive_to(x, y, yaw, tol_pos=tol_pos, tol_yaw=tol_yaw, label="final correction")
            return total

        def base_pose_candidates(name: str, standoffs=(0.65, 0.8, 0.5, 0.95, 1.1), n_angles: int = 12):
            """World-frame (x, y, yaw) base poses around a task object, facing it, nearest-to-current-heading first."""
            opos, _ = get_object_pose(name)
            rpos, _ = get_robot_pose()
            a0 = math.atan2(opos[1] - rpos[1], opos[0] - rpos[0])  # direction robot -> object
            angles = sorted(range(n_angles), key=lambda i: abs(((i * 2 * math.pi / n_angles) + math.pi) % (2 * math.pi) - math.pi))
            out = []
            for d in standoffs:
                for i in angles:
                    a = a0 + i * 2 * math.pi / n_angles  # approach direction; robot stands at object - d*(cos a, sin a), faces +a
                    out.append((float(opos[0] - d * math.cos(a)), float(opos[1] - d * math.sin(a)), float((a + math.pi) % (2 * math.pi) - math.pi)))
            return out

        def _rot_z(q_xyzw, angle: float):
            """Rotate an XYZW quaternion about the world z axis by `angle` radians (left-multiply by the z rotation)."""
            x, y, z, w = [float(v) for v in q_xyzw]
            cz, sz = math.cos(angle / 2), math.sin(angle / 2)
            # r = (0,0,sz,cz) * q
            return np.array([cz * x - sz * y, cz * y + sz * x, cz * z + sz * w, cz * w - sz * z], dtype=float)

        def _as_pose(pose):
            return None if pose is None else (th.as_tensor(np.asarray(pose[0], dtype=np.float32)), th.as_tensor(np.asarray(pose[1], dtype=np.float32)))

        def debug_base_pose(name: str, eef_pose=None, n: int = 3) -> list:
            """Diagnostics: for the first n candidate base poses around an object, report the upstream validator's
            collision flag and (if eef_pose given) the arm reachability flag separately."""
            out = []
            eef = _as_pose(eef_pose)
            for cand in base_pose_candidates(name)[:n]:
                q = s.robot.get_joint_positions().clone(); q[s.robot.base_control_idx] = th.tensor(_base_joint_targets(*cand), dtype=q.dtype)
                rec = {"pose": [round(c, 3) for c in cand]}
                try:
                    rec["collision"] = bool(prim._motion_generator.check_collisions(q.unsqueeze(0), self_collision_check=False).cpu()[0])
                except Exception as exc:  # noqa: BLE001
                    rec["collision"] = f"err {repr(exc)[:80]}"
                if eef is not None:
                    try:
                        rec["reach"] = bool(prim._target_in_reach_of_robot(eef, initial_joint_pos=q))
                    except Exception as exc:  # noqa: BLE001
                        rec["reach"] = f"err {repr(exc)[:80]}"
                out.append(rec); _log("debug_base_pose", name, rec)
            return out

        def _cell_free(x: float, y: float, clearance: float = 0.3) -> bool:
            """Whether a base at world (x, y) keeps `clearance` metres from map obstacles and the scene's furniture."""
            try:
                m = _eroded_map(clearance, True)
                r, c = [int(v) for v in th.as_tensor(s.env.scene.trav_map.world_to_map(th.tensor([float(x), float(y)]))).flatten().tolist()]
                return 0 <= r < m.shape[0] and 0 <= c < m.shape[1] and bool(m[r, c] > 0)
            except Exception as exc:  # noqa: BLE001
                _log("_cell_free failed, assuming free:", repr(exc)[:60]); return True

        def candidate_ok(cand, eef=None) -> bool:
            """Collision check of the base at a world (x, y, yaw) pose and, if eef given, arm reachability from there
            (cuRobo, with the base joints converted to the root frame, which the upstream validator forgets)."""
            q = s.robot.get_joint_positions().clone(); q[s.robot.base_control_idx] = th.tensor(_base_joint_targets(*cand), dtype=q.dtype)
            try:
                held_obj = prim._get_obj_in_hand()
                attached = {s.robot.eef_link_names[prim.arm]: held_obj.root_link} if held_obj is not None else None
                if bool(prim._motion_generator.check_collisions(q.unsqueeze(0), self_collision_check=False, attached_obj=attached).cpu()[0]):
                    return False
                return eef is None or bool(prim._target_in_reach_of_robot(eef, initial_joint_pos=q))
            except Exception as exc:  # noqa: BLE001
                _log("candidate_ok check failed, assuming ok:", repr(exc)[:80]); return True

        def navigate_to_object(name: str, eef_pose=None, standoffs=(0.65, 0.8, 0.5, 0.95, 1.1), max_attempts: int = 6,
                               validate: bool = True) -> tuple:
            """Drive the base to a pose near the object (facing it) from which the default arm can reach eef_pose (if given).
            Candidates are tried in order through the motion planner itself (a goal in collision simply fails to plan);
            `validate=True` additionally pre-filters with the upstream collision/reach validator. Returns the (x, y, yaw)
            reached; raises PrimitiveError if no candidate works within max_attempts."""
            eef = _as_pose(eef_pose)
            tried, last_err, blocked = 0, None, 0
            for cand in base_pose_candidates(name, standoffs):
                if tried >= max_attempts:
                    break
                if not _cell_free(cand[0], cand[1]):
                    blocked += 1; continue  # would stand inside / against furniture the validator cannot see
                if validate and not candidate_ok(cand, eef):
                    continue
                tried += 1
                try:
                    navigate_to_pose(*cand, attempts=2, container=(name if eef is None else None))
                except Exception as exc:  # noqa: BLE001  planning or execution failure -> next candidate
                    last_err = f"{type(exc).__name__}: {str(exc)[:100]}"
                    _log(f"navigate_to_object({name}) candidate {tried} failed: {last_err}")
                    continue
                if eef is None or prim._target_in_reach_of_robot(eef):
                    return cand
                last_err = "arrived but the end effector pose is out of reach"
                _log(f"navigate_to_object({name}) candidate {tried}: {last_err}")
            if validate and tried == 0:
                _log(f"navigate_to_object({name}): validator rejected every candidate ({blocked} blocked by furniture); trying unvalidated")
                return navigate_to_object(name, eef_pose=eef_pose, standoffs=standoffs, max_attempts=3, validate=False)
            raise PrimitiveError(f"navigate_to_object({name}): no usable base pose ({tried} tried; last: {last_err})")

        def sample_grasp_pose(name: str):
            """((pre_pos, pre_quat), (grasp_pos, grasp_quat)) top-down grasp for the object, world frame, XYZW."""
            pre, gr = prim._sample_grasp_pose(s.get_object(name))
            f = lambda p: (p[0].cpu().numpy().astype(float), p[1].cpu().numpy().astype(float))
            return f(pre), f(gr)

        def in_reach(pos, quat_xyzw) -> bool:
            """Whether the default arm can reach the world-frame pose from the current base pose (cuRobo IK)."""
            return bool(prim._target_in_reach_of_robot((th.tensor(pos, dtype=th.float32), th.tensor(quat_xyzw, dtype=th.float32))))

        def move_hand(pos, quat_xyzw, motion_constraint=None, low_precision: bool = False, max_steps: int = 2500, attempts: int = 3,
                      ignore_objects=None) -> int:
            """Plan (cuRobo, arm embodiment) and move the default end effector to the world-frame pose. motion_constraint
            [x,y,z,rx,ry,rz] with 1 = constrained (e.g. [1,1,1,1,1,0] keeps position and tilt, frees yaw). Returns env steps."""
            target = (th.tensor(np.asarray(pos, dtype=np.float32)), th.tensor(np.asarray(quat_xyzw, dtype=np.float32)))
            last = None
            for k in range(attempts):
                try:
                    ign = [s.get_object(o) if isinstance(o, str) else o for o in (ignore_objects or [])] or None
                    return s._run(prim._move_hand(target, motion_constraint=motion_constraint, low_precision=low_precision, ignore_objects=ign), max_steps, "move_hand")
                except PrimitiveError:
                    raise
                except Exception as exc:  # noqa: BLE001  (cuRobo planning is stochastic: retry)
                    import traceback as _tb
                    last = f"{type(exc).__name__}: {str(exc)[:120]}"
                    frames = [f for f in _tb.format_exc().splitlines() if f.strip().startswith("File")][-2:]
                    _log(f"move_hand attempt {k} failed: {last} @ {' | '.join(x.strip() for x in frames)}")
            raise PrimitiveError(f"move_hand: {last}")

        def move_hand_direct(pos, quat_xyzw, max_steps: int = 600, ignore_objects=None) -> int:
            """Move the default end effector to the world-frame pose WITHOUT motion planning: cuRobo IK for the
            trunk+arm joints, then direct joint interpolation (stops when reached or stuck). Ignores obstacles on the
            way; use when planning keeps failing in clutter. The IK's world-collision check excludes the object in hand
            and `ignore_objects` (names): the upstream IK treats every scene object as an obstacle, so a held can or the
            can about to be grasped would make every pose near it "infeasible". Returns env steps; raises if IK finds no
            solution."""
            target = (th.tensor(np.asarray(pos, dtype=np.float32)), th.tensor(np.asarray(quat_xyzw, dtype=np.float32)))
            ign = [s.get_object(o) if isinstance(o, str) else o for o in (ignore_objects or [])]
            held_obj = prim._get_obj_in_hand()
            if held_obj is not None:
                ign.append(held_obj)
            try:
                prim._motion_generator.update_obstacles(ignore_objects=ign or None)
            except Exception as exc:  # noqa: BLE001
                _log("update_obstacles failed:", repr(exc)[:80])
            q = None
            for _ in range(8):  # cuRobo IK is seeded randomly: retry several times before giving up
                res = prim._ik_solver_cartesian_to_joint_space(target, skip_obstacle_update=True)
                q = res[0] if isinstance(res, (tuple, list)) else res
                if q is not None:
                    break
            if q is None:
                bx, by, byaw = _base_pose(); p = np.asarray(pos, dtype=float)
                fwd = (p[0] - bx) * math.cos(byaw) + (p[1] - by) * math.sin(byaw); lat = -(p[0] - bx) * math.sin(byaw) + (p[1] - by) * math.cos(byaw)
                raise PrimitiveError(f"move_hand_direct: no IK solution for the target pose (base-relative fwd {fwd:.2f} lat {lat:.2f} z {p[2]:.2f}, held={object_in_hand()})")
            q = th.as_tensor(q).flatten()
            idx = prim._manipulation_control_idx()
            if q.numel() != idx.numel():  # full joint vector returned: slice the trunk+arm entries
                q = q[idx]
            return _direct_joint_motion(q, idx, max_steps) + settle(150)

        def _direct_joint_motion(q_target, idx, max_steps: int = 600, tol: float = 0.02, rate: float = 0.02) -> int:
            """Linearly interpolate the trunk+arm joint targets (indices idx) from the current values to q_target at
            ~rate rad per control step, then hold until converged (tol) or stuck; base and grippers hold their targets."""
            q_target = q_target.to(s.robot.get_joint_positions().dtype)
            q0 = s.robot.get_joint_positions()[idx].clone()
            T = max(20, int(float(th.max(th.abs(q_target - q0))) / rate))
            best, stall, n = float("inf"), 0, 0
            for k in range(max_steps):
                alpha = min(1.0, (k + 1) / T)
                q_full = s.robot.get_joint_positions().clone()
                q_full[idx] = q0 + alpha * (q_target - q0)
                s.step(s.keep_grip(s.robot.q_to_action(q_full))); n += 1
                err = float(th.max(th.abs(q_target - s.robot.get_joint_positions()[idx])))
                if alpha >= 1.0:
                    if err < tol:
                        return n
                    if err < best - 1e-3:
                        best, stall = err, 0
                    else:
                        stall += 1
                        if stall > 60:
                            _log(f"direct joint motion stuck (residual {err:.3f} rad)"); return n
            return n

        def _move_hand_robust(pos, quat_xyzw, motion_constraint=None, low_precision=True, attempts=2, ignore_objects=None) -> int:
            """Planned motion first, direct IK motion as the fallback."""
            try:
                return move_hand(pos, quat_xyzw, motion_constraint=motion_constraint, low_precision=low_precision, attempts=attempts, ignore_objects=ignore_objects)
            except Exception as exc:  # noqa: BLE001
                _log("planned move failed, falling back to direct IK motion:", str(exc)[:100])
                return move_hand_direct(pos, quat_xyzw, ignore_objects=ignore_objects)

        def tuck_arm(max_steps: int = 300) -> int:
            """Bring trunk and arms back to the robot's reset joint pose (compact). Optional: measured runs did not
            improve with an automatic tuck (the reset pose is sometimes unreachable), so nothing calls it implicitly."""
            idx = prim._manipulation_control_idx()
            q_reset = th.as_tensor(s.robot.reset_joint_pos)[idx]
            return _direct_joint_motion(q_reset, idx, max_steps) + _safe_settle(100)

        def carry(height: float = 0.95, forward: float = 0.35, lateral: float = 0.15) -> int:
            """Pull the held object close to the body (robot-frame offset) for carrying; keeps the top-down grip."""
            bx, by, byaw = _base_pose()
            c, si = math.cos(byaw), math.sin(byaw)
            pos = np.array([bx + c * forward - si * lateral, by + si * forward + c * lateral, height])
            _, quat = get_eef_pose()
            try:
                return move_hand_direct(pos, quat)
            except PrimitiveError as exc:
                _log("carry: could not reach the carry pose, keeping the current arm pose:", str(exc)[:60]); return 0

        def grasp(name: str, navigate: bool = True) -> str:
            """Grasp a task object with the default arm: sample a top-down grasp, navigate if out of reach, approach,
            descend, close (assisted grasping), settle. Returns the name when the object is in hand, else raises."""
            (pre_p, pre_q), (gr_p, gr_q) = sample_grasp_pose(name)
            if navigate and not in_reach(pre_p, pre_q):
                # closer standoffs first: a less extended arm keeps the IK away from joint limits and nearby furniture
                navigate_to_object(name, eef_pose=(pre_p, pre_q), standoffs=(0.65, 0.8, 0.55, 0.95))
            bx, by, byaw = _base_pose()
            _log(f"grasp({name}): object at {np.round(get_object_pose(name)[0], 3).tolist()}, base ({bx:.2f}, {by:.2f}, {byaw:.2f}), "
                 f"pre-grasp {np.round(pre_p, 3).tolist()} in reach: {in_reach(pre_p, pre_q)}")
            for attempt in range(2):
                try:
                    _move_hand_robust(pre_p, pre_q, low_precision=False, attempts=1, ignore_objects=[name])
                    move_hand_direct(gr_p, gr_q, ignore_objects=[name])  # short straight descent: planner-free
                    break
                except PrimitiveError as exc:
                    if attempt == 1 or not navigate:
                        raise
                    _log(f"grasp({name}): {str(exc)[:70]}; moving the base a little closer and retrying")
                    navigate_to_object(name, eef_pose=(pre_p, pre_q), standoffs=(0.55, 0.6, 0.5), max_attempts=4)
            _log(f"grasp({name}): descended; object now at {np.round(get_object_pose(name)[0], 3).tolist()}, eef {np.round(get_eef_pose()[0], 3).tolist()}")
            close_gripper()
            _safe_settle(200)
            held = object_in_hand()
            if held != name:  # second try: re-sample (the object may have been nudged) and grasp a little lower
                _log(f"grasp({name}): first close missed (held={held}); re-sampling and retrying 1.5 cm lower")
                open_gripper()
                (pre_p, pre_q), (gr_p, gr_q) = sample_grasp_pose(name)
                move_hand_direct(pre_p, pre_q, ignore_objects=[name])
                move_hand_direct(gr_p - np.array([0.0, 0.0, 0.015]), gr_q, ignore_objects=[name])
                close_gripper()
                _safe_settle(200)
                held = object_in_hand()
            if held != name:
                raise PrimitiveError(f"grasp({name}): nothing in hand after closing (held={held})")
            return name

        def lift(dz: float = 0.25) -> int:
            """Raise the end effector straight up by dz metres (keeps orientation)."""
            pos, quat = get_eef_pose()
            return _move_hand_robust(pos + np.array([0.0, 0.0, dz]), quat, low_precision=True, attempts=1)

        _place_counter = {"n": 0}

        def last_delivery_pose():
            """World (x, y, yaw) base pose from which the last place_inside() released its object, or None."""
            return _place_counter.get("pose")

        def _fillable_link(obj):
            """The container's fillable meta link (the inner volume the `inside` predicate tests), or None."""
            from omnigibson.macros import macros as _macros
            for link in obj.links.values():
                if link.is_meta_link and link.meta_link_type in _macros.object_states.contains.CONTAINER_META_LINK_TYPES:
                    return link
            return None

        def _contents(container: str, held: str | None) -> list:
            """(name, AABB centre, AABB extent) of the task objects whose AABB centre lies within the container's AABB."""
            c, e = get_object_bbox(container)
            out = []
            for name in s._scope():
                if name in (container, held) or name.startswith("agent"):
                    continue
                try:
                    oc, oe = get_object_bbox(name)
                except Exception:  # noqa: BLE001
                    continue
                if np.all(np.abs(oc - c) <= e / 2):
                    out.append((name, oc, oe))
            return out

        def _rot_axis(q_xyzw, axis, angle: float):
            """Rotate an XYZW quaternion about a world axis by `angle` radians (left-multiply by the axis rotation)."""
            ax = np.asarray(axis, dtype=float); ax = ax / max(1e-9, float(np.linalg.norm(ax)))
            rx, ry, rz = ax * math.sin(angle / 2); rw = math.cos(angle / 2)
            x, y, z, w = [float(v) for v in q_xyzw]
            return np.array([rw * x + rx * w + ry * z - rz * y, rw * y - rx * z + ry * w + rz * x,
                             rw * z + rx * y - ry * x + rz * w, rw * w - rx * x - ry * y - rz * z], dtype=float)

        def _landing_spot(container: str, held: str, fdir, ldir, lay: bool = False) -> dict:
            """Where to release the held object over the container (see place_inside): dict(x, y, floor, centre_z, fwd,
            lat, clear, fits). Candidates are points of the opening where the object fits inside the fillable volume at the
            height of its middle once it rests there (upright: its round footprint; lying along the robot's forward axis:
            its two ends), never beyond the container's centre as seen from the robot (reaching past it makes the trunk
            lean over the container and drag it when backing away). A candidate's floor is the container's floor, or the
            top of an object already inside whose footprint it overlaps (an object released over another stacks on it).
            Chosen: the lowest floor, then the farthest from the contents, then the one nearest to the preferred point (fwd
            -0.02 and, upright, lat +0.035: the first object goes to one side so the next one still finds floor space).
            `fits`: the object's centre ends inside the fillable volume (the `inside` predicate); a third upright soda can
            in a trash can does not, which is what lying them down is for. Object sizes come from their world AABBs, the
            smaller horizontal extent being the diameter (a held object is often tilted a little)."""
            c, e = get_object_bbox(container)
            _, he = get_object_bbox(held)
            link = _fillable_link(s.get_object(container))
            if link is not None:
                vlo, vhi = [th.as_tensor(v).cpu().numpy().astype(float) for v in link.visual_aabb]
                inside = lambda P: np.asarray(link.check_points_in_volume(th.tensor(P, dtype=th.float32)).cpu()).astype(bool)
            else:
                vlo, vhi = c - e / 2 + 0.02, c + e / 2 - 0.02
                inside = lambda P: np.all((P >= vlo) & (P <= vhi), axis=1)
            vc = (vlo[:2] + vhi[:2]) / 2
            if lay:  # lying along fdir: half length L, radius W (= its half height once down)
                L, W = 0.5 * float(max(he)), 0.5 * float(min(he))
                hh, pref = W, (-0.02, 0.0)
                cand = np.array([vc + f * fdir + l * ldir for f in (-0.04, -0.02, 0.0) for l in np.arange(-0.05, 0.0501, 0.01)])
            else:
                W = 0.5 * float(min(he[0], he[1])); L = W
                hh, pref = 0.5 * float(he[2]), (-0.02, 0.035)
                cand = np.array([(x, y) for x in np.arange(vlo[0], vhi[0] + 1e-9, 0.01) for y in np.arange(vlo[1], vhi[1] + 1e-9, 0.01)])
            rel = cand - c[:2]
            fwd, lat = rel @ fdir, rel @ ldir
            keep = fwd <= 0.01
            cand, fwd, lat = cand[keep], fwd[keep], lat[keep]
            floor, clear = np.full(len(cand), float(vlo[2])), np.full(len(cand), np.inf)
            for _, oc, oe in _contents(container, held):
                rc = 0.5 * float(min(oe[0], oe[1]))
                dv = cand - oc[:2]; d = np.linalg.norm(dv, axis=1)
                clear = np.minimum(clear, d)
                over = (np.abs(dv @ ldir) < W + rc - 0.01) & (np.abs(dv @ fdir) < L + rc - 0.01)
                floor = np.where(over, np.maximum(floor, float(oc[2] + oe[2] / 2)), floor)
            zc = floor + hh
            if lay:
                offs = [np.zeros(2), (L - 0.02) * fdir, -(L - 0.02) * fdir]
            else:
                offs = [np.zeros(2)] + [W * np.array([math.cos(a), math.sin(a)]) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
            P = np.stack([np.concatenate([cand + o, zc[:, None]], axis=1) for o in offs], axis=1)  # (N, k, 3)
            ok = inside(P.reshape(-1, 3)).reshape(len(cand), len(offs)).all(axis=1)
            if not ok.any():  # nothing fits: still pick the best point, `fits` says it will not be inside
                ok = np.ones(len(cand), dtype=bool)
            idx = np.flatnonzero(ok)
            near = np.hypot(fwd[idx] - pref[0], lat[idx] - pref[1])
            i = int(idx[np.lexsort((near, -np.minimum(clear[idx], 0.12).round(2), floor[idx].round(2)))[0]])
            fits = bool(zc[i] <= vhi[2] and inside(np.array([[cand[i][0], cand[i][1], zc[i]]]))[0])
            return dict(x=float(cand[i][0]), y=float(cand[i][1]), floor=float(floor[i]), centre_z=float(zc[i]), fwd=float(fwd[i]),
                        lat=float(lat[i]), clear=float(clear[i]), fits=fits)

        def place_inside(container: str, standoffs=(0.7, 0.8, 0.6), drop_heights=(0.16, 0.22, 0.3), back_away: float = 0.45,
                         base_pose=None, lower: bool = True, spot=None, lay: bool = False) -> int:
            """Put the held object inside a container: navigate to it (a preferred world (x, y, yaw) `base_pose` first if
            given, then several standoffs; >= 0.6 m so the base can turn in place without its corners hitting the container),
            pick a landing spot (below), bring the object above it (IK, several heights and yaws, within 6 cm), lower it into
            the container until it is 3 cm above the floor or whatever lies under it (`lower`; as deep as a collision-free IK
            solution exists), open the gripper, raise the open hand straight out, back straight away and fold the arm.
            Landing spot: `spot` = (fwd, lat) metres from the container's centre in the robot's frame (fwd towards the
            container), else chosen from the container's fillable volume (the inner volume the `inside` predicate tests) and
            the objects already in it: the lowest free floor, as far from the others as fits, the first object to one side.
            `lay`: turn the object 90 degrees (the gripper pointing away from the robot) so a tall object lies down; a
            stack of upright objects sticks out of the fillable volume sooner. Objects dropped from above the rim bounce and
            roll (measured: 1-8 cm from the release point) and stack up. Returns env steps; raises PrimitiveError if nothing
            worked (the object may still be held)."""
            # NOTE: the upstream PLACE_INSIDE primitive is deliberately not used: its placement sampler teleports objects
            # around while searching, which is not an action, so a live run would no longer match its own replay.
            # The hover/approach height keeps the carried object and the fingers (they hang ~9 cm below the eef frame) clear
            # of the rim; after a release the open hand goes straight up before the base moves (measured: backing away with
            # the fingers at rim height hooked the container and dragged it over).
            n = 0
            held = object_in_hand()
            if held is None:
                raise PrimitiveError("place_inside: nothing in hand")
            center, ext = get_object_bbox(container)
            last = None
            approaches = ([("pose", tuple(base_pose))] if base_pose is not None else []) + [("standoff", d) for d in standoffs]
            for kind, standoff in approaches:
                try:
                    if kind == "pose":
                        navigate_to_pose(*standoff, attempts=2, container=container)
                    else:
                        navigate_to_object(container, eef_pose=None, standoffs=(standoff,), max_attempts=3, validate=True)
                except Exception as exc:  # noqa: BLE001
                    last = f"navigate({standoff}): {str(exc)[:100]}"; _log("place_inside:", last); continue
                center2, ext = get_object_bbox(container)  # the container may have been bumped: aim at where it is now
                if np.linalg.norm(center2[:2] - center[:2]) > 0.1:
                    _log(f"place_inside: WARNING the container moved {np.linalg.norm(center2[:2] - center[:2]):.2f} m since the start")
                center = center2
                bx0, by0, byaw0 = _base_pose(); fdir = np.array([center[0] - bx0, center[1] - by0]); fdir /= max(1e-6, np.linalg.norm(fdir))
                ldir = np.array([-fdir[1], fdir[0]]); heading = math.atan2(fdir[1], fdir[0])
                sp = None
                if spot is None:
                    try:
                        sp = _landing_spot(container, held, fdir, ldir, lay=lay)
                    except Exception as exc:  # noqa: BLE001
                        _log("place_inside: landing-spot search failed:", repr(exc)[:120])
                if sp is None:
                    f0, l0 = (float(spot[0]), float(spot[1])) if spot is not None else (-0.04, 0.0)
                    p0 = center[:2] + f0 * fdir + l0 * ldir
                    sp = dict(x=float(p0[0]), y=float(p0[1]), floor=float(center[2] - ext[2] / 2), centre_z=float("nan"), fwd=f0, lat=l0,
                              clear=float("nan"), fits=None)
                    for _, oc, oe in _contents(container, held):  # released over another object: its top is the floor
                        if np.linalg.norm(p0 - oc[:2]) < 0.5 * float(max(get_object_bbox(held)[1][:2])) + 0.5 * float(max(oe[0], oe[1])) - 0.01:
                            sp["floor"] = max(sp["floor"], float(oc[2] + oe[2] / 2))
                _log(f"place_inside: after navigation container at {np.round(center, 3).tolist()} extent {np.round(ext, 3).tolist()}; "
                     f"landing spot fwd {sp['fwd']:+.3f} lat {sp['lat']:+.3f} from its centre, floor z {sp['floor']:.3f}, object centre "
                     f"would rest at z {sp['centre_z']:.3f} (inside the fillable volume: {sp['fits']}), clearance to the contents {sp['clear']:.3f} m"
                     + (", lying" if lay else ""))
                rim = center[2] + ext[2] / 2
                for dh in drop_heights:
                    for yaw_deg in (0, 90):
                        quat = _rot_z(TOP_DOWN_XYZW, math.radians(yaw_deg))
                        if lay:  # the gripper axis (and the object held along it) turned horizontal, pointing away from the robot
                            quat = _rot_axis(_rot_z(TOP_DOWN_XYZW, heading + math.radians(yaw_deg)), (ldir[0], ldir[1], 0.0), -math.pi / 2)
                        hover = np.array([sp["x"], sp["y"], rim + dh + 0.25])  # carried object well above the rim first
                        try:
                            n += _move_hand_robust(hover, quat, low_precision=True, attempts=1)
                            # aim the OBJECT at the spot: it hangs off the eef (below it upright, in front of it lying)
                            d_obj = get_object_bbox(held)[0] - get_eef_pose()[0]
                            hover = np.array([sp["x"] - d_obj[0], sp["y"] - d_obj[1], hover[2]])
                            top = hover - np.array([0.0, 0.0, 0.25])
                            n += move_hand_direct(top, quat)
                            eef = get_eef_pose()[0]; off = math.hypot(eef[0] - top[0], eef[1] - top[1])
                            if off > 0.05:  # IK/tracking left the hand off-centre: one more direct move from the new configuration
                                n += move_hand_direct(top, quat); eef = get_eef_pose()[0]; off = math.hypot(eef[0] - top[0], eef[1] - top[1])
                        except Exception as exc:  # noqa: BLE001
                            last = f"move_hand_direct(standoff {standoff}, dh {dh}, yaw {yaw_deg}): {str(exc)[:100]}"; _log("place_inside:", last); continue
                        if off > 0.06:
                            last = f"hand {off:.2f} m off the opening (standoff {standoff}, dh {dh}, yaw {yaw_deg})"; _log("place_inside:", last); continue
                        lowered = 0.0
                        if lower:
                            hc, he = get_object_bbox(held)
                            drop = float(hc[2] - he[2] / 2) - (sp["floor"] + 0.03)  # object bottom -> 3 cm above its floor
                            eef0 = get_eef_pose()[0]
                            for frac in (1.0, 0.6, 0.3):
                                dz = drop * frac
                                if dz < 0.03:
                                    break
                                try:
                                    n += move_hand_direct(eef0 - np.array([0.0, 0.0, dz]), quat)
                                    lowered = float(eef0[2] - get_eef_pose()[0][2]); break
                                except Exception as exc:  # noqa: BLE001
                                    _log(f"place_inside: could not lower the object {dz:.2f} m: {str(exc)[:80]}")
                        _log(f"place_inside: object above the spot within {off:.2f} m (standoff {standoff}, dh {dh}, yaw {yaw_deg}), lowered "
                             f"{lowered:.2f} m, object bottom at z {float(get_object_bbox(held)[0][2] - get_object_bbox(held)[1][2] / 2):.3f}; "
                             f"container at {np.round(get_object_bbox(container)[0], 3).tolist()}; releasing")
                        n += open_gripper(); n += _safe_settle(150)
                        if object_in_hand() is None:
                            _place_counter["n"] += 1
                            _place_counter["pose"] = _base_pose()
                            if lowered > 0 or lay:  # the open fingers are in (or right above) the container: straight up first
                                try:
                                    n += move_hand_direct(hover, quat)
                                except Exception as exc:  # noqa: BLE001
                                    _log("place_inside: raising the open hand failed:", str(exc)[:80])
                                    try:
                                        n += lift(max(0.1, lowered + 0.1))
                                    except Exception as exc2:  # noqa: BLE001
                                        _log("place_inside: lift after release failed too:", str(exc2)[:80])
                            _log(f"place_inside: released; container at {np.round(get_object_bbox(container)[0], 3).tolist()}, object at "
                                 f"{np.round(get_object_bbox(held)[0], 3).tolist()}, eef {np.round(get_eef_pose()[0], 3).tolist()}")
                            # Contacts shove the whole (floating-base) robot around: retreat straight backwards (no turn, so
                            # nothing sweeps through the container), then fold the arm for the next navigation.
                            if back_away > 0:
                                n += back_up(back_away)
                                _log(f"place_inside: after back-up container at {np.round(get_object_bbox(container)[0], 3).tolist()} extent {np.round(get_object_bbox(container)[1], 3).tolist()}")
                            try:  # fold the arm before the next navigation (a low extended hand hits furniture the map ignores)
                                n += tuck_arm()
                                _log(f"place_inside: after tuck container at {np.round(get_object_bbox(container)[0], 3).tolist()}")
                            except Exception as exc:  # noqa: BLE001
                                _log("place_inside: post-release tuck skipped:", str(exc)[:80])
                            return n
                        last = "gripper opened but the object is still attached"
            raise PrimitiveError(f"place_inside({container}): {last}")

        def place_on_top(surface: str) -> int:
            """Put the held object on top of a surface object (upstream PLACE_ON_TOP primitive). WARNING: its placement
            sampler moves objects while searching (not actions): the live outcome may differ from the replay; verify with
            the fresh-process `replay` CLI."""
            return s._run(prim.apply_ref(P.PLACE_ON_TOP, s.get_object(surface), attempts=1), 4000, "place_on_top", keep_grip=False)

        return {k: v for k, v in locals().items() if callable(v) and not k.startswith("_") and k not in ("th", "s", "prim", "Emb", "P")}

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives and this session in scope (like cap-x's executor)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "th": self.th, "session": self, "s": self,
                             "objects": self.objects, "TASK": self.spec, **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)  # noqa: S102
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            return {"ok": False, "error": repr(exc)[:400], "traceback": traceback.format_exc()[-2000:]}

    def _log_end(self) -> None:
        if not self._end_logged:           # og.shutdown() ends the process before atexit handlers run
            self._end_logged = True
            _slog("session_end", task=self.task, resets=self._resets, sim_steps=self._total_steps + int(self.env.episode_steps))

    def close(self) -> None:
        """Shuts Isaac Sim down. NOTE: og.shutdown() terminates the process; write all outputs before calling this."""
        self._log_end()
        try:
            self.ev.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: (d[k].item() if d[k].shape == () else d[k]) for k in d.files}


def cmd_make_instance(a) -> None:
    s = Session(a.task, instance_id=a.instance_id, mode=a.mode, robot_config=a.robot_config)
    out = {"task": a.task, "challenge_task": s.spec["challenge_task"], "instance_id": s.instance_id, "mode": s.mode, "text": s.spec["text"],
           "robot_config": s.robot_config_path.name, "robot_config_sha": s.robot_config_sha,
           "state_sha": s.instance_sha, "action_dim": s.action_dim, "challenge_max_steps": s.challenge_max_steps,
           "objects": s.objects(), "omnigibson_version": __import__("omnigibson").__version__}
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha, "action_dim": s.action_dim}), flush=True)
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
    s = Session(a.task, instance=a.instance, cameras="default" if a.video else "tiny", strict=a.strict)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    t0 = time.time()
    outs = []
    for i in range(a.repeat):
        if a.video and i == 0:
            s.start_video(a.video, fps=a.fps)   # the video shows the first (fresh-process-exact) replay
        outs.append(s.replay(acts))
        if a.video and i == 0:
            s.stop_video()
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "wall_s": round(time.time() - t0, 1), "video": a.video}
    print(json.dumps(out), flush=True)
    s.close()


def cmd_selftest(a) -> None:
    """Determinism evidence in 4 fresh processes: make-instance, run-oracle, replay, replay (fresh == fresh == live)."""
    here, out = Path(__file__).resolve(), Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    inst, traj = out / "instance.json", out / "trajectory.npz"
    def run(*args):
        cmd = [sys.executable, str(here), *map(str, args)]
        _log("selftest>", " ".join(cmd[2:]))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=open(out / "selftest.stderr.log", "ab"), text=True)
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {"error": f"no json output (rc={p.returncode})"}
    r0 = run("make-instance", "--task", a.task, "--instance-id", a.instance_id, "--robot-config", a.robot_config, "--out", inst)
    r1 = run("run-oracle", "--task", a.task, "--instance", inst, "--code", a.code, "--out", traj)
    r2 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    r3 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--strict")
    sha = [((r.get("replays") or [{}])[0]).get("state_sha") for r in (r2, r3)]
    ok = bool(r1.get("success")) and bool(r2.get("all_success")) and bool(r3.get("all_success")) and sha[0] == sha[1] \
        and bool(r2.get("instance_matches")) and bool(r3.get("instance_matches"))
    print(json.dumps({"make_instance": r0, "oracle": r1, "replay_1": r2, "replay_2": r3, "live_equals_replay": sha[0] == r1.get("state_sha"), "PASS": ok}, indent=1), flush=True)
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--instance-id", type=int, required=True)
    q.add_argument("--mode", default="public_test"); q.add_argument("--robot-config", default=None); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=1, help="in-process repeats; only the first is fresh-process exact")
    q.add_argument("--video", default=None); q.add_argument("--fps", type=int, default=30)
    q.add_argument("--strict", action="store_true", help="fail if the instance state sha differs from instance.json"); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="picking_up_trash"); q.add_argument("--instance-id", type=int, default=301); q.add_argument("--code", required=True); q.add_argument("--robot-config", default=str(Path(__file__).parent / "r1pro_primitives_eval.yaml")); q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
