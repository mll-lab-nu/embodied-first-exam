"""Operator-owned family specification and reproducible development case banks."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC / "components"))
sys.path.insert(0, str(SRC))
# Only the current roboEngineer work packages are generated. The other prototypes
# remain available to explicit local development calls, without published tasks.
FAMILIES = [
    "neural-fly",
    "neural-fly-general-v1",
    "neural-fly-general-skydio-v1",
    "neural-fly-vector-wind-v1",
    "g1",
    "anycar",
    "anycar-drift",
    "anycar-drift-v3",
    "anycar-circuit-lap-v2-silverstone-8",
    "anycar-circuit-lap-v2-monaco-6",
    "anycar-circuit-compact-v3-silverstone-8",
    "anycar-circuit-compact-v3-monaco-6",
    "go2-weave",
    "go2-attitude",
    "go2-forward-jump",
    "go2-yaw-jump",
]


def spec(name, index):
    circuit_revisions = {
        "anycar-circuit-v1-": "circuit-sector/1",
        "anycar-circuit-lap-v2-": "circuit-lap/2",
        "anycar-circuit-compact-v3-": "circuit-compact-lap/3",
    }
    prefix = next((key for key in circuit_revisions if name.startswith(key)), None)
    if prefix:
        from .anycar_spec import make_circuit_spec

        value = make_circuit_spec(index, name.removeprefix(prefix), revision=circuit_revisions[prefix])
        value["name"] = name
        value["public"].update(name=name, task_variant=value["task_variant"])
        value["public"]["limitations"] += " " + value["public"]["geometry"]
        return value
    if name.startswith("go2-"):
        from .trusted.go2_spec import make_spec

        value = make_spec(index, name)
        value["family"] = "go2"
        return value
    if name in (
        "neural-fly",
        "neural-fly-general-v1",
        "neural-fly-general-skydio-v1",
        "neural-fly-vector-wind-v1",
    ):
        from .neuralfly_spec import make_spec

        revision = (
            "fixed-eight/1"
            if name == "neural-fly"
            else "general-eight-wind/1"
            if name == "neural-fly-vector-wind-v1"
            else "general-eight/1"
        )
        value = make_spec(index, revision=revision)
        value["name"] = name
        value["public"]["name"] = name
        if "task_revision" in value:
            value["public"]["task_revision"] = value["task_revision"]
        if name == "neural-fly-vector-wind-v1":
            value["dynamics_revision"] = "vector-wind/1"
            value["public"]["dynamics_revision"] = "vector-wind/1"
        if name == "neural-fly-general-skydio-v1":
            value["observation_revision"] = "neuralfly-skydio/1"
            value["visual_profile"] = "skydio-x2/1"
            value["public"].update(
                observation_revision="neuralfly-skydio/1",
                visual_profile="skydio-x2/1",
                video_resolution=[960, 720],
                video_fps=10,
            )
            value["public"]["limitations"] += (
                " Skydio X2 appearance only; the underlying Neural Fly surrogate is not calibrated Skydio dynamics."
            )
        value.update(schema="control-transfer-instance/2", transfer_track="same-plant")
        return value
    if name == "anycar":
        from .anycar_spec import make_spec

        return make_spec(index)
    if name == "anycar-drift-v3":
        from .anycar_drift_v3_spec import make_spec

        value = make_spec(index)
        value["name"] = name
        value["public"].update(
            name=name,
            task_variant=value["task_variant"],
            feedback="Public course command, 14 noisy sensor/own-action values and 161 images at 10 Hz. No hidden state, plant parameters, seeds, contacts or scores.",
            command_fields=["radius", "park_x", "park_y", "slot_length", "slot_width", "target_yaw", "start_x", "revision"],
            command_units=["m", "m", "m", "m", "m", "rad", "m", "revision string"],
            video_resolution=[1920, 540],
            video_fps=10,
            image_sampling="All 161 frames at fixed 0.1-second times from 0 through 16 s, with all 161 noisy telemetry rows.",
            score="Complete the ordered U-route, then turn by pi radians within 0.25 rad, accumulating at least 120 degrees while sliding. Sliding requires body lateral speed >0.2 m/s, planar speed >0.6 m/s and sideslip >10 degrees near the bay; sustain it for 0.15 s and accumulate 0.06 m of lateral slide. Park the entire car envelope inside the bay with x error <0.18 m, y error <0.12 m, yaw error <0.14 rad, speed <0.08 m/s and yaw rate <0.1 rad/s for the final 0.5 s. Collision, rollover, chassis-ground contact or route departure fails. A successful case scores 100*exp(-final_position_error_m/0.25-final_yaw_error_rad/0.3); otherwise zero.",
        )
        return value
    if name == "anycar-drift":
        from .anycar_drift_spec import make_spec

        value = make_spec(index)
        value["name"] = name
        value["public"].update(
            task_variant=value["task_variant"],
            feedback="Public course command, 14 noisy sensor/own-action values and 161 images at 10 Hz. No hidden state, plant parameters, seeds, contacts or scores.",
            command_fields=["radius", "park_x", "park_y", "slot_length", "slot_width"],
            command_units=["m"] * 5,
            video_resolution=[1920, 540],
            video_fps=10,
            image_sampling="All 161 frames at fixed 0.1-second times from 0 through 16 s, with all 161 noisy telemetry rows.",
            score="Complete the ordered U-route, then slide near the bay with body lateral speed >0.2 m/s, planar speed >0.6 m/s and sideslip >10 degrees continuously for at least 0.15 s, accumulating at least 0.06 m of lateral slide. Park the entire car envelope inside the bay with x error <0.18 m, y error <0.12 m, yaw error <0.14 rad, speed <0.08 m/s and yaw rate <0.1 rad/s for the final 0.5 s. Collision, rollover, chassis-ground contact or route departure fails. A successful case scores 100*exp(-final_position_error_m/0.25-final_yaw_error_rad/0.3); otherwise zero.",
        )
        return value
    family = "linearbot" if name.startswith("linearbot") else name
    base = 10000 + index * 1000
    count = {"neural-fly": 5, "linearbot": 3, "spacecraft": 3, "yam": 9, "g1": 4}[family]

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
        "g1": "Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity command of 0.5–0.65 m/s for 18 s.",
    }
    scores = {
        "neural-fly": "Crash or escape: 0. Otherwise 100 exp(-max(0,tracking_RMSE_m-0.03)/0.25); success requires full horizon and RMSE<0.25 m. Tracking uses prescribed timestamps; slowing the reference is impossible.",
        "linearbot": "100 exp(-mean(normalized_errors)); six thresholds: base xy 0.06 m, yaw 0.12 rad, each hand position 0.07 m, each orientation 0.20 rad. Success requires all six time-mean errors below threshold after a 1 s acquisition interval.",
        "spacecraft": "Collision or escape: 0. Weighted terminal pose, speed, angular rate and impulse quality; unsuccessful capture is capped at 49. Thresholds: 0.08 m, 0.025 m/s, 0.07 rad, 0.025 rad/s for final 3 s.",
        "yam": "100 for final bilateral finger retention, elevated >0.32 m and speed<0.25 m/s continuously >=0.5 s. Earlier retention capped at 49; mere proximity gives zero.",
        "g1": "100 * walking survival fraction * exp(-speed MAE/commanded speed) * clipped forward-progress fraction. Success requires full 20 s survival, speed MAE<0.25 m/s, forward travel>65% of commanded walking distance, lateral drift<2 m. Standing still scores zero.",
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
            limitations="Flight-log-fitted force surrogate; approximate attitude/actuator dynamics, not a flight-stack simulation or a learned aerodynamics model.",
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
    bank = {"adaptation": cases(False), "held_out": cases(True)}
    if family == "g1":
        from sim2realbench.g1.terrain import make_spec

        terrain_spec = make_spec(index)
        bank = {part: terrain_spec[part] for part in ("adaptation", "held_out")}
        public.update(
            adaptation_cases=len(bank["adaptation"]),
            held_out_cases=len(bank["held_out"]),
        )
        public["command_channels"] = [
            "forward_velocity",
            "lateral_velocity",
            "yaw_rate",
        ]
        public["command_units"] = ["m/s", "m/s", "rad/s"]
        public["limitations"] = (
            "Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper. Coding-agent feedback is noisy joint angles, public commands and images; reference solvability remains incomplete on both development plants."
        )
    public["image_interval_s"] = 0.2 if family == "yam" else 10.0 if family == "spacecraft" else 1.0
    return {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "family": family,
        "name": name,
        "index": index,
        "public": public,
        "bank": bank,
    }
