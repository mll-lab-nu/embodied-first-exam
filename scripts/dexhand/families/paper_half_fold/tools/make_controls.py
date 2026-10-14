"""Authoring: write the positive and negative control trajectories used as evidence (not copied into tasks).

All negatives are built from the packaged oracle rows or the frozen reset targets, so they are deterministic:

    python scripts/dexhand/families/paper_half_fold/tools/make_controls.py --out $OUT/paper-controls
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
sys.path[:0] = [str(FAMILY), str(REPO / "scripts/dexhand/shared")]
from runtime import Session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    with np.load(FAMILY / "solution/trajectory.npz", allow_pickle=False) as archive:
        rows = archive["actions"].copy()
    sharpa, wuji = Session(hand="sharpa"), Session(hand="wuji")
    hold = sharpa.hold_action()
    written = {}

    def save(name, actions, session=sharpa, **extra):
        path = out / f"{name}.npz"
        if extra:
            np.savez_compressed(path, actions=np.asarray(actions, dtype=np.float64), **extra)
        else:
            session.save_trajectory(np.asarray(actions, dtype=np.float64), path)
        written[name] = {"path": str(path), "rows": int(len(actions)), "width": int(np.asarray(actions).shape[1])}

    save("oracle", rows)
    save("oracle_float32", rows.astype(np.float32), hand=np.array("sharpa"))  # what a float32 client transports
    save("nop_hold", np.repeat(hold[None], 1500, 0))
    no_press = rows[584].copy()
    no_press[2] = 0.425
    save("partial_no_crease_press", np.r_[rows[:585], np.repeat(no_press[None], 400, 0)])
    save("partial_early_stop", rows[:1050])
    start = rows[59].copy()
    pull = []
    for i in range(1, 101):
        q = start.copy()
        q[2] -= 0.10 * i / 100
        q[0] += 0.04 * i / 100
        pull.append(q)
    save("drop_pull_over_edge", np.r_[rows[:60], pull, rows[60:300]])
    save("forged_success_flags", np.repeat(hold[None], 50, 0), hand=np.array("sharpa"), success=np.array(True),
         stage=np.array(4), released_hold_steps=np.array(100))
    save("wrong_width_sharpa_rows_labelled_wuji", rows[:50], hand=np.array("wuji"))
    save("wrong_width_26_unlabelled", np.zeros((50, 26)), task=np.array("paper_half_fold"))
    whold = wuji.hold_action()
    save("wuji_nop_hold", np.repeat(whold[None], 300, 0), session=wuji)
    lo, hi = wuji.model.actuator_ctrlrange.T
    phase = np.linspace(0, 2 * np.pi, 200)
    motion = np.repeat(whold[None], 200, 0)
    motion[:, 2] += 0.03 * np.sin(phase / 2)  # lift and lower the wrist stage by up to 3 cm
    motion[:, 6:] = np.clip(whold[6:] - 0.4 * np.sin(phase)[:, None] ** 2, lo[6:], hi[6:])  # open and re-curl
    save("wuji_wrist_and_finger_motion", motion, session=wuji)
    (out / "controls.json").write_text(json.dumps(written, indent=2) + "\n")
    print(json.dumps(written, indent=2))


if __name__ == "__main__":
    main()
