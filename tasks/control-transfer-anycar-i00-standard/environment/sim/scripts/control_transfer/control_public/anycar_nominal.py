"""Editable nominal training rollout. No deployment draws, case bank or private imports."""

import argparse
import json
from pathlib import Path
import numpy as np
from .anycar import Controller, DEFAULT, DT, HORIZON, reference, validate
from ..components.anycarbench.model import Vehicle, NOMINAL


def train_rollout(policy, command=None, plant=None, surfaces=None):
    """Agent may change the nominal plant here; exported evaluator artifact is still numeric JSON."""
    validate(policy)
    command = command or dict(a=4.5, b=3.5, phase=0.0, direction=1)
    vehicle = Vehicle(plant or NOMINAL, surfaces or [(-12, 0, 0.8), (0, 12, 0.8)], command)
    start = reference(0, command)
    vehicle.reset(*start[:3])
    controller = Controller(policy)
    trajectory = []
    for i in range(round(HORIZON / DT) + 1):
        t = i * DT
        state = vehicle.state()
        target = reference(t, command)
        action = controller.step(state, reference(min(t + policy["preview"], HORIZON), command))
        trajectory.append([t, *state, *target, *action])
        if i < round(HORIZON / DT):
            vehicle.advance(action)
    return np.asarray(trajectory)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    policy = json.loads(a.policy.read_text()) if a.policy else DEFAULT
    a.out.mkdir(parents=True, exist_ok=False)
    values = train_rollout(policy)
    np.savez(a.out / "nominal.npz", trajectory=values)
    (a.out / "policy.json").write_bytes(validate(policy))
    print(
        json.dumps(
            {
                "nominal_tracking_rmse_m": float(
                    np.sqrt(np.mean(np.sum((values[:, 1:3] - values[:, 12:14]) ** 2, axis=1)))
                )
            }
        )
    )


if __name__ == "__main__":
    main()
