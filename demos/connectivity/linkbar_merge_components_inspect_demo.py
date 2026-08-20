"""Look at the Linkbar Merge Components frames, and latch the beam into either catch.

Stage-1 demo: no robot motion, no knob turn. It answers the geometry questions the
scene has to get right before a primitive is worth writing, and answers them as
numbers rather than by eye:

1. Can the beam actually reach both catches? The joint is driven to each seat
   under position control, so anything the beam fouls on the way shows up as a
   tracking error instead of as a picture that looks fine.
2. Does the latch fire where it should, and only there? Seated at a catch it must
   engage; parked between them it must not. That window is the aiming requirement
   the whole task rests on.
3. What does the lift test read? Latched into B1, B has to stay down; latched into
   A2, or not latched, B has to come off the table. The gap between those two
   numbers is what `success.max_lift_delta` gets set from, so it is measured here
   rather than guessed.

The joint sweep and the seat phases write the joint directly. That is a kinematic
check, NOT an episode, and nothing in an episode may move the beam that way
(`docs/develop/tasks/rigid_first_track_zh.md` section 3.1).

    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.static_only=true run.viewer=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.sweep_joint=true run.verbose=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.seat_phase=b1 run.lift_probe=true run.verbose=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.seat_phase=none run.lift_probe=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.primitives import SocketWeld
from topogym.supervision import stop_before_physics
from topogym.tasks import LINKBAR_SOCKETS, LinkbarMergeSceneBuilder
from topogym.tasks.connectivity._lift_probe import lift_probe
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)

SEAT_PHASES = ("none", "b1", "a2", "angle")


def _hud(state):
    def render_lines():
        return [
            "task=linkbar_merge_components",
            f"phase={state.get('phase', '-')}",
            f"angle={np.rad2deg(state.get('angle', 0.0)):+.1f}deg",
            f"latched={state.get('latched', None)}",
        ]

    return render_lines


def make_latch(merge_scene, *, auto_capture: bool) -> SocketWeld:
    return SocketWeld(
        scene=merge_scene.scene,
        moving_link_idx=merge_scene.beam_link_idx(),
        sockets={
            name: (merge_scene.socket_link_idx(name),
                   merge_scene.layout.socket_center_xy(name))
            for name in LINKBAR_SOCKETS
        },
        pin_xy_fn=merge_scene.pin_xy,
        capture_tolerance_xy=merge_scene.layout.capture_tolerance_xy,
        auto_capture=auto_capture,
    )


def drive_joint(merge_scene, target: float, *, steps: int, cfg) -> float:
    """Servo the joint to ``target`` and report the residual error, in radians.

    Position control rather than `set_arm_angle`, because the question this answers
    is whether the beam can GET there: a written angle would teleport straight
    through anything in the way and report success.
    """

    entity = merge_scene.linkbar_entity()
    dof = [int(merge_scene.joint_dof)]
    servo = cfg.run.sweep_servo
    entity.set_dofs_kp([float(servo.kp)], dofs_idx_local=dof)
    entity.set_dofs_kv([float(servo.kv)], dofs_idx_local=dof)
    entity.set_dofs_force_range(
        [-float(servo.force)], [float(servo.force)], dofs_idx_local=dof
    )
    entity.control_dofs_position([float(target)], dofs_idx_local=dof)
    for _ in range(int(steps)):
        merge_scene.scene.step()
    return float(merge_scene.arm_angle() - float(target))


def run_sweep(cfg, merge_scene, state) -> None:
    """Drive the beam to each catch and back, and report what it cost to get there."""

    layout = merge_scene.layout
    steps = int(cfg.run.sweep_steps)
    stations = [("b1", layout.socket_angle("b1")),
                ("init", layout.init_angle),
                ("a2", layout.socket_angle("a2")),
                ("init", layout.init_angle)]
    worst = 0.0
    for label, target in stations:
        state["phase"] = f"sweep:{label}"
        error = drive_joint(merge_scene, target, steps=steps, cfg=cfg)
        state["angle"] = merge_scene.arm_angle()
        worst = max(worst, abs(error))
        gaps = {name: float(np.linalg.norm(merge_scene.pin_xy() - layout.socket_center_xy(name)))
                for name in LINKBAR_SOCKETS}
        print(
            f"[sweep -> {label:4s}] target={np.rad2deg(target):+7.2f}deg "
            f"reached={np.rad2deg(merge_scene.arm_angle()):+7.2f}deg "
            f"error={np.rad2deg(error):+6.2f}deg "
            + " ".join(f"gap_{name}={gaps[name]*1000:6.1f}mm" for name in LINKBAR_SOCKETS),
            flush=True,
        )
    print(
        f"linkbar_merge_components sweep worst_error_deg={np.rad2deg(worst):.2f} "
        f"capture_window_deg={layout.capture_tolerance_deg():.2f} "
        f"reached_both={bool(np.rad2deg(worst) <= float(cfg.run.sweep_tolerance_deg))}",
        flush=True,
    )


def seat_angle_for(cfg, layout) -> tuple[str, float]:
    """(label, joint angle) for the requested seat phase."""

    phase = str(cfg.run.seat_phase)
    if phase == "none":
        # Park at the start angle: the pin is in neither window, so the latch must
        # stay open. That is the control the other phases are read against.
        return phase, layout.init_angle
    if phase == "angle":
        # An arbitrary angle, for walking the edge of the capture window: sweep
        # `run.seat_angle_deg` across a seat and the latch should start firing
        # exactly where `capture_tolerance_deg` says it will.
        return phase, float(np.deg2rad(float(cfg.run.seat_angle_deg)))
    return phase, layout.socket_angle(phase)


def run_seat(cfg, merge_scene, latch, state) -> None:
    """Put the beam at the requested seat and let the latch decide what it sees."""

    layout = merge_scene.layout
    phase, angle = seat_angle_for(cfg, layout)
    state["phase"] = f"seat:{phase}"
    merge_scene.set_arm_angle(angle)
    state["angle"] = angle
    for _ in range(int(cfg.task.success.settle_steps)):
        merge_scene.scene.step()
    state["latched"] = latch.latched
    gaps = latch.gaps()
    print(
        f"linkbar_merge_components seat phase={phase} "
        f"angle={np.rad2deg(merge_scene.arm_angle()):+7.2f}deg "
        + " ".join(f"gap_{name}={gaps[name]*1000:6.1f}mm" for name in LINKBAR_SOCKETS)
        + f" capture={layout.capture_tolerance_xy*1000:.1f}mm "
        f"latched={latch.latched} checks={latch.capture_checks} "
        f"weld_pairs={sorted(merge_scene.weld_pairs())} "
        f"latched_readback={merge_scene.latched_socket()}",
        flush=True,
    )


def run_lift(cfg, merge_scene, state) -> None:
    """The physical recheck: pull B up and see whether anything holds it."""

    state["phase"] = "lift_probe"
    probe = cfg.task.lift_test
    result = lift_probe(
        merge_scene.scene,
        merge_scene.component_b_entity(),
        mass=float(cfg.task.component_b.mass),
        force_scale=float(probe.force_scale),
        steps=int(probe.steps),
        settle_steps=int(probe.settle_steps),
    )
    held = result.peak_delta_z <= float(cfg.task.success.max_lift_delta)
    print(
        f"linkbar_merge_components lift latched={merge_scene.latched_socket()} "
        f"force={result.force:.3f}N steps={result.steps} "
        f"delta={result.delta_z:+.4f}m peak={result.peak_delta_z:+.4f}m "
        f"max_held={float(cfg.task.success.max_lift_delta):.4f} "
        f"min_free={float(cfg.task.success.min_free_lift):.4f} held={held}",
        flush=True,
    )


@hydra.main(version_base="1.3", config_path="../../configs",
            config_name="linkbar_merge_components")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"linkbar_merge_components_config -> {resolved}", flush=True)

    phase = str(cfg.run.seat_phase)
    if phase not in SEAT_PHASES:
        raise SystemExit(f"Unknown run.seat_phase={phase!r}; expected one of {list(SEAT_PHASES)}.")

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = LinkbarMergeSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    merge_scene = builder.build(show_viewer=show_viewer)
    layout = merge_scene.layout

    # Hold the arm at its home pose. It takes no part in this demo, but a Franka
    # with no joint targets collapses under gravity on the first step.
    initialize_franka_controller(
        scene=merge_scene.scene,
        manifest=merge_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0 if cfg.run.static_only else int(cfg.task.physical.settle_steps),
    )

    print(
        "linkbar_merge_components setup "
        f"pivot=({layout.pivot_xy[0]:+.3f},{layout.pivot_xy[1]:+.3f}) "
        f"arm_radius={layout.arm_radius:.3f} "
        f"init={float(cfg.task.linkbar.init_angle_deg):+.1f}deg "
        f"b1={float(cfg.task.sockets.b1_angle_deg):+.1f}deg "
        f"a2={float(cfg.task.sockets.a2_angle_deg):+.1f}deg "
        f"capture={layout.capture_tolerance_xy * 1000:.1f}mm"
        f"({layout.capture_tolerance_deg():.2f}deg) "
        f"knob_grasp_z={layout.knob_grasp_z():.4f} "
        f"b1_owner={layout.socket_owner('b1')} a2_owner={layout.socket_owner('a2')}",
        flush=True,
    )

    if stop_before_physics(cfg, merge_scene.scene, "linkbar_merge_components_inspect_demo"):
        raise SystemExit(0)

    state = {"phase": "settle", "angle": layout.init_angle, "latched": None}
    with recording_session_from_config(
        merge_scene.scene, merge_scene.cameras, cfg.recording, hud=_hud(state)
    ):
        if cfg.run.static_only:
            # Build-and-look: no stepping at all, so the scene is inspected exactly
            # as constructed. Anything that interpenetrates at build time shows up
            # here rather than being hidden by the first settle.
            print("linkbar_merge_components static_only=true; not stepping.", flush=True)
        elif cfg.run.sweep_joint:
            # No auto-capture: a sweep that latched at the first seat it passed
            # could never report what the second one costs.
            with make_latch(merge_scene, auto_capture=False):
                run_sweep(cfg, merge_scene, state)
        else:
            with make_latch(merge_scene, auto_capture=True) as latch:
                run_seat(cfg, merge_scene, latch, state)
                if cfg.run.lift_probe:
                    run_lift(cfg, merge_scene, state)
        state["phase"] = "done"

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        merge_scene.scene.step()


if __name__ == "__main__":
    main()
