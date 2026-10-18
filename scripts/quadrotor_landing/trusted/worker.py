"""Fresh-process evaluator worker, never installed in the agent container."""

import argparse
from pathlib import Path
from ..public.policy import load
from .simulation import rollout

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--scale", type=float, required=True)
    p.add_argument("--render", action="store_true")
    p.add_argument("--oracle", action="store_true", help="Operator-only exact-state calibration replay")
    p.add_argument("--reference-time", type=float)
    a = p.parse_args()
    rollout(
        load(a.policy),
        residual_path=a.residual,
        seed=a.seed,
        scale=a.scale,
        out=a.out,
        render=a.render,
        oracle=a.oracle,
        reference_time_s=a.reference_time,
    )
