"""Measured-state local paths for R2 handoff; CPU FK/IK and fixture screening.

Every input point is in the robot model frame. These paths command the robot,
never the FEM state. Runtime observations replace the offline tail prediction.
"""
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .feedback_ik_plan import GRASP_OFFSET, carry_tip, grasp_pose, pivot_pose, smoothstep
from .ik_plan import offline_controller
from .reference_ik import MarginAwareThreadingIK
from .reference_preflight import model_with_fixtures


ARM = np.array([0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13])


@dataclass
class LocalPath:
    time: np.ndarray
    qpos: np.ndarray
    stage: np.ndarray
    audit: dict | None = None

    def sample(self, time):
        return np.array([np.interp(time, self.time, self.qpos[:, j]) for j in range(16)])


class PathBuilder:
    def __init__(self, ik, qpos, dt=.04):
        self.ik, self.q, self.dt = ik, np.asarray(qpos).copy(), dt
        self.times, self.rows, self.names = [0.], [self.q.copy()], ["initial"]

    def add(self, name, duration, command):
        start = self.times[-1]
        for time in np.linspace(0., duration, int(np.ceil(duration/self.dt))+1)[1:]:
            command(float(smoothstep(time/duration)))
            self.times.append(start+float(time))
            self.rows.append(self.q.copy())
            self.names.append(name)
        return self

    def joints(self, name, duration, indices, target):
        start, target = self.q[indices].copy(), np.asarray(target)
        return self.add(name, duration, lambda u: self.q.__setitem__(indices, start*(1-u)+target*u))

    def pose(self, side, position, orientation):
        indices = slice(0, 6) if side == "left" else slice(8, 14)
        self.q[indices] = self.ik.solve(side, position, orientation.as_quat(scalar_first=True), seed=self.q[indices])

    def finish(self):
        return LocalPath(np.asarray(self.times), np.asarray(self.rows), np.asarray(self.names))


