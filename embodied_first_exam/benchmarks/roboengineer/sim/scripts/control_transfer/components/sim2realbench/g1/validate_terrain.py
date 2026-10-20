"""Operator-only fresh-process CPU validation, media decoding and negative controls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from control_public.weights import arrays, shapes
from .terrain import make_spec


def make_command_blind_policy(source, dest):
    """Negative controller: preserve the actor's balancing response but fix command and phase inputs to zero."""
    values = arrays(source, shapes("g1"))
    values["b0"] += values["w0"][:, 6:11] @ (-values["mean"][6:11] / values["std"][6:11])
    values["w0"][:, 6:11] = 0
    np.savez_compressed(dest, **values)


def validate_run(policy, out, instances=(0, 1), video_cases=4):
    if not 0 <= video_cases <= 12:
        raise ValueError("Invalid video budget")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES="",
        MUJOCO_GL="osmesa",
        PYOPENGL_PLATFORM="osmesa",
        OMP_NUM_THREADS="4",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        LP_NUM_THREADS="4",
    )
    runs = []

    def run_one(actor, folder, case, render=True, extra=()):
        command = [
            sys.executable,
            "-m",
            "sim2realbench.g1.deploy",
            "--policy",
            str(Path(actor).resolve()),
            "--out",
            str(folder),
            "--plant-seed",
            str(case["plant_seed"]),
            "--episode-seed",
            str(case["episode_seed"]),
            "--terrain",
            case["terrain"],
            "--duration",
            str(case["duration"]),
            "--speed",
            str(case["speed"]),
            *extra,
        ]
        if not render:
            command.append("--no-video")
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:])
        record = json.loads((folder / "record.json").read_text())
        if set(record["feedback"]) != {"telemetry", "commands"}:
            raise RuntimeError("Feedback leak")
        for channel, width in [("telemetry", 29), ("commands", 3)]:
            for row in record["feedback"][channel]:
                if set(row) != {"t", "values"} or len(row["values"]) != width:
                    raise RuntimeError("Feedback schema")
        feedback = json.dumps(record["feedback"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        (folder / "feedback.json").write_bytes(feedback)
        if render:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(folder / "video.mp4"), "-f", "null", "-"],
                check=True,
                capture_output=True,
                timeout=120,
            )
        return {
            "state_sha256": record["state_sha256"],
            "feedback_sha256": hashlib.sha256(feedback).hexdigest(),
            "metrics": record["metrics"],
            "dynamics": record["dynamics"],
            "video_decoded": render,
        }

    for instance in instances:
        spec = make_spec(instance)
        for index, case in enumerate(spec["held_out"]):
            name = f"i{instance:02d}-case{index:02d}-{case['terrain']}"
            a = run_one(policy, out / name, case, render=index < video_cases)
            b = run_one(policy, out / (name + "-replay"), case, render=False)
            matched = a["state_sha256"] == b["state_sha256"] and a["feedback_sha256"] == b["feedback_sha256"]
            if not matched or a["metrics"] != b["metrics"]:
                raise RuntimeError("Fresh-process replay mismatch")
            runs.append({"instance": instance, "case": index, "terrain": case["terrain"], "replay_match": matched, **a})
            (out / "progress.json").write_text(json.dumps(runs, indent=2))
            print(name, "success", a["metrics"]["success"], "score", round(a["metrics"]["score"], 3), flush=True)
        if len({json.dumps(r["dynamics"], sort_keys=True) for r in runs if r["instance"] == instance}) != 1:
            raise RuntimeError("Hidden plant drift between cases")
    values = {k: np.zeros(s, np.float32) for k, s in shapes("g1").items()}
    values["std"][:] = 1
    np.savez_compressed(out / "zero-actor.npz", **values)
    make_command_blind_policy(policy, out / "standing.npz")
    case = make_spec(instances[0])["held_out"][0]
    negatives = {
        "zero_actor": run_one(out / "zero-actor.npz", out / "negative-zero-actor", case),
        "standing": run_one(out / "standing.npz", out / "negative-standing", case, extra=("--nominal",)),
        "initial_fall": run_one(policy, out / "negative-fall", case, extra=("--initial-roll", "1.4")),
    }
    if any(r["metrics"]["success"] for r in negatives.values()):
        raise RuntimeError("Negative control passed")
    summary = {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "instance_specs": [make_spec(index) for index in instances],
        "policy_sha256": hashlib.sha256(Path(policy).read_bytes()).hexdigest(),
        "unique_cases": len(runs),
        "fresh_process_replays": len(runs),
        "all_replays_match": True,
        "cpu_physics_inference_rendering": True,
        "container_isolation_tested": False,
        "successes": sum(r["metrics"]["success"] for r in runs),
        "solvability_pass": all(r["metrics"]["success"] for r in runs),
        "runs": runs,
        "negative_controls": negatives,
    }
    (out / "validation.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--instances", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--video-cases", type=int, default=4)
    a = parser.parse_args()
    validate_run(a.policy, a.out, tuple(a.instances), a.video_cases)
