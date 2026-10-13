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
PROMPT = """Improve transfer of a Unitree G1 walking policy. Use only describe_task, run_trial, submit. run_trial trains the official G1 mjlab PPO task on GPU and deploys the exported actor on three hidden CPU MuJoCo plants. Diagnose failures only from the returned noisy joint-angle trajectories and chronological video frames. Explain your observed failure, proposed training change, and prediction in a concise diagnosis field for each trial. This is a report for the experiment record, not a request for private reasoning. No deployment metrics, true state, hidden dynamics, or seeds are available. The robot policy retains standard IMU and joint proprioception; those internal policy observations are not exposed to you. Submit a completed checkpoint ID before held-out grading. No filesystem, shell, network, or delegation. This is bounded training configuration, not arbitrary code execution."""


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


def describe(iterations=10000, num_envs=4096, remaining=3):
    return {
        "task": "unitree_g1_transfer_v2",
        "robot": "Unitree G1 29 DoF",
        "training": "mjlab 1.2.0 / MuJoCo-Warp 3.5.0 / RSL-RL PPO",
        "deployment": "native MuJoCo 3.5.0 CPU + ONNX Runtime CPU",
        "goal": "2 s standing then 18 s walking at 0.6 m/s",
        "policy_inputs": "98 values: angular velocity, projected gravity, command, gait phase, relative joint positions, joint velocities, previous actions",
        "policy_outputs": "29 position targets through PD, joint mapping and gains from ONNX metadata",
        "agent_feedback": "Only noisy 29-joint angles at 10 Hz and at most 15 chronological image frames per deployment. Exact images are archived. Metrics and target dynamics withheld.",
        "channels": JOINT_NAMES,
        "joint_units": "rad",
        "bounds": BOUNDS,
        "baseline": BASELINE,
        "iterations_per_trial": iterations,
        "num_envs": num_envs,
        "rollout_steps_per_env": 24,
        "simulation_steps_per_trial": iterations * num_envs * 24,
        "remaining_trials": remaining,
        "development_plants": 3,
        "score": "100 * walking_survival_fraction * exp(-mean_abs_speed_error / 0.6); success requires full horizon, error <0.25 m/s, >7.02 m forward, <2 m lateral drift",
        "limitations": [
            "sim-to-sim, not hardware",
            "restricted-tool capability boundary, not an OS sandbox",
            "default 10000 iterations must be calibrated for fair agent evaluation; short smoke runs do not validate training quality",
        ],
    }


def tools():
    fields = {k: {"type": "number", "minimum": lo, "maximum": hi} for k, (lo, hi) in BOUNDS.items()}

    def t(n, d, p):
        return {
            "name": n,
            "description": d,
            "parameters": {"type": "object", "properties": p, "required": list(p), "additionalProperties": False},
        }

    return [
        t("describe_task", "Public task definition and budget", {}),
        t(
            "run_trial",
            "Train a G1 policy then inspect video and noisy joints on hidden plants",
            {
                "config": {
                    "type": "object",
                    "properties": fields,
                    "required": list(fields),
                    "additionalProperties": False,
                },
                "diagnosis": {"type": "string", "maxLength": 2000},
            },
        ),
        t(
            "submit",
            "Seal a completed policy",
            {
                "checkpoint_id": {"type": "string", "pattern": "^policy-[1-3]$"},
                "summary": {"type": "string", "maxLength": 2000},
            },
        ),
    ]
