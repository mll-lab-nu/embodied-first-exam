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
             of ACTION_LAYOUT) the arm joint targets (rad) and the gripper target declared by the frozen instance / robot_spec.
             The physics runs where the instance's `simulator.compute_backend` says: the GPU (CUDA) for the soft-body
             families and lock_picking, whose contact solver is not bit-deterministic (repeated replays agree to ~1e-11
             in the state but not bit for bit), and the CPU for the other rigid families, whose replays are
             bit-deterministic on one host. Either way `deterministic` (state hashes equal) is reported and not
             required; every replay must complete the task (the same rule as robot_coding_bench's GPU backend). Nyx
             renders on the GPU in both cases.
episode end: a task's success predicate, or one of its failure predicates (e.g. touching the buzz wire), ends the
             simulated episode: later steps do not change the execution ledger or scene, and status()["episode_end"] says
             why. reset() starts again from the frozen state. A simulator breakdown (a non-finite state, a particle faster
             than PARTICLE_SPEED_LIMIT_M_S, 20 m/s, an invalid soft-body solver state, a rigid task contact deeper than
             BREAKDOWN_PENETRATION_M) ends it with episode_end "simulator_instability" (evidence in
             status()["instability"]): a simulator failure that graders report as an infrastructure error, never as
             success or as the task's failure; unless the arm was forcing (the forcing condition, FORCING) within the
             0.25 s before, then it is the agent's "forced_breakdown: ...". PBD cloth-rigid contacts are resolved
             together per particle with a physically bounded push-out (_bound_pbd_rigid_contacts), which removes the
             cause of the cloth blow-ups.
grasping   : a family may enable TopoGym's passive grasp assistance (instance.json simulator.grasp_assist; the rules are
             in robot_spec()["grippers"][...]["command"]); primitives()["object_in_hand"] says what a gripper holds.
budget     : there is no step budget: the agent's wall clock is the limit. MAX_STEPS only stops runaway trajectories.
safety     : the tooling's physical-validity policy (tooling v16, _install_rules): arm drive torques are capped and no
             gripper target goes lower than 15 mm below the tabletop (TABLE_GUARD_MARGIN_M); a crushed rope volume or a
             stretched cord attachment fails after 0.25 s; forcing (an arm drive at its torque cap while the gripper or a
             part it holds presses on another body, FORCING) and task-contact penetration are evidence only: a success
             with a deep task contact (CONTACT_RULE) is held for review instead of being credited automatically.
             s.safety() reports them.

CLI
---
  python rcb_topogym.py make-instance --task cube_pick_place --eval-index 0 --out instance.json
  python rcb_topogym.py run-oracle    --task cube_pick_place --instance instance.json --code oracle.py --out traj.npz
  python rcb_topogym.py replay        --task cube_pick_place --instance instance.json --traj traj.npz [--repeat 2] [--video replay.mp4]
                                      # as the graders replay (Session.replay grading=True)
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
  s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end', 'review'}
  s.safety()                         # drive loads, contact depths, rope volume, table-guard stops since the last call, vs the limits
  s.replay(actions)                  # resets, replays open-loop, returns status -> self-check
  s.replay(actions, grading=True)    # as the graders replay: GPU families hold up to 2 s, then replay tolerances
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
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np


class InvalidTrajectory(ValueError):
    """Malformed agent submission; distinct from simulator and host I/O errors."""


class InstanceMismatch(RuntimeError):
    """The frozen instance could not be reconstructed within its contract."""


def atomic_json(path, value):
    """Durably publish a single authoritative JSON record on the same filesystem."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def recover_reward(directory):
    """Verifier parent only, after the agent artifacts have been cleared."""
    path = Path(directory) / "verdict.json"
    if not path.is_file():
        return False
    verdict = json.loads(path.read_text())
    reward = verdict["reward"]
    if verdict.get("schema_version") != 2 or reward.get("success") not in (0, 1):
        raise ValueError("invalid committed verdict")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in reward.values()):
        raise ValueError("Harbor rewards must be finite numeric fields")
    atomic_json(Path(directory) / "reward.json", reward)
    atomic_json(Path(directory) / "reward.txt", reward["success"])
    return True


def load_trajectory(path, task, dim, *, trusted=False, layout=None):
    """Validate before scene creation. Tick metadata is accepted only from the trusted service."""
    try:
        # Inspect the array header before NumPy allocates from an untrusted shape.
        with zipfile.ZipFile(path) as archive, archive.open("actions.npy") as stream:
            version = np.lib.format.read_magic(stream)
            if version == (1, 0):
                shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
            elif version == (2, 0):
                shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
            else:
                raise InvalidTrajectory("unsupported actions array format")
            if len(shape) != 2 or shape[1] != dim or not (0 if trusted else 1) <= shape[0] <= MAX_STEPS or dtype.kind not in 'fiu':
                raise InvalidTrajectory("invalid or oversized actions array header")
        with np.load(path, allow_pickle=False) as data:
            if str(data['task']) != task:
                raise InvalidTrajectory('wrong task family')
            if layout is not None and ('action_layout' not in data or data['action_layout'].tolist() != list(layout)):
                raise InvalidTrajectory('trajectory action layout differs from frozen instance')
            raw = data['actions']
            if raw.dtype.kind not in 'fiu' or raw.ndim != 2 or raw.shape[1] != dim or not (0 if trusted else 1) <= len(raw) <= MAX_STEPS:
                raise InvalidTrajectory('actions must be a nonempty bounded numeric (T, action_dim) array')
            with np.errstate(over='ignore', invalid='ignore'):
                actions = raw.astype(np.float32)
            if not np.isfinite(actions).all():
                raise InvalidTrajectory('actions contain nonfinite values')
            ticks = None
            if trusted:
                meta = json.loads(str(data['meta'])) if 'meta' in data else {}
                live = meta.get('live_rows', len(actions))
                if type(live) is not int or not 0 <= live <= len(actions):
                    raise InvalidTrajectory('invalid live_rows')
                actions = actions[:live]
                if 'physics_steps_per_action' in data:
                    ticks = data['physics_steps_per_action']
                    if ticks.dtype.kind not in 'iu' or ticks.ndim != 1 or len(ticks) != len(raw) or np.any(ticks <= 0):
                        raise InvalidTrajectory('invalid executed tick ledger')
                    ticks = ticks[:live].copy()
            return actions, ticks
    # ZIP raises NotImplementedError for unsupported compression/flags and
    # RuntimeError for encrypted entries. This boundary only parses the submitted
    # file; simulator construction and replay exceptions remain infrastructure errors.
    except (ValueError, TypeError, KeyError, EOFError, zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
        raise InvalidTrajectory(str(exc)) from exc

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


DEFAULT_BACKEND = "cuda"          # robot_coding_bench's GPU-backend rule (determinism reported, not required); the physics device is the instance's
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
        instances=[dict(variation_id="fiber_bundling_medium", seed=0)], grasp_assist="recommended"),
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
        # Resolve the handle region from the selected variant's shaft length.
        # Frozen instances retain their own simulator config, including legacy none.
        grasp_assist="recommended"),
    "orbits": dict(
        task_id="orbits", robot="aloha",
        text="Free the complete cord and wooden handle from the fixed ring-and-post assembly. Place the entire cord and "
             "handle inside the green dashed goal area and hold them still briefly. Keep the rings, posts and other fixed "
             "components outside the area on the puzzle/system side. Holding the target is allowed; placing only the "
             "handle in the area is not completion.",
        # Weld on any link for the rigid-chain tiers only; the FEM tiers' recommendation is none (tasks/orbits/common.py).
        instances=[dict(variation_id="orbits_reference85", seed=0)], grasp_assist="recommended"),
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
        # Weld on any link and on the ring for the rigid-chain settings only; the FEM tiers' recommendation is none
        # (tasks/slotted_post_ring/common.py).
        instances=[dict(variation_id="slotted_post_ring_hard", seed=0)], grasp_assist="recommended"),
}
for _name, _t in TASKS.items():
    _t.setdefault("simulator", {}); _t.setdefault("grasp_assist", None); _t.setdefault("fixture", False)
    _t.update(simulator_name="topogym", image="topogym")
# Tooling v7 (2026-10-02 speed study, robot_coding_bench jobs/journal/2026-10-02/rigid_fast/): these rigid families simulate
# on the CPU in float64 with one global constraint solve (use_contact_island False); Nyx still renders on the GPU. Against
# v6's GPU float32: 2-3x faster control steps, sims on one host do not slow each other, replays bit-deterministic on one
# host, outcomes / per-substep contact penetration / trajectory deviation inside the GPU's own noise envelope, frames
# identical. interlocked_claws spent v8 on the GPU in float32: in medium's friction-held phase some noise runs lose the teal
# piece on the CPU; the same seeds lose it on the GPU in float64 too, so that is float64 physics (Jianwen's original
# setting), which v6's float32 does not reproduce. The soft-body families stay GPU float64.
for _name in ("buzz_wire_3d", "cast_coil", "cast_keyhole", "fiber_bundling", "hedgehog_in_cage", "horseshoe_ring",
              "interlocked_claws"):
    TASKS[_name]["simulator"] = {**TASKS[_name]["simulator"], "compute_backend": "cpu", "precision": "64",
                                 "rigid_options": {"use_contact_island": False}}
# lock_picking keeps v6's GPU float32 (slower on the CPU).
TASKS["lock_picking"]["simulator"] = {**TASKS["lock_picking"]["simulator"], "precision": "32"}
# Tooling v9 (2026-10-02 IPC speed study, robot_coding_bench jobs/journal/2026-10-02/ipc_fast/): one IPC solver substep per
# 2.5 ms tick (was four) with Newton / PCG tolerances 1e-3 / 1e-5 (were 1e-4 / 1e-6), from a scene settled for N ticks
# before the instance is frozen (the v5 instances were not at rest at t = 0). Against substeps 4 from the same settled
# state: rope_threading 8.1x, slotted_post_ring 9.2x per control step (10.7x / 10.1x with libuipc's linear_bvh broad phase
# instead of its default info_stackless_bvh: the same contacts); lift / slip / drop within 0.1 mm, centerline 0.3-0.8 mm at
# the end of a pinch-lift-release, the same cord break (0.1 s later), frames identical.
# Since v10 the settled state is frozen with the instance (export-ipc-state, SimulatorConfig.ipc_settled_state) instead
# of settling at every build: every build starts from the same bits (settling on the GPU started builds ~0.04 um apart,
# enough for a near-threshold squeeze to take another contact branch) and skips 0.8-2.4 min of settling.
# Since v12 knot_untying (v10-v11: two substeps) and orbits (v11: four) also run one substep (the user's call,
# 2026-10-02): knot 7.4x, orbits 12-15x against substeps 4 (knot easy lift / slip / drop within 0.1 mm, frames identical;
# orbits' clear approach within 0.11 mm). Accepted leniency: the larger IPC dt cushions a violent impact, so the
# reference's noise-robust tet inversion (episode end rope_volume_invalid / connection_or_volume_invalid) on knot medium's
# closing pinch and on orbits' ~2 m/s open-finger sweep does not happen: such impacts no longer end the episode.
for _name, _ticks in (("rope_threading", 300), ("slotted_post_ring", 800), ("knot_untying", 600), ("orbits", 800)):
    TASKS[_name]["simulator"] = {**TASKS[_name]["simulator"], "solver_substeps": 1, "reset_physics_steps": _ticks,
                                 "ipc_options": {"newton_tolerance": 1e-3, "linear_system_tolerance": 1e-5,
                                                 "collision_detection_method": "linear_bvh"}}
# Tooling v18 (knot K2, 2026-10-05; lab topogym_v1/topospeed/NOTES.md): knot_untying's IPC frame is 5 ms (5 ticks per
# 25 ms control step, the control period unchanged) and its Newton solve semi-implicit with at least 3 iterations per frame
# (libuipc newton_semi_implicit_enable + newton_min_iterations). Its full Newton solve to 1e-3 at 2.5 ms spent 13-16
# iterations per frame. Rejected on the way (closed-loop oracles and open-loop screens, tet volume ratio per phase against
# the full solve): one semi-implicit iteration (crushes the rope under the fingers: medium and hard fail), a looser
# tolerance (5e-2 at 5 ms: inverted tets in the grasp squeeze). K2's oracles untie hard and medium with the rope geometry
# inside the full solve's envelope (no inverted tet; centerline distance, table gap, stretch alike). The settle keeps its
# 1.5 s (300 ticks of 5 ms). Rules windows and stable durations are time-based, so they keep their meaning.
TASKS["knot_untying"]["simulator"] = {
    **TASKS["knot_untying"]["simulator"], "physics_dt_s": 0.005, "control_decimation": 5, "reset_physics_steps": 300,
    "ipc_options": {**TASKS["knot_untying"]["simulator"]["ipc_options"], "newton_semi_implicit_enable": True,
                    "newton_min_iterations": 3}}


def simulator_config(task: str, eval_index: int | None = None, *, variation_id: str | None = None,
                     seed: int | None = None, task_parameters: dict | None = None,
                     simulator_overrides: dict | None = None) -> dict:
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
    # A variation can leave its family's IPC: Orbits very_easy / easier became a rigid link chain (2026-10-07). It then
    # takes the rigid families' CPU float64 solve with the family's one substep (the teammates' chain standard), no IPC
    # settings, and settles for 3 s (1200 ticks) before every build: the chain falls onto the table and its links
    # hanging from the handle stop swinging.
    if "ipc_options" in cfg:
        from topogym.config.registry import task_definition
        definition = task_definition(spec["task_id"], resolved["variation_id"])
        # Only Orbits very_easy / easier here; another tier leaving IPC brings its own settings.
        if definition.physics_model != "fem_ipc" and getattr(definition, "difficulty", "") in {"very_easy", "easier"}:
            cfg.pop("ipc_options")
            cfg.update(compute_backend="cpu", precision="64", rigid_options={"use_contact_island": False},
                       reset_physics_steps=1200)
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
    if simulator_overrides is not None:
        # Manager/build input only. Validated values are saved in the instance;
        # a loaded episode cannot accept these overrides.
        allowed = {"physics_dt_s", "solver_substeps", "control_decimation", "reset_physics_steps",
                   "rigid_options", "ipc_options", "ipc_settled_state", "grasp_assist"}
        if not isinstance(simulator_overrides, dict) or set(simulator_overrides) - allowed:
            raise ValueError(f"simulator_overrides permits only {sorted(allowed)}")
        cfg.update(simulator_overrides)
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
    """Action layout, measured state and stateless kinematics of the TopoGym robot (_ChainFK on a fixed qpos template).
    Every group ("arm" for the Panda, "left" / "right" for ALOHA) is one arm: its arm joints then its declared gripper target."""

    def __init__(self, robot, timing, *, gripper_space="width"):
        from topogym.robot.grasp_geometry import read_grasp_geometry
        if gripper_space not in {"width", "native"}:
            raise ValueError("gripper_space must be width or native")
        self.gripper_space = gripper_space
        self.robot, self.entity, self.timing = robot, robot.entity, timing
        self.groups = {g.name: g for g in robot.description.groups}
        self.arms = list(self.groups)
        # per arm the drive force clamp of its arm joints then its actuated fingers (N m / N); the torque caps lower it
        self.drive_force = {name: tuple(float(v) for v in g.force) for name, g in self.groups.items()}
        self.template = _np(self.entity.get_qpos()).reshape(-1).astype(np.float64).copy()
        self.joint = {j.name: j for j in self.entity.joints if len(j.qs_idx_local) == 1}
        self.layout, self.arm_slice, self.grip_index, self.limits = [], {}, {}, []
        for g in self.groups.values():
            first = len(self.layout)
            self.layout += list(g.arm_joints); self.limits += [list(map(float, l)) for l in g.arm_limits_rad]
            self.arm_slice[g.name] = slice(first, len(self.layout))
            self.grip_index[g.name] = len(self.layout)
            self.layout.append(f"{g.name}_native_gripper" if gripper_space == "native" else f"{g.name}_gripper")
            self.limits.append(None)
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
        for name, g in self.groups.items():
            cmds = np.linspace(g.grasp.open_position, g.grasp.closed_position, 33)
            widths = np.minimum.accumulate(np.array([self._nominal_opening(g, c) for c in cmds]))
            keep = np.r_[True, np.diff(widths) < -1e-7]
            self.width_table[name] = (widths[keep][::-1].copy(), cmds[keep][::-1].copy())    # increasing widths
            lo, hi = float(self.width_table[name][0][0]), float(self.width_table[name][0][-1])
            self.limits[self.grip_index[name]] = [round(max(0.0, lo), 6), round(hi, 6)]
            if gripper_space == "native":
                self.limits[self.grip_index[name]] = list(map(float, g.gripper_limits))
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

    def native_to_action(self, arm, native) -> float:
        """The frozen action layout declares whether the gripper column is a drive or a gap."""
        return float(native) if self.gripper_space == "native" else self.native_to_width(arm, native)

    def action_to_native(self, arm, value) -> float:
        return float(value) if self.gripper_space == "native" else self.width_to_native(arm, value)

    # -- actions
    @property
    def action_dim(self) -> int:
        return len(self.layout)

    def clip(self, row) -> np.ndarray:
        return np.clip(np.asarray(row, dtype=np.float64), self.lo, self.hi)

    def command(self, row) -> dict:
        row = np.asarray(row, dtype=np.float64)
        # Width is not injective at the closed-end plateau. A hold must keep
        # the accepted native target, including after reset/rewind and without
        # requiring targets() to have been called first. Do not cache proposals:
        # validate_action can reject them without changing the robot.
        targets = self.robot.capture_state().targets
        out = {}
        for name, g in self.groups.items():
            width = float(row[self.grip_index[name]])
            current = float(targets[name][g.gripper_field])
            native = (float(width) if self.gripper_space == "native" else
                      current if abs(width - self.native_to_width(name, current)) <= 1e-7
                      else self.width_to_native(name, width))
            out[name] = {"joint_position_rad": row[self.arm_slice[name]].tolist(),
                         g.gripper_field: native}
        return self.robot.validate_action(out)

    def targets(self) -> np.ndarray:
        t = self.robot.capture_state().targets
        row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            row[self.arm_slice[name]] = t[name]["joint_position_rad"]
            row[self.grip_index[name]] = self.native_to_action(name, t[name][g.gripper_field])
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
            row[self.grip_index[name]] = (q[self.joint[g.actuated_fingers[0]].qs_idx_local[0]]
                                          if self.gripper_space == "native" else self.opening(name))
        return row

    def velocities(self) -> np.ndarray:
        v = _np(self.entity.get_dofs_velocity()).reshape(-1).astype(np.float64); q = self.measured_full()
        row = np.zeros(self.action_dim)
        for name, g in self.groups.items():
            row[self.arm_slice[name]] = [v[self.joint[n].dofs_idx_local[0]] for n in g.arm_joints]
            fj = self.joint[g.actuated_fingers[0]]; nq = q[fj.qs_idx_local[0]]
            slope = (self.native_to_width(name, nq + 1e-4) - self.native_to_width(name, nq - 1e-4)) / 2e-4
            if self.gripper_space == "native":
                slope = 1.
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
                force = np.asarray(self.drive_force[name][:n])
                row[self.arm_slice[name]] = np.clip(e, -force, force)
        return row

    def tcp(self, arm) -> tuple[np.ndarray, np.ndarray]:
        m = self.robot.observe()[arm]
        return np.asarray(m["tcp_position_world_m"], dtype=np.float64), np.asarray(m["tcp_orientation_wxyz"], dtype=np.float64)

    # -- kinematics (stateless: a fixed qpos template, never the simulator's state). Genesis' own FK / IK queries run their
    # kernels on the live solver and leave links_state / joints_state changed in the last bits, so a live run that queried
    # kinematics stopped replaying bit for bit (lab BUG 7); _ChainFK is the same model in numpy and never touches the solver.
    def _fk_full(self, q_full) -> dict:
        if getattr(self, "_chain", None) is None:
            self._chain = _ChainFK(self.entity)
        out = self._chain(np.asarray(q_full, dtype=np.float64))
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


def _register_runtime_physics(margin: float) -> None:
    """The kernels this tooling replaces act on every scene of its process, the preparation of a generated frozen state
    included (topogym/world/physics/pbd_initial_state_generation.py), so they enter that state's recipe. An image without
    generated states has nothing to register."""
    try:
        from topogym.world.physics.pbd_initial_state_generation import register_runtime_physics
    except ImportError:
        return
    register_runtime_physics("rcb_topogym", dict(tooling_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        deterministic_gpu_physics=DETERMINISTIC_GPU_PHYSICS, rigid_solve_arm=RIGID_SOLVE_ARM,
        pbd_depenetration_margin_m_s=margin))


def _initial_state_record(env) -> dict | None:
    """Where the episode's frozen PBD birth state came from: the instance's stored archive, or one generated from the
    instance's recipe on this GPU because the stored one was prepared on another (resource profile). None: no such state."""
    report = getattr(env, "_initial_state_report", None) or {}
    if "manifest_sha256" not in report:
        return None
    generated = report.get("generated")
    if not generated:
        return {"source": "stored", "manifest_sha256": report["manifest_sha256"]}
    keys = ("manifest_sha256", "state_sha256", "recipe_sha256", "recipe_match", "resource_profile", "stored_profile",
            "stored_manifest_sha256", "cache", "preparation_wall_s", "ensure_wall_s")
    return {"source": "generated", **{k: generated.get(k) for k in keys}}


