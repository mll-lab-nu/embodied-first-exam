"""Route a PBD/FEM cable by physically grasping the rigid plug on its free end.

The gripper never touches the deformable body: it grasps the plug, and the rope
follows through the endpoint constraint. The plug starts seated in a spawn latch
(it is mesh-only, so it would otherwise fall through the board) and is handed to
the grasp attachment at gripper close.

Configuration is Hydra (`configs/cable_routing.yaml`).

    python -m demos.routing.cable_routing_physical_handle_demo run.viewer=true run.verbose=true
    python -m demos.routing.cable_routing_physical_handle_demo run.max_waypoints=4 run.viewer=true
    python -m demos.routing.cable_routing_physical_handle_demo run.probe=true run.slow_factor=2.0
    python -m demos.routing.cable_routing_physical_handle_demo recording=default recording.path=runs/cable.mp4
    python -m demos.routing.cable_routing_physical_handle_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig, OmegaConf

from topogym.core import hydra_config_sources, save_resolved_config
from topogym.data import dataset_writer_or_null
from topogym.generation import EpisodeResult, build_cable_routing_episode_spec
from topogym.planning import CableRoutingRouteCommand, plan_cable_routing_endpoint_route
from topogym.primitives import (
    AttachmentManager,
    ConnectorLatch,
    HandleDragPrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
)
from topogym.tasks import CableRoutingSceneBuilder
from topogym.supervision import (
    StepProbe,
    peg_signature_items,
    polyline_length,
    print_phase_routing_metrics,
    print_routing_verification,
    rope_wrap_metrics,
    stop_before_physics,
)
from topogym.supervision.cable_routing import rope_particles
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
    """Config transforms this demo needs that are computed, not chosen.

    What stays here is the demo's contract: the three fixture-collision overrides
    (see the comment on C) and the endpoint handle's attachment mode. The handle
    z-offset it also overrides comes from `task.physical_handle`, so it would
    duplicate a value written a few lines away if left as a literal. Values that
    are plain settings live in the task config instead:
    `rope.endpoint_handle.friction` / `.rho` interpolate `physical_handle`, and
    `run.lite` selects the `rope.lite` block.
    """

    physical = cfg.task.physical_handle
    handle_connector_enabled = bool(
        getattr(getattr(cfg.task.rope.endpoint_handle, "connector", None), "enabled", False)
    )
    cfg = OmegaConf.merge(
        cfg,
        {
            "task": {
                "fixtures": {
                    "P1": {"collision": True},
                    "P2": {"collision": True},
                    # Probe finding (2026-07-08): the flyout was the rope endpoint
                    # deep-penetrating the raised socket walls at green_exit_pre_C
                    # (rope_jump=17m, p2_contact=0). The connector is the target we
                    # place the cable INTO, so it must not violently reject the rope:
                    # keep the socket visible but non-colliding (latch capture is
                    # geometric, so it still works). Override task.fixtures.C.collision=true
                    # to A/B test.
                    "C": {"collision": False},
                },
                "rope": {
                    "endpoint_handle": {
                        "z_offset": float(physical.z_offset),
                        "attachment_mode": "rigid_handle",
                        "fixed": False,
                        # Plug-connector mode: mesh-only (spawn latch / grasp
                        # attachment drives it); box fallback keeps friction contact.
                        "collision": not handle_connector_enabled,
                        "exclude_pbd_collision": True,
                    }
                },
            }
        },
    )
    if "cameras" in cfg.task:
        cfg = OmegaConf.merge(cfg, {"env": {"cameras": cfg.task.cameras}})
    if cfg.run.lite:
        lite = OmegaConf.to_container(cfg.task.rope.lite, resolve=True)
        cfg = OmegaConf.merge(cfg, {"task": {"rope": lite}})
    return cfg


def _hud(status: dict):
    def render_lines():
        return [
            "task=cable routing physical handle",
            f"phase={status.get('phase', 'setup')}",
            f"waypoint={status.get('waypoint', 0)}/{status.get('waypoints', 0)}",
        ]

    return render_lines


def _validate_physical_handle_contract(cfg, cable_scene) -> tuple[str, ...]:
    handle_cfg = cfg.task.rope.endpoint_handle
    if not bool(getattr(handle_cfg, "enabled", False)):
        raise RuntimeError(
            "Cable physical demo requires rope.endpoint_handle.enabled=true."
        )
    attachment_mode = str(getattr(handle_cfg, "attachment_mode", "none"))
    if attachment_mode != "rigid_handle":
        raise RuntimeError(
            "Cable physical demo requires "
            "rope.endpoint_handle.attachment_mode=rigid_handle."
        )
    if bool(getattr(handle_cfg, "fixed", True)):
        raise RuntimeError(
            "Cable physical demo requires a dynamic free-end handle "
            "(rope.endpoint_handle.fixed=false)."
        )
    connector_enabled = bool(
        getattr(getattr(handle_cfg, "connector", None), "enabled", False)
    )
    if connector_enabled:
        if bool(getattr(handle_cfg, "collision", False)):
            raise RuntimeError(
                "Plug-connector free end must stay mesh-only (collision=false); "
                "the spawn latch / grasp attachment drives it kinematically."
            )
    elif not bool(getattr(handle_cfg, "collision", False)):
        raise RuntimeError(
            "Cable physical demo requires endpoint handle collision=true."
        )
    if not bool(getattr(handle_cfg, "exclude_pbd_collision", False)):
        raise RuntimeError(
            "Cable physical demo requires exclude_pbd_collision=true so the "
            "attached endpoint particles do not collide with their own handle."
        )
    handle = cable_scene.rope_handle.end_pin
    if handle is None:
        raise RuntimeError("Cable physical demo requires a built free-end handle.")
    return (str(getattr(handle_cfg, "name", "cable_free_end_handle")),)


class CableRoutingProbe(StepProbe):
    """Per-scene-step diagnostic for the pause (#2) and placement flyout (#4).

    Machinery from `supervision.StepProbe`; the fields below are cable-specific.

    Wraps ``scene.step`` and samples every ``every`` physics steps:
    - ``hand_v``: actual hand displacement per step (m/step). Near 0 = a genuine
      stall (e.g. a direction-reversal cusp); small-but-steady = the segment is
      merely commanded slow. Compare against the PROBE_PLAN commanded_v table.
    - ``rope_minz_above_surf``: lowest rope particle relative to the table top
      (< 0 means the rope dipped into the table -> placement-flyout hypothesis 1).
    - ``rope_spread`` / ``rope_jump``: rope spread and max per-step particle jump;
      a sudden jump is the flyout blow-up itself.
    - ``p2_gap`` / ``p2_contact``: P2 wrap penetration / contact count
      (-> placement-flyout hypothesis 2, over-tense pole contact).
    """

    STALL_HAND_V = 0.0003
    FLYOUT_JUMP = 0.02

    def __init__(self, scene, controller, cable_scene, handle, status, *, every, surface_z):
        super().__init__(scene, every=every)
        self.controller = controller
        self.cable_scene = cable_scene
        self.handle = handle
        self.status = status
        self.surface_z = float(surface_z)
        self._last_hand = np.asarray(controller.hand_pos(), dtype=float)
        self._last_particles = rope_particles(cable_scene)

    def _sample(self) -> None:
        hand = np.asarray(self.controller.hand_pos(), dtype=float)
        hand_v = float(np.linalg.norm(hand - self._last_hand)) / self.every
        self._last_hand = hand
        parts = rope_particles(self.cable_scene)
        min_z_above = float(parts[:, 2].min()) - self.surface_z
        centroid = parts.mean(axis=0)
        spread = float(np.max(np.linalg.norm(parts - centroid, axis=1)))
        if self._last_particles is not None and self._last_particles.shape == parts.shape:
            jump = float(np.max(np.linalg.norm(parts - self._last_particles, axis=1))) / self.every
        else:
            jump = float("nan")
        self._last_particles = parts
        try:
            metrics = rope_wrap_metrics(self.cable_scene, "P2", "right")
            p2_gap = float(metrics["particle_surface_gap"])
            p2_contact = int(metrics["contact_particles"])
        except Exception:
            p2_gap, p2_contact = float("nan"), -1
        flags = ""
        if hand_v < self.STALL_HAND_V:
            flags += " STALL"
        if min_z_above < 0.0 or (jump == jump and jump > self.FLYOUT_JUMP):
            flags += " FLYOUT?"
        handle_z = float(entity_pos(self.handle)[2]) - self.surface_z
        print(
            f"PROBE step={self.count:05d} phase={self.status.get('phase', '?')} "
            f"hand_v={hand_v:.5f} handle_z_above={handle_z:+.4f} "
            f"rope_minz_above_surf={min_z_above:+.4f} rope_spread={spread:.4f} "
            f"rope_jump={jump:.4f} p2_gap={p2_gap:+.4f} p2_contact={p2_contact}{flags}",
            flush=True,
        )


def _print_probe_plan(target_labels, targets, target_steps) -> None:
    """Print each segment's commanded per-step speed (the 'inherently slow?' baseline)."""

    for index in range(1, len(targets)):
        dist = float(np.linalg.norm(np.asarray(targets[index]) - np.asarray(targets[index - 1])))
        steps = max(1, int(target_steps[index]))
        print(
            f"PROBE_PLAN phase={target_labels[index]} dist={dist:.4f} "
            f"steps={steps} commanded_v={dist / steps:.5f}",
            flush=True,
        )


def _run_release_end_probe(cable_scene, controller, steps, *, sample_every) -> None:
    """Kirchhoff-rod discriminator: free the plug-side band, watch the coils.

    With both ends orientation-clamped and IPC forbidding self-penetration,
    Lk = Tw + Wr is conserved: any twist stored at spawn or injected during
    transport can only live as internal twist or convert into coils (writhe).
    Freeing one end opens the topology. Coils unwinding while the freed cross
    section spins (cumulative |spin| well past 360 deg) = the coils were
    twist-fed; shape persisting = rest-configuration / stiffness driven.
    """

    backend = cable_scene.rope_backend
    rope_entity = cable_scene.rope_handle.entity
    handles = getattr(backend, "_follow_handles", {}).get(str(rope_entity.uid))
    if not handles or len(handles) < 2:
        print("RELEASE_PROBE skipped reason=no_fem_end_follow_band", flush=True)
        return

    def _rodrigues(vec, axis, angle):
        return (
            vec * np.cos(angle)
            + np.cross(axis, vec) * np.sin(angle)
            + axis * float(np.dot(axis, vec)) * (1.0 - np.cos(angle))
        )

    end_band = handles[-1]  # bands are declared start-terminal first, plug last
    band = np.asarray(end_band.verts, dtype=int)

    def _frame(prev=None):
        # In-plane reference is parallel-transported between samples (same
        # minimal-rotation trick as the tube mesher) so axis drift does not
        # read as spin.
        nodes = backend.nodes(rope_entity)
        pts = nodes[band]
        center = pts.mean(axis=0)
        dist = np.linalg.norm(nodes - center[None, :], axis=1)
        shell = np.flatnonzero((dist > 0.012) & (dist < 0.045))
        inward = (
            nodes[shell].mean(axis=0)
            if len(shell)
            else center - np.array([0.0, 0.0, 1e-6])
        )
        axis = center - inward
        axis = axis / max(float(np.linalg.norm(axis)), 1e-9)
        if prev is None:
            u = np.cross(axis, np.array([0.0, 0.0, 1.0]))
            if np.linalg.norm(u) < 1e-6:
                u = np.cross(axis, np.array([1.0, 0.0, 0.0]))
        else:
            prev_axis, prev_u = prev
            pivot = np.cross(prev_axis, axis)
            sin = float(np.linalg.norm(pivot))
            cos = float(np.clip(np.dot(prev_axis, axis), -1.0, 1.0))
            u = (
                _rodrigues(prev_u, pivot / sin, np.arctan2(sin, cos))
                if sin > 1e-9
                else prev_u
            )
        u = u - axis * float(np.dot(u, axis))
        u = u / max(float(np.linalg.norm(u)), 1e-9)
        binormal = np.cross(axis, u)
        rel = pts - center[None, :]
        return axis, u, np.arctan2(rel @ binormal, rel @ u), center

    axis, u, angles, center = _frame()
    end_band.release()
    print(
        f"RELEASE_PROBE released plug-side band verts={len(band)} "
        f"center={np.round(center, 4).tolist()} steps={steps}",
        flush=True,
    )
    spin_deg = 0.0
    done = 0
    while done < steps:
        chunk = min(int(sample_every), steps - done)
        controller.step(chunk)
        done += chunk
        axis, u, new_angles, center = _frame((axis, u))
        delta = np.angle(np.mean(np.exp(1j * (new_angles - angles))))
        angles = new_angles
        spin_deg += float(np.degrees(delta))
        print(
            f"RELEASE_PROBE step={done:05d} spin_deg={spin_deg:+.1f} "
            f"band_center={np.round(center, 4).tolist()}",
            flush=True,
        )
    turns = spin_deg / 360.0
    print(
        f"RELEASE_PROBE done cumulative_spin_deg={spin_deg:+.1f} "
        f"(~{turns:+.2f} turns) verdict_hint="
        f"{'TWIST_FED' if abs(turns) >= 1.0 else 'REST_SHAPE_OR_STIFFNESS'}",
        flush=True,
    )


def run_demo(
    cfg,
    cable_scene,
    controller,
    *,
    episode_spec,
    episode_plan,
    route_command: CableRoutingRouteCommand,
    status,
    dataset_writer=None,
) -> EpisodeResult:
    physical = cfg.task.physical_handle
    runtime_gripper_attachment = bool(
        getattr(physical, "runtime_gripper_attachment", False)
    )
    handle_connector_enabled = bool(
        getattr(getattr(cfg.task.rope.endpoint_handle, "connector", None), "enabled", False)
    )
    if handle_connector_enabled:
        # Plug mode manages its own on_close attachment handoff; the
        # primitive's post-lift attachment must stay off to avoid doubling.
        runtime_gripper_attachment = False
    manipulated = _validate_physical_handle_contract(cfg, cable_scene)
    print_collision_il_contract(
        "cable_routing_physical_handle_demo",
        manipulated=manipulated,
        runtime_attachment=runtime_gripper_attachment or handle_connector_enabled,
        runtime_set_pose=handle_connector_enabled,
        success_checks=(
            "lift_delta",
            "handle_follow_error",
            "routing_signature",
            "connector_capture",
        ),
    )
    print(
        "cable_routing_physical_handle_demo rope_contract "
        f"rope_model={cfg.task.rope.model} endpoint_constraint=fix_particles_to_link "
        "start_anchor=fixed_particles runtime_set_particles_pos=False "
        "handle_collision=True handle_needs_coup=False "
        "connector_latch=environment_socket_after_capture "
        f"gripper_transport_attachment={runtime_gripper_attachment}",
        flush=True,
    )
    handle = cable_scene.rope_handle.end_pin
    configure_gripper_contact_friction(
        entities=[handle],
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.handle_friction),
        finger_friction=float(physical.finger_friction),
    )
    print(
        "cable_routing_physical_handle_demo plan "
        f"episode_id={episode_spec.stable_id()} plan_id={episode_plan.plan_id} "
        f"planned_waypoint_count={route_command.waypoint_count} "
        f"planned_final_route_point="
        f"{[round(v, 4) for v in route_command.final_route_point_xyz]} "
        f"target_signature={route_command.target_signature}",
        flush=True,
    )
    targets = []
    target_steps = []
    target_labels = []
    last_lifted_index = None
    z_offset = float(cfg.task.rope.endpoint_handle.z_offset)
    segment_steps = getattr(physical, "segment_steps", {})
    for waypoint in episode_plan.waypoints:
        label = str(waypoint.label)
        route_point = waypoint.position
        steps = waypoint.steps
        lifted = waypoint.lifted
        center = np.asarray(route_point, dtype=float).copy()
        center[2] += z_offset
        if lifted:
            center[2] += float(physical.wrap_z_lift)
        targets.append(center)
        if lifted:
            last_lifted_index = len(targets) - 1
        configured_steps = segment_steps.get(label, None)
        target_steps.append(
            int(
                configured_steps
                if configured_steps is not None
                else steps if steps is not None else physical.move_steps
            )
        )
        target_labels.append(label)
    if cfg.run.max_waypoints is not None:
        targets = targets[: int(cfg.run.max_waypoints)]
        target_steps = target_steps[: int(cfg.run.max_waypoints)]
        target_labels = target_labels[: int(cfg.run.max_waypoints)]
    speedup = max(1.0, float(cfg.run.viewer_speedup))
    slow_factor = max(1.0, float(cfg.run.slow_factor))
    target_steps = [
        _scaled_steps(steps, speedup, minimum=24, slow_factor=slow_factor)
        for steps in target_steps
    ]
    full_route = cfg.run.max_waypoints is None
    if handle_connector_enabled and full_route and targets:
        # Elevated final approach + vertical insertion: with the flush-port
        # z_offset the raw route would slide the plug at near-board height to
        # C. Instead, after the last wrap-lifted waypoint the plug glides at
        # hover height (XY of the arm-safety-validated route unchanged)
        # straight to above the target port, then plugs straight down.
        seat_target = targets[-1].copy()
        hover_z = float(seat_target[2]) + float(
            getattr(physical, "insert_hover_lift", 0.035)
        )
        tail_start = (
            last_lifted_index + 1
            if last_lifted_index is not None
            else len(targets) - 1
        )
        for index in range(max(0, tail_start), len(targets)):
            elevated = targets[index].copy()
            elevated[2] = hover_z
            targets[index] = elevated
        target_labels[-1] = f"{target_labels[-1]}_hover"
        targets.append(seat_target)
        target_labels.append("insert_at_C")
        target_steps.append(
            _scaled_steps(
                int(physical.move_steps),
                speedup,
                minimum=24,
                slow_factor=slow_factor,
            )
        )
    early_complete_segments = tuple(
        str(value)
        for value in (_list(getattr(physical, "early_complete_segments", [])) or [])
    )
    early_complete_target_error = getattr(
        physical, "early_complete_target_error", None
    )
    max_segment_target_error = (
        None
        # Plug mode: transport is attachment-assisted, so hand-vs-commanded
        # waypoint lag is a controller property, not a grasp failure (diag
        # 2026-07-12: abort at smooth_005 with target_error=0.0716 while
        # handle_follow_error=0.007). Success gates stay: C latch + final
        # connector_error_xy.
        if cfg.run.allow_target_lag
        or handle_connector_enabled
        or getattr(physical, "max_segment_target_error", None) is None
        else float(physical.max_segment_target_error)
    )
    latch = (
        ConnectorLatch(
            scene=cable_scene.scene,
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
    spawn_latch = None
    grasp_attachment: list = []
    if handle_connector_enabled:
        # SOCKETED-at-spawn (untangle lifecycle): the mesh-only plug would
        # fall through the board otherwise; handed to the grasp attachment
        # atomically at on_close.
        spawn_latch = ConnectorLatch(
            scene=cable_scene.scene,
            handle=handle,
            target_pos=entity_pos(handle),
            capture_tolerance_xy=0.010,
            capture_tolerance_z=0.020,
            capture_max_tilt_deg=30.0,
            auto_capture=False,
        )
        if not spawn_latch.try_engage():
            raise RuntimeError("Cable free-end plug failed to seat at spawn.")

    primitive = HandleDragPrimitive(
        approach_z=cable_scene.layout.world_z(physical.approach_z),
        lift_delta=float(physical.lift_delta),
        move_steps=_scaled_steps(
            physical.move_steps,
            speedup,
            minimum=24,
            slow_factor=slow_factor,
        ),
        gripper_steps=_scaled_steps(
            physical.gripper_steps,
            speedup,
            minimum=15,
            slow_factor=slow_factor,
        ),
        grasp_qpos=float(physical.grasp_qpos),
        close_hold_steps=_scaled_steps(
            physical.close_hold_steps,
            speedup,
            minimum=20,
            slow_factor=slow_factor,
        ),
        motion_settle_steps=_scaled_steps(
            physical.motion_settle_steps,
            speedup,
            minimum=4,
            slow_factor=slow_factor,
        ),
        min_lift_delta=float(physical.min_lift_delta),
        max_handle_error=float(physical.max_handle_error),
        max_segment_follow_error=float(physical.max_segment_follow_error),
        max_segment_target_error=max_segment_target_error,
        target_error_abort_fraction=float(
            getattr(physical, "target_error_abort_fraction", 0.75)
        ),
        early_complete_segment_labels=early_complete_segments,
        early_complete_target_error=(
            None
            if early_complete_target_error is None
            else float(early_complete_target_error)
        ),
        max_downward_follow_error_z=(
            None
            # Dead signal in plug mode: the attachment pins the handle to the
            # hand, so a rope snag can no longer drag the handle downward.
            if handle_connector_enabled
            or getattr(physical, "max_downward_follow_error_z", None) is None
            else float(physical.max_downward_follow_error_z)
        ),
        release_hold_steps=_scaled_steps(
            physical.release_hold_steps,
            speedup,
            minimum=10,
            slow_factor=slow_factor,
        ),
        recover_on_segment_failure=False,
        runtime_attachment=runtime_gripper_attachment,
        runtime_attachment_handoff_steps=int(
            getattr(physical, "runtime_attachment_handoff_steps", 0)
        ),
        motion_profile=str(getattr(physical, "motion_profile", "ease")),
        # Plug mode: command-space anchoring kills the per-waypoint
        # dip-and-recover hand bobbing on dense segments (2026-07-13 diag).
        command_space_segments=handle_connector_enabled,
        verbose=cfg.run.verbose,
    )
    grasp_yaw = float(getattr(physical, "grasp_yaw", 0.0))
    ee_quat = ee_quat_for_yaw(controller.default_ee_quat, grasp_yaw)
    status.update({"phase": "settle", "waypoint": 0, "waypoints": len(targets)})
    trace: list[np.ndarray] = []
    initial_rope_length = polyline_length(cable_scene.layout.route_polyline("initial"))
    goal_reference_length = polyline_length(cable_scene.layout.route_polyline("goal"))
    handle_cfg = cfg.task.rope.endpoint_handle
    handle_shape = str(getattr(handle_cfg, "shape", "cylinder"))
    if hasattr(handle_cfg, "grip_width"):
        handle_grip_width = float(handle_cfg.grip_width)
    elif handle_shape == "box" and hasattr(handle_cfg, "size"):
        handle_size = [float(value) for value in _list(handle_cfg.size)]
        handle_grip_width = float(handle_size[1 if len(handle_size) > 1 else 0])
    else:
        handle_grip_width = 2.0 * float(handle_cfg.radius)
    handle_height = float(getattr(handle_cfg, "height", 0.0))
    if handle_shape == "box" and hasattr(handle_cfg, "size"):
        handle_size = [float(value) for value in _list(handle_cfg.size)]
        if len(handle_size) >= 3:
            handle_height = float(handle_size[2])
    target_gap_approx = 2.0 * float(physical.grasp_qpos)
    grip_interference = handle_grip_width - target_gap_approx
    print(
        "cable_routing_physical_handle_demo setup "
        f"waypoints={len(targets)} grasp_qpos={float(physical.grasp_qpos):.4f} "
        f"handle_shape={handle_shape} "
        f"handle_grip_width={handle_grip_width:.4f} "
        f"handle_height={handle_height:.4f} "
        f"handle_z_offset={z_offset:.4f} "
        f"target_gap_approx={target_gap_approx:.4f} "
        f"grip_interference={grip_interference:.4f} "
        f"grasp_yaw={grasp_yaw:.4f} "
        f"handle_friction={float(physical.handle_friction):.2f} "
        f"finger_friction={float(physical.finger_friction):.2f} "
        f"latch_xy_tol={float(physical.latch_capture_tolerance_xy):.3f} "
        f"latch_z_tol={float(physical.latch_capture_tolerance_z):.3f} "
        f"latch_tilt_tol={float(physical.latch_capture_max_tilt_deg):.1f} "
        f"latch_mode={latch.step_hook_mode if latch is not None else 'disabled'} "
        f"latch_auto_capture={bool(latch is not None and latch.auto_capture)} "
        f"runtime_gripper_attachment={runtime_gripper_attachment} "
        f"runtime_attachment_handoff_steps="
        f"{int(getattr(physical, 'runtime_attachment_handoff_steps', 0))} "
        f"motion_profile={str(getattr(physical, 'motion_profile', 'ease'))} "
        f"viewer_speedup={speedup:.2f} "
        f"slow_factor={slow_factor:.2f} "
        f"allow_target_lag={bool(cfg.run.allow_target_lag)} "
        f"segment_steps={target_steps} "
        f"max_segment_follow_error={float(physical.max_segment_follow_error):.4f} "
        f"max_segment_target_error={max_segment_target_error} "
        f"max_downward_follow_z="
        f"{getattr(physical, 'max_downward_follow_error_z', None)} "
        f"early_complete_segments={list(early_complete_segments)} "
        f"early_complete_target_error={early_complete_target_error} "
        f"safety_min_gap={getattr(physical, 'safety_min_gap', None)} "
        f"safety_max_contact_particles="
        f"{getattr(physical, 'safety_max_contact_particles', None)} "
        f"initial_rope_length={initial_rope_length:.4f} "
        f"goal_reference_length={goal_reference_length:.4f} "
        f"reference_slack={initial_rope_length - goal_reference_length:.4f}",
        flush=True,
    )

    phase_checkpoints = {
        "green_P1_top",
        "green_P2_lower_right",
        "green_exit_to_C",
    }

    def on_segment_start(index, total, label, target):
        status["phase"] = label
        status["waypoint"] = index
        print(
            "cable_routing_physical_handle_demo waypoint_start "
            f"index={index}/{total} phase={label} target={target.tolist()}",
            flush=True,
        )

    def on_segment_complete(
        index,
        total,
        label,
        target,
        handle_pos,
        follow_error,
        target_error,
    ):
        del target
        print(
            "cable_routing_physical_handle_demo waypoint_complete "
            f"index={index}/{total} phase={label} "
            f"handle={handle_pos.tolist()} follow_error={follow_error:.4f} "
            f"target_error={target_error:.4f}",
            flush=True,
        )
        if label in phase_checkpoints:
            print_phase_routing_metrics(cable_scene, trace, phase=label)
            safety_min_gap = getattr(physical, "safety_min_gap", None)
            safety_max_contact = getattr(physical, "safety_max_contact_particles", None)
            safety_fixtures = {
                str(value)
                for value in _list(getattr(physical, "safety_fixtures", []))
            }
            safety_reasons = []
            for item in peg_signature_items(cable_scene.layout):
                fixture = str(item["fixture"])
                if safety_fixtures and fixture not in safety_fixtures:
                    continue
                relation = str(item["relation"])
                metrics = rope_wrap_metrics(cable_scene, fixture, relation)
                particle_surface_gap = float(metrics["particle_surface_gap"])
                contact_particles = int(metrics["contact_particles"])
                if (
                    safety_min_gap is not None
                    and particle_surface_gap < float(safety_min_gap)
                ):
                    safety_reasons.append(
                        f"{fixture}:{relation} "
                        f"particle_surface_gap={particle_surface_gap:.4f}"
                    )
                if (
                    safety_max_contact is not None
                    and int(safety_max_contact) > 0
                    and contact_particles > int(safety_max_contact)
                ):
                    safety_reasons.append(
                        f"{fixture}:{relation} contact_particles={contact_particles}"
                    )
            if safety_reasons:
                reason = (
                    "wrap_contact_safety_abort: "
                    f"phase={label} "
                    + "; ".join(safety_reasons)
                )
                print(
                    "cable_routing_physical_handle_demo safety_abort "
                    f"reason={reason}",
                    flush=True,
                )
                return reason
        return None

    def engage_connector_latch(handle_pos, final_target):
        del handle_pos, final_target
        if latch is None:
            return False
        status["phase"] = "connector_latch"
        engaged = latch.try_engage()
        if engaged and grasp_attachment:
            release_grasp_attachment()
        print(
            "cable_routing_physical_handle_demo connector_latch "
            f"engaged={engaged} xy_error={latch.last_xy_error:.4f} "
            f"z_error={latch.last_z_error:.4f} "
            f"tilt_deg={latch.last_tilt_deg:.1f} "
            f"capture_checks={latch.capture_checks}",
            flush=True,
        )
        return bool(engaged)

    attachment_manager = AttachmentManager(cable_scene.scene)

    def engage_grasp_attachment():
        # GRASPED state: fingers closed around the plug column — hand the plug
        # from its spawn latch to a hand attachment in the same step.
        offset = entity_pos(handle) - np.asarray(controller.hand_pos(), dtype=float)
        attachment = attachment_manager.create(
            entity=handle,
            parent_pos_fn=controller.hand_pos,
            offset=offset,
        )
        spawn_latch.active = False
        attachment.attach()
        grasp_attachment.append(attachment)

    def release_grasp_attachment():
        attachment = grasp_attachment.pop()
        attachment.release(sync=False)
        attachment_manager.attachments.remove(attachment)

    if cfg.run.probe:
        _print_probe_plan(target_labels, targets, target_steps)
    probe = None
    if stop_before_physics(cfg, cable_scene.scene, "cable_routing_physical_handle_demo"):
        raise SystemExit(0)

    with recording_session_from_config(
        cable_scene.scene,
        cable_scene.cameras,
        cfg.recording,
        hud=_hud(status),
    ):
        with attachment_manager:
            controller.step(
                max(
                    0,
                    _scaled_steps(
                        cfg.run.settle_steps,
                        speedup,
                        minimum=5,
                        slow_factor=slow_factor,
                    ),
                )
            )
            status["phase"] = "physical_route"
            if cfg.run.probe:
                probe = CableRoutingProbe(
                    cable_scene.scene,
                    controller,
                    cable_scene,
                    handle,
                    status,
                    every=cfg.run.probe_every,
                    surface_z=cable_scene.layout.world_z(0.0),
                )
            result = primitive.run(
                controller,
                handle=handle,
                target_centers=targets,
                target_steps=target_steps,
                segment_labels=target_labels,
                on_segment_start=on_segment_start,
                on_segment_complete=on_segment_complete,
                on_close=(
                    engage_grasp_attachment if spawn_latch is not None else None
                ),
                before_release=engage_connector_latch if full_route else None,
                ee_quat=ee_quat,
                trace=trace,
                attachment_manager=attachment_manager,
            )
            if spawn_latch is not None and grasp_attachment:
                # Abort / refused-latch path: freeze the plug where the hand
                # stopped (fingers are still closed — recover_on_segment_failure
                # is False), instead of teleporting it home, which read as a
                # sudden "drop" in the viewer. The latch step hook outlives the
                # attachment-manager context, so the mesh-only plug cannot fall
                # during the viewer hold either.
                release_grasp_attachment()
                spawn_latch.target_pos = entity_pos(handle)
                spawn_latch.active = True
                spawn_latch.sync()
                print(
                    "cable_routing_physical_handle_demo abort_hold "
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
                routing_success = print_routing_verification(cable_scene, trace) if full_route else False
            else:
                status["phase"] = "route_failed"
                routing_success = False
                print(
                    "cable_routing_physical_handle_demo routing_verify_skipped "
                    f"reason={result.failure_reason}",
                    flush=True,
                )
            settled_handle_pos = entity_pos(handle)
            if cfg.run.release_end_steps > 0:
                _run_release_end_probe(
                    cable_scene,
                    controller,
                    int(cfg.run.release_end_steps),
                    sample_every=max(1, int(cfg.run.probe_every)),
                )
            if probe is not None:
                probe.uninstall()

    # Exclude reset_home (a set_dofs_position teleport) from the dataset: it is
    # post-task cleanup, not demonstration, and its implied action is an
    # un-replayable jump.
    if dataset_writer is not None:
        dataset_writer.stop_capture()
    if result.success:
        controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    else:
        print(
            "cable_routing_physical_handle_demo reset_home_skipped "
            "reason=physical_route_failed_before_safe_settle",
            flush=True,
        )
    connector_error_xy = float(
        np.linalg.norm(settled_handle_pos[:2] - targets[-1][:2])
    )
    endpoint_success = connector_error_xy <= float(physical.connector_tolerance_xy)
    latch_engaged = bool(latch is not None and latch.active)
    success = bool(
        result.success
        and routing_success
        and endpoint_success
        and latch_engaged
        and full_route
    )
    metrics = {
        "task_success": bool(success),
        "physical_success": bool(result.success),
        "routing_success": bool(routing_success),
        "full_route": bool(full_route),
        "endpoint_success": bool(endpoint_success),
        "latch_engaged": bool(latch_engaged),
        "connector_error_xy": float(connector_error_xy),
        "completed_waypoints": len(result.completed_segments),
        "planned_waypoints": len(targets),
    }
    episode_result = (
        EpisodeResult.ok(episode_spec.key, metrics=metrics, export_ready=True)
        if success
        else EpisodeResult.failed(
            episode_spec.key,
            result.failure_reason or "cable_routing_not_routed",
            metrics=metrics,
            stable_ready=False,
        )
    )
    print(
        "cable_routing_physical_handle_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"task_success={success} physical_success={result.success} "
        f"stable_ready={episode_result.stable_ready} export_ready={episode_result.export_ready} "
        f"routing_success={routing_success} full_route={full_route} "
        f"endpoint_success={endpoint_success} "
        f"latch_engaged={latch_engaged} "
        f"connector_error_xy={connector_error_xy:.4f} "
        f"completed_waypoints={len(result.completed_segments)}/{len(targets)} "
        f"grasped={result.grasped} "
        f"failure_reason={result.failure_reason}",
        flush=True,
    )
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="cable_routing")
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
        print(f"cable_routing_config -> {resolved}", flush=True)
    if cfg.run.randomize_layout:
        from topogym.generation.layout_randomization import randomize_task_cfg

        if not bool(cfg.task.routing.get("smooth_route", False)):
            print(
                "cable_routing_physical_handle_demo WARNING randomize-layout assumes "
                "routing.smooth_route=true; peg jitter will desync the hand-authored "
                "endpoint_oracle_waypoints.",
                flush=True,
            )
        cfg = randomize_task_cfg(
            cfg, str(cfg.task.task.id), cfg.run.seed, difficulty=cfg.run.difficulty
        )
        print(
            f"cable_routing_physical_handle_demo randomize_layout=on seed={cfg.run.seed} "
            f"difficulty={cfg.run.difficulty}",
            flush=True,
        )
    # 每个配置组解析到了哪个文件，作为 episode 溯源信息记录。
    _sources = hydra_config_sources()
    episode_spec = build_cable_routing_episode_spec(
        cfg,
        seed=cfg.run.seed,
        common_config=_sources.get("common"),
        env_config=_sources.get("env"),
        robot_config=_sources.get("robot_control"),
        task_config=_sources.get("task"),
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
        "cable_routing_physical_handle_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={cfg.run.viewer} "
        f"lite={cfg.run.lite} viewer_speedup={float(cfg.run.viewer_speedup):.2f} "
        f"slow_factor={float(cfg.run.slow_factor):.2f} "
        f"allow_target_lag={bool(cfg.run.allow_target_lag)}",
        flush=True,
    )
    scene = CableRoutingSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        route_mode="initial",
    ).build(show_viewer=cfg.run.viewer, include_robot=True)
    route_command, episode_plan = plan_cable_routing_endpoint_route(scene.layout)
    print("cable_routing_physical_handle_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        "cable_routing_physical_handle_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )
    # ``status`` is created here (not in run_demo) so the dataset writer's
    # subgoal labels can read the live phase during the run.
    status: dict = {}
    dataset_writer_cm = dataset_writer_or_null(
        cfg.run.record_dataset,
        scene=scene.scene,
        cameras=scene.cameras,
        controller=controller,
        spec=episode_spec,
        plan=episode_plan,
        task_goal="Route the cable end through the pegs into the connector.",
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
            status=status,
            dataset_writer=dataset_writer,
        )
        if dataset_writer is not None:
            dataset_writer.finalize(episode_result)
            print(f"saved dataset -> {cfg.run.record_dataset}", flush=True)
    print_recording_saved(cfg.recording)
    keep_open = bool(cfg.run.viewer and not cfg.run.close_on_finish)
    if keep_open:
        print("cable_routing_physical_handle_demo viewer_hold; press Ctrl+C to exit", flush=True)
    while keep_open:
        try:
            scene.scene.step()
        except gs.GenesisException as exc:
            if "Viewer closed" in str(exc):
                print("cable_routing_physical_handle_demo viewer_closed; exiting", flush=True)
                break
            raise


if __name__ == "__main__":
    main()
