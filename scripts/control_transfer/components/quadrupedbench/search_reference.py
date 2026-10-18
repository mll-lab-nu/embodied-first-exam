"""Bounded operator reference search on adaptation cases only; never an agent API.

Private task metrics may rank operator reference candidates. No held-out cases
are loaded, and a candidate found here is not automatically a release reference.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ...control_public.go2_data import PARAMS, validate
from ...trusted.go2_spec import make_spec
from .reference import policy
from .simulation import rollout


def objective(task, record):
    m = record["metrics"]
    if m["success"]:
        return 10000 + m["score"]
    if task == "weave":
        # Dense operator-only adaptation objective; official scoring is unchanged.
        return 30 * m["poles_passed"] + min(m["base_drift_m"], 5) - 60 * m["unsafe"]
    return (
        20 * m["flight_detected"]
        - 30 * m["touchdown_target_error"]
        - 15 * m["target_error"]
        + 20 * m["stable_touchdown"]
        - 40 * m["unsafe"]
    )


def propose(task, base, rng):
    result = copy.deepcopy(base)
    p = result["parameters"]
    ranges = {
        "weave": {
            "height": (0.24, 0.32),
            "period": (0.32, 0.65),
            "swing_height": (0.03, 0.09),
            "stride_gain": (1.7, 2),
            "lateral_gain": (0.8, 1.5),
            "yaw_gain": (0.6, 1.8),
            "support": (0.65, 1.25),
        },
        "forward-jump": {
            "crouch_height": (0.17, 0.23),
            "push_duration": (0.13, 0.24),
            "extend_height": (0.36, 0.42),
            "push_gain": (3, 5),
            "jump_forward": (1.8, 2.5),
            "flight_time": (0.18, 0.4),
            "landing_height": (0.23, 0.33),
            "push_pd_scale": (0.4, 1),
        },
        "yaw-jump": {
            "crouch_height": (0.17, 0.23),
            "push_duration": (0.12, 0.23),
            "extend_height": (0.32, 0.40),
            "push_gain": (2.4, 4.2),
            "jump_yaw": (2, 3.6),
            "flight_time": (0.16, 0.36),
            "landing_height": (0.24, 0.33),
            "push_pd_scale": (0.15, 0.8),
        },
    }[task]
    # Mix local mutations and broad candidates with a fixed, recorded RNG seed.
    for key, (lo, hi) in ranges.items():
        value = rng.uniform(lo, hi) if rng.random() < 0.25 else p[key] + rng.normal(0, (hi - lo) * 0.15)
        p[key] = float(np.clip(value, *PARAMS[key]))
    result["kp"] = [float(np.clip(result["kp"][0] + rng.normal(0, 10), 35, 100))] * 12
    result["kd"] = [float(np.clip(result["kd"][0] + rng.normal(0, 0.7), 0.8, 6))] * 12
    if task != "weave":
        # Bounded late-phase leg placement; no private state enters the controller.
        offset = float(rng.uniform(-0.25, 0.05)) if task == "forward-jump" else 0.0
        for k in range(6, 17):
            for leg in range(4):
                result["trajectory"][k][3 * leg + 1] = offset
    validate(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--candidates", type=int, default=60)
    parser.add_argument("--seconds", type=float, default=1200)
    args = parser.parse_args()
    if not 3 <= args.candidates <= 60 or not 0 < args.seconds <= 1200:
        raise ValueError("Bounded search requires 3..60 candidates and at most1200 seconds")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(20261013)
    tasks = ("weave", "forward-jump", "yaw-jump")
    best = {task: policy(task) for task in tasks}
    ranks = {task: float("-inf") for task in tasks}
    history = []
    start = time.monotonic()
    for i in range(args.candidates):
        if time.monotonic() - start > args.seconds:
            break
        task = tasks[i % 3]
        candidate = policy(task) if i < 3 else propose(task, best[task], rng)
        folder = out / f"{i:03d}-{task}"
        folder.mkdir()
        artifact = validate(candidate)
        (folder / "policy.json").write_bytes(artifact)
        cases = make_spec(0, task)["bank"]["adaptation"]
        records = []
        # Every candidate must be evaluated across the same three adaptation cases.
        for j, case in enumerate(cases):
            records.append(rollout(candidate, case, folder / f"adaptation-{j}", render=False))
        rank = sum(objective(task, r) for r in records) / len(records)
        row = {
            "candidate": i,
            "task": task,
            "rank": rank,
            "successes": sum(r["metrics"]["success"] for r in records),
            "cases": cases,
            "metrics": [r["metrics"] for r in records],
            "policy_sha256": hashlib.sha256(artifact).hexdigest(),
        }
        history.append(row)
        if rank > ranks[task]:
            best[task] = candidate
            ranks[task] = rank
            (out / f"best-{task}.json").write_bytes(artifact)
        (out / "summary.json").write_text(
            json.dumps(
                {
                    "split": "adaptation-only",
                    "seed": 20261013,
                    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "elapsed_seconds": time.monotonic() - start,
                    "history": history,
                    "best_ranks": {k: v for k, v in ranks.items() if np.isfinite(v)},
                    "held_out_tuning": False,
                    "official_predicates_changed": False,
                },
                indent=2,
            )
        )
        print(i, task, row["successes"], rank, flush=True)


if __name__ == "__main__":
    main()
