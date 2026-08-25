"""Attach to a patch of PBD cloth, carry it along waypoints, put it down.

The waypoints come from a planner and this file does not care what shape they
make: `cloth_fold` sends half a turn about the fold line, `cloth_unpleat` sends a
straight horizontal drag. What this primitive owns is the attach-and-carry
mechanism -- descend, check the hand actually reached the grasp point, close,
bind the caught particles to the gripper link, drive, release.

Written as its own primitive rather than as flags on
`PBDParticleAttachmentDragPrimitive`, which is the other PBD attach-and-drag
motion in the repo. Three things differ, and each would have meant a new branch
inside a primitive `untangle_continuous` depends on:

- that one lifts the material straight up by ``lift_delta`` before its waypoints,
  as a test that the attachment holds. A fold cannot: the grasped corner is
  joined to the fold line by a fixed length of material, so lifting it vertically
  first either stretches the cloth or leaves the arc starting from the wrong
  place. The arc's own first waypoint is already off the table;
- it settles for ``motion_settle_steps`` after every waypoint, which is right for
  a handful of drag targets and wrong for twelve segments of one continuous
  sweep -- it would insert 240 idle steps into an 121-step motion;
- it carries the material by writing particle positions from Python each step.
  Measured 2026-08-20 against the alternative of binding them to the gripper link
  before the solver runs: the link binding follows perfectly where the write
  follows 96%, needs half to a fifth of the stretch, and does not push cloth
  through the table (the write is applied after contact is resolved, so nothing
  stops it).

What IS copied is the part that matters for safety: the pads stop
``touch_clearance`` above the cloth and never touch it, and an attach further
than ``attach_tolerance`` from the intended point fails the episode honestly
instead of grabbing at a distance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from topogym.primitives.pick_place import HAND_TO_PAD_Z


def _as_numpy_qpos(value):
    """Joint vector as plain NumPy, whatever backend handed it over."""

    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value, dtype=float)


@dataclass
class ClothAttachDragResult:
    success: bool
    grasped: bool
    attached_particles: int
    attach_error: float
    worst_follow_error: float
    #: The ARM's own tracking error, separate from the cloth's. A large value
    #: here means the IK never reached the commanded pose, so nothing downstream
    #: is a statement about the trajectory or the material.
    worst_pose_error: float = float("nan")
    worst_tilt_rad: float = float("nan")
    failure_reason: str | None = None
    completed_phases: tuple[str, ...] = ()


def _quat_angle(a, b) -> float:
    """Angle between two orientations, radians. 0 when they match."""

    a = np.asarray(a, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    a = a / max(float(np.linalg.norm(a)), 1e-12)
    b = b / max(float(np.linalg.norm(b)), 1e-12)
    return float(2.0 * np.arccos(min(1.0, abs(float(np.dot(a, b))))))


def attached_indices(
    nodes: np.ndarray, center, radius: float, *, z_band: float | None = None
) -> np.ndarray:
    """Particles within ``radius`` of the grasp point, in the plane.

    Planar distance, not 3D: the disc is meant to catch the sheet under the pads
    whatever height it has settled to.

    ``z_band`` adds a height window around the grasp point on top of that, and is
    required wherever material lies under material. At docx 1.2's pleat the
    band's flat run passes directly BENEATH the crest the gripper pinches, so a
    planar disc binds a layer the pads are nowhere near. Grabbing the wrong layer
    is a failure the task has to be able to produce -- `cloth_fold`'s config
    names it as the reason that task binds a patch rather than a single particle
    -- so the attachment has to be able to miss, not reach through the cloth.

    ``None`` (the default) keeps the planar-only behaviour a single flat sheet
    wants.
    """

    nodes = np.asarray(nodes, dtype=float)
    center = np.asarray(center, dtype=float)
    within = np.linalg.norm(nodes[:, :2] - center[:2], axis=1) <= float(radius)
    if z_band is not None:
        within &= np.abs(nodes[:, 2] - float(center[2])) <= float(z_band)
    indices = np.flatnonzero(within)
    if indices.size == 0:
        raise ValueError(
            f"attach_radius={radius} z_band={z_band} caught no particles at "
            f"({center[0]:+.4f},{center[1]:+.4f},{center[2]:+.4f}); either the "
            f"disc is smaller than the particle spacing or the grasp point is "
            f"not on the layer it names."
        )
    return indices


@dataclass
class ClothLinkAttachDragPrimitive:
    """One attach-carry-release motion, driven along waypoints from the planner.

    **Two ways this puts cloth inside the table, measured 2026-08-24 across six
    runs of `cloth_unpleat` and `cloth_unroll`. They pull against each other, so
    a fix for one has so far always fed the other.**

    A. *The pads sit below the cloth.* `HAND_TO_PAD_Z` points at the pad's
       CENTRE, and the pad body reaches about 10 mm below that, so a
       `touch_clearance` of 8 mm puts the pad's underside 2 mm INSIDE the sheet.
       It ploughs a furrow wherever the pads are -- at +/-40 mm while the fingers
       are open, and directly on the grasped patch if they are closed first.
       Clearing it needs `touch_clearance` >= the pad's half height, which is
       geometry rather than tuning: the pad underside and the bound patch hang
       from the same link, so raising one above the sheet raises the hand.

    B. *The bound patch is dragged under.* The caught particles are rigid to the
       link, so whatever the arm undershoots in z, the patch goes that far below
       the waypoint -- and the waypoint is one particle radius above the table.
       At the calibrated clearance the arm holds 1.5 mm and this barely shows; at
       20 mm it holds 7.3 mm and the deepest point moves to the band centre line
       at the end of the pull, which is the patch itself, not a finger.

    Raising `touch_clearance` removes A and feeds B, because the higher pose
    tracks worse (attach error 0.16 -> 2.24 -> 3.30 -> 4.12 mm at 8/12/14/20 mm).
    The untried lever is B own cause: the carry drives waypoints with `_glide`,
    and a ramp always lags. `_hold` is what this file already uses to remove that
    lag at the END of a carry; nothing yet removes it DURING one.
    """

    approach_z: float
    touch_clearance: float
    attach_tolerance: float
    attach_radius: float
    gripper_steps: int
    move_steps: int
    release_settle_steps: int
    max_follow_error: float
    #: Height window around the grasp point, on top of the planar disc. ``None``
    #: catches whatever is under the pads at any height, which is what a single
    #: flat sheet wants; a value is needed wherever layers stack, so the hand
    #: binds the one it is actually touching. See `attached_indices`.
    attach_z_band: float | None = None
    #: Steps spent holding the LAST waypoint's command before letting go, so the
    #: arm has time to arrive at it.
    #:
    #: `_glide` ramps the COMMAND and takes one solver step per interpolation
    #: step; the arm's own position control lags that ramp and nothing waits for
    #: it, so every glide ends with the arm still short by its lag distance.
    #: Measured 2026-08-23 on `cloth_unpleat`: a 64 mm pull commanded at 1.6 mm a
    #: step ended 31 mm short, and the shortfall was identical with the wrist
    #: unconstrained and with the whole layout moved 40 mm -- it is a tracking lag,
    #: not a reach limit. The same run showed a constant 7.5 mm z shortfall left
    #: over from the descent, for the same reason.
    #:
    #: 0 keeps the old behaviour, which is what `cloth_fold` was calibrated with.
    carry_settle_steps: int = 0
    #: Steps spent holding the descent's final pose before the attach is checked.
    #: Same reason as `carry_settle_steps`; 0 keeps `cloth_fold`'s behaviour.
    touch_settle_steps: int = 0
    #: Set when the caller has already opened the gripper -- typically because it
    #: opened it DURING the scene's settle, so the motion costs no extra steps.
    #: Opening again is harmless but adds `gripper_steps` of an arm doing nothing,
    #: which is dead time in every recording of the episode.
    skip_initial_open: bool = False
    #: Close the fingers in the air, before descending, instead of on the cloth.
    #:
    #: **Measured harmful 2026-08-24. Left in place so the result is not lost,
    #: default off, and do not turn it on without reading this.** It does what it
    #: promises -- the `close` phase moves into clear air and `attach_error` is
    #: unaffected -- and total penetration got 3x worse on `cloth_unpleat`
    #: (858 -> 2741 particle-steps) and 5.6x worse on `cloth_unroll`
    #: (1801 -> 10090), because closed fingers sit ON the bound patch and press
    #: it for the whole carry, where open ones were 40 mm away from it.
    #:
    #: The attach is a kinematic bind, so the fingers never need to grip: closing
    #: on the cloth is plausibility, not mechanism. It costs something measurable
    #: though. Measured 2026-08-24 on `cloth_unroll`: with the fingers open at
    #: `open_qpos=0.04` they straddle the grasp point by 80 mm, and BOTH the
    #: descent and the 60-step close swept them across the cloth -- `close` alone
    #: put material under the table for all 60 of its steps at two different
    #: clearances. Closing first shrinks the pads' footprint over the cloth from
    #: +/-40 mm to +/-`grasp_qpos`, and moves the close itself into clear air.
    close_before_descend: bool = False
    #: Servo the commanded height so the HELD material stays at the height it
    #: had when the link took it, instead of riding the link's own z error.
    #:
    #: A link binding is rigid and takes the bound particles OUT of collision:
    #: their position is the link pose composed with an offset frozen at bind
    #: time, so `held_z(t) = held_z(bind) + [link_z(t) - link_z(bind)]` and
    #: nothing in the solver stops that patch from crossing the table. The cloth
    #: sinks by exactly how far the link fell between the bind and now -- which
    #: is why raising `touch_clearance` made total penetration WORSE (1801 ->
    #: 7205 particle-steps at 8 -> 20 mm): it fixes the pads and enlarges this.
    #:
    #: Measured 2026-08-24 on `cloth_unroll` at 20 mm clearance: the arm ran
    #: 8.3 -> 9.2 mm below its commanded z across all eight pull segments, near
    #: constant, while `follow_mm` grew 3.2 -> 5.5. A constant offset is what a
    #: ramp's tracking lag looks like, and `_glide` never waits it out.
    #:
    #: The loop closes on the MATERIAL, not the arm, so it is indifferent to why
    #: the arm falls short -- IK budget, wrist constraint or workspace limit all
    #: correct the same way. One waypoint of lag: segment 1 is uncorrected.
    hold_bound_height: bool = False
    #: Ceiling on the servo's accumulated correction, so a saturated arm cannot
    #: wind it up without bound. Two clearances' worth of the measured shortfall.
    max_height_trim: float = 0.02
    #: Cosmetic close. ``None`` keeps the gripper open the whole time, which is
    #: the honest shape for a suction-style hold; a value must be at least half a
    #: particle or the fingers have nowhere to be and the solver diverges.
    grasp_qpos: float | None = None
    verbose: bool = False
    _phases: list[str] = field(default_factory=list, init=False)

    def run(
        self,
        controller,
        cloth,
        *,
        grasp_point,
        waypoints,
        ee_quat=None,
        particles_fn,
        on_phase=None,
    ) -> ClothAttachDragResult:
        self._phases = []
        grasp_point = np.asarray(grasp_point, dtype=float)
        if not waypoints:
            raise ValueError("a carry needs at least one waypoint.")

        if not self.skip_initial_open:
            controller.open_gripper(int(self.gripper_steps))
        self._phases.append("open")

        # Down to a hand height that leaves the pads `touch_clearance` above the
        # cloth's own top, not above the table: a settled sheet is a particle
        # radius up, and a lifted one is higher still.
        nodes = particles_fn()
        indices = attached_indices(
            nodes,
            grasp_point,
            float(self.attach_radius),
            z_band=(None if self.attach_z_band is None else float(self.attach_z_band)),
        )
        pad_z = float(nodes[indices, 2].max()) + float(self.touch_clearance)
        touch_hand = self._hand_for_pad(grasp_point, pad_z)

        approach_hand = touch_hand.copy()
        approach_hand[2] = max(float(self.approach_z), float(touch_hand[2]) + 0.06)
        # `_notify` sets the CURRENT phase for whoever is watching, so it belongs
        # BEFORE the motion it names; `_phases` records what has completed, so it
        # belongs after. Those two were both after until 2026-08-24, which meant
        # every step of the descent and the touch settle was reported as
        # "approach" -- and a penetration diagnosis then pointed at the wrong
        # 120 steps.
        self._notify(on_phase, "approach")
        self._glide(controller, approach_hand, ee_quat, int(self.move_steps))
        self._phases.append("approach")

        if self.close_before_descend and self.grasp_qpos is not None:
            self._notify(on_phase, "close")
            controller.set_gripper(float(self.grasp_qpos), steps=int(self.gripper_steps))
            self._phases.append("close")

        self._notify(on_phase, "descend")
        self._glide(controller, touch_hand, ee_quat, max(1, int(self.move_steps) // 2))
        # And let the descent finish before anything is measured against it. The
        # same lag that shortens a carry also leaves the pads BELOW the height
        # they were sent to -- measured 7.5 mm low on 2026-08-23, which is most of
        # `touch_clearance` and therefore most of the promise that the fingers
        # never reach the cloth. The attach tolerance is checked right after this,
        # so the check would otherwise be scoring the lag rather than the aim.
        self._notify(on_phase, "touch_settle")
        self._hold(controller, touch_hand, ee_quat, int(self.touch_settle_steps))
        self._phases.append("touch")

        # Did the hand actually arrive over the material? Grabbing from further
        # away than this would be a gripper with a magnet, and it would erase
        # "picked up the wrong layer" as a failure mode the benchmark needs.
        reached = self._pad_for_hand(controller.hand_pos())
        attach_error = float(np.linalg.norm(reached[:2] - grasp_point[:2]))
        if attach_error > float(self.attach_tolerance):
            self._retreat(controller, ee_quat)
            return ClothAttachDragResult(
                success=False,
                grasped=False,
                attached_particles=0,
                attach_error=attach_error,
                worst_follow_error=float("nan"),
                failure_reason=(
                    f"attach_check_failed: attach_error={attach_error:.4f} "
                    f"tolerance={float(self.attach_tolerance):.4f}"
                ),
                completed_phases=tuple(self._phases),
            )

        if self.grasp_qpos is not None and not self.close_before_descend:
            self._notify(on_phase, "close")
            controller.set_gripper(float(self.grasp_qpos), steps=int(self.gripper_steps))
            self._phases.append("close")

        # Bound BEFORE the solver runs, and where the particles already are, so
        # there is no teleport on the first step: a 13 mm jump in one 10 ms step
        # is 1.3 m/s handed to a patch whose neighbours are at rest.
        cloth.fix_particles_to_link(
            controller.ee_link.idx, particles_idx_local=[int(i) for i in indices]
        )
        bind_offset = np.asarray(
            particles_fn()[indices].mean(axis=0), dtype=float
        ) - grasp_point
        # The height the servo defends. Read from the particles, not from the
        # plan: the bind freezes whatever the material actually had.
        bind_height = float(grasp_point[2] + bind_offset[2])
        height_trim = 0.0
        self._phases.append("attach")
        self._notify(on_phase, "attach")
        if self.verbose:
            print(
                f"cloth_fold attach particles={len(indices)} "
                f"attach_error_mm={attach_error * 1e3:.2f} "
                f"clearance_mm={float(self.touch_clearance) * 1e3:.1f}",
                flush=True,
            )

        worst_follow = 0.0
        worst_pose = 0.0
        worst_tilt = 0.0
        # Where the held material sits relative to the point it was asked to
        # follow, measured at bind time. Everything after is judged against
        # `waypoint + this`, so the reading is "how far is the material from where
        # the plan wants it" and nothing else. Subtracting an offset measured
        # against the PAD instead counted the clearance twice and put a constant
        # 8 mm into every reading (2026-08-20).
        for waypoint in waypoints:
            target = np.asarray(waypoint.position, dtype=float)
            steps = max(1, int(waypoint.steps or 1))
            # The pads stay `touch_clearance` ABOVE the material for the whole
            # arc, not just on the way down. Sending them to the waypoint's own
            # height instead put the fingers on the sheet the moment the carry
            # started, and the clearance -- the one guarantee that the fingers
            # never contact the cloth -- was only true during the approach.
            #
            # The bound particles keep the offset they had when the link took
            # them, which is exactly that clearance, so commanding the pad this
            # much higher puts the material on the waypoint.
            commanded = self._hand_for_pad(
                target,
                float(target[2]) + float(self.touch_clearance) + height_trim,
            )
            self._glide(controller, commanded, ee_quat, steps)
            # How far the held material is from where it was asked to be. With a
            # link binding this stays near zero; a growing value means the arm
            # could not reach and the cloth is being stretched to cover it.
            held = np.asarray(particles_fn()[indices].mean(axis=0), dtype=float)
            follow = float(np.linalg.norm(held - (target + bind_offset)))
            worst_follow = max(worst_follow, follow)
            # Did the ARM get where it was told? `continuous_ik` runs one seeded
            # solve of 50 iterations and returns whatever it reached, reporting
            # nothing when that is not the commanded pose. A fold that tracks
            # badly looks identical in the material readings to a fold whose
            # trajectory was wrong, so the two are separated here: `pose` is the
            # arm's own error, `follow` is the cloth's.
            pose = float(np.linalg.norm(np.asarray(controller.hand_pos(), dtype=float) - commanded))
            tilt = _quat_angle(controller.hand_quat(), ee_quat) if ee_quat is not None else 0.0
            worst_pose = max(worst_pose, pose)
            worst_tilt = max(worst_tilt, tilt)
            if self.hold_bound_height:
                height_trim = float(
                    np.clip(
                        height_trim + (bind_height - float(held[2])),
                        0.0,
                        float(self.max_height_trim),
                    )
                )
            self._notify(on_phase, waypoint.label)
            if self.verbose:
                # The commanded and achieved HAND poses, per axis, not just the
                # scalar gap. `continuous_ik` reports nothing when it falls
                # short, so a run that cannot reach and a run whose trajectory
                # was wrong look identical in the material readings -- and the
                # scalar `arm_pos_err_mm` still does not say WHICH way the arm
                # fell short. Measured 2026-08-23: a pull commanded 64 mm along y
                # delivered 33 mm with the orientation held to 0.8 degrees, which
                # is the signature of the solver trading position away to keep
                # the wrist angle. Per-axis is what tells that apart from simply
                # being outside the workspace.
                reached = np.asarray(controller.hand_pos(), dtype=float)
                gap = reached - commanded
                print(
                    f"cloth_fold {waypoint.label} "
                    f"target=({target[0]:+.3f},{target[1]:+.3f},{target[2]:+.3f}) "
                    f"follow_mm={follow * 1e3:.1f} "
                    f"arm_pos_err_mm={pose * 1e3:.1f} "
                    f"arm_gap_mm=({gap[0] * 1e3:+.1f},{gap[1] * 1e3:+.1f},{gap[2] * 1e3:+.1f}) "
                    f"held_dz_mm={(float(held[2]) - bind_height) * 1e3:+.1f} "
                    f"trim_mm={height_trim * 1e3:.1f} "
                    f"hand=({reached[0]:+.3f},{reached[1]:+.3f},{reached[2]:+.3f}) "
                    f"want=({commanded[0]:+.3f},{commanded[1]:+.3f},{commanded[2]:+.3f}) "
                    f"arm_tilt_deg={np.degrees(tilt):.1f}",
                    flush=True,
                )
        # Hold the last command until the arm actually gets there.
        if int(self.carry_settle_steps) > 0:
            final = np.asarray(waypoints[-1].position, dtype=float)
            commanded = self._hand_for_pad(
                final, float(final[2]) + float(self.touch_clearance)
            )
            self._hold(controller, commanded, ee_quat, int(self.carry_settle_steps))
            held = np.asarray(particles_fn()[indices].mean(axis=0), dtype=float)
            follow = float(np.linalg.norm(held - (final + bind_offset)))
            pose = float(
                np.linalg.norm(
                    np.asarray(controller.hand_pos(), dtype=float) - commanded
                )
            )
            # The worst readings are updated, not replaced: the point of the hold
            # is that the END of the carry is where the plan said, and a lag that
            # was only ever transient is not a defect worth reporting as one.
            worst_follow = follow
            worst_pose = pose
            if self.verbose:
                print(
                    f"cloth_fold carry_settled steps={int(self.carry_settle_steps)} "
                    f"follow_mm={follow * 1e3:.1f} arm_pos_err_mm={pose * 1e3:.1f}",
                    flush=True,
                )
        self._phases.append("carried")

        cloth.release_particle(particles_idx_local=[int(i) for i in indices])
        self._phases.append("release")
        self._notify(on_phase, "release")
        controller.step(max(0, int(self.release_settle_steps)))
        self._phases.append("settled")

        self._notify(on_phase, "retreat")
        self._retreat(controller, ee_quat)
        self._phases.append("retreat")
        self._notify(on_phase, "done")
        return ClothAttachDragResult(
            success=worst_follow <= float(self.max_follow_error),
            grasped=True,
            attached_particles=int(len(indices)),
            attach_error=attach_error,
            worst_follow_error=float(worst_follow),
            worst_pose_error=float(worst_pose),
            worst_tilt_rad=float(worst_tilt),
            failure_reason=(
                None
                if worst_follow <= float(self.max_follow_error)
                else f"follow_error={worst_follow:.4f}>{float(self.max_follow_error):.4f}"
            ),
            completed_phases=tuple(self._phases),
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _hand_for_pad(point, pad_z: float) -> np.ndarray:
        point = np.asarray(point, dtype=float)
        return np.array([point[0], point[1], float(pad_z) + HAND_TO_PAD_Z])

    @staticmethod
    def _pad_for_hand(hand) -> np.ndarray:
        hand = np.asarray(hand, dtype=float)
        return np.array([hand[0], hand[1], hand[2] - HAND_TO_PAD_Z])

    def _hold(self, controller, target, quat, steps: int) -> None:
        """Command one FIXED pose every step, so the arm converges onto it.

        Different from `_glide` in the way that matters here: a glide ramps the
        setpoint and stops the moment the ramp ends, which leaves the arm short
        by whatever it was lagging at that instant. A constant setpoint lets the
        error decay instead of chasing a moving one.

        Measured 2026-08-23 on `cloth_unpleat`: settling the end of a pull with a
        second glide took the arm's error from 31 mm to 9.3 mm and stalled there,
        because the second ramp had its own lag. The residual is what a hold
        removes.
        """

        target = np.asarray(target, dtype=float)
        commanded_qpos = None
        for _ in range(max(0, int(steps))):
            commanded_qpos = controller.move_ee_to(
                target, quat=quat, steps=1, continuous_ik=True
            )
        if not self.verbose or commanded_qpos is None:
            return
        # Where the residual actually lives. `move_ee_to` does two things -- solve
        # IK for a joint vector, then ask a position controller to reach it -- and
        # a steady-state pose error can come from either. Measured 2026-08-24, the
        # hand sat 4.7 mm below a target 4 mm above the one it had been holding
        # to 0.9 mm, which is the arm barely rising at all; whether that is the
        # solver not reaching the pose or the controller not reaching the joints
        # changes the fix completely, and only this comparison separates them.
        actual_qpos = np.asarray(
            _as_numpy_qpos(controller.robot.get_qpos()), dtype=float
        ).ravel()[: len(commanded_qpos)]
        joint_gap = np.abs(np.asarray(commanded_qpos, dtype=float) - actual_qpos)
        hand = np.asarray(controller.hand_pos(), dtype=float)
        print(
            f"cloth_fold hold_residual steps={int(steps)} "
            f"hand_gap_mm=({(hand[0] - target[0]) * 1e3:+.1f},"
            f"{(hand[1] - target[1]) * 1e3:+.1f},{(hand[2] - target[2]) * 1e3:+.1f}) "
            f"joint_gap_max_deg={np.degrees(joint_gap.max()):.3f} "
            f"joint_gap_sum_deg={np.degrees(joint_gap.sum()):.3f}",
            flush=True,
        )

    @staticmethod
    def _glide(controller, target, quat, steps: int) -> None:
        """Straight-line move, one solver step per interpolation step.

        `continuous_ik` so the arm's joints carry over between steps instead of
        each one being solved from scratch, which is what keeps a swept arc
        smooth rather than snapping between elbow configurations.
        """

        start = np.asarray(controller.hand_pos(), dtype=float)
        target = np.asarray(target, dtype=float)
        steps = max(1, int(steps))
        for index in range(1, steps + 1):
            alpha = index / steps
            controller.move_ee_to(
                (1.0 - alpha) * start + alpha * target,
                quat=quat,
                steps=1,
                continuous_ik=True,
            )

    def _retreat(self, controller, quat) -> None:
        hand = np.asarray(controller.hand_pos(), dtype=float).copy()
        hand[2] = max(float(self.approach_z), float(hand[2]) + 0.08)
        self._glide(controller, hand, quat, max(1, int(self.move_steps) // 2))

    @staticmethod
    def _notify(on_phase, label: str) -> None:
        if on_phase is not None:
            on_phase(str(label))
