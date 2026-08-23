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

**The wrist turns; the grip does not.** `AttachmentManager.ramp_to` could rotate the
part inside the hand and reach the same final pose, and that is exactly what
`axial_insert.py:321` warns against: the part turns while the arm holds still, so
nothing in the action stream explains the motion and a policy trained on it never
learns to align anything. Same rule as `rigid_first_track_zh.md` section 3.1. So the
caller welds the part rigidly in the hand frame (`parent_quat_fn=controller.hand_quat`)
and this primitive turns the wrist.

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
from .physical_contact import entity_pos, quat_about_axis, quat_mul

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


def _quat_angle(a, b) -> float:
    """Angle between two orientations, in radians, sign-insensitive."""

    dot = abs(float(np.dot(np.asarray(a, dtype=float), np.asarray(b, dtype=float))))
    return float(2.0 * np.arccos(np.clip(dot, -1.0, 1.0)))


def rotation_between(source, target) -> np.ndarray:
    """Shortest rotation carrying ``source`` onto ``target``, as (w, x, y, z)."""

    a = np.asarray(source, dtype=float) / np.linalg.norm(source)
    b = np.asarray(target, dtype=float) / np.linalg.norm(target)
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if dot > 1.0 - 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    if dot < -1.0 + 1e-12:
        # Antiparallel: any perpendicular axis is a valid half turn.
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if float(np.linalg.norm(axis)) < 1e-9:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        return quat_about_axis(axis, np.pi)
    return quat_about_axis(np.cross(a, b), float(np.arccos(dot)))


def face_on_quat(default_ee_quat, tool_axis, roll_deg: float = 0.0) -> np.ndarray:
    """Wrist pose whose tool axis points along ``tool_axis``, plus a roll about it.

    Built by turning the default pose rather than written out, so it follows the
    layout: for docx 3.4 the tool axis is the C ring's own normal, which is what makes
    the extraction's turn a roll about the tool axis instead of a reorientation of the
    whole hand.

    ``roll_deg`` spins the hand about that axis. Which roll puts the finger pads
    across the tube rather than along it depends on the Franka hand's own geometry,
    not on anything derivable from the scene, so it is left for a caller to set from
    what the viewer shows.
    """

    base = np.asarray(default_ee_quat, dtype=float).reshape(4)
    current = _matrix(base) @ np.array([0.0, 0.0, 1.0])
    quat = quat_mul(rotation_between(current, tool_axis), base)
    if roll_deg:
        quat = quat_mul(quat_about_axis(tool_axis, np.deg2rad(float(roll_deg))), quat)
    return quat / np.linalg.norm(quat)


def tool_offset(quat, distance: float) -> np.ndarray:
    """Where the fingertip pads sit relative to the hand origin, at this orientation."""

    return _matrix(quat) @ np.array([0.0, 0.0, float(distance)])


@dataclass
class _Tracking:
    """Worst tracking error seen so far.

    Carried as an argument rather than kept on the primitive because the primitive
    is frozen, like every other one in this package, and because making it explicit
    keeps two concurrent runs from sharing it.
    """

    worst_pose_error: float = 0.0
    worst_tilt_rad: float = 0.0


@dataclass(frozen=True)
class GatewayExtractResult:
    """What the extraction did, and how well the arm tracked it."""

    success: bool
    grasped: bool
    aligned: bool
    extracted: bool
    failure_reason: str | None
    initial_part_pos: np.ndarray
    aligned_part_pos: np.ndarray
    final_part_pos: np.ndarray
    finger_qpos: float
    grasp_pos_error: float
    align_deg: float
    worst_pose_error: float
    worst_tilt_rad: float
    completed_phases: tuple[str, ...]


