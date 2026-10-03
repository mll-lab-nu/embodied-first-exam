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

TIERS = {  # object-level settings validated 2026-09-30 (docs/develop/tasks/knot_untying_zh.md)
    "knot_untying_easy": dict(kind="carry", s=.224, delta=(-.095, 0.), lift=.025),
    "knot_untying_medium": dict(kind="closed_loop", hold="far", direction="tangent", lift=.015, straighten=.9),
    "knot_untying_hard": dict(kind="closed_loop", hold="far", direction="away", lift=.03, straighten=.9),
}
DT = .025  # control step of the instances (2.5 ms x 10)
PRE = .05  # pregrasp and retreat height above the pinch, m


class Solved(Exception):
    """The episode ended in task success: later steps would not change the scene or the recording."""


def task_dir(variation):
    return ROOT/"tasks"/f"topogym-knot-untying-{variation.removeprefix('knot_untying_')}-i00-privileged"


class Runner:
    def __init__(self, args):
        from .artifacts import load_tooling, instance_identity
        from topogym.planning.knot_untying.kinematics import KnotIK
        self.args, self.started = args, time.time()
        self.identity = instance_identity(args.instance)
        self.session = s = load_tooling(args.variation).Session("knot_untying", instance=str(args.instance))
        s.reset()
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
        ended = s.step(row)
        result = self.task.result
        k = len(self.log)
        row = dict(t=float(s.sim_time_s), physics_steps=int(s.physics_steps), phase=phase, gripper=dict(self.g),
                   stable_time_s=float(result.metrics.get("stable_time_s", 0.)), failure=result.reason if result.terminated else None)
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

    def solve(self, side, p, turn, seed=None):
        q = self.full_q.copy() if seed is None else seed
        q = self.ik.solve(side, (np.asarray(p)+self.bias[side], turn), q)
        self.full_q = q
        return q[self.robot._q_indices[side][:6]]

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
        """Horizontal distance from the centre line at s to the nearest strand more than 40 mm of rope away."""
        p = self.at(line, s)[:2]
        a, b = line[:-1, :2], line[1:, :2]
        far = np.abs(self.stations-s) > .04
        keep = far[:-1] & far[1:]
        ab = b-a
        u = np.clip(((p-a)*ab).sum(1)/np.maximum((ab*ab).sum(1), 1e-12), 0, 1)
        distances = np.linalg.norm(a+ab*u[:, None]-p, axis=1)[keep]
        return float(distances.min()) if len(distances) else float("inf")

    def grasp_site(self, s):
        """(arc, opening width): open the jaws only as wide as the free space beside the rope allows
        (half gap <= clearance - 4 mm radius - 3 mm margin, at most 19 mm); if fewer than 6 mm remain,
        move the grasp toward the rope's middle in 5 mm steps (at most 80 mm)."""
        line = self.line()
        toward = 1. if s < self.length/2 else -1.
        for k in range(17):
            arc = float(np.clip(s+toward*.005*k, .01, self.length-.01))
            half = min(.019, self.clearance(line, arc)-.007)
            if half >= .006:
                return arc, 2*half  # opening width (gap between the pads)
        raise RuntimeError(f"no grasp site with free space within 80 mm of s={s:.3f}")

    def pose(self, side, s, flips=(1, -1)):
        """Vertical pinch over the live rope at s: (tcp, turn, flip, pregrasp joints)."""
        from topogym.planning.knot_untying.kinematics import vertical_pinch
        line = self.line()
        point, tangent = self.at(line, s), (self.at(line, s+.01)-self.at(line, s-.01))[:2]
        errors = []
        for flip in flips:
            tcp, turn = vertical_pinch(point, tangent, flip)
            try:
                pre = self.ik.solve(side, (tcp+[0, 0, PRE], turn), self.full_q.copy())
                self.ik.solve(side, (tcp, turn), pre)
                return tcp, turn, flip, pre[self.robot._q_indices[side][:6]]
            except ValueError as error:
                errors.append(str(error)[:80])
        raise RuntimeError(f"{side} cannot reach s={s:.3f}: {errors}")

    def grasp(self, sides, ss, phase):
        """Both listed arms open, approach, re-aim on the live rope, descend and pinch together."""
        return self.pinch(sides, *self.place(sides, ss, phase), phase)

    def place(self, sides, ss, phase):
        """Open, approach and descend until the open jaws straddle the live rope at the chosen arcs."""
        sites = [self.grasp_site(s) for s in ss]
        ss = [arc for arc, _ in sites]
        opening = {side: cmd for side, (_, cmd) in zip(sides, sites)}
        plans = {side: self.pose(side, s) for side, s in zip(sides, ss)}
        n = int(round(1./self.dt))
        start = {side: self.q[side].copy() for side in sides}
        g0 = {side: self.g[side] for side in sides}
        for k, u in enumerate(np.linspace(0, 1, n+1)[1:]):
            for side in sides:
                self.q[side] = start[side]+(plans[side][3]-start[side])*(10*u**3-15*u**4+6*u**5)
                self.g[side] = g0[side]+(opening[side]-g0[side])*min(1., 4*u)
            self.step(phase+":approach")
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
        record = {}
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
            self.cartesian(side, self.smooth(tcp, tcp-[0, 0, lower], .03), g["turn"], phase+":lower")
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
        return ("left", "right") if xs[0] <= xs[1] else ("right", "left")

    def withdraw(self, k, action, cfg):
        anchor_side, pull_side = self.arms_for((action["s_anchor"], action["s_pull"]))
        record = dict(k=k, kind="withdraw", t=self.log[-1]["t"] if self.log else 0., **action,
                      arms=dict(anchor=anchor_side, pull=pull_side), increments=[])
        record["grasps"] = self.grasp((anchor_side, pull_side), (action["s_anchor"], action["s_pull"]), f"d{k}:grasp")
        turn = self.grasps[pull_side]["turn"]
        tcp = self.tcp(pull_side)
        self.cartesian(pull_side, self.smooth(tcp, tcp+[0, 0, cfg["lift"]], .03), turn, f"d{k}:lift")
        count0, pulled = len(self.crossings()), 0.
        direction = np.r_[action["direction"], 0.]
        while pulled < self.args.max_pull-1e-9:
            tcp = self.tcp(pull_side)
            increment = min(.05, self.args.max_pull-pulled)
            reached = self.cartesian(pull_side, self.smooth(tcp, tcp+increment*direction, self.args.speed), turn, f"d{k}:pull", allow_partial=True)
            pulled += increment
            count = len(self.crossings())
            span = float(np.linalg.norm(self.contact_point(pull_side)-self.contact_point(anchor_side)))
            record["increments"].append(dict(t=self.log[-1]["t"], pulled_m=round(pulled, 3), crossings=count, band_distance_m=round(span, 3)))
            if not reached:
                record["stopped"] = "pull arm reach limit"
                break
            if count < count0 and not self.args.full_pull:
                break
            if span >= .95*abs(self.grasps[pull_side]["s"]-self.grasps[anchor_side]["s"]):
                record["stopped"] = "band distance reached 0.95 of the rope between the grasps"
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
        for side in (side_a, side_b):
            tcp = self.tcp(side)
            self.cartesian(side, self.smooth(tcp, tcp+[0, 0, .015], .03), self.grasps[side]["turn"], f"d{k}:lift")
        extra = 0
        for _ in range(60):
            pa, pb = self.contact_point(side_a), self.contact_point(side_b)
            span = float(np.linalg.norm((pb-pa)[:2]))
            count = len(self.crossings())
            record["increments"].append(dict(t=self.log[-1]["t"], span_m=round(span, 3), crossings=count))
            if span >= min(cfg["straighten"], .95)*self.length or (count == 0 and (extra := extra+1) > 2):
                break
            if span < 1e-6:
                raise RuntimeError("end-spread grasps coincide in the table plane")
            axis = np.r_[(pb-pa)[:2]/span, 0.]
            # Both arms move together: interleave their Cartesian targets step by step.
            ta, tb = self.tcp(side_a), self.tcp(side_b)
            path_a, path_b = self.smooth(ta, ta-.025*axis, self.args.speed), self.smooth(tb, tb+.025*axis, self.args.speed)
            ok = True
            for qa, qb in zip(path_a, path_b):
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
            self.release(side, .015, f"d{k}:release")
        record["crossings_after"] = len(self.crossings())
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

    def dump(self, partial):
        result = self.task.result
        metrics = {k: v for k, v in result.metrics.items() if isinstance(v, (bool, int, float, str))}
        report = dict(variation=self.args.variation, instance=str(self.args.instance), instance_identity=self.identity, robot="aloha",
                      grasp_assist=self.env.config.grasp_assist.model, simulator=dict(
                          physics_dt_s=self.env.config.physics_dt_s, substeps=self.env.config.solver_substeps,
                          control_decimation=self.env.config.control_decimation),
                      close_width_m=self.args.close, build_s=self.build_s, wall_s=time.time()-self.started,
                      session_status={k: v for k, v in self.session.status().items()},
                      simulated_s=float(self.session.sim_time_s), partial=partial, decisions=self.decisions,
                      terminal_predicate_met=bool(metrics.get("stable_time_s", 0.) >= self.task.config["stable_duration_s"]),
                      env_task_success=bool(result.task_success), goal_complete_flag=bool(self.task.goal_complete),
                      final_metrics=metrics)
        out = self.args.output
        from topogym.utils.io import write_json_atomic
        write_json_atomic(out/"report.json", report)
        with (out/"steps.jsonl").open("w") as f:
            for r in self.log:
                f.write(json.dumps(r, default=float)+"\n")
        if not partial:
            actions = self.session.record_stop()
            self.session.save_trajectory(actions, out/"trajectory.npz", dict(oracle="run_knot_oracle.py", decisions=len(self.decisions)))
        else:
            from .artifacts import save_recording
            save_recording(self.session, out/"trajectory.partial.npz")
        if self.lines:
            np.savez_compressed(out/"centerlines.npz", t=np.array([t for t, _ in self.lines]),
                                centerline_m=np.stack([l for _, l in self.lines]), station_s_m=self.stations)

