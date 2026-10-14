"""Stdlib-only private instance-generation hook for Drift to Park."""

from .control_public.anycar_drift_v3 import CHANNELS, HORIZON, UNITS
from .control_public.anycar_drift_feedback import BOUNDS, DEFAULT


def make_spec(index):
    base = 10000 + index * 1000
    return dict(
        schema="control-transfer-instance/2",
        transfer_track="same-plant",
        family="anycar-drift-v3",
        name="drift-to-park",
        index=index,
        task_variant="drift-park/3",
        public=dict(
            schema="control-transfer/1",
            protocol="eai-policy/1.1",
            name="Drift to Park",
            goal="Follow the ordered U-bend, then execute a 180-degree drifting turn into a tight inside parallel-parking space between two stationary cars and hold a precise stop.",
            course_revision="drift-park/3",
            nominal_bay_size_m=[0.69, 0.43],
            car_envelope_m=[0.49, 0.27],
            approach_straight_m=1.0,
            max_rounds=3,
            adaptation_cases=3,
            held_out_cases=10,
            horizon_s=HORIZON,
            policy_abi="anycar-drift-controller/3 bounded numeric JSON (legacy /2 accepted)",
            default_policy=DEFAULT,
            bounds=BOUNDS,
            channels=CHANNELS,
            units=UNITS,
            image_interval_s=0.1,
            training_backend="nominal MuJoCo CPU",
            evaluation_backend="native MuJoCo CPU + OSMesa",
            actions=[
                "drive velocity command",
                "front steering",
                "rear handbrake fraction",
            ],
            score="Ordered route, a post-route 180-degree turn with at least 120 degrees while sliding, collision-free bay containment and stable aligned stop are mandatory. Quality grades final position and heading.",
            limitations="Rigid RC tire contact and rear-wheel dry-friction brake; not a calibrated pneumatic-tire drifting or vehicle-damage model.",
        ),
        bank={
            name: [
                dict(plant_seed=base + 100, episode_seed=base + start + i)
                for i in range(n)
            ]
            for name, start, n in [("adaptation", 0, 3), ("held_out", 300, 10)]
        },
    )
