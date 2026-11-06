"""HumanCLAW for EFE: one frozen episode, driven one motion skill at a time, scored by HumanCLAW's own metric code.

Shared by the standard sidecar (server.py), the privileged tools (hc_tools.py) and the privileged grader. Everything
that decides an outcome is HumanCLAW's, unchanged, as its evaluator runs it (humanclaw_bench/evaluation/evaluator.py,
HCFindNavInteractEvaluator.run_rollout under the paper_fullval_v1 profile with paper metrics on and the live video
writer off): the episode loader, the Half-Physics environment, the MotionDiT skill runner, the action families with
their clamps (agent/planner.py _chooser_action, called here), the replay trajectory recorder and the paper metric
recorder (evaluation/metrics/episode.py). The VLM agent is the only part replaced: an action comes from the caller.

Two things this file adds, both declared in the task READMEs:
  * the motion model's noise is seeded at every reset (torch / numpy / random, `seed` in the instance). HumanCLAW's
    evaluator never seeds it, so its own rollouts of the same actions differ run to run; seeded, a rollout is a
    function of (instance, actions) -- what a submitted trajectory needs to mean anything.
  * a reset rebuilds the simulator (HumanCLAW builds a fresh one per rollout as well): moved furniture comes back.

An action is a row [action_id, value]:
  0 walk forward   value: 0.2 / 0.4 / 0.6 m (HumanCLAW's slow / normal / fast stride)
  1 stop           value: 0. Ends the episode: the agent declares it is done (HumanCLAW's Stop/Stand)
  2 turn           value: signed degrees, + left (counter-clockwise seen from above), |value| clamped to [10, 120]
  3 climb up a step            value: 0
  4 sit down       value: target pelvis height in m, clamped to [0.15, 0.85]
  5 step back      value: m, clamped to [0.10, 0.60]
  6 side step      value: signed m, + left, |value| clamped to [0.10, 0.50]
  7 walk down a step           value: 0
 -1 idle (the service's hold row only): nothing moves, no action is used.
Each of 0, 2-7 is one 0.5 s motion chunk (15 frames at 30 Hz); 1 moves nothing. An episode allows max_steps (100)
actions, stop included: the 100th action ends it whatever it is, and only a stop can succeed.
Success (HumanCLAW's own, finalize()): a navigation episode (chair / potted_plant / tv) needs NavSR@20cm -- the
episode ended with a stop and the body's distance to the nearest target's bounding box is <= 0.2 m; an interaction
episode (bed / couch / toilet) needs InteractSR -- ended with a stop, at least one sit, and the pelvis touching the
target's mesh on the last frame of the last motion.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import random
import shutil
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")   # deterministic cuBLAS (set before CUDA starts)

SCHEMA = "efe-humanclaw-instance/1"
NAV_CATEGORIES = ("chair", "potted_plant", "tv")
INTERACT_CATEGORIES = ("bed", "couch", "toilet")
ACTIONS = {0: "walk_forward", 1: "stop", 2: "turn", 3: "climb_up", 4: "sit", 5: "step_back", 6: "side_step",
           7: "walk_down"}
IDLE = -1
WALK = {0.2: "slow", 0.4: "normal", 0.6: "fast"}
DECIMALS = 4          # values are rounded to this many decimals before anything else: float32 and float64 rows agree
LIMITS = {2: (10.0, 120.0), 4: (0.15, 0.85), 5: (0.10, 0.60), 6: (0.10, 0.50)}


class BadAction(ValueError):
    """An action row the episode refuses as a whole: nothing runs."""


# ---------------------------------------------------------------------------------------------------- actions
def clip_row(row: Any) -> tuple[np.ndarray, list[str]]:
    """Validate one [action_id, value] row; return it as executed (rounded, clamped) and what was clamped.
    Raises BadAction for an unknown id, a walk distance that is not 0.2/0.4/0.6, a turn of 0 or side step of 0,
    or a value on a value-less action that is not 0."""
    r = np.asarray(row, dtype=np.float64).reshape(-1)
    if r.shape != (2,) or not np.all(np.isfinite(r)):
        raise BadAction("an action is [action_id, value], two finite numbers")
    aid, v = r[0], round(float(r[1]), DECIMALS)
    if aid != int(aid) or int(aid) not in ACTIONS:
        raise BadAction(f"action_id must be one of {sorted(ACTIONS)}, got {r[0]!r}")
    aid, notes = int(aid), []
    if aid == 0:
        hit = [d for d in WALK if abs(v - d) < 1e-3]
        if not hit:
            raise BadAction(f"walk_forward: value must be 0.2, 0.4 or 0.6 (m), got {r[1]!r}")
        v = hit[0]
    elif aid in (1, 3, 7):
        if v != 0.0:
            raise BadAction(f"{ACTIONS[aid]}: value must be 0, got {r[1]!r}")
    else:
        lo, hi = LIMITS[aid]
        mag = abs(v) if aid in (2, 6) else v
        if aid in (2, 6) and mag == 0.0:
            raise BadAction(f"{ACTIONS[aid]}: value must be nonzero (its sign is the direction, + left)")
        c = min(hi, max(lo, mag))
        if c != mag:
            notes.append(f"{ACTIONS[aid]} {mag:g} clamped to {c:g}")
        v = math.copysign(c, v) if aid in (2, 6) else c
    return np.array([aid, v], dtype=np.float64), notes


def action_name(row: np.ndarray) -> str:
    """The HumanCLAW action name (prompt v4 vocabulary) for a clipped row."""
    aid, v = int(row[0]), float(row[1])
    side = "left" if v > 0 else "right"
    return {0: lambda: f"Walk<forward><{WALK.get(v, 'slow')}>", 1: lambda: "Stop/Stand",
            2: lambda: f"Turn<{side}><{abs(v)!r}>", 3: lambda: "Climb upstairs<normal>",
            4: lambda: f"Sit down<{v!r}>", 5: lambda: f"Step back<{v!r}>",
            6: lambda: f"Side step<{side}><{abs(v)!r}>", 7: lambda: "Walk downstairs<normal>"}[aid]()


def skill_call(row: np.ndarray):
    """The SkillCall HumanCLAW's planner makes of this action (its own _chooser_action, so its clamps and
    conditioning values apply exactly)."""
    from humanclaw_bench.agent.planner import HumanClawBenchPSVPlanSkillPlanner as P
    return P._chooser_action(object.__new__(P), {"action_id": int(row[0]), "action_name": action_name(row)})


# ---------------------------------------------------------------------------------------------------- instance
def load_instance(path: str | os.PathLike) -> dict:
    inst = json.loads(Path(path).read_text())
    if inst.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not an {SCHEMA} file")
    return inst


def instance_digest(inst: dict) -> str:
    """sha256 of the instance minus its own recorded hashes: what the frozen episode is."""
    core = {k: v for k, v in inst.items() if k not in ("start_sha", "digest")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _f64(*vals) -> bytes:
    out = []
    for v in vals:
        if hasattr(v, "detach"):                     # a torch tensor (on the GPU in the motion state)
            v = v.detach().cpu().double().numpy()
        a = np.asarray(v, dtype=np.float64).reshape(-1)
        out.append(struct.pack(f"<{a.size}d", *a.tolist()))
    return b"".join(out)


# ---------------------------------------------------------------------------------------------------- session
class Session:
    """One frozen HumanCLAW episode. reset() starts it, act(row) runs one action, `result` holds the outcome once the
    episode has ended (a stop, or max_steps actions)."""

    def __init__(self, instance: str | os.PathLike | dict, *, device: str | None = None, workdir: str | None = None):
        self.inst = instance if isinstance(instance, dict) else load_instance(instance)
        self.device = device or os.environ.get("HC_DEVICE") or "cuda"
        self._tmp = tempfile.mkdtemp(prefix="hc-", dir=workdir)
        self._build()
        self.env = None
        self.reset()

    # -- construction, as HCFindNavInteractEvaluator.evaluate_main does it (VLM and agent left out) --
    def _build(self) -> None:
        from humanclaw_bench.benchmark.episodes import apply_instruction_version, load_episode
        from humanclaw_bench.config import load_config
        from humanclaw_bench.motion.runner import MotionSkillRunner
        from humanclaw_bench.paths import resolve_release_path

        inst = self.inst
        self.profile = load_config(inst.get("profile", "paper_fullval_v1"))
        bench, motion = self.profile.section("benchmark"), self.profile.section("motion")
        self.physics = self.profile.section("physics")
        self.rendering = dict(self.profile.data.get("rendering") or {})
        self.max_steps = int(inst.get("max_steps", bench["max_steps"]))
        # the frozen episode as a one-episode shard in HumanCLAW's own layout, read by its own loader
        shard = Path(self._tmp) / "episodes" / str(bench["split"]) / "content"
        shard.mkdir(parents=True)
        # the frozen file carries no upstream episode id (it stays out of the agent's reach): the shard's only episode
        with gzip.open(shard / f"{inst['scene_id']}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(inst["content"], f)
        self.scene_config = resolve_release_path(bench["scene_dataset_config"])
        ep = load_episode(benchmark_dataset_dir=shard.parent.parent, split=str(bench["split"]),
                          scene_id=str(inst["scene_id"]), scene_dataset_config=self.scene_config,
                          episode_index=0,
                          object_category=str(inst["category"]), max_steps=self.max_steps)
        self.episode = apply_instruction_version(ep, str(bench["instruction_version"]))
        self.motion = MotionSkillRunner(skills=tuple(motion["skills"]), device=self.device,
                                        weights_root=str(motion["weights_root"]),
                                        weights_manifest=str(motion["weights_manifest"]),
                                        verify_weights=bool(motion["verify_weights"]))
        self.seed_mode = str(motion["seed_mode"])
        self.seed_pkl = str(resolve_release_path(motion["seed_pkl"])) if motion.get("seed_pkl") else None
        self.seed_pt = str(resolve_release_path(motion["seed_pt"])) if motion.get("seed_pt") else None
        self.metric_config = dict(self.profile.data.get("metrics") or {})

    def _new_env(self):
        from humanclaw_bench.envs.find_nav_interact_env import HCFindNavInteractEnv
        from humanclaw_bench.paths import resolve_release_path
        ph, rd = self.physics, self.rendering
        kwargs = {k: v for k, v in ph.items() if k not in {"backend", "agent_urdf", "agent_shift_npy", "physics_config"}}
        return HCFindNavInteractEnv(
            scene_id=self.episode.scene_id, scene_dataset_config=self.episode.scene_dataset_config,
            half_physics_backend=str(ph["backend"]), agent_urdf=resolve_release_path(ph["agent_urdf"]),
            agent_shift_npy=resolve_release_path(ph["agent_shift_npy"]),
            physics_config=resolve_release_path(ph["physics_config"]), max_episode_steps=self.max_steps,
            lighting=str(rd.get("lighting", "ambient")), ambient_strength=float(rd.get("ambient_strength", 1.2)),
            ego_resolution=tuple(rd.get("ego_resolution", [448, 448])),
            third_person_resolution=tuple(rd.get("third_person_resolution", [512, 512])),
            compute_metrics=True, video_enabled=bool(self.inst.get("video_enabled", False)), **kwargs)

    # -- an episode --
    def reset(self) -> None:
        """A fresh simulator at the frozen start (HumanCLAW's _reset_env_for_rollout), the noise seeded."""
        from humanclaw_bench.envs.half_physics_env import xb75_yup_to_half_physics_pose
        from humanclaw_bench.evaluation.metrics.episode import PaperMetricRecorder
        from humanclaw_bench.evaluation.trajectory import TrajectoryRecorder, build_replay_metadata
        import torch

        if self.env is not None:
            self.env.close()
        seed = int(self.inst.get("seed", 0))
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)          # also every CUDA device's generator
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)
        self.env = self._new_env()
        init_xb = self.motion.reset(self.seed_mode, self.seed_pkl, self.seed_pt, self.episode.init_offset,
                                    self.episode.init_yaw)
        tr, orient, body = xb75_yup_to_half_physics_pose(init_xb)
        self.obs = self.env.reset(self.episode, initial_transl=tr, initial_global_orient=orient,
                                  initial_body_pose=body)
        self.traj = TrajectoryRecorder(
            metadata=build_replay_metadata(profile_name=self.profile.profile, episode=self.episode, rollout_index=0,
                                           env=self.env),
            initial_xb_world_75=init_xb, initial_state=self.env.replay_initial_state())
        self.metrics = PaperMetricRecorder(episode=self.episode, env=self.env, config=self.metric_config,
                                           profile_name=self.profile.profile, rollout_index=0)
        self.metrics.record_reset()
        self.n_actions, self.done, self.result, self.rows = 0, False, None, []
        self._pelvis_y0 = float(self.env.agent.translation.y)
        # seed again once everything is built: a first build (lazy module set-up) draws from the CPU generator, a
        # rebuild does not, and the episode must start from the same state either way
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

    def act(self, row: Any) -> dict:
        """One action (a row clip_row accepts, or the idle row). Returns {done, success, ...}."""
        from humanclaw_bench.agent.skills import skill_to_text
        r = np.asarray(row, dtype=np.float64).reshape(-1)
        if r.shape == (2,) and r[0] == IDLE:
            return {"done": self.done, "success": bool(self.result and self.result["success"]), "moved": False}
        if self.done:
            raise RuntimeError("the episode has ended")
        r, _ = clip_row(r)
        call = skill_call(r)
        step = self.n_actions
        # what HumanCLAW's evaluator does with one decision (run_rollout's loop body)
        find_obs = self.env.metric_find_observation()
        decision = SimpleNamespace(action=call, stage_outputs=(), planner_skill={})
        self.metrics.record_decision(step=step, decision=decision, find_observation=find_obs)
        if call.skill == "stand":
            env_action: Any = {"stop": True, "skill": "stand", "action": call.to_json()}
        else:
            gen = self.motion.generate(call.skill, call.cond)
            self.traj.record_before(step=step, action=call, action_text=skill_to_text(call),
                                    xb_world_75=gen.xb_world_75)
            env_action = gen.xb_world_75
        self.obs, _r, done, info = self.env.step(env_action, reasoning=None)
        body = info.get("body_state") if isinstance(info, dict) else None
        if isinstance(body, dict):
            self.traj.record_after(step=step, body_state=body, object_states=dict(info.get("object_states") or {}))
        if call.skill != "stand":
            self.metrics.record_motion(step=step, action_skill=call.skill, info=info if isinstance(info, dict) else {})
        self.n_actions += 1
        self.rows.append(r)
        if done or self.n_actions >= self.max_steps:
            self._finish()
        return {"done": self.done, "success": bool(self.result and self.result["success"]), "moved": call.skill != "stand"}

    def _finish(self) -> None:
        before, after = self.traj.materialize()
        m = self.metrics.finalize(before=before, after=after)
        s = m["success"]
        interact = bool(s["is_interact_episode"])
        self.done = True
        self.result = {"success": bool(s["interact_sr"] if interact else s["nav_sr_20cm"]),
                       "rule": "InteractSR" if interact else "NavSR@20cm", "metrics": m}

    # -- what the agent may see in standard mode --
    def ego_rgb(self) -> np.ndarray:
        return np.ascontiguousarray(np.asarray(self.obs.head_rgb, dtype=np.uint8)[..., :3])

    def pelvis_rise(self) -> float:
        """How far the pelvis is above where it was at the start (m; negative: lower, e.g. seated): what the body
        feels, not where it is."""
        return round(float(self.env.agent.translation.y) - self._pelvis_y0, 4)   # Habitat is y-up

    # -- the state, for a hash --
    def state_sha(self) -> str:
        """sha256 (first 16 hex) of everything the rest of the episode depends on: the body (root pose, joints, their
        velocities), every dynamic object (pose, velocities), the motion model's rolling state and frame, the torch
        RNG states, the action count and the metric recorder's running flags."""
        import torch
        a, h = self.env.agent, hashlib.sha256()
        tr, rot = a.translation, a.rotation
        h.update(_f64([tr.x, tr.y, tr.z], [rot.vector.x, rot.vector.y, rot.vector.z, rot.scalar],
                      list(a.joint_positions), list(a.joint_velocities),
                      [a.root_linear_velocity.x, a.root_linear_velocity.y, a.root_linear_velocity.z],
                      [a.root_angular_velocity.x, a.root_angular_velocity.y, a.root_angular_velocity.z]))
        for handle, obj in sorted(self.env._tracked_dynamic_objects().items()):
            p, q = obj.translation, obj.rotation
            lv, av = obj.linear_velocity, obj.angular_velocity
            h.update(str(handle).encode())
            h.update(_f64([p.x, p.y, p.z], [q.vector.x, q.vector.y, q.vector.z, q.scalar], [lv.x, lv.y, lv.z],
                          [av.x, av.y, av.z]))
        mo = self.motion
        for t in (mo.motion_state, mo.T_ref_accum):
            h.update(b"-" if t is None else t.detach().cpu().contiguous().numpy().astype(np.float64).tobytes())
        h.update(_f64(mo.floor_y_accum, mo.current_pelvis_y, mo.step_index))   # floats or GPU scalar tensors
        h.update(torch.get_rng_state().numpy().tobytes())
        if torch.cuda.is_available():
            for s in torch.cuda.get_rng_state_all():
                h.update(s.numpy().tobytes())
        rec = self.metrics
        h.update(json.dumps([self.n_actions, self.done, rec.active_stop, rec.n_sit, rec.geo_interact_success,
                             rec._last_motion_pelvis_target_contact, rec.geo_find_success]).encode())
        return h.hexdigest()[:16]

    # -- evidence --
    def write_rollout(self, out_dir: str | os.PathLike) -> Path:
        """HumanCLAW's replay bundle of this episode (replay_manifest.json, trajectory_before/after.npz): the poses
        as the live simulator realized them, frame by frame."""
        out = Path(out_dir)
        self.traj.write(out)
        return out

    def close(self) -> None:
        if self.env is not None:
            self.env.close()
            self.env = None
        shutil.rmtree(self._tmp, ignore_errors=True)


