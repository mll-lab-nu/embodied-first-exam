"""Validate the archive and replay with independently injected code in fresh processes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

from casa_traj import load_actions


def grade(trajectory):
    if not Path(trajectory).is_file():
        return dict(success=0, missing_trajectory=1, grader_error=0)
    try:
        actions = load_actions(trajectory)
    except (ValueError, OSError, KeyError, EOFError):
        return dict(success=0, invalid_trajectory=1, grader_error=0)
    results = []
    with tempfile.TemporaryDirectory(prefix="rcb-casa-verifier-") as tmp:
        for index in range(2):
            output = Path(tmp) / f"replay-{index}.json"
            run = subprocess.run([sys.executable, str(Path(__file__).with_name("casa_traj.py")),
                "replay", "--instance", str(Path(__file__).with_name("instance.npz")),
                "--traj", str(Path(trajectory).resolve()), "--result", str(output)],
                capture_output=True, text=True, timeout=3600)
            print(run.stdout, file=sys.stderr)
            print(run.stderr, file=sys.stderr)
            if run.returncode or not output.is_file():
                raise RuntimeError("fresh-process replay failed")
            results.append(json.loads(output.read_text()))
    deterministic = results[0]["state_sha"] == results[1]["state_sha"]
    return dict(success=int(deterministic and all(r["success"] for r in results)),
        deterministic=int(deterministic), n_actions=len(actions), sim_steps=len(actions),
        physics_steps=25 * len(actions), replay_count=2,
        final_reward=results[0]["final_reward"], position_error=results[0]["position_error"],
        orientation_cos=results[0]["orientation_cos"], grader_error=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", default="/app/output/trajectory.npz")
    args = parser.parse_args()
    try:
        result = grade(args.traj)
    except Exception:
        traceback.print_exc()
        result = dict(success=0, grader_error=1)
    logs = Path(os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"))
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "reward.txt").write_text(f"{result['success']}\n")
    (logs / "reward.json").write_text(json.dumps(result) + "\n")
    print(json.dumps(result))