def _drop_fem_gradient_checkpoints(env) -> bool:
    """Active FEM solvers only (tooling v4): bound Genesis 1.2.1's per-substep FEM checkpoint store.

    Simulator.save_ckpt runs after every substep when requires_grad is False (substeps_local = 1), and FEMSolver.save_ckpt
    (genesis/engine/solvers/fem_solver.py:1058), unlike RigidSolver's, has no requires_grad guard: each call stores the FEM
    state in three new CUDA tensors (pos, vel, active) under a new name and never frees them. With 40 substeps per control
    step that is ~120 MiB per control step for knot hard's rope: a 16 GB GPU runs out of memory after ~72 control steps
    (limited trial tWKp7yB, 2026-10-01; libuipc then aborts) and shared lab GPUs fill up. The override runs Genesis' own
    save_ckpt unchanged (the same kernels, the same forward frame roll) and then deletes every older checkpoint, so memory
    stays at one checkpoint. Nothing reads the older ones: FEMSolver.load_ckpt (the backward pass, requires_grad only) is
    their only reader, and TopoGym's state graph skips _ckpt. Returns True when installed; a no-op without an active FEM
    solver or with gradients enabled."""
    sim = env._world.scene.sim
    fem = getattr(sim, "fem_solver", None)
    if fem is None or not fem.is_active or sim.requires_grad:
        return False
    if getattr(fem.save_ckpt, "_topogym_bounded", False):
        return True
    upstream = fem.save_ckpt

    def save_ckpt(ckpt_name, _fem=fem, _upstream=upstream):
        _upstream(ckpt_name)
        for key in [k for k in _fem._ckpt if k != ckpt_name]:
            del _fem._ckpt[key]
    save_ckpt._topogym_bounded = True
    fem.save_ckpt = save_ckpt
    return True


def _vectorized_planar_clearance(points, material_s, diameter):
    """knot_untying's per-tick predicate topogym.utils.geometry.passage.planar_clearance (Jianwen's 76583213), vectorized:
    the same validation (passage.points3), degenerate checks, pair set (segments i < j-1), intersection test, point-segment
    distances, early 'an intersection anywhere -> (False, minimum 0.0)' and non-local filter s[j] - s[i+1] >= 2 * diameter.
    The original loops over ~93k segment pairs in Python (~3.4 s per tick on knot, ~2/3 of a hold step); this returns the
    same bool and the same minimum (IPC-perf agent 2026-10-01: 40 / 40 test curves bit-identical; build78: checked against
    the original on live knot states)."""
    from topogym.utils.geometry import passage
    p = passage.points3(points)
    s = np.asarray(material_s, float)
    if len(p) < 2 or s.shape != (len(p),) or not np.isfinite(s).all() or np.any(np.diff(s) <= 0) or not np.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid planar rope/material coordinates")
    if np.any(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1) < 1e-9):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=None)
    edges = np.diff(p[:, :2], axis=0)
    a, b = edges[:-1], edges[1:]
    cross = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    fold = (np.abs(cross) <= 1e-12 * np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)) & (np.einsum("ij,ij->i", a, b) < 0)
    if np.any(fold):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=0.)
    m = len(p) - 1
    I, J = np.triu_indices(m, k=2)
    if not len(I):
        return True, dict(projected_degenerate=False, minimum_nonlocal_distance_m=None)
    q = p[:, :2]
    A, B, C, D = q[I], q[I + 1], q[J], q[J + 1]
    U, V = B - A, D - C

    def cr(x, y):
        return x[:, 0] * y[:, 1] - x[:, 1] * y[:, 0]
    den = cr(U, V)
    CA = C - A
    with np.errstate(divide="ignore", invalid="ignore"):
        t = cr(CA, V) / den
        u = cr(CA, U) / den
    hit = (np.abs(den) > 1e-15) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)

    def point_segment(P, X, Y):
        E = Y - X
        tt = np.clip(np.einsum("ij,ij->i", P - X, E) / np.maximum(np.einsum("ij,ij->i", E, E), 1e-30), 0, 1)
        return np.linalg.norm(P - (X + tt[:, None] * E), axis=1)
    dist = np.minimum.reduce([point_segment(A, C, D), point_segment(B, C, D), point_segment(C, A, B), point_segment(D, A, B)])
    dist = np.where(hit, 0., dist)
    if np.any(dist < 1e-10):
        return False, dict(projected_degenerate=False, minimum_nonlocal_distance_m=0.)
    nonlocal_ = (s[J] - s[I + 1]) >= 2 * diameter
    minimum = float(dist[nonlocal_].min()) if np.any(nonlocal_) else None
    return minimum is None or minimum >= diameter, dict(projected_degenerate=False, minimum_nonlocal_distance_m=minimum)


def _tree_planar_clearance(points, material_s, diameter):
    """_vectorized_planar_clearance on the segment pairs that can matter (tooling v9; 2026-10-02 IPC study: the vectorized
    form tests all ~300k pairs of the 770-station knot centerline, 0.25 s per tick). A k-d tree on the segment midpoints
    yields the pairs within R + Lmax (Lmax = the longest segment), which include every pair at segment distance <= R; the
    same per-pair arithmetic runs on those only. 'Any pair closer than 1e-10' uses R = 1e-10; the non-local minimum doubles R
    from 2 diameters until a non-local candidate lies within R (or R spans the curve), so it is the global minimum. Same bool
    and same minimum (scripts/check_knot_clearance.py; a full knot run: 770 of 770 calls identical)."""
    from scipy.spatial import cKDTree
    from topogym.utils.geometry import passage
    p = passage.points3(points)
    s = np.asarray(material_s, float)
    if len(p) < 2 or s.shape != (len(p),) or not np.isfinite(s).all() or np.any(np.diff(s) <= 0) or not np.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid planar rope/material coordinates")
    if np.any(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1) < 1e-9):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=None)
    edges = np.diff(p[:, :2], axis=0)
    a, b = edges[:-1], edges[1:]
    cross = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    fold = (np.abs(cross) <= 1e-12 * np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)) & (np.einsum("ij,ij->i", a, b) < 0)
    if np.any(fold):
        return False, dict(projected_degenerate=True, minimum_nonlocal_distance_m=0.)
    m = len(p) - 1
    if m < 3:
        return True, dict(projected_degenerate=False, minimum_nonlocal_distance_m=None)
    q = p[:, :2]
    longest = float(np.linalg.norm(edges, axis=1).max())
    tree = cKDTree(0.5 * (q[:-1] + q[1:]))

    def cr(x, y):
        return x[:, 0] * y[:, 1] - x[:, 1] * y[:, 0]

    def point_segment(P, X, Y):
        E = Y - X
        tt = np.clip(np.einsum("ij,ij->i", P - X, E) / np.maximum(np.einsum("ij,ij->i", E, E), 1e-30), 0, 1)
        return np.linalg.norm(P - (X + tt[:, None] * E), axis=1)

    def distances(I, J):
        A, B, C, D = q[I], q[I + 1], q[J], q[J + 1]
        U, V = B - A, D - C
        den = cr(U, V)
        CA = C - A
        with np.errstate(divide="ignore", invalid="ignore"):
            t = cr(CA, V) / den
            u = cr(CA, U) / den
        hit = (np.abs(den) > 1e-15) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
        dist = np.minimum.reduce([point_segment(A, C, D), point_segment(B, C, D), point_segment(C, A, B), point_segment(D, A, B)])
        return np.where(hit, 0., dist)

    def candidates(radius):
        pairs = tree.query_pairs(r=radius + longest, output_type="ndarray")
        if not len(pairs):
            return np.zeros(0, int), np.zeros(0, int)
        I, J = pairs.min(axis=1), pairs.max(axis=1)
        keep = J >= I + 2
        return I[keep], J[keep]

    I, J = candidates(1e-10)
    if len(I) and np.any(distances(I, J) < 1e-10):
        return False, dict(projected_degenerate=False, minimum_nonlocal_distance_m=0.)
    radius, span = 2.0 * diameter, float(np.linalg.norm(q.max(0) - q.min(0)))
    while True:
        I, J = candidates(radius)
        nonlocal_ = (s[J] - s[I + 1]) >= 2 * diameter
        if np.any(nonlocal_):
            minimum = float(distances(I[nonlocal_], J[nonlocal_]).min())
            if minimum <= radius or radius >= span:
                break
        elif radius >= span:
            minimum = None
            break
        radius *= 2.0
    return minimum is None or minimum >= diameter, dict(projected_degenerate=False, minimum_nonlocal_distance_m=minimum)


def _speed_up_knot_predicate(task_id: str) -> bool:
    """knot_untying only: its task module calls the k-d tree planar_clearance (same results; the vectorized form ~100x
    faster than the original loop, this one 1.2 vs 56.6 ms per call on a 770-station curve)."""
    if task_id != "knot_untying":
        return False
    import topogym.tasks.knot_untying.common as knot
    knot.planar_clearance = _tree_planar_clearance
    return True


# --------------------------------------------------------------------------- physical-validity policy (tooling v16)
# The 2026-10-03 rules audit (robot_coding_bench jobs/journal/2026-10-03/rules_audit/AUDIT.md: every finished v12 failure
# classified, nine trajectories replayed) found TopoGym's any-tick 1 mm contact limit and its any-tick tet-inversion rule
# without margin; v14's replacement (R1: a rigid task contact deeper than 3 mm, or deeper than 1 mm for 0.25 s, failed the
# episode) still ended passive impacts: v14 standard trial QKSrtdL (interlocked_claws hard) had opened both grippers and
# held every joint target when the released claw landed on the other one, 4.6 mm deep for 3 ticks at 42 N. Penetration
# depth measures the contact solver, not the agent. The user's general policy (2026-10-03 ~21:30) separates who caused
# what, with no per-artifact exceptions. Installed per Session by _install_rules, like the fast paths above: TopoGym's
# files are not edited, and everything is installed after Env.reset recorded the frozen first checkpoint (the t = 0 state
# and its hash do not change).
#  Layer 0, the environment model, the task owner's (Jianwen's release profile, topogym/tasks/release_profile.py, frozen in
#     the instance and stated in the texts): materials, solver settings and timing, grasp assistance, which robot links
#     collide with soft bodies (merged-v16 rope_threading: the fingers only). Live episode and every replay alike; this
#     policy never changes it.
#  Layer 1, guards: arm drive torque caps (ARM_TORQUE_CAPS_NM: the PD force clamp of the arm joints; the gripper drives are
#     unchanged); a fingertip-table guard on every control step (_TableGuard); the standard service's joint-speed limit
#     and IK-jump refusal (JOINT_STEP_LIMIT_RAD, IK_JUMP_LIMIT_RAD, environment/sim/server.py).
#  Layer 2, the task's own stated rules, the task owner's: its success predicate, strict live (thresholds, confirmation
#     windows, release conditions such as knot_untying's terminal v5: 1 mm from every robot part that can move, world-fixed
#     bases may touch, an overlap with any robot part's interior withholds success and never ends the episode), and the
#     failures the agent caused, which end the episode (wire / fiber touch, rotor limit, chain link, a body or the cloth
#     fallen, and this tooling's R2: a soft-body tet inversion, or a cord attachment stretched by more than 2 mm, persisting
#     for 0.25 s; while shorter the evidence reads as unavailable: no success credit, no failure).
#  Layer 3, simulator breakdown (ends the episode): a non-finite rigid state, a cloth particle faster than
#     PARTICLE_SPEED_LIMIT_M_S, an invalid native soft-body solver state, a rigid task contact deeper than
#     BREAKDOWN_PENETRATION_M -> SIMULATOR_INSTABILITY (an infrastructure error, evidence in Session.instability), unless
#     the forcing condition (below) held on any tick of the FORCING["attribution_s"] before (or at) it: then the agent's
#     "forced_breakdown: <what broke> <while which arm forced what>".
#  Layer 4, evidence only, never an episode end:
#     - FORCING, every family: an arm drive (not a gripper drive) at FORCING["near_cap"] of its torque cap or more while
#       that arm, or a movable body it holds (both fingers touching it, or an assisted-grasp binding), presses on anything
#       else with FORCING["contact_n"] or more in total. A run of it on every physics tick for FORCING["event_s"] is a
#       forcing event (_SafetyMonitor.forcing: arm, drive, % of cap, what it pressed on, how hard, how long). It does not
#       hold a success by itself (the user, 2026-10-04 ~01:10: as an episode end it stopped the claws easy standard
#       success oDonuzB, 2.2 s of forcing; the reference oracle forces for 0.33 s; and the exploit the rules exist for, the
#       pieces pulled through each other, took 3 ticks: only its depth showed it). Shown with a held success's evidence.
#     - every tick's deepest non-held and held-finger task contact (Session.safety(), the service's meta["safety"]). A tick
#       deeper than CONTACT_RULE's deep limits, or a contact above its sustained limits for its window, is a review event
#       (_SafetyMonitor.review): a success whose episode or replay had one is held for review by the graders (success 0,
#       success_pending_review 1, the events, the forcing events, and frames around both); a clean success is credited.
#  The counters (R2, the forcing that attributes a breakdown, the review contacts' persistence) live in the task's own
#  history (task_state[_RULES_KEY], absent while all are zero), so reset and rewind restore them with the rest of the task
#  state.
RULES_REVISION = "rules_2026-10-03b"
CONTACT_RULE = dict(deep_m=.003, sustained_m=.001, held_deep_m=.004, held_sustained_m=.002, window_s=.25)   # review events
SOFT_RULE = dict(window_s=.25, residual_m=.002)
# Measured on lab 2026-10-03 (docs/rcb/benchmarks/topogym.md, "Physical-validity policy"): a drive at its cap reads
# 0.99-1.00 and a working arm well below (free-air saturation: wrist wraps at 0.99 with 1 N of contact); 20 N excludes
# light touches and resting parts; event_s 0.5 s: interlocked_claws easy's reference oracle holds the condition for 0.33 s
# (131 ticks), the scripted sustained forcing for 1.1 s and more. attribution_s: a breakdown within it is the agent's.
FORCING = dict(near_cap=.95, contact_n=20., event_s=.5, attribution_s=.25)
BREAKDOWN_PENETRATION_M = .010
FORCED_BREAKDOWN = "forced_breakdown"
# N m per arm joint, in arm-joint order; the effective cap is min(this, the model's own force limit: ALOHA 35 / 144 / 59 /
# 22 / 35 / 35, Panda 87 x 4 / 12 x 3). The audit proposed the real ViperX actuators (12.9 / 25.8 / 25.8 / 12.9 / 12.9 /
# 4.8: XM540 stall torque, doubled on the dual-servo shoulder and elbow; XM430 on the wrist rotate). On lab (2026-10-03
# rules fix, NOTES) those break the validated ipc_fast rope pinch (no lift; knot 10.5 instead of 17.8 mm): its six-step
# approach (0.245 rad per control step) needs 73-77 N m on the shoulder, 45 on the elbow, the model's full 35 on the
# wrist angle and 14.3 on the wrist rotate, and lags 185 mm at the proposal (60 / 45 still 30 mm). With these the knot and
# rope pinches lift as with the uncapped arm and the rope keeps a positive tet volume (a wrist rotate cap of 9.6 turned the
# rope's lift into a 0.24 s tet inversion), and every other validated reference still succeeds; the waist and forearm roll
# keep the real-actuator caps. Panda: 50 on joints 1-4 (the cube oracle succeeds; a stiff-PD transient at the start of
# each fast step is the only binding).
ARM_TORQUE_CAPS_NM = {"aloha": (12.9, 80., 59., 12.9, 35., 17.5), "panda_robotiq": (50., 50., 50., 50., 12., 12., 12.)}
# No gripper vertex (fingers, housing) is commanded lower than the tabletop + this. Negative: below the tabletop. The
# audit proposed + 2 mm; on lab that broke two validated references (2026-10-03 rules fix, NOTES): the ipc_fast knot / rope
# pinch (its closed-loop servo commands the fingertips 0-12 mm below their +1.8 mm contact pose to cancel the arm's lag;
# + 2 mm and 0 mm both stopped it) and the cast_keyhole easier / very_easy oracles (their servo integrates up to 12 mm
# below a +1.0-1.5 mm pregrasp; stopped at + 2 mm or 0 mm it never converges). - 15 mm keeps those envelopes and still
# stops the gross below-table targets of the v12 failures (an IK swing to -245 mm, -80 mm, -41 mm).
TABLE_GUARD_MARGIN_M = -.015
IK_JUMP_LIMIT_RAD = .5           # standard service: an ee_pose row whose IK solution is farther from the measured joints is refused
JOINT_STEP_LIMIT_RAD = .04       # standard service: joint_position targets move at most this per control step (as ee_pose rows)
_RULES_KEY = "rcb_rules"


def table_guard_words() -> str:
    """The guard's limit in words ('15 mm below the tabletop'), for texts and feedback: no target goes lower than it."""
    mm = abs(TABLE_GUARD_MARGIN_M) * 1000
    return ("the tabletop" if mm == 0 else f"{mm:g} mm below the tabletop" if TABLE_GUARD_MARGIN_M < 0 else
            f"{mm:g} mm above the tabletop")


def rule_window_ticks(physics_dt_s: float, window_s: float) -> int:
    """First whole tick reaching the window; never fail before its duration."""
    return max(1, int(math.ceil(float(window_s) / float(physics_dt_s) - 1e-12)))


def contact_rule_tick(counts: dict, nonheld_m: float, held_m: float, window: int, rule: dict = CONTACT_RULE):
    """R1 for one physics tick: `counts` = consecutive ticks above the sustained limits so far ({"over", "held_over"},
    absent = 0); nonheld_m / held_m = this tick's deepest non-held task contact and held-finger contact. Returns the new
    counts (zeros dropped) and the verdict: None, "deep", "held_deep", "sustained" or "held_sustained"."""
    over = int(counts.get("over", 0)) + 1 if nonheld_m > rule["sustained_m"] else 0
    held_over = int(counts.get("held_over", 0)) + 1 if held_m > rule["held_sustained_m"] else 0
    verdict = ("deep" if nonheld_m > rule["deep_m"] else "held_deep" if held_m > rule["held_deep_m"] else
               "sustained" if over >= window else "held_sustained" if held_over >= window else None)
    return {k: v for k, v in (("over", over), ("held_over", held_over)) if v}, verdict


def soft_rule_tick(counts: dict, ratios: dict, residuals: dict, residual_m: float = SOFT_RULE["residual_m"]) -> dict:
    """R2 for one physics tick: per soft entity the consecutive ticks with an inverted tet (worst volume ratio <= 0), per
    attachment the consecutive ticks stretched beyond residual_m. Non-finite diagnostics are left to TopoGym's own check
    (it raises). Zeros are dropped."""
    inverted, stretched = counts.get("inverted", {}), counts.get("stretched", {})
    out = {"inverted": {n: int(inverted.get(n, 0)) + 1 for n, r in ratios.items() if math.isfinite(r) and r <= 0},
           "stretched": {n: int(stretched.get(n, 0)) + 1 for n, v in residuals.items() if math.isfinite(v) and v > residual_m}}
    return {k: v for k, v in out.items() if v}


def _validate_rules_history(value) -> None:
    ok = isinstance(value, dict) and not set(value) - {"contact", "soft", "forced"}
    contact, soft, forced = (value.get("contact", {}), value.get("soft", {}), value.get("forced", 1)) if ok else ({}, {}, 1)
    ok = (ok and isinstance(contact, dict) and isinstance(soft, dict) and not set(contact) - {"over", "held_over"}
          and not set(soft) - {"inverted", "stretched"} and type(forced) is int and forced >= 1)
    counters = [contact] + [soft.get(k, {}) for k in ("inverted", "stretched")] if ok else []
    if (not ok or not all(isinstance(c, dict) for c in counters)
            or any(type(v) is not int or v < 1 for c in counters for v in c.values())):
        raise ValueError("Invalid rules history")


class _ArmLoads:
    """The forcing condition's contact measure: per arm, the total contact force between its own bodies (its robot links:
    ALOHA's '<arm>/...' links, every link of a one-arm robot; plus each movable non-robot link it holds at this tick: both
    of its fingers touching it, or its assisted-grasp binding) and everything else, from the tick's rigid contacts
    (touching ones: penetration >= 0). A held part pressed on its partner, a gripper rammed into a piece or the table, two
    arms pulling one part apart (the other arm's fingers press on the part one arm holds) all count; an arm's own grip on
    the part it holds does not."""

    def __init__(self, session):
        r, ent = session.robot, session.robot.entity
        self.arms = list(r.arms)
        by_name = {link.name: int(link.idx) for link in ent.links}
        self.own = {arm: set() for arm in self.arms}
        for link in ent.links:
            prefix = link.name.split("/")[0] if "/" in link.name else ""
            arm = prefix if prefix in self.own else (self.arms[0] if len(self.arms) == 1 else None)
            if arm is not None:
                self.own[arm].add(int(link.idx))
        self.fingers = {arm: [by_name[n] for n in g.grasp.finger_links] for arm, g in r.groups.items()
                        if g.grasp is not None and all(n in by_name for n in g.grasp.finger_links)}
        robot = set(by_name.values())
        self.movable = set()
        for e in session.env._world.entities.values():
            if getattr(e, "n_dofs", 0) and getattr(e, "links", None):
                self.movable |= {int(link.idx) for link in e.links} - robot

    def held(self, la, lb, touching, grasp) -> dict:
        hands, out = (grasp or {}).get("hands", {}) or {}, {}
        for arm in self.arms:
            fingers, sel = self.fingers.get(arm, ()), set()
            if len(fingers) == 2:
                a, b = ({*lb[touching & (la == f)].tolist(), *la[touching & (lb == f)].tolist()} for f in fingers)
                sel = a & b & self.movable
            binding = (hands.get(arm) or {}).get("binding")
            if binding and len(binding.get("links", ())) == 2 and int(binding["links"][1]) in self.movable:
                sel.add(int(binding["links"][1]))
            out[arm] = sel
        return out

    def __call__(self, contacts, grasp) -> dict:
        """-> {arm: (total force N, own link, partner link of its largest contact)}; (0., None, None) without contact."""
        out = {arm: (0., None, None) for arm in self.arms}
        if not contacts or not len(np.asarray(contacts.get("penetration", ()))):
            return out
        la = np.asarray(contacts["link_a"]).reshape(-1).astype(np.int64)
        lb = np.asarray(contacts["link_b"]).reshape(-1).astype(np.int64)
        pen = np.asarray(contacts["penetration"], dtype=np.float64).reshape(-1)
        force = np.linalg.norm(np.asarray(contacts["force"], dtype=np.float64).reshape(-1, 3), axis=1)
        touching = np.isfinite(pen) & (pen >= 0) & np.isfinite(force)
        held = self.held(la, lb, touching, grasp)
        for arm in self.arms:
            own = np.fromiter(self.own[arm] | held[arm], dtype=np.int64)
            ia, ib = np.isin(la, own), np.isin(lb, own)
            m = touching & (ia ^ ib)
            if m.any():
                k = int(np.flatnonzero(m)[int(np.argmax(force[m]))])
                out[arm] = (float(force[m].sum()), int(la[k] if ia[k] else lb[k]), int(lb[k] if ia[k] else la[k]))
        return out


