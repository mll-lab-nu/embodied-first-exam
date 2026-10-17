"""Authoring search (not shipped): CEM over the right-hand pinch parameters, scored by crank progress."""

from __future__ import annotations

import json
import math
from multiprocessing import Pool
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

NAMES = ["dx", "dy", "dz", "t_cmc", "t_aa", "t_mcp", "t_ip", "f_mcp", "f_pip"]
MEAN = np.array([0.10, 0.025, -0.093, 1.2, 0.0, 0.4, 0.0, 1.1, 0.7])
STD = np.array([0.012, 0.012, 0.008, 0.25, 0.2, 0.3, 0.4, 0.25, 0.3])
LO = np.array([0.06, -0.02, -0.12, 0.3, -0.35, -0.5, 0.0, 0.3, 0.0])
HI = np.array([0.14, 0.07, -0.07, 1.9, 0.35, 1.39, 1.7, 1.57, 1.7])


def params(x):
    dx, dy, dz, tc, ta, tm, ti, fm, fp = x
    return dict(
        r_knob_offset=(dx, dy, dz),
        r_thumb=dict(thumb_CMC_FE=tc, thumb_CMC_AA=ta, thumb_MCP_FE=tm, thumb_IP=ti),
        r_close=dict(index_MCP_FE=fm, index_PIP=fp, index_DIP=0.6 * fp, middle_MCP_FE=fm, middle_PIP=fp,
                     middle_DIP=0.6 * fp),
        crank_max_steps=150,
        search_only=True,
    )


def evaluate(x):
    from author import Author

    a = Author("sharpa", **params(x))
    st = a.run(verbose=False)
    score = st["net_clockwise_deg"]
    if st["failure"]:
        score -= 1000
    return float(score), st["reason"], st["hand_contacts"]["right"]


def main():
    rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    mean, std = MEAN.copy(), STD.copy()
    best = (-1e9, None)
    with Pool(2) as pool:
        for gen in range(int(sys.argv[2]) if len(sys.argv) > 2 else 8):
            xs = np.clip(mean + std * rng.standard_normal((16, len(mean))), LO, HI)
            if gen == 0:
                xs[0] = MEAN
            res = pool.map(evaluate, list(xs))
            scores = np.array([r[0] for r in res])
            order = np.argsort(-scores)
            elite = xs[order[:4]]
            mean = elite.mean(0)
            std = np.maximum(elite.std(0), STD * 0.15)
            if scores[order[0]] > best[0]:
                best = (float(scores[order[0]]), xs[order[0]].tolist())
            print(gen, "best", round(best[0], 1), "gen top", [(round(scores[i], 1), res[i][1], res[i][2]) for i in order[:4]],
                  flush=True)
            print("   best x", dict(zip(NAMES, np.round(best[1], 4))), flush=True)
    Path("pinch_best.json").write_text(json.dumps({"score": best[0], "x": best[1], "names": NAMES}))


if __name__ == "__main__":
    main()
