#!/usr/bin/env python3
"""Authoring tool (historical): Wuji Hand 2.2 closing targets from the neutral-finger reset; all fail (see README Hands).

The declared Wuji start (assets/reset_wuji.npz, tools/build_wuji_reset.py) replaced this approach.

The Wuji reset keeps the arm/tool/debris state of the frozen scene and starts the Wuji fingers at their neutral
(zero) joint positions. Only the initial motor targets of the 40 Wuji finger actuators are chosen here: the fingers
close physically under their own position servos during the 1.2 s settling period (nothing moves the tools by
script). Each candidate is held for `--seconds` of native physics and scored on the task's own grip predicate
(force-bearing hand contacts on each shaft, grip drift/rotation, no failure).

    PYTHONPATH=<family>:<scripts/dexhand/shared> python tools/search_wuji_grip.py --out wuji-grip-search.json
"""

from __future__ import annotations

import argparse
import itertools
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np

FINGERS = ("FF", "MF", "RF", "LF")


def targets(params: dict, side: str) -> dict:
    prefix = f"{side}_wuji_{side}_"
    result = {}
    for finger in FINGERS:
        result[prefix + finger + "J0"] = params["mcp"]
        result[prefix + finger + "J1"] = 0.0
        result[prefix + finger + "J2"] = params["pip"]
        result[prefix + finger + "J3"] = params["dip"]
    for index, value in enumerate(params["thumb"]):
        result[prefix + f"THJ{index}"] = value
    return result


def evaluate(params: dict, seconds: float = 2.5) -> dict:
    from runtime import Session

    session = Session(hand="wuji", allow_unsupported_hand=True)
    names = session.actuator_names
    wanted = {**targets(params, "l"), **targets(params, "r")}
    ctrl = session.hold_action()
    for name, value in wanted.items():
        index = names.index(name)
        ctrl[index] = float(np.clip(value, *session.ctrl_range[index]))
    session.step(ctrl)
    session.hold(int(seconds / session.control_dt) - 1)
    state = session.checker.state
    result = {
        "params": params,
        "status": session.status(),
        "min_contacts": state["min_contacts"],
        "max_drift": state["max_drift"],
        "max_rotation": state["max_rotation"],
        "shaft_contacts_now": session.checker.state["last"].get("shaft_contacts"),
        "targets": {name: float(ctrl[names.index(name)]) for name in wanted},
    }
    session.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    grid = []
    for mcp, pip, dip, thumb in itertools.product(
        (0.9, 1.25, 1.55),
        (1.0, 1.6),
        (0.8, 1.3),
        ((0.6, 0.0, 0.8, 0.8), (1.1, -0.4, 1.0, 1.0), (1.2, 0.4, 1.2, 1.2), (0.3, -0.8, 0.6, 0.6)),
    ):
        grid.append({"mcp": mcp, "pip": pip, "dip": dip, "thumb": list(thumb)})
    with Pool(args.workers) as pool:
        results = pool.map(evaluate, grid)

    def score(r):
        contacts = min(v if v is not None else 0 for v in r["min_contacts"].values())
        return (not r["status"]["failed"], contacts, -r["max_drift"] - r["max_rotation"])

    results.sort(key=score, reverse=True)
    args.out.write_text(json.dumps(results, indent=1) + "\n")
    for r in results[:5]:
        print(json.dumps({k: r[k] for k in ("params", "min_contacts", "max_drift", "max_rotation")}), r["status"]["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
