import math

TASKS = {
    "catch_varied": "Catch incoming balls across front, left and right directions, low/middle/high launch heights and variable crossing heights",
    "catch_throw": "Catch and retain a ball thrown from the front, left or right with randomized launch velocity and timing",
    "reach": "Reach and settle at a visible Cartesian target",
    "pick_place": "Grasp a ball from a pedestal and release it on a second pedestal",
    "catch": "Intercept a falling ball and retain it in the original parallel gripper",
}
BOUNDS = {
    "kp_scale": (0.5, 2.0),
    "kd_scale": (0.5, 2.0),
    "speed": (0.1, 1.0),
    "ik_gain": (0.1, 1.0),
    "filter_alpha": (0.05, 1.0),
    "catch_lead": (0.0, 0.2),
    "close_delay": (-0.12, 0.15),
    "grip_open": (0.02, 0.041),
}
BASELINE = {
    "kp_scale": 1.0,
    "kd_scale": 1.0,
    "speed": 0.4,
    "ik_gain": 0.6,
    "filter_alpha": 0.3,
    "catch_lead": 0.04,
    "close_delay": 0.0,
    "grip_open": 0.038,
}
CHANNELS = [f"joint{i}" for i in range(1, 7)] + [
    "left_finger",
    "right_finger",
    "vision_ball_x",
    "vision_ball_y",
    "vision_ball_z",
]


def validate(c):
    if not isinstance(c, dict) or set(c) != set(BOUNDS):
        raise ValueError("Supply exactly the advertised configuration fields")
    for k, (lo, hi) in BOUNDS.items():
        x = c[k]
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
            raise ValueError("Invalid " + k)
    return dict(c)


def describe(task, remaining=6):
    return {
        "suite": "YAM Manipulation Bench",
        "version": 3 if task == "catch_varied" else 2 if task == "catch_throw" else 1,
        "task": task,
        "objective": TASKS[task],
        "robot": "I2RT YAM: six arm joints and coupled parallel fingers",
        "duration_s": 8,
        "remaining_trials": remaining,
        "baseline": BASELINE,
        "bounds": BOUNDS,
        "channels": CHANNELS,
        "units": ["rad"] * 6 + ["m"] * 5,
        "feedback": "RGB video samples and noisy joint/vision-position measurements only; no scores, contacts, velocities, dynamics, seeds or simulator paths",
        "vision": "Synthetic noisy 3D ball detector, not a learned camera detector.",
        "controller": "Fixed nominal-model damped-least-squares IK and position servos with nominal gravity feedforward; agent tunes bounded parameters, not arbitrary code",
        "case_counts": {"development": 9, "held_out": 27}
        if task == "catch_varied"
        else {"development": 3, "held_out": 20},
        "catch": (
            "Nine direction × launch-height strata; crossing height varies independently from 0.35–0.48 m. Launch state is hidden; estimate the crossing point from noisy measurements."
            if task == "catch_varied"
            else "Ball thrown from front/left/right at a randomized 0.8–1.5 s release time. Launch state is hidden; infer motion from noisy measurements."
            if task == "catch_throw"
            else "Ball released at 1.5 s."
        )
        + " Catch requires sustained physical contact with both fingers while elevated and slow; proximity alone never counts.",
    }


PROMPT = "You are tuning an I2RT YAM manipulation controller. Use only describe_task, run_trial, submit. Infer failures from provided video frames and noisy measurements; do not request hidden information. Use diagnosis/summary for a concise observed failure, proposed change and expected effect, not private reasoning. At most 6 trials and 20 calls. Submit one completed trial ID."


def tools():
    obj = lambda fields: {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }
    cfg = obj({k: {"type": "number", "minimum": lo, "maximum": hi} for k, (lo, hi) in BOUNDS.items()})
    return [
        {"name": "describe_task", "description": "Read the task and observation contract", "parameters": obj({})},
        {
            "name": "run_trial",
            "description": "Evaluate a controller on the fixed hidden development cases specified by describe_task",
            "parameters": obj({"config": cfg, "diagnosis": {"type": "string", "maxLength": 2000}}),
        },
        {
            "name": "submit",
            "description": "Seal a completed trial for hidden grading",
            "parameters": obj({"trial_id": {"type": "string"}, "summary": {"type": "string", "maxLength": 2000}}),
        },
    ]