def render_rollout(rollout_dir: str | os.PathLike, out_dir: str | os.PathLike) -> dict:
    """ego.mp4 + exo.mp4 of a written rollout: HumanCLAW's own renderer, which restores each recorded post-physics
    pose and renders it (simulation time never advances), i.e. the live episode's frames, not a re-run."""
    from humanclaw_bench.rendering.saved_trajectory import render_saved_trajectory
    return render_saved_trajectory(rollout_dir, out_dir, force=True, progress_every=10 ** 9)


def episode_video(session: Session, path: str | os.PathLike) -> None:
    """path (<name>.mp4): the episode's video (first person | third person, side by side, 30 fps), and <name>.last.png
    its last frame, from the live episode's recorded poses (render_rollout)."""
    import subprocess
    path = str(path)
    last = os.path.splitext(path)[0] + ".last.png"
    with tempfile.TemporaryDirectory(prefix="hc-video-", dir=os.path.dirname(path) or None) as tmp:
        session.write_rollout(Path(tmp) / "rollout")
        render_rollout(Path(tmp) / "rollout", Path(tmp) / "rendered")
        ego, exo = Path(tmp) / "rendered" / "ego.mp4", Path(tmp) / "rendered" / "exo.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ego), "-i", str(exo), "-filter_complex",
                        "[0:v]scale=-2:448[a];[1:v]scale=-2:448[b];[a][b]hstack", "-c:v", "libx264", "-preset",
                        "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-sseof", "-0.5", "-i", path, "-update", "1",
                        "-frames:v", "1", last], check=False)
        if not os.path.isfile(last):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", "reverse", "-frames:v", "1",
                            last], check=True)
