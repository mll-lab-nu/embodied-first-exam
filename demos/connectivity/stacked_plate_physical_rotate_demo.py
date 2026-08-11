"""Redesigned stacked-plate demo: rotate vertical disks on a Y rod to align sectors.

Each disk is a revolute joint about the horizontal Y rod. The arm pinches a disk's
rim between its two finger pads and rolls it downward; the disk turns **only from
finger friction** (no joint writes, no teleport), so the arc is contact-driven and
honest to the collision-based IL contract. Success = all disks' sector angles
within tolerance, with real rotation / follow-error / release-drift checks.

Configuration is Hydra (`configs/stacked_plate_rotate.yaml`).

    python -m demos.connectivity.stacked_plate_physical_rotate_demo run.viewer=true run.verbose=true
    python -m demos.connectivity.stacked_plate_physical_rotate_demo task.oracle.target_angle_deg=90
    python -m demos.connectivity.stacked_plate_physical_rotate_demo task.physical.noslip_iterations=8
    python -m demos.connectivity.stacked_plate_physical_rotate_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import hydra_config_sources, save_resolved_config
from topogym.generation import EpisodeResult, build_stacked_plate_episode_spec
from topogym.planning import plan_stacked_plate_rotation
from topogym.primitives import (
    RimRotatePrimitive,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import StackedPlateSceneBuilder
from topogym.verification import StackedPlatePuzzleEvaluator
from topogym.utils import (
    initialize_franka_controller,
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)




def _hud(plate_scene, status: dict):
    evaluator = StackedPlatePuzzleEvaluator()

    def render_lines():
        state = evaluator.classify(plate_scene)
        return [
            "task=stacked_plate (disks/sector)",
            f"phase={status.get('phase', 'setup')}",
            f"disk={status.get('disk', '-')}",
            f"spread={np.rad2deg(state.alignment_spread):.1f}deg (tol={np.rad2deg(state.alignment_tolerance):.1f})",
            f"aligned={state.is_terminal}",
        ]

    return render_lines


def _build_primitive(cfg, plate_scene) -> RimRotatePrimitive:
    physical = cfg.task.physical
    layout = plate_scene.layout
    return RimRotatePrimitive(
        approach_z=layout.world_z(float(physical.approach_z)),
        steps_move=int(physical.move_steps),
        steps_arc=int(physical.arc_steps),
        gripper_steps=int(physical.gripper_steps),
        grasp_qpos=float(physical.grasp_qpos),
        grasp_yaw_offset=float(physical.grasp_yaw_offset),
        approach_clearance=float(getattr(physical, "approach_clearance", 0.035)),
        retreat_clearance=float(getattr(physical, "retreat_clearance", 0.035)),
        close_hold_steps=int(physical.close_hold_steps),
        arc_settle_steps=int(physical.arc_settle_steps),
        release_hold_steps=int(physical.release_hold_steps),
        rotation_tolerance=float(np.deg2rad(float(physical.rotation_tolerance_deg))),
        min_rotation=float(np.deg2rad(float(physical.min_rotation_deg))),
        max_follow_error=float(getattr(physical, "max_rim_follow_error", 0.05)),
        max_release_drift=float(np.deg2rad(float(physical.max_release_drift_deg))),
        verbose=cfg.run.verbose,
    )


def run_demo(cfg, plate_scene, controller, status, *, episode_spec, episode_plan, commands) -> EpisodeResult:
    physical = cfg.task.physical
    layout = plate_scene.layout
    print_collision_il_contract(
        "stacked_plate_physical_rotate_demo",
        manipulated=tuple(f"disk_{c.disk_name}" for c in commands),
        success_checks=("rotation_achieved", "rim_follow_error", "target_angle_error", "release_drift", "sector_alignment"),
    )
    configure_gripper_contact_friction(
        entities=list(plate_scene.articulated_plate_entities.values()),
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.disk_friction),
        finger_friction=float(physical.finger_friction),
    )

    controller.step(int(physical.settle_steps))
    primitive = _build_primitive(cfg, plate_scene)
    print(
        "stacked_plate_physical_rotate_demo setup "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"disks={[c.disk_name for c in commands]} "
        f"target_angle={np.rad2deg(layout.target_angle()):.1f}deg arc_steps={primitive.steps_arc}",
        flush=True,
    )

    if stop_before_physics(cfg, plate_scene.scene, "stacked_plate_physical_rotate_demo"):
        raise SystemExit(0)

    results = []
    max_follow_error = 0.0
    for command in commands:
        status.update(disk=command.disk_name, phase="rotate")
        result = primitive.run(
            controller,
            disk_entity=plate_scene.articulated_plate_entities[command.disk_name],
            dof=plate_scene.plate_joint_dofs[command.disk_name],
            disk_name=command.disk_name,
            center=command.center_xyz,
            radius=command.radius,
            target_angle=command.target_angle,
            grasp_azimuth=command.grasp_azimuth,
            roll_sign=command.roll_sign,
            grasp_radius_scale=command.grasp_radius_scale,
        )
        results.append(result)
        max_follow_error = max(max_follow_error, result.max_follow_error)
        if cfg.run.verbose:
            print(
                f"stacked_plate_physical_rotate_demo disk={command.disk_name} "
                f"rotation_achieved={np.rad2deg(result.rotation_achieved):+.1f}deg "
                f"final_angle={np.rad2deg(result.final_disk_angle):+.1f}deg "
                f"target_error={np.rad2deg(result.target_error):.2f}deg "
                f"follow_error={result.max_follow_error:.4f} "
                f"release_drift={np.rad2deg(result.release_drift):.2f}deg "
                f"driven={result.driven} success={result.success}",
                flush=True,
            )

    status["phase"] = "verify"
    controller.step(max(0, int(physical.final_hold_steps)))
    state = StackedPlatePuzzleEvaluator().classify(plate_scene)
    follow_limit = float(getattr(physical, "max_rim_follow_error", 0.05))
    task_success = bool(state.is_terminal)
    physical_quality_success = bool(
        task_success
        and all(result.success for result in results)
        and max_follow_error <= follow_limit
    )
    status["phase"] = "success" if task_success else "failed"

    metrics = {
        "task_success": bool(task_success),
        "physical_quality_success": bool(physical_quality_success),
        "aligned": bool(state.is_terminal),
        "alignment_spread_deg": float(np.rad2deg(state.alignment_spread)),
        "alignment_tolerance_deg": float(np.rad2deg(state.alignment_tolerance)),
        "max_follow_error": float(max_follow_error),
        "all_disks_driven": bool(all(result.driven for result in results)),
    }
    episode_result = (
        EpisodeResult.ok(episode_spec.key, metrics=metrics, export_ready=physical_quality_success)
        if task_success
        else EpisodeResult.failed(
            episode_spec.key, "sectors_not_aligned", metrics=metrics, stable_ready=False
        )
    )
    print(
        "stacked_plate_physical_rotate_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"task_success={task_success} "
        f"physical_quality_success={physical_quality_success} "
        f"aligned={state.is_terminal} spread={np.rad2deg(state.alignment_spread):.2f}deg "
        f"max_follow_error={max_follow_error:.4f}",
        flush=True,
    )
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="stacked_plate_rotate")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"stacked_plate_rotate_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        from topogym.generation.layout_randomization import randomize_task_cfg

        cfg = randomize_task_cfg(
            cfg, str(cfg.task.task.id), cfg.run.seed, difficulty=cfg.run.difficulty
        )
        print(
            f"stacked_plate_physical_rotate_demo randomize_layout=on seed={cfg.run.seed} "
            f"difficulty={cfg.run.difficulty}",
            flush=True,
        )
    # Which config file each group resolved to, recorded as episode provenance.
    sources = hydra_config_sources()
    episode_spec = build_stacked_plate_episode_spec(
        cfg,
        seed=cfg.run.seed,
        common_config=sources.get("common"),
        env_config=sources.get("env"),
        robot_config=sources.get("robot_control"),
        task_config=sources.get("task"),
        variant_id=cfg.run.variant_id,
    )
    has_display = os.name == "nt" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if cfg.run.viewer and not has_display:
        raise SystemExit("No graphical display detected.")
    noslip_iterations = int(cfg.task.physical.noslip_iterations)
    if noslip_iterations < 0:
        raise SystemExit("noslip-iterations must be non-negative.")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    print(
        f"stacked_plate_physical_rotate_demo building_scene backend={cfg.env.genesis.backend} viewer={cfg.run.viewer}",
        flush=True,
    )
    plate_scene = StackedPlateSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        rigid_options=gs.options.RigidOptions(noslip_iterations=noslip_iterations),
    ).build(show_viewer=cfg.run.viewer)
    commands, episode_plan = plan_stacked_plate_rotation(plate_scene.layout)
    print("stacked_plate_physical_rotate_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=plate_scene.scene,
        manifest=plate_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        f"stacked_plate_physical_rotate_demo robot_home_ready hand={controller.hand_pos().tolist()}",
        flush=True,
    )

    status = {"phase": "setup", "disk": "-"}
    with recording_session_from_config(
        plate_scene.scene,
        plate_scene.cameras,
        cfg.recording,
        hud=_hud(plate_scene, status),
    ):
        run_demo(
            cfg,
            plate_scene,
            controller,
            status,
            episode_spec=episode_spec,
            episode_plan=episode_plan,
            commands=commands,
        )

    print_recording_saved(cfg.recording)


if __name__ == "__main__":
    main()
