"""Operator-only held-out grading after sealing and stopping the agent."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from ..public.policy import load
from ..public.model import TASK_VERSION, SCORE_VERSION
from .session import digest
from .oracle import load_bank


def grade(root, residual, render=False):
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
    if destination.exists():
        # an interrupted finalization (the service restarted): the sealed policy and the bank are frozen, so the
        # evaluation runs again from scratch; the partial run is kept aside as evidence
        destination.rename(root / f"held-out-interrupted-{time.time_ns()}")
    destination.mkdir()

    def evaluate(item):
        i, case = item
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
            # 6 cases x 2 runs on 4 workers within the 840 s collect budget: a hung run is named in final.json
            subprocess.run(args, check=True, timeout=150, env={**os.environ, "OPENBLAS_NUM_THREADS": "1"})
            runs.append(json.loads((path / "record.json").read_text()))
        if runs[0] != runs[1]:
            raise RuntimeError("Independent replay mismatch")
        if runs[0]["metrics"]["score"] is None:
            raise RuntimeError("Uncalibrated held-out score")
        return {
            "case": i,
            **runs[0]["metrics"],
            "replay_sha256": digest(runs[0]),
            "replay_verified": True,
            "oracle_reference_sha256": digest(references["held_out"][i]),
        }

    # both runs unrendered: the verdict never waits for or depends on a video (render_held_out, after it)
    with ThreadPoolExecutor(4) as pool:   # the sim service's 4 CPUs, one single-threaded worker each
        rows = list(pool.map(evaluate, enumerate(state["bank"]["held_out"])))
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


def render_held_out(root, residual):
    """After the verdict (PROTOCOL §4): one rendered run of the sealed policy per held-out case, joined into
    <data>/replay.mp4. Best effort; it never changes grade.json or final.json."""
    root, residual = Path(root), Path(residual)
    state = json.loads((root / "state.json").read_text())
    policy = root / state["selected"] / "policy.json"
    references = load_bank(state["bank"], residual, root / "oracle", state["oracle_bank_sha256"])
    folder = root / "held-out-video"
    if folder.exists():
        folder.rename(root / f"held-out-video-interrupted-{time.time_ns()}")
    folder.mkdir()
    out = root.parent / "replay.mp4"
    out.unlink(missing_ok=True)   # a restart renders again from scratch
    graded = {r["case"]: r["replay_sha256"] for r in json.loads((root / "grade.json").read_text())["episodes"]}

    def one(item):
        i, case = item
        path = folder / f"case-{i}"
        try:
            subprocess.run([sys.executable, "-m", "scripts.quadrotor_landing.trusted.worker", "--policy", str(policy),
                            "--residual", str(residual), "--out", str(path), "--seed", str(case["seed"]),
                            "--scale", str(case["scale"]), "--reference-time",
                            str(references["held_out"][i]["oracle_time_s"]), "--render"],
                           check=True, timeout=600, env={**os.environ, "OPENBLAS_NUM_THREADS": "1"})
            # the rendered run is the graded one again (rendering never changes the physics)
            return path / "video.mp4", digest(json.loads((path / "record.json").read_text())) == graded.get(i)
        except Exception:   # one case without a video does not cost the others theirs
            return path / "video.mp4", False

    with ThreadPoolExecutor(2) as pool:
        rendered = list(pool.map(one, enumerate(state["bank"]["held_out"])))
    parts = [p for p, _ in rendered if p.is_file()]
    listing = folder / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    tmp = root.parent / "replay.tmp.mp4"   # never a truncated replay.mp4 (a collect budget running out)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    str(tmp)], check=True, timeout=300, capture_output=True)
    os.replace(tmp, out)
    return out, all(ok for _, ok in rendered)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--no-video", action="store_true")
    a = p.parse_args()
    print(json.dumps(grade(a.root, a.residual)))
