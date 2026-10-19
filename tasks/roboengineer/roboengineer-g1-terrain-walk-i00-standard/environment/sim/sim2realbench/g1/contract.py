import math

JOINT_NAMES = (
    [
        f"{side}_{part}_joint"
        for side in ["left", "right"]
        for part in ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
    ]
    + [f"waist_{axis}_joint" for axis in ["yaw", "roll", "pitch"]]
    + [
        f"{side}_{part}_joint"
        for side in ["left", "right"]
        for part in [
            "shoulder_pitch",
            "shoulder_roll",
            "shoulder_yaw",
            "elbow",
            "wrist_roll",
            "wrist_pitch",
            "wrist_yaw",
        ]
    ]
)
BOUNDS = {
    "learning_rate": (0.00003, 0.003),
    "entropy_coef": (0.0, 0.03),
    "friction_low": (0.1, 1.0),
    "friction_high": (1.0, 2.0),
    "encoder_bias": (0.0, 0.04),
    "com_offset": (0.0, 0.08),
    "action_rate_weight": (-0.2, 0.0),
}
BASELINE = {
    "learning_rate": 0.001,
    "entropy_coef": 0.01,
    "friction_low": 0.3,
    "friction_high": 1.6,
    "encoder_bias": 0.015,
    "com_offset": 0.05,
    "action_rate_weight": -0.05,
}


def validate(c):
    if not isinstance(c, dict) or set(c) != set(BOUNDS):
        raise ValueError("Supply exactly the documented training settings")
    for k, (lo, hi) in BOUNDS.items():
        v = c[k]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("Invalid setting: " + k)
    if c["friction_low"] > c["friction_high"]:
        raise ValueError("Invalid friction range")
    return dict(c)


def describe(iterations=10000, num_envs=256, remaining=3):
    """Public description only. Shared eai-policy service owns admission and final grading."""
    return {
        "task": "unitree_g1_terrain_transfer_v1",
        "robot": "Unitree G1 29 DoF",
        "training": "blind-terrain mjlab 1.2.0 / MuJoCo-Warp 3.5.0 / PPO",
        "deployment": "native MuJoCo 3.5.0 CPU + NumPy CPU + OSMesa",
        "goal": "Stand 2 s, then walk 18 s at the public command over flat, slope, rough or stepped terrain",
        "policy_inputs": "98 values: noisy angular velocity, projected gravity, command, gait phase, relative joints, joint velocities, previous actions; no terrain scan",
        "policy_outputs": "29 joint position offsets through the fixed actuator ABI",
        "agent_feedback": "Noisy 29-joint angles at 10 Hz, public velocity commands and sampled video; no IMU, scores, hidden parameters or true state",
        "channels": JOINT_NAMES,
        "joint_units": "rad",
        "bounds": BOUNDS,
        "baseline": BASELINE,
        "iterations_per_trial": iterations,
        "num_envs": num_envs,
        "rollout_steps_per_env": 24,
        "policy_steps_per_trial": iterations * num_envs * 24,
        "remaining_trials": remaining,
        "adaptation_cases": 4,
        "held_out_cases": 12,
        "plants_per_instance": 1,
        "score": "100 * walking survival fraction * exp(-speed MAE / commanded speed) * clipped forward-progress fraction",
        "success": "Full survival, speed MAE <0.25 m/s, forward displacement >65% of commanded walking distance, absolute lateral displacement <2 m",
        "limitations": [
            "sim-to-sim, not hardware",
            "short training is not convergence",
            "native Harbor isolation validation is separate from local rollouts",
        ],
    }