_IPC_INTEGRITY: list = []       # TopoGym's own topogym.evaluation.task_metrics.ipc_integrity (set once)
_SOFT_CONTEXT: dict = {}        # the tick being evaluated by an R2 task: {"state", "counts", "window"}


def _ipc_integrity_rules(state, soft_names, attachment_names=(), residual_limit=.002):
    """topogym.evaluation.task_metrics.ipc_integrity with R2's persistence: TopoGym's function runs first (its validation
    and verdicts are unchanged); a False caused only by tet inversions or stretched attachments that have not yet
    persisted for the window becomes None (unavailable: no success, no failure). An invalid native state, an inconsistent
    diagnostic, or a state no R2 task is evaluating keeps TopoGym's verdict."""
    verdict = _IPC_INTEGRITY[0](state, soft_names, attachment_names, residual_limit)
    ctx = _SOFT_CONTEXT
    if verdict is not False or not ctx or ctx["state"] is not state:
        return verdict
    ipc = state["ipc"]
    if not ipc["native_valid"]:
        return False
    counts, ages = ctx["counts"], []
    for name in soft_names:
        lo, hi = (float(ipc["volume_ratio"][name][k]) for k in ("minimum", "maximum"))
        if hi < lo:
            return False
        if lo <= 0:
            ages.append(counts.get("inverted", {}).get(name, 0))
    for name in attachment_names:
        if float(ipc["attachment_residual_m"][name]) > residual_limit:
            ages.append(counts.get("stretched", {}).get(name, 0))
    return False if not ages or max(ages) >= ctx["window"] else None


def _patch_ipc_integrity(task) -> None:
    """Route TopoGym's ipc_integrity through _ipc_integrity_rules: the task_metrics module global (placement_candidate,
    placement.py) and every module of the task's class hierarchy that imported it by name."""
    import topogym.evaluation.task_metrics as metrics
    if not _IPC_INTEGRITY:
        _IPC_INTEGRITY.append(metrics.ipc_integrity)
    metrics.ipc_integrity = _ipc_integrity_rules
    for cls in type(task).__mro__:
        module = sys.modules.get(cls.__module__)
        if module is not None and getattr(module, "ipc_integrity", None) is _IPC_INTEGRITY[0]:
            module.ipc_integrity = _ipc_integrity_rules


def _rigid_measurements_rules(self, state):
    """RigidTaskDefinition.rigid_measurements (topogym/tasks/base.py) with the same poses, bounds, quiet flag and failures
    (a non-finite state, a body more than 100 mm below the table) and the same contact sets (held = topogym.utils.grasp
    .held_finger_contact_mask over every contact sample of the tick), but without the any-tick penetration verdict: this
    tick's deepest non-held and held task contacts go to self._rcb_contact for R1 (_install_rules)."""
    from scipy.spatial.transform import Rotation
    from topogym.utils.grasp import held_finger_contact_mask
    poses, bounds, quiet = {}, {}, True
    for name, vertices in self.local_vertices.items():
        body = state["bodies"][name]
        position = np.asarray(body["position_m"], dtype=float)
        quaternion = np.asarray(body["quaternion_wxyz"], dtype=float)
        velocity = np.asarray(body["linear_velocity_m_s"], dtype=float)
        angular = np.asarray(body["angular_velocity_rad_s"], dtype=float)
        if not np.isfinite(np.r_[position, quaternion, velocity, angular]).all():
            return {}, {}, False, "Non-finite physical state"
        rotation = Rotation.from_quat(quaternion[[1, 2, 3, 0]])
        points = rotation.apply(vertices) + position
        if points[:, 2].min() < self.table_height_m - .1:
            return {}, {}, False, "A task body fell below the table"
        poses[name] = (position, rotation)
        bounds[name] = (points.min(axis=0), points.max(axis=0))
        quiet = quiet and np.linalg.norm(velocity) < .001 and np.linalg.norm(angular) < .02
    contact_states = [dict(contacts=state.get("contacts"), grasp=state.get("grasp"))]
    if state.get("terminal_contract_version", 1) == 2:
        events = state.get("contact_events") or {}
        if not events.get("substeps_complete") or not events.get("contact_snapshots"):
            raise RuntimeError("terminal contract 2 requires complete rigid substep contact coverage")
        contact_states = events["contact_snapshots"]
    worst = {"nonheld": (0., None, 0.), "held": (0., None, 0.)}
    for sample in contact_states:
        contacts = sample["contacts"]
        if contacts is None:
            continue
        a, b = np.asarray(contacts["link_a"]), np.asarray(contacts["link_b"])
        involved = np.isin(a, list(self._task_link_indices)) | np.isin(b, list(self._task_link_indices))
        penetration = np.asarray(contacts["penetration"])
        held = held_finger_contact_mask(contacts, self._finger_links_by_hand, self._movable_task_link_indices,
                                        sample.get("grasp"))
        for key, mask in (("nonheld", involved & ~held), ("held", involved & held)):
            depth = float(penetration[mask].max(initial=0.))
            if math.isfinite(depth) and depth > worst[key][0]:          # NaN: no verdict, as TopoGym's comparison
                i = int(np.flatnonzero(mask & (penetration == depth))[0])
                force = contacts.get("force")
                force = float(np.linalg.norm(np.asarray(force)[i])) if force is not None else 0.
                worst[key] = (depth, (int(a[i]), int(b[i])), force)
    self._rcb_contact = worst
    return poses, bounds, bool(quiet), None


SOFT_FAILURES = ("rope_volume_invalid", "connection_or_volume_invalid")


def _install_rules(session) -> dict:
    """The physical-validity policy for this Session (see the block comment above): every family gets the forcing
    evidence and the breakdown attribution; the rigid task families the review contacts and the extreme-penetration bound;
    the IPC families R2. Returns the installed parameters (Session.rules)."""
    from types import MethodType
    task = session.env._task
    dt = float(session.env.config.physics_dt_s)
    session.torque_caps = _install_torque_caps(session)
    session.monitor = _SafetyMonitor(session)
    session.table_guard = _TableGuard(session)
    session.last_guard = None
    session.last_forcing = None          # the latest tick of the forcing condition: what a breakdown is blamed on

    def on_lifecycle(event):
        if event["kind"] == "rewind":
            # A rewind (reset) restores the checkpoint's engine buffers, Genesis' force ranges included (recorded
            # before the caps): apply them again before the next physics step.
            _apply_torque_caps(session)
            session.monitor.reset()
            session.last_forcing = None
    session.env.add_lifecycle_sink(on_lifecycle)
    contact = hasattr(task, "rigid_measurements")
    soft = getattr(task, "physics_model", "") == "fem_ipc"
    event = rule_window_ticks(dt, FORCING["event_s"])
    attribution = rule_window_ticks(dt, FORCING["attribution_s"])
    rules = {"revision": RULES_REVISION, "torque_caps_nm": session.torque_caps,
             "table_guard_margin_m": TABLE_GUARD_MARGIN_M if session.table_guard.limit is not None else None,
             "forcing": dict(FORCING, event_ticks=event, attribution_ticks=attribution),
             "breakdown_penetration_m": BREAKDOWN_PENETRATION_M if contact else None,
             "contact": dict(CONTACT_RULE, window_ticks=rule_window_ticks(dt, CONTACT_RULE["window_s"])) if contact else None,
             "soft": dict(SOFT_RULE, window_ticks=rule_window_ticks(dt, SOFT_RULE["window_s"])) if soft else None}
    words = _link_words(session)
    loads = _ArmLoads(session)
    caps = {arm: np.asarray(session.robot.drive_force[arm][:len(session.robot.groups[arm].arm_joints)], dtype=np.float64)
            for arm in loads.arms}
    if contact:
        task._rcb_contact = None
        task.rigid_measurements = MethodType(_rigid_measurements_rules, task)
    if soft:
        _patch_ipc_integrity(task)
    original_transition, original_validate = task.evaluate_transition, task.validate_task_state
    depth = [0]

    def validate_task_state(self, state):
        if isinstance(state, dict) and _RULES_KEY in state:
            _validate_rules_history(state[_RULES_KEY])
            state = {k: v for k, v in state.items() if k != _RULES_KEY}
        return original_validate(state)

    def pressing_at(state) -> dict:
        """arm -> its load at this tick, for the arms pressing with at least FORCING["contact_n"]; "forcing" = the
        forcing condition (an arm drive at FORCING["near_cap"] of its cap or more). The drive forces are read only when
        an arm presses."""
        tick = loads(state.get("contacts"), state.get("grasp")) if loads.arms else {}
        pressing = {arm: v for arm, v in tick.items() if v[0] >= FORCING["contact_n"]}
        if not pressing:
            return {}
        effort, out = np.abs(session.robot.efforts()), {}
        for arm, (force, own_link, partner) in pressing.items():
            frac = effort[session.robot.arm_slice[arm]] / caps[arm]
            j = int(np.argmax(frac))
            out[arm] = dict(joint=session.robot.groups[arm].arm_joints[j], fraction=float(frac[j]), cap_nm=float(caps[arm][j]),
                            force_n=force, own=own_link, partner=partner, held=own_link not in loads.own[arm],
                            physics_step=int(state.get("physics_step", -1)), forcing=bool(frac[j] >= FORCING["near_cap"]))
        return out

    def evaluate_transition(self, state, private):
        mine = dict(private.get(_RULES_KEY) or {}) if isinstance(private, dict) else {}
        own = {k: v for k, v in private.items() if k != _RULES_KEY} if isinstance(private, dict) else private
        if depth[0]:                     # a family's own nested call (evaluate_state -> evaluate_transition): plain
            return original_transition(state, own)
        soft_counts, ipc = mine.get("soft", {}), state.get("ipc") or {}
        if soft and ipc and "native_valid" in ipc:
            ratios = {k: float(v["minimum"]) for k, v in (ipc.get("volume_ratio") or {}).items()}
            residuals = {k: float(v) for k, v in (ipc.get("attachment_residual_m") or {}).items()}
            soft_counts = soft_rule_tick(soft_counts, ratios, residuals)
            _SOFT_CONTEXT.update(state=state, counts=soft_counts, window=rules["soft"]["window_ticks"])
            session.monitor.soft(ratios, residuals, soft_counts)
        self._rcb_contact = None
        depth[0] += 1
        try:
            reached, failure, metrics, private = original_transition(state, own)
        finally:
            depth[0] -= 1
            _SOFT_CONTEXT.clear()
        # Layer 4 (evidence): forcing; its condition also attributes a breakdown within the window after it (Layer 3)
        pressing = pressing_at(state)
        forcing = {arm: v for arm, v in pressing.items() if v["forcing"]}
        forced_left = int(mine.get("forced", 0))
        forced_recent = bool(forcing) or forced_left > 0
        forced_left = attribution if forcing else max(0, forced_left - 1)
        if forcing:
            session.last_forcing = max(forcing.items(), key=lambda kv: kv[1]["force_n"])
        session.monitor.forcing_tick(pressing, words, event)
        # Layer 4 (evidence): the tick's deepest task contacts, review events
        tick = self._rcb_contact if contact else None
        contact_counts = mine.get("contact", {})
        if tick is not None:
            contact_counts, verdict = contact_rule_tick(contact_counts, tick["nonheld"][0], tick["held"][0],
                                                        rules["contact"]["window_ticks"])
            session.monitor.contact(tick, contact_counts)
            session.monitor.review_event(verdict, tick, words, int(state.get("physics_step", -1)))
        # Layer 3: a simulator breakdown is an infrastructure error, unless the arm was forcing
        breakdown = None
        if failure == SIMULATOR_INSTABILITY:                     # the particle speed guard (its evidence: Session.instability)
            breakdown = dict(session.instability or {}, kind="particle_speed")
        elif contact and failure == "Non-finite physical state":
            breakdown = dict(kind="non_finite_state")
        elif soft and failure in SOFT_FAILURES and ipc and not ipc.get("native_valid", True):
            breakdown = dict(kind="soft_solver_invalid")
        elif tick is not None and failure is None:
            key = max(("nonheld", "held"), key=lambda k: tick[k][0])
            d, pair, force = tick[key]
            if d > BREAKDOWN_PENETRATION_M:
                breakdown = dict(kind="extreme_penetration", depth_mm=round(d * 1000, 3), force_n=round(force, 1),
                                 bodies=[words.get(i, "a task part") for i in (pair or ())], held=key == "held")
        if breakdown is not None:
            breakdown.setdefault("physics_step", int(state.get("physics_step", -1)))
            reached = False
            if forced_recent:
                failure = _forced_breakdown_reason(session, words, breakdown)
            else:
                failure = SIMULATOR_INSTABILITY
                if breakdown["kind"] != "particle_speed":
                    session._on_instability(breakdown)
        elif soft and failure in SOFT_FAILURES:
            failure = _soft_reason(session, failure, ipc, soft_counts)
        kept = {k: v for k, v in (("contact", contact_counts), ("soft", soft_counts), ("forced", forced_left)) if v}
        if isinstance(private, dict):
            private = {**{k: v for k, v in private.items() if k != _RULES_KEY}, **({_RULES_KEY: kept} if kept else {})}
        return reached, failure, metrics, private

    task.validate_task_state = MethodType(validate_task_state, task)
    task.evaluate_transition = MethodType(evaluate_transition, task)
    return rules


def _link_words(session) -> dict:
    """global link index -> plain words for the readable failure reasons."""
    words, robot = {}, session.robot
    fingers = {name: arm for arm, g in robot.groups.items() if g.grasp is not None for name in g.grasp.finger_links}
    gripper = {i: arm for arm, links in session.table_guard.subtrees.items() for i in links}
    for ename, ent in session.env._world.entities.items():
        for link in getattr(ent, "links", ()):
            i = int(link.idx)
            if ename == "robot":
                arm = gripper.get(i) or fingers.get(link.name)
                side = f"the {arm} " if arm and len(robot.arms) > 1 else "the "
                if link.name in fingers:
                    words[i] = f"{side}gripper's finger"
                elif arm:
                    words[i] = f"{side}gripper"
                else:
                    prefix = link.name.split("/")[0] if "/" in link.name else ""
                    words[i] = (f"the {prefix} arm's {link.name.split('/')[-1]}" if prefix in robot.arms else
                                f"the robot's {link.name}")
            elif ename == "table" or ename.startswith(("table", "lab_")):
                words[i] = "the table" if ename.startswith("table") else f"the {ename.replace('_', ' ')}"
            else:
                words[i] = f"the {ename.replace('_', ' ')}"
    return words


def _drive_context(session) -> str:
    """What the arms were doing when a rule fired: a drive at its torque cap, or a fast joint motion."""
    try:
        r = session.robot
        effort, speed = np.abs(r.efforts()), np.abs(r.velocities())
        worst = max(((arm, float(np.max(effort[r.arm_slice[arm]] / np.asarray(r.drive_force[arm][:len(r.groups[arm].arm_joints)]))))
                     for arm in r.arms), key=lambda x: x[1])
        fast = max(((arm, float(np.max(speed[r.arm_slice[arm]]))) for arm in r.arms), key=lambda x: x[1])
        if worst[1] >= .9:
            side = f"the {worst[0]} arm" if len(r.arms) > 1 else "the arm"
            return f", while {side} pushed at {100 * min(worst[1], 1.):.0f} % of its drive torque limit"
        if fast[1] >= 1.:
            side = f"the {fast[0]} arm" if len(r.arms) > 1 else "the arm"
            return f", during a fast motion of {side} ({fast[1]:.1f} rad/s)"
    except Exception:  # noqa: BLE001 -- a reason must never fail a physics tick
        pass
    return ""


def _forcing_words(session, words, arm, d) -> str:
    """'the left arm's waist drive was at 100 % of its torque cap (12.9 N m) while the claw 0 it holds pressed on the claw 1
    with 63 N' for one tick of the forcing condition."""
    side = f"the {arm} arm's" if len(session.robot.arms) > 1 else "the arm's"
    own = words.get(d["own"], "a part") + (" it holds" if d["held"] else "")
    return (f"{side} {d['joint'].split('/')[-1]} drive was at {100 * min(d['fraction'], 1.):.0f} % of its torque cap "
            f"({d['cap_nm']:g} N m) while {own} pressed on {words.get(d['partner'], 'another body')} with {d['force_n']:.0f} N")


def breakdown_words(b: dict) -> str:
    """What broke down in the simulation, in words (Session.instability / the forced-breakdown reason)."""
    kind = b.get("kind")
    if kind == "extreme_penetration":
        one, two = (list(b.get("bodies") or ()) + ["a task part", "another body"])[:2]
        return (f"{one} and {two} interpenetrated {b['depth_mm']:.1f} mm (contact force {b['force_n']:.0f} N; a rigid "
                f"contact deeper than {BREAKDOWN_PENETRATION_M * 1000:g} mm is a solver breakdown)")
    if kind == "particle_speed":
        speed = "a non-finite speed" if b.get("max_speed_m_s") is None else f"{b['max_speed_m_s']:.3g} m/s"
        return f"a {b.get('entity', 'cloth')} particle moved at {speed} (limit {PARTICLE_SPEED_LIMIT_M_S:g} m/s)"
    if kind == "soft_solver_invalid":
        return "the soft-body solver reported an invalid state"
    return "the rigid-body state became non-finite"


def _forced_breakdown_reason(session, words, b) -> str:
    last, dt = session.last_forcing, float(session.env.config.physics_dt_s)
    if last is not None:
        arm, d = last
        ago = (int(b["physics_step"]) - int(d["physics_step"])) * dt
        forcing = _forcing_words(session, words, arm, d) + (f" ({ago:.3g} s before)" if ago > 0 else "")
    else:
        forcing = f"an arm forced within the {FORCING['attribution_s']:g} s before"
    return (f"{FORCED_BREAKDOWN}: the simulation broke down ({breakdown_words(b)}) right after forcing: {forcing}. A "
            f"breakdown within {FORCING['attribution_s']:g} s of forcing is the agent's failure; without forcing it is "
            "an infrastructure error.")


def _soft_reason(session, code, ipc, counts) -> str:
    if not ipc.get("native_valid", True):
        return f"{code}: the soft-body solver reported an invalid state"
    window = session.rules["soft"]["window_ticks"]
    inverted = {k: v for k, v in counts.get("inverted", {}).items() if v >= window}
    if inverted:
        name = max(inverted, key=inverted.get)
        ratio = float((ipc.get("volume_ratio") or {}).get(name, {}).get("minimum", float("nan")))
        return (f"{code}: the {name} stayed crushed for {SOFT_RULE['window_s']:g} s (an inverted volume element, worst "
                f"volume ratio {ratio:.3f}){_gripper_context(session)}. A squeeze that recovers within "
                f"{SOFT_RULE['window_s']:g} s is tolerated; a full close on it, or pressing it into the table, is not.")
    stretched = {k: v for k, v in counts.get("stretched", {}).items() if v >= window}
    if stretched:
        name = max(stretched, key=stretched.get)
        value = float((ipc.get("attachment_residual_m") or {}).get(name, float("nan")))
        return (f"{code}: the cord's permanent attachment {name} stayed stretched by {value * 1000:.1f} mm (limit "
                f"{SOFT_RULE['residual_m'] * 1000:g} mm) for {SOFT_RULE['window_s']:g} s{_drive_context(session)}")
    return code


def _gripper_context(session) -> str:
    """Where the grippers working near the tabletop (lowest point within 5 cm) were when a soft rule fired: closed on
    something, or touching the tabletop. A gripper parked higher up is not mentioned."""
    try:
        r, guard = session.robot, session.table_guard
        low = guard.lowest(r.positions()) if guard.limit is not None else {}
        parts = []
        for arm in r.arms:
            if arm in low and low[arm] - guard.table > .05:
                continue
            width, bits = r.opening(arm), []
            if width < .012:
                bits.append(f"closed to {width * 1000:.0f} mm")
            if arm in low and low[arm] - guard.table < .006:
                bits.append(f"its lowest point {max(low[arm] - guard.table, 0.) * 1000:.0f} mm above the tabletop")
            if bits:
                parts.append(f"{'the ' + arm + ' gripper' if len(r.arms) > 1 else 'the gripper'} " + " and ".join(bits))
        return f" ({'; '.join(parts)})" if parts else ""
    except Exception:  # noqa: BLE001
        return ""


