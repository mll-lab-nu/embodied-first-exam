"""Wind a FEM rope around a post by physically grasping the plug on its free end.

Task book 2.4 (0 -> N turns): the post is fixed at both ends of the episode, so
its top is the only gateway that can change the winding number; the oracle keeps
the plug below it and orbits instead. Winding is signed -- running the mirrored
trajectory (`task.winding.direction=cw`) reaches -turns and fails, which is the
task's contrast pair: same grasp, same placement, opposite topology.

The gripper never touches the deformable body: it grasps the plug, and the rope
follows through the endpoint constraint. The plug starts seated in a spawn latch
(mesh-only, so it would otherwise fall through the board) and is handed to the
grasp attachment at gripper close.

Configuration is Hydra (`configs/rope_winding.yaml`).

    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true run.verbose=true
    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true run.probe=true run.max_waypoints=10
    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true task.winding.direction=cw
    python -m demos.routing.rope_winding_physical_handle_demo task.winding.turns=1
    python -m demos.routing.rope_winding_physical_handle_demo --cfg job
"""

from __future__ import annotations

import os
import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig, OmegaConf

from topogym.core import hydra_config_sources, save_resolved_config
from topogym.data import dataset_writer_or_null
from topogym.generation import EpisodeResult, build_cable_routing_episode_spec
from topogym.planning import (
    RopeWindingRouteCommand,
    WindingSpec,
    plan_rope_winding_route,
    post_center,
)
from topogym.primitives import (
    AttachmentManager,
    ConnectorLatch,
    HandleDragPrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
)
from topogym.supervision import (
    StepProbe,
    material_bins,
    post_contact,
    print_winding_verification,
    rope_twist_turns,
    stop_before_physics,
    winding_centerline,
    winding_number,
)
from topogym.supervision.cable_routing import rope_particles
from topogym.tasks import RopeWindingSceneBuilder
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


def _scaled_steps(
    value: int | float,
    speedup: float,
    *,
    minimum: int,
    slow_factor: float = 1.0,
) -> int:
    value_i = max(1, int(round(float(value) * max(1.0, float(slow_factor)))))
    speedup_f = max(1.0, float(speedup))
    if speedup_f <= 1.0:
        return value_i
    return max(int(minimum), int(round(value_i / speedup_f)))


def derive_config(cfg):
    """Config transforms this demo computes rather than chooses.

    Only the lite block: everything else this task needs is a plain setting and
    lives in the task config (the grasp contract on
    `rope.endpoint_handle`, the solid post, the plug z-offset).
    """

    if cfg.run.lite:
        lite = OmegaConf.to_container(cfg.task.rope.lite, resolve=True)
        cfg = OmegaConf.merge(cfg, {"task": {"rope": lite}})
    return cfg


def robot_contact_mode(cfg) -> str:
    """Whether the rope can see the gripper: 'off' or 'fingers'.

    Reads the same key the scene builder branches on
    (`tasks/routing/cable_routing.py` `_robot_material`), so the banner cannot
    claim one thing while the scene was built the other way.
    """

    return str(
        getattr(cfg.task.physical_handle, "robot_rope_contact", "off") or "off"
    )


def _hud(status: dict):
    def render_lines():
        return [
            "task=rope winding physical handle",
            f"phase={status.get('phase', 'setup')}",
            f"waypoint={status.get('waypoint', 0)}/{status.get('waypoints', 0)}",
            f"winding={status.get('winding', 0.0):+.2f}/{status.get('target_winding', 0.0):+.1f}",
        ]

    return render_lines


