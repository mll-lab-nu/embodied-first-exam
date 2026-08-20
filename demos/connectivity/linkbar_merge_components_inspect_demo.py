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
from topogym.verification import LinkbarMergeEvaluator

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


def b_xy(merge_scene) -> np.ndarray:
    """Component B's position, for measuring whether the beam walked it out of place.

    B is a free body on purpose -- the lift test needs it to be -- so the pin
    brushing a jaw on the way in can shove it. Its catch only has 4 mm of side
    clearance, so a few millimetres of drift is the difference between latching and
    not, and it is the number the locating cleats have to justify.
    """

    value = merge_scene.component_b_entity().get_pos()
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value).reshape(-1, 3)[0][:2].astype(float)


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


def link_owners(merge_scene) -> dict[int, str]:
    """Global link index -> the manifest name of the entity it belongs to."""

    owners = {}
    for name, entity in merge_scene.manifest.as_dict().items():
        links = getattr(entity, "links", None)
        if not links:
            continue
        for link in links:
            owners[int(link.idx)] = name
    return owners


def blockers(merge_scene, owners) -> str:
    """What is the beam touching right now, and how hard.

    A stalled sweep is either a collision or a servo that ran out of authority, and
    the two want opposite fixes. Guessing between them from the angle alone was
    wrong once already, so the demo reads the contact set instead: Genesis reports
    the pairs from the last step, and the manifest turns a link index back into a
    part name.
    """

    contacts = merge_scene.linkbar_entity().get_contacts(exclude_self_contact=True)
    if not contacts:
        return "none"
    link_a = np.asarray(_to_numpy(contacts["link_a"])).reshape(-1)
    link_b = np.asarray(_to_numpy(contacts["link_b"])).reshape(-1)
    force = np.asarray(_to_numpy(contacts["force_a"])).reshape(-1, 3)
    beam = int(merge_scene.beam_link_idx())
    totals: dict[str, float] = {}
    for index, (first, second) in enumerate(zip(link_a, link_b)):
        other = int(second) if int(first) == beam else int(first)
        name = owners.get(other, f"link{other}")
        totals[name] = totals.get(name, 0.0) + float(np.linalg.norm(force[index]))
    if not totals:
        return "none"
    return ",".join(
        f"{name}:{value:.2f}N"
        for name, value in sorted(totals.items(), key=lambda item: -item[1])
    )


def _to_numpy(value):
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return value


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
    owners = link_owners(merge_scene)
    for label, target in stations:
        state["phase"] = f"sweep:{label}"
        error = drive_joint(merge_scene, target, steps=steps, cfg=cfg)
        state["angle"] = merge_scene.arm_angle()
        worst = max(worst, abs(error))
        b_drift = max(b_drift, float(np.linalg.norm(b_xy(merge_scene) - b_start)))
        gaps = {name: float(np.linalg.norm(merge_scene.pin_xy() - layout.socket_center_xy(name)))
                for name in LINKBAR_SOCKETS}
        print(
            f"[sweep -> {label:4s}] target={np.rad2deg(target):+7.2f}deg "
            f"reached={np.rad2deg(merge_scene.arm_angle()):+7.2f}deg "
            f"error={np.rad2deg(error):+6.2f}deg "
            + " ".join(f"gap_{name}={gaps[name]*1000:6.1f}mm" for name in LINKBAR_SOCKETS)
            + f" touching={blockers(merge_scene, owners)}",
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


def run_lift(cfg, merge_scene, state):
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
    return result


def run_classify(cfg, merge_scene, lift_result) -> None:
    """Read the constraint graph, and check it against what the lift test saw.

    The peak rise is what the judge gets, not the final one: a body that is held
    still gives a little under load, and the peak is the honest reading of how much.
    """

    state = LinkbarMergeEvaluator().classify(
        merge_scene,
        lift_delta=None if lift_result is None else lift_result.peak_delta_z,
    )
    info = state.to_info()
    print(
        "linkbar_merge_components classify "
        + " ".join(
            f"{key}={info[key]}"
            for key in ("invariant", "invariant_value", "space", "component_count",
                        "latched_socket", "latch_edges", "lift_tested", "lift_held",
                        "judge_disagrees", "probe_uninformative", "failure_label",
                        "terminal")
        ),
        flush=True,
    )
    if state.judge_disagrees:
        print(
            "[warn] the constraint graph says merged but component B lifted anyway. "
            "That means the JUDGE is wrong, not the run: check the weld set and the "
            "link -> assembly mapping in verification/linkbar_merge_components_verifier.py "
            "before touching the scene.",
            flush=True,
        )
    if state.probe_uninformative:
        print(
            "[warn] component B did not merge and did not lift either, so the pull "
            "was too weak to judge with. Raise task.lift_test.force_scale until an "
            "unmerged B clears task.success.min_free_lift.",
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
    print(
        f"linkbar_merge_components home_clearance "
        f"hand_task=({hand_task[0]:+.4f},{hand_task[1]:+.4f},{hand_task[2]:+.4f}) "
        f"hand_radius={hand_radius:.4f} hand_angle={hand_angle:+.1f}deg "
        f"knob_station={layout.knob_station:.4f} "
        f"radial_gap={abs(hand_radius - layout.knob_station):.4f} "
        f"knob_top_z={layout.knob_top_z:.4f} "
        f"vertical_gap={hand_task[2] - layout.knob_top_z:+.4f}",
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
                lift_result = run_lift(cfg, merge_scene, state) if cfg.run.lift_probe else None
                if cfg.run.classify:
                    run_classify(cfg, merge_scene, lift_result)
        state["phase"] = "done"

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        merge_scene.scene.step()


if __name__ == "__main__":
    main()
