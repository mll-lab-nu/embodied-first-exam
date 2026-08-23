"""Turn a held part until its opening lines up with a bar, then draw it off.

docx 3.4's action: grasp the C ring hanging on the closed ring's lower bar, roll it
about that bar until its opening faces the bar, translate straight out so the bar
leaves through the opening, and carry it clear. The trajectory itself was measured
without a solver first (`tests/check_c_ring_clearance.py`); this primitive is how an
arm executes it.

**Why this is not a branch on `AxialInsertPrimitive`.** Not the amount of work -- it
cannot express the motion. That primitive's `align_axis` computes its correction as
`_rotation_between(part_axis_now, insert_axis)`, and here the turn is a roll *about
the part's own normal*: the normal does not move, so the correction is identically
zero. Its `_axis_tilt` gate is zero for the same reason. Both the motion and its gate
have to be written against a different reading.

**Who turns the part: `rotate_with`.** Two modes, and the choice is a real trade.

``"wrist"`` turns the hand and lets the rigid grip carry the part, which is what
`rigid_first_track_zh.md` section 3.1 asks for: every pose change of the part is
explained by a pose change of the arm. `axial_insert.py:321` spells out why the
alternative makes a useless demonstration.

``"attachment"`` holds the hand still and ramps the part's orientation inside the grip
(`AttachmentManager.ramp_to`). It gives up that property. It exists because the wrist
sometimes cannot do the turn at all: `untangle_continuous_physical_pinch_demo.py:419`
rejected a wrist pitch as needing "a large wrist pitch to reach", and rope_winding,
untangle_continuous and swap_crossing_sign all turn their plugs this way. Measured for
docx 3.4 on 2026-08-22: commanded 45 degrees about a horizontal axis, the wrist
tracked 2 -- the hand followed the position arc and simply did not rotate.

Whichever mode runs is printed and recorded, because it changes what the recorded
episode means.

**Targets are the part's centre, and the grasp offset rotates with the hand.**
`axial_insert` keeps one world-frame carry offset because its hand never changes
orientation. Here the hand turns 90 degrees, so the offset is stored in the hand's
own frame and mapped back out every waypoint: `hand = part - R(q) @ offset_in_hand`.
Interpolating the *part* rather than the hand also matters more than usual -- the
measured clearance along this path is 0.15 mm, so a hand that travels in a straight
line while the wrist slerps would swing the part into the bar in the middle.

**Nothing here reports IK residuals, because `move_ee_to` does not.** A 90 degree
reorientation about a horizontal axis has no precedent in this repo, so the primitive
measures its own tracking error every waypoint and hands back the worst, the way
`cloth_link_attach_drag` does. That reading is the evidence for whether the wrist actually
followed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ClassVar

import numpy as np

from .attachment import slerp
from .physical_contact import entity_pos, entity_quat, quat_about_axis, quat_mul

# Distance from the `hand` link origin to the fingertip pad centre, along the tool
# axis. Vertical only while the fingers point down, which is why it is applied
# through the commanded rotation rather than added to z.
from .pick_place import HAND_TO_PAD_Z


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _matrix(quat) -> np.ndarray:
    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _quat_angle_between_axes(a, b) -> float:
    """Angle in degrees between two axes, sign-insensitive.

    A rotation axis and its negation are the same axis, so the reading has to fold
    at 90 degrees or a flipped normal reads as fully drifted.
    """

    a = np.asarray(a, dtype=float).reshape(3)
    b = np.asarray(b, dtype=float).reshape(3)
    scale = float(np.linalg.norm(a) * np.linalg.norm(b))
    if scale < 1e-12:
        return 0.0
    return float(np.rad2deg(np.arccos(np.clip(abs(float(np.dot(a, b))) / scale, 0.0, 1.0))))


def _quat_angle(a, b) -> float:
    """Angle between two orientations, in radians, sign-insensitive."""

    dot = abs(float(np.dot(np.asarray(a, dtype=float), np.asarray(b, dtype=float))))
    return float(2.0 * np.arccos(np.clip(dot, -1.0, 1.0)))


def tool_offset(quat, distance: float) -> np.ndarray:
    """Where the fingertip pads sit relative to the hand origin, at this orientation."""

    return _matrix(quat) @ np.array([0.0, 0.0, float(distance)])


@dataclass
class _Tracking:
    """Worst tracking error seen so far.

    Carried as an argument rather than kept on the primitive because the primitive
    is frozen, like every other one in this package, and because making it explicit
    keeps two concurrent runs from sharing it.

    The TURN gets its own instance. A single worst-over-the-run figure is dominated
    by the long free-space flight from the home pose -- measured 68.6 mm and 28.6
    degrees before the hand had even reached the part on 2026-08-23 -- and reading
    that as evidence about the turn is how a wrist that was merely lagging on
    approach gets blamed for a turn it may well be able to make.
    """

    worst_pose_error: float = 0.0
    worst_tilt_rad: float = 0.0


@dataclass(frozen=True)
class GatewayExtractResult:
    """What the extraction did, and how well the arm tracked it."""

    success: bool
    hovered: bool
    grasped: bool
    aligned: bool
    extracted: bool
    failure_reason: str | None
    initial_part_pos: np.ndarray
    aligned_part_pos: np.ndarray
    final_part_pos: np.ndarray
    finger_qpos: float
    hover_xy_error: float
    grasp_pos_error: float
    # The alignment reading at three points, because one number at the end cannot say
    # WHERE it went wrong. If the part is already off at `grasp_align_deg`, the hand
    # disturbed it on the way in; if it is right there and wrong after the turn, the
    # wrist is the problem. Those two have opposite fixes.
    hover_align_deg: float
    grasp_align_deg: float
    align_deg: float
    # Tracking during the turn alone, apart from the run-wide worst below.
    align_pose_error: float
    align_tilt_rad: float
    worst_pose_error: float
    worst_tilt_rad: float
    completed_phases: tuple[str, ...]


@dataclass(frozen=True)
class GatewayExtractPrimitive:
    """Roll a grasped part about an external axis, draw it off, and set it down."""

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
        "hover_settle",
        "descend",
        "close",
        "grasp_settle",
        "align",
        "align_settle",
        "extract",
        "clear",
        "place",
        "release",
        "release_settle",
        "retreat",
    )

    steps_per_phase: int
    gripper_steps: int
    approach_clearance: float
    retreat_clearance: float
    grasp_qpos: float | None = None
    # Hold above the part before descending. `move_ee_to` runs one seeded solve per
    # waypoint and reports nothing, so the hand arrives wherever 50 iterations got to;
    # settling here is what turns that into a pose worth measuring, and measuring it
    # before the descent is what keeps a misaligned hand from knocking a free part
    # away instead of gripping it.
    hover_settle_steps: int = 40
    # "wrist" or "attachment"; see the module docstring. Not a tuning knob -- it
    # decides whether the episode's action stream explains the part's rotation.
    rotate_with: str = "wrist"
    # How many measure-and-turn passes the attachment mode gets. One is not enough:
    # a pass does not necessarily deliver the whole rotation it asks for, and the
    # alignment gate is tight because the extraction has 2 mm of room per side.
    align_passes: int = 3
    # Bounds on the hover re-aim. It corrects for the part having been nudged since
    # the pose was handed in, so it is a small correction by construction; a large one
    # means the measurement is wrong, and following it does more damage than ignoring
    # the nudge would have.
    max_regrasp_move: float = 0.030
    max_regrasp_wrist_deg: float = 30.0
    close_hold_steps: int = 30
    align_steps: int | None = None
    align_settle_steps: int = 30
    extract_steps: int | None = None
    release_hold_steps: int = 100
    motion_settle_steps: int = 0
    # Under an assisted carry the part moves whether or not the pads touched it, so
    # finger travel is the only reading that separates "closed on the part" from
    # "closed on air". None leaves it unchecked; the value is reported either way,
    # which is how the threshold gets set in the first place.
    min_finger_qpos: float | None = None
    max_grasp_pos_error: float = 0.020
    # The measured clearance along the extraction is 0.15 mm against a 2.00 mm
    # per-side opening, so the alignment gate is tight by necessity, not by taste.
    max_align_deg: float = 3.0
    verbose: bool = False

    def run(
        self,
        controller,
        *,
        part: Any,
        grasp_pos,
        rotation_axis,
        rotation_deg: float,
        extract_delta,
        clear_delta,
        place_delta,
        ee_quat=None,
        align_probe: Callable[[], float] | None = None,
        align_target_fn: Callable[[], Any] | None = None,
        regrasp_fn: Callable[[], Any] | None = None,
        attach_fn: Callable[[], Any] | None = None,
        release_fn: Callable[[], None] | None = None,
        skip_align: bool = False,
    ) -> GatewayExtractResult:
        """Execute the extraction.

        ``grasp_pos`` is where the fingertip pads must land, in world coordinates --
        a point on the part, not a hand pose. ``extract_delta`` / ``clear_delta`` /
        ``place_delta`` are displacements of the part's CENTRE, for the reason
        `axial_insert` gives: aiming the hand at a precomputed number assumes the
        part is exactly where it was nominally placed, and spends the receptacle's
        clearance on a deviation nobody measured.

        ``align_probe`` returns the alignment reading in degrees (for docx 3.4, the
        angle from the opening to the bar). It is a callback rather than an import so
        this module stays out of `verification/`.

        ``skip_align=True`` runs everything except the turn. That is the anti-shortcut
        contrast: the same grasp, the same descent, the same carry, and an opening
        that was never brought onto the bar.
        """

        base_quat = np.asarray(
            controller.default_ee_quat if ee_quat is None else ee_quat, dtype=float
        ).reshape(4)
        turn = quat_about_axis(rotation_axis, np.deg2rad(float(rotation_deg)))
        aligned_quat = base_quat if skip_align else quat_mul(turn, base_quat)
        aligned_quat = np.asarray(aligned_quat, dtype=float) / np.linalg.norm(aligned_quat)

        grasp_pos = np.asarray(grasp_pos, dtype=float).reshape(3)
        hand_at_grasp = grasp_pos - tool_offset(base_quat, HAND_TO_PAD_Z)
        hand_approach = hand_at_grasp - tool_offset(base_quat, float(self.approach_clearance))

        phases: list[str] = []
        track = _Tracking()
        initial_part_pos = entity_pos(part)

        controller.open_gripper(int(self.gripper_steps))
        phases.append("open")

        self._move_hand(controller, track, hand_approach, quat=base_quat,
                        start_quat=_as_numpy(controller.hand_quat()).reshape(4))
        phases.append("approach")

        # Hover: settle, then check the pads are over the grasp point before going
        # down. The part is free and light, so a hand that is off by more than the
        # tube is wide will push it away on the way in, and the close that follows
        # grips nothing while every other reading still looks plausible.
        controller.step(int(self.hover_settle_steps))

        # Re-aim at where the part is NOW, then settle again. The pose handed in was
        # measured before the arm moved, and by the time the hand is overhead the part
        # has been nudged: measured 2026-08-23, the ring reached hover with its plane
        # 25.8 deg off the layout's, which puts the true tube 22.7 mm from the point
        # this was told to grasp and turns the closing axis 26 deg off the tube's
        # normal. The pads then graze the tube instead of pinching it -- they close to
        # the commanded width on air while shoving the part on the way past.
        #
        # Both quantities have to be re-derived, not just the position: the wrist yaw
        # that closes ACROSS the tube depends on which way the part is facing.
        if regrasp_fn is not None:
            new_pos, new_quat = regrasp_fn()
            new_pos = np.asarray(new_pos, dtype=float).reshape(3)
            new_quat = np.asarray(new_quat, dtype=float).reshape(4)
            new_quat = new_quat / np.linalg.norm(new_quat)
            # How big a correction is being asked for? A re-aim is meant to be a few
            # millimetres and a few degrees. Anything larger means the reading is bad,
            # and acting on it swings the hand through the very part it is aiming at:
            # measured 2026-08-23, an unclamped re-aim turned the wrist 179 deg and
            # left the ring at 168 deg from the bar, worse than it started.
            self._log(
                "regrasp", track,
                moved=float(np.linalg.norm(new_pos - grasp_pos)),
                wrist_deg=float(np.rad2deg(_quat_angle(base_quat, new_quat))),
            )
            if (
                float(np.linalg.norm(new_pos - grasp_pos)) > float(self.max_regrasp_move)
                or float(np.rad2deg(_quat_angle(base_quat, new_quat)))
                > float(self.max_regrasp_wrist_deg)
            ):
                return self._abort(
                    controller, track, phases, release_fn,
                    reason=(
                        f"regrasp_implausible(moved="
                        f"{float(np.linalg.norm(new_pos - grasp_pos)):.4f}, wrist="
                        f"{float(np.rad2deg(_quat_angle(base_quat, new_quat))):.1f}deg)"
                    ),
                    initial_part_pos=initial_part_pos, finger_qpos=0.0,
                    hover_xy_error=0.0, grasp_pos_error=0.0,
                    hover_align_deg=0.0, grasp_align_deg=0.0,
                )
            grasp_pos = new_pos
            base_quat = new_quat
            aligned_quat = base_quat if skip_align else quat_mul(
                quat_about_axis(rotation_axis, np.deg2rad(float(rotation_deg))), base_quat
            )
            aligned_quat = np.asarray(aligned_quat, dtype=float) / np.linalg.norm(aligned_quat)
            hand_at_grasp = grasp_pos - tool_offset(base_quat, HAND_TO_PAD_Z)
            self._move_hand(
                controller, track,
                hand_at_grasp - tool_offset(base_quat, float(self.approach_clearance)),
                quat=base_quat,
                start_quat=_as_numpy(controller.hand_quat()).reshape(4),
            )
            controller.step(int(self.hover_settle_steps))

        pads_now = np.asarray(controller.hand_pos(), dtype=float) + tool_offset(
            base_quat, HAND_TO_PAD_Z
        )
        hover_xy_error = float(np.linalg.norm((pads_now - grasp_pos)[:2]))
        hover_align_deg = float(align_probe()) if align_probe is not None else 0.0
        phases.append("hover_settle")
        self._log("hover", track, xy_error=hover_xy_error, align_deg=hover_align_deg)
        if hover_xy_error > float(self.max_grasp_pos_error):
            return self._abort(
                controller, track, phases, release_fn,
                reason=f"hover_misaligned(xy_error={hover_xy_error:.4f})",
                initial_part_pos=initial_part_pos, finger_qpos=0.0,
                hover_xy_error=hover_xy_error, grasp_pos_error=hover_xy_error,
                hover_align_deg=hover_align_deg, grasp_align_deg=hover_align_deg,
            )

        # Which phase tips the part out of its own plane, and by how much? The layout
        # spawns the part unrotated with its normal ON the rotation axis (checked
        # offline by `tests/check_c_ring_clearance.py`), so the part's live normal is
        # just the current rotation applied to that axis. Sampled at hover, after the
        # descent and after the close, because a reading taken only at the end cannot
        # say which phase did it.
        def drift() -> float:
            return _quat_angle_between_axes(
                _matrix(entity_quat(part)) @ np.asarray(rotation_axis, dtype=float),
                rotation_axis,
            )

        self._log("pre_descend", track, align_deg=hover_align_deg, axis_drift=drift())
        self._move_hand(controller, track, hand_at_grasp, quat=base_quat)
        phases.append("descend")
        self._log(
            "post_descend", track,
            align_deg=float(align_probe()) if align_probe is not None else 0.0,
            axis_drift=drift(),
        )

        # Weld BEFORE the fingers move, not after. A ring hanging on a bar is a free
        # pendulum with a swivel: the first pad to touch it shoves it away instead of
        # trapping it. Measured 2026-08-23, closing on the unheld ring knocked its
        # normal 57 deg off the layout axis, and no amount of in-plane alignment can
        # turn that back -- the roll axis IS the normal. Welding first pins the pose
        # the hover already got right (0.5 mm) so the close cannot spoil it.
        #
        # This does not paper over a missed grasp, it exposes one. With the ring held
        # still, the fingers stall on the tube if they are actually around it and run
        # to the commanded width if they are not, so `finger_qpos` finally means
        # something; before this it read 0.0041 either way because the tube was being
        # swept aside rather than gripped.
        attachment = attach_fn() if attach_fn is not None else None

        if self.grasp_qpos is None:
            controller.close_gripper(int(self.gripper_steps))
        else:
            controller.set_gripper(float(self.grasp_qpos), steps=int(self.gripper_steps))
        phases.append("close")
        controller.step(int(self.close_hold_steps))
        phases.append("grasp_settle")

        finger_qpos = float(np.min(_as_numpy(controller.gripper_qpos())))
        grasp_align_deg = float(align_probe()) if align_probe is not None else 0.0
        pads = np.asarray(controller.hand_pos(), dtype=float) + tool_offset(
            base_quat, HAND_TO_PAD_Z
        )
        grasp_pos_error = float(np.linalg.norm(pads - grasp_pos))
        grasped = grasp_pos_error <= float(self.max_grasp_pos_error) and (
            self.min_finger_qpos is None or finger_qpos >= float(self.min_finger_qpos)
        )
        self._log("grasp", track, finger_qpos=finger_qpos, pos_error=grasp_pos_error,
                  align_deg=grasp_align_deg, disturbed=grasp_align_deg - hover_align_deg,
                  axis_drift=drift())
        if not grasped:
            return self._abort(
                controller, track, phases, release_fn,
                reason=f"grasp_failed(finger_qpos={finger_qpos:.4f}, "
                       f"pos_error={grasp_pos_error:.4f})",
                initial_part_pos=initial_part_pos, finger_qpos=finger_qpos,
                hover_xy_error=hover_xy_error, grasp_pos_error=grasp_pos_error,
                hover_align_deg=hover_align_deg, grasp_align_deg=grasp_align_deg,
            )

        # The part is welded in the hand frame from here on, so the offset from hand
        # to part centre is constant in THAT frame and has to be rotated back out at
        # every waypoint. This is the one place this primitive differs in kind from
        # `axial_insert`, whose hand never turns.
        offset_in_hand = _matrix(base_quat).T @ (
            entity_pos(part) - np.asarray(controller.hand_pos(), dtype=float)
        )
        part_center = entity_pos(part)

        align_steps = int(self.align_steps or self.steps_per_phase)
        turn_track = _Tracking()
        if self.rotate_with == "attachment" and attachment is not None:
            # Ramp to an ABSOLUTE pose, not an incremental roll, and iterate.
            #
            # A roll about the part's own normal cannot fix a part whose normal is
            # wrong, and the descent tips this one badly: measured 2026-08-23, the
            # ring reached the close with its normal 65 deg off the layout axis. Rolled
            # about that axis the ring does not travel along the bar it hangs on, it
            # sweeps through it -- which is what `min_gap_seen` was reporting as 5 mm
            # of interpenetration. The target below puts the normal back on the layout
            # axis and the opening on the bar in one motion, so the roll that follows
            # is a roll along the bar.
            #
            # Iterated because the target is re-read each pass: it is measured against
            # the part's live centre, and one ramp does not have to land it exactly.
            for attempt in range(max(1, int(self.align_passes))):
                if align_target_fn is not None:
                    target = np.asarray(align_target_fn(), dtype=float).reshape(4)
                else:
                    target = quat_mul(
                        quat_about_axis(rotation_axis, np.deg2rad(float(rotation_deg))),
                        entity_quat(part),
                    )
                residual = float(np.rad2deg(_quat_angle(entity_quat(part), target)))
                self._log("turn_pass", turn_track, attempt=attempt + 1,
                          residual=residual, axis_drift=drift())
                if residual <= float(self.max_align_deg):
                    break
                # ramp_to counts SYNC calls, and the manager syncs twice a step. Rather
                # than trust that accounting, step until it says it is done: `ramping()`
                # clears when `_advance_ramp` reaches the last step.
                attachment.ramp_to(target, 2 * align_steps)
                for _ in range(4 * align_steps):
                    if not attachment.ramping():
                        break
                    controller.step(1)
        else:
            self._move_part(
                controller, turn_track, part_from=part_center, part_to=part_center,
                quat_from=base_quat, quat_to=aligned_quat,
                offset_in_hand=offset_in_hand, steps=align_steps,
            )
            track.worst_pose_error = max(track.worst_pose_error, turn_track.worst_pose_error)
            track.worst_tilt_rad = max(track.worst_tilt_rad, turn_track.worst_tilt_rad)
        phases.append("align")
        controller.step(int(self.align_settle_steps))
        phases.append("align_settle")

        # The grip changed if the attachment did the turning, and the hand may have
        # tracked imperfectly if the wrist did, so re-measure rather than trusting the
        # offset captured before the turn.
        carry_quat = base_quat if self.rotate_with == "attachment" else aligned_quat
        offset_in_hand = _matrix(carry_quat).T @ (
            entity_pos(part) - np.asarray(controller.hand_pos(), dtype=float)
        )
        part_center = entity_pos(part)

        align_deg = float(align_probe()) if align_probe is not None else 0.0
        self._log("turn", turn_track, align_deg=align_deg)
        aligned_part_pos = entity_pos(part)
        aligned = skip_align or align_deg <= float(self.max_align_deg)
        self._log("align", track, align_deg=align_deg)
        if not aligned:
            # Stop before the descent rather than after: the opening is not on the
            # bar, so going down drives the ring into it. Under an assisted carry
            # that is a tunnel, not a jam, and the episode would look fine.
            return self._abort(
                controller, track, phases, release_fn,
                reason=f"align_failed(opening_to_bar={align_deg:.2f}deg)",
                initial_part_pos=initial_part_pos, finger_qpos=finger_qpos,
                hover_xy_error=hover_xy_error, grasp_pos_error=grasp_pos_error,
                hover_align_deg=hover_align_deg, grasp_align_deg=grasp_align_deg,
                grasped=True, align_deg=align_deg, aligned_part_pos=aligned_part_pos,
                align_pose_error=turn_track.worst_pose_error,
                align_tilt_rad=turn_track.worst_tilt_rad,
            )

        for name, delta, steps in (
            ("extract", extract_delta, self.extract_steps),
            ("clear", clear_delta, None),
            ("place", place_delta, None),
        ):
            target = part_center + np.asarray(delta, dtype=float).reshape(3)
            self._move_part(
                controller, track, part_from=part_center, part_to=target,
                quat_from=carry_quat, quat_to=carry_quat,
                offset_in_hand=offset_in_hand, steps=steps,
            )
            part_center = target
            phases.append(name)
            self._log(name, track, part=entity_pos(part))

        if release_fn is not None:
            release_fn()
        controller.open_gripper(int(self.gripper_steps))
        phases.append("release")
        controller.step(int(self.release_hold_steps))
        phases.append("release_settle")

        hand_now = np.asarray(controller.hand_pos(), dtype=float)
        self._move_hand(
            controller, track,
            hand_now - tool_offset(carry_quat, float(self.retreat_clearance)),
            quat=carry_quat,
        )
        phases.append("retreat")

        return GatewayExtractResult(
            success=True, hovered=True, grasped=True, aligned=True, extracted=True,
            failure_reason=None,
            initial_part_pos=initial_part_pos,
            aligned_part_pos=aligned_part_pos,
            final_part_pos=entity_pos(part),
            finger_qpos=finger_qpos,
            hover_xy_error=hover_xy_error,
            grasp_pos_error=grasp_pos_error,
            hover_align_deg=hover_align_deg,
            grasp_align_deg=grasp_align_deg,
            align_deg=align_deg,
            align_pose_error=turn_track.worst_pose_error,
            align_tilt_rad=turn_track.worst_tilt_rad,
            worst_pose_error=track.worst_pose_error,
            worst_tilt_rad=track.worst_tilt_rad,
            completed_phases=tuple(phases),
        )

    # ------------------------------------------------------------------ motion

    def _move_hand(self, controller, track, target, *, quat, start_quat=None,
                   steps=None) -> None:
        """Straight line for the hand. Used before the part is in the grip."""

        start = np.asarray(controller.hand_pos(), dtype=float)
        target = np.asarray(target, dtype=float)
        steps = max(1, int(self.steps_per_phase if steps is None else steps))
        for step in range(1, steps + 1):
            alpha = self._ease(step / steps)
            waypoint_quat = quat if start_quat is None else slerp(start_quat, quat, alpha)
            self._command(controller, track, (1.0 - alpha) * start + alpha * target,
                          waypoint_quat)
        controller.step(max(0, int(self.motion_settle_steps)))

    def _move_part(self, controller, track, *, part_from, part_to, quat_from, quat_to,
                   offset_in_hand, steps=None) -> None:
        """Straight line for the PART, with the hand solved for at every waypoint.

        During the turn ``part_from == part_to``: the part's centre is held while the
        orientation slerps, which is the pure roll the clearance was measured on. A
        hand-space interpolation would instead swing the part through an arc, and
        with 0.15 mm of room that is the difference between clearing the bar and
        going through it.
        """

        part_from = np.asarray(part_from, dtype=float).reshape(3)
        part_to = np.asarray(part_to, dtype=float).reshape(3)
        steps = max(1, int(self.steps_per_phase if steps is None else steps))
        for step in range(1, steps + 1):
            alpha = self._ease(step / steps)
            quat = slerp(quat_from, quat_to, alpha)
            part = (1.0 - alpha) * part_from + alpha * part_to
            self._command(controller, track, part - _matrix(quat) @ offset_in_hand, quat)
        controller.step(max(0, int(self.motion_settle_steps)))

    def _command(self, controller, track, hand_target, quat) -> None:
        """One waypoint, plus the tracking error nobody else measures."""

        controller.move_ee_to(hand_target, quat=quat, steps=1, continuous_ik=True)
        reached = np.asarray(controller.hand_pos(), dtype=float)
        track.worst_pose_error = max(
            track.worst_pose_error, float(np.linalg.norm(reached - hand_target))
        )
        track.worst_tilt_rad = max(
            track.worst_tilt_rad,
            _quat_angle(_as_numpy(controller.hand_quat()).reshape(4), quat),
        )

    @staticmethod
    def _ease(progress: float) -> float:
        return float(0.5 - 0.5 * np.cos(np.pi * progress))

    # ----------------------------------------------------------------- helpers

    def _abort(self, controller, track, phases, release_fn, *, reason, initial_part_pos,
               finger_qpos, grasp_pos_error, hover_xy_error=0.0, hover_align_deg=0.0,
               grasp_align_deg=0.0, grasped=False, align_deg=0.0,
               align_pose_error=0.0, align_tilt_rad=0.0,
               aligned_part_pos=None) -> GatewayExtractResult:
        if release_fn is not None:
            release_fn()
        controller.open_gripper(int(self.gripper_steps))
        phases.append("recovery_open")
        hand_now = np.asarray(controller.hand_pos(), dtype=float)
        # Back off along the tool axis the hand is ACTUALLY holding, not the default
        # one. This primitive's approach is face-on and horizontal, so retreating
        # along the default (fingers-down) axis would drive the hand into the table.
        held_quat = _as_numpy(controller.hand_quat()).reshape(4)
        self._move_hand(
            controller, track,
            hand_now - tool_offset(held_quat, float(self.retreat_clearance)),
            quat=held_quat,
        )
        phases.append("recovery_retreat")
        zero = np.zeros(3)
        return GatewayExtractResult(
            success=False, hovered=hover_xy_error <= float(self.max_grasp_pos_error),
            grasped=grasped, aligned=False, extracted=False,
            failure_reason=reason,
            initial_part_pos=initial_part_pos,
            aligned_part_pos=zero if aligned_part_pos is None else aligned_part_pos,
            final_part_pos=zero,
            finger_qpos=finger_qpos,
            hover_xy_error=hover_xy_error,
            grasp_pos_error=grasp_pos_error,
            hover_align_deg=hover_align_deg,
            grasp_align_deg=grasp_align_deg,
            align_deg=align_deg,
            align_pose_error=align_pose_error,
            align_tilt_rad=align_tilt_rad,
            worst_pose_error=track.worst_pose_error,
            worst_tilt_rad=track.worst_tilt_rad,
            completed_phases=tuple(phases),
        )

    def _log(self, label: str, track: _Tracking, **values) -> None:
        if not self.verbose:
            return
        parts = []
        for key, value in values.items():
            rendered = (
                np.array2string(np.round(value, 4))
                if isinstance(value, np.ndarray)
                else format(float(value), ".4f")
            )
            parts.append(f"{key}={rendered}")
        print(
            f"[gateway_extract {label}] {' '.join(parts)} "
            f"pose_err={track.worst_pose_error:.4f} "
            f"tilt={np.rad2deg(track.worst_tilt_rad):.2f}deg",
            flush=True,
        )
