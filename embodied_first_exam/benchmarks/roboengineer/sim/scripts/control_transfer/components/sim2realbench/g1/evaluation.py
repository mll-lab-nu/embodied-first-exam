"""Trusted G1 integration hook. The service owns admission, round limits, sealing and feedback filtering."""

from control_public.g1 import validate
from .deploy import rollout as run
from .terrain import make_spec


def rollout(policy_path, case, out, render):
    allowed = {"plant_seed", "episode_seed", "terrain", "duration", "speed"}
    if not isinstance(case, dict) or set(case) != allowed:
        raise ValueError("Invalid trusted G1 case")
    return run(policy_path, out=out, render=render, **case)


__all__ = ["make_spec", "rollout", "validate"]