def _install_torque_caps(session) -> dict:
    """R3: the arm joints' PD force clamp (Genesis set_dofs_force_range) becomes min(model limit, ARM_TORQUE_CAPS_NM);
    the gripper drives keep theirs. The world checkpoint (recorded before) restores Genesis' engine buffers, the force
    range included, so every rewind applies the caps again (_install_rules' lifecycle sink)."""
    rr = session.env._robot
    caps = ARM_TORQUE_CAPS_NM.get(rr.description.robot_id)
    session._torque_cap_dofs, out = [], {}
    if caps is None:
        return out
    for g in rr.description.groups:
        n = len(g.arm_joints)
        if len(caps) != n:
            raise ValueError(f"torque caps for {rr.description.robot_id} name {len(caps)} joints, the arm has {n}")
        limits = np.minimum(np.asarray(g.force[:n], dtype=np.float64), np.asarray(caps, dtype=np.float64))
        session._torque_cap_dofs.append((list(rr._controlled[g.name][:n]), limits))
        session.robot.drive_force[g.name] = tuple(float(v) for v in limits) + tuple(float(v) for v in g.force[n:])
        out[g.name] = [float(v) for v in limits]
    _apply_torque_caps(session)
    return out


def _apply_torque_caps(session) -> None:
    for dofs, limits in session._torque_cap_dofs:
        session.env._robot.entity.set_dofs_force_range(-limits, limits, dofs)


class _ChainFK:
    """Forward kinematics of the robot entity in numpy, from Genesis' own static link / joint / dof data, mirroring
    func_forward_kinematics_entity (genesis/engine/solvers/rigid/abd/forward_kinematics.py: fixed root, revolute,
    prismatic and fixed joints). Genesis' RigidEntity.forward_kinematics runs its kernel on the live solver arrays and
    changes the next physics step in the last bits (a guard that stops nothing must not change the simulation), and it
    costs a kernel launch; this reads the solver once and never again."""

    def __init__(self, entity):
        solver = entity._solver

        def read(field, n):
            a = np.asarray(field.to_numpy(), dtype=np.float64)
            return a.reshape(a.shape[0], -1, n)[:, 0, :] if n else a.reshape(a.shape[0], -1)[:, 0]
        self.names = {int(link.idx): link.name for link in entity.links}
        self.l0, self.l1, self.q0 = int(entity.link_start), int(entity.link_end), int(entity.q_start)
        info, joints, dofs = solver.links_info, solver.joints_info, solver.dofs_info
        self.lpos, self.lquat = read(info.pos, 3), read(info.quat, 4)
        self.parent, self.fixed = read(info.parent_idx, 0).astype(int), read(info.is_fixed, 0).astype(bool)
        self.jstart, self.jend = read(info.joint_start, 0).astype(int), read(info.joint_end, 0).astype(int)
        self.jtype, self.jq = read(joints.type, 0).astype(int), read(joints.q_start, 0).astype(int)
        self.jdof, self.jpos = read(joints.dof_start, 0).astype(int), read(joints.pos, 3)
        self.mang, self.mvel = read(dofs.motion_ang, 3), read(dofs.motion_vel, 3)
        self.qpos0 = read(solver._rigid_global_info.qpos0, 0)
        root_pos, root_quat = read(solver.links_state.pos, 3), read(solver.links_state.quat, 4)
        self.root = {i: (root_pos[i].copy(), root_quat[i].copy()) for i in range(self.l0, self.l1)
                     if self.parent[i] == -1 and self.fixed[i]}            # fixed roots keep their placed pose
        import genesis as gs
        self.types = (int(gs.JOINT_TYPE.FIXED), int(gs.JOINT_TYPE.REVOLUTE), int(gs.JOINT_TYPE.PRISMATIC))

    @staticmethod
    def _mul(u, v):
        w1, x1, y1, z1 = u
        w2, x2, y2, z2 = v
        q = np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                      w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])
        return q / np.linalg.norm(q)

    def __call__(self, q_local) -> dict:
        """link name -> 4x4 world pose for the entity-local qpos q_local (Session._Robot q_full layout)."""
        fixed, revolute, prismatic = self.types
        q = self.qpos0.copy()
        q[self.q0:self.q0 + len(q_local)] = np.asarray(q_local, dtype=np.float64)
        P, Q, out = {}, {}, {}
        for i in range(self.l0, self.l1):
            if i in self.root:
                P[i], Q[i] = self.root[i]
            else:
                pos, quat, parent = self.lpos[i], self.lquat[i], self.parent[i]
                if parent != -1:
                    pos, quat = P[parent] + quat_to_mat(Q[parent]) @ self.lpos[i], self._mul(Q[parent], self.lquat[i])
                for j in range(self.jstart[i], self.jend[i]):
                    kind, angle = self.jtype[j], q[self.jq[j]] - self.qpos0[self.jq[j]]
                    if kind == revolute:
                        anchor = quat_to_mat(quat) @ self.jpos[j] + pos
                        v = self.mang[self.jdof[j]] * angle
                        theta = float(np.linalg.norm(v))
                        local = (np.r_[math.cos(theta / 2), math.sin(theta / 2) / theta * v] if theta > 1e-15
                                 else np.array([1., 0., 0., 0.]))
                        quat = self._mul(quat, local)
                        pos = anchor - quat_to_mat(quat) @ self.jpos[j]
                    elif kind == prismatic:
                        pos = pos + quat_to_mat(quat) @ self.mvel[self.jdof[j]] * angle
                    elif kind != fixed:
                        raise ValueError(f"kinematics: unsupported joint type {kind}")
                P[i], Q[i] = pos, quat
            out[self.names[i]] = _T(P[i], Q[i])
        return out


class _TableGuard:
    """R4: before a control step runs, stop each arm's commanded joint targets where any collision vertex of its gripper
    (the subtree of its grasp contact_root_link: fingers and housing, at the commanded opening) would come lower than the
    tabletop + TABLE_GUARD_MARGIN_M (negative: below the tabletop; see the constant). Only arm motion is stopped, along
    the step (previous joint targets -> new ones), so the stop lies on the commanded path; a gripper command is never
    changed (closing a Robotiq moves its fingertips forward: near the table they may touch it, with the gripper's own
    small force). A gripper already below may move up, not further down. Forward kinematics (_ChainFK) runs only for
    arms whose joint targets changed. A guarded target is rounded to float32 like every recorded row, so live execution
    and replays command the same values (a replayed guarded row is not changed again)."""

    def __init__(self, session):
        self.s, r = session, session.robot
        self.table = session.table_z()
        self.limit = None if self.table is None else self.table + TABLE_GUARD_MARGIN_M
        self.points: dict = {}           # arm -> [(link name, (k, 3) link-frame vertices)]
        self.subtrees: dict = {}         # arm -> {global link indices}
        links = list(r.entity.links)
        for arm, g in r.groups.items():
            root = next((link for link in links if g.grasp is not None and link.name == g.grasp.contact_root_link), None)
            if root is None:
                continue
            tree, grown = {int(root.idx)}, True
            while grown:
                grown = False
                for link in links:
                    if int(link.idx) not in tree and int(link.parent_idx) in tree:
                        tree.add(int(link.idx))
                        grown = True
            self.subtrees[arm] = tree
            pts = []
            for link in links:
                if int(link.idx) in tree and link.geoms:
                    local = np.concatenate([quat_to_mat(gm.init_quat).dot(np.asarray(gm.init_verts, dtype=np.float64).T).T
                                            + np.asarray(gm.init_pos, dtype=np.float64) for gm in link.geoms])
                    try:
                        from scipy.spatial import ConvexHull
                        local = local[ConvexHull(local).vertices]
                    except Exception:  # noqa: BLE001 -- a degenerate hull keeps every vertex
                        pass
                    pts.append((link.name, local))
            self.points[arm] = pts
        self.count, self.events = 0, []
        self.fk = _ChainFK(r.entity) if self.points else None

    def lowest(self, row) -> dict:
        """arm -> the lowest world z of its gripper at the joint row `row` (action layout)."""
        r, row = self.s.robot, np.asarray(row, dtype=np.float64)
        q = r.q_full(np.concatenate([row[r.arm_slice[a]] for a in r.arms]))
        q = r._with_fingers(q, {a: r.action_to_native(a, row[r.grip_index[a]]) for a in r.arms})
        T = self.fk(q)
        return {arm: min(float((local @ T[name][2, :3] + T[name][2, 3]).min()) for name, local in pts)
                for arm, pts in self.points.items() if pts}

    def apply(self, target, previous):
        """-> the guarded target (the input itself when nothing is stopped); sets the Session's last_guard event."""
        self.s.last_guard = None
        if self.limit is None or not self.points:
            return target
        r = self.s.robot
        previous = np.asarray(previous, dtype=np.float64)
        moved = [a for a in self.points if not np.array_equal(target[r.arm_slice[a]], previous[r.arm_slice[a]])]
        if not moved:
            return target                                     # a gripper command alone is never stopped
        want = self.lowest(target)
        low = [a for a in moved if want.get(a, np.inf) < self.limit - 1e-5]
        if not low:
            return target
        base = np.asarray(target, dtype=np.float64).copy()    # the previous joint targets at the new openings
        for arm in low:
            base[r.arm_slice[arm]] = previous[r.arm_slice[arm]]
        have = self.lowest(base)
        out, event = np.asarray(target, dtype=np.float64).copy(), {}
        for arm in low:
            bound = min(self.limit, have[arm])
            if want[arm] >= bound - 1e-5:
                continue                                      # moving up from below the limit is allowed
            idx = list(range(r.arm_slice[arm].start, r.arm_slice[arm].stop))
            lo, hi = 0., 1.
            for _ in range(14):                               # the stop within 0.01 % of the step
                mid = (lo + hi) / 2
                trial = out.copy()
                trial[idx] = previous[idx] + (out[idx] - previous[idx]) * mid
                if self.lowest(trial)[arm] >= bound + 1e-6:
                    lo = mid
                else:
                    hi = mid
            out[idx] = previous[idx] + (out[idx] - previous[idx]) * lo
            event[arm] = dict(asked_mm=round((want[arm] - self.table) * 1000, 1), stopped_mm=round((bound - self.table) * 1000, 1),
                              fraction=round(lo, 4))
        if not event:
            return target
        out = out.astype(np.float32).astype(np.float64)
        self.count += 1
        self.s.last_guard = dict(step=int(self.s.n_steps) + 1, **event)
        self.events = (self.events + [self.s.last_guard])[-20:]
        self.s.monitor.guard(self.s.last_guard)
        if self.count <= 5 or self.count % 100 == 0:
            _log("table guard:", "; ".join(f"{a} gripper target {e['asked_mm']:+.1f} mm from the tabletop, stopped at "
                                           f"{e['stopped_mm']:+.1f} mm" for a, e in event.items()), f"(guarded steps: {self.count})")
        return out


class _SafetyMonitor:
    """What the physical-validity policy measures, for the agent (Session.safety(), the standard service's meta["safety"]):
    maxima since the previous read and over the episode (since the last reset), against their limits; and the episode's
    evidence for the graders (Layer 4): its review events (review()) and forcing events (forcing())."""
    MAX_EVENTS = 20

    def __init__(self, session):
        self.s = session
        self.reset()

    @staticmethod
    def _blank() -> dict:
        return dict(contact=0., held=0., over=0, held_over=0, ratio={}, inverted=0, residual=0., stretched=0, guard=0,
                    guard_events=[], ik=[], press_force=0., press_fraction=0., forcing=0, forcing_events=[],
                    forcing_count=0, review=[], review_count=0)

    def reset(self) -> None:
        self.last, self.episode = self._blank(), self._blank()
        self._open = False
        self._runs, self._open_forcing = {}, {}       # arm -> consecutive forcing ticks; arm -> its open forcing event

    def _both(self):
        return (self.last, self.episode)

    def contact(self, tick, counts) -> None:
        for d in self._both():
            d.update(contact=max(d["contact"], tick["nonheld"][0]), held=max(d["held"], tick["held"][0]),
                     over=max(d["over"], counts.get("over", 0)), held_over=max(d["held_over"], counts.get("held_over", 0)))

    def forcing_tick(self, pressing, words, event_ticks) -> None:
        """One tick of the forcing measures: the arms pressing with at least FORCING["contact_n"] and their drive load.
        A run of the forcing condition on `event_ticks` consecutive ticks opens a forcing event (when it reached that
        length: arm, drive, % of cap, what it pressed on, force); later ticks of the run extend it."""
        forcing = {arm: v for arm, v in pressing.items() if v["forcing"]}
        self._runs = {arm: self._runs.get(arm, 0) + 1 for arm in forcing}
        self._open_forcing = {arm: e for arm, e in self._open_forcing.items() if arm in self._runs}
        longest = max(self._runs.values(), default=0)
        for d in self._both():
            d["forcing"] = max(d["forcing"], longest)
            for v in pressing.values():
                d.update(press_force=max(d["press_force"], v["force_n"]), press_fraction=max(d["press_fraction"], v["fraction"]))
        for arm, n in self._runs.items():
            v, e = forcing[arm], self._open_forcing.get(arm)
            if e is not None:
                e.update(ticks=n, max_force_n=max(e["max_force_n"], round(v["force_n"], 1)))
            elif n == event_ticks:
                e = dict(arm=arm, joint=v["joint"].split("/")[-1], step=int(self.s.n_steps) + 1, physics_step=v["physics_step"],
                         ticks=n, fraction=round(v["fraction"], 3), cap_nm=v["cap_nm"], max_force_n=round(v["force_n"], 1),
                         pressing=words.get(v["own"], "a part") + (" it holds" if v["held"] else ""),
                         on=words.get(v["partner"], "another body"))
                self._open_forcing[arm] = e
                for d in self._both():
                    d["forcing_count"] += 1
                    if len(d["forcing_events"]) < self.MAX_EVENTS:
                        d["forcing_events"].append(e)

    def forcing(self) -> dict | None:
        """The episode's forcing events (None: none): evidence only, they never end the episode or hold a success."""
        d = self.episode
        if not d["forcing_count"]:
            return None
        dt = float(self.s.env.config.physics_dt_s)
        return dict(count=d["forcing_count"], longest_s=round(d["forcing"] * dt, 4), events=[dict(e) for e in d["forcing_events"]])

    def review_event(self, verdict, tick, words, physics_step) -> None:
        """One tick of contact_rule_tick's verdict: consecutive ticks with a verdict make one review event (its worst
        depth, the force there, its length in ticks)."""
        if not verdict:
            self._open = False
            return
        held = verdict.startswith("held")
        depth, pair, force = tick["held" if held else "nonheld"]
        for d in self._both():
            if self._open and d["review"] and d["review_count"] == len(d["review"]):
                e = d["review"][-1]
                e["ticks"] += 1
                if depth * 1000 > e["depth_mm"]:
                    e.update(depth_mm=round(depth * 1000, 3), force_n=round(force, 1))
            elif not self._open:
                d["review_count"] += 1
                if len(d["review"]) < self.MAX_EVENTS:
                    d["review"].append(dict(kind=verdict, step=int(self.s.n_steps) + 1, physics_step=int(physics_step), ticks=1,
                                            bodies=[words.get(i, "a task part") for i in (pair or ())],
                                            depth_mm=round(depth * 1000, 3), force_n=round(force, 1)))
        self._open = True

    def review(self) -> dict | None:
        """The episode's review events (None: none). A success with any is held for review by the graders."""
        d = self.episode
        if not d["review_count"]:
            return None
        return dict(pending=True, count=d["review_count"], max_depth_mm=max(e["depth_mm"] for e in d["review"]),
                    events=[dict(e) for e in d["review"]])

    def soft(self, ratios, residuals, counts) -> None:
        for d in self._both():
            for name, value in ratios.items():
                if math.isfinite(value):
                    d["ratio"][name] = min(d["ratio"].get(name, value), value)
            d["residual"] = max([d["residual"]] + [v for v in residuals.values() if math.isfinite(v)])
            d["inverted"] = max([d["inverted"]] + list(counts.get("inverted", {}).values()))
            d["stretched"] = max([d["stretched"]] + list(counts.get("stretched", {}).values()))

    def guard(self, event) -> None:
        for d in self._both():
            d.update(guard=d["guard"] + 1, guard_events=(d["guard_events"] + [event])[-5:])

    def ik_jump(self, event) -> None:
        for d in self._both():
            d["ik"] = (d["ik"] + [event])[-5:]

    def read(self, *, episode: bool = False, reset: bool = True) -> dict:
        d, s = (self.episode if episode else self.last), self.s
        dt = float(s.env.config.physics_dt_s)
        rules = s.rules
        out = {"rules": RULES_REVISION, "scope": "episode" if episode else "since the previous read"}
        p = FORCING
        out["forcing"] = dict(event_after_s=p["event_s"], near_cap_fraction=p["near_cap"], contact_n=p["contact_n"],
                              max_press_force_n=round(d["press_force"], 1),
                              max_drive_fraction_while_pressing=round(d["press_fraction"], 3),
                              longest_forcing_s=round(d["forcing"] * dt, 4), events=d["forcing_count"],
                              recent=[dict(e) for e in d["forcing_events"][-3:]],
                              note=f"recorded only: forcing never ends the episode; a simulator breakdown within "
                                   f"{p['attribution_s']:g} s of it is the agent's failure")
        if rules["contact"]:
            c = CONTACT_RULE
            out["task_contact_mm"] = dict(max=round(d["contact"] * 1000, 3), review_above=c["deep_m"] * 1000,
                                          review_if_above_for_s=[c["sustained_m"] * 1000, c["window_s"]],
                                          longest_above_s=round(d["over"] * dt, 4),
                                          breakdown_above=BREAKDOWN_PENETRATION_M * 1000)
            out["held_finger_contact_mm"] = dict(max=round(d["held"] * 1000, 3), review_above=c["held_deep_m"] * 1000,
                                                 review_if_above_for_s=[c["held_sustained_m"] * 1000, c["window_s"]],
                                                 longest_above_s=round(d["held_over"] * dt, 4))
            out["review"] = dict(events=d["review_count"], recent=d["review"][-3:],
                                 note="a success with a review event is held for review instead of credited automatically")
        if rules["soft"]:
            w = SOFT_RULE["window_s"]
            out["soft_volume_ratio"] = dict(min={k: round(v, 4) for k, v in d["ratio"].items()}, fails_at_or_below_for_s=[0., w],
                                            longest_at_or_below_s=round(d["inverted"] * dt, 4))
            out["attachment_stretch_mm"] = dict(max=round(d["residual"] * 1000, 3),
                                                fails_if_above_for_s=[SOFT_RULE["residual_m"] * 1000, w],
                                                longest_above_s=round(d["stretched"] * dt, 4))
        if rules["table_guard_margin_m"] is not None:
            out["table_guard"] = dict(margin_mm=TABLE_GUARD_MARGIN_M * 1000, stopped_steps=d["guard"], recent=d["guard_events"])
        if d["ik"]:
            out["ik_jumps"] = d["ik"]
        if reset and not episode:
            self.last = self._blank()
        return out


def _settle_only_when_reached(task) -> bool:
    """Tooling v12, families with a final-settling check (knot_untying, cast_coil, buzz_wire_3d, blanket_flatten):
    TaskDefinition._evaluate_terminal (topogym/tasks/base.py) runs evaluate_settling (release clearance over every FEM
    tet, speeds, drift) only on ticks where the task's own goal predicate is reached. On the other ticks its result cannot
    change the outcome (it is ANDed into reached, the stability window restarts, next_reference is discarded), so
    success, failures and the episode end are unchanged; those ticks only leave out metrics["final_settling"] and its
    evaluation_status. knot_untying: task cost 1.84 -> 0.04 s per control step (IPC study, 2026-10-02)."""
    if task.final_settling_spec() is None:
        return False
    from types import MethodType

    def _evaluate_terminal(self, state, private, reference):
        reached, failure, metrics, private = self.evaluate_transition(state, private)
        spec = self.final_settling_spec()
        next_reference = None
        if spec is not None and not failure and reached:
            from topogym.evaluation.terminal import evaluate_settling
            settled, measurements, next_reference = evaluate_settling(state, spec, reference)
            status = metrics.get("evaluation_status", "available")
            if status not in {"available", "unavailable"}:
                raise ValueError("Invalid task evaluation status")
            status = "available" if status == measurements["evaluation_status"] == "available" else "unavailable"
            metrics = {**metrics, "final_settling": measurements, "evaluation_status": status}
            reached = bool(reached and settled and status == "available")
            if not reached:
                next_reference = None
        return reached, failure, metrics, private, next_reference
    task._evaluate_terminal = MethodType(_evaluate_terminal, task)
    return True



