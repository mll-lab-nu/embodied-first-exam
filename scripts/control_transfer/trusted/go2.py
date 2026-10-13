"""Operator-only Go2 family definitions and adapter; do not copy to the agent image."""

from pathlib import Path
import json

from ..control_public.go2_data import validate as validate
from .go2_spec import TASKS as TASKS, make_spec as make_spec


def rollout(policy_path, case, out, render=True):
    from ..components.quadrupedbench.simulation import rollout as run

    with Path(policy_path).open("rb") as artifact:
        raw = artifact.read(65537)
    if len(raw) > 65536:
        raise ValueError("Policy size limit")
    policy = json.loads(raw)
    validate(policy)
    return run(policy, case, out, render)
