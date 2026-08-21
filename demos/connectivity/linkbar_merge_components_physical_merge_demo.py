"""Turn the beam into the catch that belongs to component B, and check the frames merged.

The episode docx 4.4 describes, end to end: the arm takes the beam's knob, sweeps
one arc, the latch fires where the pin seats, the arm retreats, and component B's
carriage is then pushed along its rail to see whether the two frames really are one.

Two rules run the same episode (`run.oracle_mode`):

    oracle          read which catch belongs to the other frame, go there
    nearest_socket  go to whichever catch is the shorter turn

Both reach a catch, both latch, both cost the same motion. Only the constraint
graph tells them apart, which is the point of the task -- and with the two catch
angles drawn independently on either side of the start, `nearest_socket` is right
half the time. `tests/check_linkbar_planner.py` settles that offline; this demo is
where it gets settled against physics.

`run.stage=rotate_only` stops after the sweep. That is the primitive's own
acceptance run -- reach, follow error, grip -- with no judging attached.

    python -m demos.connectivity.linkbar_merge_components_physical_merge_demo run.viewer=true
    python -m demos.connectivity.linkbar_merge_components_physical_merge_demo run.stage=rotate_only run.verbose=true
    python -m demos.connectivity.linkbar_merge_components_physical_merge_demo run.oracle_mode=nearest_socket
    python -m demos.connectivity.linkbar_merge_components_physical_merge_demo task.sockets.b1_angle_deg=-40 task.sockets.a2_angle_deg=50
    python -m demos.connectivity.linkbar_merge_components_physical_merge_demo --cfg job
"""

from __future__ import annotations

