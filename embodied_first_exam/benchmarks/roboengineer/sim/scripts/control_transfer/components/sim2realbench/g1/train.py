"""Compatibility entry point for the public blind-terrain PPO trainer. No evaluator imports."""

import argparse
import json
from pathlib import Path

from .assets import UPSTREAM, verify
from .contract import BASELINE, validate


def train(config, out, seed=0, gpu=0, iterations=10000, num_envs=256, checkpoint=None, initial_actor=None):
    verify()
    from control_public.g1_training import train as run

    return run(
        UPSTREAM,
        out,
        seed=seed,
        gpu=gpu,
        iterations=iterations,
        num_envs=num_envs,
        checkpoint=checkpoint,
        initial_actor=initial_actor,
        settings=validate(config),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--num-envs", type=int, default=256)
    parser.add_argument("--checkpoint")
    parser.add_argument("--initial-actor")
    a = parser.parse_args()
    train(
        json.loads(a.config.read_text()) if a.config else BASELINE,
        a.out,
        a.seed,
        a.gpu,
        a.iterations,
        a.num_envs,
        a.checkpoint,
        a.initial_actor,
    )
