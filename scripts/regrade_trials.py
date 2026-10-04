#!/usr/bin/env python3
"""Re-run the bound privileged verifier of a trial of the active release into a new evidence directory."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym_versions import require_task
from topogym.utils.process_limits import run_guarded


def original_task(trial):
    """Use Harbor's recorded path, never reconstruct it from a same-named task."""
    trial = Path(trial)
    result = json.loads((trial / "result.json").read_text())
    value = (result.get("task_id") or {}).get("path")
    if not value and (trial / "config.json").is_file():
        value = (json.loads((trial / "config.json").read_text()).get("task") or {}).get("path")
    if not value:
        raise ValueError(f"Trial has no recorded task path: {trial}")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"Trial task path is relative/ambiguous: {value}")
    return path


def plan(trial, output, gpu):
    task = original_task(trial)
    bound = require_task(task, ROOT, inspect_docker=True)
    if (task / "environment/sim").exists():
        raise ValueError("Standard trials require their original service recordings; privileged regrade is not applicable")
    trajectory = Path(trial) / "artifacts/app/output"
    if not (trajectory / "trajectory.npz").is_file():
        raise ValueError("No submitted trajectory")
    instance = json.loads((task / "tests/instance.json").read_text())
    command = ["docker", "run", "--rm", "--name", "topogym-regrade-" + uuid.uuid4().hex,
        "--network", "none", "--gpus", "device=" + gpu,
        "--user", f"{os.getuid()}:{os.getgid()}", "--shm-size", "2g", "-e", "HOME=/tmp",
        "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "PYTHONPATH=/tests:/opt/topogym",
        "-v", f"{task}/tests:/tests:ro", "-v", f"{trajectory}:/app/output:ro",
        "-v", f"{output}:/logs/verifier", "-w", "/tmp", bound["runtime_binding"]["image"]["id"],
        "python", "/tests/grade.py", "--family", instance["task"], "--instance", "/tests/instance.json",
        "--traj", "/app/output/trajectory.npz", "--repeat", "2"]
    return dict(trial=str(trial), task=str(task), bound=bound, output=str(output), command=command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()
    job = args.job.resolve()
    output = (args.output or job / "regrades" / str(time.time_ns())).resolve()
    if output.exists():
        parser.error("Output already exists; retain previous evidence and choose a new directory")
    plans = []
    try:
        for path in sorted(job.glob("*/result.json")):
            trial = path.parent
            reward = json.loads((trial / "verifier/reward.json").read_text())
            if not reward.get("grader_error") and reward.get("video_rendered"):
                continue
            plans.append(plan(trial, output / trial.name, args.gpu))
        if not plans:
            print("No privileged regrade candidates")
            return 0
        output.mkdir(parents=True)
        (output / "plan.json").write_text(json.dumps(plans, indent=2) + "\n")
        for item in plans:
            folder = Path(item["output"]); folder.mkdir()
            (folder / "supervision").mkdir()
            try:
                code = run_guarded(item["command"], folder / "supervision", cwd=ROOT, env=dict(os.environ))
            finally:
                name = item["command"][item["command"].index("--name") + 1]
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
            if code:
                return code
            reward = json.loads((folder / "reward.json").read_text())
            if reward.get("grader_error") or reward.get("infra_error") or reward.get("instance_mismatch"):
                return 2
        print(output)
        return 0
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"Regrade blocked: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