def _validate_physical_handle_contract(cfg, scene) -> tuple[str, ...]:
    handle_cfg = cfg.task.rope.endpoint_handle
    if not bool(getattr(handle_cfg, "enabled", False)):
        raise RuntimeError("Rope winding demo requires rope.endpoint_handle.enabled=true.")
    if str(getattr(handle_cfg, "attachment_mode", "none")) != "rigid_handle":
        raise RuntimeError(
            "Rope winding demo requires rope.endpoint_handle.attachment_mode=rigid_handle."
        )
    if bool(getattr(handle_cfg, "fixed", True)):
        raise RuntimeError(
            "Rope winding demo requires a dynamic free-end handle "
            "(rope.endpoint_handle.fixed=false)."
        )
    if not bool(getattr(getattr(handle_cfg, "connector", None), "enabled", False)):
        raise RuntimeError(
            "Rope winding demo requires the plug connector "
            "(rope.endpoint_handle.connector.enabled=true)."
        )
    if bool(getattr(handle_cfg, "collision", False)):
        raise RuntimeError(
            "Plug-connector free end must stay mesh-only (collision=false); "
            "the spawn latch / grasp attachment drives it kinematically."
        )
    if not bool(getattr(handle_cfg, "exclude_pbd_collision", False)):
        raise RuntimeError(
            "Rope winding demo requires exclude_pbd_collision=true so the "
            "attached endpoint nodes do not collide with their own plug."
        )
    spec = WindingSpec.from_config(cfg.task)
    if not bool(cfg.task.fixtures[spec.post].collision):
        raise RuntimeError(
            f"The winding post ({spec.post}) must be solid: "
            f"set task.fixtures.{spec.post}.collision=true."
        )
    contact_mode = robot_contact_mode(cfg)
    if contact_mode not in ("off", "fingers"):
        raise RuntimeError(
            "task.physical_handle.robot_rope_contact must be 'off' or 'fingers', "
            f"got {contact_mode!r}."
        )
    if contact_mode == "fingers" and not list(cfg.task.physical_handle.finger_links):
        raise RuntimeError(
            "robot_rope_contact='fingers' needs task.physical_handle.finger_links "
            "-- those are the links registered with IPC."
        )
    if scene.rope_handle.end_pin is None:
        raise RuntimeError("Rope winding demo requires a built free-end handle.")
    return (str(getattr(handle_cfg, "name", "winding_free_end_handle")),)


class RopeWindingProbe(StepProbe):
    """Per-step diagnostic; the winding number is the one that matters.

    Beyond the shared rope health fields (lowest node vs the table, spread, and
    per-step jump = blow-up detection), this samples the live signed winding
    number. A run that is winding shows it climbing one turn per orbit; a run
    whose rope is slipping off the post shows it stalling or falling back.
    """

    STALL_HAND_V = 0.0003
    FLYOUT_JUMP = 0.02

    def __init__(self, scene, controller, handle, spec, groups, status, *, every, surface_z):
        super().__init__(scene.scene, every=every)
        self.controller = controller
        self.winding_scene = scene
        self.handle = handle
        self.spec = spec
        self.groups = groups
        self.status = status
        self.surface_z = float(surface_z)
        self.post_xy = post_center(scene.layout, spec)
        self._last_hand = np.asarray(controller.hand_pos(), dtype=float)
        self._last_nodes = rope_particles(scene)

    def _sample(self) -> None:
        hand = np.asarray(self.controller.hand_pos(), dtype=float)
        hand_v = float(np.linalg.norm(hand - self._last_hand)) / self.every
        self._last_hand = hand
        nodes = rope_particles(self.winding_scene)
        min_z_above = float(nodes[:, 2].min()) - self.surface_z
        centroid = nodes.mean(axis=0)
        spread = float(np.max(np.linalg.norm(nodes - centroid, axis=1)))
        if self._last_nodes is not None and self._last_nodes.shape == nodes.shape:
            jump = float(np.max(np.linalg.norm(nodes - self._last_nodes, axis=1))) / self.every
        else:
            jump = float("nan")
        self._last_nodes = nodes
        turns = winding_number(
            winding_centerline(self.winding_scene, self.groups), self.post_xy
        )
        self.status["winding"] = turns
        twist = rope_twist_turns(self.winding_scene, self.groups)
        contact = post_contact(self.winding_scene, self.spec)
        flags = ""
        if hand_v < self.STALL_HAND_V:
            flags += " STALL"
        if min_z_above < 0.0 or (jump == jump and jump > self.FLYOUT_JUMP):
            flags += " FLYOUT?"
        handle_z = float(entity_pos(self.handle)[2]) - self.surface_z
        print(
            f"PROBE step={self.count:05d} phase={self.status.get('phase', '?')} "
            f"winding={turns:+.3f} twist={twist:+.2f} "
            f"hand_v={hand_v:.5f} handle_z_above={handle_z:+.4f} "
            f"rope_minz_above_surf={min_z_above:+.4f} rope_spread={spread:.4f} "
            f"rope_jump={jump:.4f} post_gap={contact['surface_gap']:+.4f} "
            f"post_contact={contact['contact_nodes']}{flags}",
            flush=True,
        )


