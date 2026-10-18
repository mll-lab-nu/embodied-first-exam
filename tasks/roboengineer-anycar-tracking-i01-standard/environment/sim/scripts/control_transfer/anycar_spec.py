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
        limitations="Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No learned vehicle model is evaluated.",
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

    if revision not in ("circuit-sector/1", "circuit-lap/2", "circuit-compact-lap/3"):
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
        from .components.anycarbench.tracks import route_metadata, route_budget

        metadata = route_metadata(layout)
        for bank in spec["bank"].values():
            for case in bank:
                case["full_lap"] = True
        spec["task_variant"] = revision
        spec["public"].update(
            task_variant=revision,
            scaled_length_m=metadata["scaled_length_m"],
            runtime_budget=route_budget(layout),
            horizon_s=metadata["horizon_s"],
            horizon_rule="ceil_50Hz(scaled_length_m / 0.85 + 2.5)",
            completion="All ordered gates, spaced at most 0.5 m, including the finish line",
            goal="Track one complete lap of a scaled circuit at the prescribed speed; cross every ordered gate and finish line, avoiding collisions/offtrack. Record actual finish-crossing time.",
        )
    if revision == "circuit-compact-lap/3":
        from .components.anycarbench.tracks import compact_catalog, compact_route_budget

        row = compact_catalog()["routes"][layout]
        for bank in spec["bank"].values():
            for case in bank:
                case.update(full_lap=True, route_revision="compact-30s/1")
        spec["task_variant"] = revision
        spec["public"].update(
            task_variant=revision, route_revision="compact-30s/1",
            horizon_s=30.0, target_lap_time_s=28.0, scaled_length_m=row["length_m"],
            runtime_budget=compact_route_budget(layout),
            completion="Every ordered forward gate and the finish line within 30 simulated seconds",
            goal="Track a complete compact F1-inspired lap, targeted at 28 seconds within a 30-second episode, avoiding collisions/offtrack.",
            geometry=compact_catalog()["geometry"],
            geometry_modifications={key: row[key] for key in ("smoothing_sigma_samples", "source_samples", "minor_axis_widening")},
        )
    return spec
