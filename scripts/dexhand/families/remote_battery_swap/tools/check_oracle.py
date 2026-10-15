"""Authoring-only: oracle robustness and negative variants, each graded by a fresh-process ``replay.py``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from scene import hands  # noqa: E402


# Marvin arm layout (sharpa): right arm J1..J7 = columns 7..13, right thumb + index = columns 36..44.
RIGHT_J2 = 8
PINCH = slice(36, 45)


def variants(actions, initial, success_step, closed_step):
    out = {"float32": actions.astype(np.float32).astype(np.float64)}
    out["nop"] = np.repeat(initial[None], 300, axis=0)
    out["nop_full_budget"] = np.repeat(initial[None], 6000, axis=0)
    out["truncated_before_cover_closed"] = actions[: closed_step - 60]
    out["one_row_short_of_hold"] = actions[: success_step - 1]
    drop = actions.copy()
    drop[720:, PINCH] = actions[480, PINCH]  # open the thumb-index pinch mid-carry, several cm above the table
    out["drop_old_cell_mid_carry"] = drop[:900]
    # knock: while the hand pinches the gray cell in the remote, the right shoulder rolls 0.6 rad over 80 controls
    row = actions[599].copy()
    sweep = []
    for t in np.linspace(0, 1, 80):
        r = row.copy()
        r[RIGHT_J2] += 0.6 * t
        sweep.append(r)
    out["knock_remote_sideways"] = np.concatenate([actions[:600], np.asarray(sweep)])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--live", required=True, help="live summary json of the oracle (success/closed steps)")
    parser.add_argument("--extra", nargs="*", default=[], help="more archives to replay (tools/negatives.py output)")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    actions, hand, _ = hands.read_trajectory(args.traj, widths={"sharpa": 58, "wuji": 54}, max_rows=6000,
                                             task="remote_battery_swap")
    task = json.loads((HERE / "task.json").read_text())
    initial = np.asarray(task["initial_targets"][hand], dtype=float)
    summary = {}
    procs = []
    live = json.loads(Path(args.live).read_text())
    jobs = [(name, rows) for name, rows in variants(actions, initial, live["success_step"],
                                                     live["stage_steps"]["cover_closed"]).items()]
    jobs += [(Path(p).stem, Path(p)) for p in args.extra]
    for name, rows in jobs:
        if args.only and name not in args.only:
            continue
        path = out / f"{name}.npz"
        if isinstance(rows, Path):
            path = rows
        else:
            hands.write_trajectory(path, rows, hand=hand, task="remote_battery_swap")
        result = out / f"{name}.json"
        procs.append((name, result, subprocess.Popen(
            [args.python, str(HERE / "replay.py"), "--task", "remote_battery_swap", "--traj", str(path), "--out",
             str(result)], cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
        if len(procs) >= 2:
            name0, result0, p0 = procs.pop(0)
            p0.wait()
            summary[name0] = result0
    for name0, result0, p0 in procs:
        p0.wait()
        summary[name0] = result0
    table = {}
    for name, result in summary.items():
        r = json.loads(result.read_text())
        table[name] = {k: r.get(k) for k in ("success", "reason", "steps", "stage", "n_actions", "state_sha",
                                             "failure_detail", "bad_trajectory")}
    (out / "summary.json").write_text(json.dumps(table, indent=2) + "\n")
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
