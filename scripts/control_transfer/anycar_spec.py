"""Stdlib-only operator-owned AnyCar instance hook; never copy into the agent image."""

from .control_public.anycar import CHANNELS, UNITS, DEFAULT, BOUNDS


def make_spec(index):
    base = 10000 + index * 1000
    plant_seed = base + 100

    def cases(start, n):
        return [dict(plant_seed=plant_seed, episode_seed=base + start + i) for i in range(n)]

    public = dict(
        schema="control-transfer/1",
        protocol="eai-policy/1.1",
        name="anycar",
        goal="Track one prescribed-time lap of a randomized ellipse across rigid traction patches; avoid barriers, rollover and offtrack excursions.",
        score="Ordered completion and time-indexed position/heading/speed accuracy. Safety violation gives zero. No nearest-waypoint score.",
        max_rounds=3,
        adaptation_cases=3,
        held_out_cases=10,
        training_backend="nominal MuJoCo CPU",
        evaluation_backend="native MuJoCo CPU + OSMesa + NumPy CPU",
        policy_abi="anycar-controller/1 bounded numeric JSON",
        default_policy=DEFAULT,
        bounds=BOUNDS,
        channels=CHANNELS,
        units=UNITS,
        image_interval_s=1.0,
        limitations="Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No AnyCar learned transformer is evaluated.",
    )
    return dict(
        schema="control-transfer-instance/2",
        transfer_track="same-plant",
        family="anycar",
        name="anycar",
        index=index,
        public=public,
        bank=dict(adaptation=cases(0, 3), held_out=cases(300, 10)),
    )


def make_circuit_spec(index, track_id="zigzag", revision="circuit-sector/1"):
    """Versioned circuit-sector bank; legacy ellipse instances remain unchanged."""
    from .components.anycarbench.tracks import resolve_track

    if revision not in ("circuit-sector/1", "circuit-lap/2"):
        raise ValueError(f"Unknown circuit revision: {revision}")
    spec = make_spec(index)
    layout = resolve_track(track_id)
    for bank in spec["bank"].values():
        for case in bank:
            case["track_id"] = layout
    spec["task_variant"] = "circuit-sector/1"
    spec["public"].update(
        track_id=layout,
        horizon_s=24.0,
        goal="Track a prescribed-time 24-second sector of a scaled circuit; cross ordered gates and avoid collisions/offtrack. Public nominal supports full-lap training.",
        geometry="Planar SVG-derived schematic, smoothed and uniformly scaled for RC steering; no elevation/bridge reconstruction.",
    )
    if revision == "circuit-lap/2":
        from .components.anycarbench.tracks import route_metadata

        metadata = route_metadata(layout)
        for bank in spec["bank"].values():
            for case in bank:
                case["full_lap"] = True
        spec["task_variant"] = revision
        spec["public"].update(
            task_variant=revision,
            scaled_length_m=metadata["scaled_length_m"],
            horizon_s=metadata["horizon_s"],
            horizon_rule="ceil_50Hz(scaled_length_m / 0.85 + 2.5)",
            completion="All ordered gates, spaced at most 0.5 m, including the finish line",
            goal="Track one complete lap of a scaled circuit at the prescribed speed; cross every ordered gate and finish line, avoiding collisions/offtrack. Record actual finish-crossing time.",
        )
    return spec
