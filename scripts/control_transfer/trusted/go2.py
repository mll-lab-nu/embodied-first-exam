"""Operator-only Go2 family definitions and adapter; do not copy to the agent image."""

from pathlib import Path
import json

from ..control_public.go2 import CHANNELS, UNITS, PARAMS, default_policy, validate

TASKS = ("weave", "attitude", "forward-jump", "yaw-jump")


def make_spec(index=0, task="attitude"):
    if task.startswith("go2-"):
        task = task[4:]
    if task not in TASKS or type(index) is not int or not 0 <= index < 10000:
        raise ValueError("Invalid Go2 specification")
    plant = 730000 + index

    def bank(held):
        return [
            {"task": task, "plant_seed": plant, "episode_seed": 100000 + index * 1000 + (100 if held else 0) + i}
            for i in range(10 if held else 3)
        ]

    goals = {
        "weave": "Execute a predeclared body velocity command schedule to pass four alternating poles without contact; no global-position feedback.",
        "attitude": "Track public roll/pitch sinusoids after a 1 s acquisition interval while maintaining ground support.",
        "forward-jump": "Jump a commanded 0.70–1.00 m forward distance with verified flight and stable touchdown; walking to the goal is rejected.",
        "yaw-jump": "Jump through a commanded 110–150 degree heading change with verified airborne rotation and stable touchdown; ground spinning is rejected.",
    }
    score = {
        "weave": "Success requires four ordered alternating crossings, clearance >=0.16 m, no pole/body-ground collision, final x beyond last pole +0.35 m; score combines crossing fraction and tracking quality, unsuccessful capped at 49.",
        "attitude": "Success requires full horizon, roll/pitch RMSE <0.08 rad, base drift <0.25 m, supported fraction >=0.95, and no body-ground collision; unsuccessful score capped at 49.",
        "forward-jump": "Success requires flight >=0.08 s, height rise >=0.07 m, airborne x displacement >=70% command, first-touch and final x error <0.15 m, lateral error <0.15 m, and final 1 s stable support; unsuccessful score capped at 49.",
        "yaw-jump": "Success requires flight >=0.08 s, height rise >=0.07 m, airborne yaw >=70% command with first-touch yaw error <0.25 rad, final yaw error <0.18 rad, drift <0.25 m, and final 1 s stable support; unsuccessful score capped at 49.",
    }
    public = {
        "schema": "control-transfer/1",
        "protocol": "eai-policy/1.1",
        "name": f"go2-{task}",
        "goal": goals[task],
        "score": score[task],
        "max_rounds": 3,
        "adaptation_cases": 3,
        "held_out_cases": 10,
        "training_backend": "nominal MuJoCo CPU; GPU training may export the same bounded numeric artifact",
        "evaluation_backend": "native MuJoCo CPU / NumPy CPU / OSMesa software rendering",
        "policy_abi": "go2-controller/1 bounded JSON; validated numeric parameters, 17x12 offsets and 12x6 feedback gains",
        "default_policy": default_policy(),
        "bounds": PARAMS,
        "channels": CHANNELS,
        "units": UNITS,
        "image_interval_s": 1.0,
        "feedback": "37 noisy proprioceptive/public-command channels and sampled images; no global position, velocity, contact flags, scores, hidden parameters or seeds.",
        "limitations": "SPI-Active-inspired task port, not a hardware calibration or reproduction of its trained policies; MuJoCo contacts differ from Isaac Gym.",
    }
    return {
        "schema": "control-transfer-instance/1",
        "family": f"go2-{task}",
        "name": f"go2-{task}",
        "index": index,
        "public": public,
        "bank": {"adaptation": bank(False), "held_out": bank(True)},
    }


def rollout(policy_path, case, out, render=True):
    from ..components.quadrupedbench.simulation import rollout as run

    with Path(policy_path).open("rb") as artifact:
        raw = artifact.read(65537)
    if len(raw) > 65536:
        raise ValueError("Policy size limit")
    policy = json.loads(raw)
    validate(policy)
    return run(policy, case, out, render)
