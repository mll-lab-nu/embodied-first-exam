"""Authoring (not shipped): build negative / robustness variants of the oracle rows.

    python tools/negatives.py OUT_DIR
Writes one trajectory archive per case (actions + hand + task); replay each with replay.py in a fresh process.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from author import Author  # noqa: E402
from rig import Layout  # noqa: E402
from search_episode import params  # noqa: E402
import scene  # noqa: E402


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rows = np.asarray(np.load(HERE.parent / "solution/trajectory.npz")["actions"], dtype=np.float64)
    x = json.loads((HERE / "oracle_params.json").read_text())["x"]
    cases = {}
    cases["float32"] = rows.astype(np.float32).astype(np.float64)
    from runtime import Session

    s = Session(hand="sharpa")
    L = Layout(s)
    nop = np.tile(s.initial_targets, (len(rows), 1))
    cases["nop"] = nop
    cases["nop_full_budget"] = np.tile(s.initial_targets, (3000, 1))
    cases["truncated_mid_crank_row500"] = rows[:500]
    cases["truncated_before_release_row620"] = rows[:620]
    cases["one_row_short_of_hold_753"] = rows[:753]
    # knock-off: after the cranking, the right wrist sweeps sideways through the grinder hopper
    knock = rows[:700].copy()
    last = knock[-1].copy()
    ix = L.index["right_wrist_x_act"], L.index["right_wrist_y_act"], L.index["right_wrist_z_act"]
    seq = []
    start = last.copy()
    for k in range(1, 41):  # go down to the hopper height on the -y side
        r = start.copy()
        u = k / 40
        r[ix[0]] = start[ix[0]] + u * (0.36 - start[ix[0]])
        r[ix[1]] = start[ix[1]] + u * (-0.16 - start[ix[1]])
        r[ix[2]] = start[ix[2]] + u * (0.93 - start[ix[2]])
        seq.append(r)
    for k in range(1, 61):  # sweep +y through the grinder body
        r = seq[-1].copy()
        r[ix[1]] = -0.16 + k * 0.006
        seq.append(r)
    seq += [seq[-1]] * 100
    cases["knock_over_after_crank"] = np.vstack([knock, np.asarray(seq)])
    # drop the counterhold mid-crank: the left hand opens and withdraws while the right hand keeps cranking
    drop = rows.copy()
    left_fingers = [i for i, n in enumerate(L.names) if n.startswith("left_") and "wrist" not in n]
    lyi = L.index["left_wrist_y_act"]
    for i in range(420, len(drop)):
        u = min(1.0, (i - 420) / 20)
        drop[i, left_fingers] = (1 - u) * rows[420, left_fingers]
        drop[i, lyi] = rows[420, lyi] + 0.1 * min(1.0, max(0.0, (i - 440) / 20))
    cases["counterhold_released_mid_crank"] = drop
    # wrong direction and too few turns, produced by the same controller
    for name, extra in (("crank_counter_clockwise", dict(direction=-1, target_turns=2.06)),
                        ("only_1p5_turns", dict(target_turns=1.5))):
        a = Author("sharpa", **{**params(x), **extra})
        a.run(verbose=False)
        r = list(a.rows)
        cases[name] = np.asarray(r + [r[-1]] * 100)
    for name, actions in cases.items():
        if name != "float32":  # float32 rows are kept exactly as rounded (no clipping)
            actions = np.clip(actions, s.lo, s.hi)
        s.save_trajectory(actions, out / f"{name}.npz")
        print(name, actions.shape)
    s.close()


if __name__ == "__main__":
    main()
