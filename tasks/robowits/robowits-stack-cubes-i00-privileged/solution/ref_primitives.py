"""Task-level skills used by the reference solutions (solution/ only; never in the agent image). The agent's tooling
(rcb_robowits.Session.primitives) is deliberately thin: IK moves, joint moves, gripper, hold. Skills like these are what
an agent builds for itself. An oracle loads them with

    import sys; sys.path.insert(0, "/solution")
    from ref_primitives import extend
    globals().update(extend(session))
"""
import math

import numpy as np

from rcb_robowits import GRIPPER_OPEN, PrimitiveError, quat_to_mat, top_down_quat, wrap_angle


def extend(s) -> dict:
    """The session's thin primitives plus object_yaws / nearest_yaw / grasp / place."""
    p = s.primitives()
    move_ee, open_gripper, close_gripper = p["move_ee"], p["open_gripper"], p["close_gripper"]

    def object_yaws(name: str):
        """Yaw angles (rad) of the horizontal face normals of a box-like object (4 values, 90 deg apart), from its quaternion."""
        _, q = s.object_pose(name); R = quat_to_mat(q); out = []
        for c in range(3):
            ax = R[:, c]
            if abs(ax[2]) < 0.5:
                a = math.atan2(ax[1], ax[0]); out += [wrap_angle(a), wrap_angle(a + math.pi)]
        return sorted(out)

    def nearest_yaw(cands, preferred: float = math.pi / 2):
        """The candidate yaw closest (mod 2pi) to `preferred` (default pi/2: fingers closing along world y, as at reset)."""
        return min(cands, key=lambda a: abs(wrap_angle(a - preferred)))

    def grasp(arm: str, name: str, *, hover: float = 0.10, depth: float = 0.0, closing_yaw: float | None = None,
              tilt: float = 0.0, preferred_yaw: float = math.pi / 2, lift: float = 0.10, close_steps: int = 20):
        """Top-down grasp of object `name` with `arm`: open, move `hover` m above the object centre, descend to the object
        centre (+`depth` m), close, lift `lift` m. Fingers close along `closing_yaw` (default: the object's face normal
        nearest `preferred_yaw`); `tilt` leans the approach away from the robot. Returns the held object's offset from the
        tip in the tip frame (used by place()). Raises PrimitiveError if the object did not come up with the gripper."""
        c, _ = s.object_pose(name)
        yaw = closing_yaw if closing_yaw is not None else nearest_yaw(object_yaws(name), preferred_yaw)
        quat = top_down_quat(yaw, tilt)
        if s.gripper_width(arm) < GRIPPER_OPEN - 0.015:
            open_gripper(arm, 10)
        move_ee(arm, c + np.array([0, 0, hover]), quat)
        move_ee(arm, c + np.array([0, 0, depth]), quat, linear=3, max_dq=0.03, settle=3)
        close_gripper(arm, close_steps)
        move_ee(arm, c + np.array([0, 0, lift]), quat, linear=2, max_dq=0.03, settle=5)
        c2, _ = s.object_pose(name)
        if c2[2] - c[2] < 0.5 * lift:
            raise PrimitiveError(f"grasp of {name!r} failed (object rose {c2[2] - c[2]:.3f} m)")
        tp, tq = s.ee_pose(arm)
        return quat_to_mat(tq).T @ (c2 - tp)

    def place(arm: str, target_center, held_offset_tip, *, closing_yaw: float | None = None, tilt: float = 0.0,
              hover: float = 0.08, release_gap: float = 0.004, open_steps: int = 15, retreat: float = 0.10):
        """Put the held object (offset from the tip in the tip frame as returned by grasp()) with its centre at world
        `target_center`: move above it, descend so the object stops `release_gap` m above the target height, open, retreat
        `retreat` m up. `closing_yaw` re-orients the object (default: keep the current tip yaw). Returns the tip pose error."""
        tp, tq = s.ee_pose(arm)
        if closing_yaw is None:
            R = quat_to_mat(tq); closing_yaw = math.atan2(R[1, 0], R[0, 0])
        quat = top_down_quat(closing_yaw, tilt)
        off_world = quat_to_mat(quat) @ np.asarray(held_offset_tip, dtype=np.float64)
        tgt = np.asarray(target_center, dtype=np.float64)
        tip_goal = tgt + np.array([0, 0, release_gap]) - off_world
        move_ee(arm, tip_goal + np.array([0, 0, hover]), quat)
        err = move_ee(arm, tip_goal, quat, linear=3, max_dq=0.03, settle=5)
        open_gripper(arm, open_steps)
        move_ee(arm, tip_goal + np.array([0, 0, retreat]), quat, linear=2, settle=5)
        return err

    return {**p, "object_yaws": object_yaws, "nearest_yaw": nearest_yaw, "grasp": grasp, "place": place}
