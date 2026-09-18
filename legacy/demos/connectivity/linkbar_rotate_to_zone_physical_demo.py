"""Turn the beam so its pin rests on the zone the instruction names, and judge it.

The episode end to end: the arm takes the beam's knob, sweeps one arc, lets go,
retreats; the beam parks on joint friction; after a short settle the judge reads
which zone the pin is on and whether the beam has stopped.

Two rules run the same episode (`run.oracle_mode`):

    oracle          go to the zone painted the colour the instruction names
    nearest_zone    go to whichever zone is the shorter turn

Both reach a zone. What tells them apart is what they read, which is the point of
the task -- and with the target zone drawn independently of the two positions on
the rail, the shortcut is right half the time. A third rule, `nearest_colour` ("go
to whichever zone's paint is closest to the pin's"), ran here until 2026-09-09; it
was the ORACLE until 2026-09-08, when the pin still carried the target zone's
colour. The beam now carries no colour at all, so that rule has no input and is
gone. `tests/check_linkbar_planner.py` settles the rules offline; this demo is
where they get settled against physics.

`run.stage=rotate_only` stops after the sweep. That is the primitive's own
acceptance run -- reach, follow error, grip -- with no judging attached.

    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.viewer=true
    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.stage=rotate_only run.verbose=true
    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.oracle_mode=nearest_zone
    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo task.zones.target=color_1
    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo task.zones.color_1.angle_deg=30 task.zones.color_2.angle_deg=60
    python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo --cfg job
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
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.planning import make_linkbar_rule
from topogym.primitives import (
    PivotLeverPrimitive,
    configure_gripper_contact_friction,
    print_collision_il_contract,
)
from topogym.primitives.physical_contact import ee_quat_for_yaw
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import LINKBAR_ZONES, LinkbarRotateSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import LinkbarRotateEvaluator

TASK_ID = "linkbar_rotate_to_zone"
STAGES = ("full", "rotate_only")


def _variant_line(cfg) -> str:
    """One parseable line with every sampled leaf (bash_scripts/tests/linkbar_variation_sweep.sh reads it)."""
    z = cfg.task.zones
    init = float(cfg.task.linkbar.init_angle_deg)
    c1, c2 = float(z.color_1.angle_deg), float(z.color_2.angle_deg)
    # Clear angle between the two painted spans (0 = touching), and whether both
    # zones lie on one side of the beam's start -- the two things the old
    # envelope could not produce.
    gap = abs(c2 - c1) - 2.0 * float(z.half_width_deg)
    same_side = (c1 - init) * (c2 - init) > 0.0
    return (
        f"{TASK_ID} variant seed={int(cfg.run.seed)} target={z.target} "
        f"assignment=color_1:{z.assignment.color_1},color_2:{z.assignment.color_2} "
        f"target_colour={str(getattr(z.assignment, str(z.target)))} "
        f"color_1_deg={c1:+.2f} color_2_deg={c2:+.2f} init_deg={init:+.2f} "
        f"gap_deg={gap:.2f} same_side={str(same_side).lower()}"
    )

# How much room the pads need over the knob's cap while the gripper traverses to it
# at `motion.approach_z`. The approach ends directly over the knob, so this is the
# clearance that decides whether the trip brushes the beam -- and the fingertips sit
# about another 10 mm below the pad centre, so the pad figure is the one to gate on.
# Measured 2026-08-22: 16 mm of pad clearance left roughly 6 mm at the fingertips,
# the traverse pushed the beam 2.49 degrees, and the gripper then closed on empty
# air. It regressed silently once already, which is why it is checked rather than
# remembered.
_APPROACH_PAD_CLEARANCE_M = 0.030


def _hud(status):
    def render_lines():
        return [
            f"task={TASK_ID}",
            f"phase={status.get('phase', '-')}",
            f"mode={status.get('mode', '-')}",
            f"target={status.get('target', '-')}",
            f"pin_zone={status.get('pin_zone', '-')}",
        ]

    return render_lines


class FirstDisturbance:
    """Catch the step at which the beam first leaves its start angle.

    Phase-boundary logging says the beam moved somewhere inside a phase; it does not
    say when, or against what. Both matter here: raising the pads' clearance over the
    knob from 6 mm to 31 mm made the disturbance WORSE (2.49 -> 40.44 degrees), which
    rules out the explanation that had been assumed twice. This watches every step and
    freezes the contact set at the moment the angle first moves, so the next reading
    names the part instead of narrowing a guess.

    Wraps `scene.step` and restores it on exit.
    """

    def __init__(self, rotate_scene, *, tolerance_deg: float = 0.5):
        self.scene = rotate_scene
        self.tolerance = float(np.deg2rad(tolerance_deg))
        self.start = rotate_scene.arm_angle()
        self.step_index = 0
        self.hit_step = None
        self.hit_angle = None
        self.hit_touching = None
        self._original = None

    def __enter__(self):
        original = self.scene.scene.step

        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            self.step_index += 1
            if self.hit_step is None:
                angle = self.scene.arm_angle()
                if abs(angle - self.start) > self.tolerance:
                    self.hit_step = self.step_index
                    self.hit_angle = angle
                    self.hit_touching = self.scene.touching()
            return result

        self._original = original
        self.scene.scene.step = wrapped
        return self

    def __exit__(self, *exc):
        if self.scene.scene.step is not self._original:
            self.scene.scene.step = self._original

    def report(self) -> str:
        if self.hit_step is None:
            return f"never (start={np.rad2deg(self.start):+.2f}deg, {self.step_index} steps)"
        return (
            f"step={self.hit_step} angle={np.rad2deg(self.hit_angle):+.2f}deg "
            f"(start={np.rad2deg(self.start):+.2f}deg) touching={self.hit_touching}"
        )


def build_primitive(cfg, layout, sweep: float) -> PivotLeverPrimitive:
    motion = cfg.task.motion
    return PivotLeverPrimitive(
        approach_z=layout.world_z(float(motion.approach_z)),
        retreat_z=layout.world_z(float(motion.retreat_z)),
        steps_per_phase=int(motion.steps_per_phase),
        # Derived from the sweep so the angular speed is the same for every variant.
        steps_arc=layout.steps_arc(sweep),
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


def run_episode(cfg, rotate_scene, controller, *, episode_key, status) -> EpisodeResult:
    layout = rotate_scene.layout
    status["mode"] = str(cfg.run.oracle_mode)

    print_collision_il_contract(
        f"{TASK_ID}_physical_demo",
        manipulated=["linkbar"],
        runtime_attachment=False,
        runtime_set_pose=False,
        success_checks=("target_error", "finger_qpos", "pin_zone", "angular_speed"),
    )

    rule = make_linkbar_rule(cfg.run.oracle_mode)
    plan = rule.decide(layout, rotate_scene.arm_angle())
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
    status["target"] = f"{plan.target_zone}@{np.rad2deg(plan.target_angle):+.1f}"
    print(
        f"{TASK_ID} plan mode={cfg.run.oracle_mode} "
        f"target_zone={plan.target_zone} instructed_zone={layout.target_zone()} "
        f"target_colour={layout.target_colour()} goal_id={layout.goal_id()} "
        f"start={np.rad2deg(plan.start_angle):+.2f}deg "
        f"target={np.rad2deg(plan.target_angle):+.2f}deg "
        f"sweep={np.rad2deg(plan.sweep):+.2f}deg rotate={plan.rotate} "
        f"steps_arc={layout.steps_arc(plan.target_angle - plan.start_angle)} "
        f"reason={plan.reason} prompt={layout.instruction()!r}",
        flush=True,
    )

    if stop_before_physics(cfg, rotate_scene.scene, f"{TASK_ID}_physical_demo"):
        raise SystemExit(0)

    # From the two angles rather than `plan.sweep`: an offset run rewrote the target.
    primitive = build_primitive(cfg, layout, plan.target_angle - plan.start_angle)
    evaluator = LinkbarRotateEvaluator()

    # How far the wrist is asked to turn on the very first commanded step. The
    # approach's opening move eases its POSITION to the traverse height over the
    # phase, but hands the controller its final ORIENTATION on step 1 -- so a home
    # pose that is not already square to the knob gets corrected in one step at
    # full gain. The disturbance on 2026-08-22 landed 7 steps into that move, at
    # 218 N, with the hand 0.6 mm from where it started; that only adds up if what
    # swung was the wrist. This prints the size of the swing it is asked for.
    home_quat = np.asarray(controller.hand_quat(), dtype=float).reshape(4)
    want_quat = np.asarray(
        ee_quat_for_yaw(controller.default_ee_quat, rotate_scene.arm_angle()), dtype=float
    ).reshape(4)
    snap_deg = np.rad2deg(
        2.0 * np.arccos(np.clip(abs(float(np.dot(home_quat, want_quat))), 0.0, 1.0))
    )
    print(
        f"{TASK_ID} wrist_snap "
        f"home=({','.join(f'{v:+.3f}' for v in home_quat)}) "
        f"commanded=({','.join(f'{v:+.3f}' for v in want_quat)}) "
        f"turn={snap_deg:.2f}deg",
        flush=True,
    )

    with FirstDisturbance(rotate_scene) as watch:
        result = None
        if plan.rotate:
            status["phase"] = "rotate"
            result = primitive.run(
                controller,
                entity=rotate_scene.linkbar_entity(),
                dof=rotate_scene.joint_dof,
                pivot_xy=layout.position_to_world(
                    (layout.pivot_xy[0], layout.pivot_xy[1], 0.0)
                )[:2],
                radius=layout.knob_station,
                grasp_z=float(layout.knob_grasp_world(plan.start_angle)[2]),
                target_angle=plan.target_angle,
            )
            status["pin_zone"] = rotate_scene.pin_zone()
            print(f"{TASK_ID} first_disturbance {watch.report()}", flush=True)
            print(
                f"{TASK_ID} rotate "
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
                f"pin_zone={rotate_scene.pin_zone()}",
                flush=True,
            )

    if str(cfg.run.stage) == "rotate_only":
        status["phase"] = "done"
        metrics = {
            "stage": "rotate_only",
            "rotate_success": bool(result is not None and result.success),
            "pin_zone": rotate_scene.pin_zone(),
        }
        return (
            EpisodeResult.ok(episode_key, metrics=metrics, export_ready=False)
            if metrics["rotate_success"]
            else EpisodeResult.failed(
                episode_key, "rotate_check_failed", metrics=metrics, stable_ready=False
            )
        )

    # Let the beam park. It stops on joint friction, not on anything the arm did,
    # and the judge wants a reading of where it RESTS, not where the hand left it.
    status["phase"] = "settle"
    for _ in range(int(cfg.task.success.settle_steps)):
        rotate_scene.scene.step()

    status["phase"] = "verify"
    state = evaluator.classify(
        rotate_scene, rotate_ok=bool(result is None or result.success)
    )
    status["pin_zone"] = state.pin_zone
    info = state.to_info()
    print(
        f"{TASK_ID} result "
        f"mode={cfg.run.oracle_mode} planned={plan.target_zone} "
        f"pin_angle={np.rad2deg(state.pin_angle):+.2f}deg "
        f"pin_zone={info['pin_zone']} target_zone={info['target_zone']} "
        f"angular_speed={state.angular_speed:+.4f}rad/s "
        f"(max {state.max_angular_speed:.4f}) at_rest={info['at_rest']} "
        f"rotate_ok={info['rotate_ok']} "
        f"task_success={info['terminal']} failure={info['failure_label']}",
        flush=True,
    )
    if cfg.run.verbose:
        print(f"{TASK_ID} topology {info}", flush=True)

    metrics = {
        "stage": "full",
        "task_success": bool(state.is_terminal),
        "pin_zone": state.pin_zone,
        "target_zone": state.target_zone,
        "planned_zone": plan.target_zone,
        "pin_angle_deg": float(np.rad2deg(state.pin_angle)),
        "angular_speed": float(state.angular_speed),
        "at_rest": bool(state.at_rest),
        "rotate_ok": bool(state.rotate_ok),
        "target_error_deg": (
            None if result is None else float(np.rad2deg(result.target_error))
        ),
        "finger_qpos": None if result is None else float(result.finger_qpos),
    }
    # Hold the settled scene for the recording. Nothing is measured here -- the
    # verdict is already in -- but a video that cuts on the frame the verdict lands
    # gives the viewer nothing to look at.
    status["phase"] = "done"
    for _ in range(int(getattr(cfg.run, "final_hold_steps", 0) or 0)):
        rotate_scene.scene.step()

    if state.is_terminal:
        return EpisodeResult.ok(
            episode_key, metrics=metrics, export_ready=bool(state.rotate_ok)
        )
    return EpisodeResult.failed(
        episode_key, state.failure_label or "unknown", metrics=metrics, stable_ready=False
    )


@hydra.main(version_base="1.3", config_path="../../configs",
            config_name="linkbar_rotate_to_zone_rotate")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"{TASK_ID}_config -> {resolved}", flush=True)

    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, TASK_ID, cfg.run.seed, difficulty=cfg.run.difficulty)
        print(_variant_line(cfg), flush=True)

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

    builder = LinkbarRotateSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    rotate_scene = builder.build(show_viewer=show_viewer)
    layout = rotate_scene.layout

    controller = initialize_franka_controller(
        scene=rotate_scene.scene,
        manifest=rotate_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_gripper_contact_friction(
        entities=[rotate_scene.linkbar_entity()],
        robot=controller.robot,
        finger_links=list(cfg.task.motion.finger_links),
        object_friction=float(cfg.task.motion.knob_friction),
        finger_friction=float(cfg.task.motion.finger_friction),
    )

    print(
        f"{TASK_ID} setup "
        f"pivot=({layout.pivot_xy[0]:+.3f},{layout.pivot_xy[1]:+.3f}) "
        f"arm_radius={layout.arm_radius:.3f} knob_station={layout.knob_station:.3f} "
        f"init={float(cfg.task.linkbar.init_angle_deg):+.1f}deg "
        + " ".join(
            f"{zone}={np.rad2deg(layout.zone_angle(zone)):+.1f}deg/"
            f"{layout.zone_color_name(zone)}"
            for zone in LINKBAR_ZONES
        )
        + f" target={layout.target_zone()} "
        f"half_width={float(cfg.task.zones.half_width_deg):.1f}deg "
        f"tolerance={float(cfg.task.motion.target_tolerance_deg):.2f}deg "
        f"stage={stage} mode={cfg.run.oracle_mode}",
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
    # After the home settle and before anything is commanded. A beam that has left
    # its start angle here moved without being asked to, and `touching` says whether
    # something pushed it or it drifted on its own.
    print(
        f"{TASK_ID} settle_check "
        f"angle={np.rad2deg(rotate_scene.arm_angle()):+.2f}deg "
        f"(init={float(cfg.task.linkbar.init_angle_deg):+.2f}deg) "
        f"speed={rotate_scene.arm_velocity():+.4f}rad/s "
        f"touching={rotate_scene.touching()}",
        flush=True,
    )

    episode_key = EpisodeKey(
        task_id=TASK_ID, seed=int(cfg.run.seed), variant_id=str(cfg.run.variant_id)
    )
    status = {"phase": "home", "mode": "-", "target": "-", "pin_zone": None}
    with recording_session_from_config(
        rotate_scene.scene, rotate_scene.cameras, cfg.recording, hud=_hud(status)
    ):
        run_episode(cfg, rotate_scene, controller, episode_key=episode_key, status=status)

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        rotate_scene.scene.step()


if __name__ == "__main__":
    main()
