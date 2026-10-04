#!/usr/bin/env python3
"""Check native Harbor completion and bound verifier evidence, not reward.txt alone."""
import argparse
import json
from pathlib import Path


def bound_sidecar(folder, lock):
    from topogym.simulator.frozen_binding import binding_id
    wanted = binding_id(lock)
    for name in ("startup_binding.json", "replay.verdict.json"):
        record = json.loads((Path(folder) / name).read_text())
        if (record.get("instance_exact") is not True
                or (record.get("runtime_binding") or {}).get("binding_id") != wanted):
            raise ValueError("Sidecar startup/replay differs from the frozen runtime: " + name)


def check(job, expected, task=None):
    trials = list(Path(job).glob("*/result.json"))
    if len(trials) != 1:
        raise ValueError("Expected exactly one Harbor trial")
    result = json.loads(trials[0].read_text())
    reward = json.loads((trials[0].parent / "verifier/reward.json").read_text())
    if task is not None and Path(result.get("task_name", "")).name != Path(task).name:
        raise ValueError("Harbor evidence belongs to a different task")
    if result.get("exception_info") or not result.get("finished_at"):
        raise ValueError("Harbor trial did not finish cleanly")
    if reward.get("success") != expected or any(reward.get(k) for k in
            ("infra_error", "grader_error", "instance_mismatch", "gpu_lost")):
        raise ValueError("Unexpected score or infrastructure failure")
    if expected == 1 and (reward.get("runtime_binding_ok") != 1 or
            reward.get("instance_exact", reward.get("runtime_binding_ok")) != 1):
        raise ValueError("Success lacks exact bound replay evidence")
    # TopoGym's GPU graders report final-state determinism as a diagnostic.
    # Requiring it here rejects valid live/replay successes accepted by both graders.
    if str(result.get("task_name", "")).endswith("-standard") and (
            reward.get("runtime_binding_ok") != 1 or reward.get("finalized") != 1):
        raise ValueError("Standard trial lacks bound finalization/replay evidence")
    return reward


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--expected", type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    try:
        check(args.job, args.expected)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"Trial validation failed: {error}\n")
