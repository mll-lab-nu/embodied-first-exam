"""Dual-arm IK conversion of a Rope Threading object witness (no physics).

Serialized timeline: the rope moves only while exactly one hand pinches it;
the other hand moves only while tip travel is constant. Every sample is a full
joint configuration of both arms checked against rings/stands/bases, the
table, the other arm, authored same-arm pairs, joint limits with margin and
the current follow-the-leader rope tube.

For each hold the planner enumerates grasp orientations and IK branches at
the grasp pose, keeps a branch only if the whole rope-following segment stays
on it without a joint jump, and then connects the arm to that branch with a
collision-checked joint-space transit. Sampled configurations are evidence of
reachability and clearance at the samples, not a continuous certificate and
not a physical execution.
"""
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .relay_kinematics import (RopeThreadingKinematics, grasp_orientation, interpolate_pose,
                             track_orientation, track_material_orientation)
from topogym.utils.arrays import to_numpy
from .object_oracle import Track, build_tip_route

FAMILIES = ("across", "along", "along_lead")
ROLLS_DEG = (0., -90., 90., 180., 45., -45., 135., -135.)
DEFAULT_OPTIONS = dict(hold_step_m=.01, joint_step_rad=.05, approach_m=.06, approach_step_m=.005,
                       max_joint_change_rad=.5, branch_seeds=16, pinch_opening_m=.0123, free_opening_m=.03,
                       release_opening_m=.017,
                       material_tangent=False, material_tangent_delay_m=0., material_tangent_min_lead_m=0.,
                       material_axis_tolerance_deg=0., max_holds=None, recover_wrist_branch=False,
                       fixture_margin_m=.005, rope_margin_m=.003, inter_arm_m=.01, max_penetration_m=0.)


