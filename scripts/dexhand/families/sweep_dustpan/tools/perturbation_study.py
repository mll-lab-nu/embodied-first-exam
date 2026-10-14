#!/usr/bin/env python3
"""Authoring study: how robust is the oracle (accepted controls) to small action perturbations?

Cases (each a full replay with the packaged Session and predicate, run in parallel worker processes):
  float32              every row rounded to float32 (what rcb_client.submit sends)
  noise<sigma>_s<seed> i.i.d. Gaussian noise of sigma rad on the 44 finger targets of every row
  base                 the unperturbed oracle (reference)
Optional `--grip-offset D --side r|l|both`: add D rad to the holding flexion targets of that hand first (a firmer or
looser grip), to separate grip-force margin from the threshold.

    PYTHONPATH=<family>:<scripts/dexhand/shared> python tools/perturbation_study.py --out study.json --workers 8
"""

from __future__ import annotations

import argparse
import json
from multiprocessing import Pool
from pathlib import Path
import time

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
FINGERS = slice(14, 58)
HANDS = {"l": slice(14, 36), "r": slice(36, 58)}


def load_oracle():
    """The oracle rows (float64) from solution/trajectory.json + parts, checked by the shared loader."""
    import sys

    sys.path.insert(0, str(FAMILY.parents[1] / "shared/solution"))
    from solution_parts import load

    return load(FAMILY / "solution")


def flexion_mask(names: list[str]) -> np.ndarray:
    """Flexion joints of the Sharpa fingers (MCP_FE, PIP, DIP, thumb CMC_FE/MCP_FE/IP); abduction joints excluded."""
    keys = ("MCP_FE", "PIP", "DIP", "CMC_FE", "_IP")
    return np.array([any(k in n for k in keys) and not n.endswith("_AA") for n in names])


def run(case: dict) -> dict:
    from runtime import Session

    session = Session()
    rows = np.ascontiguousarray(load_oracle()[0], dtype=np.float64)
    lo, hi = session.ctrl_range.T
    if case.get("extra_hold"):
        rows = np.concatenate([rows, np.repeat(rows[-1:], case["extra_hold"], axis=0)])
    if case.get("grip_offset"):
        mask = np.zeros(58, bool)
        flex = flexion_mask(session.actuator_names)
        for side in ("l", "r") if case["side"] == "both" else (case["side"],):
            mask[HANDS[side]] = flex[HANDS[side]]
        rows[:, mask] += case["grip_offset"]
    if case["kind"] == "float32":
        rows = rows.astype(np.float32).astype(np.float64)
    elif case["kind"] == "noise":
        rng = np.random.default_rng(case["seed"])
        rows[:, FINGERS] += rng.normal(0.0, case["sigma"], size=rows[:, FINGERS].shape)
    rows = np.clip(rows, lo, hi)
    start = time.time()
    status = session.replay(rows)
    features = session.features()
    session.close()
    return {**case, "success": status["success"], "reason": status["reason"], "steps": status["steps"],
            "in_pan": status["in_pan"], "grip_by_tool": features["grip_by_tool"],
            "min_contacts": features["min_contacts"], "max_terminal_run": features["max_terminal_run"],
            "seconds": round(time.time() - start, 1)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--sigmas", default="1e-6,1e-4,1e-3")
    parser.add_argument("--grip-offset", type=float, default=0.0)
    parser.add_argument("--side", default="r", choices=["l", "r", "both"])
    parser.add_argument("--no-base", action="store_true")
    parser.add_argument("--extra-hold", type=int, default=0, help="append this many more copies of the last row")
    args = parser.parse_args()
    common = {"grip_offset": args.grip_offset, "side": args.side, "extra_hold": args.extra_hold}
    cases = [] if args.no_base else [{"name": "base", "kind": "base", **common}]
    cases.append({"name": "float32", "kind": "float32", **common})
    for sigma in [float(x) for x in args.sigmas.split(",") if x]:
        for seed in range(args.seeds):
            cases.append({"name": f"noise{sigma:g}_s{seed}", "kind": "noise", "sigma": sigma, "seed": seed, **common})
    with Pool(args.workers) as pool:
        results = pool.map(run, cases, chunksize=1)
    summary = {}
    for r in results:
        key = r["kind"] if r["kind"] != "noise" else f"noise {r['sigma']:g}"
        entry = summary.setdefault(key, {"runs": 0, "success": 0, "reasons": {}})
        entry["runs"] += 1
        entry["success"] += int(r["success"])
        entry["reasons"][r["reason"] or "no success"] = entry["reasons"].get(r["reason"] or "no success", 0) + 1
    args.out.write_text(json.dumps({"grip_offset": args.grip_offset, "side": args.side,
                                    "extra_hold": args.extra_hold, "summary": summary,
                                    "runs": results}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
