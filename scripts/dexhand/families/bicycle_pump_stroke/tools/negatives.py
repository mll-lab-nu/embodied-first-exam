"""Authoring-only: build negative trajectories from the oracle and check them in fresh replay processes.

Cases: nop (hold the reset targets), nop to the episode budget, truncations (before the 6th stroke, after the 6th
stroke but before the release hold, one row short of the hold), five strokes only, shallow strokes (85 % travel),
a lateral knock into the pump mid-episode, the knock followed by the rest of the oracle (later rows cannot undo a
failure), and a Wuji-labelled Sharpa-width archive (rejected).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
from controller import Pumper  # noqa: E402
from runtime import TASK, Session  # noqa: E402
from scene import hands  # noqa: E402


def write(path, rows, hand="sharpa"):
    hands.write_trajectory(path, np.asarray(rows, dtype=np.float64), hand=hand, task=TASK)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--params", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, hand, _ = hands.read_trajectory(args.oracle, widths={"sharpa": 28, "wuji": 26}, max_rows=3000, task=TASK)
    s = Session(hand=hand)
    status = s.replay(rows)
    success_step = status["steps"]
    sixth = status["stroke_controls"][5]
    third = status["stroke_controls"][2]
    cases = {}
    hold = np.repeat(s.initial_targets[None], len(rows), axis=0)
    cases["nop"] = hold
    cases["nop_budget"] = np.repeat(s.initial_targets[None], 3000, axis=0)
    cases["truncated_before_6th_stroke"] = rows[: sixth - 5]
    cases["truncated_before_release_hold"] = rows[: sixth + 40]
    cases["one_row_short_of_hold"] = rows[: success_step - 1]
    params = json.loads(args.params)
    five = Session(hand=hand)
    five_rows = Pumper(five, dict(params, strokes=5)).run()
    cases["five_strokes"] = np.vstack([five_rows, np.repeat(five_rows[-1:], 200, axis=0)])
    shallow = Session(hand=hand)
    shallow_rows = Pumper(shallow, dict(params, strokes=8, press_world_z=params["press_world_z"] + 0.025)).run()
    cases["shallow_strokes_85pct"] = np.vstack([shallow_rows, np.repeat(shallow_rows[-1:], 200, axis=0)])
    # Knock: after the third stroke, sweep the hand sideways (+x) through the pump barrel at mid height.
    knock = [r.copy() for r in rows[: third + 10]]
    last = knock[-1].copy()
    origin = np.asarray(s.config["stage_origin"])
    side = last.copy()
    side[0] = 0.30 - origin[0]
    side[2] = 1.05 - origin[2]
    for t in np.linspace(0, 1, 40)[1:]:
        r = last.copy()
        r[2] = last[2] + (1.25 - origin[2] - last[2]) * t
        r[6:] = last[6:] * (1 - t)  # open the hand while lifting off the handle
        knock.append(r)
    up = knock[-1].copy()
    for t in np.linspace(0, 1, 30)[1:]:
        r = up.copy()
        r[0] = up[0] + (side[0] - up[0]) * t
        knock.append(r)
    lowered = knock[-1].copy()
    for t in np.linspace(0, 1, 30)[1:]:
        r = lowered.copy()
        r[2] = lowered[2] + (side[2] - lowered[2]) * t
        knock.append(r)
    pushed = knock[-1].copy()
    for t in np.linspace(0, 1, 60)[1:]:
        r = pushed.copy()
        r[0] = pushed[0] + 0.30 * t
        knock.append(r)
    knock = np.asarray(knock)
    cases["knock_pump_sideways"] = knock
    cases["knock_then_oracle_rest"] = np.vstack([knock, rows[third + 10:]])
    results = {}
    for name, case_rows in cases.items():
        path = out / f"{name}.npz"
        write(path, case_rows, hand)
        results[name] = path
    bad = out / "sharpa_width_labelled_wuji.npz"
    write(bad, rows, "wuji")
    results["sharpa_width_labelled_wuji"] = bad
    summary = {}
    for name, path in results.items():
        result_path = out / f"{name}.result.json"
        subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", TASK, "--traj", str(path), "--out",
                        str(result_path)], check=True, cwd=HERE, stdout=subprocess.DEVNULL)
        r = json.loads(result_path.read_text())
        summary[name] = {k: r.get(k) for k in ("success", "reason", "steps", "stage", "strokes", "n_actions",
                                                "bad_trajectory", "failure_detail", "error")}
        print(name, json.dumps(summary[name]), flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
