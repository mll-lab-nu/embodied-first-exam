#!/usr/bin/env python3
"""Authoring tool: derive negative-control trajectories from the oracle rows (evidence for the strict predicate).

Writes `<out>/<case>.npz` (agent-format archives) and `<out>/cases.json` (expected verdicts). Physical cases change
only motor targets; metadata cases exercise the archive reader. Run every case through the task's own grader.

Physical cases (Sharpa, 2000 Hz rows; times are simulated seconds of the oracle):
  oracle_float32    the oracle rounded to float32: documents the sensitivity of the accepted grip (fails)
  nop_hold          the reset targets held for 20 s: nothing is swept (0/6)
  truncated         the oracle cut one row before its 1.0 s terminal hold completes (132,391 rows)
  no_lift           the left (dustpan) arm keeps its targets from 59.2 s: all six pieces in a pan left on the floor
  skip_cleanup      the right arm keeps the broom raised from 43.2 s to 56.2 s (no cleanup pass), then rejoins the
                    oracle over 1 s: the piece the cleanup pass recovers stays outside, the pan is lifted with 5/6
  drop_dustpan      the left-hand fingers open at 61.0 s while the loaded pan is lifted
  drop_broom        the right-hand fingers open at 8.0 s during the first sweeping pass
  wuji_hold         Wuji-labelled 54-wide rows (arm reset targets, zero fingers): valid width, reward 0
Metadata cases: wrong width, Sharpa rows labelled wuji, Wuji rows labelled sharpa, unknown hand, other task,
actuator-name mismatch, NaN, out-of-range target, too many rows, empty, an object array, forged success members.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
DT = 0.0005


def load_oracle():
    """The oracle rows (float64) from solution/trajectory.json + parts, checked by the shared loader."""
    import sys

    sys.path.insert(0, str(FAMILY.parents[1] / "shared/solution"))
    from solution_parts import load

    return load(FAMILY / "solution")


def step(t: float) -> int:
    return int(round(t / DT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    oracle = np.ascontiguousarray(load_oracle()[0])
    reset = np.load(FAMILY / "assets/reset.npz", allow_pickle=False)
    hold = reset["initial_ctrl"]
    names = [str(n) for n in reset["actuator_names"]]
    left_arm, right_arm = slice(0, 7), slice(7, 14)
    left_hand, right_hand = slice(14, 36), slice(36, 58)
    cases = {}

    def save(name, expect, note, **arrays):
        arrays.setdefault("hand", np.array("sharpa"))
        np.savez_compressed(out / f"{name}.npz", **arrays)
        cases[name] = {"expected_reward": expect, "note": note}

    save("oracle", 1, "the packaged oracle rows (positive control)", actions=oracle)
    save("oracle_float32", 0, "the oracle rows rounded to float32 (rcb_client.submit's wire type): the broom grip "
         "rotation passes 0.25 rad, tool_slipped_in_hand", actions=oracle.astype(np.float32))
    save("nop_hold", 0, "reset targets held for 20 s", actions=np.repeat(hold[None], step(20.0), axis=0))
    # The oracle's terminal hold completes on physics step 132,392 (bit-exact replay, tools/bitexact.py).
    save("truncated", 0, "oracle cut after 132,391 rows: the 1.0 s terminal hold is one step short",
         actions=oracle[:132391])
    rows = oracle.copy()
    rows[step(59.2):, left_arm] = rows[step(59.2), left_arm]
    save("no_lift", 0, "dustpan arm frozen from 59.2 s: pan never lifted", actions=rows)
    rows = oracle.copy()
    a, b, c = step(43.2), step(56.2), step(57.2)
    rows[a:b, right_arm] = rows[a, right_arm]
    weights = np.linspace(0.0, 1.0, c - b + 1)[1:, None]
    rows[b:c, right_arm] = (1 - weights) * rows[a, right_arm] + weights * oracle[c, right_arm]
    save("skip_cleanup", 0, "broom kept raised 43.2-56.2 s (cleanup pass skipped), then smoothly rejoins", actions=rows)
    rows = oracle.copy()
    rows[step(61.0):, left_hand] = 0.0
    save("drop_dustpan", 0, "left-hand finger targets set to 0 (open) at 61.0 s during the lift", actions=rows)
    rows = oracle.copy()
    rows[step(8.0):, right_hand] = 0.0
    save("drop_broom", 0, "right-hand finger targets set to 0 (open) at 8.0 s", actions=rows)

    wuji_hold = np.zeros((step(3.0), 54))
    wuji_hold[:, :14] = hold[:14]
    save("wuji_hold", 0, "Wuji-labelled 54-wide rows (arm reset targets, zero fingers, 3 s): the fingers open, the tools drop",
         actions=wuji_hold, hand=np.array("wuji"))
    short = oracle[:2000]
    save("bad_width", 0, "57 columns", actions=short[:, :57])
    save("sharpa_rows_labelled_wuji", 0, "58-wide rows with hand=wuji", actions=short, hand=np.array("wuji"))
    save("wuji_rows_labelled_sharpa", 0, "54-wide rows with hand=sharpa", actions=wuji_hold[:2000])
    save("unknown_hand", 0, "hand=allegro", actions=short, hand=np.array("allegro"))
    save("other_task", 0, "task=essential_cube_layer", actions=short, task=np.array("essential_cube_layer"))
    save("actuator_names_mismatch", 0, "actuator_names reversed", actions=short,
         actuator_names=np.array(names[::-1]))
    nan = short.copy()
    nan[100, 3] = np.nan
    save("nan", 0, "one NaN", actions=nan)
    wide = short.copy()
    wide[100, 0] = 10.0
    save("out_of_range", 0, "one target far outside the joint limit", actions=wide)
    save("too_many_rows", 0, "160,001 rows", actions=np.repeat(hold[None], 160_001, axis=0))
    save("empty", 0, "zero rows", actions=np.zeros((0, 58)))
    save("forged_success", 0, "nop rows plus success=1, in_pan=6, state_sha and reward members",
         actions=np.repeat(hold[None], step(2.0), axis=0), success=np.array(1), in_pan=np.array(6),
         reward=np.array(1.0), state_sha=np.array("0" * 64))
    with open(out / "object_array.npz", "wb") as stream:
        np.savez(stream, actions=np.array([[1, 2], [3]], dtype=object), hand=np.array("sharpa"))
    cases["object_array"] = {"expected_reward": 0, "note": "pickled object array (must not be loaded)"}
    (out / "cases.json").write_text(json.dumps(cases, indent=1) + "\n")
    print(json.dumps({k: v["expected_reward"] for k, v in cases.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
