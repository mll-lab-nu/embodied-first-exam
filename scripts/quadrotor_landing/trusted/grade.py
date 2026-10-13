"""Operator-only held-out grading after sealing and stopping the agent."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from ..public.policy import load
from ..public.model import TASK_VERSION, SCORE_VERSION
from .session import digest
from .oracle import load_bank


def grade(root, residual, render=True):
    root, residual = Path(root), Path(residual)
    state = json.loads((root / "state.json").read_text())
    if state.get("task_version") != TASK_VERSION:
        raise ValueError("Task version changed")
    if not state["sealed"] or state["infrastructure_error"]:
        raise ValueError("No valid sealed submission")
    if hashlib.sha256(residual.read_bytes()).hexdigest() != state["residual_sha256"]:
        raise ValueError("Evaluator changed")
    selected = next(r for r in state["rounds"] if r["id"] == state["selected"])
    policy = root / selected["id"] / "policy.json"
    if digest(load(policy)) != selected["policy_sha256"]:
        raise ValueError("Sealed policy changed")
    references = load_bank(state["bank"], residual, root / "oracle", state["oracle_bank_sha256"])
    destination = root / "held-out"
    destination.mkdir(exist_ok=False)
    rows = []
    for i, case in enumerate(state["bank"]["held_out"]):
        runs = []
        for repeat in range(2):
            path = destination / f"case-{i}-replay-{repeat}"
            args = [
                sys.executable,
                "-m",
                "scripts.quadrotor_landing.trusted.worker",
                "--policy",
                str(policy),
                "--residual",
                str(residual),
                "--out",
                str(path),
                "--seed",
                str(case["seed"]),
                "--scale",
                str(case["scale"]),
                "--reference-time",
                str(references["held_out"][i]["oracle_time_s"]),
            ]
            if render and repeat == 0:
                args += ["--render"]
            subprocess.run(args, check=True, timeout=120, env={**os.environ, "OPENBLAS_NUM_THREADS": "1"})
            runs.append(json.loads((path / "record.json").read_text()))
        if runs[0] != runs[1]:
            raise RuntimeError("Independent replay mismatch")
        if runs[0]["metrics"]["score"] is None:
            raise RuntimeError("Uncalibrated held-out score")
        rows.append(
            {
                "case": i,
                **runs[0]["metrics"],
                "replay_sha256": digest(runs[0]),
                "replay_verified": True,
                "oracle_reference_sha256": digest(references["held_out"][i]),
            }
        )
    successful = [r for r in rows if r["success"]]
    report = {
        "kind": "held_out_policy_evaluation",
        "task_version": TASK_VERSION,
        "score_version": SCORE_VERSION,
        "model_evaluation": False,
        "oracle_bank_sha256": state["oracle_bank_sha256"],
        "oracle_global_optimality_certified": False,
        "policy_sha256": selected["policy_sha256"],
        "episodes": rows,
        "successes": len(successful),
        "success_rate": len(successful) / len(rows),
        "mean_successful_completion_time_s": (
            sum(r["completion_time_s"] for r in successful) / len(successful) if successful else None
        ),
        "score": sum(r["score"] for r in rows) / len(rows),
    }
    (root / "grade.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--no-video", action="store_true")
    a = p.parse_args()
    print(json.dumps(grade(a.root, a.residual, not a.no_video)))
