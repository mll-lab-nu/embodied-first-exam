"""Verifier-equivalent replay checks; original reports alone cannot pass this audit."""
from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np

from topogym.utils.io import write_json_atomic


def install_progress(tooling, output):
    """Observe native step/replay returns; never change actions, tick requests or episode control."""
    native_step, native_replay = tooling.Session.step, tooling.Session.replay
    output = Path(output)

    def write(session, phase, result=None):
        task = session.env._task.result
        row = dict(wall_time=time.time(), phase=phase, replay=session._resets,
                   actions=session.n_steps, physics_steps=session.physics_steps,
                   sim_time_s=session.sim_time_s, episode_end=session.episode_end,
                   stable_time_s=float(task.metrics.get("stable_time_s", 0.)),
                   task_metrics={k: v for k, v in task.metrics.items() if isinstance(v, (bool, int, float, str))})
        if result is not None:
            row["result"] = result
            with (output/"replay_passes.jsonl").open("a") as stream:
                stream.write(json.dumps(row)+"\n")
        write_json_atomic(output/"replay_progress.json", row)

    def step(session, action, **kwargs):
        ended = native_step(session, action, **kwargs)
        requested = kwargs.get("_physics_steps")
        partial = requested is not None and requested < session.physics_substeps
        if session.n_steps == 1 or session.n_steps % 20 == 0 or ended or partial:
            write(session, "step")
        return ended

    def replay(session, actions, **kwargs):
        result = native_replay(session, actions, **kwargs)
        write(session, "replay_complete", result)
        return result

    tooling.Session.step, tooling.Session.replay = step, replay


def trajectory_identity(path, instance):
    with np.load(path, allow_pickle=False) as z:
        for key, expected in (("task", "knot_untying"), ("variation_id", instance["simulator"]["variation_id"]),
                              ("scene_seed", instance["simulator"]["seed"]), ("action_dim", instance["action_dim"])):
            if key not in z or z[key].item() != expected:
                raise ValueError(f"trajectory {key} differs from the frozen instance")
        if z["action_layout"].tolist() != instance["action_layout"]:
            raise ValueError("trajectory action layout differs from the frozen instance")
        actions, ticks = z["actions"], z["physics_steps_per_action"]
        if (actions.ndim != 2 or actions.shape[1] != instance["action_dim"] or len(actions) == 0
                or not np.isfinite(actions).all() or ticks.shape != (len(actions),) or ticks.dtype.kind not in "iu"
                or np.any(ticks <= 0) or np.any(ticks > instance["simulator"]["control_decimation"])):
            raise ValueError("invalid trajectory action/tick ledger")
        return dict(actions=len(actions), physics_steps=int(ticks.sum()))


def read_replay_report(log):
    reports = []
    for line in Path(log).read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and "all_success" in row:
            reports.append(row)
    return reports[-1] if reports else None


def assess(report, *, repeat, exit_code, actions):
    errors = []
    if exit_code != 0:
        errors.append(f"replay process exited {exit_code}")
    if not isinstance(report, dict):
        return dict(accepted=False, errors=errors+["missing native replay report"])
    if report.get("instance_matches") is not True or report.get("instance_exact") is not True:
        errors.append("formal frozen instance was not reproduced exactly")
    replays = report.get("replays", [])
    if len(replays) != repeat or repeat < 1:
        errors.append("incomplete replay count")
    if report.get("n_actions") != actions:
        errors.append("replayed trajectory action count differs")
    if report.get("all_success") is not True or not replays or any(
            r.get("success") is not True or r.get("episode_end") != "success" for r in replays):
        errors.append("not every replay reached native task_success")
    return dict(accepted=not errors, errors=errors, replay_count=len(replays),
                determinism_tested=len(replays) >= 2, deterministic=report.get("deterministic"),
                scope="native task_success in a fresh process using task-local replay, not a full collision/convergence audit")
