"""Render the proposed corner-fold assets in the shared Genesis/Nyx scene.

Example (from the repository root)::

    PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m \
        topogym.tasks.blanket_flatten.below_easy_preview --variation very_easy \
        --output runs/test_results/blanket_corner_preview/very_easy

This writes an authored particle pose once, at tick zero. It does not prepare or
install a frozen task instance, perform gravity settling, or qualify a solution.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np

from topogym.assets.geometry.blanket_corner_folds import (
    REVISION, folded_positions, generate, profile_for,
)
from topogym.assets.geometry.blanket_flatten import write_obj
from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic


def preview(variation, output, *, backend="cuda", seed=0):
    from omegaconf import OmegaConf
    from scipy.spatial import cKDTree
    import torch
    from topogym.config.scene import load_scene_config
    from topogym.recording.segment import save_rgb
    from topogym.robot import make_robot
    from topogym.sensors.observation import SensorSuite
    from topogym.simulator.config import SimulatorConfig
    from topogym.tasks.blanket_flatten.common import BlanketFlattenTask
    from topogym.tasks.blanket_flatten.gathered import scene_parameters
    from topogym.utils.arrays import to_numpy
    from topogym.world.genesis_world import GenesisWorld

    torch.set_num_threads(1)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    # Inherit dimensions, material, placement, friction and goal thresholds from
    # easy; flat birth preserves the common rest metric and visual binding.
    parameters = scene_parameters("easy")
    parameters.pop("gathered_profile")
    parameters.pop("initial_state_acceptance")
    parameters["initialization_mode"] = "flat_for_preparation"
    config = SimulatorConfig(task_id="blanket_flatten", variation_id="easy",
        compute_backend=backend, task_parameters=parameters, seed=seed)
    cfg = load_scene_config(config)
    task = BlanketFlattenTask(parameters, seed=seed)
    table = cfg.env.world.table
    table_z = float(table.pos[2]+table.size[2]/2)
    spec = task.declare(root/"assets", table_z)
    # The dynamic-mesh Nyx exporter reads entity.surface, where the implicit
    # Cloth double-sided default can remain None. Explicitly show the reverse
    # side of each turned flap; keep the inherited fabric texture/material.
    spec = replace(spec, entities=tuple(replace(entity,
        surface={**entity.surface, "double_sided": True}) for entity in spec.entities))
    profile = profile_for(variation)
    display, faces, uv, report = generate(variation, task.layout)
    origin = np.array([*task.config["center_xy_m"], table_z])
    write_obj(root/"authored_fold.obj", display+origin, faces, uv, task.layout)
    report.update(status="building", variation_id=f"blanket_flatten_{variation}",
        seed=seed, config=to_jsonable(config), inherited_task_parameters=task.config,
        scene=OmegaConf.to_container(cfg, resolve=True), physics_ticks=0,
        particle_position_writes=1, rest_shape_writes=0, visual_support_writes=0,
        initial_state_archive_exported=False,
        preview_surface_override={"double_sided": True},
        source_sha256={str(p.relative_to(Path(__file__).parents[2])): sha256_file(p)
            for p in (Path(__file__), Path(__file__).parents[2]/"assets/geometry/blanket_corner_folds.py",
                      Path(__file__).with_name("common.py"), Path(__file__).with_name("gathered.py"))})
    write_json_atomic(root/"report.json", report)
    world = None
    try:
        world = GenesisWorld.from_tabletop(cfg.env, cfg.robot_control,
            physics_options=spec.physics_options, compute_backend=backend,
            precision=config.precision, seed=seed, cameras=True)
        world.add_entities(spec.entities)
        world.build()
        print("Built shared scene; mapping the authored corner fold", flush=True)
        robot = make_robot(world.entities["robot"], cfg.robot_control)
        robot.reset_home()
        task.bind(world.entities)
        cloth = world.entities["blanket"]
        target = folded_positions(task.material_uv, task.layout.length_m,
            task.layout.width_m, profile)+origin
        material_distance = 4*task.layout.particle_size_m
        pairs = cKDTree(target).query_pairs(material_distance, output_type="ndarray")
        pairs = pairs[np.linalg.norm(task.material_uv[pairs[:, 0]]-
            task.material_uv[pairs[:, 1]], axis=1) > material_distance]
        gap = (float(np.linalg.norm(target[pairs[:, 0]]-target[pairs[:, 1]], axis=1).min())
               if len(pairs) else material_distance)
        report["particle_gap_check"] = dict(minimum_nonlocal_distance_m=gap,
            material_distance_cutoff_m=material_distance,
            required_gap_m=task.layout.particle_size_m,
            scope="sampled particle separation; not surface collision or settling qualification")
        if gap < task.layout.particle_size_m:
            raise ValueError("Authored fold brings nonlocal material particles too close")
        cloth.set_particles_pos(target)
        cloth.set_particles_vel(np.zeros_like(target))
        readback = to_numpy(cloth.get_particles_pos())
        state = world.read_state()
        goal, failure, metrics = task.evaluate_state(state)
        if goal or failure:
            raise ValueError(f"Authored preview must be unsolved and valid: {failure}, {metrics}")
        task.initialize(state)
        frame = SensorSuite(world, robot, enable_rgb=True).sample(
            episode_id=f"{REVISION}_{variation}", branch_id=0, state_id=0, task=task)[1]
        report["frames"] = save_rgb(root, "initial", frame)
        report["camera_metadata"] = to_jsonable(frame.camera_metadata)
        report["robot_home_observation"] = to_jsonable(robot.observe())
        report["binding"] = task.binding_report
        report["metrics"] = metrics
        report["initial_goal_satisfied"] = bool(goal)
        report["maximum_particle_readback_error_m"] = float(np.max(np.abs(readback-target)))
        report["particles"] = len(target)
        report["status"] = "static_preview_rendered"
        np.savez_compressed(root/"authored_particles.npz", positions=readback,
            material_uv=task.material_uv, faces=task.particle_faces,
            velocities=to_numpy(cloth.get_particles_vel()))
        assert world.physics_step == 0
        return report
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json_atomic(root/"report.json", report)
        if world is not None:
            world.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variation", choices=("very_easy", "easier"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    report = preview(args.variation, args.output, backend=args.backend, seed=args.seed)
    print(f"Rendered {args.variation}: {report['frames']}", flush=True)


if __name__ == "__main__":
    main()