@dataclass(frozen=True)
class GatewayExtractPrimitive:
    """Roll a grasped part about an external axis, draw it off, and set it down."""

    NOMINAL_PHASES: ClassVar[tuple[str, ...]] = (
        "open",
        "approach",
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
        self._move_hand(controller, track, hand_at_grasp, quat=base_quat)
        phases.append("descend")

        if self.grasp_qpos is None:
            controller.close_gripper(int(self.gripper_steps))
        else:
            controller.set_gripper(float(self.grasp_qpos), steps=int(self.gripper_steps))
        phases.append("close")
        controller.step(int(self.close_hold_steps))
        phases.append("grasp_settle")

        finger_qpos = float(np.min(_as_numpy(controller.gripper_qpos())))
        pads = np.asarray(controller.hand_pos(), dtype=float) + tool_offset(
            base_quat, HAND_TO_PAD_Z
        )
        grasp_pos_error = float(np.linalg.norm(pads - grasp_pos))
        grasped = grasp_pos_error <= float(self.max_grasp_pos_error) and (
            self.min_finger_qpos is None or finger_qpos >= float(self.min_finger_qpos)
        )
        self._log("grasp", track, finger_qpos=finger_qpos, pos_error=grasp_pos_error)
        if not grasped:
            return self._abort(
                controller, track, phases, release_fn,
                reason=f"grasp_failed(finger_qpos={finger_qpos:.4f}, "
                       f"pos_error={grasp_pos_error:.4f})",
                initial_part_pos=initial_part_pos, finger_qpos=finger_qpos,
                grasp_pos_error=grasp_pos_error,
            )

        attachment = attach_fn() if attach_fn is not None else None

        # The part is welded in the hand frame from here on, so the offset from hand
        # to part centre is constant in THAT frame and has to be rotated back out at
        # every waypoint. This is the one place this primitive differs in kind from
        # `axial_insert`, whose hand never turns.
        offset_in_hand = _matrix(base_quat).T @ (
            entity_pos(part) - np.asarray(controller.hand_pos(), dtype=float)
        )
        part_center = entity_pos(part)

        self._move_part(
            controller, track, part_from=part_center, part_to=part_center,
            quat_from=base_quat, quat_to=aligned_quat,
            offset_in_hand=offset_in_hand, steps=self.align_steps,
        )
        phases.append("align")
        controller.step(int(self.align_settle_steps))
        phases.append("align_settle")

        align_deg = float(align_probe()) if align_probe is not None else 0.0
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
                grasp_pos_error=grasp_pos_error, grasped=True, align_deg=align_deg,
                aligned_part_pos=aligned_part_pos,
            )

        for name, delta, steps in (
            ("extract", extract_delta, self.extract_steps),
            ("clear", clear_delta, None),
            ("place", place_delta, None),
        ):
            target = part_center + np.asarray(delta, dtype=float).reshape(3)
            self._move_part(
                controller, track, part_from=part_center, part_to=target,
                quat_from=aligned_quat, quat_to=aligned_quat,
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
            hand_now - tool_offset(aligned_quat, float(self.retreat_clearance)),
            quat=aligned_quat,
        )
        phases.append("retreat")

        del attachment  # lifetime belongs to the caller's AttachmentManager
        return GatewayExtractResult(
            success=True, grasped=True, aligned=True, extracted=True, failure_reason=None,
            initial_part_pos=initial_part_pos,
            aligned_part_pos=aligned_part_pos,
            final_part_pos=entity_pos(part),
            finger_qpos=finger_qpos,
            grasp_pos_error=grasp_pos_error,
            align_deg=align_deg,
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
               finger_qpos, grasp_pos_error, grasped=False, align_deg=0.0,
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
            success=False, grasped=grasped, aligned=False, extracted=False,
            failure_reason=reason,
            initial_part_pos=initial_part_pos,
            aligned_part_pos=zero if aligned_part_pos is None else aligned_part_pos,
            final_part_pos=zero,
            finger_qpos=finger_qpos,
            grasp_pos_error=grasp_pos_error,
            align_deg=align_deg,
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