def _print_probe_plan(labels, targets, steps) -> None:
    """Each segment's commanded per-step speed, as the 'is it slow?' baseline."""

    for index in range(1, len(targets)):
        distance = float(
            np.linalg.norm(np.asarray(targets[index]) - np.asarray(targets[index - 1]))
        )
        segment_steps = max(1, int(steps[index]))
        print(
            f"PROBE_PLAN phase={labels[index]} dist={distance:.4f} "
            f"steps={segment_steps} commanded_v={distance / segment_steps:.5f}",
            flush=True,
        )


def run_demo(
    cfg,
    scene,
    controller,
    *,
    episode_spec,
    episode_plan,
    route_command: RopeWindingRouteCommand,
    spec: WindingSpec,
    status,
    dataset_writer=None,
) -> EpisodeResult:
    physical = cfg.task.physical_handle
    manipulated = _validate_physical_handle_contract(cfg, scene)
    print_collision_il_contract(
        "rope_winding_physical_handle_demo",
        manipulated=manipulated,
        runtime_attachment=True,
        runtime_set_pose=True,
        success_checks=("lift_delta", "handle_follow_error", "winding_number", "connector_capture"),
    )
    contact_mode = robot_contact_mode(cfg)
    print(
        "rope_winding_physical_handle_demo rope_contract "
        f"rope_model={cfg.task.rope.model} rest_shape={cfg.task.rope.fem.rest_shape} "
        "endpoint_constraint=follow_band start_anchor=fixed_nodes "
        "handle_collision=False handle_needs_coup=False "
        f"robot_rope_contact={contact_mode} "
        f"ipc_links={list(cfg.task.physical_handle.finger_links) if contact_mode == 'fingers' else []} "
        "connector_latch=environment_socket_after_capture",
        flush=True,
    )
    handle = scene.rope_handle.end_pin
    configure_gripper_contact_friction(
        entities=[handle],
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.handle_friction),
        finger_friction=float(physical.finger_friction),
    )
    print(
        "rope_winding_physical_handle_demo plan "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"planned_waypoint_count={route_command.waypoint_count} "
        f"turns={route_command.turns} direction={route_command.direction} "
        f"target_winding={route_command.target_winding:+.1f} "
        f"planned_final_route_point="
        f"{[round(v, 4) for v in route_command.final_route_point_xyz]}",
        flush=True,
    )

    # Planner waypoints are already absolute plug targets (a helix cannot be
    # expressed as a planar route point plus a fixed lift), so nothing is added
    # to them here.
    targets = [np.asarray(waypoint.position, dtype=float) for waypoint in episode_plan.waypoints]
    target_labels = [str(waypoint.label) for waypoint in episode_plan.waypoints]
    target_steps = [int(waypoint.steps) for waypoint in episode_plan.waypoints]
    if cfg.run.max_waypoints is not None:
        limit = int(cfg.run.max_waypoints)
        targets = targets[:limit]
        target_labels = target_labels[:limit]
        target_steps = target_steps[:limit]
    speedup = max(1.0, float(cfg.run.viewer_speedup))
    slow_factor = max(1.0, float(cfg.run.slow_factor))
    target_steps = [
        _scaled_steps(steps, speedup, minimum=24, slow_factor=slow_factor)
        for steps in target_steps
    ]
    full_route = cfg.run.max_waypoints is None

    latch = (
        ConnectorLatch(
            scene=scene.scene,
            handle=handle,
            target_pos=targets[-1],
            capture_tolerance_xy=float(physical.latch_capture_tolerance_xy),
            capture_tolerance_z=float(physical.latch_capture_tolerance_z),
            capture_max_tilt_deg=float(physical.latch_capture_max_tilt_deg),
            auto_capture=bool(getattr(physical, "latch_auto_capture", True)),
        )
        if full_route
        else None
    )
    # SOCKETED at spawn: the mesh-only plug would fall through the board
    # otherwise; handed to the grasp attachment atomically at on_close.
    spawn_latch = ConnectorLatch(
        scene=scene.scene,
        handle=handle,
        target_pos=entity_pos(handle),
        capture_tolerance_xy=0.010,
        capture_tolerance_z=0.020,
        capture_max_tilt_deg=30.0,
        auto_capture=False,
    )
    if not spawn_latch.try_engage():
        raise RuntimeError("Rope winding free-end plug failed to seat at spawn.")
    grasp_attachment: list = []

    primitive = HandleDragPrimitive(
        approach_z=scene.layout.world_z(physical.approach_z),
        lift_delta=float(physical.lift_delta),
        move_steps=_scaled_steps(physical.move_steps, speedup, minimum=24, slow_factor=slow_factor),
        gripper_steps=_scaled_steps(
            physical.gripper_steps, speedup, minimum=15, slow_factor=slow_factor
        ),
        grasp_qpos=float(physical.grasp_qpos),
        close_hold_steps=_scaled_steps(
            physical.close_hold_steps, speedup, minimum=20, slow_factor=slow_factor
        ),
        motion_settle_steps=_scaled_steps(
            physical.motion_settle_steps, speedup, minimum=4, slow_factor=slow_factor
        ),
        min_lift_delta=float(physical.min_lift_delta),
        max_handle_error=float(physical.max_handle_error),
        max_segment_follow_error=float(physical.max_segment_follow_error),
        # Transport is attachment-assisted, so hand-vs-commanded waypoint lag is
        # a controller property, not a grasp failure. Success gates stay: the
        # winding number, the C latch, and the final connector error.
        max_segment_target_error=(
            None
            if cfg.run.allow_target_lag
            else float(physical.max_segment_target_error)
        ),
        target_error_abort_fraction=float(physical.target_error_abort_fraction),
        early_complete_segment_labels=tuple(
            str(value) for value in (_list(physical.early_complete_segments) or [])
        ),
        early_complete_target_error=float(physical.early_complete_target_error),
        # Dead signal in plug mode: the attachment pins the handle to the hand,
        # so a rope snag can no longer drag the handle downward.
        max_downward_follow_error_z=None,
        release_hold_steps=_scaled_steps(
            physical.release_hold_steps, speedup, minimum=10, slow_factor=slow_factor
        ),
        recover_on_segment_failure=False,
        # Plug mode manages its own on_close attachment handoff; the primitive's
        # post-lift attachment must stay off to avoid doubling.
        runtime_attachment=False,
        motion_profile=str(physical.motion_profile),
        command_space_segments=True,
        verbose=cfg.run.verbose,
    )
    ee_quat = ee_quat_for_yaw(controller.default_ee_quat, float(physical.grasp_yaw))
    status.update(
        {
            "phase": "settle",
            "waypoint": 0,
            "waypoints": len(targets),
            "winding": 0.0,
            "target_winding": route_command.target_winding,
        }
    )
    trace: list[np.ndarray] = []

    # Material grouping of the rope's nodes: computed once, valid all episode.
    groups = material_bins(scene, bins=int(cfg.task.success.centerline_bins))
    print(
        "rope_winding_physical_handle_demo setup "
        f"waypoints={len(targets)} groups={len(groups)} "
        f"grasp_qpos={float(physical.grasp_qpos):.4f} "
        f"grasp_yaw={float(physical.grasp_yaw):.4f} "
        f"wind_radius={spec.wind_radius:.3f} wind_z_start={spec.wind_z_start:.3f} "
        f"climb_per_turn={spec.climb_per_turn:.3f} "
        f"follow_swivel={bool(getattr(cfg.task.rope.fem, 'follow_swivel', False))} "
        f"robot_rope_friction={float(physical.robot_rope_friction):.3f} "
        f"latch_mode={latch.step_hook_mode if latch is not None else 'disabled'} "
        f"viewer_speedup={speedup:.2f} slow_factor={slow_factor:.2f} "
        f"allow_target_lag={bool(cfg.run.allow_target_lag)} "
        f"segment_steps={target_steps}",
        flush=True,
    )

    def on_segment_start(index, total, label, target):
        status["phase"] = label
        status["waypoint"] = index
        print(
            "rope_winding_physical_handle_demo waypoint_start "
            f"index={index}/{total} phase={label} target={target.tolist()}",
            flush=True,
        )

    def on_segment_complete(index, total, label, target, handle_pos, follow_error, target_error):
        del target
        print(
            "rope_winding_physical_handle_demo waypoint_complete "
            f"index={index}/{total} phase={label} handle={handle_pos.tolist()} "
            f"follow_error={follow_error:.4f} target_error={target_error:.4f}",
            flush=True,
        )
        # One winding report per completed turn: the count should step by
        # exactly one, which is what separates winding from dragging the rope
        # around without ever catching the post.
        if label.startswith("wind_t") and label.endswith(f"{spec.arc_points_per_turn:02d}"):
            turns = winding_number(winding_centerline(scene, groups), post_center(scene.layout, spec))
            print(
                f"rope_winding_physical_handle_demo turn_complete phase={label} "
                f"winding_number={turns:+.3f}",
                flush=True,
            )
        # Divergence guard: the rope sinking into the post, or the whole rope
        # piling onto it, are the two ways a wrap goes wrong before it blows up.
        contact = post_contact(scene, spec)
        gap = float(contact["surface_gap"])
        nodes_touching = int(contact["contact_nodes"])
        if gap < float(physical.safety_min_gap):
            reason = f"post_contact_safety_abort: phase={label} surface_gap={gap:.4f}"
            print(f"rope_winding_physical_handle_demo safety_abort reason={reason}", flush=True)
            return reason
        if nodes_touching > int(physical.safety_max_contact_nodes):
            reason = (
                f"post_contact_safety_abort: phase={label} contact_nodes={nodes_touching}"
            )
            print(f"rope_winding_physical_handle_demo safety_abort reason={reason}", flush=True)
            return reason
        return None

    attachment_manager = AttachmentManager(scene.scene)

    def engage_grasp_attachment():
        # GRASPED: fingers closed around the plug column -- hand the plug from
        # its spawn latch to a hand attachment in the same step.
        offset = entity_pos(handle) - np.asarray(controller.hand_pos(), dtype=float)
        attachment = attachment_manager.create(
            entity=handle, parent_pos_fn=controller.hand_pos, offset=offset
        )
        spawn_latch.active = False
        attachment.attach()
        grasp_attachment.append(attachment)

    def release_grasp_attachment():
        attachment = grasp_attachment.pop()
        attachment.release(sync=False)
        attachment_manager.attachments.remove(attachment)

    def engage_connector_latch(handle_pos, final_target):
        del handle_pos, final_target
        if latch is None:
            return False
        status["phase"] = "connector_latch"
        engaged = latch.try_engage()
        if engaged and grasp_attachment:
            release_grasp_attachment()
        print(
            "rope_winding_physical_handle_demo connector_latch "
            f"engaged={engaged} xy_error={latch.last_xy_error:.4f} "
            f"z_error={latch.last_z_error:.4f} tilt_deg={latch.last_tilt_deg:.1f} "
            f"capture_checks={latch.capture_checks}",
            flush=True,
        )
        return bool(engaged)

    if cfg.run.probe:
        _print_probe_plan(target_labels, targets, target_steps)
    probe = None
    if stop_before_physics(cfg, scene.scene, "rope_winding_physical_handle_demo"):
        raise SystemExit(0)

    with recording_session_from_config(scene.scene, scene.cameras, cfg.recording, hud=_hud(status)):
        with attachment_manager:
            controller.step(
                max(
                    0,
                    _scaled_steps(
                        cfg.run.settle_steps, speedup, minimum=5, slow_factor=slow_factor
                    ),
                )
            )
            status["phase"] = "wind_route"
            if cfg.run.probe:
                probe = RopeWindingProbe(
                    scene,
                    controller,
                    handle,
                    spec,
                    groups,
                    status,
                    every=cfg.run.probe_every,
                    surface_z=scene.layout.world_z(0.0),
                )
            result = primitive.run(
                controller,
                handle=handle,
                target_centers=targets,
                target_steps=target_steps,
                segment_labels=target_labels,
                on_segment_start=on_segment_start,
                on_segment_complete=on_segment_complete,
                on_close=engage_grasp_attachment,
                before_release=engage_connector_latch if full_route else None,
                ee_quat=ee_quat,
                trace=trace,
                attachment_manager=attachment_manager,
            )
            if grasp_attachment:
                # The plug is still in hand: either the route was cut short by
                # `run.max_waypoints` (staged verification) or it aborted. Both
                # need the plug frozen where the hand left it -- it is mesh-only,
                # so releasing it without a latch drops it through the board --
                # but only one of them is a failure, and the log has to say which.
                release_grasp_attachment()
                spawn_latch.target_pos = entity_pos(handle)
                spawn_latch.active = True
                spawn_latch.sync()
                print(
                    "rope_winding_physical_handle_demo "
                    f"{'staged_hold' if result.success else 'abort_hold'} "
                    "plug frozen at hand pose (not returned to spawn)",
                    flush=True,
                )
            if result.success:
                status["phase"] = "route_settle"
                controller.step(
                    max(
                        0,
                        _scaled_steps(
                            physical.route_settle_steps,
                            speedup,
                            minimum=10,
                            slow_factor=slow_factor,
                        ),
                    )
                )
                status["phase"] = "verify"
                winding_success = (
                    print_winding_verification(scene, spec, groups) if full_route else False
                )
            else:
                status["phase"] = "route_failed"
                winding_success = False
                print(
                    "rope_winding_physical_handle_demo winding_verify_skipped "
                    f"reason={result.failure_reason}",
                    flush=True,
                )
            settled_handle_pos = entity_pos(handle)
            if probe is not None:
                probe.uninstall()

    # Exclude reset_home (a set_dofs_position teleport) from the dataset: it is
    # post-task cleanup, not demonstration.
    if dataset_writer is not None:
        dataset_writer.stop_capture()
    if result.success:
        controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    else:
        print(
            "rope_winding_physical_handle_demo reset_home_skipped "
            "reason=wind_route_failed_before_safe_settle",
            flush=True,
        )
    connector_error_xy = float(np.linalg.norm(settled_handle_pos[:2] - targets[-1][:2]))
    endpoint_success = connector_error_xy <= float(physical.connector_tolerance_xy)
    latch_engaged = bool(latch is not None and latch.active)
    success = bool(
        result.success and winding_success and endpoint_success and latch_engaged and full_route
    )
    metrics = {
        "task_success": bool(success),
        "physical_success": bool(result.success),
        "winding_success": bool(winding_success),
        "full_route": bool(full_route),
        "endpoint_success": bool(endpoint_success),
        "latch_engaged": bool(latch_engaged),
        "connector_error_xy": float(connector_error_xy),
        "turns": int(spec.turns),
        "direction": str(spec.direction),
        "completed_waypoints": len(result.completed_segments),
        "planned_waypoints": len(targets),
    }
    episode_result = (
        EpisodeResult.ok(episode_spec.key, metrics=metrics, export_ready=True)
        if success
        else EpisodeResult.failed(
            episode_spec.key,
            result.failure_reason or "rope_not_wound",
            metrics=metrics,
            stable_ready=False,
        )
    )
    print(
        "rope_winding_physical_handle_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"task_success={success} physical_success={result.success} "
        f"stable_ready={episode_result.stable_ready} export_ready={episode_result.export_ready} "
        f"winding_success={winding_success} full_route={full_route} "
        f"endpoint_success={endpoint_success} latch_engaged={latch_engaged} "
        f"connector_error_xy={connector_error_xy:.4f} "
        f"turns={spec.turns} direction={spec.direction} "
        f"completed_waypoints={len(result.completed_segments)}/{len(targets)} "
        f"grasped={result.grasped} failure_reason={result.failure_reason}",
        flush=True,
    )
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="rope_winding")
def main(cfg: DictConfig) -> None:
    if cfg.run.max_waypoints is not None and cfg.run.max_waypoints <= 0:
        raise SystemExit("run.max_waypoints must be positive.")
    if float(cfg.run.viewer_speedup) <= 0.0:
        raise SystemExit("run.viewer_speedup must be positive.")
    if float(cfg.run.slow_factor) <= 0.0:
        raise SystemExit("run.slow_factor must be positive.")
    cfg = derive_config(cfg)
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"rope_winding_config -> {resolved}", flush=True)
    spec = WindingSpec.from_config(cfg.task)

    # Which yaml each config group resolved to, recorded as episode provenance.
    sources = hydra_config_sources()
    episode_spec = build_cable_routing_episode_spec(
        cfg,
        seed=cfg.run.seed,
        common_config=sources.get("common"),
        env_config=sources.get("env"),
        robot_config=sources.get("robot_control"),
        task_config=sources.get("task"),
        variant_id=cfg.run.variant_id,
        route_mode="initial",
    )
    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if cfg.run.viewer and not has_display:
        raise SystemExit("No graphical display detected.")
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    print(
        "rope_winding_physical_handle_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer} lite={cfg.run.lite} "
        f"turns={spec.turns} direction={spec.direction} "
        f"target_winding={spec.target_winding:+.1f}",
        flush=True,
    )
    scene = RopeWindingSceneBuilder(
        cfg.env, cfg.task, cfg.robot_control, route_mode="initial"
    ).build(show_viewer=cfg.run.viewer, include_robot=True)
    route_command, episode_plan = plan_rope_winding_route(scene.layout)
    print("rope_winding_physical_handle_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        "rope_winding_physical_handle_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )
    # `status` lives here (not in run_demo) so the dataset writer's subgoal
    # labels can read the live phase during the run.
    status: dict = {}
    dataset_writer_cm = dataset_writer_or_null(
        cfg.run.record_dataset,
        scene=scene.scene,
        cameras=scene.cameras,
        controller=controller,
        spec=episode_spec,
        plan=episode_plan,
        task_goal=(
            f"Wind the rope {spec.turns} turns {spec.direction} around the post "
            "and plug its end into the target port."
        ),
        every_n_steps=cfg.run.dataset_every_n_steps,
        subgoal_label_fn=lambda: str(status.get("phase", "setup")),
    )
    with dataset_writer_cm as dataset_writer:
        episode_result = run_demo(
            cfg,
            scene,
            controller,
            episode_spec=episode_spec,
            episode_plan=episode_plan,
            route_command=route_command,
            spec=spec,
            status=status,
            dataset_writer=dataset_writer,
        )
        if dataset_writer is not None:
            dataset_writer.finalize(episode_result)
            print(f"saved dataset -> {cfg.run.record_dataset}", flush=True)
    print_recording_saved(cfg.recording)
    # Both holds are for looking at the scene, so both are gated on the viewer:
    # without one there is nothing to hold open and the loop would just spin
    # forever -- which is what a headless recording run would have done.
    if cfg.run.viewer and cfg.run.keep_open_no_step:
        print(
            "rope_winding_physical_handle_demo viewer_hold frozen; press Ctrl+C to exit",
            flush=True,
        )
        while True:
            time.sleep(0.05)
    hold_open = bool(cfg.run.viewer and cfg.run.keep_open)
    if hold_open:
        print("rope_winding_physical_handle_demo viewer_hold; press Ctrl+C to exit", flush=True)
    while hold_open:
        try:
            scene.scene.step()
        except gs.GenesisException as exc:
            if "Viewer closed" in str(exc):
                print("rope_winding_physical_handle_demo viewer_closed; exiting", flush=True)
                break
            raise


if __name__ == "__main__":
    main()
