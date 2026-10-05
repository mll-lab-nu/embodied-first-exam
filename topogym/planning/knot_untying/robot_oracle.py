"""ALOHA unties the knot in the frozen benchmark instance, choosing each grasp from the live rope.

Same decisions as scripts/run_knot_robot_route.py (HULK node deletion with a far-end pin, Reidemeister end spread, the
easy R-II carry; topogym/planning/knot_untying/route_rule.py), but executed through the task directory's own
rcb_topogym.Session: the frozen instance (settled IPC state, 2.5 ms x 10 ticks per 25 ms control step, one IPC substep,
physical grasping unless the instance says otherwise). Every control step is a recorded JOINT_ABS row (arm joints,
gripper opening width), saved as trajectory.npz for `rcb_topogym.py replay`, which grades it in a fresh process.

Usage: python scripts/oracle_runners/run_knot_oracle.py --variation knot_untying_medium --output <new dir>
"""
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]

TIERS = {  # Route defaults; physical qualification is recorded separately for each run.
    "knot_untying_easy": dict(kind="carry", s=.224, delta=(-.095, 0.), lift=.025),
    "knot_untying_medium": dict(kind="closed_loop", hold="far", direction="tangent", lift=.015, straighten=.9),
    "knot_untying_hard": dict(kind="closed_loop", hold="far", direction="away", lift=.03,
                             anchor_lift_m=.002, pinch_height_m=.0015, straighten=.9),
}
DT = .025  # control step of the instances (2.5 ms x 10)
PRE = .05  # pregrasp and retreat height above the pinch, m
COMMAND_TABLE_GAP_M = .0005  # planner margin, not an allowed physical penetration
COMMAND_TABLE_RAISE_PAD_M = .0001  # clear IK's 10 um stopping tolerance on an upward retry


class Solved(Exception):
    """The episode ended in task success: later steps would not change the scene or the recording."""


def task_dir(variation):
    return ROOT/"tasks"/f"topogym-knot-untying-{variation.removeprefix('knot_untying_')}-i00-privileged"