# ---- deterministic GPU physics (tooling v17, 2026-10-05; jobs/journal/2026-10-05/determinism)
# Scope (every Session, installed before the first scene is built):
#   - every scene on the GPU: the rigid constraint solve is pinned to Genesis' monolith arm. This changes the rounding
#     of blanket_flatten, lock_picking and of the robots / rigid bodies of the IPC scenes (knot_untying, rope_threading,
#     slotted_post_ring, orbits); their libuipc FEM/ABD solve itself is unchanged (still not reproducible). CPU scenes:
#     unchanged (the CPU backend only has the monolith arm).
#   - blanket_flatten only (the only PBD scene): PBD stretch / bending / particle collision and the PBD-rigid link
#     forces summed in fixed point.
#   - instance shas: unchanged (every instance restores its frozen / settled state without a physics step).
# Grading replays re-run an agent's actions in fresh processes. On the GPU families they did not reproduce the live run:
# two fresh replays of one blanket trajectory already differed by 1.6e-13 m after the first control step, by millimetres
# after 100 and in the outcome after ~1400 (one succeeded, one did not). In-process stage isolation (the same engine
# buffers in, each kernel run three times) found the causes, all in scheduling-order arithmetic, none in the physics:
#   1. Genesis' rigid constraint solve (func_solve_body) is a qd.perf_dispatch autotuner: with cooperative kernels on
#      (GPU, n_dofs >= 16) it alternates the "monolith" and "decomposed" arms and re-times them every 5 s of wall clock,
#      so the arm that integrates a substep depends on the host's load. The monolith arm, pinned, is reproducible (stage
#      isolation and fresh-process replays); the switching is not. Pinned here for the whole process (both arms solve
#      the same Newton problem; the CPU backend only ever runs the monolith, so the CPU families are unchanged).
#   2. PBD constraint projection (stretch, bending) scatters `dpos += ...` from parallel loops over constraints: float
#      atomics in GPU scheduler order.
#   3. PBD particle collision sums neighbour contributions in the spatial hash's cell order, which an atomic counting
#      sort assigns differently every substep (the reordered layout itself is scratch: rebuilt each substep before use).
#   4. The PBD-rigid contact (_bound_pbd_rigid_contacts) applies coupling forces to robot links with float atomics.
# 2-4 become integer sums: each contribution is rounded once to a fixed-point quantum and added with an int64 atomic;
# integer addition is associative, so the total does not depend on the order; it is converted back to float once per
# particle / link and accumulation. Quanta: particle corrections 2^-48 m (3.6e-15 m), link forces 2^-32 N (2.3e-10 N)
# and torques 2^-32 N m. A contribution above PBD_FX_LIMIT_M (16 m) / 2^16 N / 2^17 N m, or not finite, makes that
# particle's correction (link's force) NaN, so the instability guard ends the episode as before (16 m / 2^-48 = 2^52
# quanta per contribution: 2^11 contributions per particle and accumulation fit in int64; forces 2^48 / 2^49 quanta, 2^14
# contributions per link and substep; an 8181-particle cloth on one link is 2^13). The constraint math, its iteration
# structure, which contributions exist and the apply loops are Genesis' expressions, unchanged. Genesis' files are not
# edited (kernels replaced at runtime like _bound_pbd_rigid_contacts), so the frozen blanket states' backend identity,
# which hashes them, still matches; the integer scratch lives outside the engine-buffer graph that checkpoints and frozen
# states inventory (it holds zeros between kernels).
# Measured (lab RTX PRO 6000, image 0.2.14-dev): see docs/rcb/benchmarks/topogym.md "Deterministic GPU physics".
# The IPC families' libuipc solver keeps its own float atomics (not covered here).
DETERMINISTIC_GPU_PHYSICS = "fixed_point_pbd_pinned_solve_arm_2026-10-05"
RIGID_SOLVE_ARM = "func_solve_body_monolith"
PBD_FX_SCALE_M, PBD_FX_QUANTUM_M, PBD_FX_LIMIT_M = 2.0 ** 48, 2.0 ** -48, 16.0
COUPLING_FX_SCALE, COUPLING_FX_QUANTUM = 2.0 ** 32, 2.0 ** -32
COUPLING_FORCE_LIMIT_N, COUPLING_TORQUE_LIMIT_NM = 65536.0, 131072.0


def _deterministic_gpu_physics() -> dict:
    """Install the deterministic replacements (the block comment above) right after genesis.init (Genesis' solver
    modules cannot be imported before it), before the first scene is built. Idempotent; returns what is installed."""
    import genesis as gs
    if getattr(gs, "_initialized", False):
        return _install_deterministic_gpu_physics()
    if not getattr(gs.init, "_topogym_deterministic", False):
        original = gs.init

        def init(*args, **kwargs):
            result = original(*args, **kwargs)
            _install_deterministic_gpu_physics()
            return result
        init._topogym_deterministic = True
        gs.init = init
    return dict(version=DETERMINISTIC_GPU_PHYSICS, installed="at genesis.init")


