"""Task-level skills used by the reference solutions (solution/ only; never in the agent image). The agent's tooling
(rcb_robolab.Session.primitives) is deliberately thin: move_ee / move_joints / gripper / hold / ik_step. Skills like these
are what an agent builds for itself. An oracle loads them with

    import sys; sys.path.insert(0, "/solution")
    from ref_primitives import extend
    globals().update(extend(session))
"""
import math

import numpy as np

from rcb_robolab import PrimitiveError, _log, quat_to_mat, wrap_angle


def extend(s) -> dict:
    """The session's thin primitives plus object_yaws / nearest_yaw / grasp_point / grasp / place / settle."""
    p = s.primitives()
    hold, open_gripper, close_gripper, move_ee = p["hold"], p["open_gripper"], p["close_gripper"], p["move_ee"]
    top_down_quat, yaw_for_closing_dir = p["top_down_quat"], p["yaw_for_closing_dir"]

    def object_yaws(name: str):
        """Yaw angles (rad) of the horizontal axes of an object's frame (4 values, 90 deg apart)."""
        _, q = s.object_pose(name); R = quat_to_mat(q); out = []
        for c in range(3):
            ax = R[:, c]
            if abs(ax[2]) < 0.5:
                a = math.atan2(ax[1], ax[0]); out += [wrap_angle(a), wrap_angle(a + math.pi)]
        return sorted(out)

    def nearest_yaw(cands, preferred: float = 0.0):
        """The candidate yaw closest (mod 2pi) to `preferred`."""
        return min(cands, key=lambda a: abs(wrap_angle(a - preferred)))

    def grasp_point(name: str, frac: float = 0.5, slab: float = 0.015):
        """Grasp point on an elongated object's body from its surface points: principal horizontal axis, the slab of
        points at fraction `frac` (0..1) of the length, centroid of that slab. Returns (point_xyz, closing_yaw) where the
        fingers close across the local body direction. (A banana's pose/AABB centre lies in its concavity.)"""
        pts = s.object_points(name)
        xy = pts[:, :2]; mu = xy.mean(axis=0); _, _, vt = np.linalg.svd(xy - mu, full_matrices=False)
        u = vt[0]; t = (xy - mu) @ u; lo, hi = t.min(), t.max(); t0 = lo + frac * (hi - lo)

        def slab_centroid(tc):
            m = np.abs(t - tc) < slab
            if m.sum() < 5:
                m = np.abs(t - tc) < 3 * slab
            return pts[m].mean(axis=0) if m.sum() >= 5 else None
        centre = slab_centroid(t0)
        if centre is None:
            centre = pts.mean(axis=0)
        ca, cb = slab_centroid(t0 - 2 * slab), slab_centroid(t0 + 2 * slab)   # neighbouring slabs give the local body direction
        tangent = (cb - ca)[:2] if (ca is not None and cb is not None and np.linalg.norm((cb - ca)[:2]) > 1e-4) else u
        tangent = tangent / np.linalg.norm(tangent)
        perp = np.array([-tangent[1], tangent[0]])
        return centre, yaw_for_closing_dir(perp)

    def grasp(name: str, *, hover: float = 0.12, depth: float = 0.0, yaw: float | None = None, lift: float = 0.12,
              close_steps: int = 30, point=None, settle_steps: int = 10, lift_speed: float = 0.06):
        """Top-down grasp of object `name`: open, move `hover` m above the grasp point (default: the object's pose;
        `point` = explicit env-local xyz, e.g. from grasp_point()), descend to the point's height + `depth`, close, lift
        `lift` m. `yaw` (rad, about world z) sets the finger-closing direction relative to the reset pose (default: close
        across the object's longer horizontal AABB axis). Returns the held object's offset from the fingertip frame (in
        that frame), for place(). Raises PrimitiveError if the object did not come up with the gripper."""
        if s.episode_done:
            return None
        c, _ = s.object_pose(name)
        c0 = c.copy()                        # the object's pose before the grasp (the lift check uses it)
        if point is not None:
            c = np.asarray(point, dtype=np.float64)
        if yaw is None:
            b = s.object_bounds(name); ext = b[1] - b[0]
            yaw_ = yaw_for_closing_dir([1.0, 0.0] if ext[1] >= ext[0] else [0.0, 1.0])
        else:
            yaw_ = yaw
        quat = top_down_quat(yaw_)
        if s.gripper_angle() > 0.1:
            open_gripper(10)
        move_ee(c + np.array([0, 0, hover]), quat, max_steps=150)
        try:
            move_ee(c + np.array([0, 0, depth]), quat, speed=0.12, settle=3, max_steps=80)
        except PrimitiveError as exc:
            _log(f"grasp {name!r}: descent stopped early ({exc}); closing anyway")
        tp0, _ = s.ee_pose()
        fp_open = s._finger_positions()
        close_gripper(close_steps)
        hold(settle_steps)                       # let the pinch settle before moving
        g_closed = s.gripper_angle(); c1, _ = s.object_pose(name)
        fp = s._finger_positions()
        try:
            touching = s.world.get_objects_in_contact_with(name, env_id=0)
        except Exception as exc:  # noqa: BLE001
            touching = f"n/a ({repr(exc)[:60]})"
        _log(f"grasp {name!r}: objects in contact with it after closing: {touching}")
        if fp is not None and fp_open is not None:
            mid = (fp[0] + fp[1]) / 2
            _log(f"grasp {name!r}: finger CoM midpoint - tool frame = {np.round(mid - tp0, 4).tolist()} (open: {np.round((fp_open[0] + fp_open[1]) / 2 - tp0, 4).tolist()}), "
                 f"CoM separation {np.linalg.norm(fp[1] - fp[0]):.3f} m (open {np.linalg.norm(fp_open[1] - fp_open[0]):.3f}); grasp point - object pose = {np.round(c - c0, 4).tolist()}")
        if g_closed < 0.05:
            _log(f"grasp {name!r}: WARNING the gripper did not close (finger angle {g_closed:.3f} rad): fingers jammed against the table?")
        move_ee(c + np.array([0, 0, lift]), quat, speed=lift_speed, max_dq=0.03, settle=5)
        c2, _ = s.object_pose(name)
        _log(f"grasp {name!r}: tip reached z={tp0[2]:.3f} (target {c[2] + depth:.3f}), finger angle after close {g_closed:.2f} rad, "
             f"object z {c0[2]:.3f} -> {c1[2]:.3f} (closed) -> {c2[2]:.3f} (lifted), xy drift {np.linalg.norm(c2[:2] - c0[:2]) * 1000:.0f} mm")
        if s.episode_done:
            return None
        if c2[2] - c0[2] < 0.5 * lift:
            raise PrimitiveError(f"grasp of {name!r} failed (object rose {c2[2] - c[2]:.3f} m)")
        tp, tq = s.ee_pose()
        return quat_to_mat(tq).T @ (c2 - tp)

    def place(target_center, held_offset_tip, *, yaw: float | None = None, hover: float = 0.10, release_gap: float = 0.01,
              open_steps: int = 15, retreat: float = 0.12):
        """Put the held object (offset from the fingertip frame as returned by grasp()) with its centre at env-local
        `target_center`: move above it, descend so the object stops `release_gap` m above the target height, open, retreat
        `retreat` m up. `yaw` re-orients the gripper (default: keep the current yaw). Returns the fingertip pose error (m)."""
        if s.episode_done:
            return None
        tp, tq = s.ee_pose()
        quat = top_down_quat(yaw) if yaw is not None else tq
        off_world = quat_to_mat(quat) @ np.asarray(held_offset_tip, dtype=np.float64)
        tgt = np.asarray(target_center, dtype=np.float64)
        tip_goal = tgt + np.array([0, 0, release_gap]) - off_world
        move_ee(tip_goal + np.array([0, 0, hover]), quat)
        err = move_ee(tip_goal, quat, speed=0.12, settle=5)
        open_gripper(open_steps)
        move_ee(tip_goal + np.array([0, 0, retreat]), quat, speed=0.15, settle=5)
        return err

    def settle(steps: int = 15):
        """Alias of hold()."""
        hold(steps)

    return {**p, "object_yaws": object_yaws, "nearest_yaw": nearest_yaw, "grasp_point": grasp_point, "grasp": grasp,
            "place": place, "settle": settle}