class Runner:
    def __init__(self, args, *, session=None):
        from .artifacts import load_tooling, instance_identity
        from topogym.planning.knot_untying.kinematics import KnotIK
        self.args, self.started = args, time.time()
        self.identity = instance_identity(args.instance)
        self.owns_session = session is None
        self.session = s = (load_tooling(args.variation).Session("knot_untying", instance=str(args.instance))
                            if session is None else session)
        if self.owns_session:
            s.reset()
        elif s.n_steps or s._resets or getattr(s, "gripper_space", "width") != "width":
            raise ValueError("Knot requires a fresh caller-owned Session with width actions")
        self.build_s = time.time()-self.started
        self.env = s.env
        self.task, self.world, self.robot = self.env._task, self.env._world, self.env._robot
        self.ik = KnotIK(self.world, self.robot, self.task.table_height_m)
        self.home = self.ik.seed.copy()
        self.row = s.hold_action()
        self.layout = s.action_layout
        self.dt = float(self.env.timing_spec["control_dt_s"])
        self.q = {side: self.home[self.robot._q_indices[side][:6]].copy() for side in ("left", "right")}
        self.g = {side: float(self.row[s.robot.grip_index[side]]) for side in ("left", "right")}  # opening width, m
        idx, material = self.task.centerline_map
        self.stations = material[idx].mean(axis=1) if material[idx].ndim == 2 else material[idx]
        self.length = float(self.stations[-1]-self.stations[0])
        self.log, self.lines, self.decisions, self.grasps = [], [], [], {}
        self.full_q = self.home.copy()
        # Joint PD tracking leaves a few mm of TCP error at rest: every Cartesian target is shifted
        # by a per-arm bias learned while holding still before a pinch.
        self.bias = {side: np.zeros(3) for side in ("left", "right")}
        self.motion_options = {}
        if self.owns_session:
            s.record_start()

    # ---------- observation ----------
    def line(self):
        from topogym.utils.geometry.rope import sample_material_centerline
        return sample_material_centerline(self.world.read_state()["fem"]["rope"], *self.task.centerline_map)

    def at(self, line, s):
        return np.array([np.interp(s, self.stations, line[:, k]) for k in range(3)])

    def crossings(self, line=None):
        from topogym.assets.geometry.knot_untying import projected_crossings
        return projected_crossings(self.line() if line is None else line)

    def tcp(self, side):
        return np.asarray(self.robot.observe()[side]["tcp_position_world_m"])

    # ---------- actuation ----------
    @property
    def native_command_guard(self):
        """v14+ Session owns its command rules; use the fallback only for older tooling."""
        return callable(getattr(getattr(self.session, 'table_guard', None), 'apply', None))

    def step(self, phase):
        s = self.session
        if s.episode_end == "success":
            raise Solved()
        if s.episode_end is not None or s.episode_done:
            raise RuntimeError(f"episode already ended: {s.episode_end or 'step_limit'}")
        row = s.hold_action()
        for side in self.q:
            row[s.robot.arm_slice[side]] = self.q[side]
            row[s.robot.grip_index[side]] = self.g[side]
        self.validate_command(row)
        ended = s.step(row)
        if self.native_command_guard:
            # Session records the targets after native R4 clipping. Use those
            # accepted targets for the next IK seed instead of the rejected ask.
            accepted_row = s.hold_action()
            self.full_q = self.command_positions(accepted_row)
            for side in self.q:
                self.q[side] = self.full_q[self.robot._q_indices[side][:6]].copy()
                self.g[side] = float(accepted_row[s.robot.grip_index[side]])
        result = self.task.result
        k = len(self.log)
        row = dict(t=float(s.sim_time_s), physics_steps=int(s.physics_steps), phase=phase, gripper=dict(self.g),
                   stable_time_s=float(result.metrics.get("stable_time_s", 0.)), failure=result.reason if result.terminated else None)
        if k % 8 == 0 or ended:
            # Preserve all terminal diagnostics, including nested release/clearance
            # reasons, while the worker is live and before a possible rewind.
            from topogym.utils.io import write_json_atomic
            write_json_atomic(self.args.output/"native_progress.json", dict(
                **row, metrics=dict(result.metrics), task_success=bool(result.task_success)))
        if k % 8 == 0:
            line = self.line()
            self.lines.append((row["t"], line.astype(np.float32)))
            row["crossings"] = len(self.crossings(line))
            # Grasp evidence: rope centre at the grasped arc vs the pads' contact point (rope follows if ~0).
            row["grasped"] = {side: dict(rope_z_m=float(self.at(line, g["s"])[2]),
                                         rope_minus_contact_m=(self.at(line, g["s"])-self.contact_point(side)).round(4).tolist())
                              for side, g in self.grasps.items()}
            held = " ".join(f"{side}: rope z {v['rope_z_m']*1000:.1f} mm, rope-contact {np.round(np.array(v['rope_minus_contact_m'])*1000, 1).tolist()} mm"
                            for side, v in row["grasped"].items())
            print(f"t={row['t']:7.2f}s {phase:22s} crossings={row['crossings']} stable={row['stable_time_s']:.2f}s "
                  f"wall={time.time()-self.started:6.0f}s {held}", flush=True)
        self.log.append(row)
        if ended:
            if s.episode_end == "success":
                raise Solved()
            raise RuntimeError(f"episode ended: {s.episode_end}")

    def command_positions(self, row):
        """Exact accepted joint/finger targets, including width conversion and clipping."""
        command = self.session.robot.command(self.session.robot.clip(np.asarray(row, dtype=np.float32).astype(np.float64)))
        q = self.full_q.copy()
        for side, group in self.robot.groups.items():
            ids = self.robot._q_indices[side]
            q[ids[:6]] = command[side]['joint_position_rad']
            q[ids[6:]] = command[side][group.gripper_field]
        return q

    def validate_command(self, row):
        if self.native_command_guard:
            return  # Session.step applies the published rule once, before physics.
        gaps = self.ik.gripper_table_clearance(self.command_positions(row))
        if min(gaps.values()) < COMMAND_TABLE_GAP_M-1e-9:
            raise ValueError(f'Unsafe gripper command above table: {gaps}')

    def solve(self, side, p, turn, seed=None):
        q = self.full_q.copy() if seed is None else seed
        initial_q = np.asarray(q).copy()
        target = np.asarray(p, float)+self.bias[side]
        native_guard = self.native_command_guard
        trace = []
        for _ in range(1 if native_guard else 4):
            try:
                q = self.ik.solve(side, (target, turn), q)
            except ValueError as error:
                detail = dict(side=side, target_m=target.tolist(), seed_qpos=np.asarray(q).tolist(),
                              turn_xyzw=None if turn is None else turn.as_quat().tolist(), reason=str(error))
                raise ValueError('Cartesian IK rejected: '+json.dumps(detail)) from error
            row = self.session.hold_action()
            for arm in self.robot.groups:
                row[self.session.robot.arm_slice[arm]] = q[self.robot._q_indices[arm][:6]]
                row[self.session.robot.grip_index[arm]] = self.g[arm]
            accepted = self.command_positions(row)
            if native_guard:
                self.full_q = accepted
                return accepted[self.robot._q_indices[side][:6]]
            gap = self.ik.gripper_table_clearance(accepted, (side,))[side]
            trace.append(dict(target_m=target.tolist(), gap_m=float(gap)))
            if gap >= COMMAND_TABLE_GAP_M:
                self.full_q = accepted
                return accepted[self.robot._q_indices[side][:6]]
            # A micron-sized correction can leave the seed inside IK's stopping
            # tolerance and return the same unsafe command on every retry.
            target[2] += COMMAND_TABLE_GAP_M-gap+COMMAND_TABLE_RAISE_PAD_M
        detail = dict(side=side, required_gap_m=COMMAND_TABLE_GAP_M,
                      gripper_widths_m=dict(self.g), initial_qpos=initial_q.tolist(),
                      turn_xyzw=None if turn is None else turn.as_quat().tolist(), trace=trace)
        raise ValueError('No reachable gripper command above the table: '+json.dumps(detail))

    def cartesian(self, side, targets, turn, phase, *, allow_partial=False):
        """TCP through the given points, one per control step; returns False when IK fails (reach limit)."""
        for p in targets:
            try:
                self.q[side] = self.solve(side, p, turn)
            except ValueError:
                if allow_partial:
                    return False
                raise
            self.step(phase)
        return True

    def smooth(self, a, b, speed):
        n = max(2, int(np.ceil(1.5*np.linalg.norm(b-a)/speed/self.dt)))
        u = np.linspace(0, 1, n+1)[1:, None]
        return a+(b-a)*(3*u**2-2*u**3)

    # ---------- grasp primitives ----------
    def clearance(self, line, s):
        """Spatial distance to the nearest strand more than 40 mm of material away."""
        p = self.at(line, s)
        a, b = line[:-1], line[1:]
        far = np.abs(self.stations-s) > .04
        keep = far[:-1] & far[1:]
        ab = b-a
        u = np.clip(((p-a)*ab).sum(1)/np.maximum((ab*ab).sum(1), 1e-12), 0, 1)
        distances = np.linalg.norm(a+ab*u[:, None]-p, axis=1)[keep]
        return float(distances.min()) if len(distances) else float("inf")

    def grasp_site(self, s):
        """Rank nearby 3-D grasp sites; crowding is a preference, not a veto."""
        line = self.line()
        toward = 1. if s < self.length/2 else -1.
        options = getattr(self, 'motion_options', {})
        s += options.get('grasp_shift_m', 0.)
        extent = options.get('grasp_search_m', .16)
        offsets = [0.]+[sign*toward*x for x in np.arange(.005, extent+.0025, .005) for sign in (1., -1.)]
        candidates = []
        for offset in offsets:
            arc = float(np.clip(s+offset, .001, self.length-.001))
            half = min(.019, self.clearance(line, arc)-.004)
            candidates.append((half, -abs(offset), arc))
            if half >= .006:
                return arc, 2*half
        half, _, arc = max(candidates)
        return arc, float(np.clip(2*half, .009, .038))

    def pose(self, side, s, flips=(1, -1)):
        """Vertical pinch over the live rope at s: (tcp, turn, flip, pregrasp joints)."""
        from topogym.planning.knot_untying.kinematics import vertical_pinch
        line = self.line()
        point, tangent = self.at(line, s), (self.at(line, s+.01)-self.at(line, s-.01))[:2]
        options = getattr(self, 'motion_options', {})
        point = point+[0., 0., options.get('pinch_height_m', 0.)]
        errors, candidates = [], []
        if len(flips) > 1 and options.get('grasp_flip') is not None:
            flips = (options['grasp_flip'],)
        indices = self.robot._q_indices[side][:6]
        measured = np.asarray(self.robot.observe()[side]['joint_position_rad'])
        for flip in flips:
            tcp, turn = vertical_pinch(point, tangent, flip,
                yaw_deg=options.get('grasp_yaw_deg', 0.), tilt_deg=options.get('grasp_tilt_deg', 0.))
            try:
                pre = self.ik.solve(side, (tcp+[0, 0, PRE], turn), self.full_q.copy())
                self.ik.solve(side, (tcp, turn), pre)
                joints = pre[indices]
                travel = np.abs(joints-measured)
                candidates.append(((float(travel.max()), float(travel@travel)),
                                   (tcp, turn, flip, joints)))
            except ValueError as error:
                errors.append(str(error)[:80])
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
        raise RuntimeError(f"{side} cannot reach s={s:.3f}: {errors}")

    def wait_for_pregrasp(self, sides, plans, phase):
        """Let torque-limited arms reach the requested orientation before Cartesian descent.

        These tolerances schedule the transition only. The native IK and safety
        rules still validate every command; a timeout does not reject a grasp.
        """
        from scipy.spatial.transform import Rotation
        limit = getattr(self, 'motion_options', {}).get('approach_wait_s', 4.)
        steps = int(np.ceil(limit/self.dt))
        errors = {}
        for k in range(steps+1):
            observation = self.robot.observe()
            for side in sides:
                actual = observation[side]
                turn = Rotation.from_quat(np.asarray(actual['tcp_orientation_wxyz'])[[1, 2, 3, 0]])
                errors[side] = dict(position_m=float(np.linalg.norm(
                    np.asarray(actual['tcp_position_world_m'])-(plans[side][0]+[0, 0, PRE]))),
                    orientation_rad=float((turn.inv()*plans[side][1]).magnitude()))
            ready = all(x['position_m'] <= .02 and x['orientation_rad'] <= .1 for x in errors.values())
            if ready or k == steps:
                return dict(waited_s=k*self.dt, ready=ready, errors=errors)
            self.step(phase+':approach_settle')

    def grasp(self, sides, ss, phase):
        """Both listed arms open, approach, re-aim on the live rope, descend and pinch together."""
        return self.pinch(sides, *self.place(sides, ss, phase), phase)

    def place(self, sides, ss, phase):
        """Open, approach and descend until the open jaws straddle the live rope at the chosen arcs."""
        sites = [self.grasp_site(s) for s in ss]
        ss = [arc for arc, _ in sites]
        opening = {side: cmd for side, (_, cmd) in zip(sides, sites)}
        plans = {side: self.pose(side, s) for side, s in zip(sides, ss)}
        n = max(1, int(np.ceil(getattr(self, 'motion_options', {}).get('approach_s', 1.)/self.dt)))
        start = {side: self.q[side].copy() for side in sides}
        g0 = {side: self.g[side] for side in sides}
        for k, u in enumerate(np.linspace(0, 1, n+1)[1:]):
            for side in sides:
                self.q[side] = start[side]+(plans[side][3]-start[side])*(10*u**3-15*u**4+6*u**5)
                self.g[side] = g0[side]+(opening[side]-g0[side])*min(1., 4*u)
            self.step(phase+":approach")
        tracking = self.wait_for_pregrasp(sides, plans, phase)
        print(f'   {phase}: pregrasp tracking {json.dumps(tracking)}', flush=True)
        # The rope keeps relaxing during the approach: aim again with the same jaw flip.
        plans = {side: self.pose(side, s, (plans[side][2],)) for side, s in zip(sides, ss)}
        paths = {side: self.smooth(self.tcp(side), plans[side][0], .1) for side in sides}
        for k in range(max(len(v) for v in paths.values())):
            for side in sides:
                path = paths[side]
                self.q[side] = self.solve(side, path[min(k, len(path)-1)], plans[side][1])
            self.step(phase+":descend")
        # The descent ends before the PD-tracked TCP arrives: learn the bias until every TCP is within
        # 2 mm, re-aim once if the rope moved, then close.
        self.grasp_turn = {side: plans[side][1] for side in sides}
        record = dict(pregrasp_tracking=tracking)
        for attempt in range(2):
            error = self.converge(sides, {side: plans[side][0] for side in sides}, phase+":converge")
            again = {side: self.pose(side, s, (plans[side][2],)) for side, s in zip(sides, ss)}
            moved = max(float(np.linalg.norm(again[side][0]-plans[side][0])) for side in sides)
            record[f"attempt{attempt}"] = dict(tcp_error_m=error, rope_moved_m=moved,
                                               bias_m={side: self.bias[side].round(4).tolist() for side in sides})
            if moved < .003:
                break
            plans = again
            self.grasp_turn = {side: plans[side][1] for side in sides}
            for side in sides:
                self.q[side] = self.solve(side, plans[side][0], plans[side][1])
        return ss, opening, plans, record

    def pinch(self, sides, ss, opening, plans, record, phase):
        """Close the placed jaws on the rope."""
        for u in np.linspace(0, 1, int(round(.4/self.dt))+1)[1:]:
            for side in sides:
                self.g[side] = opening[side]+(self.args.close-opening[side])*u
            self.step(phase+":close")
        for _ in range(10):
            self.step(phase+":squeeze")
        out = []
        for side, s in zip(sides, ss):
            tcp, turn, flip, _ = plans[side]
            self.grasps[side] = dict(s=s, turn=turn, tcp=tcp.copy(), flip=flip, open=opening[side])
            out.append(dict(side=side, s=s, flip=flip, open_width_m=opening[side], tcp=tcp.round(4).tolist(), placement=record))
        return out

    def converge(self, sides, targets, phase, tolerance=.002, limit_s=4.):
        """Wait until the arms settle, add the remaining TCP error to their bias, repeat until within tolerance.

        One-shot corrections after settling (not a running integral): the IPC-coupled arm responds slowly,
        and an integral would overshoot the fingers into the rope and table.
        """
        previous = {side: self.tcp(side) for side in sides}
        for _ in range(int(limit_s/self.dt)):
            self.step(phase)
            now = {side: self.tcp(side) for side in sides}
            settled = all(np.linalg.norm(now[side]-previous[side])/self.dt < .003 for side in sides)
            previous = now
            errors = {side: targets[side]-now[side] for side in sides}
            if max(float(np.linalg.norm(e)) for e in errors.values()) <= tolerance:
                break
            if settled:
                print(f"   {phase}: settled TCP error {[np.round(errors[x]*1000, 1).tolist() for x in sides]} mm, "
                      f"bias {[np.round(self.bias[x]*1000, 1).tolist() for x in sides]} mm", flush=True)
                for side in sides:
                    bias = self.bias[side]+errors[side]
                    self.bias[side] = bias*min(1., .04/max(float(np.linalg.norm(bias)), 1e-9))
                    self.q[side] = self.solve(side, targets[side], self.grasp_turn[side])
        return max(float(np.linalg.norm(self.tcp(side)-targets[side])) for side in sides)

    def release(self, side, lower, phase):
        g = self.grasps.pop(side)
        tcp = self.tcp(side)
        if lower:
            from .kinematics import CONTACT_IN_TCP_M
            rest_z = self.task.table_height_m+self.task.layout.rope_radius_m-g['turn'].apply(CONTACT_IN_TCP_M)[2]
            # Retain the selected pinch height while lowering: opening the jaws
            # lets the strand settle the remaining distance onto the table.
            rest_z += getattr(self, 'motion_options', {}).get('pinch_height_m', 0.)
            target = tcp.copy()
            target[2] = max(float(tcp[2]-lower), float(rest_z))
            self.cartesian(side, self.smooth(tcp, target, .03), g["turn"], phase+":lower")
            tcp = self.tcp(side)
        start = self.g[side]
        for u in np.linspace(0, 1, int(round(.25/self.dt))+1)[1:]:
            self.g[side] = start+(g["open"]-start)*u
            self.step(phase+":open")
        self.cartesian(side, self.smooth(tcp, tcp+[0, 0, PRE], .1), g["turn"], phase+":retreat")

    def contact_point(self, side):
        from topogym.planning.knot_untying.kinematics import CONTACT_IN_TCP_M
        return self.tcp(side)+self.grasps[side]["turn"].apply(CONTACT_IN_TCP_M)

    # ---------- decisions ----------
    def arms_for(self, s_points):
        """Left arm takes the point nearer the left base (-X side)."""
        line = self.line()
        xs = [self.at(line, s)[0] for s in s_points]
        arms = ("left", "right") if xs[0] <= xs[1] else ("right", "left")
        return arms[::-1] if getattr(self, 'motion_options', {}).get('arm_order') == 'swapped' else arms

    def withdraw(self, k, action, cfg):
        anchor_side, pull_side = self.arms_for((action["s_anchor"], action["s_pull"]))
        record = dict(k=k, kind="withdraw", t=self.log[-1]["t"] if self.log else 0., **action,
                      arms=dict(anchor=anchor_side, pull=pull_side), increments=[])
        record["grasps"] = self.grasp((anchor_side, pull_side), (action["s_anchor"], action["s_pull"]), f"d{k}:grasp")
        # The stationary anchor can keep sagging after the pinch as PD tracking
        # settles. Lift the held strand before pulling instead of pressing the
        # fingers into the table. This is a route option, not a command guard.
        anchor_lift = float(cfg.get("anchor_lift_m", 0.))
        record["anchor_lift_m"] = anchor_lift
        if anchor_lift:
            anchor_tcp = self.tcp(anchor_side)
            self.cartesian(anchor_side, self.smooth(anchor_tcp, anchor_tcp+[0, 0, anchor_lift], .03),
                           self.grasps[anchor_side]["turn"], f"d{k}:anchor_lift")
        turn = self.grasps[pull_side]["turn"]
        tcp = self.tcp(pull_side)
        raised = tcp+[0, 0, cfg["lift"]]
        self.cartesian(pull_side, self.smooth(tcp, raised, .03), turn, f"d{k}:lift")
        count0, pulled = len(self.crossings()), 0.
        direction = np.asarray(action["direction"], float)
        if direction.shape == (2,):
            direction = np.r_[direction, 0.]
        origin = raised.copy()
        lateral = np.array([-direction[1], direction[0], 0.])
        lateral /= max(np.linalg.norm(lateral), 1e-12)
        while pulled < self.args.max_pull-1e-9:
            tcp = self.tcp(pull_side)
            increment = min(.05, self.args.max_pull-pulled)
            fraction = (pulled+increment)/self.args.max_pull
            target = origin+(pulled+increment)*direction
            target += np.sin(np.pi*fraction)*(cfg.get('path_lateral_m', 0.)*lateral
                                              +np.array([0., 0., cfg.get('path_arch_m', 0.)]))
            reached = self.cartesian(pull_side, self.smooth(tcp, target, self.args.speed), turn, f"d{k}:pull", allow_partial=True)
            pulled += increment
            count = len(self.crossings())
            span = float(np.linalg.norm(self.contact_point(pull_side)-self.contact_point(anchor_side)))
            record["increments"].append(dict(t=self.log[-1]["t"], pulled_m=round(pulled, 3), crossings=count, band_distance_m=round(span, 3)))
            if not reached:
                record["stopped"] = "pull arm reach limit"
                break
            if count < count0 and not self.args.full_pull:
                break
            if cfg.get('span_ratio') is not None and span >= cfg['span_ratio']*abs(
                    self.grasps[pull_side]["s"]-self.grasps[anchor_side]["s"]):
                record["stopped"] = "optional configured grasp-span budget reached"
                break
        self.release(pull_side, cfg["lift"], f"d{k}:release")
        self.release(anchor_side, 0., f"d{k}:release")
        record["crossings_after"] = len(self.crossings())
        return record

    def straighten(self, k, cfg):
        a, b = self.args.end_offset, self.length-self.args.end_offset
        side_a, side_b = self.arms_for((a, b))
        record = dict(k=k, kind="straighten", t=self.log[-1]["t"] if self.log else 0., arms={str(a): side_a, str(b): side_b},
                      crossings_before=len(self.crossings()), increments=[])
        record["grasps"] = self.grasp((side_a, side_b), (a, b), f"d{k}:grasp_ends")
        heights = {}
        for side in (side_a, side_b):
            tcp = self.tcp(side)
            raised = tcp+[0, 0, cfg.get('spread_lift', .015)]
            heights[side] = float(raised[2])
            self.cartesian(side, self.smooth(tcp, raised, .03), self.grasps[side]["turn"], f"d{k}:lift")
        extra = 0
        for _ in range(60):
            pa, pb = self.contact_point(side_a), self.contact_point(side_b)
            span = float(np.linalg.norm((pb-pa)[:2]))
            count = len(self.crossings())
            record["increments"].append(dict(t=self.log[-1]["t"], span_m=round(span, 3), crossings=count))
            if span >= cfg["straighten"]*self.length or (count == 0 and (extra := extra+1) > cfg.get('clear_spread_steps', 2)):
                break
            if span < 1e-6:
                raise RuntimeError("end-spread grasps coincide in the table plane")
            angle = np.arctan2(pb[1]-pa[1], pb[0]-pa[0])+np.deg2rad(cfg.get('pull_yaw_deg', 0.))
            pitch = np.deg2rad(cfg.get('pull_pitch_deg', 0.))
            axis = np.array([np.cos(angle)*np.cos(pitch), np.sin(angle)*np.cos(pitch), np.sin(pitch)])
            # Both arms move together: interleave their Cartesian targets step by step.
            ta, tb = self.tcp(side_a), self.tcp(side_b)
            target_a, target_b = ta-.025*axis, tb+.025*axis
            heights[side_a] -= .025*axis[2]
            heights[side_b] += .025*axis[2]
            target_a[2], target_b[2] = heights[side_a], heights[side_b]
            path_a, path_b = self.smooth(ta, target_a, self.args.speed), self.smooth(tb, target_b, self.args.speed)
            ok = True
            for index in range(max(len(path_a), len(path_b))):
                qa, qb = path_a[min(index, len(path_a)-1)], path_b[min(index, len(path_b)-1)]
                try:
                    self.q[side_a] = self.solve(side_a, qa, self.grasps[side_a]["turn"])
                    self.q[side_b] = self.solve(side_b, qb, self.grasps[side_b]["turn"])
                except ValueError:
                    ok = False
                    break
                self.step(f"d{k}:spread")
            if not ok:
                record["stopped"] = "reach limit"
                break
        for side in (side_a, side_b):
            self.release(side, cfg.get('spread_lift', .015), f"d{k}:release")
        record["crossings_after"] = len(self.crossings())
        return record

    def rank_translations(self, k, candidates):
        """Order cleanup moves using native clearance; estimates never reject a move.

        Translating the measured rope rigidly at fixed robot poses is only a
        planning estimate. Real grasping, deformation, release and native success
        remain necessary, and every original candidate remains in the search.
        """
        from topogym.evaluation.terminal.clearance import fem_clearance_lower_bound
        from topogym.utils.io import write_json_atomic
        rows, error, tick = [], None, None
        try:
            state = self.world.read_state()
            tick = state['physics_step']
            geometry = state['release_geometry']
            if geometry['schema_version'] not in (2, 3) or not geometry['complete'] or geometry['physics_step'] != tick:
                raise ValueError('Incomplete or stale native release geometry')
            if not len(geometry['robot_bounds_m']):
                raise ValueError('No robot collision geometry to rank against')
            points = np.asarray(state['fem']['rope']['position_m'])
            cells = geometry['fem_elements']['rope']
            required = self.task.final_settling_spec().clearance_m
            indices = self.release_search_colliders(points, cells, geometry, required)
            boxes = np.asarray(geometry['robot_bounds_m'])[indices]
            planes = [geometry['robot_convex_planes_m'][i] for i in indices]
            if not len(indices):
                raise ValueError('No active or contact-failing collider requires translation')
            for candidate in candidates:
                delta = np.array([candidate.get('translate_x_m', 0.), candidate.get('translate_y_m', -.02), 0.])
                distance = fem_clearance_lower_bound(points+delta, cells, boxes, planes, required)
                rows.append(dict(candidate=dict(candidate), predicted_clear=bool(distance >= required),
                                 clearance_lower_bound_m=float(distance), displacement_m=float(np.linalg.norm(delta))))
        except (KeyError, ValueError, AttributeError) as exc:
            error = f'{type(exc).__name__}: {exc}'
            rows = []
        ranked = sorted(rows, key=lambda row: (not row['predicted_clear'],
                        row['displacement_m'] if row['predicted_clear'] else -row['clearance_lower_bound_m']))
        folder = self.args.output/'clearance_plans'
        folder.mkdir(exist_ok=True)
        write_json_atomic(folder/f'd{k}_{time.time_ns()}.json', dict(physics_step=tick, candidates=ranked,
            fallback_error=error, scope='Rigid rope translation at fixed measured robot poses; ranking only, '
            'no candidate rejection or physical/success qualification. Native final clearance is unchanged.'))
        return [row['candidate'] for row in ranked] if ranked else list(candidates)

    @staticmethod
    def release_search_colliders(points, cells, geometry, required):
        """Do not move away from an already permitted fixed-base contact."""
        indices = list(range(len(geometry['robot_bounds_m'])))
        if geometry['schema_version'] == 3:
            from topogym.evaluation.terminal.robot_contact import evaluate_robot_contact
            _, metrics = evaluate_robot_contact({'rope': points}, {'rope': cells}, geometry, required)
            failing = {f['collider'] for f in metrics['robot_contact_failures']}
            indices = [i for i in indices if not geometry['robot_solids'][i]['fixed_to_world'] or i in failing]
        return indices

    def translation_stations(self, cfg):
        """Pair a clearance-limited rope segment with its farther material end.

        Ends alone may drag only slack while the nearby base segment stays put.
        Native filled-volume bounds identify the limiting collider; centerline
        supporting-plane distances then locate a grasp candidate. This changes
        grasp priority only, and never certifies the resulting physical motion.
        """
        ends = (self.args.end_offset, self.length-self.args.end_offset)
        record = dict(mode=cfg.get('translate_grasp', 'ends'), stations_m=list(ends))
        if record['mode'] == 'ends':
            return ends, record
        from topogym.evaluation.terminal.clearance import fem_clearance_lower_bound
        try:
            state = self.world.read_state()
            geometry = state['release_geometry']
            if geometry['schema_version'] not in (2, 3) or not geometry['complete'] or geometry['physics_step'] != state['physics_step']:
                raise ValueError('Incomplete or stale native release geometry')
            boxes = np.asarray(geometry['robot_bounds_m'])
            planes = geometry['robot_convex_planes_m']
            if not len(boxes):
                raise ValueError('No robot collision geometry to select a grasp against')
            points = np.asarray(state['fem']['rope']['position_m'])
            cells = geometry['fem_elements']['rope']
            required = self.task.final_settling_spec().clearance_m
            indices = self.release_search_colliders(points, cells, geometry, required)
            bounds = [fem_clearance_lower_bound(points, cells, boxes[i:i+1], [plane], required)
                      if i in indices else float('inf') for i, plane in enumerate(planes)]
            index = int(np.argmin(bounds))
            if bounds[index] >= required:
                record['fallback'] = 'Current measured robot clearance already satisfied'
                return ends, record
            line = self.line()
            box, plane = boxes[index], np.asarray(planes[index])
            distance = np.linalg.norm(np.maximum(np.maximum(line-box[1], box[0]-line), 0.), axis=1)
            if len(plane):
                distance = np.maximum(distance, (line@plane[:, :3].T+plane[:, 3]).max(axis=1))
            station = float(self.stations[int(np.argmin(distance))])
            local = float(np.clip(station+cfg.get('translate_grasp_offset_m', 0.), 0., self.length))
            partner = max(ends, key=lambda end: abs(end-local))
            stations = (local, partner)
            record.update(stations_m=list(stations), physics_step=state['physics_step'],
                robot_box_index=index, clearance_lower_bound_m=float(bounds[index]),
                limiting_station_m=station, scope='Native volume clearance selects the collider; '
                'centerline supporting-plane distances choose a nearby grasp, not a motion certificate.')
            return stations, record
        except (KeyError, ValueError, AttributeError) as error:
            record['fallback'] = f'{type(error).__name__}: {error}'
            return ends, record

    def arrange(self, k, cfg, mode):
        """Continue after zero crossings with release, placement or rope translation."""
        before = len(self.crossings())
        record = dict(k=k, kind=mode, t=self.session.sim_time_s, crossings_before=before)
        if mode == 'translate':
            stations, record['grasp_selection'] = self.translation_stations(cfg)
            sides = self.arms_for(stations)
            record['grasps'] = self.grasp(sides, stations, f'd{k}:translate:grasp')
            delta = np.array([cfg.get('translate_x_m', 0.), cfg.get('translate_y_m', -.02), 0.])
            record['commanded_translation_m'] = delta.tolist()
            record['translation_arch_m'] = cfg.get('translate_lift_m', .005)
            paths = {side: self.smooth(self.tcp(side), self.tcp(side)+delta, self.args.speed) for side in sides}
            count = max(len(path) for path in paths.values())
            for index in range(count):
                arch = record['translation_arch_m']*np.sin(np.pi*index/max(1, count-1))
                try:
                    targets = {side: self.solve(side, paths[side][min(index, len(paths[side])-1)]+[0., 0., arch],
                                               self.grasps[side]['turn']) for side in sides}
                except ValueError:
                    record['stopped'] = 'translation arm reach limit'
                    break
                # A failed IK for either arm must not execute the other arm alone.
                self.q.update(targets)
                self.step(f'd{k}:translate')
            for side in sides:
                self.release(side, 0., f'd{k}:translate:release')
        elif mode == 'laydown':
            line = self.line()
            high = float(self.stations[int(np.argmax(line[:, 2]))])
            partner = self.args.end_offset if high > self.length/2 else self.length-self.args.end_offset
            sides = self.arms_for((high, partner))
            self.grasp(sides, (high, partner), f'd{k}:laydown')
            for side in sides:
                # release computes the nominal rope-on-table pose itself.
                self.release(side, max(.01, self.tcp(side)[2]-self.task.table_height_m), f'd{k}:laydown')
        elif mode == 'retreat':
            for side in list(self.grasps):
                self.release(side, 0., f'd{k}:release')
            for side in self.q:
                self.g[side] = .038
            for _ in range(int(.3/self.dt)):
                self.step(f'd{k}:open')
            from scipy.spatial.transform import Rotation
            observation = self.robot.observe()
            for side in self.q:
                tcp = self.tcp(side)
                turn = Rotation.from_quat(np.asarray(observation[side]['tcp_orientation_wxyz'])[[1, 2, 3, 0]])
                self.cartesian(side, self.smooth(tcp, tcp+[0, 0, cfg.get('retreat_height', .08)], .05),
                               turn, f'd{k}:retreat', allow_partial=True)
        deadline = self.session.sim_time_s+self.args.settle
        while self.session.sim_time_s < deadline:
            self.step(f'd{k}:arrange_settle')
        record['crossings_after'] = len(self.crossings())
        record['terminal_waited'] = True
        return record

    def carry(self, cfg):
        line = self.line()
        side = "right" if self.at(line, cfg["s"])[0] > -.01 else "left"
        record = dict(k=1, kind="carry_r2", t=0., s=cfg["s"], side=side, crossings_before=len(self.crossings()))
        record["grasps"] = self.grasp((side,), (cfg["s"],), "d1:carry")
        turn = self.grasps[side]["turn"]
        tcp = self.tcp(side)
        self.cartesian(side, self.smooth(tcp, tcp+[0, 0, cfg["lift"]], .03), turn, "d1:lift")
        tcp = self.tcp(side)
        self.cartesian(side, self.smooth(tcp, tcp+[cfg["delta"][0], cfg["delta"][1], 0], self.args.speed), turn, "d1:carry")
        self.release(side, cfg["lift"], "d1:release")
        record["crossings_after"] = len(self.crossings())
        return record

    def run(self):
        from topogym.planning.knot_untying.route_rule import choose, only_local_loops
        cfg = TIERS[self.args.variation]
        try:
            if cfg["kind"] == "carry":
                self.decisions.append(self.carry(cfg))
            else:
                for k in range(1, self.args.max_decisions+1):
                    line = self.line()
                    crossings = self.crossings(line)
                    if not crossings:
                        break
                    if only_local_loops(crossings, self.stations) and not (self.decisions and self.decisions[-1]["kind"] == "straighten"):
                        self.decisions.append(self.straighten(k, cfg))
                    else:
                        action = choose(line, self.stations, crossings, self.length, cfg["hold"], cfg["direction"])
                        self.decisions.append(dict(self.withdraw(k, action, cfg), crossings_before=len(crossings)))
                        if 0 < self.decisions[-1]["crossings_after"] < len(crossings):
                            self.decisions.append(self.straighten(k, cfg))
                    print(json.dumps({x: self.decisions[-1].get(x) for x in ("k", "kind", "crossings_before", "crossings_after", "stopped")}), flush=True)
                    self.dump(partial=True)
            # Settle until the terminal predicate has held for its stable window, or give up.
            deadline = self.session.sim_time_s+self.args.settle
            while self.session.sim_time_s < deadline:
                self.step("final_settle")
        except Solved:
            self.decisions.append(dict(kind="episode_end", t=self.log[-1]["t"], episode_end="success"))
            print("SOLVED at t =", self.log[-1]["t"], flush=True)
        except Exception as error:  # keep the evidence of any failed run
            self.decisions.append(dict(kind="error", error=f"{type(error).__name__}: {error}"))
            print("ERROR", error, flush=True)
        self.dump(partial=False)
        return bool(self.task.result.task_success)

    def save_attempt_evidence(self, output):
        """Keep a rejected prefix and its last committed state before rewind."""
        from topogym.simulator.rollout_simulation.evidence import SegmentEvidence
        from topogym.utils.io import write_json_atomic
        output.mkdir(parents=True, exist_ok=False)
        self.dump(partial=True, output=output)
        folder = output/'last_tick'
        folder.mkdir()
        writer = SegmentEvidence(folder, self.env)
        try:
            record = self.env.tick_record()
            writer.tick(record, segment_id=1)
            write_json_atomic(folder/'scope.json', dict(
                scope='One last committed tick of a rejected attempt; not a complete trajectory capture',
                state=record['state'], **writer.statistics()))
        finally:
            writer.close()

    def dump(self, partial, output=None):
        result = self.task.result
        metrics = {k: v for k, v in result.metrics.items() if isinstance(v, (bool, int, float, str))}
        report = dict(variation=self.args.variation, instance=str(self.args.instance), instance_identity=self.identity, robot="aloha",
                      grasp_assist=self.env.config.grasp_assist.model, simulator=dict(
                          physics_dt_s=self.env.config.physics_dt_s, substeps=self.env.config.solver_substeps,
                          control_decimation=self.env.config.control_decimation),
                      close_width_m=self.args.close, build_s=self.build_s, wall_s=time.time()-self.started,
                      command_safety=dict(owner='native_session' if self.native_command_guard else 'legacy_oracle_fallback',
                          native_rules=getattr(self.session, 'rules', None),
                          extra_oracle_table_margin_m=None if self.native_command_guard else COMMAND_TABLE_GAP_M),
                      session_status={k: v for k, v in self.session.status().items()},
                      simulated_s=float(self.session.sim_time_s), partial=partial, decisions=self.decisions,
                      terminal_predicate_met=bool(metrics.get("stable_time_s", 0.) >= self.task.config["stable_duration_s"]),
                      env_task_success=bool(result.task_success), goal_complete_flag=bool(self.task.goal_complete),
                      final_metrics=metrics, terminal_metrics=dict(result.metrics))
        out = self.args.output if output is None else output
        from topogym.utils.io import write_json_atomic
        write_json_atomic(out/"report.json", report)
        with (out/"steps.jsonl").open("w") as f:
            for r in self.log:
                f.write(json.dumps(r, default=float)+"\n")
        if not partial and self.owns_session:
            actions = self.session.record_stop()
            self.session.save_trajectory(actions, out/"trajectory.npz", dict(oracle="run_knot_oracle.py", decisions=len(self.decisions)))
        elif self.owns_session:
            from .artifacts import save_recording
            save_recording(self.session, out/"trajectory.partial.npz")
        if self.lines:
            np.savez_compressed(out/"centerlines.npz", t=np.array([t for t, _ in self.lines]),
                                centerline_m=np.stack([line for _, line in self.lines]), station_s_m=self.stations)
