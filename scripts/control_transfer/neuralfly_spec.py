"""Operator-owned frozen development banks. Never copy this module into the agent image."""

import copy

from .neuralfly_constants import BOUNDS, DEFAULT


def make_spec(index, revision="fixed-eight/1"):
    if revision not in ("fixed-eight/1", "general-eight/1", "general-eight-wind/1"):
        raise ValueError("Trajectory revision")
    if type(index) is not int or not 0 <= index < 1000:
        raise ValueError("Instance index")
    base = 10000 + index * 1000
    plant = base + 100

    def bank(held):
        return [
            {"plant_seed": plant, "episode_seed": base + (300 if held else 0) + i, "stratum": i % 5}
            for i in range(10 if held else 5)
        ]

    result = {
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
            "limitations": "Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not a learned aerodynamics model or flight-stack simulation. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight limit.",
        },
        "bank": {"adaptation": bank(False), "held_out": bank(True)},
    }

    if revision in ("general-eight/1", "general-eight-wind/1"):
        result.update(name="neural-fly-general-v1", task_revision=revision)
        result["public"].update(
            name="neural-fly-general-v1",
            goal="Track six timed laps of a randomized figure eight: vertical, horizontal or inclined plane; yaw in [-pi,pi]; both traversal directions; half extents 0.9-1.5 m and 0.45-0.85 m; angular rate 0.8-1.1 rad/s; randomized phase, center and initial offset. Follow the provided world-frame position, velocity and acceleration commands.",
        )
        for cases in result["bank"].values():
            for case in cases:
                case["trajectory_revision"] = "general-eight/1"
    if revision == "general-eight-wind/1":
        result["name"] = result["public"]["name"] = "neural-fly-vector-wind-v1"
        result["public"]["limitations"] += (
            " Synthetic world-frame vector wind with isotropic quadratic drag increment (0.045 kg/m); not calibrated directional aerodynamics. Per-axis residual force cap remains 12 N."
        )
        for cases in result["bank"].values():
            for case in cases:
                case["dynamics_revision"] = "vector-wind/1"
    return result
