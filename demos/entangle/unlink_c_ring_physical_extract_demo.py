"""Take the C ring off the closed ring, and judge whether it really came off.

The motion is the one `tests/check_c_ring_clearance.py` measured before any of this
was built: roll the C about the bar it hangs on until its opening faces the bar, draw
it straight down 18 mm so the bar leaves through the opening, carry it clear along the
bar, set it down.

**Read this before trusting the result.** The ring is carried by an assisted
attachment, which writes its pose every step. That means a wrong trajectory does not
jam -- it tunnels. The 8.75-9.00 mm of interlock the offline gate measured blocking
every non-gateway path is real geometry, but nothing in the solver enforces it while
the attachment is driving. Two consequences:

- The judge is the topology reading, not the collision. `verification/` decides.
- The end state cannot tell the two apart on its own. Tunnel through the ring and
  carry the C 90 mm away and it reads unlinked, because it is. So this demo watches
  the surface clearance every step and hands the minimum to the verifier as
  `min_gap_seen`; a path that went through the ring is rejected on that, not on where
  it finished.

`run.oracle_mode=no_align` is the contrast: same grasp, same descent, same carry, and
an opening that was never brought onto the bar. It is expected to execute cleanly and
to be judged a failure.

    python -m demos.entangle.unlink_c_ring_physical_extract_demo run.build_only=true
    python -m demos.entangle.unlink_c_ring_physical_extract_demo run.verbose=true
    python -m demos.entangle.unlink_c_ring_physical_extract_demo run.oracle_mode=no_align
    python -m demos.entangle.unlink_c_ring_physical_extract_demo run.viewer=true run.keep_open=true
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig, OmegaConf

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.primitives import (
    AttachmentManager,
    GatewayExtractPrimitive,
    configure_gripper_contact_friction,
    entity_pos,
    entity_quat,
    face_on_quat,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import UnlinkCRingSceneBuilder
from topogym.tasks.entangle import _c_ring_geometry as ring_geometry
from topogym.tasks.entangle._c_ring_travel_probe import free_translation_probe
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import (
    UnlinkCRingPuzzleEvaluator,
    c_ring_frame,
    opening_to_bar_deg,
)


@contextmanager
def watch_surface_gap(ring_scene, status):
    """Record the smallest clearance the two chains ever have.

    Wraps `scene.step` the way the recorder and the attachment manager do, so every
    caller -- the controller, the primitive, the probe -- feeds it without knowing.
    Costs 0.28 ms a step against a 1 ms step, which is worth paying for the one
    reading that distinguishes the gateway from a tunnel.
    """

    geometry = ring_scene.geometry
    fixed_axes = geometry.fixed_axes()
    scene = ring_scene.scene
    original_step = scene.step
    seen = {"min_gap": float("inf")}

    def wrapped_step(*args, **kwargs):
        result = original_step(*args, **kwargs)
        gap = ring_geometry.surface_gap(fixed_axes, geometry.c_axes(c_ring_frame(ring_scene)))
        if gap < seen["min_gap"]:
            seen["min_gap"] = gap
            status["min_gap"] = gap
        return result

    scene.step = wrapped_step
    try:
        yield seen
    finally:
        scene.step = original_step


def _hud(ring_scene, evaluator, status):
    """Live readings on every rendered frame.

    Re-reading the topology per frame rather than echoing the last logged value is
    what makes the video legible: the interlock reading flips the instant the bar
    leaves the opening, and that frame is the one worth watching. It costs 4.7 ms a
    render against a 1 ms step, paid only on frames that are actually captured.
    """

    def render_lines():
        state = evaluator.classify(ring_scene)
        return [
            "task=unlink_c_ring",
            f"phase={status.get('phase', '-')}",
            f"mode={status.get('mode', 'gateway')}",
            f"Lk={state.linking:+.1f}",
            f"opening_to_bar={state.opening_to_bar_deg:.0f}deg",
            f"min_gap={status.get('min_gap', 0.0) * 1000:+.1f}mm",
            # A push that is being resisted looks like nothing happening; the number
            # is the only evidence a force was applied at all.
            status.get("probe", ""),
        ]

    return render_lines


def approach_axis(ring_scene, mount_pos) -> np.ndarray:
    """Which way the fingers point: along the C's normal, away from the robot.

    The C's normal has two signs and only one of them has the arm reaching outward
    rather than through its own base, so the sign is chosen against the robot mount
    instead of being written into config where a change of `hang_yaw_deg` would
    silently invert it.
    """

    geometry = ring_scene.geometry
    axis = np.asarray(geometry.tube_direction, dtype=float)
    mount = np.asarray(OmegaConf.to_container(mount_pos), dtype=float)[:2]
    outward = geometry.c_rest_frame.center[:2] - mount
    return axis if float(np.dot(axis[:2], outward)) >= 0.0 else -axis


def configure_contacts(cfg, ring_scene, controller) -> None:
    """Apply the configured friction to the C ring and the fingers.

    From `main` rather than `run_demo` so a build-only look settles under the same
    friction the episode runs on.
    """

    physical = cfg.task.physical
    configure_gripper_contact_friction(
        entities=[ring_scene.c_ring_entity()],
        robot=controller.robot,
        finger_links=list(physical.finger_links),
        object_friction=float(physical.c_ring_friction),
        finger_friction=float(physical.finger_friction),
    )


def build_primitive(cfg) -> GatewayExtractPrimitive:
    spec = cfg.task.primitive
    min_finger = spec.min_finger_qpos
    return GatewayExtractPrimitive(
        steps_per_phase=int(spec.steps_per_phase),
        gripper_steps=int(spec.gripper_steps),
        approach_clearance=float(spec.approach_clearance),
        retreat_clearance=float(spec.retreat_clearance),
        grasp_qpos=float(spec.grasp_qpos),
        close_hold_steps=int(spec.close_hold_steps),
        align_steps=int(spec.align_steps),
        align_settle_steps=int(spec.align_settle_steps),
        extract_steps=int(spec.extract_steps),
        release_hold_steps=int(spec.release_hold_steps),
        min_finger_qpos=None if min_finger is None else float(min_finger),
        max_grasp_pos_error=float(spec.max_grasp_pos_error),
        max_align_deg=float(spec.max_align_deg),
        verbose=bool(cfg.run.verbose),
    )


def run_demo(cfg, ring_scene, controller, *, episode_key, mode, status) -> EpisodeResult:
    print_collision_il_contract(
        "unlink_c_ring_physical_extract_demo",
        manipulated=["c_ring"],
        runtime_attachment=True,
        runtime_set_pose=False,
        success_checks=(
            "finger_qpos",
            "opening_to_bar",
            "min_gap_seen",
            "linking_number",
            "free_translation",
            "release_stable",
        ),
    )

    layout = ring_scene.layout
    geometry = ring_scene.geometry
    spec = cfg.task.primitive
    physical = cfg.task.physical
    evaluator = UnlinkCRingPuzzleEvaluator.from_config(cfg.task)
    c_ring = ring_scene.c_ring_entity()

    # Aim at where the ring actually settled, not at where it was spawned.
    settled = c_ring_frame(ring_scene)
    grasp_point = settled.point(
        np.deg2rad(float(spec.grasp_azimuth_deg)), geometry.c_ring.major_radius
    )[0]
    axis, rotation_deg = geometry.align_rotation()
    # Come in face-on to the C, tool axis along the C's own normal, pointed away from
    # the robot. That makes the extraction's turn a roll about the tool axis -- one
    # wrist joint -- instead of tipping the whole hand over, which is the single
    # biggest thing the flat-ring layout bought.
    tool_axis = approach_axis(ring_scene, cfg.common.robot_setup.mount.pos)
    ee_quat = face_on_quat(
        controller.default_ee_quat, tool_axis, float(spec.grasp_roll_deg)
    )

    primitive = build_primitive(cfg)
    if stop_before_physics(cfg, ring_scene.scene, "unlink_c_ring_physical_extract_demo"):
        raise SystemExit(0)

    with watch_surface_gap(ring_scene, status) as gap_watch:
        with AttachmentManager(ring_scene.scene) as attachment_manager:
            held: list = []

            def attach_ring():
                attachment = attachment_manager.create(
                    entity=c_ring,
                    parent_pos_fn=controller.hand_pos,
                    offset=entity_pos(c_ring) - np.asarray(controller.hand_pos(), dtype=float),
                    quat=entity_quat(c_ring),
                    # Rigid in the hand's frame: the wrist's 90 degree turn is what
                    # turns the ring, which is the whole point of the motion.
                    parent_quat_fn=controller.hand_quat,
                )
                attachment.attach()
                held.append(attachment)
                status["phase"] = "carrying"
                return attachment

            def release_ring():
                status["phase"] = "released"
                for attachment in held:
                    attachment.release(sync=False)
                    attachment_manager.attachments.remove(attachment)
                held.clear()

            def align_probe() -> float:
                reading = opening_to_bar_deg(geometry, c_ring_frame(ring_scene))
                status["align_deg"] = reading
                return reading

            status["phase"] = "extract" if mode == "gateway" else "no_align"
            result = primitive.run(
                controller,
                part=c_ring,
                grasp_pos=layout.position_to_world(grasp_point),
                rotation_axis=axis,
                rotation_deg=rotation_deg,
                extract_delta=(0.0, 0.0, -geometry.extract_travel),
                # Radially outward, away from the closed ring's centre. Along the
                # bar instead would curve back under the far rim.
                clear_delta=tuple(float(spec.carry) * geometry.hang_direction),
                place_delta=(0.0, 0.0, -float(spec.place_drop)),
                ee_quat=ee_quat,
                align_probe=align_probe,
                attach_fn=attach_ring,
                release_fn=release_ring,
                skip_align=(mode != "gateway"),
            )

            # Released, the ring has to COME TO REST -- not to stay where it was
            # put. A freed C ring is a ring standing on its edge, so letting go of it
            # drops it flat: about 31 mm down and 35 mm sideways. That is what
            # setting a ring down looks like, and failing the episode on it would be
            # judging the scene, not the run. What must not happen is that it never
            # stops (rolling off the board) or that the reading changes. So the
            # measurement is the displacement over the LAST window of the check.
            status["phase"] = "release_check"
            pre = evaluator.classify(ring_scene, min_gap_seen=gap_watch["min_gap"])
            settle_window = int(physical.release_settle_window)
            controller.step(max(0, int(physical.release_check_steps) - settle_window))
            before = entity_pos(c_ring)
            controller.step(settle_window)
            drift = float(np.linalg.norm(entity_pos(c_ring) - before))
            post = evaluator.classify(ring_scene, min_gap_seen=gap_watch["min_gap"])
            release_stable = bool(
                drift <= float(physical.release_max_drift) and post.unlinked == pre.unlinked
            )
            status["linking"] = post.linking

            # The physical recheck the C3 contract asks for: can it now be pushed
            # away in every direction that used to be blocked?
            status["phase"] = "travel_probe"
            probe_cfg = cfg.task.travel_test
            travel = free_translation_probe(
                ring_scene.scene,
                c_ring,
                link_idx=ring_scene.c_ring_link_idx(),
                geometry=geometry,
                mass=float(cfg.task.c_ring.mass),
                force_scale=float(probe_cfg.force_scale),
                steps=int(probe_cfg.steps),
                free_travel=float(probe_cfg.free_travel),
                settle_steps=int(probe_cfg.settle_steps),
                on_step=lambda force, moved: status.update(
                    probe=f"push {force:.2f}N  travel {moved * 1000:5.1f}mm"
                ),
            )

    state = evaluator.classify(
        ring_scene,
        min_gap_seen=gap_watch["min_gap"],
        travel=travel,
        release_stable=release_stable,
    )
    status["phase"] = "done"
    status["linking"] = state.linking

    metrics = {
        "physical_success": bool(result.success),
        "linking_number": float(state.linking),
        "unlinked": bool(state.unlinked),
        "surface_gap": float(state.surface_gap),
        "min_gap_seen": float(gap_watch["min_gap"]),
        "passed_through": bool(state.passed_through),
        "travel_free": bool(state.travel_free),
        "min_peak_travel": float(travel.min_peak_travel),
        "release_stable": bool(release_stable),
        "release_settle_drift": drift,
        "finger_qpos": float(result.finger_qpos),
        "grasp_pos_error": float(result.grasp_pos_error),
        "align_deg": float(result.align_deg),
        "worst_pose_error": float(result.worst_pose_error),
        "worst_tilt_deg": float(np.rad2deg(result.worst_tilt_rad)),
        "oracle_mode": mode,
    }

    task_success = bool(state.is_terminal)
    if task_success:
        episode_result = EpisodeResult.ok(
            episode_key, metrics=metrics, export_ready=bool(result.success)
        )
    else:
        episode_result = EpisodeResult.failed(
            episode_key,
            result.failure_reason
            or (
                "c_ring_passed_through_the_closed_ring"
                if state.passed_through
                else f"c_ring_still_linked(Lk={state.linking:+.1f})"
            ),
            metrics=metrics,
            stable_ready=False,
        )

    # The leading space on ` success=` is what `stability_sweep.sh` greps for; it is
    # deliberately distinct from `physical_success=`.
    print(
        "unlink_c_ring_physical_extract_demo result "
        f"mode={mode} success={episode_result.success} "
        f"Lk={state.linking:+.1f} unlinked={state.unlinked} "
        f"passed_through={state.passed_through} min_gap_seen={gap_watch['min_gap'] * 1000:+.2f}mm "
        f"travel_free={state.travel_free} min_peak_travel={travel.min_peak_travel * 1000:.1f}mm "
        f"blocked={','.join(travel.blocked) or 'none'} "
        f"release_stable={release_stable} settle_drift={drift:.5f} "
        f"finger_qpos={result.finger_qpos:.4f} align={result.align_deg:.2f}deg "
        f"pose_err={result.worst_pose_error:.4f} "
        f"wrist_tilt={np.rad2deg(result.worst_tilt_rad):.2f}deg "
        f"failure_reason={episode_result.failure_reason} "
        f"phases={len(result.completed_phases)}/{len(GatewayExtractPrimitive.NOMINAL_PHASES)}",
        flush=True,
    )
    if state.judge_disagrees:
        print(
            "[warn] the reading says unlinked but the ring would not move: the judge "
            "is wrong, not the run. Check the canonical closure and the projection.",
            flush=True,
        )
    if state.probe_uninformative:
        print(
            "[warn] the ring travelled freely while still reading linked -- the push "
            "overpowered the interlock. Lower task.travel_test.force_scale.",
            flush=True,
        )
    if result.worst_tilt_rad > np.deg2rad(5.0):
        print(
            f"[warn] the wrist lagged its commanded pose by up to "
            f"{np.rad2deg(result.worst_tilt_rad):.1f} deg. The turn is meant to be a "
            "roll about the tool axis (joint 7), so a large lag means the approach "
            "pose is off: check task.primitive.grasp_roll_deg and that the tool axis "
            "really lines up with the C ring's normal.",
            flush=True,
        )
    if cfg.run.verbose:
        print(f"unlink_c_ring topology {state.to_info()}", flush=True)
    return episode_result


@hydra.main(
    version_base="1.3", config_path="../../configs", config_name="unlink_c_ring_extract"
)
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"unlink_c_ring_config -> {resolved}", flush=True)

    mode = cfg.run.oracle_mode or str(cfg.task.oracle.mode)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision)
    )

    builder = UnlinkCRingSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    ring_scene = builder.build(show_viewer=show_viewer)
    geometry = ring_scene.geometry

    controller = initialize_franka_controller(
        scene=ring_scene.scene,
        manifest=ring_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_contacts(cfg, ring_scene, controller)

    axis, rotation_deg = geometry.align_rotation()
    print(
        "unlink_c_ring setup "
        f"mode={mode} "
        f"grasp_azimuth={float(cfg.task.primitive.grasp_azimuth_deg):.0f}deg "
        f"turn={rotation_deg:.0f}deg about ({axis[0]:+.2f},{axis[1]:+.2f},{axis[2]:+.2f}) "
        f"extract={geometry.extract_travel * 1000:.0f}mm "
        f"carry={float(cfg.task.primitive.carry) * 1000:.0f}mm "
        f"opening_to_bar={opening_to_bar_deg(geometry, geometry.c_rest_frame):.1f}deg",
        flush=True,
    )

    episode_key = EpisodeKey(task_id="unlink_c_ring", seed=int(cfg.run.seed))
    evaluator = UnlinkCRingPuzzleEvaluator.from_config(cfg.task)
    status = {"phase": "home", "mode": mode, "linking": 0.0, "align_deg": 0.0, "min_gap": 0.0}

    with recording_session_from_config(
        ring_scene.scene,
        ring_scene.cameras,
        cfg.recording,
        hud=_hud(ring_scene, evaluator, status),
    ):
        run_demo(cfg, ring_scene, controller, episode_key=episode_key, mode=mode, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ring_scene.scene.step()


if __name__ == "__main__":
    main()
