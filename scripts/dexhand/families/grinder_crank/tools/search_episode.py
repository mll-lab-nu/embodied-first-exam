"""Authoring search (not shipped): CEM over left-grasp / release parameters, scored on the whole episode."""

from __future__ import annotations

import json
from multiprocessing import Pool
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

NAMES = ["gx", "gy", "gz", "t_cmc", "t_ip", "f_close", "rp_close", "lead", "rate"]
MEAN = np.array([0.557, 0.053, 0.795, 1.15, 1.7, 1.2, 0.5, 0.12, 2.513])
STD = np.array([0.006, 0.006, 0.008, 0.15, 0.1, 0.15, 0.2, 0.04, 0.4])
LO = np.array([0.53, 0.04, 0.78, 0.7, 1.2, 0.8, 0.0, 0.03, 1.5])
HI = np.array([0.58, 0.07, 0.82, 1.6, 1.74, 1.57, 1.2, 0.3, 4.0])


def params(x):
    gx, gy, gz, tc, ti, fc, rc, lead, rate = x
    return dict(
        l_grasp=(gx, gy, gz),
        l_close=dict(index_MCP_FE=fc, index_PIP=fc, index_DIP=0.8, middle_MCP_FE=fc, middle_PIP=fc, middle_DIP=0.8,
                     ring_MCP_FE=rc, ring_PIP=rc, ring_DIP=0.5, pinky_MCP_FE=rc, pinky_PIP=rc, pinky_DIP=0.5,
                     thumb_CMC_FE=tc, thumb_CMC_AA=-0.35, thumb_MCP_FE=1.4, thumb_MCP_AA=-0.35, thumb_IP=ti),
        lead=lead,
        turn_rate=2 * np.pi / rate,
    )


def evaluate(x):
    from author import Author

    a = Author("sharpa", **params(x))
    st = a.run(verbose=False)
    score = min(st["net_clockwise_deg"], 760.0) + 300 * (st["stage"] >= 1) + 3 * st["released_hold_steps"]
    score += 3000 * st["success"] - 3000 * st["slide_m"] - 20 * abs(st["body_yaw_deg"]) / 45
    return float(score), st["reason"], int(st["steps"]), round(st["slide_m"], 4), round(st["body_yaw_deg"], 1)


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    gens = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    rng = np.random.default_rng(seed)
    mean, std = MEAN.copy(), STD.copy()
    best = (-1e9, None)
    with Pool(2) as pool:
        for gen in range(gens):
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
            print(gen, "best", round(best[0], 1), "top", [(round(scores[i], 1),) + res[i][1:] for i in order[:4]], flush=True)
            print("   best x", dict(zip(NAMES, np.round(best[1], 4))), flush=True)
            Path(f"episode_best_{seed}.json").write_text(json.dumps({"score": best[0], "x": best[1], "names": NAMES}))


if __name__ == "__main__":
    main()
