"""Look at the Linkbar Rotate To Zone scene, and put the beam on either zone.

Stage-1 demo: no robot motion, no knob turn. It answers the geometry questions the
scene has to get right before the primitive run is worth reading, and answers them
as numbers rather than by eye:

1. Can the beam actually reach both zones? The joint is driven to each centre
   under position control, so anything the beam fouls on the way shows up as a
   tracking error instead of as a picture that looks fine.
2. Does the judge read what the paint shows? Parked on a zone it must report that
   zone; parked between them it must report none; walked across an edge with
   `run.seat_phase=angle` it must flip exactly at `half_width_deg`.
3. Does the beam stay put? After a written angle and the settle, the joint speed
   must be under `success.max_angular_speed`, or the "at rest" half of the verdict
   cannot be met by any run.

The joint sweep and the seat phases write the joint directly. That is a kinematic
check, NOT an episode, and nothing in an episode may move the beam that way
(`docs/develop/tasks/rigid_first_track_zh.md` section 3.1).

    python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.static_only=true run.viewer=true
    python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.sweep_joint=true run.verbose=true
    python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.seat_phase=left
    python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.seat_phase=angle run.seat_angle_deg=47.5
    python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.supervision import stop_before_physics
from topogym.tasks import LINKBAR_ZONES, LinkbarRotateSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import LinkbarRotateEvaluator

TASK_ID = "linkbar_rotate_to_zone"
SEAT_PHASES = ("none", "left", "right", "angle")

# How much room the pads need over the knob's cap while the gripper traverses to it
# at `motion.approach_z`. See the physical demo for the measurement behind it.
_APPROACH_PAD_CLEARANCE_M = 0.030

# How far the parked hand's axis has to be from the knob's circle. The arm sits at
# its home pose for the whole sweep, and an open gripper reaches about 40 mm to
# either side of that axis, so a hand parked near the circle is something the beam
# has to push through. Measured 2026-08-20: 37 mm fouled the beam at ~20 N and
# stalled it 8 degrees short; 77 mm is clear.
_HOME_RADIAL_CLEARANCE_M = 0.060


def _hud(state):
    def render_lines():
        return [
            f"task={TASK_ID}",
            f"phase={state.get('phase', '-')}",
            f"angle={np.rad2deg(state.get('angle', 0.0)):+.1f}deg",
            f"pin_zone={state.get('pin_zone', None)}",
        ]

    return render_lines


def drive_joint(rotate_scene, target: float, *, steps: int, cfg) -> float:
    """Servo the joint to ``target`` and report the residual error, in radians.

    Position control rather than `set_arm_angle`, because the question this answers
    is whether the beam can GET there: a written angle would teleport straight
    through anything in the way and report success.
    """

    entity = rotate_scene.linkbar_entity()
    dof = [int(rotate_scene.joint_dof)]
    servo = cfg.run.sweep_servo
    entity.set_dofs_kp([float(servo.kp)], dofs_idx_local=dof)
    entity.set_dofs_kv([float(servo.kv)], dofs_idx_local=dof)
    entity.set_dofs_force_range(
        [-float(servo.force)], [float(servo.force)], dofs_idx_local=dof
    )
    entity.control_dofs_position([float(target)], dofs_idx_local=dof)
    for _ in range(int(steps)):
        rotate_scene.scene.step()
    return float(rotate_scene.arm_angle() - float(target))


def run_sweep(cfg, rotate_scene, state) -> None:
    """Drive the beam to each zone and back, and report what it cost to get there."""

    layout = rotate_scene.layout
    steps = int(cfg.run.sweep_steps)
    stations = [("left", layout.zone_angle("left")),
                ("init", layout.init_angle),
                ("right", layout.zone_angle("right")),
                ("init", layout.init_angle)]
    worst = 0.0
    for label, target in stations:
        state["phase"] = f"sweep:{label}"
        error = drive_joint(rotate_scene, target, steps=steps, cfg=cfg)
        state["angle"] = rotate_scene.arm_angle()
        state["pin_zone"] = rotate_scene.pin_zone()
        worst = max(worst, abs(error))
        print(
            f"[sweep -> {label:5s}] target={np.rad2deg(target):+7.2f}deg "
            f"reached={np.rad2deg(rotate_scene.arm_angle()):+7.2f}deg "
            f"error={np.rad2deg(error):+6.2f}deg "
            f"pin_zone={rotate_scene.pin_zone()} "
            f"touching={rotate_scene.touching()}",
            flush=True,
        )
    print(
        f"{TASK_ID} sweep worst_error_deg={np.rad2deg(worst):.2f} "
        f"half_width_deg={float(cfg.task.zones.half_width_deg):.2f} "
        f"reached_both={bool(np.rad2deg(worst) <= float(cfg.run.sweep_tolerance_deg))}",
        flush=True,
    )


def seat_angle_for(cfg, layout) -> tuple[str, float]:
    """(label, joint angle) for the requested seat phase."""

    phase = str(cfg.run.seat_phase)
    if phase == "none":
        # Park at the start angle: the pin is on neither zone, so the judge must
        # say so. That is the control the other phases are read against.
        return phase, layout.init_angle
    if phase == "angle":
        # An arbitrary angle, for walking a zone's edge: sweep `run.seat_angle_deg`
        # across it and the verdict should flip exactly where `half_width_deg` says.
        return phase, float(np.deg2rad(float(cfg.run.seat_angle_deg)))
    return phase, layout.zone_angle(phase)


def run_seat(cfg, rotate_scene, state) -> None:
    """Put the beam at the requested angle, settle, and read the judge."""

    layout = rotate_scene.layout
    phase, angle = seat_angle_for(cfg, layout)
    state["phase"] = f"seat:{phase}"
    rotate_scene.set_arm_angle(angle)
    state["angle"] = angle
    for _ in range(int(cfg.task.success.settle_steps)):
        rotate_scene.scene.step()
    verdict = LinkbarRotateEvaluator().classify(rotate_scene)
    state["pin_zone"] = verdict.pin_zone
    info = verdict.to_info()
    print(
        f"{TASK_ID} seat phase={phase} "
        f"written={np.rad2deg(angle):+7.2f}deg "
        f"settled={np.rad2deg(rotate_scene.arm_angle()):+7.2f}deg "
        f"drift={np.rad2deg(rotate_scene.arm_angle() - angle):+.3f}deg "
        f"speed={verdict.angular_speed:+.4f}rad/s "
        + " ".join(
            f"in_{zone}={layout.in_zone(rotate_scene.arm_angle(), zone)}"
            for zone in LINKBAR_ZONES
        )
        + f" touching={rotate_scene.touching()}",
        flush=True,
    )
    print(
        f"{TASK_ID} classify "
        + " ".join(
            f"{key}={info[key]}"
            for key in ("invariant", "invariant_value", "space", "pin_zone",
                        "target_zone", "in_target", "at_rest", "failure_label",
                        "terminal")
        ),
        flush=True,
    )


@hydra.main(version_base="1.3", config_path="../../configs",
            config_name="linkbar_rotate_to_zone")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"{TASK_ID}_config -> {resolved}", flush=True)

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

    builder = LinkbarRotateSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    rotate_scene = builder.build(show_viewer=show_viewer)
    layout = rotate_scene.layout

    # Hold the arm at its home pose. It takes no part in this demo, but a Franka
    # with no joint targets collapses under gravity on the first step.
    controller = initialize_franka_controller(
        scene=rotate_scene.scene,
        manifest=rotate_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0 if cfg.run.static_only else int(cfg.task.physical.settle_steps),
    )

    # Where the parked hand sits relative to the knob's circle. The beam sweeps
    # through every angle while the arm is parked, so a home pose that overlaps the
    # circle is an obstacle the beam has to push through.
    hand = np.asarray(controller.hand_pos(), dtype=float).reshape(3)
    hand_task = hand - np.asarray(layout.task_origin, dtype=float)
    hand_radius = float(np.linalg.norm(hand_task[:2] - layout.pivot_xy))
    hand_angle = float(np.rad2deg(np.arctan2(
        hand_task[1] - layout.pivot_xy[1], hand_task[0] - layout.pivot_xy[0]
    )))
    radial_gap = abs(hand_radius - layout.knob_station)
    print(
        f"{TASK_ID} home_clearance "
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
        f"{TASK_ID} setup "
        f"pivot=({layout.pivot_xy[0]:+.3f},{layout.pivot_xy[1]:+.3f}) "
        f"arm_radius={layout.arm_radius:.3f} "
        f"init={float(cfg.task.linkbar.init_angle_deg):+.1f}deg "
        + " ".join(
            f"{zone}={np.rad2deg(layout.zone_angle(zone)):+.1f}deg/"
            f"{layout.zone_color_name(zone)}"
            for zone in LINKBAR_ZONES
        )
        + f" target={layout.target_zone()} "
        f"half_width={float(cfg.task.zones.half_width_deg):.1f}deg "
        f"knob_grasp_z={layout.knob_grasp_z():.4f}",
        flush=True,
    )
    pad_z = float(cfg.task.motion.approach_z) - HAND_TO_PAD_Z
    approach_clearance = pad_z - layout.knob_cap_top_z
    print(
        f"{TASK_ID} approach_clearance "
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
            f"{TASK_ID} settle_check "
            f"angle={np.rad2deg(rotate_scene.arm_angle()):+.2f}deg "
            f"(init={float(cfg.task.linkbar.init_angle_deg):+.2f}deg) "
            f"speed={rotate_scene.arm_velocity():+.4f}rad/s "
            f"touching={rotate_scene.touching()}",
            flush=True,
        )

    if stop_before_physics(cfg, rotate_scene.scene, f"{TASK_ID}_inspect_demo"):
        raise SystemExit(0)

    state = {"phase": "settle", "angle": layout.init_angle, "pin_zone": None}
    with recording_session_from_config(
        rotate_scene.scene, rotate_scene.cameras, cfg.recording, hud=_hud(state)
    ):
        if cfg.run.static_only:
            # Build-and-look: no stepping at all, so the scene is inspected exactly
            # as constructed. Anything that interpenetrates at build time shows up
            # here rather than being hidden by the first settle.
            print(f"{TASK_ID} static_only=true; not stepping.", flush=True)
        elif cfg.run.sweep_joint:
            run_sweep(cfg, rotate_scene, state)
        else:
            run_seat(cfg, rotate_scene, state)
        # Hold the settled scene for the recording: a video that stops on the last
        # measured frame shows nothing.
        state["phase"] = "done"
        for _ in range(int(getattr(cfg.run, "final_hold_steps", 0) or 0)):
            rotate_scene.scene.step()

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        rotate_scene.scene.step()


if __name__ == "__main__":
    main()