def _install_deterministic_gpu_physics() -> dict:
    import quadrants as qd
    import genesis as gs
    from genesis.engine.solvers.pbd_solver import PBDSolver
    from genesis.engine.solvers.rigid.constraint import solver as constraint_solver
    from genesis.engine.solvers.rigid.constraint import solver_breakdown  # noqa: F401  (registers the decomposed arm)

    info = dict(version=DETERMINISTIC_GPU_PHYSICS, rigid_solve_arm=RIGID_SOLVE_ARM)
    if getattr(PBDSolver, "_topogym_deterministic", False):
        return info

    # 1. the rigid constraint-solve arm, pinned
    dispatcher = constraint_solver.func_solve_body
    arms = {impl.get_implementation2().__name__: impl for impl in dispatcher._dispatch_impls}
    chosen = arms[RIGID_SOLVE_ARM]
    autotuned = type(dispatcher).__call__

    class _PinnedArm(type(dispatcher)):
        def __call__(self, *args, **kwargs):
            if chosen.is_compatible is None or chosen.is_compatible(*args, **kwargs):
                return chosen(*args, **kwargs)
            return autotuned(self, *args, **kwargs)   # not reached in TopoGym scenes (prefer_decomposed_solver != 1)
    dispatcher.__class__ = _PinnedArm

    # 2-3. PBD constraint projection and particle collision with order-independent sums
    @qd.data_oriented
    class _Scratch:
        """Integer accumulators of one solver / coupler (not traversed by checkpoints; zeros between kernels)."""
        def __init__(self, n, batch, k):
            self.acc = qd.field(qd.i64, shape=(max(int(n), 1), int(batch), int(k)))
            self.bad = qd.field(qd.i32, shape=(max(int(n), 1), int(batch)))

    @qd.func
    def _bad(x, limit):
        # non-finite (all-ones exponent, read from the bits: fast-math cannot fold the test) or out of range
        b = False
        if qd.static(gs.qd_float == qd.f64):
            b = ((qd.bit_cast(x, qd.i64) >> 52) & 0x7FF) == 0x7FF
        else:
            b = ((qd.bit_cast(x, qd.i32) >> 23) & 0xFF) == 0xFF
        return b or qd.abs(x) > limit

    @qd.func
    def _fx(x, scale):
        return qd.cast(qd.floor(x * scale + 0.5), qd.i64)

    @qd.func
    def _nan():
        r = gs.qd_float(0.0)
        if qd.static(gs.qd_float == qd.f64):
            r = qd.bit_cast(qd.i64(0x7FF8000000000000), qd.f64)
        else:
            r = qd.bit_cast(qd.i32(0x7FC00000), qd.f32)
        return r

    def _scatter(det, i, i_b, c):
        for k in qd.static(range(3)):
            if _bad(c[k], PBD_FX_LIMIT_M):
                det.bad[i, i_b] = 1
            else:
                qd.atomic_add(det.acc[i, i_b, k], _fx(c[k], PBD_FX_SCALE_M))
    _scatter.__annotations__ = dict(det=qd.template())
    _scatter = qd.func(_scatter)

    def _take(det, i, i_b):
        d = qd.Vector.zero(gs.qd_float, 3)
        for k in qd.static(range(3)):
            d[k] = qd.cast(det.acc[i, i_b, k], gs.qd_float) * PBD_FX_QUANTUM_M
            det.acc[i, i_b, k] = 0
        if det.bad[i, i_b] != 0:
            det.bad[i, i_b] = 0
            d = qd.Vector([_nan(), _nan(), _nan()], dt=gs.qd_float)
        return d
    _take.__annotations__ = dict(det=qd.template())
    _take = qd.func(_take)

    @qd.func
    def _add3(acc, bad, c):
        for k in qd.static(range(3)):
            if _bad(c[k], PBD_FX_LIMIT_M):
                bad = 1
            else:
                acc[k] += _fx(c[k], PBD_FX_SCALE_M)
        return acc, bad

    @qd.data_oriented
    class _DeterministicPBD:
        # Genesis 1.2.1 pbd_solver.py:411-430 (_kernel_solve_stretch), the scatter order-independent
        def _kernel_solve_stretch(self, f):
            for _ in qd.static(range(self._max_stretch_solver_iterations)):
                for i_e, i_b in qd.ndrange(self._n_edges, self._B):
                    v1 = self.edges_info[i_e].v1
                    v2 = self.edges_info[i_e].v2

                    w1 = self.particles[v1, i_b].free / self.particles_info[v1].mass
                    w2 = self.particles[v2, i_b].free / self.particles_info[v2].mass
                    n = self.particles[v1, i_b].pos - self.particles[v2, i_b].pos
                    C = n.norm() - self.edges_info[i_e].len_rest
                    alpha = self.edges_info[i_e].stretch_compliance / (self._substep_dt**2)
                    dp = -C / (w1 + w2 + alpha) * n / n.norm(gs.EPS) * self.edges_info[i_e].stretch_relaxation
                    _scatter(self._det, v1, i_b, dp * w1)
                    _scatter(self._det, v2, i_b, -(dp * w2))

                for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                    total = self.particles[i_p, i_b].dpos + _take(self._det, i_p, i_b)
                    if self.particles[i_p, i_b].free and self.particles_info[i_p].material_type != self.MATERIAL.PARTICLE:
                        self.particles[i_p, i_b].pos = self.particles[i_p, i_b].pos + total
                        self.particles[i_p, i_b].dpos.fill(0)
                    else:
                        self.particles[i_p, i_b].dpos = total
        _kernel_solve_stretch.__annotations__ = dict(f=qd.i32)
        _kernel_solve_stretch = qd.kernel(_kernel_solve_stretch)

        # Genesis 1.2.1 pbd_solver.py:432-483 (_kernel_solve_bending)
        def _kernel_solve_bending(self, f):
            for _ in qd.static(range(self._max_bending_solver_iterations)):
                for i_ie, i_b in qd.ndrange(self._n_inner_edges, self._B):
                    v1 = self.inner_edges_info[i_ie].v1
                    v2 = self.inner_edges_info[i_ie].v2
                    v3 = self.inner_edges_info[i_ie].v3
                    v4 = self.inner_edges_info[i_ie].v4

                    w1 = self.particles[v1, i_b].free / self.particles_info[v1].mass
                    w2 = self.particles[v2, i_b].free / self.particles_info[v2].mass
                    w3 = self.particles[v3, i_b].free / self.particles_info[v3].mass
                    w4 = self.particles[v4, i_b].free / self.particles_info[v4].mass

                    if w1 + w2 + w3 + w4 > 0.0:
                        p2 = self.particles[v2, i_b].pos - self.particles[v1, i_b].pos
                        p3 = self.particles[v3, i_b].pos - self.particles[v1, i_b].pos
                        p4 = self.particles[v4, i_b].pos - self.particles[v1, i_b].pos
                        l23 = p2.cross(p3).norm()
                        l24 = p2.cross(p4).norm()
                        n1 = p2.cross(p3) / l23
                        n2 = p2.cross(p4) / l24
                        d = qd.math.clamp(n1.dot(n2), -1.0, 1.0)

                        q3 = (p2.cross(n2) + n1.cross(p2) * d) / l23
                        q4 = (p2.cross(n1) + n2.cross(p2) * d) / l24
                        q2 = -(p3.cross(n2) + n1.cross(p3) * d) / l23 - (p4.cross(n1) + n2.cross(p4) * d) / l24
                        q1 = -q2 - q3 - q4
                        sum_wq = w1 * q1.norm_sqr() + w2 * q2.norm_sqr() + w3 * q3.norm_sqr() + w4 * q4.norm_sqr()
                        constraint = qd.acos(d) - qd.acos(-1.0)

                        alpha = self.inner_edges_info[i_ie].bending_compliance / (self._substep_dt**2)
                        constraint = (
                            -qd.sqrt(1 - d**2)
                            * constraint
                            / (sum_wq + alpha)
                            * self.inner_edges_info[i_ie].bending_relaxation
                        )

                        _scatter(self._det, v1, i_b, w1 * constraint * q1)
                        _scatter(self._det, v2, i_b, w2 * constraint * q2)
                        _scatter(self._det, v3, i_b, w3 * constraint * q3)
                        _scatter(self._det, v4, i_b, w4 * constraint * q4)

                for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                    total = self.particles[i_p, i_b].dpos + _take(self._det, i_p, i_b)
                    if self.particles[i_p, i_b].free and self.particles_info[i_p].material_type != self.MATERIAL.PARTICLE:
                        self.particles[i_p, i_b].pos = self.particles[i_p, i_b].pos + total
                        self.particles[i_p, i_b].dpos.fill(0)
                    else:
                        self.particles[i_p, i_b].dpos = total
        _kernel_solve_bending.__annotations__ = dict(f=qd.i32)
        _kernel_solve_bending = qd.kernel(_kernel_solve_bending)

        # Genesis 1.2.1 pbd_solver.py:525-558 (_func_solve_collision): neighbour j's two contributions to particle i
        @qd.func
        def _det_collision_terms(self, i, j, i_b):
            c1 = qd.Vector.zero(gs.qd_float, 3)
            c2 = qd.Vector.zero(gs.qd_float, 3)
            cur_dist = (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm(gs.EPS)
            rest_dist = (
                self.particles_info_reordered[i, i_b].pos_rest - self.particles_info_reordered[j, i_b].pos_rest
            ).norm(gs.EPS)
            target_dist = self._particle_size
            if cur_dist < target_dist and rest_dist > target_dist:
                wi = self.particles_reordered[i, i_b].free / self.particles_info_reordered[i, i_b].mass
                wj = self.particles_reordered[j, i_b].free / self.particles_info_reordered[j, i_b].mass
                n = (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos) / cur_dist
                c1 = wi / (wi + wj) * (target_dist - cur_dist) * n
                dv = (self.particles_reordered[i, i_b].pos - self.particles_reordered[i, i_b].ipos) - (
                    self.particles_reordered[j, i_b].pos - self.particles_reordered[j, i_b].ipos
                )
                dpos = -(dv - n * n.dot(dv))
                d = target_dist - cur_dist
                mu_s = qd.max(self.particles_info_reordered[i, i_b].mu_s, self.particles_info_reordered[j, i_b].mu_s)
                mu_k = qd.max(self.particles_info_reordered[i, i_b].mu_k, self.particles_info_reordered[j, i_b].mu_k)
                if dpos.norm() < mu_s * d:
                    c2 = wi / (wi + wj) * dpos
                else:
                    c2 = wi / (wi + wj) * dpos * qd.min(1.0, mu_k * d / dpos.norm(gs.EPS))
            return c1, c2

        # Genesis 1.2.1 pbd_solver.py:560-589 (_kernel_solve_collision): the per-particle gather, its sum order-independent
        def _kernel_solve_collision(self, f):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_info_reordered[i_p, i_b].material_type != self.MATERIAL.PARTICLE:
                    acc = qd.Vector([0, 0, 0], dt=qd.i64)
                    bad = 0
                    base = self.sh.pos_to_grid(self.particles_reordered[i_p, i_b].pos)
                    for offset in qd.grouped(qd.ndrange((-1, 2), (-1, 2), (-1, 2))):
                        slot_idx = self.sh.grid_to_slot(base + offset)
                        for j in range(
                            self.sh.slot_start[slot_idx, i_b],
                            self.sh.slot_size[slot_idx, i_b] + self.sh.slot_start[slot_idx, i_b],
                        ):
                            if (
                                i_p != j
                                and (self.particles_reordered[i_p, i_b].free or self.particles_reordered[j, i_b].free)
                                and not (
                                    self.particles_info_reordered[i_p, i_b].material_type == self.MATERIAL.LIQUID
                                    and self.particles_info_reordered[j, i_b].material_type == self.MATERIAL.LIQUID
                                )
                            ):
                                c1, c2 = self._det_collision_terms(i_p, j, i_b)
                                acc, bad = _add3(acc, bad, c1)
                                acc, bad = _add3(acc, bad, c2)
                    d = qd.Vector.zero(gs.qd_float, 3)
                    for k in qd.static(range(3)):
                        d[k] = qd.cast(acc[k], gs.qd_float) * PBD_FX_QUANTUM_M
                    if bad != 0:
                        d = qd.Vector([_nan(), _nan(), _nan()], dt=gs.qd_float)
                    self.particles_reordered[i_p, i_b].dpos = self.particles_reordered[i_p, i_b].dpos + d

            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if (
                    self.particles_reordered[i_p, i_b].free
                    and self.particles_info_reordered[i_p, i_b].material_type != self.MATERIAL.PARTICLE
                ):
                    self.particles_reordered[i_p, i_b].pos = (
                        self.particles_reordered[i_p, i_b].pos + self.particles_reordered[i_p, i_b].dpos
                    )
                    self.particles_reordered[i_p, i_b].dpos.fill(0)
        _kernel_solve_collision.__annotations__ = dict(f=qd.i32)
        _kernel_solve_collision = qd.kernel(_kernel_solve_collision)

    from genesis.engine.couplers import legacy_coupler
    coupler_build = legacy_coupler.LegacyCoupler.build

    def build_coupler(self):
        coupler_build(self)
        if self._rigid_pbd:
            self._det = _Scratch(self.rigid_solver.n_links, self.pbd_solver._B, 6)
    legacy_coupler.LegacyCoupler.build = build_coupler

    pbd_build = PBDSolver.build

    def build(self):
        pbd_build(self)
        if self.is_active:
            self._det = _Scratch(self._n_particles, self._B, 3)
    PBDSolver.build = build
    for name in ("_kernel_solve_stretch", "_kernel_solve_bending", "_kernel_solve_collision", "_det_collision_terms"):
        setattr(PBDSolver, name, _DeterministicPBD.__dict__[name])
    PBDSolver._topogym_deterministic = True
    return info


# ---- PBD cloth contact (the blanket blow-up of 2026-10-03: trials mCa9CZt / r42VtjE, jobs/journal/2026-10-03/blanket_debug)
SIMULATOR_INSTABILITY = "simulator_instability"     # the episode end of a numerically unstable simulation
# Guard (a backstop; _bound_pbd_rigid_contacts removes the cause). PBD reports a particle's velocity over its last
# 0.625 ms substep. Runs that did not blow up reached at most 9.2 m/s, with Genesis' contact and the bounded one alike:
# brief substep-scale oscillations while a gripper pinned or squeezed the cloth (no particle moved faster than 0.5 m/s
# between 50 ms samples); a cloth dropped from the robot's reach lands below ~3 m/s. Every recorded Genesis blow-up
# crossed 10 m/s in one jump (11-24 m/s) and reached 1e3-1e5 m/s within three ticks; traced tick by tick: 21.5 -> 35 ->
# 159,526 and 20.1 -> 28.5 -> 5,337 m/s, the cloth falling off the table at the third tick. 20 m/s keeps twice the
# headroom over the fastest run that did not blow up and still ends every blow-up no later than the tick in which its
# cloth would fall (the guard runs before the task's predicates). A cloth particle faster than this means the
# simulation, not the agent, failed. These speeds are PBD's last-substep velocities (the particle speed through tooling
# 18). Since tooling 19 the guard reads what every consumer reads, the end-of-tick displacement over the tick
# (topogym/world/genesis_world.py read_state), an average over the tick's substeps: substep-scale oscillations read
# lower, and a blow-up's first tick may read lower too. The traced blow-ups reached 1e3-1e5 m/s by their third tick, so
# their displacement should cross the limit by then as well; this limit was not measured again with the displacement
# (docs/rcb/benchmarks/topogym.md, Cloth settle speed: follow-ups).
PARTICLE_SPEED_LIMIT_M_S = 20.0
# Depenetration allowance of the PBD-rigid contact (_bound_pbd_rigid_contacts): the speed beyond the colliding body's own
# approach and the particle's own inward motion at which a contact may push a particle out (resolving penetration left by
# an infeasible squeeze). Gravity's per-substep sag needs g * dt = 0.006 m/s; resting and pushed cloth never reaches it.
PBD_DEPENETRATION_MARGIN_M_S = 0.05


def _bound_pbd_rigid_contacts() -> float:
    """PBD scenes (blanket_flatten): resolve a cloth particle's rigid contacts together and bound the push-out by the
    contact's physics. Installed before the scene's first physics step (it replaces Genesis 1.2.1's
    LegacyCoupler.kernel_pbd_rigid_collide; the Genesis files are not edited, so the frozen blanket states' backend
    identity, which hashes those files, still matches). A no-op for scenes without PBD particles: the kernel runs only when
    rigid and PBD solvers are both active. Genesis 1.2.1-1.4.3 and main (2026-10-03) share the replaced code unchanged.

    Genesis (legacy_coupler.py:736-760, 895-916), once per substep after the cloth constraints: for each coupled geom in
    turn, a particle within the particle radius r of the geom is moved out along that geom's SDF normal by the whole
    penetration, and its velocity becomes the substep's whole displacement over dt (0.625 ms); the geom's link receives
    -m dv/dt. With one contact this is ordinary position-based contact. With two rigid surfaces closer than 2r (closed
    fingertips pressed onto the table through the cloth; finger pads closing on a cloth edge) the constraints cannot all
    hold: each geom undoes the previous one, the last geom wins, the particle moves by up to ~2r per substep, partly
    sideways along the tilted SDF normals at the fingertip's edges, and all of it becomes velocity. The cloth constraints
    pull the particle back in the next substep, which feeds the cycle: 0.96 -> 21 -> 35 -> 159,526 m/s in three ticks (the
    easy trial's replay), the cloth thrown metres off the table, "Cloth fell below the table".

    Here, per particle and substep, at the particle's pre-contact position x (after the cloth constraints; v its velocity,
    x0 its position at the substep's start):
      1. all coupled geoms are evaluated at x and their push-outs p_g = n_g (r - sd_g) summed (one simultaneous
         projection, independent of the geom order): one contact gives Genesis' push-out, orthogonal contacts (a table
         corner against a finger) are resolved together, opposing contacts (a squeeze) give their compromise, so a
         squeezed particle stays held between the two surfaces;
      2. the push-out along each contact normal is bounded by what that contact can physically do within the substep:
         stop the particle's own motion into the geom, follow the geom's own approach (its velocity at the contact point)
         and resolve old penetration at PBD_DEPENETRATION_MARGIN_M_S. The sum is scaled by the tightest bound, so no
         contact moves a particle out faster than the body pushing it (plus the margin), and none lags behind it (no
         tunnelling). Penetration an infeasible squeeze leaves is carried and resolved at the margin's speed;
      3. the velocity is the bounded displacement over dt (PBD's own velocity rule), so a contact cannot give a particle
         more normal speed than the colliding body's plus the margin: no energy from depenetration. The cloth
         constraints see the corrected positions (they start the next substep's solve), and because the correction now
         has the size of the physical motion they propagate it as ordinary motion;
      4. each geom's link receives Genesis' reaction to its own full penetration, m p_g / dt^2 (the PBD constraint force
         of that contact), so squeezed cloth still resists the gripper as before (the grip of a closing gripper). The
         reactions are summed per link in fixed point and applied once per link and substep (deterministic GPU physics,
         tooling v17: Genesis' func_apply_coupling_force adds them with float atomics in scheduler order).
    When one contact is active and its push-out is within the bound (cloth resting on the table, cloth pushed by a moving
    body, a falling particle stopped by the table: every contact of an unsqueezed cloth), the particle runs Genesis' own
    expressions, bit for bit. Returns the margin."""
    import quadrants as qd
    import genesis as gs
    import genesis.utils.sdf as sdf
    from genesis.engine.couplers import legacy_coupler
    from genesis.utils import array_class
    _deterministic_gpu_physics()   # allocates the coupler's fixed-point scratch at build (after genesis.init)
    installed = getattr(legacy_coupler.LegacyCoupler.kernel_pbd_rigid_collide, "_topogym_depenetration_margin_m_s", None)
    if installed is not None:
        return installed
    margin = float(PBD_DEPENETRATION_MARGIN_M_S)

    def _coupling_force(det, links_state, pos, force, link_idx, i_b):
        # genesis/engine/solvers/rigid/abd/misc.py:796-799 (func_apply_coupling_force), summed in fixed point
        torque = (pos - links_state.root_COM[link_idx, i_b]).cross(force)
        for k in qd.static(range(3)):
            fb = False
            tb = False
            if qd.static(gs.qd_float == qd.f64):   # non-finite: all-ones exponent, read from the bits (fast-math safe)
                fb = ((qd.bit_cast(force[k], qd.i64) >> 52) & 0x7FF) == 0x7FF
                tb = ((qd.bit_cast(torque[k], qd.i64) >> 52) & 0x7FF) == 0x7FF
            else:
                fb = ((qd.bit_cast(force[k], qd.i32) >> 23) & 0xFF) == 0xFF
                tb = ((qd.bit_cast(torque[k], qd.i32) >> 23) & 0xFF) == 0xFF
            if fb or tb or qd.abs(force[k]) > COUPLING_FORCE_LIMIT_N or qd.abs(torque[k]) > COUPLING_TORQUE_LIMIT_NM:
                det.bad[link_idx, i_b] = 1
            else:
                qd.atomic_add(det.acc[link_idx, i_b, k], qd.cast(qd.floor(force[k] * COUPLING_FX_SCALE + 0.5), qd.i64))
                qd.atomic_add(det.acc[link_idx, i_b, 3 + k],
                              qd.cast(qd.floor(torque[k] * COUPLING_FX_SCALE + 0.5), qd.i64))
    _coupling_force.__annotations__ = dict(det=qd.template(), links_state=array_class.LinksState)
    _coupling_force = qd.func(_coupling_force)

    @qd.data_oriented
    class _BoundedPBDRigidContact:
        def kernel_pbd_rigid_collide(self, geoms_state, geoms_info, links_state, sdf_info, rigid_global_info,
                                     collider_static_config):
            for i_p, i_b in qd.ndrange(self.pbd_solver._n_particles, self.sph_solver._B):
                if self.pbd_solver.particles_ng_reordered[i_p, i_b].active:
                    r = self.pbd_solver.particle_size / 2
                    dt = self.pbd_solver._substep_dt
                    x = self.pbd_solver.particles_reordered[i_p, i_b].pos
                    v = self.pbd_solver.particles_reordered[i_p, i_b].vel
                    x0 = self.pbd_solver.particles_reordered[i_p, i_b].ipos
                    mass = self.pbd_solver.particles_info_reordered[i_p, i_b].mass
                    push = qd.Vector.zero(gs.qd_float, 3)
                    n_contacts = 0
                    g_first = 0
                    n_first = qd.Vector.zero(gs.qd_float, 3)
                    sd_first = gs.qd_float(0.0)
                    # 1. every coupled geom at the pre-contact position; the push-outs summed
                    for i_g in range(self.rigid_solver.n_geoms):
                        if geoms_info.needs_coup[i_g]:
                            signed_dist = sdf.sdf_func_world(
                                geoms_state=geoms_state, geoms_info=geoms_info, sdf_info=sdf_info, pos_world=x,
                                geom_idx=i_g, batch_idx=i_b)
                            contact_normal = sdf.sdf_func_normal_world(
                                geoms_state=geoms_state, geoms_info=geoms_info, rigid_global_info=rigid_global_info,
                                collider_static_config=collider_static_config, sdf_info=sdf_info, pos_world=x,
                                geom_idx=i_g, batch_idx=i_b)
                            self.pbd_rigid_normal_reordered[i_p, i_b, i_g] = contact_normal
                            if signed_dist < r:
                                push = push + contact_normal * (r - signed_dist)
                                if n_contacts == 0:
                                    g_first = i_g
                                    n_first = contact_normal
                                    sd_first = signed_dist
                                n_contacts += 1
                    if n_contacts > 0:
                        # 2. the tightest physical bound of the push-out along a contact normal
                        scale = gs.qd_float(1.0)
                        if n_contacts == 1:
                            u = self.rigid_solver._func_vel_at_point(
                                pos_world=x, link_idx=geoms_info.link_idx[g_first], i_b=i_b, links_state=links_state)
                            allowed = (qd.max(u.dot(n_first), 0.0) + qd.max(-v.dot(n_first), 0.0) + margin) * dt
                            along = push.dot(n_first)
                            if along > allowed:
                                scale = allowed / along
                        else:
                            for i_g in range(self.rigid_solver.n_geoms):
                                if geoms_info.needs_coup[i_g]:
                                    signed_dist = sdf.sdf_func_world(
                                        geoms_state=geoms_state, geoms_info=geoms_info, sdf_info=sdf_info, pos_world=x,
                                        geom_idx=i_g, batch_idx=i_b)
                                    if signed_dist < r:
                                        contact_normal = sdf.sdf_func_normal_world(
                                            geoms_state=geoms_state, geoms_info=geoms_info,
                                            rigid_global_info=rigid_global_info,
                                            collider_static_config=collider_static_config, sdf_info=sdf_info,
                                            pos_world=x, geom_idx=i_g, batch_idx=i_b)
                                        u = self.rigid_solver._func_vel_at_point(
                                            pos_world=x, link_idx=geoms_info.link_idx[i_g], i_b=i_b,
                                            links_state=links_state)
                                        allowed = (qd.max(u.dot(contact_normal), 0.0)
                                                   + qd.max(-v.dot(contact_normal), 0.0) + margin) * dt
                                        along = push.dot(contact_normal)
                                        if along > allowed:
                                            scale = qd.min(scale, allowed / along)
                        new_pos = x
                        new_vel = v
                        if n_contacts == 1 and scale >= 1.0:
                            # Genesis' own expressions (legacy_coupler.py:907-924), bit for bit
                            stiffness = 1.0
                            energy_loss = 0.0
                            new_pos = x + stiffness * n_first * (self.pbd_solver.particle_size / 2 - sd_first)
                            new_vel = (new_pos - x0) / self.pbd_solver._substep_dt
                            delta_mv = mass * (new_vel - v)
                            force = (-delta_mv / self.rigid_solver._substep_dt) * (1 - energy_loss)
                            _coupling_force(self._det, links_state, x, force, geoms_info.link_idx[g_first], i_b)
                        else:
                            # 3. the bounded simultaneous push-out; the velocity from the displacement
                            new_pos = x + scale * push
                            new_vel = (new_pos - x0) / dt
                            # 4. each link: the reaction to its own full penetration
                            for i_g in range(self.rigid_solver.n_geoms):
                                if geoms_info.needs_coup[i_g]:
                                    signed_dist = sdf.sdf_func_world(
                                        geoms_state=geoms_state, geoms_info=geoms_info, sdf_info=sdf_info, pos_world=x,
                                        geom_idx=i_g, batch_idx=i_b)
                                    if signed_dist < r:
                                        contact_normal = sdf.sdf_func_normal_world(
                                            geoms_state=geoms_state, geoms_info=geoms_info,
                                            rigid_global_info=rigid_global_info,
                                            collider_static_config=collider_static_config, sdf_info=sdf_info,
                                            pos_world=x, geom_idx=i_g, batch_idx=i_b)
                                        force = -mass * contact_normal * (r - signed_dist) / (
                                            dt * self.rigid_solver._substep_dt)
                                        _coupling_force(self._det, links_state, x, force, geoms_info.link_idx[i_g], i_b)
                        self.pbd_solver.particles_reordered[i_p, i_b].pos = new_pos
                        self.pbd_solver.particles_reordered[i_p, i_b].vel = new_vel
            # each link once: Genesis' `cfrc_coupling -= torque / force` with the order-independent totals
            for i_l, i_b in qd.ndrange(self.rigid_solver.n_links, self.pbd_solver._B):
                frc = qd.Vector.zero(gs.qd_float, 3)
                trq = qd.Vector.zero(gs.qd_float, 3)
                for k in qd.static(range(3)):
                    frc[k] = qd.cast(self._det.acc[i_l, i_b, k], gs.qd_float) * COUPLING_FX_QUANTUM
                    trq[k] = qd.cast(self._det.acc[i_l, i_b, 3 + k], gs.qd_float) * COUPLING_FX_QUANTUM
                    self._det.acc[i_l, i_b, k] = 0
                    self._det.acc[i_l, i_b, 3 + k] = 0
                if self._det.bad[i_l, i_b] != 0:
                    self._det.bad[i_l, i_b] = 0
                    nan = gs.qd_float(0.0)
                    if qd.static(gs.qd_float == qd.f64):
                        nan = qd.bit_cast(qd.i64(0x7FF8000000000000), qd.f64)
                    else:
                        nan = qd.bit_cast(qd.i32(0x7FC00000), qd.f32)
                    frc = qd.Vector([nan, nan, nan], dt=gs.qd_float)
                    trq = frc
                links_state.cfrc_coupling_ang[i_l, i_b] = links_state.cfrc_coupling_ang[i_l, i_b] - trq
                links_state.cfrc_coupling_vel[i_l, i_b] = links_state.cfrc_coupling_vel[i_l, i_b] - frc
        # Real annotation objects (this module uses postponed annotations; Quadrants needs the types themselves)
        kernel_pbd_rigid_collide.__annotations__ = dict(
            geoms_state=array_class.GeomsState, geoms_info=array_class.GeomsInfo, links_state=array_class.LinksState,
            sdf_info=array_class.SDFInfo, rigid_global_info=array_class.RigidGlobalInfo,
            collider_static_config=qd.template())
        kernel_pbd_rigid_collide = qd.kernel(kernel_pbd_rigid_collide)

    kernel = _BoundedPBDRigidContact.__dict__["kernel_pbd_rigid_collide"]
    kernel._topogym_depenetration_margin_m_s = margin
    legacy_coupler.LegacyCoupler.kernel_pbd_rigid_collide = kernel
    return margin


def _guard_particle_speeds(task, on_trip: Callable[[dict], None]) -> bool:
    """Every physics tick (Task.update -> evaluate_state): a particle entity with a non-finite or faster than
    PARTICLE_SPEED_LIMIT_M_S particle ends the episode with failure reason SIMULATOR_INSTABILITY before the task's own
    predicates run (blanket: "Cloth fell below the table", which a blow-up reaches a tick or two later), so a numerical
    blow-up is never graded as the agent's success or as the task's failure: the standard service, its collect hook and
    both graders report it as an infrastructure error. It ends the episode through the task's own termination path, so
    the env stays consistent (the trajectory, its replay and the video are kept). The check reads the tick's velocities
    only; scenes without particles are unchanged."""
    original = task.evaluate_state

    def evaluate_state(state):
        for name, fields in (state.get("particles") or {}).items():
            v = np.asarray(fields.get("velocity_m_s"), dtype=np.float64).reshape(-1, 3)
            if not len(v):
                continue
            s2 = np.einsum("ij,ij->i", v, v)
            finite = bool(np.isfinite(s2).all())
            i = int(np.argmax(np.where(np.isfinite(s2), s2, np.inf)))
            speed = float(np.sqrt(s2[i])) if finite else float("inf")
            if not finite or speed > PARTICLE_SPEED_LIMIT_M_S:
                p = np.asarray(fields.get("position_m"), dtype=np.float64).reshape(-1, 3)
                on_trip(dict(kind="particle_speed", entity=str(name), particle=i, max_speed_m_s=speed if finite else None, finite=finite,
                             limit_m_s=PARTICLE_SPEED_LIMIT_M_S, physics_step=int(state.get("physics_step", -1)),
                             sim_time_s=float(state.get("sim_time_s", float("nan"))),
                             position_m=[float(x) for x in p[i]] if i < len(p) and np.isfinite(p[i]).all() else None))
                return False, SIMULATOR_INSTABILITY, {}
        return original(state)
    task.evaluate_state = evaluate_state
    return True


BINDING_API = 1


# --------------------------------------------------------------------------- grading replays (tooling v16, 2026-10-03)
# The user's decisions (2026-10-03): live-strict, replay-tolerant grading for the families whose physics runs on the GPU,
# which is not bit-deterministic (PBD cloth, the IPC FEM ropes and cords, lock_picking's GPU float32 rigid bodies), and a
# tolerant replay may only CONFIRM a strict success, never turn a failure into one. A genuine live success could miss
# its own fresh replay: blanket medium standard trial ihy7Nru succeeded live at row 3089 and the grader's replay of those
# rows did not (a speed spike restarted its confirmation at the last row). What the agent sees (the live episode, its own
# Session) is unchanged. A grading replay (Session.replay(..., grading=True): environment/sim/replay.py after a live
# success, both replays of the privileged tests/grade.py, the `replay` CLI) of one of these families
#   1. re-executes the trajectory's rows with the instance's own thresholds: a success within the rows is a STRICT
#      success (the grading record's strict_success and success_row);
#   2. if the episode has not ended after the last row, holds the final targets for up to GRADING_HOLD_S of simulated
#      time, stopping at the first success or failure, so a confirmation window that starts a few ticks later than live
#      can still complete; during this hold only, the task's predicate uses REPLAY_TOLERANCES: continuous thresholds,
#      each one of the task's own parameters loosened by a small slack and restored after the replay. A confirmation
#      window already running at the last row carries on. Binary and topological conditions, failure predicates and the
#      length of every confirmation window are never changed.
# The graders combine it: standard = the live success (strict) AND this replay's success (a live failure stays final:
# finalize.sh then replays plainly); privileged = both replays succeed AND at least one of them is a strict success within
# the agent's own rows (the trajectory itself reached the goal at least once). The record (_GradingReplay.record) carries
# the hold used, every relaxed threshold with its live and replay values and, over the confirmation window that ended in
# success, the worst measured value and whether it stayed within the live threshold (tolerance_needed: the pass needed
# the slack). The CPU families are not in the table: their grading replays are plain replays (bit-exact, the same
# verdicts and state hashes); a plain replay's success is a strict success.
GRADING_REVISION = "replay_tolerance_2026-10-03b"
GRADING_HOLD_S = 2.0
# family -> {threshold: (task parameter, the side that passes, slack in the parameter's unit, towards passing)}.
# blanket_flatten: the user's numbers (2026-10-03 20:50): coverage live 0.95 / hold 0.92; particle speed live 0.03 / hold
# 0.08 m/s (maximum_speed_m_s: the cheap "settled" gate and the final settling's speed; the 3 mm displacement from the start
# of confirmation, maximum_drift_m, and the 0.5 s window stay). Through tooling 18 the particle speed was PBD's last-substep
# velocity, which on cloth at rest spikes to 0.04-0.07 m/s and restarted the confirmation (ihy7Nru's replays); since tooling
# 19 (the user's decision, 2026-10-06) the world reports a particle's end-of-tick displacement over the tick
# (topogym/world/genesis_world.py read_state), and these numbers are unchanged. knot's rope speed: 2 x the largest
# replay-to-replay spread measured in a success's confirmation window (0.12 mm/s, lab 2026-10-03); its release conditions
# (terminal v5) are geometric and never relaxed. The other families: no measured spread that a small slack would absorb
# (docs/rcb/benchmarks/topogym.md, "Grading replays"), so the hold only; rope_threading's live thresholds are the release
# profile's (merged-v16: rope speed 10 mm/s, a 1 mm aperture allowance), never loosened again here.
REPLAY_TOLERANCES: dict[str, dict[str, tuple[str, str, float]]] = {
    "blanket_flatten": {"coverage": ("minimum_coverage_ratio", "at_least", -.03),
                        "particle_speed": ("maximum_speed_m_s", "at_most", .05)},
    "knot_untying": {"rope_speed": ("terminal.maximum_speed_m_s", "at_most", .00025)},
    "rope_threading": {},
    "slotted_post_ring": {},
    "orbits": {},
    "lock_picking": {},
}
# threshold -> the quantity the task compares with it at a tick, from the tick's world state and the task's metrics
_GRADING_VALUES: dict[str, Callable] = {
    "coverage": lambda task, state, metrics: metrics.get("coverage_ratio"),
    "particle_speed": lambda task, state, metrics: metrics.get("maximum_speed_m_s"),
    "rope_speed": lambda task, state, metrics: metrics.get("maximum_speed_m_s"),
}


def _parameter(config, path):
    for key in path.split("."):
        config = config[key]
    return config


def _set_parameter(config, path, value) -> None:
    *head, last = path.split(".")
    for key in head:
        config = config[key]
    config[last] = value


class _GradingReplay:
    """The grading-replay policy of one replay (the block comment above): a recorder of the confirmation window on the
    Session's task from the first row on, the hold after the rows with the replay thresholds, and the grading record;
    remove() restores the task's own thresholds and update."""

    def __init__(self, session):
        self.s, self.task = session, session.env._task
        self.thresholds = {}
        for name, (path, side, slack) in REPLAY_TOLERANCES[session.task].items():
            live = float(_parameter(self.task.config, path))
            self.thresholds[name] = dict(parameter=path, passes=side, live=live, replay=round(live + slack, 12),
                                         slack=slack)
        self.hold_limit = int(round(GRADING_HOLD_S * session.control_hz))
        self.hold_steps, self.relaxed = 0, False
        self.window: list = []          # (physics step, {threshold: value}) of the current confirmation window
        self._own_update = self.task.__dict__.get("update")
        self._update = self.task.update
        self.task.update = self._recording_update

    def _recording_update(self, state, physics_dt_s):
        result = self._update(state, physics_dt_s)
        if self.task._goal_active:      # this tick starts or extends the confirmation window
            self.window.append((int(state["physics_step"]),
                                {n: _GRADING_VALUES[n](self.task, state, result.metrics) for n in self.thresholds}))
        elif self.window:
            self.window = []
        return result

    def hold(self) -> None:
        """After the rows, while the episode has not ended: the replay thresholds, then the final targets until the
        episode ends or for at most hold_limit control steps."""
        s = self.s
        if s.episode_end is not None or s.episode_done:
            return
        for t in self.thresholds.values():
            _set_parameter(self.task.config, t["parameter"], t["replay"])
        self.relaxed = True
        while s.episode_end is None and not s.episode_done and self.hold_steps < self.hold_limit:
            s.step(s.hold_action())
            self.hold_steps += 1

    def remove(self) -> None:
        if self.relaxed:
            for t in self.thresholds.values():
                _set_parameter(self.task.config, t["parameter"], t["live"])
        if self._own_update is None:
            self.task.__dict__.pop("update", None)
        else:
            self.task.update = self._own_update

    def record(self, rows: int) -> dict:
        success = bool(self.s.success())
        strict = success and self.hold_steps == 0
        out = dict(revision=GRADING_REVISION, rows=int(rows), strict_success=strict,
                   success_row=int(rows) if strict else None, hold_steps=self.hold_steps,
                   hold_limit_steps=self.hold_limit, success_in_hold=success and self.hold_steps > 0, thresholds={},
                   tolerance_needed=False)
        window = self.window if success else []
        for name, t in self.thresholds.items():
            entry = dict(t)
            values = [v[name] for _, v in window if v.get(name) is not None]
            if values:
                worst = min(values) if t["passes"] == "at_least" else max(values)
                held = worst >= t["live"] if t["passes"] == "at_least" else worst <= t["live"]
                entry.update(window_ticks=len(window), window_worst=float(worst), live_held=bool(held))
                out["tolerance_needed"] = out["tolerance_needed"] or not held
            out["thresholds"][name] = entry
        return out


def strict_goal(statuses) -> tuple[int, int] | None:
    """(1-based replay, row) of the first graded replay that met the instance's own (strict) goal within the trajectory's
    rows, or None. A plain replay (a CPU family: no grading record) uses the instance's thresholds throughout."""
    for i, st in enumerate(statuses, 1):
        g = st.get("grading")
        if st.get("success") and (g is None or g.get("strict_success")):
            return i, int(g["success_row"]) if g is not None else int(st.get("sim_steps", 0))
    return None


# --------------------------------------------------------------------------- libuipc build per GPU
# The image holds two builds of one libuipc recipe (pyuipc 0.0.25+topogym.det1.cuda128: libuipc 292c98c3 plus the
# determinism patches, nvcc 12.8; images/robotangle/Dockerfile). Both have the same version and source commit, which the
# frozen IPC settled states hold, so either restores them. They differ only in their uipc-build.json, whose sha256 names
# the build (scripts/robotangle/release.json and every runtime binding: uipc_builds):
#   audited  the wheel of every evidence run, in site-packages (/opt/uipc-build.json): SASS sm_89 and sm_120, PTX compute_120;
#   sm86     its own prefix /opt/uipc_sm86: SASS sm_86 (runs on 8.6 and 8.7), PTX compute_86 (JIT-compiled on 9.x and 10.x).
# The rule: compute capability 8.9 or 12.x loads the audited wheel, any other GPU the sm86 build, no visible GPU the audited
# wheel (no libuipc scene runs there). A Session applies it before anything imports uipc and refuses a choice that
# contradicts it; installed_runtime() and the session's runtime_binding name the build in use.
UIPC_BUILDS = {"audited": None, "sm86": "/opt/uipc_sm86"}   # build -> its prefix (site-packages/, uipc-build.json); None: site-packages
DEFAULT_UIPC_BUILD = "/opt/uipc-build.json"
_GPU_CAPABILITIES: list | None = None
_UIPC_BUILD: dict | None = None


def gpu_capabilities() -> list[tuple[int, int]]:
    """Compute capabilities of the CUDA devices this process sees (CUDA_VISIBLE_DEVICES applies), from the CUDA driver API
    through ctypes: no context, no torch. Empty without a driver or a visible device."""
    global _GPU_CAPABILITIES
    if _GPU_CAPABILITIES is None:
        import ctypes
        caps = []
        try:
            cuda = ctypes.CDLL("libcuda.so.1")
        except OSError:
            cuda = None
        count = ctypes.c_int(0)
        if cuda is not None and cuda.cuInit(0) == 0 and cuda.cuDeviceGetCount(ctypes.byref(count)) == 0:
            for index in range(count.value):
                device, major, minor = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
                if (cuda.cuDeviceGet(ctypes.byref(device), index) != 0
                        or cuda.cuDeviceGetAttribute(ctypes.byref(major), 75, device) != 0     # ..._COMPUTE_CAPABILITY_MAJOR
                        or cuda.cuDeviceGetAttribute(ctypes.byref(minor), 76, device) != 0):   # ..._COMPUTE_CAPABILITY_MINOR
                    raise RuntimeError(f"CUDA driver error while reading the compute capability of device {index}")
                caps.append((major.value, minor.value))
        _GPU_CAPABILITIES = caps
    return list(_GPU_CAPABILITIES)


def uipc_build_for(capabilities) -> str:
    """The rule (above): the libuipc build for the visible GPUs. Mixed compute capabilities are refused: a process loads
    one build, and a RoboTangle container sees exactly one GPU (Nyx needs one)."""
    caps = sorted({tuple(c) for c in capabilities})
    if len(caps) > 1:
        raise RuntimeError("The visible GPUs have different compute capabilities ("
                           + ", ".join(f"{a}.{b}" for a, b in caps) + "): a process loads one libuipc build. Give the "
                           "container exactly one GPU, as RoboTangle needs, or GPUs of one model.")
    if not caps:
        return "audited"
    major, minor = caps[0]
    return "audited" if (major, minor) == (8, 9) or major == 12 else "sm86"


def _sha256_file(path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def select_uipc_build(capability: tuple[int, int] | None = None) -> dict:
    """Choose this process's libuipc build by the rule, once and before uipc is imported: the sm86 prefix goes first on
    sys.path when the rule picks it. `capability` stands in for the GPU's (tests); a Session refuses a choice that
    contradicts the visible GPU (uipc_build_in_use). Returns the build in use: its name, the compute capability it was
    chosen for, its uipc-build.json and that file's sha256, and the uipc package Python imports."""
    global _UIPC_BUILD
    if _UIPC_BUILD is not None:
        return _UIPC_BUILD
    import importlib
    import importlib.util
    caps = [tuple(capability)] if capability is not None else gpu_capabilities()
    name = uipc_build_for(caps)
    prefix = UIPC_BUILDS[name]
    record = Path(prefix, "uipc-build.json") if prefix else Path(DEFAULT_UIPC_BUILD)
    site = Path(prefix, "site-packages") if prefix else None
    if site is not None:
        loaded = sys.modules.get("uipc")
        if loaded is not None and not Path(loaded.__file__).resolve().is_relative_to(site):
            raise InstanceMismatch(f"uipc was imported from {loaded.__file__} before the Session chose the {name} build ({site})")
        if not record.is_file():
            raise InstanceMismatch(f"this image has no {name} libuipc build ({record})")
        if str(site) not in sys.path:
            sys.path.insert(0, str(site))
            importlib.invalidate_caches()
    spec = importlib.util.find_spec("uipc")
    module = Path(spec.origin).resolve() if spec is not None and spec.origin else None
    others = [Path(p, "site-packages") for n, p in UIPC_BUILDS.items() if p and n != name]
    if module is not None and ((site is not None and not module.is_relative_to(site))
                               or any(module.is_relative_to(o) for o in others)):
        raise InstanceMismatch(f"uipc resolves to {module}, not to the {name} libuipc build")
    _UIPC_BUILD = dict(build=name, capability=list(caps[0]) if caps else None, uipc_build=str(record),
                       uipc_build_sha256=_sha256_file(record), module=str(module) if module else None)
    return _UIPC_BUILD


def uipc_build_in_use() -> dict:
    """select_uipc_build(), refused when it contradicts the rule for the visible GPU (a forced choice)."""
    chosen = select_uipc_build()
    rule = uipc_build_for(gpu_capabilities())
    if chosen["build"] != rule:
        raise InstanceMismatch(f"libuipc build {chosen['build']} (chosen for compute capability {chosen['capability']}) "
                               f"contradicts the rule for the visible GPU ({gpu_capabilities() or 'none'}: {rule})")
    return chosen


def installed_runtime(root=None) -> dict:
    """topogym.simulator.frozen_binding.installed_runtime() for an image with two libuipc builds: uipc_builds = the builds
    the rule chooses from (name -> its uipc-build.json sha256, None if absent), uipc_build_sha256 = the one this process
    uses (select_uipc_build)."""
    from topogym.simulator.frozen_binding import installed_runtime as image_runtime
    runtime = image_runtime(root)
    runtime["uipc_builds"] = {name: _sha256_file(Path(prefix, "uipc-build.json") if prefix else DEFAULT_UIPC_BUILD)
                              for name, prefix in UIPC_BUILDS.items()}
    runtime["uipc_build_sha256"] = select_uipc_build()["uipc_build_sha256"]
    return runtime


def check_runtime(lock: dict) -> dict:
    """frozen_binding.check_runtime() for an image with two libuipc builds. The binding's runtime names the default
    (audited) build and lock["uipc_builds"] both allowed ones: the image must hold exactly those, and this process must use
    the one the rule chooses for the visible GPU."""
    from topogym.simulator.frozen_binding import BindingMismatch, validate_lock
    validate_lock(lock)
    builds = lock.get("uipc_builds")
    if (not isinstance(builds, dict) or set(builds) != set(UIPC_BUILDS)
            or builds["audited"] != lock["runtime"].get("uipc_build_sha256")):
        raise BindingMismatch(f"Runtime binding lacks the libuipc builds {sorted(UIPC_BUILDS)} (uipc_builds; audited = runtime's)")
    chosen = uipc_build_in_use()
    expected = dict(lock["runtime"], uipc_builds=builds, uipc_build_sha256=builds[chosen["build"]])
    actual = installed_runtime()
    if actual != expected:
        raise BindingMismatch("Actual installed source/dependencies/libuipc builds differ from the bound runtime")
    return actual


class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, eval_index: int | None = None,
                 variation_id: str | None = None, seed: int | None = None, task_parameters: dict | None = None,
                 simulator_overrides: dict | None = None, gripper_space: str | None = None,
                 strict: bool = True, max_steps: int | None = None, backend: str = DEFAULT_BACKEND):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        if backend != "cuda":
            raise ValueError("TopoGym sessions follow the GPU-backend rule; the physics device comes from the instance")
        self.task, self.spec = task, dict(TASKS[task])
        self.runtime_binding = None
        self.uipc_build = uipc_build_in_use()     # the libuipc build, by the rule, before anything imports uipc
        inst = None
        if instance is not None:
            if gripper_space is not None:
                raise ValueError("The frozen instance owns gripper_space")
            if any(x is not None for x in (eval_index, variation_id, seed, task_parameters, simulator_overrides)):
                raise ValueError("frozen instance cannot be combined with scene overrides")
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            lock_path = Path(instance).resolve().parent / "runtime_binding.json"
            if lock_path.is_file():
                from topogym.simulator.frozen_binding import check_inputs, binding_id
                try:
                    lock = json.loads(lock_path.read_text())
                    check_inputs(instance, __file__, lock)
                    runtime = check_runtime(lock)       # this tooling's: both libuipc builds and the one in use
                except (OSError, ValueError, KeyError) as exc:
                    raise InstanceMismatch(f"Frozen runtime binding failed: {exc}") from exc
                self.runtime_binding = dict(binding_id=binding_id(lock), runtime=runtime, uipc_build=self.uipc_build,
                                            creation_source=lock["creation_source"], image=lock["image"])
            eval_index = inst["eval_index"]
            cfg = dict(inst["simulator"])       # the frozen configuration: the task directory's own copy
            cfg["task_parameters"] = dict(cfg.get("task_parameters", {}))
            dependency = cfg["task_parameters"].get("initial_state_path")
            if dependency and not Path(dependency).is_absolute():
                cfg["task_parameters"]["initial_state_path"] = str(Path(instance).resolve().parent / dependency)
            settled = cfg.get("ipc_settled_state")
            if settled and not Path(settled).is_absolute():
                cfg["ipc_settled_state"] = str(Path(instance).resolve().parent / settled)
        else:
            cfg = simulator_config(task, eval_index, variation_id=variation_id, seed=seed,
                                   task_parameters=task_parameters, simulator_overrides=simulator_overrides)
        self.eval_index, self.max_steps, self.backend = eval_index, int(max_steps or MAX_STEPS), backend
        self.config = cfg
        if self.spec["fixture"]:
            _register_cube()
        from topogym.simulator.config import SimulatorConfig
        from topogym.simulator.env import Env
        t0 = time.time()
        _log(f"building {cfg['task_id']} / {cfg['variation_id']} (seed {cfg['seed']}, eval index {self.eval_index}) ...")
        if cfg.get("compute_backend") == "cpu":
            # Genesis' CPU getters are torch CPU ops, and torch sizes its pool to the host (256 threads on lab), which spins
            # under a container's CPU quota. The results are the same at any count (2026-10-02 study).
            import torch
            torch.set_num_threads(4)
        self.deterministic_physics = _deterministic_gpu_physics()   # before genesis.init / the first scene build
        margin = _bound_pbd_rigid_contacts()   # before the scene's first physics step (kernels compile on first use)
        _register_runtime_physics(margin)
        self.env = Env(SimulatorConfig(**cfg))
        # Tooling v7: frames come only from env.sensor_frame() (render_frame / render_grid / render_depth / videos), so the
        # per-step observation skips the camera pass and a frame is rendered when asked (image 0.2.9; physics identical).
        self.env.defer_rgb = True
        self.env.reset(seed=int(cfg["seed"]))
        self.fem_checkpoint_store_bounded = _drop_fem_gradient_checkpoints(self.env)
        self.knot_predicate_vectorized = _speed_up_knot_predicate(cfg["task_id"])
        self.settle_only_when_reached = _settle_only_when_reached(self.env._task)
        # The bounded PBD-rigid contact applies when this scene couples rigid bodies with PBD particles (blanket_flatten)
        self.pbd_depenetration_margin_m_s = margin if getattr(self.env._world.scene.sim.coupler, "_rigid_pbd", False) else None
        self.instability: dict | None = None    # the first simulator instability of this episode (None: none)
        self.particle_speed_guard = _guard_particle_speeds(self.env._task, self._on_instability)
        if not self.spec["fixture"]:
            # The family catalog is only a short catalog label. Public goals
            # come from the selected instance, for both Session and limited SPEC.
            self.spec["text"] = self.env._task.public_instruction()
        self.gripper_space = (inst.get("gripper_space", "width") if inst else gripper_space or "width")
        self.robot = _Robot(self.env._robot, self.env.timing_spec, gripper_space=self.gripper_space)
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
        self.rules = _install_rules(self)    # R1-R4 (2026-10-03), after Env.reset recorded the frozen first checkpoint
        _slog("session_start", task=task, eval_index=self.eval_index)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self.n_steps))
        # Every episode -- live or replayed, in this process or a fresh one -- starts from a restore of the frozen state.
        self._restore()
        self.asset_identity = self._asset_identity()
        self.instance_sha = self.state_sha()
        self.initial_state = _initial_state_record(self.env)
        self.instance_generated = (self.initial_state or {}).get("source") == "generated"
        expected = inst.get("state_sha") if inst else None
        self.instance_exact = expected is None or expected == self.instance_sha
        assets_match = inst is None or inst.get("asset_identity", self.asset_identity) == self.asset_identity
        if self.instance_generated:
            # The frozen evidence state (state_sha) was prepared on another GPU. The instance is its recipe, realized on
            # this GPU: the stored archive's scene identity and preparation equal the ones run here (recipe_match). Its
            # state hash is this run's own; every process of the run restores the same generated archive.
            gen = self.initial_state
            self.instance_matches = assets_match and (expected is None or gen.get("recipe_match") is True)
            msg = (f"initial state generated for {gen.get('resource_profile')} (cache {gen.get('cache')}; the frozen "
                   f"state {expected} belongs to {gen.get('stored_profile')}): state_sha {self.instance_sha}")
            if not self.instance_matches:
                if strict or self.runtime_binding is not None:
                    self.env.close()
                    raise InstanceMismatch(msg + "; it does not realize this instance's recipe and assets")
                _log("WARNING:", msg, "does not realize this instance's recipe and assets")
            else:
                _log(msg)
        else:
            self.instance_matches = assets_match and (self.instance_exact or (inst is not None and self._poses_match(inst)))
        if not self.instance_generated and (not self.instance_exact or not assets_match):
            msg = f"instance state sha {self.instance_sha} != expected {expected}"
            if strict or self.runtime_binding is not None:
                self.env.close()
                raise InstanceMismatch(msg + "; exact frozen state and assets are required by candidate tooling")
            if self.instance_matches:
                _log(f"WARNING: {msg}, but every object/joint pose matches within tolerance")
            else:
                if strict:
                    self.env.close()
                    raise InstanceMismatch(msg + " and poses differ (asset / simulator drift?)")
                _log("WARNING:", msg, "and poses differ")
        _log(f"instance ready in {time.time() - t0:.0f}s; state_sha={self.instance_sha}; max_steps={self.max_steps}")

    def _asset_identity(self):
        """Compare actual generated assets, normalizing only their temporary root."""
        build = self.env._asset_build
        root = str(build.root.resolve()).encode()
        return {name: hashlib.sha256((build.root / name).read_bytes().replace(root, b"<instance-assets>")).hexdigest()
                for name in sorted(build.files)}

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2, joint_tol: float = 2e-3) -> bool:
        try:
            objs = self.objects()
            if set(objs) != set(inst.get("objects") or {}):
                return False
            soft = self._soft_state()
            reference = inst.get("soft_state") or {}
            if set(soft) != set(reference):
                return False  # old centroid-only soft instances require exact state identity
            for name, fields in soft.items():
                if set(fields) != set(reference[name]):
                    return False
                for field, value in fields.items():
                    current, wanted = np.asarray(value), np.asarray(reference[name][field])
                    tolerance = pos_tol if field in ("position_m", "vertices_m") else 2e-3
                    if current.shape != wanted.shape or not np.allclose(current, wanted, atol=tolerance, rtol=0):
                        return False
            for name, ref in (inst.get("objects") or {}).items():
                cur = objs.get(name)
                if cur is None:
                    return False
                if np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                if "orientation_wxyz" not in cur or "orientation_wxyz" not in ref:
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

    def _soft_state(self) -> dict:
        world = self.env._world.read_state()
        return {name: {key: _plain(value) for key, value in fields.items()
                       if key in ("position_m", "vertices_m", "velocity_m_s")}
                for kind in ("particles", "fem") for name, fields in world.get(kind, {}).items()
                if name in self._entities() and isinstance(fields, dict)}

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
        self._recorded_ticks = []
        self._saved_recording = None
        self.episode_done = False
        self.episode_end = None
        self.n_steps = 0
        self.physics_steps = 0
        self.sim_time_s = 0.0
        self.last_step_ticks = 0
        self._reward = 0.0
        self.instability = None
        self.env.privileged.rewind_to(self.S0)
        self._targets = self.robot.targets()

    def _on_instability(self, info: dict) -> None:
        """A simulator breakdown (the particle speed guard, _guard_particle_speeds; the policy's Layer 3, _install_rules):
        keep the first evidence of this episode."""
        if self.instability is None:
            self.instability = info
            _log(f"SIMULATOR INSTABILITY at physics step {info.get('physics_step')}: {breakdown_words(info)}. Unless an arm "
                 f"was forcing within {FORCING['attribution_s']:g} s before, the episode ends with episode_end "
                 f"'{SIMULATOR_INSTABILITY}': a simulator failure, graded as an infrastructure error, not as the task's "
                 "failure predicate; reset() starts again from the frozen state")

    @property
    def action_dim(self) -> int:
        return self.robot.action_dim

    @property
    def action_layout(self) -> list[str]:
        return list(self.robot.layout)

    def step(self, action, *, _physics_steps=None) -> bool:
        """Apply one low-level action (ACTION_LAYOUT: per arm its joint targets, then its declared gripper target) for one control
        step. Out-of-limit values are clipped to the joint / gripper limits. Returns True once max_steps control steps
        have run (a runaway guard, not a budget); further steps raise. After the task's own episode end (success or a
        failure predicate) steps return True without changing the scene or execution ledger. A numerically unstable
        simulation (a particle faster than PARTICLE_SPEED_LIMIT_M_S) ends the episode the same way, with episode_end
        SIMULATOR_INSTABILITY and the evidence in self.instability: a simulator failure, not the task's."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != self.action_dim:
            raise ValueError(f"action must have {self.action_dim} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.episode_done:
            raise PrimitiveError(f"{self.max_steps} control steps reached (runaway guard); call reset() before stepping again")
        if self.episode_end is not None:
            return True
        target = self.robot.clip(a.astype(np.float64))
        target = self.table_guard.apply(target, self._targets)   # R4: no gripper vertex below TABLE_GUARD_MARGIN_M
        command = self.robot.command(target)
        self._video_begin()
        kwargs = {} if _physics_steps is None else {"_physics_steps": int(_physics_steps)}
        try:
            _, reward, terminated, truncated, info = self.env.step(command, **kwargs)
        except Exception as exc:
            if getattr(self.env, "_faulted", False):
                raise RuntimeError("simulator fault during control execution; result not committed") from exc
            raise
        self.last_step_ticks = int(info["physics_steps"])
        self.physics_steps += self.last_step_ticks
        self.sim_time_s += float(info["action_duration_s"])
        self._reward = float(reward)
        if terminated or truncated:
            self.episode_end = "success" if info["task_success"] else (info.get("termination_reason") or "task_failed")
        if self._recording is not None:
            self._recording.append(target.astype(np.float32).copy())
            self._recorded_ticks.append(self.last_step_ticks)
        self._targets = target
        self.n_steps += 1
        if self._video is not None:
            self._video_add()
        if self.n_steps >= self.max_steps:
            self.episode_done = True
        return self.episode_done or self.episode_end is not None

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current joint targets (what the robot does when a primitive is idle)."""
        return self._targets.copy()

    def safety(self, *, episode: bool = False) -> dict[str, Any]:
        """What the physical-validity policy measured since the previous safety() call (episode=True: since the last
        reset), against its limits: forcing (the largest contact force an arm or a part it holds pressed with, the drive
        load meanwhile, the longest run of the forcing condition, the forcing events: evidence only, but a simulator
        breakdown within FORCING["attribution_s"] of forcing is the agent's failure), the deepest task contact and
        held-finger contact (mm; rigid families: evidence only, a success with a review event is held for review; deeper
        than BREAKDOWN_PENETRATION_M is a solver breakdown), the lowest
        soft-body volume ratio and the longest time at or below 0 (IPC families: 0.25 s ends it), the worst cord
        attachment stretch, the control steps whose gripper target the table guard stopped (table_guard_words()), and IK
        solutions far from the current joints (move_ee). Reading it does not touch the simulation."""
        return self.monitor.read(episode=episode)

    def ik_jump(self, arm: str, q_arm) -> tuple[float, str]:
        """(largest |q_arm - the measured joints of `arm`| in rad, that joint's name): how far an IK solution lies from
        where the arm is. A large jump for a small pose change is another IK branch, which swings the arm."""
        sl = [self.robot.arm_joints.index(n) for n in self.robot.groups[arm].arm_joints]
        d = np.abs(np.asarray(q_arm, dtype=np.float64).reshape(-1) - self.robot.arm_q()[sl])
        j = int(np.argmax(d))
        return float(d[j]), self.robot.groups[arm].arm_joints[j]

    def success(self) -> bool:
        return bool(self.env.is_solved())

    def status(self) -> dict[str, Any]:
        """The episode so far. "review": its review events (deep task contacts, CONTACT_RULE; None: none): a success with
        any is held for review by the graders instead of being credited automatically. "forcing": its forcing events
        (FORCING; None: none): evidence only."""
        return {"success": self.success(), "progress": round(self._reward, 4), "sim_steps": int(self.n_steps),
                "physics_steps": self.physics_steps, "sim_time_s": self.sim_time_s,
                "resets": self._resets, "state_sha": self.state_sha(), "episode_end": self.episode_end,
                "instability": self.instability, "instance_exact": self.instance_exact,
                "instance_generated": self.instance_generated,
                "runtime_binding": self.runtime_binding, "review": self.monitor.review(), "forcing": self.monitor.forcing()}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []
        self._recorded_ticks = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, self.action_dim), np.float32)
        self._saved_recording = (acts.copy(), np.asarray(self._recorded_ticks, dtype=np.int64))
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=self.success())
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        extra = {}
        saved = getattr(self, "_saved_recording", None)
        if saved is not None and np.array_equal(actions, saved[0]):
            extra = dict(trajectory_version=2, physics_steps_per_action=saved[1])
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, topogym_task=self.config["task_id"],
                 variation_id=self.config["variation_id"], eval_index=-1 if self.eval_index is None else self.eval_index,
                 scene_seed=int(self.config["seed"]), instance_sha=self.instance_sha,
                 action_dim=self.action_dim, action_layout=np.array(self.action_layout),
                 gripper_space=self.gripper_space, meta=json.dumps(meta or {}), **extra)

    def replay(self, actions: np.ndarray, *, physics_steps=None, grading: bool = False) -> dict[str, Any]:
        """Open-loop replay after reset(): what the verifier does, twice, in its own process. grading=True is the
        graders' replay: for a family of REPLAY_TOLERANCES (physics on the GPU) the rows run with the instance's own
        thresholds (a success there is strict) and, if the episode has not ended after the last row, the final targets
        are held for up to GRADING_HOLD_S with the listed continuous thresholds loosened; the status then carries a
        "grading" record. Every other family replays as without it."""
        self.reset()
        if self._video is not None:
            self._video_begin()
        if physics_steps is not None and len(physics_steps) != len(actions):
            raise ValueError("tick ledger length differs from actions")
        policy = _GradingReplay(self) if grading and self.task in REPLAY_TOLERANCES else None
        try:
            for i, a in enumerate(np.asarray(actions, dtype=np.float32)):
                if self.step(a, _physics_steps=None if physics_steps is None else physics_steps[i]):
                    break
            rows = self.n_steps
            if policy is not None:
                policy.hold()
        finally:
            if policy is not None:
                policy.remove()
        st = self.status()
        if policy is not None:
            st["grading"] = policy.record(rows)
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

    def render_review_frames(self, actions, events, out_dir, *, physics_steps=None, offsets=(-10, 0, 10),
                             size=(424, 240)) -> list[str]:
        """Frames around events (a success held for review: status()["review"]["events"] and its forcing events): replays
        the rows from the frozen state as replay() does and saves render_grid() at each event's control step + `offsets`
        (clamped to the first step; control steps past the rows hold the final targets). Returns the files written;
        rendering does not touch the physics."""
        from PIL import Image
        want = sorted({max(1, int(e["step"]) + o) for e in events for o in offsets})
        if not want:
            return []
        os.makedirs(out_dir, exist_ok=True)
        acts, files = np.asarray(actions, dtype=np.float32), []
        self.reset()
        while self.n_steps < want[-1]:
            k = self.n_steps
            done = (self.step(acts[k], _physics_steps=None if physics_steps is None else physics_steps[k]) if k < len(acts)
                    else self.step(self.hold_action()))
            if self.n_steps in want and self.n_steps > k:
                path = os.path.join(str(out_dir), f"step_{self.n_steps:05d}.png")
                Image.fromarray(self.render_grid(size=size)).save(path)
                files.append(path)
            if done:
                break
        return files

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 2, fps: int = 15,
                     cameras=None, cols=3, size=(424, 240), physics_steps=None) -> dict[str, Any]:
        """Record one replay through the shared SensorFrame recording module.

        Legacy layout/sampling arguments no longer create a separate writer.
        The shared recording manifest and physical timestamps live beside the video.
        """
        self.start_video(path, fps=fps)
        self._video["grid"] = dict(cameras=cameras, cols=cols, size=size)
        status = self.replay(actions, physics_steps=physics_steps)
        self.stop_video()
        return {**status, "video": str(path)}

    def start_video(self, path: str | Path, fps: int = 15, every: int | None = None) -> None:
        if self._video is not None:
            raise RuntimeError("finish the current recording before starting another")
        if not np.isfinite(fps) or not 0 < fps <= self.control_hz:
            raise ValueError("video fps must be positive and no greater than control_hz")
        # Arm only: replay restores its initial state before taking the first frame.
        self._video = {"path": str(path), "fps": fps, "session": None, "error": None}

    def _video_begin(self):
        v = self._video
        if v is None or v["session"] is not None or v["error"]:
            return
        try:
            from topogym.recording import RecordingSession
            path = Path(v["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix=path.stem + ".recording-", dir=path.parent))
            rec = RecordingSession(root / "recording", fps=v["fps"], metadata={
                "task": self.task, "instance_sha": self.instance_sha, "scope": "frozen-instance replay"})
            v["session"] = rec
            rec.__enter__()
            rec.append(self._recording_frame())
        except Exception as exc:
            v["error"] = repr(exc)

    def _video_add(self) -> None:
        self._video_begin()
        v = self._video
        if v["error"]:
            return
        try:
            frame = self._recording_frame()
            if frame.state_id != v["session"].previous_state_id:
                v["session"].append(frame)
        except Exception as exc:
            v["error"] = repr(exc)

    def _recording_frame(self, video=None):
        """Keep Harbor's all-camera composite; shared recording owns its clock/writer."""
        from dataclasses import replace
        frame = self.env.sensor_frame()
        settings = video if video is not None else self._video
        pixels = self.render_grid(**settings["grid"]) if settings and "grid" in settings else self._video_frame()
        return replace(frame, rgb={"combined": pixels})

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
        self._video_begin()
        v, self._video = self._video, None
        rec = v["session"]
        if v["error"]:
            if rec is not None:
                rec.close(commit=False)
            raise RuntimeError(v["error"])
        import shutil
        from PIL import Image
        try:
            frame = self._recording_frame(v)
            rec.append_final(frame)
            rec.finish(self.status())
            rec.close(commit=True)
            first = next(iter(frame.rgb))
            from topogym.recording.encoding import probe
            validation = probe(rec.output / "videos" / (first + ".mp4"), decode=True)
            if validation["frames"] != rec.frame_count:
                raise RuntimeError("recorded video and frame map have different lengths")
            shutil.copyfile(rec.output / "videos" / (first + ".mp4"), v["path"])
            frame_map = Path(v["path"]).with_suffix(".frame_map.jsonl")
            shutil.copyfile(rec.output / "frame_map.jsonl", frame_map)
            manifest = json.loads((rec.output / "recording_manifest.json").read_text())
            manifest["videos"][first]["path"] = Path(v["path"]).name
            manifest["frame_map"]["path"] = frame_map.name
            manifest["validation"] = validation
            atomic_json(Path(v["path"]).with_suffix(".recording_manifest.json"), manifest)
            Image.fromarray(np.asarray(frame.rgb[first])).save(Path(v["path"]).with_suffix(".last.png"))
        finally:
            rec.close(commit=False)
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
        """Current joint positions in action layout (gripper entries use the frozen instance command space)."""
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
        if ga.model in {"ipc_soft_band_v1", "pbd_local_patch_v1"}:
            mechanics = ("an elastic IPC attachment" if ga.model == "ipc_soft_band_v1"
                         else "a local kinematic PBD attachment")
            return (f"assisted grasping ({ga.model}): closing intent and bilateral finger proximity to a material patch "
                    f"of {parts} must persist for {ga.stable_time_s:g} s, with penetration at most "
                    f"{ga.max_penetration_m * 1000:g} mm and the TCP within {ga.max_tcp_distance_m * 100:g} cm. "
                    f"The admitted patch follows through {mechanics}; the rest remains deformable. "
                    f"Opening by more than {ga.intent_deadband * 100:g} % of gripper travel releases it. "
                    f"A hold is lost on excessive opening, material strain, invalid volume or follow error above "
                    f"{ga.max_translation_error_m * 1000:g} mm; a lost hand must open before reacquiring. "
                    "Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. "
                    "Patch radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets")
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
                               "effort_limit": round(float(r.drive_force[name][i]), 6), "group": f"gripper_{name}" if finger else f"arm_{name}",
                               "note": "velocity_limit: the simulation enforces none (the PD tracking sets the speed); effort_limit: "
                                       "the drive force clamp" + ("; the gripper action is the opening width, converted to this "
                                                                  "coordinate" if finger else
                                                                  " (arm joints: capped by this benchmark's safety rules, so an arm "
                                                                  "pushing against an obstacle stalls at this torque)")})
                gains[jn] = {"stiffness": float(g.kp[i]), "damping": float(g.kv[i])}
            lo, hi = r.limits[r.grip_index[name]]
            grip[name] = {"joints": list(g.finger_joints), "opening_m": [lo, hi], "tcp_frame": r.tcp_frames[name],
                          "command": f"joint_position entry {name}_gripper (index {r.grip_index[name]}) and the ee_pose {name}_gripper "
                                     f"entry: the target opening width in metres, {lo:g} = closed .. {hi:g} = open (the nominal gap "
                                     f"between the finger pads), converted to the gripper's native drive coordinate; it switches at "
                                     f"the row (no interpolation). Grasping: {self.grasp_rules()}"}
            if r.gripper_space == "native":
                unit = "m" if g.gripper_field.endswith("_m") else "rad"
                grip[name].update(opening_m=[float(r.width_table[name][0][0]), float(r.width_table[name][0][-1])],
                    command_space="native", command_unit=unit, command_limits=[lo, hi],
                    open_target=float(g.grasp.open_position), closed_target=float(g.grasp.closed_position),
                    command=f"{r.layout[r.grip_index[name]]}: native actuator target in {unit}; "
                            f"open={g.grasp.open_position:g}, closed={g.grasp.closed_position:g}. "
                            f"This is a drive coordinate, not a finger-pad gap. Grasping: {self.grasp_rules()}")
            a, c = r.axes[name]
            tcp[r.tcp_frames[name]] = {"parent_link": g.hand_link, "link_T_frame": _r(r.hand_T_tcp[name]),
                                       "definition": f"the {name} gripper's tool frame (TCP): a fixed point near the closed finger pads; "
                                                     f"approach axis (hand -> fingertips) = local {_r(a, 3)}, finger-closing axis = local "
                                                     f"{_r(c, 3)}. The ee_pose action, the proprio tcp pose and the IK use this frame."}
        base = r.entity.links[0].name
        return {"name": self.env._robot.description.robot_id, "gripper_space": r.gripper_space,
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
            value = r.width_to_native(arm, width) if r.gripper_space == "native" else width
            t = s.hold_action(); t[r.grip_index[arm]] = float(np.clip(value, *r.limits[r.grip_index[arm]]))
            for _ in range(int(steps)):
                s.step(t)

        def open_gripper(arm: str, steps: int = 15):
            """Open the gripper of `arm` fully."""
            set_gripper(arm, float(r.width_table[arm][0][-1]), steps)

        def close_gripper(arm: str, steps: int = 15):
            """Close the gripper of `arm` (width target 0; the PD controller squeezes whatever is between the fingers)."""
            if r.gripper_space == "native":
                t = s.hold_action(); t[r.grip_index[arm]] = r.groups[arm].grasp.closed_position
                for _ in range(int(steps)):
                    s.step(t)
            else:
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
            descents/lifts). Raises PrimitiveError if the IK residual exceeds `tol` metres. Returns the final TCP error (m).
            An IK solution more than 0.5 rad from the current joints is noted in s.safety()["ik_jumps"] and on stderr: for
            a small pose change it is another IK branch, which swings the arm (split the move, or use linear=k)."""
            p1 = np.asarray(pos, dtype=np.float64)
            p0, q0 = s.ee_pose(arm)
            quat = np.asarray(quat_wxyz if quat_wxyz is not None else q0, dtype=np.float64)
            k = max(1, int(linear))
            for j in range(1, k + 1):
                pj = p0 + (p1 - p0) * (j / k) if k > 1 else p1
                q7, ep, er = s.ik(arm, pj, quat)
                if ep > tol or er > 0.2:
                    raise PrimitiveError(f"IK for {arm} arm at {np.round(pj, 3).tolist()} failed: residual {ep * 1000:.1f} mm / {math.degrees(er):.1f} deg")
                jump, joint = s.ik_jump(arm, q7)
                if jump > IK_JUMP_LIMIT_RAD:
                    event = dict(step=int(s.n_steps), arm=arm, joint=joint, jump_rad=round(jump, 3))
                    s.monitor.ik_jump(event)
                    _log(f"move_ee: the IK solution for {'the ' + arm + ' arm' if len(r.arms) > 1 else 'the arm'} is {jump:.2f} "
                         f"rad from the current joints ({joint}); for a small pose change that is another IK branch and the "
                         "arm will swing")
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
    if not p.is_file():
        return {}
    from topogym.simulator.frozen_binding import installed_runtime
    return installed_runtime(p.parent)["source"]


def success_enabled(task) -> bool:
    """Whether the image judges success for this task: the task's goal_complete switch. Since Jianwen's 2ec4b8d6 it is
    True by default in every family (an enable switch, not the episode's success state; topogym/tasks/base.py)."""
    return bool(getattr(task, "goal_complete", True))


def grasp_words(s: "Session") -> str:
    """The instance's grasping, from its frozen SimulatorConfig: his recommended / explicit assistance or physical."""
    ga = s.config.get("grasp_assist") or {}
    if ga.get("model", "none") == "none":
        return "physical grasping"
    return f"frozen {ga['model']} grasp assistance"


def success_rule(s: "Session") -> str:
    """Provenance of this instance's success rule, recorded in instance.json and task.toml: his default success with the
    terminal revision, plus his qualification record where one matches this instance. Since 2ec4b8d6 a record is owner
    metadata only (terminal_metadata()["qualification"]); it never enables or disables success."""
    task = s.env._task
    if not success_enabled(task):
        return "not evaluable (goal_complete False)"
    meta = task.terminal_metadata()
    out = f"task-native success (goal_complete True; frozen parameters; terminal revision {meta.get('revision', task.terminal_revision)})"
    record = meta.get("qualification")
    if record:
        out += (f"; his qualification record for this variation matches, as metadata only (record profile: "
                f"{record.get('profile', 'not recorded')}{'; ' + record['scope'] if record.get('scope') else ''}); this "
                f"instance runs {'CPU' if s.config.get('compute_backend') == 'cpu' else 'CUDA'} "
                f"{float(s.config['physics_dt_s']) * 1000:g} ms ticks x {int(s.config['solver_substeps'])} "
                f"substeps with joint-position actions and {grasp_words(s)}, which the record does not cover")
    return out


def cmd_export_ipc_state(a) -> None:
    """Build the scene with the family's settling (reset_physics_steps) and archive the settled IPC state (-> make-instance
    --ipc-settled-state): every build of that instance then restores the same bits instead of settling again."""
    from topogym.world.physics.ipc_settled_state import export_settled_state, identity
    params, overrides = _build_options(a)
    s = Session(a.task, eval_index=a.eval_index, variation_id=a.variation, seed=a.scene_seed,
                task_parameters=params, simulator_overrides=overrides)
    env = s.env
    manifest = export_settled_state(env._world, a.out, scene_identity=identity(env._world, env._task, env._scene_spec,
                                    env._asset_build), metadata=dict(settled_ticks=int(s.config["reset_physics_steps"]),
                                    solver_substeps=int(s.config["solver_substeps"]),
                                    ipc_options=dict(s.config.get("ipc_options") or {})))
    print(json.dumps({"archive": str(manifest), "settled_ticks": int(s.config["reset_physics_steps"])}), flush=True)
    s.close()


def _build_options(a):
    def read(name):
        path = getattr(a, name, None)
        return json.loads(Path(path).read_text()) if path else None
    return read("task_parameters"), read("simulator_overrides")


def cmd_make_instance(a) -> None:
    params, overrides = _build_options(a)
    if a.ipc_settled_state:   # restore the archived settled state instead of settling at every build
        overrides = {**(overrides or {}), "reset_physics_steps": 0,
                     "ipc_settled_state": str(Path(a.ipc_settled_state).resolve())}
    s = Session(a.task, eval_index=a.eval_index, variation_id=a.variation, seed=a.scene_seed,
                task_parameters=params, simulator_overrides=overrides, gripper_space=getattr(a, "gripper_space", "width"))
    import genesis as gs
    from topogym.tasks.goal_description import TASK_IDS, describe_goal
    out = {"task": a.task, "topogym_task": s.config["task_id"], "variation_id": s.config["variation_id"], "seed": s.config["seed"],
           "eval_index": s.eval_index, "text": s.spec["text"], "simulator": s.config, "state_sha": s.instance_sha,
           "action_dim": s.action_dim, "action_layout": s.action_layout, "gripper_space": s.gripper_space,
           "control_hz": s.control_hz, "backend": s.backend,
           "reset_joint_targets": [round(float(x), 6) for x in s.joint_positions()], "objects": s.objects(),
           "instance_contract_version": 2, "soft_state": s._soft_state(), "asset_identity": s.asset_identity,
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
    if s.config.get("ipc_settled_state"):
        import shutil
        settled = Path(s.config["ipc_settled_state"])
        source = settled.resolve().parent
        target = Path(a.out).resolve().parent / "instance_assets" / "ipc_state"
        if source != target:
            shutil.copytree(source, target, dirs_exist_ok=True)
        out["simulator"]["ipc_settled_state"] = "instance_assets/ipc_state/" + settled.name
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
    acts, ticks = load_trajectory(a.traj, a.task, s.action_dim, trusted=True, layout=s.action_layout)
    t0 = time.time()
    outs = [s.replay(acts, physics_steps=ticks, grading=True) for _ in range(a.repeat)]   # as the graders replay
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "instance_generated": s.instance_generated, "initial_state": s.initial_state,
           "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "strict_goal": strict_goal(outs),
           "wall_s": round(time.time() - t0, 1)}
    if a.video:
        s.start_video(a.video, fps=a.fps); s.replay(acts, physics_steps=ticks, grading=True); s.stop_video()
        out["video"] = a.video
    print(json.dumps(out), flush=True)
    s.close()


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance)
    cams = tuple(a.cameras.split(",")) if a.cameras else None
    actions, ticks = load_trajectory(a.traj, a.task, s.action_dim, trusted=True, layout=s.action_layout)
    print(json.dumps(s.render_video(actions, a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols, physics_steps=ticks)), flush=True)
    s.close()


