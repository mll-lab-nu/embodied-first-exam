"""Authoring search (not shipped): CEM for a Wuji Hand 2.2 version of the scripted two-hand operation.

Same controller as the Sharpa oracle (tools/author.py); finger keys are aliased to Wuji actuators by tools/rig.py.
    python tools/search_wuji.py SEED GENS [init.json]
Score: crank progress, stage, released hold, success; minus slide/yaw and failure penalties.
"""

from __future__ import annotations

import json
from multiprocessing import Pool
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

NAMES = ["gx", "gy", "gz", "l_t0", "l_t1", "l_t2", "l_t3", "l_f", "l_rp",
         "dx", "dy", "dz", "r_t0", "r_t1", "r_t2", "r_t3", "r_f0", "r_f2", "lead", "rate"]
MEAN = np.array([0.55, 0.059, 0.796, 0.39, -1.24, 1.5, 0.5, 1.0, 0.5,
                 0.0914, 0.0114, -0.056, 1.25, -0.27, 0.29, -0.8, 1.57, 1.45, 0.115, 2.04])
STD = np.array([0.012, 0.008, 0.012, 0.4, 0.4, 0.4, 0.4, 0.25, 0.3,
                0.015, 0.015, 0.012, 0.4, 0.4, 0.4, 0.4, 0.3, 0.4, 0.04, 0.5])
LO = np.array([0.50, 0.03, 0.77, -1.18, -1.48, -1.04, -1.04, 0.2, 0.0,
               0.04, -0.03, -0.13, -1.18, -1.48, -1.04, -1.04, 0.0, 0.0, 0.03, 1.5])
HI = np.array([0.60, 0.08, 0.83, 1.29, 0.69, 1.57, 1.57, 1.57, 1.57,
               0.14, 0.07, -0.05, 1.29, 0.69, 1.57, 1.57, 1.57, 2.09, 0.3, 4.0])


def params(x):
    (gx, gy, gz, lt0, lt1, lt2, lt3, lf, lrp, dx, dy, dz, rt0, rt1, rt2, rt3, rf0, rf2, lead, rate) = x
    thumb_l = dict(thumb_CMC_FE=lt0, thumb_CMC_AA=lt1, thumb_MCP_FE=lt2, thumb_IP=lt3)
    return dict(
        l_grasp=(gx, gy, gz),
        l_open=dict(index_MCP_FE=0.0, middle_MCP_FE=0.0, ring_MCP_FE=0.0, pinky_MCP_FE=0.0, **thumb_l),
        l_close=dict(index_MCP_FE=lf, index_PIP=lf, index_DIP=0.8, middle_MCP_FE=lf, middle_PIP=lf, middle_DIP=0.8,
                     ring_MCP_FE=lrp, ring_PIP=lrp, ring_DIP=0.5, pinky_MCP_FE=lrp, pinky_PIP=lrp, pinky_DIP=0.5,
                     **thumb_l),
        r_open=dict(index_MCP_FE=1.57, index_PIP=2.09, index_DIP=1.2, middle_MCP_FE=1.57, middle_PIP=2.09,
                    middle_DIP=1.2, ring_MCP_FE=1.5, ring_PIP=1.6, ring_DIP=1.0, pinky_MCP_FE=1.5, pinky_PIP=1.6,
                    pinky_DIP=1.0, thumb_CMC_FE=-0.5, thumb_CMC_AA=rt1, thumb_MCP_FE=0.0, thumb_IP=0.0),
        r_thumb=dict(thumb_CMC_FE=rt0, thumb_CMC_AA=rt1, thumb_MCP_FE=rt2, thumb_IP=rt3),
        r_close=dict(index_MCP_FE=rf0, index_PIP=rf2, index_DIP=0.6 * rf2, middle_MCP_FE=rf0, middle_PIP=rf2,
                     middle_DIP=0.6 * rf2),
        r_knob_offset=(dx, dy, dz),
        lead=lead,
        turn_rate=2 * np.pi / rate,
    )


MODE = {"mode": "full"}
MASKS = {"left": slice(0, 9), "pinch": slice(9, 18), "full": slice(0, 20)}


def evaluate(x, mode="full"):
    from author import Author

    extra = {}
    if mode == "left":
        extra = dict(crank_max_steps=60, search_only=True)
    elif mode == "pinch":
        extra = dict(crank_max_steps=150, search_only=True)
    a = Author("wuji", **{**params(x), **extra})
    st = a.run(verbose=False)
    if mode == "left":
        score = 1000 * (not st["failure"]) - 3000 * st["slide_m"] - 20 * st["tilt_deg"] + 5 * min(st["hand_contacts"]["left"], 10)
        score += min(st["net_clockwise_deg"], 100)
        return float(score), st["reason"], int(st["steps"]), round(st["slide_m"], 4)
    score = min(st["net_clockwise_deg"], 760.0) + 300 * (st["stage"] >= 1) + 3 * st["released_hold_steps"]
    score += 3000 * st["success"] - 3000 * st["slide_m"] - 20 * abs(st["body_yaw_deg"]) / 45
    if st["failure"] and st["stage"] == 0 and mode == "full":
        score -= 200
    return float(score), st["reason"], int(st["steps"]), round(st["net_clockwise_deg"], 1)


def _eval(args):
    return evaluate(*args)


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    gens = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    mode = sys.argv[3] if len(sys.argv) > 3 else "full"
    mean, std = MEAN.copy(), STD.copy()
    if len(sys.argv) > 4:
        mean = np.asarray(json.loads(Path(sys.argv[4]).read_text())["x"])
    mask = np.zeros(len(mean), bool)
    mask[MASKS[mode]] = True
    std = np.where(mask, std if mode != "full" else std * 0.4, 0.0)
    rng = np.random.default_rng(seed)
    best = (-1e9, None)
    import os
    with Pool(int(os.environ.get("SEARCH_PROCS", "2"))) as pool:
        for gen in range(gens):
            xs = np.clip(mean + std * rng.standard_normal((16, len(mean))), LO, HI)
            xs[0] = np.clip(mean, LO, HI)
            res = pool.map(_eval, [(x, mode) for x in xs])
            scores = np.array([r[0] for r in res])
            order = np.argsort(-scores)
            elite = xs[order[:4]]
            mean = elite.mean(0)
            std = np.where(mask, np.maximum(elite.std(0), STD * 0.1), 0.0)
            if scores[order[0]] > best[0]:
                best = (float(scores[order[0]]), xs[order[0]].tolist())
            print(gen, mode, "best", round(best[0], 1), "top", [(round(scores[i], 1),) + res[i][1:] for i in order[:4]],
                  flush=True)
            Path(f"wuji_best_{mode}_{seed}.json").write_text(json.dumps({"score": best[0], "x": best[1], "names": NAMES}))


if __name__ == "__main__":
    main()
