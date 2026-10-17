"""Authoring (not shipped): regenerate the oracle rows deterministically.

Runs the closed-loop scripted controller (tools/author.py) with the parameters in tools/oracle_params.json (Sharpa;
found by tools/search_pinch.py and tools/search_episode.py) or tools/oracle_params_wuji.json (Wuji; tools/search_wuji.py
in the modes left -> pinch -> full), appends hold rows (slack after success), and writes
``solution/trajectory.npz`` (actions + hand + task) and an authoring copy with per-row phase labels.

    python tools/make_oracle.py [--hand sharpa] [--extra-hold 100] [--labels out_with_phases.npz]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from author import Author  # noqa: E402
from search_episode import params  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--extra-hold", type=int, default=100)
    ap.add_argument("--out", default=str(HERE.parent / "solution/trajectory.npz"))
    ap.add_argument("--labels")
    args = ap.parse_args()
    if args.hand == "wuji":
        from search_wuji import params as wuji_params

        x = json.loads((HERE / "oracle_params_wuji.json").read_text())["x"]
        a = Author("wuji", **wuji_params(x))
    else:
        x = json.loads((HERE / "oracle_params.json").read_text())["x"]
        a = Author(args.hand, **params(x))
    st = a.run(verbose=False)
    if not st["success"]:
        raise SystemExit(f"authoring run did not succeed: {st['reason']}")
    success_row = len(a.rows)
    rows = np.asarray(a.rows + [a.rows[-1]] * args.extra_hold, dtype=np.float64)
    phases = np.asarray(a.phases + ["hold (slack after success)"] * args.extra_hold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    a.s.save_trajectory(rows, out)
    if args.labels:
        np.savez(args.labels, actions=rows, phases=phases, hand=np.asarray(a.s.hand), task=np.asarray("grinder_crank"))
    print(json.dumps({"path": str(out), "rows": len(rows), "success_row": success_row,
                      "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "hand": a.s.hand}))


if __name__ == "__main__":
    main()