class MeasuredHandoffPlanner:
    def __init__(self, cfg, qpos):
        self.ik = MarginAwareThreadingIK(None, offline_controller(cfg, np.asarray(qpos)))
        self.model = model_with_fixtures(cfg)
        self.model.geom_margin[:] = .003
        self.data = mujoco.MjData(self.model)

    def gap(self, q):
        self.data.qpos[:] = q
        mujoco.mj_forward(self.model, self.data)
        if not len(self.data.contact):
            return .006, []
        contact = min(self.data.contact, key=lambda c: c.dist)
        return float(contact.dist), [self.model.geom(i).name or self.model.body(self.model.geom_bodyid[i]).name
                                     for i in (contact.geom1, contact.geom2)]

    def screen(self, path, *, minimum_gap=.00025):
        times = np.unique(np.r_[path.time, np.arange(0., path.time[-1], .005), path.time[-1]])
        minimum, where, pair = float("inf"), 0., []
        for time in times:
            gap, names = self.gap(path.sample(time))
            if gap < minimum:
                minimum, where, pair = gap, float(time), names
        arms = path.qpos[:, ARM].reshape(-1, 2, 6)
        limits = self.ik.joint_limits
        margin = float(np.minimum(arms-limits[:, 0], limits[:, 1]-arms).min())
        speed = float((np.abs(np.diff(arms, axis=0))/np.diff(path.time)[:, None, None]).max())
        path.audit = dict(samples=len(times), minimum_gap_m=minimum, gap_time_s=where, gap_pair=pair,
            minimum_joint_margin_rad=margin, maximum_joint_speed_rad_s=speed,
            required_gap_m=minimum_gap, physical_execution_verified=False,
            scope="5 ms sampled robot/fixture proxy collision screen; native physical audits remain mandatory")
        path.audit["passed"] = bool(minimum >= minimum_gap and margin >= .02-1e-9 and speed <= .8)
        if not path.audit["passed"]:
            raise ValueError(f"Local path screen rejected: {path.audit}")
        return path

    def pivot(self, q, anchor, degrees=6.):
        b = PathBuilder(self.ik, q)
        b.joints("right_narrow_open", .5, slice(14, 16), [.018, .018])
        p, r = self.ik.pose("left", q[:6])
        b.add("left_pivot", 3., lambda u: b.pose("left", *pivot_pose(p, r, anchor, np.deg2rad(degrees)*u)))
        return self.screen(b.finish())

    def approach(self, q, tip, tangent, *, transit=True, preferred_angle=28.):
        """Reselect orientation using the observed tail; screen transit AND approach.

        Prefer the first fully clear family member, with a deterministic search
        fallback. The runtime observes again after transit and before closing.
        """
        rejected = []
        angles = list(dict.fromkeys([preferred_angle, 28., 24., 32., 20., 36., 16., 40., 8., 48., 0., 56.]))
        for angle in angles:
            for distance in ([.06, .045] if transit else [0.]):
                try:
                    p, r = grasp_pose(tip, tangent, angle)
                    goal = self.ik.solve("right", p, r.as_quat(scalar_first=True), seed=[-.7, .2, -.4, -2.3, -1.4, -1.])
                    for finger in [.018, .014, .010]:
                        end = q.copy()
                        end[8:14], end[14:16] = goal, finger
                        if self.gap(end)[0] < .00025:
                            raise ValueError("Grasp aperture sweep is too close to a fixture/other hand")
                    b = PathBuilder(self.ik, q)
                    if transit:
                        pre = self.ik.solve("right", p-distance*r.apply([1., 0., 0.]),
                                            r.as_quat(scalar_first=True), seed=goal)
                        b.joints("right_transit", 14., slice(8, 14), pre)
                        transit_path = b.finish()
                    start_p, start_r = self.ik.pose("right", b.q[8:14])
                    rotations = Slerp([0., 1.], Rotation.concatenate([start_r, r]))
                    b.add("right_approach", 4., lambda u: b.pose("right", start_p*(1-u)+p*u, rotations(u)))
                    # Include the whole closing sweep in screening, but leave
                    # its execution to the bilateral-contact gate.
                    b.joints("screen_closure_only", 2., slice(14, 16), [.010, .010])
                    screened = self.screen(b.finish())
                    path = transit_path if transit else LocalPath(
                        screened.time[screened.time <= 4.+1e-8], screened.qpos[screened.time <= 4.+1e-8],
                        screened.stage[screened.time <= 4.+1e-8])
                    path.audit = dict(screened.audit, screen_includes_future_approach_and_closure=True,
                        selected_azimuth_deg=angle, pregrasp_distance_m=distance,
                        measured_tip_model_m=np.asarray(tip).tolist(), measured_tangent_model=np.asarray(tangent).tolist(),
                        rejected_candidates=rejected)
                    return path, angle
                except ValueError as exc:
                    rejected.append(dict(angle_deg=angle, distance_m=distance, reason=str(exc)))
        raise ValueError(f"No screened approach to measured tail: {rejected}")

    def unpinch(self, q, increment=.0003, *, side="left"):
        fingers = slice(6, 8) if side == "left" else slice(14, 16)
        return self.screen(PathBuilder(self.ik, q).joints(
            side+"_unpinch", .5, fingers, q[fingers]+increment).finish())

    def withdraw(self, q, *, side="left", distance=.10):
        b = PathBuilder(self.ik, q)
        indices = slice(0, 6) if side == "left" else slice(8, 14)
        p, r = self.ik.pose(side, q[indices])
        b.add(side+"_withdraw", 4., lambda u: b.pose(side, p-distance*u*r.apply([1., 0., 0.]), r))
        return self.screen(b.finish())

    def join_arm(self, q, join, side, duration=5., *, match_fingers=False):
        indices = slice(0, 6) if side == "left" else slice(8, 14)
        b = PathBuilder(self.ik, q)
        if match_fingers:
            fingers = slice(6, 8) if side == "left" else slice(14, 16)
            b.joints(side+"_open_outside_ring", .5, fingers, join[fingers])
        return self.screen(b.joints(side+"_join_reference", duration, indices, join[indices]).finish())

    def return_left(self, q, join):
        b = PathBuilder(self.ik, q)
        b.joints("left_open_outside_ring", .5, slice(6, 8), join[6:8])
        b.joints("left_return", 3., slice(0, 6), join[:6])
        return self.screen(b.finish())

    def carry(self, q, measured_tip, join):
        start_p, start_r = self.ik.pose("right", q[8:14])
        local = start_r.inv().apply(measured_tip-start_p)
        end_p, end_r = self.ik.pose("right", join[8:14])
        end_tip = end_p+end_r.apply(local)
        rotations = Slerp([0., 1.], Rotation.concatenate([start_r, end_r]))
        rejected = []
        for detour in ([.04, -.04, 0.], [.045, -.05, 0.], [.035, -.045, 0.], [.04, -.06, 0.]):
            try:
                b = PathBuilder(self.ik, q)
                b.add("right_carry", 5., lambda u: b.pose("right",
                    carry_tip(measured_tip, end_tip, u, detour)-rotations(u).apply(local), rotations(u)))
                path = self.screen(b.finish())
                difference = float(np.abs(path.qpos[-1, ARM]-join[ARM]).max())
                if difference > 1e-6:
                    raise ValueError(f"Reference joint branch mismatch: {difference} rad")
                path.audit.update(measured_tip_local_m=local.tolist(), detour_m=detour,
                                  join_joint_difference_rad=difference, rejected_candidates=rejected)
                return path
            except ValueError as exc:
                rejected.append(str(exc))
        raise ValueError(f"No screened carry to reference: {rejected}")
