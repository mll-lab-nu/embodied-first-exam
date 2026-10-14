"""Regenerate the successful Wuji Hand 2.2 assemble_hamburger trajectory (motor targets only).

Runs the per-layer controller of wuji_layers.py sequentially with the parameters the greedy search accepted
(no search, no fork): Wuji pinch IK (wrist stage + thumb + index joints), side pinch between the thumb and index
fingertips, lift, carry over the plate, lower, open, withdraw. Only actuator target rows are produced; no object
pose, weld or force is ever written. Output: trajectory.npz (actions + hand + task, via Session.save_trajectory).

Usage (pinned MuJoCo 3.4.0 env, or inside ghcr.io/mll-lab-nu/eai-dexhand:0.2.0), with the task's runtime importable
(a generated task's environment/ folder, or this family folder plus scripts/dexhand/shared):
    PYTHONPATH=<task>/environment python wuji_gen.py --out trajectory.npz
The result is byte-identical to ../solution/wuji/trajectory.npz (sha256 1e30c0db...); the authoring search itself
(`wuji_layers.py --plan`) is not needed to regenerate it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wuji_demo as wd  # noqa: E402
import wuji_layers as wl  # noqa: E402

ACCEPTED = {
    "patty": {"place_gap": 0.006, "open_n": 150, "open_frac": 1.0},
    "cheese": {"transport": 300, "lift": 0.16, "close_clear": -0.01, "grasp_z": 0.0},
    "tomato": {"place_gap": 0.012, "open_n": 90, "close_clear": -0.004, "transport": 300},
    "lettuce": {"transport": 300, "lift": 0.1, "close_clear": -0.01, "grasp_z": 0.0},
    "top_bun": {"place_gap": 0.012, "open_n": 90, "close_clear": -0.004, "transport": 160},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/app/output/trajectory.npz")
    args = parser.parse_args()
    demo = wd.Demo(wd.default_params())
    s = demo.session
    base = s.hold_action()
    curled = base.copy()
    curled[6:10] = demo.p["thumb_seed"]
    curled[10:14] = demo.p["index_seed"]
    for k in (14, 18, 22):
        curled[k:k + 4] = demo.p["curl"]
    demo.execute(base, 10, "settle ingredients")
    demo.execute(curled, 40, "shape hand")
    ctrl = {"previous_opened": None, "previous_center": None, "previous_direction": 1}
    for layer, name in enumerate(s.names[1:], 1):
        ctrl, status = wl.layer_routine(demo, layer, name, {**wl.BASE, **ACCEPTED[name]}, ctrl)
        print(f">> {name}: {status} steps={s.steps} score={wl.score(s, layer)[0]:.2f}", flush=True)
        if status != "ok" or s.failure:
            break
    if not s.done:
        demo.execute(demo.joint_target, 400, "stability check")
    actions = np.asarray(s.actions, dtype=np.float64)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    s.save_trajectory(actions, out)
    st = s.status()
    print(json.dumps({"success": st["success"], "reason": st["reason"], "steps": st["steps"], "rows": len(actions),
                      "state_sha": s.state_sha(),
                      "rows_sha256": hashlib.sha256(np.ascontiguousarray(actions, "<f8").tobytes()).hexdigest()}))


if __name__ == "__main__":
    main()