import os
from dataclasses import replace

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation import EpisodeKey, EpisodeResult
from topogym.planning import make_linkbar_rule
from topogym.primitives import (
    PivotLeverPrimitive,
    SocketWeld,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.supervision import stop_before_physics
from topogym.tasks import LINKBAR_SOCKETS, LinkbarMergeSceneBuilder
from topogym.tasks.connectivity._travel_probe import travel_probe
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import LinkbarMergeEvaluator

STAGES = ("full", "rotate_only")


def _hud(status):
    def render_lines():
        return [
            "task=linkbar_merge_components",
            f"phase={status.get('phase', '-')}",
            f"mode={status.get('mode', '-')}",
            f"target={status.get('target', '-')}",
            f"latched={status.get('latched', None)}",
            # A held carriage does not move, so without this the travel test looks
            # like nothing happening. The number is the evidence.
            status.get("probe", ""),
        ]

    return render_lines


def make_latch(merge_scene) -> SocketWeld:
    """The catches' snap-lock, armed before the sweep starts.

    Armed early on purpose: the latch has to fire the moment the pin reaches a
    seat, mid-sweep, the way a spring catch does. Arming it afterwards would make
    latching a thing the demo decided rather than a thing the mechanism did.
    """

    return SocketWeld(
        scene=merge_scene.scene,
        moving_link_idx=merge_scene.beam_link_idx(),
        sockets={name: merge_scene.socket_link_idx(name) for name in LINKBAR_SOCKETS},
        seat_xy_fn=merge_scene.socket_seat_xy,
        pin_xy_fn=merge_scene.pin_xy,
        capture_tolerance_xy=merge_scene.layout.capture_tolerance_xy,
        auto_capture=True,
    )


def build_primitive(cfg, layout) -> PivotLeverPrimitive:
    motion = cfg.task.motion
    return PivotLeverPrimitive(
        approach_z=layout.world_z(float(motion.approach_z)),
        retreat_z=layout.world_z(float(motion.retreat_z)),
        steps_per_phase=int(motion.steps_per_phase),
        steps_arc=int(motion.steps_arc),
        gripper_steps=int(motion.gripper_steps),
        grasp_qpos=float(motion.grasp_qpos),
        close_hold_steps=int(motion.close_hold_steps),
        arc_settle_steps=int(motion.arc_settle_steps),
        release_hold_steps=int(motion.release_hold_steps),
        target_tolerance=float(np.deg2rad(float(motion.target_tolerance_deg))),
        max_follow_error=float(motion.max_follow_error),
        max_lag=float(np.deg2rad(float(motion.max_lag_deg))),
        max_release_drift=float(np.deg2rad(float(motion.max_release_drift_deg))),
        min_finger_qpos=(
            None if motion.min_finger_qpos is None else float(motion.min_finger_qpos)
        ),
        verbose=bool(cfg.run.verbose),
    )


def run_episode(cfg, merge_scene, controller, *, episode_key, status) -> EpisodeResult:
    layout = merge_scene.layout
    status["mode"] = str(cfg.run.oracle_mode)

    print_collision_il_contract(
        "linkbar_merge_components_physical_merge_demo",
        manipulated=["linkbar"],
        runtime_attachment=False,
        runtime_set_pose=False,
        success_checks=("target_error", "finger_qpos", "component_count", "travel"),
    )

    rule = make_linkbar_rule(cfg.run.oracle_mode)
    plan = rule.decide(layout, merge_scene.arm_angle())
    # Deliberate under- or over-rotation, for contrast runs. Applied to the rule's
    # answer rather than inside the rule: the rule stays the oracle, and what is
    # being shown is an execution error on top of a correct plan.
    offset = float(np.deg2rad(float(getattr(cfg.run, "target_offset_deg", 0.0) or 0.0)))
    if offset != 0.0:
        plan = replace(
            plan,
            target_angle=plan.target_angle + offset,
            reason=f"{plan.reason}+offset{np.rad2deg(offset):+.0f}deg",
        )
    status["target"] = f"{plan.target_socket}@{np.rad2deg(plan.target_angle):+.1f}"
    print(
        f"linkbar_merge_components plan mode={cfg.run.oracle_mode} "
        f"target_socket={plan.target_socket} owner={layout.socket_owner(plan.target_socket)} "
        f"start={np.rad2deg(plan.start_angle):+.2f}deg "
        f"target={np.rad2deg(plan.target_angle):+.2f}deg "
        f"sweep={np.rad2deg(plan.sweep):+.2f}deg rotate={plan.rotate} "
        f"reason={plan.reason} prompt={str(cfg.task.command.prompt)!r}",
        flush=True,
    )

    if stop_before_physics(cfg, merge_scene.scene, "linkbar_merge_components_physical_merge_demo"):
        raise SystemExit(0)

    primitive = build_primitive(cfg, layout)
    evaluator = LinkbarMergeEvaluator()

    with make_latch(merge_scene) as latch:
        result = None
        if plan.rotate:
            status["phase"] = "rotate"
            result = primitive.run(
                controller,
                entity=merge_scene.linkbar_entity(),
                dof=merge_scene.joint_dof,
                pivot_xy=layout.position_to_world(
                    (layout.pivot_xy[0], layout.pivot_xy[1], 0.0)
                )[:2],
                radius=layout.knob_station,
                grasp_z=float(layout.knob_grasp_world(plan.start_angle)[2]),
                target_angle=plan.target_angle,
            )
            status["latched"] = latch.latched
            gaps = latch.gaps()
            print(
                "linkbar_merge_components rotate "
                f"success={result.success} start={np.rad2deg(result.start_angle):+.2f}deg "
                f"target={np.rad2deg(result.target_angle):+.2f}deg "
                f"final={np.rad2deg(result.final_angle):+.2f}deg "
                f"target_error={np.rad2deg(result.target_error):.2f}deg "
                f"follow_error={result.max_follow_error:.4f} "
                f"max_lag={np.rad2deg(result.max_lag):.2f}deg "
                f"release_drift={np.rad2deg(result.release_drift):.2f}deg "
                f"finger_qpos={result.finger_qpos:.4f} "
                f"phases={len(result.completed_phases)}/{len(PivotLeverPrimitive.NOMINAL_PHASES)} "
                f"reason={result.failure_reason} "
                + " ".join(f"gap_{name}={gaps[name] * 1000:.1f}mm" for name in LINKBAR_SOCKETS)
                + f" latched={latch.latched}",
                flush=True,
            )

        if str(cfg.run.stage) == "rotate_only":
            status["phase"] = "done"
            metrics = {
                "stage": "rotate_only",
                "rotate_success": bool(result is not None and result.success),
                "latched_socket": latch.latched,
            }
            return (
                EpisodeResult.ok(episode_key, metrics=metrics, export_ready=False)
                if metrics["rotate_success"]
                else EpisodeResult.failed(
                    episode_key, "rotate_check_failed", metrics=metrics, stable_ready=False
                )
            )

        # The physical recheck runs with the arm clear and the mechanism left as the
        # episode left it. Disarm capture first: the probe runs the carriage down its
        # rail, and a latch still watching for a seat would be watching a moving one.
        latch.auto_capture = False
        status["phase"] = "travel_probe"
        probe = cfg.task.travel_test
        travel = travel_probe(
            merge_scene.scene,
            merge_scene.component_b_entity(),
            dof=merge_scene.carriage_dof,
            link_idx=merge_scene.carriage_link_idx(),
            direction=np.append(layout.rail_direction_world(), 0.0),
            mass=float(cfg.task.component_b.mass),
            force_scale=float(probe.force_scale),
            steps=int(probe.steps),
            limit=layout.rail_travel,
            settle_steps=int(probe.settle_steps),
            on_step=lambda force, moved: status.update(
                probe=f"push {force:.1f}N  travel {moved * 1000:5.1f}mm"
            ),
        )

    status["phase"] = "verify"
    state = evaluator.classify(
        merge_scene,
        travel=travel.peak_travel,
        rotate_ok=bool(result is None or result.success),
    )
    info = state.to_info()
    print(
        "linkbar_merge_components result "
        f"mode={cfg.run.oracle_mode} planned={plan.target_socket} "
        f"latched={info['latched_socket']} "
        f"component_count={info['component_count']} "
        f"travel={travel.peak_travel:.4f}m of {travel.limit:.4f}m "
        f"motion_blocked={info['motion_blocked']} "
        f"rotate_ok={info['rotate_ok']} "
        f"task_success={info['terminal']} failure={info['failure_label']}",
        flush=True,
    )
    if state.judge_disagrees:
        print(
            "[warn] the constraint graph says merged but the carriage travelled anyway. "
            "That means the JUDGE is wrong, not the run: check the weld set and the "
            "link -> assembly mapping before touching the scene.",
            flush=True,
        )
    if state.probe_uninformative:
        print(
            "[warn] the carriage neither merged nor travelled, so the push was too weak "
            "to judge with. Raise task.travel_test.force_scale.",
            flush=True,
        )
    if cfg.run.verbose:
        print(f"linkbar_merge_components topology {info}", flush=True)

    metrics = {
        "stage": "full",
        "task_success": bool(state.is_terminal),
        "component_count": int(state.component_count),
        "latched_socket": state.latched_socket,
        "planned_socket": plan.target_socket,
        "travel": float(travel.peak_travel),
        "travel_limit": float(travel.limit),
        "motion_blocked": bool(state.motion_blocked),
        "rotate_ok": bool(state.rotate_ok),
        "target_error_deg": (
            None if result is None else float(np.rad2deg(result.target_error))
        ),
        "finger_qpos": None if result is None else float(result.finger_qpos),
        "judge_disagrees": bool(state.judge_disagrees),
    }
    # Hold the settled scene for the recording. Nothing is measured here -- the
    # verdict is already in -- but a video that cuts on the frame the verdict lands
    # gives the viewer nothing to look at.
    status["phase"] = "done"
    for _ in range(int(getattr(cfg.run, "final_hold_steps", 0) or 0)):
        merge_scene.scene.step()

    if state.is_terminal:
        return EpisodeResult.ok(
            episode_key, metrics=metrics, export_ready=bool(state.rotate_ok)
        )
    return EpisodeResult.failed(
        episode_key, state.failure_label or "unknown", metrics=metrics, stable_ready=False
    )


@hydra.main(version_base="1.3", config_path="../../configs",
            config_name="linkbar_merge_components_merge")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"linkbar_merge_components_config -> {resolved}", flush=True)

    stage = str(cfg.run.stage)
    if stage not in STAGES:
        raise SystemExit(f"Unknown run.stage={stage!r}; expected one of {list(STAGES)}.")

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)],
            precision=str(cfg.env.genesis.precision))

    builder = LinkbarMergeSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    merge_scene = builder.build(show_viewer=show_viewer)
    layout = merge_scene.layout

    controller = initialize_franka_controller(
        scene=merge_scene.scene,
        manifest=merge_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_gripper_contact_friction(
        entities=[merge_scene.linkbar_entity()],
        robot=controller.robot,
        finger_links=list(cfg.task.motion.finger_links),
        object_friction=float(cfg.task.motion.knob_friction),
        finger_friction=float(cfg.task.motion.finger_friction),
    )

    print(
        "linkbar_merge_components setup "
        f"pivot=({layout.pivot_xy[0]:+.3f},{layout.pivot_xy[1]:+.3f}) "
        f"arm_radius={layout.arm_radius:.3f} knob_station={layout.knob_station:.3f} "
        f"init={float(cfg.task.linkbar.init_angle_deg):+.1f}deg "
        f"b1={float(cfg.task.sockets.b1_angle_deg):+.1f}deg "
        f"a2={float(cfg.task.sockets.a2_angle_deg):+.1f}deg "
        f"capture={layout.capture_tolerance_deg():.2f}deg "
        f"tolerance={float(cfg.task.motion.target_tolerance_deg):.2f}deg "
        f"stage={stage} mode={cfg.run.oracle_mode}",
        flush=True,
    )

    episode_key = EpisodeKey(task_id="linkbar_merge_components", seed=int(cfg.run.seed))
    status = {"phase": "home", "mode": "-", "target": "-", "latched": None}
    with recording_session_from_config(
        merge_scene.scene, merge_scene.cameras, cfg.recording, hud=_hud(status)
    ):
        run_episode(cfg, merge_scene, controller, episode_key=episode_key, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        merge_scene.scene.step()


if __name__ == "__main__":
    main()
