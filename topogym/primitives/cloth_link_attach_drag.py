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


def attached_indices(nodes: np.ndarray, center, radius: float) -> np.ndarray:
    """Particles within ``radius`` of the grasp point, in the plane.

    Planar distance, not 3D: the disc is meant to catch the sheet under the pads
    whatever height it has settled to.
    """

    offsets = np.asarray(nodes, dtype=float)[:, :2] - np.asarray(center, dtype=float)[:2]
    indices = np.flatnonzero(np.linalg.norm(offsets, axis=1) <= float(radius))
    if indices.size == 0:
        raise ValueError(
            f"attach_radius={radius} caught no particles; the cloth's particle "
            f"spacing is larger than the disc."
        )
    return indices


@dataclass
class ClothLinkAttachDragPrimitive:
    """One lift-move-place fold, driven along waypoints from the planner."""

    approach_z: float
    touch_clearance: float
    attach_tolerance: float
    attach_radius: float
    gripper_steps: int
    move_steps: int
    release_settle_steps: int
    max_follow_error: float
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
            raise ValueError("a fold needs at least one waypoint.")

        controller.open_gripper(int(self.gripper_steps))
        self._phases.append("open")

        # Down to a hand height that leaves the pads `touch_clearance` above the
        # cloth's own top, not above the table: a settled sheet is a particle
        # radius up, and a lifted one is higher still.
        nodes = particles_fn()
        indices = attached_indices(nodes, grasp_point, float(self.attach_radius))
        pad_z = float(nodes[indices, 2].max()) + float(self.touch_clearance)
        touch_hand = self._hand_for_pad(grasp_point, pad_z)

        approach_hand = touch_hand.copy()
        approach_hand[2] = max(float(self.approach_z), float(touch_hand[2]) + 0.06)
        self._glide(controller, approach_hand, ee_quat, int(self.move_steps))
        self._phases.append("approach")
        self._notify(on_phase, "approach")

        self._glide(controller, touch_hand, ee_quat, max(1, int(self.move_steps) // 2))
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

        if self.grasp_qpos is not None:
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
            self._glide(
                controller,
                self._hand_for_pad(target, float(target[2]) + float(self.touch_clearance)),
                ee_quat,
                steps,
            )
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
            commanded = self._hand_for_pad(
                target, float(target[2]) + float(self.touch_clearance)
            )
            pose = float(np.linalg.norm(np.asarray(controller.hand_pos(), dtype=float) - commanded))
            tilt = _quat_angle(controller.hand_quat(), ee_quat) if ee_quat is not None else 0.0
            worst_pose = max(worst_pose, pose)
            worst_tilt = max(worst_tilt, tilt)
            self._notify(on_phase, waypoint.label)
            if self.verbose:
                print(
                    f"cloth_fold {waypoint.label} "
                    f"target=({target[0]:+.3f},{target[1]:+.3f},{target[2]:+.3f}) "
                    f"follow_mm={follow * 1e3:.1f} "
                    f"arm_pos_err_mm={pose * 1e3:.1f} "
                    f"arm_tilt_deg={np.degrees(tilt):.1f}",
                    flush=True,
                )
        self._phases.append("carried")

        cloth.release_particle(particles_idx_local=[int(i) for i in indices])
        self._phases.append("release")
        self._notify(on_phase, "release")
        controller.step(max(0, int(self.release_settle_steps)))
        self._phases.append("settled")

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
