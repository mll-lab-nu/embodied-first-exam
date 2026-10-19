"""Editable nominal drift training. No trusted imports or hidden banks."""

import argparse
import json
from pathlib import Path

import numpy as np
from scripts.control_transfer.components.anycarbench.model import Diverged

from scripts.control_transfer.components.anycarbench.drift_v3 import (
    DEFAULT_COURSE,
    DriftVehicle,
)

from .anycar_drift_v3 import DT, HORIZON, Controller, validate
from .anycar_drift_feedback import DEFAULT


def train_rollout(policy, course=None):
    c = dict(DEFAULT_COURSE if course is None else course)
    v = DriftVehicle(c)
    v.reset(c.get("start_x", -3.0), -c["radius"], 0)
    controller = Controller(policy, c)
    rows = []
    for i in range(round(HORIZON / DT) + 1):
        obs = v.state()
        action = controller.step(obs)
        rows.append([i * DT, *obs, *action])
        if i < round(HORIZON / DT):
            try:
                v.advance(action)
            except Diverged:   # the simulation diverged: the rollout ends at the last finite state
                break
    return np.asarray(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--policy", type=Path)
    a = p.parse_args()
    policy = json.loads(a.policy.read_text()) if a.policy else DEFAULT
    a.out.mkdir(parents=True, exist_ok=False)
    np.savez(a.out / "nominal.npz", trajectory=train_rollout(policy))
    (a.out / "policy.json").write_bytes(validate(policy))


if __name__ == "__main__":
    main()
