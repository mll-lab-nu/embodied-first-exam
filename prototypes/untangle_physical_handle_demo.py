from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.data import dataset_writer_or_null
from topogym.envs import UntangleHighLevelEnv
from topogym.generation import EpisodeResult, build_untangle_episode_spec
from topogym.planning import plan_next_untangle_move
from topogym.primitives import (
    AttachmentManager,
    ConnectorLatch,
    PBDHandleDragPrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    print_collision_il_contract,
)
from topogym.supervision import StepProbe, probe_particles
from topogym.tasks import UntangleSceneBuilder
from topogym.utils import (
    add_recording_args,
    initialize_franka_controller,
    merge_recording_config,
    print_recording_saved,
    recording_session_from_config,
)


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "untangle_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Untangle PBD ropes by physically grasping rigid endpoint handles."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Stable episode seed. The current tabletop untangle layout is deterministic.",
    )
    parser.add_argument(
        "--variant-id",
        default="default",
        help="Stable variant label for manifests and result lines.",
    )
    parser.add_argument(
        "--randomize-layout",
        action="store_true",
        help="Apply seeded bounded layout randomization (default off = deterministic).",
    )
    parser.add_argument(
        "--difficulty",
        default="default",
        help="Randomization magnitude bucket (easy/default/hard); only with --randomize-layout.",
    )
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default=None)
    parser.add_argument(
        "--grasp-rope",
        type=int,
        default=None,
        help=(
            "Force the planner onto this rope (0=red, 1=green, 2=blue; strand "
            "order in the task config) and waive the wrong-rope veto. The "
            "contact test: green lies over red, so --grasp-rope 0 drags the "
            "UNDER rope -- a move that cannot undo the crossing; the honest "
            "outcome is a blocked rope and a surviving crossing."
        ),
    )
    parser.add_argument(
        "--fem-e",
        type=float,
        default=None,
        help=(
            "Override rope.fem.E (Pa). Default 1e5 was calibrated on the "
            "continuous task's on-table ropes; suspended spans here read stiff "
            "at that value."
        ),
    )
    parser.add_argument(
        "--fem-nu",
        type=float,
        default=None,
        help=(
            "Override rope.fem.nu. Default 0.45 is near-incompressible, which "
            "locks linear-tet bending (rope reads rigid); try 0.3."
        ),
    )
    parser.add_argument(
        "--fem-friction-mu",
        type=float,
        default=None,
        help="Override rope.fem.friction_mu (default 0.3).",
    )
    parser.add_argument(
        "--log-level",
        choices=("debug", "info", "warning"),
        default=None,
        help=(
            "Override env.genesis.logging_level. 'debug' additionally turns on "
            "libuipc's own logging (the IPC coupler only enables it at that "
            "level), which is the visibility needed for CUDA-side crashes."
        ),
    )
    parser.add_argument(
        "--rope-model",
        choices=("pbd_elastic_tube", "fem_ipc_tube"),
        default=None,
        help=(
            "Override rope.model. 'fem_ipc_tube' selects the FEM+IPC backend; "
            "pair it with --env-config world_tabletop_fem_v1.yaml. "
            "--lite is a PBD-resolution knob and does not apply there."
        ),
    )
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--close-on-finish", action="store_true")
    parser.add_argument("--lite", action="store_true", help="Use a lower-resolution PBD rope.")
    parser.add_argument("--max-moves", type=int, default=8)
    parser.add_argument("--max-grasp-attempts", type=int, default=None)
    parser.add_argument("--between-moves-settle-steps", type=int, default=None)
    parser.add_argument("--settle-steps", type=int, default=60)
    add_recording_args(parser, default_fps=60, default_camera="oblique")
    parser.add_argument(
        "--record-dataset",
        type=Path,
        default=None,
        help="Write a RoboMME-structural HDF5 dataset for this episode to this path.",
    )
    parser.add_argument(
        "--dataset-every-n-steps",
        type=int,
        default=10,
        help="Capture one dataset frame every N scene.step() calls (action granularity).",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Per-step flyout diagnostic PROBE lines (H1 finger contact vs H2 compression).",
    )
    parser.add_argument("--probe-every", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def load_configs(args: argparse.Namespace):
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    physical = cfg.task.physical_handle
    connector_enabled = bool(
        getattr(getattr(cfg.task.rope.anchor_pins, "connector", None), "enabled", False)
    )
    overrides = {
        "task": {
            "rope": {
                "anchor_pins": {
                    "attachment_mode": "rigid_handles",
                    "radius": float(physical.radius),
                    "height": float(physical.height),
                    "z_offset": float(physical.z_offset),
                    "fixed": False,
                    # Plug-connector mode (redesign Phase B): the connector is a
                    # kinematic body driven by the socket latch / grasp attachment,
                    # so it stays mesh-only — its below-board pin would otherwise
                    # fight the solid board through the convex collision hull.
                    "collision": not connector_enabled,
                    "friction": float(physical.handle_friction),
                    "rho": float(physical.rho),
                    "exclude_pbd_collision": True,
                }
            }
        }
    }
    if args.backend is not None:
        overrides["env"] = {"genesis": {"backend": args.backend}}
    cfg = OmegaConf.merge(cfg, overrides)
    if args.rope_model is not None:
        cfg = OmegaConf.merge(cfg, {"task": {"rope": {"model": args.rope_model}}})
    if args.log_level is not None:
        cfg = OmegaConf.merge(
            cfg, {"env": {"genesis": {"logging_level": args.log_level}}}
        )
    for key, value in (
        ("E", args.fem_e),
        ("nu", args.fem_nu),
        ("friction_mu", args.fem_friction_mu),
    ):
        if value is not None:
            cfg = OmegaConf.merge(cfg, {"task": {"rope": {"fem": {key: value}}}})
    if args.lite:
        cfg = OmegaConf.merge(
            cfg,
            {
                "task": {
                    "rope": {
                        "particle_size": 0.006,
                        "mesh": {
                            "segment_length": 0.014,
                            "radial_segments": 6,
                            "maxvolume": 0.00000012,
                        },
                        "pbd": {
                            "max_stretch_solver_iterations": 6,
                            "max_bending_solver_iterations": 3,
                            "max_volume_solver_iterations": 3,
                        },
                    }
                }
            },
        )
    return merge_recording_config(cfg, args)


def _endpoint_pin(handle, endpoint_index: int):
    return handle.start_pin if int(endpoint_index) == 0 else handle.end_pin


def _physical_handle_names(untangle_scene) -> tuple[str, ...]:
    names: list[str] = []
    for rope_name, rope_handle in sorted(untangle_scene.rope_handles.items()):
        for endpoint_name, pin in (
            ("start", rope_handle.start_pin),
            ("end", rope_handle.end_pin),
        ):
            if pin is None:
                raise RuntimeError(
                    "Untangle physical demo requires dynamic rigid endpoint "
                    f"handles, but {rope_name}:{endpoint_name} has no pin."
                )
            names.append(f"anchor_pin_{rope_name}_{endpoint_name}")
    return tuple(names)


def _validate_physical_handle_contract(cfg, untangle_scene) -> tuple[str, ...]:
    pin_cfg = cfg.task.rope.anchor_pins
    attachment_mode = str(getattr(pin_cfg, "attachment_mode", "fixed_particles"))
    if attachment_mode != "rigid_handles":
        raise RuntimeError(
            "Untangle physical demo requires "
            "rope.anchor_pins.attachment_mode=rigid_handles."
        )
    if bool(getattr(pin_cfg, "fixed", True)):
        raise RuntimeError(
            "Untangle physical demo requires dynamic endpoint handles "
            "(rope.anchor_pins.fixed=false)."
        )
    connector_enabled = bool(
        getattr(getattr(pin_cfg, "connector", None), "enabled", False)
    )
    if connector_enabled:
        if bool(getattr(pin_cfg, "collision", False)):
            raise RuntimeError(
                "Plug-connector handles must stay mesh-only (collision=false); "
                "the socket latch / grasp attachment drives them kinematically."
            )
    elif not bool(getattr(pin_cfg, "collision", False)):
        raise RuntimeError(
            "Untangle physical demo requires endpoint handle collision=true."
        )
    if not bool(getattr(pin_cfg, "exclude_pbd_collision", False)):
        raise RuntimeError(
            "Untangle physical demo requires exclude_pbd_collision=true so "
            "attached endpoint particles do not collide with their own handle."
        )
    return _physical_handle_names(untangle_scene)


class UntangleProbe(StepProbe):
    """Per-scene-step flyout diagnostic. Machinery from `supervision.StepProbe`.

    Wraps ``scene.step`` and samples every ``every`` physics steps:
    - per rope: ``parked`` count (particles pinned at the PBD domain corner
      (100,100,100) = already ejected), max per-step particle ``jump``, ``zmax``;
    - moved rope: ``finger_dist`` = min particle distance to either finger pad
      (H1 gripper-contact evidence) and ``endpoint_sep`` = xy separation of its
      two endpoint pins (H2 compression evidence).
    The first parked particle per rope triggers a PROBE_FLYOUT line with the
    particle's spawn position. See untangle_connector_flyout_debug_zh.md §4.
    """

    def __init__(
        self, scene, controller, rope_handles, status, *, finger_links, every, rope_backend=None
    ):
        super().__init__(scene, every=every)
        self.controller = controller
        self.rope_handles = rope_handles
        self.status = status
        # Node access goes through the scene's rope backend when present
        # (solver-agnostic); the direct PBD probe is the fallback.
        self._rope_backend = rope_backend
        self.finger_links = [
            controller.robot.get_link(str(name)) for name in finger_links
        ]
        self.moved = None
        self._spawn = {
            name: self._particles(handle.entity)
            for name, handle in rope_handles.items()
        }
        self._last = dict(self._spawn)
        self._flyout_reported: set[str] = set()

    def set_move(self, rope_handle) -> None:
        self.moved = rope_handle

    def _particles(self, entity) -> np.ndarray:
        if self._rope_backend is not None:
            return np.asarray(self._rope_backend.nodes(entity), dtype=float)
        return probe_particles(entity)

    @staticmethod
    def _link_pos(link) -> np.ndarray:
        pos = link.get_pos()
        if hasattr(pos, "detach"):
            pos = pos.detach().cpu().numpy()
        return np.asarray(pos, dtype=float).reshape(-1, 3)[0]

    def _sample(self) -> None:
        fields = [
            f"PROBE step={self.count:05d}"
            f" phase={self.status.get('phase', '?')}"
            f" move={self.status.get('move', '-')}"
        ]
        flyout_lines = []
        for name, handle in self.rope_handles.items():
            parts = self._particles(handle.entity)
            parked_mask = np.linalg.norm(parts - self.DOMAIN_CORNER, axis=1) < 1.0
            parked = int(parked_mask.sum())
            last = self._last[name]
            if last.shape == parts.shape:
                jump = float(np.max(np.linalg.norm(parts - last, axis=1))) / self.every
            else:
                jump = float("nan")
            self._last[name] = parts
            fields.append(
                f"{name}[parked={parked} jump={jump:.4f} zmax={parts[:, 2].max():.3f}]"
            )
            if parked and name not in self._flyout_reported:
                self._flyout_reported.add(name)
                first_idx = int(np.flatnonzero(parked_mask)[0])
                spawn = self._spawn[name][first_idx]
                flyout_lines.append(
                    "PROBE_FLYOUT "
                    f"rope={name} step={self.count} n_parked={parked} "
                    f"first_idx={first_idx} "
                    f"spawn=({spawn[0]:+.4f},{spawn[1]:+.4f},{spawn[2]:+.4f})"
                )
        if self.moved is not None:
            parts = self._last[self.moved.name]
            live_mask = np.linalg.norm(parts - self.DOMAIN_CORNER, axis=1) >= 1.0
            live = parts[live_mask] if live_mask.any() else parts
            finger_dist = min(
                float(np.min(np.linalg.norm(live - self._link_pos(link)[None, :], axis=1)))
                for link in self.finger_links
            )
            endpoint_sep = float(
                np.linalg.norm(
                    entity_pos(self.moved.start_pin)[:2]
                    - entity_pos(self.moved.end_pin)[:2]
                )
            )
            fields.append(
                f"moved={self.moved.name}"
                f" finger_dist={finger_dist:.4f}"
                f" endpoint_sep={endpoint_sep:.4f}"
            )
        print(" ".join(fields), flush=True)
        for line in flyout_lines:
            print(line, flush=True)


def _hud(topology_env: UntangleHighLevelEnv, status: dict):
    def render_lines():
        state = topology_env.topology_state()
        return [
            "task=untangle physical handle",
            f"phase={status.get('phase', 'setup')}",
            f"move={status.get('move', '-')}",
            f"terminal={state.is_terminal}",
            f"crossings={len(state.crossings)}",
            f"knots={len(state.knots)}",
        ]

    return render_lines


def run_demo(
    args, cfg, untangle_scene, controller, *, episode_spec, status, dataset_writer=None
) -> EpisodeResult:
    physical = cfg.task.physical_handle
    connector_enabled = bool(
        getattr(getattr(cfg.task.rope.anchor_pins, "connector", None), "enabled", False)
    )
    manipulated = _validate_physical_handle_contract(cfg, untangle_scene)
    print_collision_il_contract(
        "untangle_physical_handle_demo",
        manipulated=manipulated,
        runtime_attachment=connector_enabled,
        runtime_set_pose=connector_enabled,
        success_checks=(
            "lift_delta",
            "handle_follow_error",
            "placement_error_xy",
            "topology_terminal",
        ),
    )
    print(
        "untangle_physical_handle_demo pbd_contract "
        "rope_model=pbd_elastic_tube endpoint_constraint=fix_particles_to_link "
        f"runtime_set_particles_pos=False handle_collision={not connector_enabled} "
        f"handle_needs_coup=False connector_latch={connector_enabled}",
        flush=True,
    )
    max_grasp_attempts = (
        int(physical.max_grasp_attempts)
        if args.max_grasp_attempts is None
        else int(args.max_grasp_attempts)
    )
    between_moves_settle_steps = (
        int(physical.between_moves_settle_steps)
        if args.between_moves_settle_steps is None
        else int(args.between_moves_settle_steps)
    )
    if max_grasp_attempts <= 0:
        raise ValueError("physical_handle.max_grasp_attempts must be positive.")
    if between_moves_settle_steps < 0:
        raise ValueError(
            "physical_handle.between_moves_settle_steps must be nonnegative."
        )
    placement_tolerance_xy = float(physical.placement_tolerance_xy)
    topology_env = UntangleHighLevelEnv(
        task_cfg=cfg.task,
        seed=int(args.seed),
        random_reset=False,
        max_episode_steps=max(1, int(args.max_moves)),
    )
    topology_env.reset()
    handles = [
        pin
        for rope_handle in untangle_scene.rope_handles.values()
        for pin in (rope_handle.start_pin, rope_handle.end_pin)
        if pin is not None
    ]
    configure_gripper_contact_friction(
        # Mesh-only connectors carry no contact geometry; only finger friction matters.
        entities=[] if connector_enabled else handles,
        robot=controller.robot,
        finger_links=physical.finger_links,
        object_friction=float(physical.handle_friction),
        finger_friction=float(physical.finger_friction),
    )
    latches: dict[tuple[str, int], ConnectorLatch] = {}
    if connector_enabled:
        # Socket latches implement the SOCKETED state of the two-state connector
        # lifecycle (untangle_redesign_plan_zh.md §2): each connector spawns seated
        # in its hole and is pose-locked there until a grasp hands it to the arm.
        for rope_name, rope_handle in untangle_scene.rope_handles.items():
            for endpoint_index, pin in (
                (0, rope_handle.start_pin),
                (1, rope_handle.end_pin),
            ):
                latch = ConnectorLatch(
                    scene=untangle_scene.scene,
                    handle=pin,
                    target_pos=entity_pos(pin),
                    capture_tolerance_xy=0.010,
                    capture_tolerance_z=0.020,
                    capture_max_tilt_deg=30.0,
                    auto_capture=False,
                )
                if not latch.try_engage():
                    raise RuntimeError(
                        f"Connector {rope_name}:{endpoint_index} failed to seat at spawn."
                    )
                latches[(rope_name, endpoint_index)] = latch
    status.update({"phase": "settle", "move": ""})
    primitive = PBDHandleDragPrimitive(
        approach_z=untangle_scene.layout.world_z(physical.approach_z),
        lift_delta=float(physical.lift_delta),
        move_steps=int(physical.move_steps),
        gripper_steps=int(physical.gripper_steps),
        grasp_qpos=float(physical.grasp_qpos),
        close_hold_steps=int(physical.close_hold_steps),
        pre_lift_delta=float(getattr(physical, "pre_lift_delta", 0.0)),
        pre_lift_steps=int(getattr(physical, "pre_lift_steps", 0)),
        motion_settle_steps=int(physical.motion_settle_steps),
        min_lift_delta=float(physical.min_lift_delta),
        max_handle_error=float(physical.max_handle_error),
        release_hold_steps=int(physical.release_hold_steps),
        verbose=args.verbose,
    )
    print(
        "untangle_physical_handle_demo setup "
        f"episode_id={episode_spec.stable_id()} "
        "planner=untangle_topology_greedy_endpoint_move "
        f"ropes={len(untangle_scene.rope_handles)} max_moves={int(args.max_moves)} "
        f"max_grasp_attempts={max_grasp_attempts} "
        f"grasp_qpos={float(physical.grasp_qpos):.4f} "
        f"lift_delta={float(physical.lift_delta):.4f} "
        f"move_steps={int(physical.move_steps)} "
        f"handle_friction={float(physical.handle_friction):.2f} "
        f"finger_friction={float(physical.finger_friction):.2f}",
        flush=True,
    )

    probe = (
        UntangleProbe(
            untangle_scene.scene,
            controller,
            untangle_scene.rope_handles,
            status,
            finger_links=physical.finger_links,
            every=args.probe_every,
            rope_backend=untangle_scene.rope_backend,
        )
        if args.probe
        else None
    )
    moves_completed = 0
    failure_reason = None
    all_physical_moves_succeeded = True
    with recording_session_from_config(
        untangle_scene.scene,
        untangle_scene.cameras,
        cfg.recording,
        hud=_hud(topology_env, status),
    ), AttachmentManager(untangle_scene.scene) as attachment_manager:
        controller.step(max(0, int(args.settle_steps)))
        initial_state = topology_env.topology_state()
        print(
            "untangle_physical_handle_demo initial_topology "
            f"crossings={len(initial_state.crossings)} knots={len(initial_state.knots)} "
            f"endpoint_overlaps={len(initial_state.endpoint_overlaps)}",
            flush=True,
        )
        for move_index in range(max(1, int(args.max_moves))):
            planned_move = plan_next_untangle_move(
                topology_env, untangle_scene.layout, grasp_rope=args.grasp_rope
            )
            if planned_move is None:
                if not topology_env.topology_state().is_terminal:
                    failure_reason = "planner_exhausted"
                break
            command, episode_plan = planned_move
            rope_index = command.rope_index
            endpoint_index = command.endpoint_index
            target_hole = command.target_hole
            rope_name = command.rope_name
            rope_handle = untangle_scene.rope_handles[rope_name]
            if probe is not None:
                probe.set_move(rope_handle)
            pin = _endpoint_pin(rope_handle, endpoint_index)
            if pin is None:
                raise RuntimeError(f"No rigid handle for {rope_name}:{endpoint_index}.")
            pin_pos = entity_pos(pin)
            drop_target = untangle_scene.layout.hole_center(
                int(target_hole[0]),
                int(target_hole[1]),
            )
            # hole_center(z=...) expects task-frame z for tabletop configs, while
            # pin_pos is already world-frame. Set world z after XY conversion to
            # avoid adding the tabletop origin height twice.
            drop_target[2] = float(pin_pos[2])
            carry_target = drop_target.copy()
            carry_target[2] += float(physical.lift_delta)
            endpoint_name = command.endpoint_name
            status["phase"] = "physical_drag"
            status["move"] = f"{rope_name}:{endpoint_name}->{list(target_hole)}"
            print(
                "untangle_physical_handle_demo move "
                f"index={move_index + 1} plan_id={episode_plan.plan_id} "
                f"action={command.action} {status['move']} "
                f"conflicts={command.conflict_count_before}->{command.conflict_count_after}",
                flush=True,
            )
            latch = latches.get((rope_name, endpoint_index))
            origin_seat = None if latch is None else latch.target_pos.copy()
            ee_quat = None
            if latch is not None:
                # The rope leaves the carried connector's top and drapes toward the
                # rope's other end. With the default yaw the finger pads flank the
                # column along that same axis, so on release/retreat a pad hooks
                # the drape and tears the rope (observed PBD blowup). Yaw the
                # gripper so the pads stay clear of the drape direction at both
                # the grasp hole and the target hole.
                other_pin = _endpoint_pin(rope_handle, 1 - endpoint_index)
                other_xy = entity_pos(other_pin)[:2]
                directions = []
                for anchor_xy in (pin_pos[:2], drop_target[:2]):
                    delta = other_xy - anchor_xy
                    norm = float(np.linalg.norm(delta))
                    if norm > 1e-6:
                        directions.append(delta / norm)
                bisector = np.sum(directions, axis=0) if directions else np.array([1.0, 0.0])
                if float(np.linalg.norm(bisector)) < 1e-6:
                    bisector = directions[0]
                grasp_yaw = float(np.arctan2(bisector[1], bisector[0]))
                ee_quat = ee_quat_for_yaw(controller.default_ee_quat, grasp_yaw)
            grasp_attachment: list = []

            def engage_grasp_attachment():
                # Assisted grasp (GRASPED state, redesign §2): with the fingers
                # closed around the grasp column, hand the connector from its
                # socket latch to a hand attachment in the same step so it is
                # never free-simulated.
                offset = entity_pos(pin) - np.asarray(controller.hand_pos(), dtype=float)
                attachment = attachment_manager.create(
                    entity=pin,
                    parent_pos_fn=controller.hand_pos,
                    offset=offset,
                )
                latch.active = False
                attachment.attach()
                grasp_attachment.append(attachment)

            def release_grasp_attachment():
                attachment = grasp_attachment.pop()
                attachment.release(sync=False)
                attachment_manager.attachments.remove(attachment)

            def seat_connector(handle_pos, final_target):
                del handle_pos, final_target
                # Snap seating = the move's topology event: weld the connector
                # into the target hole, then free the fingers.
                latch.target_pos = np.asarray(drop_target, dtype=float)
                engaged = latch.try_engage()
                if not engaged:
                    # Atomicity: refused seating returns the connector to its
                    # original socket; a move completes or changes nothing.
                    latch.target_pos = origin_seat
                    latch.active = True
                    latch.sync()
                release_grasp_attachment()
                print(
                    "untangle_physical_handle_demo connector_seat "
                    f"move={move_index + 1} engaged={engaged} "
                    f"xy_error={latch.last_xy_error:.4f} "
                    f"z_error={latch.last_z_error:.4f}",
                    flush=True,
                )
                return bool(engaged)

            move_succeeded = False
            for attempt in range(1, max_grasp_attempts + 1):
                print(
                    "untangle_physical_handle_demo attempt "
                    f"move={move_index + 1} attempt={attempt}/{max_grasp_attempts}",
                    flush=True,
                )
                result = primitive.run(
                    controller,
                    handle=pin,
                    target_centers=[carry_target, drop_target],
                    target_steps=[int(physical.move_steps) * 2, int(physical.move_steps) // 2],
                    segment_labels=["carry_above_target", "place_at_target"],
                    on_close=engage_grasp_attachment if latch is not None else None,
                    before_release=seat_connector if latch is not None else None,
                    ee_quat=ee_quat,
                    on_segment_start=(
                        lambda index, total, label, target: print(
                            "untangle_physical_handle_demo segment_start "
                            f"move={move_index + 1} index={index}/{total} "
                            f"label={label} target={target.tolist()}",
                            flush=True,
                        )
                    ),
                    on_segment_complete=(
                        lambda index, total, label, target, handle_pos, follow_error, target_error: print(
                            "untangle_physical_handle_demo segment_complete "
                            f"move={move_index + 1} index={index}/{total} "
                            f"label={label} handle={handle_pos.tolist()} "
                            f"follow_error={follow_error:.4f} "
                            f"target_error={target_error:.4f}",
                            flush=True,
                        )
                    ),
                )
                if latch is not None and grasp_attachment:
                    # Failure path (before_release never ran): re-socket the
                    # connector at its origin hole so state is unchanged.
                    release_grasp_attachment()
                    latch.target_pos = origin_seat
                    latch.active = True
                    latch.sync()
                controller.step(max(0, between_moves_settle_steps))
                settled_pin_pos = entity_pos(pin)
                placement_error_xy = float(
                    np.linalg.norm(settled_pin_pos[:2] - drop_target[:2])
                )
                move_succeeded = bool(
                    result.success and placement_error_xy <= placement_tolerance_xy
                )
                print(
                    "untangle_physical_handle_demo physical_move "
                    f"move={move_index + 1} attempt={attempt} "
                    f"success={move_succeeded} grasped={result.grasped} "
                    f"placement_error_xy={placement_error_xy:.4f} "
                    f"failure_reason={result.failure_reason}",
                    flush=True,
                )
                if move_succeeded:
                    break
            if not move_succeeded:
                all_physical_moves_succeeded = False
                failure_reason = (
                    result.failure_reason
                    if not result.success
                    else (
                        "placement_check_failed:"
                        f" placement_error_xy={placement_error_xy:.4f}"
                        f" tolerance={placement_tolerance_xy:.4f}"
                    )
                )
                break
            _, reward, terminated, truncated, info = topology_env.step(command.action)
            moves_completed += 1
            print(
                "untangle_physical_handle_demo topology "
                f"reward={reward:+.3f} terminal={terminated} truncated={truncated} "
                f"state={info['topology_state']}",
                flush=True,
            )
            if terminated:
                break
            if truncated:
                failure_reason = "max_moves_reached"
                break

    if probe is not None:
        probe.uninstall()
    final_state = topology_env.topology_state()
    # Exclude reset_home (a set_dofs_position teleport) from the dataset: it is
    # post-task cleanup, not demonstration, and its implied action is an
    # un-replayable jump.
    if dataset_writer is not None:
        dataset_writer.stop_capture()
    controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)
    task_success = bool(final_state.is_terminal)
    metrics = {
        "task_success": bool(task_success),
        "physical_success": bool(all_physical_moves_succeeded),
        "terminal": bool(final_state.is_terminal),
        "crossings": int(len(final_state.crossings)),
        "knots": int(len(final_state.knots)),
        "endpoint_overlaps": int(len(final_state.endpoint_overlaps)),
        "moves_completed": int(moves_completed),
        "max_moves": int(args.max_moves),
    }
    episode_result = (
        EpisodeResult.ok(
            episode_spec.key,
            metrics=metrics,
            export_ready=True,
        )
        if task_success
        else EpisodeResult.failed(
            episode_spec.key,
            failure_reason or "untangle_not_terminal",
            metrics=metrics,
            stable_ready=False,
        )
    )
    print(
        "untangle_physical_handle_demo result "
        f"episode_id={episode_spec.stable_id()} success={episode_result.success} "
        f"task_success={task_success} "
        f"physical_success={all_physical_moves_succeeded} "
        f"stable_ready={episode_result.stable_ready} "
        f"export_ready={episode_result.export_ready} "
        f"terminal={final_state.is_terminal} "
        f"crossings={len(final_state.crossings)} "
        f"knots={len(final_state.knots)} moves_completed={moves_completed} "
        f"failure_reason={episode_result.failure_reason}",
        flush=True,
    )
    return episode_result


def main() -> None:
    args = parse_args()
    if args.max_moves <= 0:
        raise SystemExit("--max-moves must be positive.")
    if args.max_grasp_attempts is not None and args.max_grasp_attempts <= 0:
        raise SystemExit("--max-grasp-attempts must be positive.")
    if (
        args.between_moves_settle_steps is not None
        and args.between_moves_settle_steps < 0
    ):
        raise SystemExit("--between-moves-settle-steps must be nonnegative.")
    cfg = load_configs(args)
    if args.randomize_layout:
        from topogym.generation.layout_randomization import randomize_task_cfg

        cfg = randomize_task_cfg(
            cfg, str(cfg.task.task.id), args.seed, difficulty=args.difficulty
        )
        print(
            f"untangle_physical_handle_demo randomize_layout=on seed={args.seed} "
            f"difficulty={args.difficulty}",
            flush=True,
        )
    episode_spec = build_untangle_episode_spec(
        cfg,
        seed=args.seed,
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
        variant_id=args.variant_id,
    )
    if args.verbose:
        print(
            "untangle_physical_handle_demo runtime "
            f"python={sys.executable} "
            f"genesis={getattr(gs, '__version__', '<unknown>')} "
            f"genesis_path={Path(gs.__file__).resolve()}",
            flush=True,
        )
    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if args.viewer and not has_display:
        raise SystemExit("No graphical display detected.")
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[cfg.env.genesis.backend],
        precision=cfg.env.genesis.precision,
        logging_level=cfg.env.genesis.logging_level,
    )
    print(
        "untangle_physical_handle_demo building_scene "
        f"backend={cfg.env.genesis.backend} viewer={args.viewer} lite={args.lite}",
        flush=True,
    )
    scene = UntangleSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        show_viewer=args.viewer,
        include_robot=True,
    )
    print("untangle_physical_handle_demo scene_ready", flush=True)
    controller = initialize_franka_controller(
        scene=scene.scene,
        manifest=scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    print(
        "untangle_physical_handle_demo robot_home_ready "
        f"hand={controller.hand_pos().tolist()}",
        flush=True,
    )
    # ``status`` is created here (not in run_demo) so the dataset writer's
    # subgoal labels can read the live phase/move during the run.
    status: dict = {}
    dataset_writer_cm = dataset_writer_or_null(
        args.record_dataset,
        scene=scene.scene,
        cameras=scene.cameras,
        controller=controller,
        spec=episode_spec,
        plan=None,  # untangle plans per-move; no single episode plan
        task_goal="Untangle the ropes into their target holes.",
        every_n_steps=args.dataset_every_n_steps,
        subgoal_label_fn=lambda: f"{status.get('phase', 'setup')}:{status.get('move', '')}",
    )
    with dataset_writer_cm as dataset_writer:
        episode_result = run_demo(
            args,
            cfg,
            scene,
            controller,
            episode_spec=episode_spec,
            status=status,
            dataset_writer=dataset_writer,
        )
        if dataset_writer is not None:
            dataset_writer.finalize(episode_result)
            print(f"saved dataset -> {args.record_dataset}", flush=True)
    print_recording_saved(cfg.recording)
    keep_open = bool(args.viewer and not args.close_on_finish)
    if keep_open:
        print("untangle_physical_handle_demo viewer_hold; press Ctrl+C to exit", flush=True)
    while keep_open:
        try:
            scene.scene.step()
        except gs.GenesisException as exc:
            if "Viewer closed" in str(exc):
                print("untangle_physical_handle_demo viewer_closed; exiting", flush=True)
                break
            raise


if __name__ == "__main__":
    main()
