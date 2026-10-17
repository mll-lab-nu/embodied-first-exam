"""Authoring evidence (not shipped): negative trajectories on the Marvin arm rig.

python tools/make_negatives.py --out-dir DIR    # writes DIR/<case>.npz; grade each with replay.py in a fresh process

Cartesian negatives (knock-offs) are authored on the floating wrist stage (tools/floating_task.json, demo.Controller)
and moved onto the arm with the same hand-pose tracking as the oracle (tools/arm_port.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.append(str(HERE.parents[1] / "shared"))
import demo  # noqa: E402
import replay  # noqa: E402
from runtime import Session  # noqa: E402
import arm_port  # noqa: E402

FLOATING = json.loads((HERE / "tools/floating_task.json").read_text())


def knock_off_floating(kind, shove=(0.08, 0.0), depth=0.0015, press_offset=(0.03, -0.06)):
    """Press the letter (or the envelope) and shove it off, on the floating stage: the stage rows."""
    s = Session(config=FLOATING)
    posture = np.asarray(s.config["initial_targets"]["sharpa"][6:])
    c = demo.Controller(s, posture, 0.55)
    top = s.config["desk_top_z"]
    if kind == "letter_off_desk":
        lp, _ = c.letter()
        press, surface = lp[:2].copy(), top + s.config["letter"]["thickness_m"]
        c.run(c.pose(press, 0.0, surface + 0.06), 60, "approach")
        c.run(c.pose(press, 0.0, surface - 0.0015), 60, "press")
        goal = press + np.array([0.0, -0.33])
        c.run(c.pose(goal, 0.0, surface - 0.0015), 200, "shove the letter off the desk")
    else:  # envelope shoved more than 5 cm (towards the robot: the arm reaches the mouth side, not the far side)
        ep, _, _ = c.envelope()
        press = ep[:2] + np.asarray(press_offset)
        surface = top + 0.0064
        c.run(c.pose(press, 0.0, surface + 0.06), 60, "approach")
        c.run(c.pose(press, 0.0, surface - depth), 60, "press the envelope")
        c.run(c.pose(press + np.asarray(shove), 0.0, surface - depth), 150, "shove the envelope")
    c.hold(60, "hold")
    return np.asarray(s.actions)


def knock_off(kind, **kw):
    rows, status, _ = arm_port.track_floating(knock_off_floating(kind, **kw), slow=2, hold=30)
    return rows, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    oracle, hand, _ = replay.load_trajectory(HERE / "solution/trajectory.npz")
    s = Session(hand="sharpa")
    cases = {}
    cases["nop"] = np.repeat(s.hold_action()[None], 600, axis=0)
    st = s.replay(oracle)
    stage_steps = st["stage_steps"]
    cases["truncated_before_stage1"] = oracle[: stage_steps["letter_at_mouth"] - 1]
    cases["truncated_before_stage2"] = oracle[: stage_steps["letter_inserted"] - 1]
    cases["truncated_before_release"] = oracle[: stage_steps["released_hold"] - 1]
    cases["one_row_short_of_the_hold"] = oracle[: st["steps"] - 1]
    # Released too early: the oracle until the letter is at the mouth, then the hand rises straight up and waits.
    lay_right = slice(7, 14)
    held = oracle[stage_steps["letter_at_mouth"]].copy()
    up = held.copy()
    up[8] -= 0.25  # right shoulder roll: lift the hand away
    lift = np.linspace(held, up, 80)
    cases["stage1_only_then_release"] = np.vstack([oracle[: stage_steps["letter_at_mouth"] + 1], lift,
                                                   np.repeat(up[None], 200, axis=0)])
    rows, status = knock_off("envelope_shoved")
    cases["envelope_shoved"] = rows
    # Shove, then resume the oracle: the failure is permanent.
    cases["envelope_shoved_then_oracle"] = np.vstack([rows, oracle])
    for name, rows in cases.items():
        s.save_trajectory(rows, out / f"{name}.npz")
    (out / "cases.json").write_text(json.dumps({k: len(v) for k, v in cases.items()}, indent=1) + "\n")
    print(json.dumps({k: len(v) for k, v in cases.items()}))


if __name__ == "__main__":
    main()
