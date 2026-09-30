"""Harbor verifier: trusted descriptor, two isolated processes, native predicates."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--instance", default=str(HERE / "instance.json"))
    p.add_argument("--traj", default="/app/output/trajectory.npz")
    p.add_argument("--logs", default="/logs/verifier")
    args = p.parse_args()
    logs = Path(args.logs)
    logs.mkdir(parents=True, exist_ok=True)
    reward = dict(success=0, deterministic=0, n_actions=0, sim_steps=0,
                  missing_trajectory=0, grader_error=0, invalid_trajectory=0)
    details = dict(evaluation="privileged-state coding-agent evaluation")
    start = time.monotonic()
    try:
        if not Path(args.traj).is_file():
            reward["missing_trajectory"] = 1
            return
        sys.path.insert(0, str(HERE))
        from vlb_traj import load_archive
        try:
            data = load_archive(args.traj)
            reward["n_actions"] = len(data["actions"])
        except Exception as exc:
            reward["invalid_trajectory"] = 1
            details["error"] = repr(exc)
            return
        results = []
        for i in range(2):
            output = logs / f"replay-{i}.json"
            command = [sys.executable, "-I", str(HERE / "worker.py"),
                       "replay", "--instance", args.instance, "--traj", args.traj,
                       "--result", str(output)]
            env = {k: v for k, v in os.environ.items()
                   if k not in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD")}
            with (logs / f"replay-{i}.log").open("w") as log:
                proc = subprocess.run(command, env=env, cwd="/", stdout=log,
                                      stderr=subprocess.STDOUT, timeout=3600)
            if proc.returncode:
                # Worker distinguishes validation failure (2) and infrastructure (3).
                reward["invalid_trajectory" if proc.returncode == 2 else "grader_error"] = 1
                details["failed_replay"] = i
                return
            results.append(json.loads(output.read_text()))
        reward["deterministic"] = int(results[0]["state_sha"] == results[1]["state_sha"])
        reward["success"] = int(all(r["success"] for r in results) and reward["deterministic"])
        reward["sim_steps"] = sum(r["sim_steps"] for r in results)
        reward["physics_steps"] = sum(r["physics_steps"] for r in results)
        states = [np.load(logs / f"replay-{i}.json.state.npz")["integration"] for i in range(2)]
        reward["max_abs_state_difference"] = float(np.max(np.abs(states[0]-states[1])))
        details["replays"] = results
    except Exception as exc:
        reward["grader_error"] = 1
        details["error"] = repr(exc)
    finally:
        reward["verifier_wall_seconds"] = time.monotonic()-start
        (logs / "reward.txt").write_text(str(reward["success"])+"\n")
        (logs / "reward.json").write_text(json.dumps(reward, indent=2)+"\n")
        (logs / "details.json").write_text(json.dumps(details, indent=2)+"\n")
        print(json.dumps(reward))

if __name__ == "__main__": main()
