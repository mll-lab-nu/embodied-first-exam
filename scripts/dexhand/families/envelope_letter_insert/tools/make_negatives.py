"""Authoring evidence: negative trajectories (nop, truncations, partial push, knock-offs, drop-then-oracle).

python tools/make_negatives.py --out-dir DIR    # writes DIR/<case>.npz; grade each with replay.py in a fresh process
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo  # noqa: E402
import replay  # noqa: E402
from runtime import Session  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


def knock_off(kind):
    """Press the letter (or the envelope) and shove it off: letter off the desk edge / envelope pushed away."""
    s = Session()
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
    else:  # envelope shoved more than 5 cm
        ep, _, _ = c.envelope()
        press = ep[:2] + np.array([0.0, -0.06])
        surface = top + 0.0064
        c.run(c.pose(press, 0.0, surface + 0.06), 60, "approach")
        c.run(c.pose(press, 0.0, surface - 0.0015), 60, "press the envelope")
        c.run(c.pose(press + np.array([-0.08, 0.0]), 0.0, surface - 0.0015), 150, "shove the envelope")
    c.hold(60, "hold")
    return np.asarray(s.actions), s.status()


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
    # Partial insertion: stop the final edge push when about 85 % of the letter is inside (later push rows replaced by
    # holding that target), then the oracle's withdrawal and waiting rows.
    s.reset()
    cut = None
    for i, row in enumerate(oracle):
        f = s.step(row)
        if s.stage >= 1 and f["inserted_fraction"] >= 0.85:
            cut = i + 1
            break
    held = oracle[cut - 1]
    lift = [held + np.r_[0.03 * r, 0.0, 0.03 * r, np.zeros(len(held) - 3)] for r in np.linspace(0, 1, 51)[1:]]
    away = [lift[-1] + np.r_[0.07 * r, 0.0, 0.09 * r, np.zeros(len(held) - 3)] for r in np.linspace(0, 1, 61)[1:]]
    partial = np.vstack([oracle[:cut], np.repeat(held[None], 30, axis=0), lift, away, np.repeat(away[-1][None], 150, axis=0)])
    cases["partial_push_then_withdraw"] = partial
    rows, status = knock_off("letter_off_desk")
    cases["letter_knocked_off_desk"] = rows
    knocked = rows
    rows, status = knock_off("envelope_shoved")
    cases["envelope_shoved"] = rows
    # Drop, then resume the oracle: the failure is permanent.
    cases["knock_off_then_oracle"] = np.vstack([knocked, oracle])
    for name, rows in cases.items():
        s.save_trajectory(rows, out / f"{name}.npz")
    (out / "cases.json").write_text(json.dumps({k: len(v) for k, v in cases.items()}, indent=1) + "\n")
    print(json.dumps({k: len(v) for k, v in cases.items()}))


if __name__ == "__main__":
    main()
