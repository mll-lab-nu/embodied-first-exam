"""Verifier entry point (privileged mode): replay /app/output/trajectory.npz from the frozen instance, write rewards.

    python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2

Replays `--repeat` times, each in its own fresh process (`hc_tools.py replay`) on the verifier's own copy of the
instance and tools. Success (reward.txt 1) needs every replay to succeed under HumanCLAW's rule (NavSR@20cm or
InteractSR) AND every replay to end in the same state hash, and the frozen start rebuilt here to hash as recorded
(instance.json start_sha). Writes /logs/verifier/reward.txt (1/0), reward.json (numbers only) and replay.mp4 +
replay.last.png (the first replay's recorded poses, for people; never decides anything).

Whose failure a 0 is (every path writes a reward; deterministic, grader_error and infra_error are always present):
- the agent's: no file (missing_trajectory), a file that is not a trajectory (bad_trajectory: not an npz, no
  `actions`, pickled / object arrays, the wrong shape, NaN/inf, an invalid row, more than max_steps rows), a replay
  that does not succeed, or replays that disagree (deterministic 0);
- the verifier's (grader_error 1 + infra_error 1, no verdict on the agent): a replay process that dies or runs out of
  time (replay_timed_out), the rebuilt start not matching the instance (instance_ok 0), any other error here.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback

LOG = os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier")
HERE = os.path.dirname(os.path.abspath(__file__))
REPLAY_TIMEOUT_S = 1800      # one replay: ~40 s to build + <= 100 skills at ~1-2 s each on an L40S / 4090


def write(out: dict) -> None:
    os.makedirs(LOG, exist_ok=True)
    num = {k: (int(v) if isinstance(v, bool) else v) for k, v in out.items() if isinstance(v, (bool, int, float))}
    for k in ("success", "deterministic", "grader_error", "infra_error"):
        num.setdefault(k, 0)
    open(f"{LOG}/reward.json", "w").write(json.dumps(num, indent=1) + "\n")
    open(f"{LOG}/reward.txt", "w").write(f"{int(num.get('success', 0))}\n")
    print(json.dumps(out), file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="/tests/instance.json")
    ap.add_argument("--traj", default="/app/output/trajectory.npz")
    ap.add_argument("--repeat", type=int, default=2)
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    import hc_core
    import hc_tools
    inst = hc_core.load_instance(a.instance)
    if not os.path.isfile(a.traj) or os.path.islink(a.traj):
        return write({"success": 0, "missing_trajectory": 1})
    try:
        actions = hc_tools.load_actions(a.traj, int(inst.get("max_steps", 100)))
    except Exception as exc:  # noqa: BLE001 -- the agent's file: its 0
        print(f"[grade] bad trajectory: {exc!r}", file=sys.stderr)
        return write({"success": 0, "bad_trajectory": 1})
    runs = []
    for i in range(a.repeat):
        js = f"/tmp/replay{i}.json"
        cmd = [sys.executable, os.path.join(HERE, "hc_tools.py"), "replay", a.traj, "--instance", a.instance, "--json", js]
        if i == 0:
            cmd += ["--video", f"{LOG}/replay.mp4"]
        try:
            subprocess.run(cmd, check=True, timeout=REPLAY_TIMEOUT_S, stdout=sys.stderr)
        except subprocess.TimeoutExpired:
            return write({"success": 0, "grader_error": 1, "infra_error": 1, "replay_timed_out": 1})
        except subprocess.CalledProcessError as exc:
            return write({"success": 0, "grader_error": 1, "infra_error": 1, "replay_rc": int(exc.returncode)})
        runs.append(json.load(open(js)))
    instance_ok = all(not inst.get("start_sha") or r["start_sha"] == inst["start_sha"] for r in runs)
    det = len({r["final_sha"] for r in runs}) == 1
    ok = instance_ok and det and all(r["success"] for r in runs)
    r0 = runs[0]
    out = {"success": int(ok), "deterministic": int(det), "instance_ok": int(instance_ok),
           "grader_error": int(not instance_ok), "infra_error": int(not instance_ok),
           "replays": len(runs), "replays_succeeded": sum(int(r["success"]) for r in runs),
           "n_actions": int(len(actions)), "n_executed": r0["n_executed"], "n_ignored": r0["n_ignored"],
           "ended_by_stop": int(bool(r0.get("active_stop"))), "n_sit": int(r0.get("n_sit") or 0),
           "video": int(bool(r0.get("video")))}
    if r0.get("final_body_target_aabb_distance_m") is not None:
        out["final_body_target_distance_m"] = float(r0["final_body_target_aabb_distance_m"])
    write(out)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        write({"success": 0, "grader_error": 1, "infra_error": 1})
