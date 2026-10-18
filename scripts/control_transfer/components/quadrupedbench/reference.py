"""Operator-only reference candidates; do not install in the agent image.

Attitude has a demonstrated positive rollout. The other three candidates are
partial controls, retained to expose unresolved physical solvability gaps.
"""

import argparse
from pathlib import Path

from ...control_public.go2_data import default_policy, validate

SETTINGS = {
    "weave": {
        "parameters": {
            "height": 0.3,
            "stance_width": 0.12,
            "period": 0.5125964844738918,
            "swing_height": 0.04797793084814035,
            "stride_gain": 1.8930321526384768,
            "lateral_gain": 0.9768681796053276,
            "push_pd_scale": 0.25,
            "yaw_gain": 1.4340884899637416,
            "attitude_gain": 0.5,
            "rate_gain": 0.04,
            "support": 1.0,
            "crouch_height": 0.2,
            "push_duration": 0.16,
            "extend_height": 0.4,
            "push_gain": 2.8,
            "jump_forward": 1.0,
            "jump_yaw": 1.0,
            "flight_time": 0.35,
            "landing_height": 0.28,
        },
        "kp": 51.096628002016615,
        "kd": 1.82276161327083,
    },
    "forward-jump": {
        "parameters": {
            "height": 0.3,
            "stance_width": 0.12,
            "period": 0.5,
            "swing_height": 0.06,
            "stride_gain": 1.0,
            "lateral_gain": 1.0,
            "push_pd_scale": 1.0,
            "yaw_gain": 1.0,
            "attitude_gain": 0.5,
            "rate_gain": 0.04,
            "support": 1.0,
            "crouch_height": 0.20181658636255598,
            "push_duration": 0.1634987030005488,
            "extend_height": 0.4094891428248523,
            "push_gain": 3.9145046628850535,
            "jump_forward": 1.972010062566881,
            "jump_yaw": 2.102235382578857,
            "flight_time": 0.1658240046900319,
            "landing_height": 0.2973839993390586,
        },
        "kp": 85.77769640843006,
        "kd": 3.9171331647259944,
    },
    "yaw-jump": {
        "parameters": {
            "attitude_gain": 0.5,
            "crouch_height": 0.2,
            "extend_height": 0.34,
            "flight_time": 0.15,
            "height": 0.3,
            "jump_forward": 1.0,
            "jump_yaw": 2.5,
            "landing_height": 0.31,
            "lateral_gain": 0.65,
            "period": 0.5,
            "push_duration": 0.16,
            "push_gain": 2.8,
            "push_pd_scale": 0.25,
            "rate_gain": 0.04,
            "stance_width": 0.12,
            "stride_gain": 1.85,
            "support": 1.0,
            "swing_height": 0.06,
            "yaw_gain": 1.0,
        },
        "kp": 60.0,
        "kd": 2.0,
    },
}


def policy(task):
    if task not in ("attitude", "weave", "forward-jump", "yaw-jump"):
        raise ValueError("Unknown task")
    result = default_policy()
    if task in SETTINGS:
        entry = SETTINGS[task]
        result["parameters"].update(entry["parameters"])
        result["kp"] = [entry["kp"]] * 12
        result["kd"] = [entry["kd"]] * 12
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    for task in ("attitude", "weave", "forward-jump", "yaw-jump"):
        (out / (task + ".json")).write_bytes(validate(policy(task)))
