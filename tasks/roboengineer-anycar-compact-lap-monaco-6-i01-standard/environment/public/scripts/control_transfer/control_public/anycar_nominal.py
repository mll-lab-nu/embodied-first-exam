"""Editable nominal training rollout. No deployment draws, case bank or private imports."""

import argparse
import json
from pathlib import Path
import numpy as np
from .anycar import Controller, DEFAULT, DT, HORIZON, reference, validate

if __package__ == "control_public":
    # The agent image duplicates public modules at /app/control_public; components
    # remain exclusively in the namespaced public package.
    from scripts.control_transfer.components.anycarbench.model import Diverged, Vehicle, NOMINAL
else:
    from ..components.anycarbench.model import Diverged, Vehicle, NOMINAL


def train_rollout(policy, command=None, plant=None, surfaces=None, horizon=HORIZON):
    """Agent may change the nominal plant here; exported evaluator artifact is still numeric JSON."""
    validate(policy)
    command = command or dict(a=4.5, b=3.5, phase=0.0, direction=1)
    if "track_id" in command and surfaces is None:
        from scripts.control_transfer.components.anycarbench.tracks import get_route

        extent = get_route(command["track_id"], command.get("route_revision", "circuit-sector/1")).half_extent
        surfaces = [(-extent, 0, 0.8), (0, extent, 0.8)]
    vehicle = Vehicle(plant or NOMINAL, surfaces or [(-12, 0, 0.8), (0, 12, 0.8)], command)
    start = reference(0, command)
    vehicle.reset(*start[:3])
    controller = Controller(policy)
    trajectory = []
    for i in range(round(horizon / DT) + 1):
        t = i * DT
        state = vehicle.state()
        target = reference(t, command)
        action = controller.step(state, reference(min(t + policy["preview"], horizon), command))
        trajectory.append([t, *state, *target, *action])
        if i < round(horizon / DT):
            try:
                vehicle.advance(action)
            except Diverged:   # the simulation diverged: the rollout ends at the last finite state
                break
    return np.asarray(trajectory)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--track", help="Historical layout ID, circuit alias, or zigzag")
    p.add_argument(
        "--full-lap", action="store_true", help="Nominal full-lap training for the circuit-lap benchmark"
    )
    p.add_argument("--compact-30s", action="store_true")
    p.add_argument("--list-tracks", action="store_true")
    a = p.parse_args()
    from scripts.control_transfer.components.anycarbench.tracks import get_route, track_ids

    if a.list_tracks:
        print(json.dumps(track_ids()))
        return
    if a.out is None or ((a.full_lap or a.compact_30s) and not a.track):
        p.error("--out is required for rollouts; --full-lap requires --track")
    command = dict(track_id=a.track, start_fraction=0.0, speed=0.85) if a.track else None
    horizon = get_route(a.track).length / 0.85 + 0.5 if a.full_lap else HORIZON
    if a.compact_30s:
        route = get_route(a.track, "compact-30s/1")
        command.update(route_revision="compact-30s/1", speed=route.length / 27.5)
        horizon = 30.0
    policy = json.loads(a.policy.read_text()) if a.policy else DEFAULT
    a.out.mkdir(parents=True, exist_ok=False)
    values = train_rollout(policy, command=command, horizon=horizon)
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
