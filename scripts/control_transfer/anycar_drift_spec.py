"""Stdlib-only private instance-generation hook for Drift to Park."""

from .control_public.anycar_drift import DEFAULT, BOUNDS, CHANNELS, UNITS, HORIZON


def make_spec(index):
    base = 10000 + index * 1000
    return dict(
        schema="control-transfer-instance/2",
        transfer_track="same-plant",
        family="anycar-drift",
        name="drift-to-park",
        index=index,
        task_variant="drift-park/1",
        public=dict(
            schema="control-transfer/1",
            protocol="eai-policy/1.1",
            name="Drift to Park",
            goal="Follow the ordered U-bend, then slide sideways into a parallel-parking space between two stationary cars and hold a precise stop.",
            max_rounds=3,
            adaptation_cases=3,
            held_out_cases=10,
            horizon_s=HORIZON,
            policy_abi="anycar-drift-controller/1 bounded numeric JSON",
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
            score="Ordered route, measured continuous sideslip, collision-free bay containment and stable aligned stop are mandatory. Quality grades final position and heading.",
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