class RelayPlanner:
    def __init__(self, problem, track, holds, assignment, options=None, progress=None, kin=None, attempt_progress=None):
        self.problem, self.track, self.holds = problem, track, holds
        self.assignment = dict(assignment)
        self.o = dict(DEFAULT_OPTIONS, **(options or {}))
        self.kin = RopeThreadingKinematics(problem) if kin is None else kin
        self.q = self.kin.home.copy()
        self.progress = progress or (lambda *a: None)
        self.attempt_progress = attempt_progress or (lambda *a: None)
        self.samples = []
        self.phases = []
        self.stays = []
        self.rng = np.random.default_rng(0)

    # ----- helpers -------------------------------------------------------
    def side(self, hand):
        return self.assignment[hand]

    def arm(self, side):
        return self.kin.robot._q_indices[side][:6]

    def set_fingers(self, q, side, opening):
        q = np.asarray(q, float).copy()
        q[self.kin.robot._q_indices[side][6:]] = opening
        return q

    def grasp_pose(self, hold, sigma, family, roll):
        side = self.side(hold["hand"])
        station = hold["station_m"]
        p = self.track.rope([station], sigma)[0]
        t = self.track.tangent(np.array([station+sigma]))[0]
        r = grasp_orientation(t, family, roll)
        return p-r.apply(self.kin.pad_offset[side]), r

    def check(self, q, holding):
        return self.kin.check(q, holding=holding, margin_m=self.o["fixture_margin_m"],
                              rope_margin_m=self.o["rope_margin_m"], inter_arm_m=self.o["inter_arm_m"],
                              max_penetration_m=self.o["max_penetration_m"])

    @staticmethod
    def issues(result):
        extra = {k: v for k, v in result.items() if k.endswith("_near_fixtures")
                 or k in {"self_collisions", "rejected_contacts"}}
        return str(result["issues"])+(f" {extra}" if extra else "")

    def other_holder(self, hold, sigma):
        others = [h for h in self.holds if h["hand"] != hold["hand"]
                  and h["sigma_start"]-1e-9 <= sigma <= h["sigma_end"]+1e-9]
        return self.side(others[0]["hand"]) if others else None

    def branches(self, side, pose, seed):
        """Distinct limit-respecting IK solutions, nearest to the seed first."""
        idx = self.arm(side)
        lo, hi = self.kin.limits[side][:, 0]+.02, self.kin.limits[side][:, 1]-.02
        found = []
        # Only the moving arm may change its seed. Replacing the full qpos
        # with home silently teleports the other (possibly holding) arm when
        # this branch is committed at pinch, invalidating its collision audit.
        home_seed = np.asarray(seed, float).copy()
        home_seed[idx] = self.kin.home[idx]
        starts = [np.asarray(seed, float), home_seed]
        for _ in range(self.o["branch_seeds"]):
            s = np.asarray(seed, float).copy()
            s[idx] = self.rng.uniform(lo, hi)
            starts.append(s)
        for start in starts:
            try:
                q = self.kin.solve(side, pose, start, iterations=200)
            except ValueError:
                continue
            if all(np.abs(q[idx]-f[idx]).max() > .3 for f in found):
                found.append(q)
        # Genesis' own IK as an extra branch finder (then polished by the DLS
        # solver so the result respects the same tolerances and limits).
        group = self.kin.robot.groups[side]
        hand_p, hand_r = self.kin.hand_target(side, pose)
        for start in starts[:10]:
            try:
                raw = self.kin.ik.solve_checked(link_name=group.hand_link, position_world_m=hand_p,
                                                orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]], initial_qpos=start,
                                                joint_dof_indices=self.kin.robot._indices[side][:6], max_solver_iterations=300)
                q = self.kin.solve(side, pose, raw, iterations=60)
            except ValueError:
                continue
            if np.all(q[idx] > lo) and np.all(q[idx] < hi) and all(np.abs(q[idx]-f[idx]).max() > .3 for f in found):
                found.append(q)
        return sorted(found, key=lambda q: np.abs(q[idx]-np.asarray(seed)[idx]).max())

    # ----- segments ------------------------------------------------------
    def cartesian(self, side, q_start, target, *, steps, holding, opening, phase, sigma, record):
        """Straight TCP line from the pose at q_start to target (small moves)."""
        idx = self.arm(side)
        start = self.kin.tcp_pose(q_start, side)
        q = self.set_fingers(q_start, side, opening)
        minima = []
        for k in range(1, steps+1):
            pose = interpolate_pose(start, target, k/steps)
            try:
                candidate = self.kin.solve(side, pose, q)
            except ValueError as error:
                raise ValueError(f"{phase} at step {k}/{steps}: {error}") from error
            if np.abs(candidate[idx]-q[idx]).max() > self.o["max_joint_change_rad"]:
                raise ValueError(f"{phase}: joint branch jump at step {k}/{steps}")
            candidate = self.set_fingers(candidate, side, opening)
            result = self.check(candidate, holding)
            if not result["passed"]:
                raise ValueError(f"{phase}: {self.issues(result)} at step {k}/{steps}")
            minima.append(result)
            q = candidate
            record.append(dict(phase=phase, sigma=float(sigma), q=q.tolist()))
        return q, minima

    def joint_transit(self, side, q_from, q_to, *, holding, opening, phase, sigma, record):
        idx = self.arm(side)
        q_to = self.set_fingers(q_to, side, opening)
        span = float(np.abs(q_to[idx]-q_from[idx]).max())
        steps = max(1, int(np.ceil(span/self.o["joint_step_rad"])))
        minima = []
        q = self.set_fingers(q_from, side, opening)
        for k in range(1, steps+1):
            candidate = q.copy()
            candidate[idx] = q_from[idx]+(k/steps)*(q_to[idx]-q_from[idx])
            result = self.check(candidate, holding)
            if not result["passed"]:
                raise ValueError(f"{phase}: {self.issues(result)} at step {k}/{steps}")
            minima.append(result)
            q = candidate
            record.append(dict(phase=phase, sigma=float(sigma), q=q.tolist()))
        return q, minima

    def transit(self, side, q_to, *, holding, phase, sigma, record):
        """Try a direct joint path, short detours, home, then a Cartesian lift."""
        saved, saved_q = len(record), self.q.copy()
        try:
            return self.joint_transit(side, self.q, q_to, holding=holding, opening=self.o["free_opening_m"],
                                      phase=phase, sigma=sigma, record=record)
        except ValueError as direct:
            record[:] = record[:saved]
            # A straight joint chord can clip a rim even when both ends are
            # clear. Try short shoulder/elbow detours before a large trip home.
            # The non-moving arm remains at its actual held configuration.
            indices = self.arm(side)
            lo = self.kin.limits[side][:, 0]+.02
            hi = self.kin.limits[side][:, 1]-.02
            for fraction in (.5, .75):
                for joint, offset in ((1, -.2), (1, -.4), (2, .2), (2, -.2), (0, -.2), (0, .2)):
                    middle = saved_q.copy()
                    middle[indices] += fraction*(q_to[indices]-saved_q[indices])
                    middle[indices[joint]] += offset
                    if np.any(middle[indices] < lo) or np.any(middle[indices] > hi):
                        continue
                    try:
                        q, m1 = self.joint_transit(side, saved_q, middle, holding=holding,
                            opening=self.o["free_opening_m"], phase=phase+"/detour", sigma=sigma, record=record)
                        q, m2 = self.joint_transit(side, q, q_to, holding=holding,
                            opening=self.o["free_opening_m"], phase=phase+"/detour", sigma=sigma, record=record)
                        return q, m1+m2
                    except ValueError:
                        record[:] = record[:saved]
            home = self.q.copy()
            home[self.arm(side)] = self.kin.home[self.arm(side)]
            try:
                q, m1 = self.joint_transit(side, self.q, home, holding=holding, opening=self.o["free_opening_m"],
                                           phase=phase+"/via_home", sigma=sigma, record=record)
                q, m2 = self.joint_transit(side, q, q_to, holding=holding, opening=self.o["free_opening_m"],
                                           phase=phase+"/via_home", sigma=sigma, record=record)
                return q, m1+m2
            except ValueError as via:
                record[:] = record[:saved]
                # Lift the hand straight up first (Cartesian), then go in joint space.
                try:
                    p, r = self.kin.tcp_pose(self.q, side)
                    q, m1 = self.cartesian(side, self.q, (p+[0., 0., .12], r), steps=8, holding=holding,
                                           opening=self.o["free_opening_m"], phase=phase+"/lift", sigma=sigma, record=record)
                    self.q = q
                    q, m2 = self.joint_transit(side, q, q_to, holding=holding, opening=self.o["free_opening_m"],
                                               phase=phase+"/lift", sigma=sigma, record=record)
                    return q, m1+m2
                except ValueError as lift:
                    self.q, record[:] = saved_q, record[:saved]
                    raise ValueError(f"direct: {direct}; via_home: {via}; lift: {lift}")

    def desired_orientation(self, hold, sigma, t, fallback):
        """Scheduled orientation for the hand at this travel, or the fallback."""
        schedule = hold.get("orientation")
        if not schedule:
            return fallback
        arc = float(sigma-hold["station_behind_tip_m"])
        chosen = None
        for entry in schedule:
            if float(entry[0]) <= arc:
                chosen = entry
        if chosen is None:
            return fallback
        return grasp_orientation(t, chosen[1], np.deg2rad(float(chosen[2])))

    def reconfiguration(self, side, q_from, q_to, target_pad, *, tolerance_m=.006, substeps=12, holding=None):
        """Joint-space path between two IK solutions whose pad stays on the rope.

        Wrist branch changes pass near the wrist singularity; the pad position
        must stay within tolerance and every sub-configuration must pass the
        geometric checks. Returns the checked sub-configurations or None.
        """
        idx = self.arm(side)
        path = []
        for k in range(1, substeps+1):
            q = q_from.copy()
            q[idx] = q_from[idx]+(k/substeps)*(q_to[idx]-q_from[idx])
            p, r = self.kin.tcp_pose(q, side)
            pad = p+r.apply(self.kin.pad_offset[side])
            if np.linalg.norm(pad-target_pad) > tolerance_m:
                return None
            result = self.check(q, side if holding is None else holding)
            if not result["passed"]:
                return None
            path.append((q, result))
        return path

    def follow(self, hold, family, roll, q_start, record, *, orientation=None, holding=None):
        """Rope-following segment on one IK branch; no joint jumps allowed.

        The tool orientation tracks the rope with minimal reorientation (closing
        axis perpendicular to the rope). If a sample cannot be reached on the
        branch, small rotations about the closing axis and about the rope are
        tried before the segment is rejected.
        """
        side = self.side(hold["hand"])
        holders = {side} if holding is None else set(holding)
        idx = self.arm(side)
        station = hold["station_m"]
        align_material = (self.o["material_tangent"] and
                          hold["station_behind_tip_m"] >= self.o["material_tangent_min_lead_m"])
        sigmas = np.arange(hold["sigma_start"], hold["sigma_end"], self.o["hold_step_m"])
        sigmas = np.r_[sigmas[1:], hold["sigma_end"]] if hold["sigma_end"] > hold["sigma_start"]+1e-12 else np.array([])
        q, minima = self.set_fingers(q_start, side, self.o["pinch_opening_m"]), []
        R = orientation if orientation is not None else self.grasp_pose(hold, hold["sigma_start"], family, roll)[1]
        adjustments = [(0., 0.)]+[(np.deg2rad(a), 0.) for a in (10, -10, 20, -20, 30, -30)] \
            +[(0., np.deg2rad(b)) for b in (10, -10, 20, -20)]
        free_adjustments = adjustments
        for sigma in sigmas:
            self.kin.set_rope(self.track.rope(self.problem.stations_m, sigma))
            p = self.track.rope([station], sigma)[0]
            t = self.track.tangent(np.array([station+sigma]))[0]
            desired = self.desired_orientation(hold, sigma, t, None)
            if desired is not None:
                # Turn towards the scheduled orientation by at most 15 degrees per sample.
                delta = (desired*R.inv()).as_rotvec()
                angle = float(np.linalg.norm(delta))
                if angle > 1e-9:
                    R = Rotation.from_rotvec(delta*min(1., np.deg2rad(15)/angle))*R
            material_active = align_material and (
                hold["sigma_start"] > 1e-9 or sigma >= self.o["material_tangent_delay_m"])
            base = track_material_orientation(R, t, family) if material_active else track_orientation(R, t)
            if material_active and self.o["material_tangent_delay_m"] and hold["sigma_start"] <= 1e-9:
                delta = (base*R.inv()).as_rotvec()
                base = Rotation.from_rotvec(delta*min(1., .25/max(np.linalg.norm(delta), 1e-12)))*R
            adjustments = ([(0., np.deg2rad(b)) for b in (0, 10, -10, 20, -20, 30, -30)]
                           if material_active else free_adjustments)
            if material_active and self.o["material_axis_tolerance_deg"]:
                tolerance = self.o["material_axis_tolerance_deg"]
                adjustments += [(np.deg2rad(a), 0.) for a in (5, -5, 10, -10, 15, -15, tolerance, -tolerance)
                                if abs(a) <= tolerance]
            errors = []
            for about_y, about_t in adjustments:
                candidate_r = Rotation.from_rotvec(about_t*t)*Rotation.from_rotvec(about_y*base.apply([0., 1., 0.]))*base
                if material_active:
                    allowed = max(np.deg2rad(self.o["material_axis_tolerance_deg"]),
                                  (track_material_orientation(base, t, family)*base.inv()).magnitude())
                    error = (track_material_orientation(candidate_r, t, family)*candidate_r.inv()).magnitude()
                    if error > allowed+1e-8:
                        errors.append("material axis tilt exceeds the alignment envelope")
                        continue
                pose = (p-candidate_r.apply(self.kin.pad_offset[side]), candidate_r)
                try:
                    candidate = self.kin.solve(side, pose, q)
                except ValueError as error:
                    errors.append(str(error)[:60]); continue
                candidate = self.set_fingers(candidate, side, self.o["pinch_opening_m"])
                if np.abs(candidate[idx]-q[idx]).max() > self.o["max_joint_change_rad"]:
                    flip = self.reconfiguration(side, q, candidate, p, holding=holders)
                    if flip is None:
                        errors.append("joint branch jump"); continue
                    for qq, rr in flip[:-1]:
                        minima.append(rr)
                        record.append(dict(phase=f"hold:{hold['hand']}:{hold['ring']}/reconfigure", sigma=float(sigma), q=qq.tolist()))
                result = self.check(candidate, holders)
                if not result["passed"]:
                    errors.append(self.issues(result)); continue
                q, R = candidate, candidate_r
                minima.append(result)
                record.append(dict(phase=f"hold:{hold['hand']}:{hold['ring']}", sigma=float(sigma), q=q.tolist()))
                break
            else:
                # A wrist branch can end at a joint limit even though the
                # same TCP pose exists on the other branch. Switch at the
                # previous material travel, keeping the captured band still,
                # then try the next target from that branch.
                if self.o["recover_wrist_branch"]:
                    old_pose = self.kin.tcp_pose(q, side)
                    old_pad = old_pose[0]+old_pose[1].apply(self.kin.pad_offset[side])
                    recovered = False
                    for branch in self.branches(side, old_pose, q):
                        if np.max(np.abs(branch[idx]-q[idx])) < .3:
                            continue
                        branch = self.set_fingers(branch, side, self.o["pinch_opening_m"])
                        flip = self.reconfiguration(side, q, branch, old_pad, holding=holders, substeps=24)
                        if flip is None or any((self.kin.tcp_pose(qq, side)[1]*old_pose[1].inv()).magnitude() > .12
                                               for qq, _ in flip):
                            continue
                        pose = (p-base.apply(self.kin.pad_offset[side]), base)
                        try:
                            candidate = self.kin.solve(side, pose, branch)
                        except ValueError:
                            continue
                        candidate = self.set_fingers(candidate, side, self.o["pinch_opening_m"])
                        result = self.check(candidate, holders)
                        if not result["passed"] or np.max(np.abs(candidate[idx]-branch[idx])) > self.o["max_joint_change_rad"]:
                            continue
                        before_sigma = record[-1]["sigma"] if record else hold["sigma_start"]
                        for qq, rr in flip:
                            minima.append(rr)
                            record.append(dict(phase=f"hold:{hold['hand']}:{hold['ring']}/branch",
                                               sigma=float(before_sigma), q=qq.tolist()))
                        minima.append(result)
                        record.append(dict(phase=f"hold:{hold['hand']}:{hold['ring']}", sigma=float(sigma), q=candidate.tolist()))
                        q, R, recovered = candidate, base, True
                        break
                    if recovered:
                        continue
                # Reorient the wrist about the rope (or the closing axis) in
                # small sub-steps at constant travel before giving up.
                done = False
                for about_y, about_t in [(0., np.deg2rad(a)) for a in (45, -45, 90, -90, 135, -135, 180)] \
                        +[(np.deg2rad(b), 0.) for b in (45, -45, 90, -90)]:
                    if material_active and about_y:
                        continue
                    steps = int(np.ceil(max(abs(about_y), abs(about_t))/np.deg2rad(10)))
                    qq, path, ok = q, [], True
                    y_axis = base.apply([0., 1., 0.])
                    for k in range(1, steps+1):
                        f = k/steps
                        candidate_r = Rotation.from_rotvec(f*about_t*t)*Rotation.from_rotvec(f*about_y*y_axis)*base
                        pose = (p-candidate_r.apply(self.kin.pad_offset[side]), candidate_r)
                        try:
                            cand = self.kin.solve(side, pose, qq)
                        except ValueError:
                            ok = False; break
                        if np.abs(cand[idx]-qq[idx]).max() > self.o["max_joint_change_rad"]:
                            ok = False; break
                        cand = self.set_fingers(cand, side, self.o["pinch_opening_m"])
                        result = self.check(cand, holders)
                        if not result["passed"]:
                            ok = False; break
                        qq = cand
                        path.append((cand, result, candidate_r))
                    if ok and path:
                        for cand, result, candidate_r in path:
                            minima.append(result)
                            record.append(dict(phase=f"hold:{hold['hand']}:{hold['ring']}/reorient", sigma=float(sigma), q=cand.tolist()))
                        q, R = path[-1][0], path[-1][2]
                        done = True
                        break
                if not done:
                    raise ValueError(f"hold {hold['hand']}:{hold['ring']} at travel {sigma:.3f}: {sorted(set(errors))}")
        if align_material and len(sigmas):
            aligned = track_material_orientation(R, t, family)
            if (aligned*R.inv()).magnitude() > np.deg2rad(max(5., self.o["material_axis_tolerance_deg"]))+1e-8:
                raise ValueError("Material axis did not align before the handoff")
        return q, minima

    def retreat_and_park(self, hand, sigma, record, *, holding):
        """Open, back away from the rope, then return to the arm's home configuration.

        Several retreat directions are tried (tool axis, world up, towards the
        base). The just-opened fingers start within the rope margin, so the
        retreating hand is checked like a holder (fingers excluded) during the
        retreat; the park transit uses the full check.
        """
        side = self.side(hand)
        self.kin.set_rope(self.track.rope(self.problem.stations_m, sigma))
        p, r = self.kin.tcp_pose(self.q, side)
        base_link = self.kin.robot.entity.links[self.kin.link_names.index(f"{side}/base_link")]
        base_xy = to_numpy(base_link.get_pos()).reshape(-1)[:2]
        towards_base = np.r_[base_xy-p[:2], 0.]
        towards_base = towards_base/max(np.linalg.norm(towards_base), 1e-9)
        holders = set() if holding is None else ({holding} if isinstance(holding, str) else set(holding))
        n = max(2, int(np.ceil(self.o["approach_m"]/self.o["approach_step_m"])))
        errors, minima = [], None
        # A wide-open pad can strike the next ring before the arm retreats.
        # Try a narrower release if necessary; open fully only in a checked park.
        for opening in (self.o["free_opening_m"], self.o["release_opening_m"]):
            for name, direction in (("tool", -r.apply([1., 0., 0.])), ("up", np.array([0., 0., 1.])), ("base", towards_base)):
                saved = len(record)
                try:
                    q, minima = self.cartesian(side, self.q, (p+self.o["approach_m"]*direction, r), steps=n,
                                               holding=holders | {side}, opening=opening,
                                               phase=f"retreat:{hand}/{name}", sigma=sigma, record=record)
                    self.q = q
                    break
                except ValueError as error:
                    errors.append(f"{name} opening={opening}: {error}")
                    record[:] = record[:saved]
            if minima is not None:
                break
        if minima is None:
            raise ValueError("retreat failed: " + "; ".join(errors))
        # Keep backing off along the same direction until the whole arm clears
        # the rope margin (the fingers start within it); at most 4 extensions.
        for extension in range(4):
            full = self.check(self.q, holders)
            if full["passed"] or f"{side}/rope" not in full["issues"]:
                break
            p, r = self.kin.tcp_pose(self.q, side)
            q, more = self.cartesian(side, self.q, (p+self.o["approach_m"]*direction, r), steps=n,
                                     holding=holders | {side}, opening=opening,
                                     phase=f"retreat:{hand}/{name}+{extension+1}", sigma=sigma, record=record)
            self.q = q
            minima += more
        home = self.q.copy()
        home[self.arm(side)] = self.kin.home[self.arm(side)]
        # Park: direct joint path home; else lift first; else move towards the
        # base, lift, then go home (the joint path must not sweep the rope).
        park_errors = []
        idx = self.arm(side)
        waist = idx[0]
        # Joint-space waypoints: fold the arm towards home without turning the
        # waist, then turn (or the reverse), so the gripper does not sweep the rope.
        fold = home.copy(); fold[waist] = self.q[waist]
        turn = self.q.copy(); turn[waist] = home[waist]
        # Joint-ordered sequences: move the listed joint groups to home one
        # group at a time (0 waist, 1 shoulder, 2 elbow, 3 forearm roll,
        # 4 wrist angle, 5 wrist rotate). Lifting the shoulder first carries
        # the gripper over the rope before the arm folds back.
        def ordered(groups):
            q, points = self.q.copy(), []
            for group in groups:
                q = q.copy()
                for j in group:
                    q[idx[j]] = home[idx[j]]
                points.append(q)
            return points
        lo, hi = self.kin.limits[side][:, 0]+.02, self.kin.limits[side][:, 1]-.02
        lifted = self.q.copy(); lifted[idx[1]] = max(lo[1], self.q[idx[1]]-.6)
        strategies = (("fold_then_turn", [fold]), ("turn_then_fold", [turn]),
                      ("shoulder_first", ordered([[1], [2, 4], [0], [3, 5]])),
                      ("lift_then_fold", [lifted, fold]),
                      ("wrist_first", ordered([[4, 5, 3], [2], [1], [0]])))
        for name, waypoints in strategies:
            saved_q, saved = self.q.copy(), len(record)
            try:
                more = []
                for wp in waypoints+[home]:
                    q, m = self.joint_transit(side, self.q, wp, holding=holders, opening=self.o["free_opening_m"],
                                              phase=f"park:{hand}/{name}", sigma=sigma, record=record)
                    self.q = q
                    more += m
                return minima+more
            except ValueError as error:
                park_errors.append(f"{name}: {error}")
                self.q, record[:] = saved_q, record[:saved]
        for name, legs in (("direct", []), ("up", [np.array([0., 0., .15])]),
                           ("base_up", [.15*towards_base, np.array([0., 0., .15])])):
            saved_q, saved = self.q.copy(), len(record)
            try:
                more = []
                for leg in legs:
                    p, r = self.kin.tcp_pose(self.q, side)
                    steps = max(2, int(np.ceil(np.linalg.norm(leg)/self.o["transit_step_m"])) if "transit_step_m" in self.o else 8)
                    q, m = self.cartesian(side, self.q, (p+leg, r), steps=steps, holding=holders,
                                          opening=self.o["free_opening_m"], phase=f"park:{hand}/{name}", sigma=sigma, record=record)
                    self.q = q
                    more += m
                q, m = self.joint_transit(side, self.q, home, holding=holders, opening=self.o["free_opening_m"],
                                          phase=f"park:{hand}/{name}", sigma=sigma, record=record)
                self.q = q
                return minima+more+m
            except ValueError as error:
                park_errors.append(f"{name}: {error}")
                self.q, record[:] = saved_q, record[:saved]
        # No way home: raise the arm (shoulder back/up, elbow folded) to a clear
        # parking pose above the rope so later transits can pass over it.
        for name, d_shoulder, d_elbow in (("raise", -.4, 0.), ("raise_fold", -.7, .3), ("raise_more", -1.0, .5)):
            target = self.q.copy()
            target[idx[1]] = float(np.clip(self.q[idx[1]]+d_shoulder, lo[1], hi[1]))
            target[idx[2]] = float(np.clip(self.q[idx[2]]+d_elbow, lo[2], hi[2]))
            saved_q, saved = self.q.copy(), len(record)
            try:
                q, m = self.joint_transit(side, self.q, target, holding=holders, opening=self.o["free_opening_m"],
                                          phase=f"park:{hand}/{name}", sigma=sigma, record=record)
                self.q = q
                self.stays.append(dict(hand=hand, sigma=float(sigma), parked=name))
                return minima+m
            except ValueError as error:
                park_errors.append(f"{name}: {error}")
                self.q, record[:] = saved_q, record[:saved]
        # Otherwise stay at the retreated configuration if it is itself clear.
        # Later segments keep checking this arm every sample.
        stay = self.check(self.q, holders)
        if stay["passed"]:
            record.append(dict(phase=f"park:{hand}/stay", sigma=float(sigma), q=self.q.tolist()))
            self.stays.append(dict(hand=hand, sigma=float(sigma), reasons=park_errors))
            return minima+[stay]
        raise ValueError("park failed: " + "; ".join(park_errors))

    # ----- one hold ------------------------------------------------------
    def attempt_hold(self, hold, family, roll, previous, record):
        side, sigma = self.side(hold["hand"]), hold["sigma_start"]
        holding_other = self.other_holder(hold, sigma)
        self.kin.set_rope(self.track.rope(self.problem.stations_m, sigma))
        p, r = self.grasp_pose(hold, sigma, family, roll)
        grasp = (p, r)
        pre = (p-r.apply([self.o["approach_m"], 0., 0.]), r)
        tried = []
        for branch in self.branches(side, grasp, self.q):
            trial, q_before = [], self.q.copy()
            try:
                pinched = self.set_fingers(branch, side, self.o["pinch_opening_m"])
                both = {side} | ({holding_other} if holding_other else set())
                result = self.check(pinched, both)
                if not result["passed"]:
                    raise ValueError(f"grasp pose: {self.issues(result)}")
                # Connect, acquire and park the previous holder before checking
                # the full hold. Testing the entire hold while the old holder
                # remains frozen at the handoff creates false inter-arm failures.
                # The follow below still rejects the complete branch on failure.
                self.kin.set_rope(self.track.rope(self.problem.stations_m, sigma))
                q_pre = self.kin.solve(side, pre, branch, iterations=200)
                if np.abs(q_pre[self.arm(side)]-branch[self.arm(side)]).max() > self.o["max_joint_change_rad"]:
                    raise ValueError("pre-grasp pose leaves the branch")
                minima = []
                if previous is not None and previous["hand"] == hold["hand"]:
                    minima += self.retreat_and_park(hold["hand"], sigma, trial, holding=None)
                q, m = self.transit(side, q_pre, holding=holding_other, phase=f"transit:{hold['hand']}:{hold['ring']}",
                                    sigma=sigma, record=trial)
                minima += m
                n = max(2, int(np.ceil(self.o["approach_m"]/self.o["approach_step_m"])))
                q, m = self.cartesian(side, q, grasp, steps=n, holding={side} | ({holding_other} if holding_other else set()),
                                      opening=self.o["free_opening_m"], phase=f"approach:{hold['hand']}:{hold['ring']}",
                                      sigma=sigma, record=trial)
                minima += m
                if np.abs(q[self.arm(side)]-branch[self.arm(side)]).max() > .1:
                    raise ValueError("approach landed on a different branch")
                self.q = self.set_fingers(branch, side, self.o["pinch_opening_m"])
                trial.append(dict(phase=f"pinch:{hold['hand']}:{hold['ring']}", sigma=float(sigma), q=self.q.tolist()))
                if previous is not None and previous["hand"] != hold["hand"]:
                    minima += self.retreat_and_park(previous["hand"], sigma, trial, holding=side)
                _, m = self.follow(hold, family, roll, self.q, trial)
                minima += m
                self.q = np.asarray(trial[-1]["q"])
                record += trial
                return dict(family=family, roll_deg=float(np.rad2deg(roll)), samples=len(trial),
                            branch_index=len(tried),
                            minimum_fixture_m=min(min(x.get("left_fixture_m", 1.), x.get("right_fixture_m", 1.)) for x in minima),
                            minimum_rope_m=min(min(x.get("left_rope_m", 1.), x.get("right_rope_m", 1.)) for x in minima),
                            minimum_inter_arm_m=min(x["inter_arm_m"] for x in minima),
                            minimum_table_m=min(x["table_clearance_m"] for x in minima))
            except ValueError as error:
                tried.append(str(error))
                self.q = q_before
        raise ValueError("; ".join(tried) if tried else "no IK branch at the grasp pose")

    # ----- driver --------------------------------------------------------
    def plan(self, candidates=None):
        candidates = candidates or [(f, np.deg2rad(d)) for f in FAMILIES for d in ROLLS_DEG]
        holds = sorted(self.holds, key=lambda h: (h["sigma_start"], h["role"] == "pusher"))
        if self.o["max_holds"] is not None:
            holds = holds[:self.o["max_holds"]]
        previous = None
        for index, hold in enumerate(holds):
            report = dict(hand=hold["hand"], side=self.side(hold["hand"]), role=hold["role"], ring=hold["ring"],
                          sigma_start=hold["sigma_start"], sigma_end=hold["sigma_end"],
                          unheld_regrasp=hold.get("unheld_regrasp", False), attempts=[], accepted=None)
            options = candidates
            if hold.get("orientation"):
                first = hold["orientation"][0]
                options = [(first[1], np.deg2rad(float(first[2])))]+[c for c in candidates if c[0] != first[1] or abs(np.rad2deg(c[1])-float(first[2])) > 1e-9]
            for family, roll in options:
                started = time.monotonic()
                record = []
                try:
                    accepted = self.attempt_hold(hold, family, roll, previous, record)
                except ValueError as error:
                    report["attempts"].append(dict(family=family, roll_deg=float(np.rad2deg(roll)),
                                                   error=str(error)[:600], wall_s=time.monotonic()-started))
                    self.attempt_progress(index, report)
                    continue
                accepted["wall_s"] = time.monotonic()-started
                report["accepted"] = accepted
                self.attempt_progress(index, report)
                self.samples += record
                break
            self.phases.append(report)
            self.progress(index, len(holds), report["accepted"])
            if report["accepted"] is None:
                return dict(passed=False, failed_hold=index, phases=self.phases)
            previous = hold
        if len(holds) < len(self.holds):
            return dict(passed=True, complete_relay=False, phases=self.phases)
        # Native success permits retaining the final grasp. Keep that stable
        # configuration instead of requiring an unrelated release/park path.
        self.phases.append(dict(role="final_hold", passed=True, samples=0))
        return dict(passed=True, phases=self.phases)


def plan_relay_ik(problem, witness, *, assignment, options=None, progress=None, kin=None, holds=None, track=None,
                  attempt_progress=None):
    started = time.monotonic()
    if track is None:
        controls, dense, _ = build_tip_route(problem, witness["route"]["parameters"])
        track = Track(problem.initial_m, dense)
    holds = witness["schedule"]["holds"] if holds is None else holds
    planner = RelayPlanner(problem, track, holds, assignment, options, progress, kin=kin, attempt_progress=attempt_progress)
    result = planner.plan()
    return dict(scope="sampled dual-arm IK and collision checks along the object witness; no physics",
                assignment=dict(assignment), options=planner.o, families=FAMILIES, rolls_deg=ROLLS_DEG,
                pad_offset_m={s: v.tolist() for s, v in planner.kin.pad_offset.items()},
                passed=bool(result["passed"]), complete_relay=result.get("complete_relay", True),
                phases=result["phases"], failed_hold=result.get("failed_hold"),
                unparked_arms=planner.stays,
                sample_count=len(planner.samples), wall_time_s=time.monotonic()-started,
                robot_ik_verified=bool(result["passed"]), robot_execution_verified=False, task_success=False), planner.samples
