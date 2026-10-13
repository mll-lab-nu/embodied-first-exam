"""Operator-owned family specification and reproducible development case banks."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC / "components"))
sys.path.insert(0, str(SRC))
# Only the current roboEngineer work packages are generated. The other prototypes
# remain available to explicit local development calls, without published tasks.
FAMILIES = ["neural-fly", "g1"]


def spec(name, index):
    family = "linearbot" if name.startswith("linearbot") else name
    base = 10000 + index * 1000
    count = {"neural-fly": 5, "linearbot": 3, "spacecraft": 3, "yam": 9, "g1": 3}[family]

    def cases(held):
        result = []
        for i in range(count * (2 if held else 1)):
            episode = base + (300 if held else 0) + i
            if family == "yam":
                episode = episode * 9 + i % 9
            c = {"plant_seed": base + 100, "episode_seed": episode}
            if family == "linearbot":
                c["mode"] = "fixed" if name.endswith("fixed") else ["coordinated", "world_lock", "height_sweep"][i % 3]
            if family == "neural-fly":
                c["stratum"] = i % 5
            result.append(c)
        return result

    goals = {
        "neural-fly": "Track six laps of x=1.25 sin(t), y=0, z=1.8+0.75 sin(2t), with randomized center and initial phase, in constant and time-varying wind.",
        "linearbot": "Track independent world-frame base x/y/yaw and both gripper 6D poses simultaneously. Initial base displacement 0.40–0.65 m; hand displacement 0.30–0.85 m. Fixed and moving classes are separate tasks.",
        "spacecraft": "Rendezvous at [0.65,0,0] m in LVLH with identity attitude. Hold position, velocity, attitude and angular-rate tolerances for 3 s without collision.",
        "yam": "Catch and retain a thrown ball with the original YAM fingers; front/left/right approaches crossed with low/middle/high launch heights. No grasp weld or teleport capture.",
        "g1": "Train a 29-DoF Unitree G1 walking policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo. Stand 2 s, walk forward at 0.6 m/s for 18 s.",
    }
    scores = {
        "neural-fly": "Crash or escape: 0. Otherwise 100 exp(-max(0,tracking_RMSE_m-0.03)/0.25); success requires full horizon and RMSE<0.25 m. Tracking uses prescribed timestamps; slowing the reference is impossible.",
        "linearbot": "100 exp(-mean(normalized_errors)); six thresholds: base xy 0.06 m, yaw 0.12 rad, each hand position 0.07 m, each orientation 0.20 rad. Success requires all six time-mean errors below threshold after a 1 s acquisition interval.",
        "spacecraft": "Collision or escape: 0. Weighted terminal pose, speed, angular rate and impulse quality; unsuccessful capture is capped at 49. Thresholds: 0.08 m, 0.025 m/s, 0.07 rad, 0.025 rad/s for final 3 s.",
        "yam": "100 for final bilateral finger retention, elevated >0.32 m and speed<0.25 m/s continuously >=0.5 s. Earlier retention capped at 49; mere proximity gives zero.",
        "g1": "100 * walking survival fraction * exp(-mean absolute speed error/0.6). Success additionally requires full survival, speed error<0.25 m/s, forward travel>7.02 m, lateral drift<2 m.",
    }
    public = {
        "schema": "control-transfer/1",
        "protocol": "eai-policy/1.1",
        "name": name,
        "goal": goals[family],
        "score": scores[family],
        "max_rounds": 3,
        "adaptation_cases": count,
        "held_out_cases": count * 2,
        "feedback": "Video frames and noisy measurements only; no deployment scores, contacts, parameters, seeds or true state. Diagnosis is a short observation/change/prediction, not private reasoning.",
        "training_backend": "mjlab / MuJoCo Warp GPU"
        if family == "g1"
        else "MuJoCo Warp GPU"
        if family == "linearbot"
        else "nominal MuJoCo CPU",
        "evaluation_backend": "native MuJoCo CPU",
        "policy_abi": "numeric fixed MLP NPZ (8 MiB maximum)"
        if family in ("g1", "linearbot")
        else "bounded JSON controller coefficients",
    }
    if family == "neural-fly":
        import ast

        values = {
            n.targets[0].id: ast.literal_eval(n.value)
            for n in ast.parse((SRC / "control_public/fly.py").read_text()).body
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "BOUNDS"
        }
        BOUNDS = values["BOUNDS"]
        DEFAULT = {
            "kp": 6.0,
            "kd": 4.0,
            "ki": 0.4,
            "attitude_gain": 80.0,
            "rate_gain": 16.0,
            "residual": [[0.0] * 7 for _ in range(3)],
        }
        public.update(
            default_policy=DEFAULT,
            bounds=BOUNDS,
            limitations="Flight-log-fitted force surrogate; approximate attitude/actuator dynamics, not PX4 SITL or a DAIML reproduction.",
        )
    elif family == "spacecraft":
        from nonlinearbench.contract import BASELINE, BOUNDS

        public.update(
            default_policy=BASELINE,
            bounds=BOUNDS,
            limitations="Rigid-body two-body relative dynamics; continuous body wrench, simplified contact geometry, no discrete thrusters or capture latch.",
        )
    elif family == "yam":
        from manipulationbench.contract import BASELINE, BOUNDS

        public.update(
            default_policy=BASELINE,
            bounds=BOUNDS,
            limitations="Hardware-derived YAM Menagerie model; synthetic noisy ball-position detector, benchmark contact and latency randomization; not hardware-calibrated.",
        )
    elif family == "linearbot":
        public["limitations"] = (
            "Provided robot geometry with idealized planar mobile base; no physical wheel-ground drive. Fixed 62→256→256→16 tanh actor."
        )
    else:
        public["limitations"] = (
            "Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor, frozen public PD wrapper. Coding-agent feedback contains only joint angles and images."
        )
    if family == "g1":
        from sim2realbench.g1.contract import JOINT_NAMES

        public["channels"] = JOINT_NAMES
        public["units"] = ["rad"] * 29
    elif family == "linearbot":
        public["channels"] = ["base_x", "base_y", "base_yaw", "joint9"] + [
            f"joint{i}_{side}" for side in ("L", "R") for i in range(1, 7)
        ]
        public["units"] = ["m", "m", "rad", "m"] + ["rad"] * 12
    elif family == "spacecraft":
        from nonlinearbench.contract import CHANNELS, UNITS

        public["channels"], public["units"] = CHANNELS, UNITS
    elif family == "yam":
        public["channels"] = [f"arm_joint_{i}" for i in range(1, 7)] + [
            "left_finger",
            "right_finger",
            "ball_x",
            "ball_y",
            "ball_z",
        ]
        public["units"] = ["rad"] * 6 + ["m"] * 5
    else:
        public["channels"] = {
            "position": "world m",
            "velocity": "world m/s",
            "quaternion": "wxyz body-to-world",
            "omega": "body rad/s",
            "target_position": "world m",
            "target_velocity": "world m/s",
            "target_acceleration": "world m/s²",
        }
    public["image_interval_s"] = 0.2 if family == "yam" else 10.0 if family == "spacecraft" else 1.0
    return {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "family": family,
        "name": name,
        "index": index,
        "public": public,
        "bank": {"adaptation": cases(False), "held_out": cases(True)},
    }
