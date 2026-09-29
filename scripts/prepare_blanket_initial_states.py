"""Build a qualified offline Blanket candidate and record its whole preparation.

Run with the repository (or an immutable source snapshot) on PYTHONPATH.
This is management velocity control, not a robot oracle or agent action.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import traceback

import numpy as np

from topogym.utils.io import write_json_atomic, sha256_file, to_jsonable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tier", choices=("easy", "medium", "hard"),
                        help="Use the shared fixed gathered scene recipe; geometric/material CLI overrides are not allowed")
    parser.add_argument("--acceptance", choices=("released_stable", "scene_layout"), default="released_stable",
                        help="Scene layout defers particle-motion qualification, keeping material and placement checks")
    parser.add_argument("--twist-angle", type=float, default=0.)
    parser.add_argument("--placement-roll", type=float, default=0.)
    parser.add_argument("--gather-seconds", type=float, default=3.)
    parser.add_argument("--table-friction", action="store_true", help="Enable the same contact model during preparation and runtime")
    parser.add_argument("--air-resistance", type=float, default=.001,
                        help="Explicit persistent PBD damping parameter")
    parser.add_argument("--maximum-settle-seconds", type=float, default=8.)
    parser.add_argument("--center-y", type=float, default=.05,
                        help="Explicit candidate placement; keep the preparation clear of the home grippers")
    parser.add_argument("--panels", type=int, choices=(2, 8), default=8,
                        help="Two panels provide a single-fold control")
    parser.add_argument("--axial-scale", type=float, default=.92)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeded", action="store_true",
                        help="variation_id='seeded': tier = seed %% 3, plus the seed's colour/pattern/centre draw "
                             "(topogym.tasks.scene_variation), applied before freezing")
    parser.add_argument("--bending-compliance", type=float, default=1e-5,
                        help="Explicit candidate material; never changes task defaults")
    parser.add_argument("--bending-relaxation", type=float, default=.1,
                        help="Explicit candidate bending strength; 0 means no bending response")
    parser.add_argument("--no-rgb", action="store_true", help="Explicit physics diagnostic only")
    parser.add_argument("--particle-diagnostics", action="store_true",
                        help="Read-only per-tick material/binding/speed/contact-candidate diagnostics")
    args = parser.parse_args()
    if args.seeded:
        from topogym.config.registry import TIER_ORDER
        tier = TIER_ORDER[args.seed % 3]
        if args.tier not in (None, tier):
            parser.error(f"--seeded seed {args.seed} selects tier {tier}, not {args.tier}")
        args.tier = tier
    if args.acceptance == "scene_layout" and not args.tier:
        parser.error("--acceptance scene_layout requires an explicit --tier")
    if args.tier:
        import sys
        forbidden = {"--twist-angle", "--placement-roll", "--table-friction", "--air-resistance",
                     "--center-y", "--panels", "--axial-scale", "--bending-compliance", "--bending-relaxation"}
        if any(token.split("=")[0] in forbidden for token in sys.argv[1:]):
            parser.error("--tier owns geometry and material parameters; use an untiered candidate for experiments")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    from topogym.simulator.config import SimulatorConfig
    from topogym.config.scene import load_scene_config
    from topogym.tasks.blanket_flatten.common import BlanketFlattenTask
    from topogym.world.genesis_world import GenesisWorld
    from topogym.world.physics.cloth_preparation import ClothPreparation, PreparationConfig
    from topogym.world.physics.pbd_initial_state import export_initial_state
    from topogym.world.initial_state import scene_identity
    from topogym.assets.geometry.blanket_gathered import GatheredProfile
    from topogym.assets.library import describe_build
    from topogym.robot import make_robot
    from topogym.sensors.observation import SensorSuite
    from topogym.recording.segment import SegmentMedia
    from topogym.utils.variant_rng import seed_process
    from topogym.utils.snapshots import thaw
    import topogym
    source = Path(topogym.__file__).parent
    config = SimulatorConfig(task_id="blanket_flatten", variation_id="simple_folds", enable_rgb=not args.no_rgb,
        seed=args.seed, task_parameters={"initialization_mode": "flat_for_preparation",
            "center_xy_m": [-.1356786, args.center_y],
            "table_friction": {"static_mu": .5, "kinetic_mu": .4, "contact_tolerance_m": .001} if args.table_friction else None,
            "material": {"bending_compliance": args.bending_compliance,
                         "bending_relaxation": args.bending_relaxation,
                         "air_resistance": args.air_resistance}})
    profile, preparation = GatheredProfile(twist_angle_deg=args.twist_angle,
        placement_roll_deg=args.placement_roll, axial_scale=args.axial_scale,
        end_opening_deg=0. if args.panels == 2 else 10.,
        centerline_sway_m=0. if args.panels == 2 else .006,
        panel_fractions=(.5, .5) if args.panels == 2 else GatheredProfile().panel_fractions), PreparationConfig(gather_seconds=args.gather_seconds,
            maximum_settle_seconds=args.maximum_settle_seconds)
    task_class = BlanketFlattenTask
    scene_variation = None
    if args.tier:
        from importlib import import_module
        from dataclasses import replace
        from topogym.tasks.blanket_flatten.gathered import scene_parameters
        module = import_module(f"topogym.tasks.blanket_flatten.blanket_flatten_{args.tier}")
        task_class = getattr(module, f"BlanketFlatten{args.tier.title()}Task")
        parameters = scene_parameters(args.tier)
        if args.seeded:
            from topogym.tasks.base import merge_parameters
            from topogym.tasks.scene_variation import SCENE_VARIATION_VERSION, draw
            draws = draw(task_class, args.seed)
            scene_variation = dict(version=SCENE_VARIATION_VERSION, draws=draws)
            parameters = merge_parameters(parameters, draws)
        parameters["initialization_mode"] = "flat_for_preparation"
        config = replace(config, variation_id=args.tier, task_parameters=parameters)
        profile = GatheredProfile(**parameters["gathered_profile"])
    report = dict(status="in_progress", robot_manipulation=False, kind="offline_initial_state_preparation",
        config=to_jsonable(config), profile=asdict(profile), preparation=asdict(preparation),
        acceptance=args.acceptance, scene_variation=scene_variation,
        source_sha256={str(p.relative_to(source)): sha256_file(p) for p in sorted(source.rglob("*.py"))})
    write_json_atomic(root/"report.json", report)
    world = media = controller = diagnostic = None
    tick_log = (root/"ticks.jsonl").open("w")
    chunk, chunk_id = [], 0
    def flush():
        nonlocal chunk, chunk_id
        if chunk:
            target = root/f"particles_{chunk_id:04d}.npz"
            temporary = target.with_suffix(".npz.tmp")
            with temporary.open("xb") as stream:
                np.savez_compressed(stream, physics_step=np.array([row[0] for row in chunk]),
                    positions=np.stack([row[1] for row in chunk]), velocities=np.stack([row[2] for row in chunk]))
            temporary.rename(target)
            for row in chunk:
                tick_log.write(row[3]+"\n")
            tick_log.flush()
            chunk, chunk_id = [], chunk_id+1
    try:
        seed_process(args.seed)
        cfg = load_scene_config(config)
        task = task_class(thaw(config.task_parameters), seed=args.seed)
        table = cfg.env.world.table
        spec = task.declare(root/"assets", float(table.pos[2]+table.size[2]/2))
        build = describe_build(config.task_id, root/"assets", task.config, args.seed)
        identity = scene_identity(config, cfg, task, spec, build)
        write_json_atomic(root/"identity.json", identity)
        world = GenesisWorld.from_tabletop(cfg.env, cfg.robot_control, physics_options=spec.physics_options,
            compute_backend=config.compute_backend, precision=config.precision, seed=args.seed, cameras=config.enable_rgb)
        world.diagnostics_dir = root/"physics_diagnostics"
        world.add_entities(spec.entities)
        world.build()
        robot = make_robot(world.entities["robot"], cfg.robot_control)
        robot.reset_home()
        task.bind(world.entities)
        report["birth_binding"] = task.binding_report
        table_xy, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
        if args.particle_diagnostics:
            from topogym.world.physics.cloth_diagnostics import ClothDiagnosticRecorder
            diagnostic = ClothDiagnosticRecorder(root/"particle_diagnostics", task, profile,
                table_bounds=(table_xy-half, table_xy+half), speed_limit=preparation.settled_maximum_speed_m_s)
            report["particle_diagnostics"] = "particle_diagnostics"
        write_json_atomic(root/"report.json", report)
        sensors = SensorSuite(world, robot, enable_rgb=config.enable_rgb)
        def frame():
            return sensors.sample(episode_id="blanket_offline_preparation", branch_id=0,
                state_id=world.physics_step, task=task)[1]
        if config.enable_rgb:
            media = SegmentMedia(root, 0, frame())
        next_frame = 1/30
        previous_stage = None
        def on_tick(stage, positions, velocities):
            nonlocal next_frame, previous_stage
            if stage != previous_stage:
                print(f"STAGE {stage} tick={world.physics_step} t={world.sim_time_s:.3f}", flush=True)
                previous_stage = stage
            row = json.dumps(dict(physics_step=world.physics_step, sim_time_s=world.sim_time_s,
                stage=stage, particle_file=f"particles_{chunk_id:04d}.npz", particle_row=len(chunk),
                robot=to_jsonable(robot.observe())))
            chunk.append((world.physics_step, positions.copy(), velocities.copy(), row))
            if diagnostic is not None:
                diagnostic.sample(world.physics_step, world.sim_time_s, stage, positions, velocities)
            if len(chunk) >= 100:
                flush()
                tick_log.flush()
            if media is not None and world.sim_time_s+1e-10 >= next_frame:
                media.append(frame())
                next_frame += 1/30
        controller = ClothPreparation(world, task, profile, table_bounds=(table_xy-half, table_xy+half),
            config=preparation, on_tick=on_tick)
        on_tick("flat_birth", *controller.state())
        controller.run(acceptance=args.acceptance)
        report["preparation_result"] = controller.report
        # A complete retained log/video is separate from qualification success.
        if media is not None:
            if media.last_frame.state_id != world.physics_step:
                media.append(frame())
            report["media"] = media.finish()
            media = None
        flush()
        tick_log.flush()
        write_json_atomic(root/"qualification.json", controller.report)
        qualified = controller.report["completed"]
        manifest = export_initial_state(world, root/"state", identity=identity, robot=robot,
            qualification=dict(passed=qualified, scope=args.acceptance,
                scene_layout_passed=qualified or controller.report.get("scene_layout_completed", False),
                report_sha256=sha256_file(root/"qualification.json"),
                preparation=controller.report, binding=task.binding_report))
        report.update(status="passed" if qualified else "scene_layout_ready", manifest=str(manifest),
                      motion_qualified=qualified, actual_physics_ticks=world.physics_step)
        np.savez_compressed(root/"reference.npz", positions=controller.state()[0], velocities=controller.state()[1])
        # Independent continuation evidence; it does not alter the frozen anchor.
        positions, velocities = [], []
        for _ in range(5):
            world.advance()
            p, v = controller.state()
            positions.append(p); velocities.append(v)
        np.savez_compressed(root/"continuation.npz", positions=positions, velocities=velocities)
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        if controller is not None:
            report["preparation_result"] = controller.report
        if media is not None:
            try:
                if media.last_frame.state_id != world.physics_step:
                    media.append(frame())
                report["media"] = media.finish()
                media = None
            except BaseException as media_error:
                report["media_error"] = repr(media_error)
        raise
    finally:
        flush()
        tick_log.close()
        if diagnostic is not None:
            diagnostic.close()
        write_json_atomic(root/"report.json", report)
        if media is not None:
            media.abort()
        if world is not None:
            world.close()


if __name__ == "__main__":
    main()
