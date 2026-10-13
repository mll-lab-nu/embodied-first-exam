"""Public controller contract, with no realized dynamics or evaluation seeds."""

import math

BOUNDS = {
    "position_gain": (0.01, 2.0),
    "velocity_gain": (0.05, 4.0),
    "attitude_gain": (0.01, 2.0),
    "angular_gain": (0.01, 2.0),
    "max_speed": (0.02, 0.4),
    "estimated_mass": (5.0, 20.0),
    "estimated_inertia": (0.1, 2.0),
    "filter_tau": (0.0, 1.0),
}
BASELINE = {
    "family": "geometric_pd",
    "position_gain": 0.3,
    "velocity_gain": 0.2,
    "attitude_gain": 0.4,
    "angular_gain": 0.1,
    "max_speed": 0.2,
    "estimated_mass": 10.0,
    "estimated_inertia": 0.6,
    "filter_tau": 0.1,
    "approach_gate": False,
}
REFERENCE = {
    **BASELINE,
    "family": "velocity_shaping",
    "position_gain": 0.25,
    "velocity_gain": 1.1,
    "attitude_gain": 0.8,
    "angular_gain": 1.3,
    "max_speed": 0.15,
    "filter_tau": 0.25,
    "approach_gate": True,
}
CHANNELS = ["x", "y", "z", "vx", "vy", "vz", "qw", "qx", "qy", "qz", "wx", "wy", "wz"]
UNITS = ["m"] * 3 + ["m/s"] * 3 + ["unit quaternion"] * 4 + ["rad/s"] * 3
PROMPT = """Tune the spacecraft rendezvous controller using only describe_task, run_trial, and submit.
Use noisy telemetry and chronological external-camera frames to diagnose failures. Models and
realized dynamics are hidden. Do not request filesystem, execution, network, seeds, true state,
or evaluator metrics. System identification using permitted observations is allowed. This is
bounded configuration of nonlinear feedback controllers, not arbitrary code execution. Read
all parameter bounds with describe_task. Submit a configuration within 12 trials and 30 minutes.
Frames cover the episode at 10-second intervals; full videos are retained for operator review."""


def validate(config):
    if not isinstance(config, dict) or set(config) != set(BASELINE):
        raise ValueError("Provide exactly the public controller fields")
    if config["family"] not in ("geometric_pd", "velocity_shaping"):
        raise ValueError("Unknown controller family")
    if type(config["approach_gate"]) is not bool:
        raise ValueError("approach_gate must be boolean")
    for k, (lo, hi) in BOUNDS.items():
        x = config[k]
        if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
            raise ValueError(f"{k} must be in [{lo},{hi}]")
    return dict(config)


def describe(remaining=12):
    return {
        "suite": "Robotic Engineering Bench",
        "benchmark": "Nonlinear Control Bench",
        "task": "rendezvous_docking_v1",
        "goal": "Approach the fixed target station and hold chaser center at [0.65,0,0] m with identity attitude. Avoid all target geometry.",
        "frame": "Rotating local orbital frame: x radial, y along-track, z orbit-normal. Quaternion wxyz rotates body into this frame; angular velocity is body-relative to this frame.",
        "horizon_s": 120,
        "control_dt_s": 0.1,
        "physics_dt_s": 0.02,
        "telemetry_dt_s": 0.5,
        "video_fps": 5,
        "video_size": [320, 240],
        "capture_tolerance": {
            "position_m": 0.08,
            "speed_m_s": 0.025,
            "attitude_rad": 0.07,
            "angular_rate_rad_s": 0.025,
            "final_dwell_s": 3,
        },
        "nominal_model": {
            "mass_kg": 10,
            "inertia_kg_m2": [0.55, 0.65, 0.5],
            "orbit_radius_m": 6971100,
            "mu_m3_s2": 3.986004418e14,
            "force_limit_N_per_axis": 0.4,
            "torque_limit_Nm_per_axis": 0.08,
        },
        "channels": CHANNELS,
        "units": UNITS,
        "remaining_trials": remaining,
        "baseline": BASELINE,
        "bounds": BOUNDS,
        "families": {
            "geometric_pd": "World acceleration = position_gain*(goal-position) - velocity_gain*velocity; estimated-mass feedforward cancels nominal orbital acceleration. Quaternion-log attitude PD.",
            "velocity_shaping": "Desired velocity = -max_speed*tanh(position_gain*(position-goal)/max_speed); velocity feedback produces acceleration, with nominal orbital feedforward and quaternion-log attitude PD.",
        },
        "approach_gate": "Hold radial position at least 1.5 m while lateral error >0.12 m or attitude error >0.08 rad. Below 1.5 m, limit desired speed to 0.04 m/s.",
        "noise": "Persistent Gaussian position, velocity, attitude and angular-rate noise plus per-episode biases. No perfect-state region near the goal.",
        "limitations": [
            "Simplified rigid spacecraft and station geometry",
            "Capture tolerance only; no latch or soft-capture mechanism",
            "Continuous body wrench; no discrete thruster allocation or fuel mass depletion",
            "External illustrative camera, not an onboard optical navigation sensor",
            "Restricted-tool track, not an OS sandbox for arbitrary code",
        ],
    }


def tools():
    fields = {k: {"type": "number", "minimum": a, "maximum": b} for k, (a, b) in BOUNDS.items()}
    fields.update(
        family={"type": "string", "enum": ["geometric_pd", "velocity_shaping"]}, approach_gate={"type": "boolean"}
    )
    config = {"type": "object", "properties": fields, "required": list(BASELINE), "additionalProperties": False}
    return [
        {
            "type": "function",
            "name": name,
            "description": desc,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {} if name == "describe_task" else {"config": config},
                "required": [] if name == "describe_task" else ["config"],
                "additionalProperties": False,
            },
        }
        for name, desc in [
            ("describe_task", "Read the public task and bounds."),
            ("run_trial", "Evaluate configuration; receive noisy telemetry and sampled video frames only."),
            ("submit", "Seal final controller configuration."),
        ]
    ]
