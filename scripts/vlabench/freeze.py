"""Verify the VLABench frozen instances and oracles (trusted authoring step; run it through freeze.sh).

For every candidate in tasks.json (frozen/<task>/instance.json and oracle.npy, imported from PR #4, commit ad3c5109), in the
eai-vlabench image:
1. the instance rebuilds: the compiled model's and the initial state's hashes match the instance (vlb_tool.Session);
2. it is not solved at the start, and reset() is bit-exact (a step, then reset, gives the initial state again);
3. the oracle (VLABench's expert, recorded as control steps) replayed from the start ends with the task's success,
   exactly at its last action (the episode ends there);
4. two more replays, each in a fresh process, end in the same state and succeed.
Writes frozen/report.json (read by generate.py). Each task is checked in its own process, several at a time.

    bash scripts/vlabench/freeze.sh [task ...]
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "frozen"
sys.path.insert(0, str(HERE / "shared"))


def replay_child(task: str) -> None:
    """Fresh process: one replay of the oracle; prints its status as JSON."""
    import numpy as np
    import vlb_tool

    r = vlb_tool.Session(FROZEN / task / "instance.json").replay(np.load(FROZEN / task / "oracle.npy"))
    print(json.dumps(r), flush=True)
    os._exit(0)


def check_child(task: str) -> None:
    """Fresh process: checks 1-3 for one task; prints a JSON record."""
    import numpy as np
    import vlb_tool

    rec = {"task": task}
    try:
        s = vlb_tool.Session(FROZEN / task / "instance.json")  # 1: hashes checked in reset()
        rec.update(instance_sha=s.instance_sha, seed=s.spec["seed"], instruction=s.instruction, control_dt=s.dt)
        rec["initial_success"] = s.success()
        sha0 = s.state_sha()
        s.step(s.targets)
        s.reset()
        rec["reset_exact"] = s.state_sha() == sha0  # 2
        actions = np.load(FROZEN / task / "oracle.npy")
        r = s.replay(actions)  # 3: raises if the task terminated before the last action
        rec.update(n_actions=len(actions), oracle_success=r["success"], ends_at_success=r["done"],
                   live_state_sha=r["state_sha"])  # fmt: skip
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
    print(json.dumps(rec), flush=True)
    os._exit(0)


def run(args: list[str]) -> dict:
    p = subprocess.run([sys.executable, __file__, *args], capture_output=True, text=True, timeout=3600)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        return {"error": f"exit {p.returncode}: {p.stderr[-500:]}"}
    return json.loads(lines[-1])


def verify(task: str) -> dict:
    rec = run(["--check", task])
    if "error" not in rec and rec.get("oracle_success"):
        replays = [run(["--replay", task]) for _ in range(2)]
        rec["replay_state_sha"] = [r.get("state_sha") for r in replays]
        rec["deterministic"] = all(r.get("state_sha") == rec["live_state_sha"] for r in replays)
        rec["replay_success"] = all(r.get("success") for r in replays)
    rec["verified"] = bool(
        "error" not in rec
        and not rec.get("initial_success")
        and rec.get("reset_exact")
        and rec.get("oracle_success")
        and rec.get("ends_at_success")
        and rec.get("deterministic")
        and rec.get("replay_success")
    )
    return rec


def main(tasks: list[str]) -> None:
    path = FROZEN / "report.json"
    report = json.loads(path.read_text()) if path.exists() else {}
    with ThreadPoolExecutor(max_workers=int(os.environ.get("FREEZE_JOBS", "6"))) as pool:
        for rec in pool.map(verify, tasks):
            report[rec["task"]] = rec
            print(f"{rec['task']:36s} n={rec.get('n_actions')} verified={rec['verified']} {rec.get('error', '')}")
    path.write_text(json.dumps(dict(sorted(report.items())), indent=1) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--replay":
        replay_child(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--check":
        check_child(sys.argv[2])
    else:
        main(sys.argv[1:] or json.loads((HERE / "tasks.json").read_text())["candidates"])
