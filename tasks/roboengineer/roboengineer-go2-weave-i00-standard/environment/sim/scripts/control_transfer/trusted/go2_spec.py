"""Stdlib-only operator Go2 specifications; never export private case banks."""

from ..control_public.go2_data import CHANNELS, UNITS, PARAMS, default_policy

TASKS = ("weave", "attitude", "forward-jump", "yaw-jump")


def make_spec(index=0, task="attitude"):
    if task.startswith("go2-"):
        task = task[4:]
    if task not in TASKS or type(index) is not int or not 0 <= index < 10000:
        raise ValueError("Invalid Go2 specification")
    base = 10000 + index * 1000
    plant = base + 100

    def bank(held):
        return [
            {"task": task, "plant_seed": plant, "episode_seed": base + (300 if held else 0) + i}
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
        "limitations": "A simulated port of published quadruped performance tasks, not a hardware calibration; MuJoCo contacts differ from other simulators.",
    }
    return {
        "schema": "control-transfer-instance/2",
        "transfer_track": "same-plant",
        "family": f"go2-{task}",
        "name": f"go2-{task}",
        "index": index,
        "public": public,
        "bank": {"adaptation": bank(False), "held_out": bank(True)},
    }