def cmd_describe(a) -> None:
    """What the task generator writes into instruction.md / README.md: cameras, robot, kinematics, the success predicate's
    source, the table height; one JSON line."""
    import inspect
    runtime_identity = installed_runtime()      # this tooling's: both libuipc builds and the one in use
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
    out = {"runtime_identity": runtime_identity,
           "sec_per_step": round(sec_per_step, 3), "cameras": s.camera_info(), "robot_spec": s.robot_spec(), "kinematics": s.kinematics_spec(), "arms": list(s.robot.arms),
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
                      instance_matches=s.instance_matches, instance_exact=s.instance_exact, status=status,
                      replay=s.replay(actions),
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
    q.add_argument("--simulator-overrides", help="manager-only JSON build options, frozen with the instance")
    q.add_argument("--ipc-settled-state", help="an export-ipc-state archive (manifest.json) to restore instead of settling")
    q.add_argument("--gripper-space", choices=("width", "native"), default="width",
                   help="Frozen public gripper command representation; native preserves actuator targets without gap inversion")
    q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("export-ipc-state"); q.add_argument("--task", required=True); q.add_argument("--eval-index", type=int)
    q.add_argument("--variation"); q.add_argument("--scene-seed", type=int); q.add_argument("--out", required=True)
    q.add_argument("--task-parameters"); q.add_argument("--simulator-overrides")
    q.set_defaults(fn=cmd_export_ipc_state)
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
