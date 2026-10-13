"""Operator-owned frozen development banks. Never copy this module into the agent image."""

import copy

from .control_public.fly import BOUNDS, DEFAULT


def make_spec(index):
    if type(index) is not int or not 0 <= index < 1000:
        raise ValueError("Instance index")
    base = 10000 + index * 1000
    plant = base + 100

    def bank(held):
        return [
            {"plant_seed": plant, "episode_seed": base + (300 if held else 0) + i, "stratum": i % 5}
            for i in range(10 if held else 5)
        ]

    return {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "family": "neural-fly",
        "name": "neural-fly",
        "index": index,
        "public": {
            "schema": "control-transfer/1",
            "protocol": "eai-policy/1.1",
            "name": "neural-fly",
            "goal": "Track six timed vertical figure-eight laps: x=1.25 sin(t), y=0, z=1.8+0.75 sin(2t), with randomized phase, horizontal center and initial position offset.",
            "score": "Crash or escape: 0. Otherwise 100 exp(-max(0,RMSE_m-0.03)/0.25). Success requires the full horizon and RMSE<0.25 m; acquisition is included.",
            "max_rounds": 3,
            "adaptation_cases": 5,
            "held_out_cases": 10,
            "training_backend": "nominal MuJoCo CPU",
            "evaluation_backend": "native MuJoCo CPU / NumPy CPU / OSMesa",
            "policy_abi": "bounded JSON controller coefficients; optional observer_gain in [0,15], default 0",
            "default_policy": copy.deepcopy(DEFAULT),
            "bounds": copy.deepcopy(BOUNDS),
            "feedback": "Noisy telemetry and sampled images only; no scores, contacts, hidden parameters, true state or seeds.",
            "channels": {
                "position": "world m",
                "velocity": "world m/s",
                "quaternion": "wxyz body-to-world",
                "omega": "body rad/s",
                "target_position": "world m",
                "target_velocity": "world m/s",
                "target_acceleration": "world m/s²",
            },
            "telemetry_interval_s": 0.1,
            "image_interval_s": 1.0,
            "limitations": "Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not DAIML or PX4. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight limit.",
        },
        "bank": {"adaptation": bank(False), "held_out": bank(True)},
    }
