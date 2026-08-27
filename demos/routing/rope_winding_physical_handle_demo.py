"""Wind a FEM rope around a post by physically grasping the plug on its free end.

Task book 2.4 (0 -> N turns): the post is fixed at both ends of the episode, so
its top is the only gateway that can change the winding number; the oracle keeps
the plug below it and orbits instead. Winding is signed -- running the mirrored
trajectory (`task.winding.direction=cw`) reaches -turns and fails, which is the
task's contrast pair: same grasp, same placement, opposite topology.

The gripper never touches the deformable body: it grasps the plug, and the rope
follows through the endpoint constraint. The plug lies flat on the board and is
plugged into nothing -- it exists so the arm has a rigid body to hold. It is
mesh-only, so a kinematic hold keeps it from falling through the board until the
grasp attachment takes over at gripper close, and the same hold sets it down
again at the target.

Configuration is Hydra (`configs/rope_winding.yaml`). Task book 2.5, taking a
rope OFF the post (`winding.start_turns` wraps at spawn, `turns: 0`), runs the
same code through `demos/routing/rope_unwinding_physical_handle_demo.py`
(`configs/rope_unwinding.yaml`).

    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true run.verbose=true
    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true run.probe=true run.max_waypoints=10
    python -m demos.routing.rope_winding_physical_handle_demo run.viewer=true task.winding.direction=cw
    python -m demos.routing.rope_winding_physical_handle_demo task.winding.turns=1
    python -m demos.routing.rope_winding_physical_handle_demo task.winding.yaw_track=false
    python -m demos.routing.rope_winding_physical_handle_demo --cfg job

The wrist turns with the orbit (`task.winding.yaw_track`) so the rope keeps the
same bearing out of the hand instead of sweeping around it once per turn; set it
false for the fixed-wrist behaviour the `wrap` numbers were first measured
against. `wrap_report` / `wrap_summary` are the readout for both.

What actually keeps torsion out of the rope is a different knob:
`task.physical_handle.plug_spin_tracks_orbit` turns the PLUG about the vertical
inside the gripper, by the hand's own azimuth about the post. Carried pin-up the
rope leaves the plug's cap straight down, so the welded band's tangent is
vertical and the orbit's rotation would otherwise land entirely along it -- as
one turn of twist per orbit. `wrap_plug` near zero says the rope and the plug
held the same relative angle; `wrap` beside it is the old wrist-referenced
baseline.

Two numbers in `wrap_report` / `wrap_summary` guard the grasp itself:
`grip_slip_deg` is how far the plug is from where the attachment commands it
(0 unless the solver moves it between syncs), and `plug_vs_rope_deg` is the angle
between the plug's bore and the rope arriving at it (past 90 the rope is entering
side-on through the plug's body instead of through its cap). Both were
assumptions until 2026-08-15, when the first turned out to be false for the whole
route.

Rope torsion is reported by `TWIST` / `twist_onset` / `twist_summary`, which run
unconditionally: their reference frame is fixed at the episode's first step, so
they cannot be switched off without losing the baseline. `twist_legacy` beside
them is `rope_twist_turns`, kept only until the two have been compared on a run.
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
    SLACK_BAND,
    RopeWindingRouteCommand,
    WindingSpec,
    plan_rope_winding_route,
    post_center,
    taut_demand,
)
from topogym.primitives import (
    AttachmentManager,
    ConnectorLatch,
    HandleDragPrimitive,
    configure_gripper_contact_friction,
    ee_quat_for_yaw,
    entity_pos,
    entity_quat,
    print_collision_il_contract,
    quat_about_axis,
    quat_mul,
)
from topogym.supervision import (
    StepProbe,
    TwistProbe,
    gripper_wrap,
    material_bins,
    material_coords,
    pad_gap,
    post_contact,
    print_winding_verification,
    rope_free_end_first,
    rope_twist_turns,
    settled_band_radius,
    stop_before_physics,
    winding_centerline,
    winding_number,
)
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.supervision.cable_routing import rope_particles, tensor_to_numpy
from topogym.tasks import RopeWindingSceneBuilder
from topogym.tasks.routing.cable_routing import connector_pose
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


def _check_rope_slack(cfg, scene, spec, episode_plan) -> str:
    """Refuse a (turns, sweep_deg) pair the rope cannot serve. Returns a report.

    One turn on the post eats `2 pi * settle_radius` -- 151 mm here -- so the
    taut demand moves with `winding.turns` while the spawn arc's length does not
    follow on its own. Three turns on the two-turn arc is 12% SHORT: the rope
    would be dragged off the post or through the anchor. Too much slack is the
    other failure, the one cable_routing's helix blew up on at 19%.

    Checked here rather than only in `tests/check_rope_winding_geometry.py`
    because the pair is set on the command line, and the cost of finding out
    late is a 40-minute GPU run.
    """

    length = float(
        np.sum(
            np.linalg.norm(
                np.diff(scene.layout.route_polyline("initial"), axis=0), axis=1
            )
        )
    )
    need, label = taut_demand(scene.layout, spec, episode_plan.waypoints)
    slack = (length - need) / need
    low, high = SLACK_BAND
    sweep = float(cfg.task.rope.spawn_arc.sweep_deg)
    report = (
        f"start_turns={spec.start_turns} turns={spec.turns} sweep_deg={sweep:.0f} "
        f"rope={length:.3f} taut_need={need:.3f} at {label} slack={slack * 100:.1f}% "
        f"band={low * 100:.0f}..{high * 100:.0f}%"
    )
    if not low <= slack <= high:
        # Whichever of the two is nonzero is the one that sets the demand.
        unwinding = spec.start_turns > spec.turns
        key = "winding.start_turns" if unwinding else "winding.turns"
        gate = (
            f"tests/check_rope_unwinding_geometry.py --start-turns {spec.start_turns}"
            if unwinding
            else f"tests/check_rope_winding_geometry.py --turns {spec.turns}"
        )
        raise RuntimeError(
            f"{cfg.task.task.id} slack out of band -- {report}. `{key}` and "
            "`rope.spawn_arc.sweep_deg` have to be set together; the table is in "
            f"the task config beside `spawn_arc`. Run `python {gate} "
            "--sweep-deg <deg>` to find the sweep this turn count needs."
        )
    return report


def _quat_conjugate(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(-1, 4)[0])
    return np.array([w, -x, -y, -z], dtype=float)


def _quat_axes(quat) -> np.ndarray:
    """Columns of the rotation matrix for a (w, x, y, z) quat: its local x, y, z."""

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(-1, 4)[0])
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _grasp_geometry(scene, handle, ee_quat, heading, free_end_first) -> str:
    """Three angles that say whether the gripper holds the plug the intended way.

    The intent is stated in three places (`rope_axis_heading`'s docstring, the
    `plug_heading` field comment, the grasp-yaw comment below): the plug lies
    along the rope, and the pads close ACROSS its axis rather than along it.
    Nothing checked it. `gs.morphs.Mesh(euler=...)` is x-y-z degrees but the
    repo never pinned down extrinsic vs intrinsic, and for this plug the two
    differ completely -- intrinsic would spin a solid of revolution about its
    own axis and leave it pointing along world -x whatever the rope does.

    So: derive the directions from the entity's ACTUAL pose and report the
    angles. Printed every run, like `start_anchor=`, because the alternative is
    another assumption that looks obviously right and was never measured.
    """

    axis = _quat_axes(entity_quat(handle))[:, 2]          # plug's local +z = its bore
    pads = _quat_axes(ee_quat)[:, 1]                      # hand's local y = finger travel
    rope = np.array([np.cos(heading), np.sin(heading), 0.0])

    def between(a, b) -> float:
        cos = float(np.clip(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0))
        return float(np.degrees(np.arccos(cos)))

    # Where the rope actually ends, from the nodes rather than the design route.
    arc = material_coords(scene)[:, 0]
    fraction = arc / max(float(arc.max()), 1e-9)
    tail = fraction <= 0.02 if free_end_first else fraction >= 0.98
    rope_end = rope_particles(scene)[tail].mean(axis=0)
    # Perpendicular distance from that point to the plug's axis line, split into
    # its vertical and lateral parts. Which one is non-zero says where to look:
    # `dz` is a height mismatch (`rope.z` vs the plug's axis), `lateral` means the
    # rope's mesh does not end where its design route says it does.
    offset = rope_end - np.asarray(entity_pos(handle), dtype=float)
    perpendicular = offset - axis * float(np.dot(offset, axis))
    off_axis = float(np.linalg.norm(perpendicular))

    return (
        f"axis_vs_pads_deg={between(axis, pads):.1f} "
        f"axis_vs_rope_deg={between(axis, rope):.1f} "
        f"rope_end_off_axis_mm={off_axis * 1000:.1f} "
        f"(dz={perpendicular[2] * 1000:+.1f} "
        f"lateral={float(np.linalg.norm(perpendicular[:2])) * 1000:.1f}) "
        f"plug_z_mm={float(entity_pos(handle)[2]) * 1000:.1f} "
        f"rope_end_z_mm={float(rope_end[2]) * 1000:.1f}"
    )


def _arm_qpos(controller) -> np.ndarray:
    qpos = np.asarray(tensor_to_numpy(controller.robot.get_qpos()), dtype=float)
    width = controller.arm_joint_count + controller.gripper_joint_count
    return qpos.reshape(-1, width)[0, : controller.arm_joint_count]


class _Unwrapped:
    """Accumulated change of an angle, sampled at intervals under half a turn."""

    def __init__(self) -> None:
        self._previous: float | None = None
        self.total = 0.0

    def update(self, angle) -> float:
        angle = float(angle)
        if angle != angle:  # NaN: no usable sample, hold the accumulator.
            return self.total
        if self._previous is not None:
            step = angle - self._previous
            self.total += float(np.arctan2(np.sin(step), np.cos(step)))
        self._previous = angle
        return self.total


class OrbitSpin:
    """How far the plug must turn about the vertical, right now.

    The free span between the plug and the post rotates about the post once per
    orbit. Carried pin-up the rope leaves the plug's cap straight DOWN, so the
    welded band's tangent is vertical and that rotation lands entirely along the
    rope's own tangent -- as torsion, one turn per orbit, unless the plug turns
    with it. Turning it by the same angle makes plug and span a single rigid
    rotation, which is what "the rope and the plug keep the same relative angle"
    means as a number.

    The angle is the hand's own azimuth about the post, read from where the hand
    ACTUALLY is (so IK lag is followed rather than fought), unwrapped, and zeroed
    at the grasp. Signed by construction: ccw orbits raise it, cw lower it, so
    nothing here needs to know the winding direction.

    It stops accumulating at `freeze()`. Past the last orbit point the rope is
    already wound and has nowhere to pay out to, so more turning would inject
    torsion rather than cancel it -- the same reason the planner holds its final
    wrist roll through exit, travel and placement instead of unwinding it.
    """

    def __init__(self, controller, post_xy) -> None:
        self.controller = controller
        self.post_xy = np.asarray(post_xy, dtype=float)[:2]
        self._azimuth = _Unwrapped()
        self._zero = 0.0
        self.frozen = False
        self._held = 0.0

    def reset(self) -> None:
        """Start from zero here -- called once the plug is grasped and pitched."""

        self._azimuth = _Unwrapped()
        self._zero = self._sample()
        self.frozen = False
        self._held = 0.0

    def freeze(self) -> None:
        self._held = self()
        self.frozen = True

    def _sample(self) -> float:
        hand = np.asarray(self.controller.hand_pos(), dtype=float)
        return self._azimuth.update(
            np.arctan2(hand[1] - self.post_xy[1], hand[0] - self.post_xy[0])
        )

    def __call__(self) -> float:
        if self.frozen:
            return self._held
        return self._sample() - self._zero


class WrapTracker:
    """How far the rope has swept around the gripper, accumulated over the run.

    The review says the rope tangles with the gripper itself, and the agreed cure
    is to spin the wrist as it orbits. Before writing that spin, two numbers have
    to be measured rather than assumed: how much rotation the rope actually
    demands, and how much of it the wrist can deliver.

    `wrap` is the first. It is the strand's world bearing out of the hand minus
    the hand's own yaw, unwrapped -- one turn per orbit is the tangling
    hypothesis, and `strand_bearing` against `orbit` is directly the yaw profile
    a co-rotating wrist would have to follow. `q7` is the second: the Franka's
    tool roll, whose travel is the budget the profile has to fit in.

    One instance is shared by the probe and the per-waypoint report, so both read
    the same accumulators. Unwrapping only needs samples closer together than
    half a turn, and either caller alone provides that (a waypoint is 45 degrees
    of orbit).
    """

    def __init__(
        self, scene, controller, groups, spec, handle, *, free_end_first: bool,
        cap_offset: float = 0.0, carry_pitch: float = 0.0, spin=None,
        commanded_quat_fn=lambda: None,
    ):
        self.scene = scene
        self.controller = controller
        self.groups = groups
        self.handle = handle
        self.free_end_first = bool(free_end_first)
        # The `OrbitSpin` driving the plug, or None -- reported so a run can be
        # read back without guessing what the plug was asked to do.
        self.spin = spin
        # What the grasp attachment currently commands the plug's orientation to
        # be, or None before there is one. `grip_slip_deg` measures against this.
        self.commanded_quat_fn = commanded_quat_fn
        self.post_xy = np.asarray(post_center(scene.layout, spec), dtype=float)[:2]
        # Where the cable actually leaves the plug, in world z: the pads are
        # `HAND_TO_PAD_Z` below the hand, and the cap sits `cap_offset` along the
        # plug's axis from there -- straight down when the carry is nose-down,
        # level with the pads when it is flat.
        self._outlet_drop = HAND_TO_PAD_Z + cap_offset * float(np.sin(carry_pitch))
        self.reset()

    def reset(self) -> None:
        """Start over, at the grasp.

        Before the fingers close there is nothing to accumulate: the hand is
        still crossing the board, and its bearing to the rope can swing more than
        half a turn between probe samples, which is exactly what an unwrap cannot
        survive. Wrap is defined relative to the grasp anyway.
        """

        self._orbit = _Unwrapped()
        self._yaw = _Unwrapped()
        self._bearing = _Unwrapped()
        self._plug_yaw = _Unwrapped()
        self.max_wrap = 0.0
        self.max_wrap_plug = 0.0
        self.max_intrusion = 0
        self.first_intrusion_phase: str | None = None
        self.q7_min = float("inf")
        self.q7_max = float("-inf")
        self.yaw_min = 0.0
        self.yaw_max = 0.0
        self.max_roll_error = 0.0
        self.max_twist = 0.0
        self.max_grip_slip = 0.0
        # `grip_slip` is only a promise while the plug IS held; the summary says
        # so rather than implying the number covers the whole run. (It used to be
        # load-bearing: measured against a grasp-time snapshot, the 80 mm hand-off
        # retreat added 53 degrees of "slip" on the 2026-08-15 run and read as a
        # broken grasp. Measured against the command it cannot, but the run still
        # ends with nobody commanding anything.)
        self.held = True
        self.max_plug_vs_rope = 0.0
        self.max_cap_entry = 0.0
        self.obtuse_samples = 0
        self.samples = 0
        # The rising-spiral invariant: the outlet must stay above everything
        # already laid down. Worst case over the run is the number that says
        # whether it held.
        self.worst_blocking_gap = float("inf")

    def sample(self, phase: str, commanded_roll: float | None = None) -> dict:
        hand = np.asarray(self.controller.hand_pos(), dtype=float)
        metrics = gripper_wrap(
            self.scene,
            self.controller,
            self.groups,
            free_end_first=self.free_end_first,
            outlet_z=float(hand[2]) - self._outlet_drop,
        )
        orbit = self._orbit.update(
            np.arctan2(hand[1] - self.post_xy[1], hand[0] - self.post_xy[0])
        )
        yaw = self._yaw.update(metrics["hand_yaw"])
        bearing = self._bearing.update(metrics["strand_bearing"])
        wrap = (bearing - yaw) / (2.0 * np.pi)
        # The same sweep measured against the PLUG rather than the hand. Once the
        # plug turns inside the gripper the two stop agreeing, and it is the plug
        # the rope is welded to: `wrap_plug` near zero is the statement that the
        # rope and the plug kept the same relative angle, which is the whole
        # point of the spin. The plug's local x is horizontal whenever its axis is
        # vertical, so its azimuth is well defined in the carried pose.
        plug_x = _quat_axes(entity_quat(self.handle))[:, 0]
        plug_yaw = self._plug_yaw.update(np.arctan2(plug_x[1], plug_x[0]))
        wrap_plug = (bearing - plug_yaw) / (2.0 * np.pi)
        q7 = float(_arm_qpos(self.controller)[-1])
        intrusion = int(metrics["intrusion"])
        # Torsion in the rope itself, per waypoint rather than per N steps. The
        # question it answers is where twist enters: smoothly along the tracked
        # arcs, or in steps at the flicks.
        twist = rope_twist_turns(self.scene, self.groups)
        if twist == twist:
            self.max_twist = max(self.max_twist, abs(twist))

        self.max_wrap = max(self.max_wrap, abs(wrap))
        self.max_wrap_plug = max(self.max_wrap_plug, abs(wrap_plug))
        self.max_intrusion = max(self.max_intrusion, intrusion)
        if intrusion and self.first_intrusion_phase is None:
            self.first_intrusion_phase = phase
        self.q7_min = min(self.q7_min, q7)
        self.q7_max = max(self.q7_max, q7)
        self.yaw_min = min(self.yaw_min, yaw)
        self.yaw_max = max(self.yaw_max, yaw)
        # Commanded roll minus what the wrist actually reached. This is the
        # measurement the wrist-budget question needs: the arm has redundancy
        # beyond joint7, and only a run that asks for roll can say how much of it
        # is available.
        roll_error = 0.0 if commanded_roll is None else float(commanded_roll) - yaw
        self.max_roll_error = max(self.max_roll_error, abs(roll_error))

        grip = self._grip_metrics()
        if self.held:
            self.max_grip_slip = max(self.max_grip_slip, grip["grip_slip_deg"])
        self.max_plug_vs_rope = max(self.max_plug_vs_rope, grip["plug_vs_rope_deg"])
        self.max_cap_entry = max(self.max_cap_entry, grip["cap_entry_mm"])
        self.samples += 1
        if grip["plug_vs_rope_deg"] >= 90.0:
            self.obtuse_samples += 1
        gap = float(metrics.get("blocking_gap", float("nan")))
        if gap == gap:
            self.worst_blocking_gap = min(self.worst_blocking_gap, gap)

        return {
            "roll_cmd": float("nan") if commanded_roll is None else float(commanded_roll),
            "roll_error": roll_error,
            "orbit": orbit,
            "hand_yaw": yaw,
            "plug_yaw": plug_yaw,
            "strand_bearing": bearing,
            "wrap": wrap,
            "wrap_plug": wrap_plug,
            "plug_spin": 0.0 if self.spin is None else float(self.spin()),
            "near_r": float(metrics["near_r"]),
            "near_depth": float(metrics["near_depth"]),
            "near_s": float(metrics["near_s"]),
            "intrusion": intrusion,
            "q7": q7,
            "twist": twist,
            "blocking_gap": float(metrics.get("blocking_gap", float("nan"))),
            **grip,
        }

    def _grip_metrics(self) -> dict:
        """The two promises the winding schedule makes, as numbers.

        `grip_slip_deg` -- the plug's actual orientation against the one the
        attachment commands. Zero means the solver is not moving it between
        syncs. It is measured against the COMMAND, not against a snapshot taken
        when the fingers closed, because this task turns the plug on purpose once
        it is held (90 degrees of carry pitch, then a turn per orbit) and a
        snapshot reads all of that as slip. The property a snapshot used to guard
        -- that the plug follows the hand's rotation rather than sitting in a
        fixed world orientation, false in the shipped code until 2026-08-15 -- is
        now structural (`parent_quat_fn`) and proved offline every run of
        `tests/check_rope_winding_geometry.py`.

        `plug_vs_rope_deg` -- the angle between the plug's bore and the rope
        arriving at it. `connector_mesh` is a solid of revolution with no cable
        hole, so the rope always passes through the plug's surface; whether that
        reads as "plugged in" or as clipping is entirely whether it goes in
        through the cap, on axis. Past 90 degrees it is entering side-on.

        `cap_entry_mm` -- how far the rope's end sits off that axis, which is the
        other way the cap can be missed.
        """

        # Where the attachment says the plug should be, against where it is.
        # Zero unless the solver moves it between syncs.
        commanded = self.commanded_quat_fn()
        if commanded is None:
            slip = 0.0
        else:
            # Angle of commanded^-1 * actual. Via atan2 of the vector part against
            # the scalar, not `2*acos(w)`: near identity -- which is where a rigid
            # grasp lives, and the whole point of the number -- acos reads back
            # the square root of the floating-point error rather than the angle.
            drift = quat_mul(_quat_conjugate(commanded), entity_quat(self.handle))
            slip = 2.0 * float(
                np.arctan2(float(np.linalg.norm(drift[1:])), abs(float(drift[0])))
            )

        axis = _quat_axes(entity_quat(self.handle))[:, 2]
        nodes = rope_particles(self.scene)
        arc = material_coords(self.scene)[:, 0]
        fraction = arc / max(float(arc.max()), 1e-9)
        if not self.free_end_first:
            fraction = 1.0 - fraction
        end = nodes[fraction <= 0.02].mean(axis=0)
        # A short way back along the rope, so the direction is the strand's own
        # rather than one section's noise.
        back = nodes[(fraction > 0.04) & (fraction <= 0.09)].mean(axis=0)
        # Toward the rope, not away from it. The plug's bore points BACK DOWN the
        # cable it swallows, so aligned means the bore and this vector agree.
        # Written the other way round first, which made a correctly held plug read
        # 174 degrees instead of 6 -- the 2026-08-15 run's `obtuse=24/24`.
        approach = back - end
        norm = float(np.linalg.norm(approach))
        cos = (
            float(np.clip(np.dot(axis, approach / norm), -1.0, 1.0))
            if norm > 1e-9
            else 1.0
        )
        offset = end - np.asarray(entity_pos(self.handle), dtype=float)
        perpendicular = offset - axis * float(np.dot(offset, axis))
        return {
            "grip_slip_deg": float(np.degrees(slip)),
            "plug_vs_rope_deg": float(np.degrees(np.arccos(cos))),
            "cap_entry_mm": float(np.linalg.norm(perpendicular)) * 1000.0,
        }

    def summary_text(self) -> str:
        first = self.first_intrusion_phase or "none"
        q7_min = self.q7_min if self.q7_min < float("inf") else float("nan")
        q7_max = self.q7_max if self.q7_max > float("-inf") else float("nan")
        return (
            f"max_wrap={self.max_wrap:.3f} "
            # Against the plug, not the wrist. With the spin on this is the
            # success number: near zero means the rope and the plug held the same
            # relative angle through the orbits, so nothing was wrung in.
            f"max_wrap_plug={self.max_wrap_plug:.3f} "
            f"first_intrusion_phase={first} "
            f"max_intrusion={self.max_intrusion} "
            f"q7_min={q7_min:+.4f} q7_max={q7_max:+.4f} "
            f"yaw_span_deg={np.degrees(self.yaw_max - self.yaw_min):+.1f} "
            f"max_roll_error_deg={np.degrees(self.max_roll_error):.1f} "
            f"max_twist={self.max_twist:.2f} "
            # The two constraints the 2026-08-15 rework exists to keep. Lead with
            # them: `max_grip_slip_deg` must be 0 (anything else means the solver
            # is moving the plug out from under the attachment's write), and
            # `obtuse` must be 0 outside the flicks, where the plug turns in place
            # and has to sweep past the rope.
            f"max_grip_slip_deg={self.max_grip_slip:.2f}{'' if self.held else ' (to handoff)'} "
            f"max_plug_vs_rope_deg={self.max_plug_vs_rope:.1f} "
            f"obtuse={self.obtuse_samples}/{self.samples} "
            f"max_cap_entry_mm={self.max_cap_entry:.1f} "
            # Negative anywhere means the spiral stopped rising clear of itself.
            f"worst_blocking_gap={self.worst_blocking_gap:+.4f}"
        )


class RopeWindingProbe(StepProbe):
    """Per-step diagnostic; the winding number is the one that matters.

    Beyond the shared rope health fields (lowest node vs the table, spread, and
    per-step jump = blow-up detection), this samples the live signed winding
    number. A run that is winding shows it climbing one turn per orbit; a run
    whose rope is slipping off the post shows it stalling or falling back.
    """

    STALL_HAND_V = 0.0003
    FLYOUT_JUMP = 0.02

    def __init__(
        self,
        scene,
        controller,
        handle,
        spec,
        groups,
        status,
        wrap_tracker,
        *,
        every,
        surface_z,
        finger_links,
    ):
        super().__init__(scene.scene, every=every)
        self.controller = controller
        self.winding_scene = scene
        self.handle = handle
        self.spec = spec
        self.groups = groups
        self.status = status
        self.wrap_tracker = wrap_tracker
        self.finger_links = tuple(str(name) for name in finger_links)
        self.surface_z = float(surface_z)
        self.post_xy = post_center(scene.layout, spec)
        self.settled_band = settled_band_radius(scene.layout, spec)
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
            winding_centerline(self.winding_scene, self.groups),
            self.post_xy,
            self.settled_band,
        )
        self.status["winding"] = turns
        twist = rope_twist_turns(self.winding_scene, self.groups)
        contact = post_contact(self.winding_scene, self.spec)
        pads = pad_gap(self.winding_scene, self.controller.robot, self.finger_links)
        phase = self.status.get("phase", "?")
        wrap = self.wrap_tracker.sample(phase)
        flags = ""
        if pads <= 0.0:
            flags += " PADCONTACT"
        if hand_v < self.STALL_HAND_V:
            flags += " STALL"
        if min_z_above < 0.0 or (jump == jump and jump > self.FLYOUT_JUMP):
            flags += " FLYOUT?"
        if wrap["intrusion"]:
            flags += " GRIPWRAP"
        handle_z = float(entity_pos(self.handle)[2]) - self.surface_z
        print(
            f"PROBE step={self.count:05d} phase={phase} "
            f"winding={turns:+.3f} twist_legacy={twist:+.2f} "
            f"hand_v={hand_v:.5f} handle_z_above={handle_z:+.4f} "
            f"rope_minz_above_surf={min_z_above:+.4f} rope_spread={spread:.4f} "
            f"rope_jump={jump:.4f} pad_gap={pads:+.4f} "
            f"post_gap={contact['surface_gap']:+.4f} "
            f"post_contact={contact['contact_nodes']} "
            f"orbit={np.degrees(wrap['orbit']):+.1f} "
            f"hand_yaw={np.degrees(wrap['hand_yaw']):+.1f} "
            f"strand_bearing={np.degrees(wrap['strand_bearing']):+.1f} "
            f"wrap={wrap['wrap']:+.3f} wrap_plug={wrap['wrap_plug']:+.3f} "
            f"plug_spin_deg={np.degrees(wrap['plug_spin']):+.1f} "
            f"grip_slip_deg={wrap['grip_slip_deg']:.1f} "
            f"plug_vs_rope_deg={wrap['plug_vs_rope_deg']:.1f} "
            f"blocking_gap={wrap['blocking_gap']:+.4f} "
            f"near_r={wrap['near_r']:.4f} "
            f"near_depth={wrap['near_depth']:+.4f} near_s={wrap['near_s']:.3f} "
            f"intrusion={wrap['intrusion']} q7={wrap['q7']:+.4f}{flags}",
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
    print(
        "rope_winding_physical_handle_demo rope_slack "
        + _check_rope_slack(cfg, scene, spec, episode_plan),
        flush=True,
    )
    print_collision_il_contract(
        "rope_winding_physical_handle_demo",
        manipulated=manipulated,
        runtime_attachment=True,
        runtime_set_pose=True,
        success_checks=("lift_delta", "handle_follow_error", "winding_number", "placement_xy"),
    )
    contact_mode = robot_contact_mode(cfg)
    # Derived, not asserted. This line read `start_anchor=fixed_nodes` as a
    # literal until 2026-08-14 while the scene was actually following the
    # terminal's link, and that sent a whole debugging round down the wrong path.
    # A contract banner that cannot be wrong is worth more than a tidy one.
    start_anchor = (
        "pinned_nodes" if bool(cfg.task.rope.anchor_start) else "terminal_follow_band"
    )
    print(
        "rope_winding_physical_handle_demo rope_contract "
        f"rope_model={cfg.task.rope.model} rest_shape={cfg.task.rope.fem.rest_shape} "
        f"endpoint_constraint=follow_band start_anchor={start_anchor} "
        "handle_collision=False handle_needs_coup=False "
        f"robot_rope_contact={contact_mode} "
        f"ipc_links={list(cfg.task.physical_handle.finger_links) if contact_mode == 'fingers' else []} "
        f"follow_swivel={bool(getattr(cfg.task.rope.fem, 'follow_swivel', False))} "
        "placement=set_down_at_target_zone",
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
    # Tool roll per waypoint, relative to the grasp yaw. The planner works in
    # offsets because the grasp yaw is the plug's, and the scene decides it at
    # spawn (see `grasp_yaw` below).
    target_rolls = [
        0.0 if waypoint.yaw is None else float(waypoint.yaw)
        for waypoint in episode_plan.waypoints
    ]
    if cfg.run.max_waypoints is not None:
        limit = int(cfg.run.max_waypoints)
        targets = targets[:limit]
        target_labels = target_labels[:limit]
        target_steps = target_steps[:limit]
        target_rolls = target_rolls[:limit]
    speedup = max(1.0, float(cfg.run.viewer_speedup))
    slow_factor = max(1.0, float(cfg.run.slow_factor))
    target_steps = [
        _scaled_steps(steps, speedup, minimum=24, slow_factor=slow_factor)
        for steps in target_steps
    ]
    full_route = cfg.run.max_waypoints is None

    # The plug lies flat and is put DOWN at the target rather than plugged into
    # anything, so there is no socket to latch into. The hold that keeps the
    # mesh-only plug from falling through the board is the same one it spawned
    # with, re-aimed at wherever the hand left it (see the end of the run).
    # RESTING on the board at spawn: the mesh-only plug would fall through it
    # otherwise; handed to the grasp attachment atomically at on_close.
    spawn_latch = ConnectorLatch(
        scene=scene.scene,
        handle=handle,
        target_pos=entity_pos(handle),
        # The pose it is already in. Leaving this at the default upright quat
        # would both fail the tilt gate (a plug on its side reads 90 degrees off
        # vertical) and, worse, snap it upright the moment it engaged -- and the
        # rope's end is welded to it.
        target_quat=entity_quat(handle),
        capture_tolerance_xy=0.010,
        capture_tolerance_z=0.020,
        capture_max_tilt_deg=30.0,
        auto_capture=False,
    )
    if not spawn_latch.try_engage():
        raise RuntimeError("Rope winding free-end plug failed to seat at spawn.")
    grasp_attachment: list = []
    # The pose the plug was picked up in -- lying flat -- as the base the carry
    # pitch turns FROM. It is not turned back: the plug is set down standing.
    flat_quat: list = []
    pitch_angle = float(np.radians(float(getattr(physical, "carry_pitch_deg", 0.0))))
    pitch_steps = int(getattr(physical, "carry_pitch_steps", 120))

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
        # winding number and where the plug ends up.
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
    # A plug lying on its side has one grasp yaw that works: the pads have to
    # close ACROSS its axis, not along it. That axis is wherever the rope
    # arrives from, so the scene hands the angle over rather than the config
    # guessing it. An upright plug is symmetric about the approach, so there the
    # config's fixed yaw is the answer.
    grasp_yaw = (
        float(scene.plug_heading)
        if scene.plug_heading is not None
        else float(physical.grasp_yaw)
    )
    ee_quat = ee_quat_for_yaw(controller.default_ee_quat, grasp_yaw)
    # One commanded orientation per waypoint: the grasp yaw plus the planner's
    # tool roll. With `winding.yaw_track` off every roll is 0 and this is just
    # `ee_quat` repeated, i.e. the fixed-wrist behaviour.
    segment_quats = [
        ee_quat_for_yaw(controller.default_ee_quat, grasp_yaw + roll)
        for roll in target_rolls
    ]
    yaw_tracking = any(roll != 0.0 for roll in target_rolls)
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
    # Which end of that ordering the plug is at: asked once, at spawn, while the
    # rope is still where the layout put it.
    free_end_first = rope_free_end_first(scene, groups, entity_pos(handle))
    connector_cfg = cfg.task.rope.endpoint_handle.connector
    column_height = float(connector_cfg.column_height)
    cap_offset = 0.5 * column_height + float(
        getattr(connector_cfg, "cap_height", 0.35 * column_height)
    )
    # None when the switch is off, and then nothing is handed to the attachment
    # and the run is the old one exactly.
    orbit_spin = (
        OrbitSpin(controller, post_center(scene.layout, spec))
        if bool(getattr(physical, "plug_spin_tracks_orbit", False))
        else None
    )
    wrap_tracker = WrapTracker(
        scene,
        controller,
        groups,
        spec,
        handle,
        free_end_first=free_end_first,
        cap_offset=cap_offset,
        carry_pitch=float(np.radians(float(getattr(physical, "carry_pitch_deg", 0.0)))),
        spin=orbit_spin,
        commanded_quat_fn=(
            lambda: grasp_attachment[0].commanded_quat() if grasp_attachment else None
        ),
    )
    print(
        "rope_winding_physical_handle_demo grasp_geometry "
        + (
            _grasp_geometry(scene, handle, ee_quat, grasp_yaw, free_end_first)
            if scene.plug_heading is not None
            else "plug_pose=upright; no axis to align"
        )
        + "  (targets: axis_vs_pads 90, axis_vs_rope 0 or 180, off_axis 0)",
        flush=True,
    )
    print(
        "rope_winding_physical_handle_demo setup "
        f"waypoints={len(targets)} groups={len(groups)} "
        f"free_end_first={free_end_first} "
        f"grasp_qpos={float(physical.grasp_qpos):.4f} "
        f"wind_radius={spec.wind_radius:.3f} wind_z_start={spec.wind_z_start:.3f} "
        f"climb_per_turn={spec.climb_per_turn:.3f} "
        f"follow_swivel={bool(getattr(cfg.task.rope.fem, 'follow_swivel', False))} "
        f"robot_rope_friction={float(physical.robot_rope_friction):.3f} "
        f"plug_pose={connector_pose(cfg.task.rope)} "
        f"grasp_yaw={grasp_yaw:+.4f} yaw_track={yaw_tracking} "
        f"plug_spin_tracks_orbit={orbit_spin is not None} "
        f"roll_band_deg=[{np.degrees(min(target_rolls)):+.0f},"
        f"{np.degrees(max(target_rolls)):+.0f}] "
        f"viewer_speedup={speedup:.2f} slow_factor={slow_factor:.2f} "
        f"allow_target_lag={bool(cfg.run.allow_target_lag)} "
        f"segment_steps={target_steps}",
        flush=True,
    )

    def on_segment_start(index, total, label, target):
        status["phase"] = label
        status["waypoint"] = index
        # The orbit is over at `wind_exit`. Stop turning the plug there, for the
        # reason the planner holds its last wrist roll from here on: the rope is
        # wound and can no longer pay anything out, so a turn past this point
        # wrings torsion in instead of cancelling it.
        if label == "wind_exit" and orbit_spin is not None:
            orbit_spin.freeze()
            print(
                "rope_winding_physical_handle_demo plug_spin_frozen "
                f"phase={label} deg={np.degrees(orbit_spin()):+.1f}",
                flush=True,
            )
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
        # One line per waypoint, probe or no probe: this is the table the wrist
        # spin gets designed from. `strand_bearing` against `orbit` is the yaw
        # profile the wrist would have to follow; `q7` is what it has to spend.
        wrap = wrap_tracker.sample(label, commanded_roll=target_rolls[index - 1])
        print(
            "rope_winding_physical_handle_demo wrap_report "
            f"phase={label} orbit_deg={np.degrees(wrap['orbit']):+.1f} "
            f"strand_bearing_deg={np.degrees(wrap['strand_bearing']):+.1f} "
            f"hand_yaw_deg={np.degrees(wrap['hand_yaw']):+.1f} "
            f"roll_cmd_deg={np.degrees(wrap['roll_cmd']):+.1f} "
            f"roll_err_deg={np.degrees(wrap['roll_error']):+.1f} "
            f"wrap={wrap['wrap']:+.3f} wrap_plug={wrap['wrap_plug']:+.3f} "
            f"plug_spin_deg={np.degrees(wrap['plug_spin']):+.1f} "
            f"grip_slip_deg={wrap['grip_slip_deg']:.1f} "
            f"plug_vs_rope_deg={wrap['plug_vs_rope_deg']:.1f} "
            f"cap_entry_mm={wrap['cap_entry_mm']:.1f} "
            f"blocking_gap={wrap['blocking_gap']:+.4f} "
            f"twist_span={twist_probe.latest['span']:+.3f} "
            f"twist_net={twist_probe.latest['net']:+.3f} "
            f"twist_peak_s={twist_probe.latest['peak_s']:.3f} "
            f"twist_legacy={wrap['twist']:+.2f} "
            f"intrusion={wrap['intrusion']} "
            f"near_r={wrap['near_r']:.4f} near_depth={wrap['near_depth']:+.4f} "
            f"near_s={wrap['near_s']:.3f} q7={wrap['q7']:+.4f}",
            flush=True,
        )
        # One winding report per completed turn: the count should step by
        # exactly one, which is what separates winding from dragging the rope
        # around without ever catching the post.
        if label.startswith("wind_t") and label.endswith(f"{spec.arc_points_per_turn:02d}"):
            turns = winding_number(
                winding_centerline(scene, groups),
                post_center(scene.layout, spec),
                settled_band_radius(scene.layout, spec),
            )
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
            entity=handle,
            parent_pos_fn=controller.hand_pos,
            offset=offset,
            # Hold the pose it is in. The default is yaw-only and therefore
            # upright, which would wrench a plug lying on its side through 90
            # degrees in a single step -- and the rope's end band rides the
            # plug's link, so the rope goes with it.
            quat=entity_quat(handle),
            # ...and keep holding it *relative to the hand*, so the wrist's orbit
            # tracking turns the plug with it. Until 2026-08-15 only the line
            # above was here: the plug kept one world orientation for the whole
            # route while the wrist rolled +-90 and threw 180 three times, so the
            # pads swept that entire schedule across a plug that never moved, and
            # the rope's end band -- welded to the plug's link -- stayed clamped
            # in world orientation while the rope was wound twice around a post.
            parent_quat_fn=controller.hand_quat,
            # ...and turn it about the vertical as the hand orbits, so the plug
            # and the free span rotate together instead of the span wringing
            # torsion into a plug held still. See `OrbitSpin`.
            yaw_spin_fn=orbit_spin,
        )
        spawn_latch.active = False
        attachment.attach()
        grasp_attachment.append(attachment)
        flat_quat.append(entity_quat(handle))
        pitch_plug_for_carry(attachment)
        # Wrap is measured from the grasp: this is the moment the gripper and the
        # rope acquire a relationship worth accumulating. The spin's zero is the
        # same moment, and is taken after the carry pitch so the pitch itself is
        # not counted as orbit.
        wrap_tracker.reset()
        if orbit_spin is not None:
            orbit_spin.reset()

    def pitch_plug_for_carry(attachment) -> None:
        """Stand the plug up PIN UP, so the cable leaves it below the fingertips.

        Naming, because this has been read backwards more than once: for this
        task "plug up" means the PIN -- the pointed end -- is up, which puts the
        cap, where the cable enters, DOWN, and sends the rope downward out of the
        hand. `carry_pitch_deg` +90 is that pose. Always say which way BOTH ends
        go; "up" on its own is ambiguous.

        Lying flat, the plug's cap sits at the same height as the pads and the
        cable runs out along its axis -- 17 mm from the grip centre, against
        fingers that reach 10.5 mm. Measured 2026-08-15: the rope's last 3 cm was
        inside the jaw for the whole orbit (`near_s` 0.96, `near_depth` -0.011,
        `pad_gap` 0.0032), including the six waypoints where the plug's alignment
        was perfect. No amount of wrist rotation reaches that -- it is where the
        cable comes out, not which way the plug points.

        Pin up puts the outlet 17 mm BELOW the grip centre against fingertips
        that reach 9.4 mm, so the cable emerges 7.6 mm clear of them and stays
        clear at every bearing, for any number of turns. It is the only one of
        the three poses with clearance in all directions: flat leaves the outlet
        in the pad plane, and pin DOWN lifts it 8.5 mm over the pads but leaves
        it between the finger bodies, which run 44.5 mm higher still.

        Known cost, chosen with it: the outlet aims at the board 28 mm below, so
        the rope turns 90 degrees inside that drop -- about 1.6 rope diameters of
        bend radius -- and then trails along the surface, where on 2026-08-14 it
        wrapped the post's flared base instead of its shaft (`post_contact`
        48 -> 0). The knob for that is `winding.wind_z_start`, not the pose.

        The axis is the one perpendicular to both the plug's own axis and the
        vertical, which turns the cap through a quarter circle without twisting
        the rope about its own centreline -- untangle_continuous picks the same
        one for the same reason. The turn is ramped, not written, because the
        rope's end band rides the plug's link.

        It stays this way to the end. Standing up the plug is a solid of
        revolution about the VERTICAL, so orbiting no longer sweeps its bore past
        the rope and there is nothing for the wrist to track; and it is set down
        on the target zone still standing (`physical_handle.z_offset` carries the
        seat height that goes with that).
        """

        if pitch_angle == 0.0:
            return
        # `z x axis`, not `axis x z`, and then the SIGN picks the end: the plug's
        # local +z IS the cap -- the end that swallows the cable -- so about this
        # axis a POSITIVE angle turns the cap down and the pin up, which is the
        # shipped pose. With the cross product the other way round both flip,
        # which is what this did when first written.
        axis = np.cross(np.array([0.0, 0.0, 1.0]), _quat_axes(flat_quat[0])[:, 2])
        if float(np.linalg.norm(axis)) < 1e-9:
            return
        target = quat_mul(quat_about_axis(axis, pitch_angle), flat_quat[0])
        attachment.ramp_to(target, pitch_steps)
        print(
            "rope_winding_physical_handle_demo carry_pitch "
            f"deg={np.degrees(pitch_angle):.0f} steps={pitch_steps} "
            f"axis={np.round(axis / np.linalg.norm(axis), 3).tolist()}",
            flush=True,
        )

    def release_grasp_attachment():
        attachment = grasp_attachment.pop()
        attachment.release(sync=False)
        attachment_manager.attachments.remove(attachment)

    def hand_off_at_target(pre_release_pos, final_target) -> bool:
        """Pin the plug where the route put it, before the gripper lets go.

        `HandleDragPrimitive` opens the fingers and then lifts the hand 80 mm to
        get clear. The grasp attachment follows `hand_pos` and does not care that
        the fingers opened, so until 2026-08-15 the plug rode the retreat up and
        was only pinned afterwards -- at whatever height the hand had reached.
        Measured: `handle_z_above` climbed from the 0.015 it was placed at to
        0.112 and the spawn latch froze it there, plug and rope end hanging in
        mid air. Nothing in the solver corrects that: the plug is mesh-only and
        kinematically driven, so it neither falls nor rests on anything.

        Returning True tells the primitive the object is already held by someone
        else, so it does not sync its own hold on the way out.
        """

        if not grasp_attachment:
            return False
        release_grasp_attachment()
        wrap_tracker.held = False
        spawn_latch.target_pos = entity_pos(handle)
        spawn_latch.active = True
        spawn_latch.sync()
        print(
            "rope_winding_physical_handle_demo handoff_at_target "
            f"plug pinned at {np.round(entity_pos(handle), 4).tolist()} "
            f"target {np.round(final_target, 4).tolist()}",
            flush=True,
        )
        return True


    if cfg.run.probe:
        _print_probe_plan(target_labels, targets, target_steps)
    probe = None
    if stop_before_physics(cfg, scene.scene, "rope_winding_physical_handle_demo"):
        raise SystemExit(0)

    with recording_session_from_config(scene.scene, scene.cameras, cfg.recording, hud=_hud(status)):
        with attachment_manager:
            # Installed before the settle, and not behind `run.probe`: its
            # reference frame is fixed at the first sample, so that sample has to
            # be the true start of the episode, and its unwrap needs a steady
            # cadence from there on. Diagnostics you can switch off are fine;
            # a baseline you can switch off is not.
            twist_probe = TwistProbe(scene, status, every=int(cfg.run.probe_every))
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
                    wrap_tracker,
                    every=cfg.run.probe_every,
                    surface_z=scene.layout.world_z(0.0),
                    finger_links=physical.finger_links,
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
                # Fires after the last waypoint and BEFORE the fingers open and
                # the hand retreats -- which is the only moment the plug is both
                # let go of and still where the route put it.
                before_release=hand_off_at_target,
                ee_quat=ee_quat,
                segment_quats=segment_quats,
                trace=trace,
                attachment_manager=attachment_manager,
            )
            print(
                "rope_winding_physical_handle_demo wrap_summary "
                f"{wrap_tracker.summary_text()}",
                flush=True,
            )
            print(
                "rope_winding_physical_handle_demo twist_summary "
                f"{twist_probe.summary_text()}",
                flush=True,
            )
            if grasp_attachment:
                # Only reached when `before_release` did not fire -- an abort
                # returns from `run()` without ever getting to the hand-off. The
                # plug is mesh-only, so nothing in the solver would stop it
                # falling through the board; the same hold it spawned with is
                # re-aimed at wherever the hand left it.
                release_grasp_attachment()
                spawn_latch.target_pos = entity_pos(handle)
                spawn_latch.active = True
                spawn_latch.sync()
                if not result.success:
                    ending = "abort_hold"
                elif full_route:
                    ending = "placed"
                else:
                    ending = "staged_hold"
                print(
                    f"rope_winding_physical_handle_demo {ending} "
                    f"plug set down at {np.round(entity_pos(handle), 4).tolist()}",
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
            twist_probe.uninstall()

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
    # "Put down at the target", not "plugged in": the placement check is how far
    # the plug ended up from the target zone's centre.
    placement_error_xy = float(np.linalg.norm(settled_handle_pos[:2] - targets[-1][:2]))
    placement_success = placement_error_xy <= float(physical.connector_tolerance_xy)
    success = bool(
        result.success and winding_success and placement_success and full_route
    )
    metrics = {
        "task_success": bool(success),
        "physical_success": bool(result.success),
        "winding_success": bool(winding_success),
        "full_route": bool(full_route),
        "placement_success": bool(placement_success),
        "placement_error_xy": float(placement_error_xy),
        "turns": int(spec.turns),
        "start_turns": int(spec.start_turns),
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
        f"placement_success={placement_success} "
        f"placement_error_xy={placement_error_xy:.4f} "
        f"turns={spec.turns} start_turns={spec.start_turns} direction={spec.direction} "
        f"completed_waypoints={len(result.completed_segments)}/{len(targets)} "
        f"grasped={result.grasped} failure_reason={result.failure_reason}",
        flush=True,
    )
    return episode_result


@hydra.main(version_base="1.3", config_path="../../configs", config_name="rope_winding")
def main(cfg: DictConfig) -> None:
    run_from_config(cfg, scene_builder=RopeWindingSceneBuilder)


def run_from_config(cfg: DictConfig, *, scene_builder=RopeWindingSceneBuilder) -> None:
    """The whole run, from a composed config: scene, plan, episode, viewer hold.

    `scene_builder` is the task's builder class -- rope_unwinding's demo passes
    its own; everything below reads the task from `cfg` and the planner's spec.
    """

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
        f"task={cfg.task.task.id} turns={spec.turns} start_turns={spec.start_turns} "
        f"direction={spec.direction} orbit={'ccw' if spec.orbit_sign > 0 else 'cw'}"
        f"{'' if spec.orbit_direction is None else ' (forced)'} "
        f"target_winding={spec.target_winding:+.1f} expected_winding={spec.expected_winding:+.1f}",
        flush=True,
    )
    scene = scene_builder(
        cfg.env, cfg.task, cfg.robot_control, route_mode="initial"
    ).build(show_viewer=cfg.run.viewer, include_robot=True)
    route_command, episode_plan = plan_rope_winding_route(
        scene.layout,
        # The emitted wrist yaw is an offset from the pose the plug is grasped
        # in, so the planner needs that pose to aim the plug at the rope rather
        # than at wherever the spawn route happened to leave it.
        plug_heading=(
            0.0 if scene.plug_heading is None else float(scene.plug_heading)
        ),
    )
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
            f"Unwind the rope's {spec.start_turns} {spec.direction} turns from the "
            "post and set its plug down on the target zone."
            if spec.start_turns > spec.turns
            else f"Wind the rope {spec.turns} turns {spec.direction} around the post "
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
