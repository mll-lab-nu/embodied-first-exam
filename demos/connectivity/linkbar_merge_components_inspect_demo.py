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
3. What does the travel test read? Latched into B1 the carriage cannot run; latched
   into A2, or not latched, it goes to the end of its rail. The gap between those
   two numbers is what `success.max_travel` gets set from, so it is measured here
   rather than guessed.

The joint sweep and the seat phases write the joint directly. That is a kinematic
check, NOT an episode, and nothing in an episode may move the beam that way
(`docs/develop/tasks/rigid_first_track_zh.md` section 3.1).

    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.static_only=true run.viewer=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.sweep_joint=true run.verbose=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.seat_phase=b1 run.travel_probe=true run.verbose=true
    python -m demos.connectivity.linkbar_merge_components_inspect_demo run.seat_phase=none run.travel_probe=true
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
from topogym.primitives.pick_place import HAND_TO_PAD_Z
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

SEAT_PHASES = ("none", "b1", "a2", "angle")

# How much room the pads need over the knob's cap while the gripper traverses to it
# at `motion.approach_z`. The approach ends directly over the knob, so this is the
# clearance that decides whether the trip brushes the beam -- and the fingertips sit
# about another 10 mm below the pad centre, so the pad figure is the one to gate on.
# Measured 2026-08-22: 16 mm of pad clearance left roughly 6 mm at the fingertips,
# the traverse pushed the beam 2.49 degrees toward A2, and the gripper then closed
# on empty air. It regressed silently when the coupling height was raised and
# `approach_z` was not, which is why it is checked rather than remembered.
_APPROACH_PAD_CLEARANCE_M = 0.030

# How far the parked hand's axis has to be from the knob's circle. The arm sits at
# its home pose for the whole sweep, and an open gripper reaches about 40 mm to
# either side of that axis, so a hand parked near the circle is something the beam
# has to push through. Measured 2026-08-20: 37 mm fouled the beam at ~20 N and
# stalled it 8 degrees short; 77 mm is clear. This is a "does the arm sit in the
# way at all" cutoff rather than a design dial, so it stays here rather than in
# config -- and it exists because finding this out cost two sweeps.
_HOME_RADIAL_CLEARANCE_M = 0.060


def _hud(state):
    def render_lines():
        return [
            "task=linkbar_merge_components",
            f"phase={state.get('phase', '-')}",
            f"angle={np.rad2deg(state.get('angle', 0.0)):+.1f}deg",
            f"latched={state.get('latched', None)}",
            state.get("probe", ""),
        ]

    return render_lines


def b_xy(merge_scene) -> np.ndarray:
    """The carriage's catch, for measuring whether the beam walked it out of place.

    On a rail it can only move along one line, which is the point of the rail -- but
    the pin brushing a jaw can still run the carriage down it, and the catch has only
    4 mm of side clearance, so the drift is worth reading rather than assuming.
    """

    return np.asarray(merge_scene.socket_seat_xy("b1"), dtype=float)


