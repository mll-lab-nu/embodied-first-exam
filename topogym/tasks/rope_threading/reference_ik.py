"""Task-space reference IK with an explicit, small tool-roll relaxation.

The ALOHA wrist_rotate joint rotates about gripper_link's local X axis without
moving its origin. The reference approaches its lower stop to within 0.0034
degrees. Preserve the hand position and tool axis, but smoothly relax tool roll
near that stop. This changes the requested pose; it is not exact-pose IK for
the unmodified reference, and does not certify dynamic tracking or rope motion.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.knot_untying.control import BoundedAlohaIK


JOINT_MARGIN_RAD = .02
ROLL_TRANSITION_RAD = .005


def free_hand_clearance(time, phase, stages, side):
    """C2-continuous 3 mm +Z detours around R2, only while left is unheld.

    Dense screening of this public reference found gripper-base grazing during
    phase 40 (approach node 75) and 49 (withdraw after release). Offsets vanish
    before either segment boundary, preserving the original acquisition poses.
    """
    offsets = {40: 5.7705, 49: 7.2355}
    if side != "left" or phase not in offsets:
        return np.zeros(3)
    center = float(stages[phase]["start_s"])+offsets[phase]
    u = (float(time)-center)/1.75
    return np.array([0., 0., .003*max(0., 1.-u*u)**3])


def relaxed_roll(angle, limits, margin=JOINT_MARGIN_RAD, width=ROLL_TRANSITION_RAD):
    """Smooth projection into the inset interval, with no wrap across +/- pi."""
    lower, upper = np.asarray(limits, dtype=float)
    if not (np.isfinite([angle, lower, upper, margin, width]).all()
            and width > 0 and margin > 1e-5 and lower+margin < upper-margin):
        raise ValueError("Invalid wrist-roll limits, margin or transition width")
    lower, upper = lower+margin, upper-margin
    return float(lower+width*np.logaddexp(0., (angle-lower)/width)
                 -width*np.logaddexp(0., (angle-upper)/width))


class MarginAwareThreadingIK(BoundedAlohaIK):
    def __init__(self, task, controller, *, margin=JOINT_MARGIN_RAD):
        super().__init__(task, controller)
        self.joint_limits = self.limits.copy()
        if not np.isfinite(margin) or margin <= 1e-5 or np.any(np.diff(self.limits, axis=1) <= 2*margin):
            raise ValueError("Invalid joint safety margin")
        self.margin = float(margin)
        # BoundedAlohaIK adds another 1e-5 inset internally.
        self.limits = self.joint_limits+np.array([margin-1e-5, -margin+1e-5])
        self.max_reference_roll_relaxation = 0.
        for side in controller.arms:
            joint = self.model.joint(f"{side}/wrist_rotate")
            if (not np.allclose(joint.axis, [1, 0, 0])
                    or int(joint.bodyid[0]) != self.model.body(f"{side}/gripper_link").id
                    or not np.allclose(joint.pos, 0.)):
                raise ValueError("Tool-roll relaxation requires a gripper-origin X-axis wrist")

    def reference_target(self, quat, reference_q):
        roll = relaxed_roll(float(reference_q[-1]), self.joint_limits[-1], self.margin)
        delta = roll-float(reference_q[-1])
        orientation = (Rotation.from_quat(quat, scalar_first=True)
                       *Rotation.from_rotvec([delta, 0., 0.]))
        return orientation.as_quat(scalar_first=True), delta

    def solve_reference(self, side, position, quat, reference_q):
        target_quat, delta = self.reference_target(quat, reference_q)
        seed = np.asarray(reference_q).copy()
        seed[-1] += delta
        result = self.solve(side, position, target_quat, seed=seed)
        self.max_reference_roll_relaxation = max(self.max_reference_roll_relaxation, abs(delta))
        return result