def make_latch(merge_scene, *, auto_capture: bool) -> SocketWeld:
    return SocketWeld(
        scene=merge_scene.scene,
        moving_link_idx=merge_scene.beam_link_idx(),
        sockets={name: merge_scene.socket_link_idx(name) for name in LINKBAR_SOCKETS},
        seat_xy_fn=merge_scene.socket_seat_xy,
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
    b_start = b_xy(merge_scene)
    b_drift = 0.0
    for label, target in stations:
        state["phase"] = f"sweep:{label}"
        error = drive_joint(merge_scene, target, steps=steps, cfg=cfg)
        state["angle"] = merge_scene.arm_angle()
        worst = max(worst, abs(error))
        b_drift = max(b_drift, float(np.linalg.norm(b_xy(merge_scene) - b_start)))
        gaps = {name: float(np.linalg.norm(merge_scene.pin_xy() - merge_scene.socket_seat_xy(name)))
                for name in LINKBAR_SOCKETS}
        print(
            f"[sweep -> {label:4s}] target={np.rad2deg(target):+7.2f}deg "
            f"reached={np.rad2deg(merge_scene.arm_angle()):+7.2f}deg "
            f"error={np.rad2deg(error):+6.2f}deg "
            + " ".join(f"gap_{name}={gaps[name]*1000:6.1f}mm" for name in LINKBAR_SOCKETS)
            + f" touching={merge_scene.touching()}",
            flush=True,
        )
    print(
        f"linkbar_merge_components sweep worst_error_deg={np.rad2deg(worst):.2f} "
        f"capture_window_deg={layout.capture_tolerance_deg():.2f} "
        f"b_drift_mm={b_drift * 1000:.2f} "
        f"side_clearance_mm={float(cfg.task.socket.pin_clearance) * 1000:.1f} "
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
    b_start = b_xy(merge_scene)
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
        f"b_drift_mm={float(np.linalg.norm(b_xy(merge_scene) - b_start)) * 1000:.2f} "
        f"latched={latch.latched} checks={latch.capture_checks} "
        f"weld_pairs={sorted(merge_scene.weld_pairs())} "
        f"latched_readback={merge_scene.latched_socket()}",
        flush=True,
    )


def run_travel(cfg, merge_scene, state):
    """The physical recheck: push the carriage along its rail and see what holds it."""

    state["phase"] = "travel_probe"
    probe = cfg.task.travel_test
    layout = merge_scene.layout
    result = travel_probe(
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
        on_step=lambda force, moved: state.update(
            probe=f"push {force:.1f}N  travel {moved * 1000:5.1f}mm"
        ),
    )
    blocked = result.peak_travel <= float(cfg.task.success.max_travel)
    print(
        f"linkbar_merge_components travel latched={merge_scene.latched_socket()} "
        f"force={result.force:.3f}N steps={result.steps} "
        f"travel={result.travel:.4f}m peak={result.peak_travel:.4f}m "
        f"limit={result.limit:.4f}m reached_stop={result.reached_stop} "
        f"max_blocked={float(cfg.task.success.max_travel):.4f} "
        f"min_free={float(cfg.task.success.min_free_travel):.4f} blocked={blocked}",
        flush=True,
    )
    return result


def run_classify(cfg, merge_scene, travel_result) -> None:
    """Read the constraint graph, and check it against what the travel test saw.

    The peak travel is what the judge gets, not the final one: a carriage that is
    held still gives a little under load, and the peak is the honest reading.
    """

    state = LinkbarMergeEvaluator().classify(
        merge_scene,
        travel=None if travel_result is None else travel_result.peak_travel,
    )
    info = state.to_info()
    print(
        "linkbar_merge_components classify "
        + " ".join(
            f"{key}={info[key]}"
            for key in ("invariant", "invariant_value", "space", "component_count",
                        "latched_socket", "latch_edges", "travel_tested",
                        "motion_blocked",
                        "judge_disagrees", "probe_uninformative", "failure_label",
                        "terminal")
        ),
        flush=True,
    )
    if state.judge_disagrees:
        print(
            "[warn] the constraint graph says merged but the carriage travelled anyway. "
            "That means the JUDGE is wrong, not the run: check the weld set and the "
            "link -> assembly mapping in verification/linkbar_merge_components_verifier.py "
            "before touching the scene.",
            flush=True,
        )
    if state.probe_uninformative:
        print(
            "[warn] the carriage did not merge and did not travel either, so the push "
            "was too weak to judge with. Raise task.travel_test.force_scale until an "
            "unmerged carriage clears task.success.min_free_travel.",
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
    controller = initialize_franka_controller(
        scene=merge_scene.scene,
        manifest=merge_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0 if cfg.run.static_only else int(cfg.task.physical.settle_steps),
    )

    # Where the parked hand sits relative to the knob's circle. The beam sweeps
    # through every angle while the arm is parked, so a home pose that overlaps the
    # circle is an obstacle the beam has to push through -- `stacked_plate` hit the
    # same shared home and ended up needing its own raised one.
    hand = np.asarray(controller.hand_pos(), dtype=float).reshape(3)
    hand_task = hand - np.asarray(layout.task_origin, dtype=float)
    hand_radius = float(np.linalg.norm(hand_task[:2] - layout.pivot_xy))
    hand_angle = float(np.rad2deg(np.arctan2(
        hand_task[1] - layout.pivot_xy[1], hand_task[0] - layout.pivot_xy[0]
    )))
    radial_gap = abs(hand_radius - layout.knob_station)
    print(
        f"linkbar_merge_components home_clearance "
        f"hand_task=({hand_task[0]:+.4f},{hand_task[1]:+.4f},{hand_task[2]:+.4f}) "
        f"hand_radius={hand_radius:.4f} hand_angle={hand_angle:+.1f}deg "
        f"knob_station={layout.knob_station:.4f} "
        f"radial_gap={radial_gap:.4f} "
        f"knob_top_z={layout.knob_top_z:.4f} "
        f"vertical_gap={hand_task[2] - layout.knob_top_z:+.4f}",
        flush=True,
    )
    if radial_gap < _HOME_RADIAL_CLEARANCE_M:
        print(
            f"[warn] the parked hand sits {radial_gap * 1000:.1f} mm from the knob's "
            f"circle, under the {_HOME_RADIAL_CLEARANCE_M * 1000:.0f} mm an open "
            "gripper needs. Expect the sweep to stall against the arm rather than "
            "reach its target. Move task.pivot so the hand parks over the hub, or "
            "give this task its own raised home the way stacked_plate did -- do not "
            "edit the shared home.",
            flush=True,
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
    print(f"linkbar_merge_components heights {merge_scene.height_chain()}", flush=True)
    pad_z = float(cfg.task.motion.approach_z) - HAND_TO_PAD_Z
    approach_clearance = pad_z - layout.knob_cap_top_z
    print(
        "linkbar_merge_components approach_clearance "
        f"approach_z={float(cfg.task.motion.approach_z):.4f} pad_z={pad_z:.4f} "
        f"knob_cap_top={layout.knob_cap_top_z:.4f} "
        f"clearance={approach_clearance:+.4f}",
        flush=True,
    )
    if approach_clearance < _APPROACH_PAD_CLEARANCE_M:
        print(
            f"[warn] the pads pass {approach_clearance * 1000:.1f} mm over the knob on "
            f"the way to it, under the {_APPROACH_PAD_CLEARANCE_M * 1000:.0f} mm an open "
            "gripper needs. Expect the traverse to brush the beam and turn it before "
            "the grasp. Raise task.motion.approach_z, or lower the knob.",
            flush=True,
        )
    if not cfg.run.static_only:
        print(
            "linkbar_merge_components settle_check "
            f"angle={np.rad2deg(merge_scene.arm_angle()):+.2f}deg "
            f"(init={float(cfg.task.linkbar.init_angle_deg):+.2f}deg) "
            f"carriage={merge_scene.carriage_travel() * 1000:+.2f}mm "
            f"touching={merge_scene.touching()}",
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
                probe = run_travel(cfg, merge_scene, state) if cfg.run.travel_probe else None
                if cfg.run.classify:
                    run_classify(cfg, merge_scene, probe)
        # Hold the settled scene for the recording, for the same reason the merge
        # demo does: a video that stops on the last measured frame shows nothing.
        state["phase"] = "done"
        for _ in range(int(getattr(cfg.run, "final_hold_steps", 0) or 0)):
            merge_scene.scene.step()

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        merge_scene.scene.step()


if __name__ == "__main__":
    main()
