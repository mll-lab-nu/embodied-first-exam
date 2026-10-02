"""ALOHA executes the knot object-level route in the task Env, choosing each grasp from the live rope.

Literature mapping (see topogym/planning/knot_untying/route_rule.py):
  * node deletion (HULK, Grannen et al. CoRL 2020): pin arm on the far end (v9 remote anchor), pull arm 35 mm
    past the first under-crossing from the nearer end, lifted and pulled away from the crossing in 50 mm
    increments; crossings are recounted after each increment (HULK's re-perception between actions);
  * Reidemeister move (HULK; SGTM 2.0 arXiv 2207.07813): both arms pinch near the ends and pull them apart
    while only local curls remain;
  * easy (two overlaps, one strand over both): R-II move, one arm carries the over strand across.
Grasps are vertical pinches by friction only (no grasp assist), jaws across the rope. The task terminal
predicate (no projected crossing/overlap, on table, quiet, released, robot clear, stable 0.5 s) is read
from the task result; knot_untying has goal_complete=False, so the Env itself never raises task_success.

Usage: .venv-gs121-nyx/bin/python scripts/run_knot_robot_route.py --variation knot_untying_medium --output <new dir>
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TIERS = {  # validated object-level settings (runs/test_results/knot_object_route_20260930)
    "knot_untying_easy": dict(kind="carry", s=.224, delta=(-.095, 0.), lift=.025),
    "knot_untying_medium": dict(kind="closed_loop", hold="far", direction="tangent", lift=.015, straighten=.9),
    "knot_untying_hard": dict(kind="closed_loop", hold="far", direction="away", lift=.03, straighten=.9),
}
DT = .025  # control step
PRE = .05  # pregrasp and retreat height above the pinch, m


class Runner:
    def __init__(self, args):
        from topogym.simulator.config import SimulatorConfig
        from topogym.simulator.env import Env
        from topogym.planning.knot_untying.kinematics import KnotIK
        self.args, self.started = args, time.time()
        self.env = Env(SimulatorConfig(task_id="knot_untying", robot_id="aloha", variation_id=args.variation,
                                       compute_backend="cuda", enable_rgb=False, enable_depth=False,
                                       enable_privileged=True, control_mode="JOINT_ABS", max_physics_steps=None,
                                       physics_dt_s=args.physics_dt, solver_substeps=args.substeps,
                                       control_decimation=args.decimation, work_dir=args.output/"episode", seed=0))
        self.env.reset(seed=0)
        self.build_s = time.time()-self.started
        self.task, self.world, self.robot = self.env._task, self.env._world, self.env._robot
        self.ik = KnotIK(self.world, self.robot, self.task.table_height_m)
        self.home = self.ik.seed.copy()
        self.q = {s: self.home[self.robot._q_indices[s][:6]].copy() for s in ("left", "right")}
        self.g = {s: float(self.home[self.robot._q_indices[s][6]]) for s in ("left", "right")}
        idx, material = self.task.centerline_map
        self.stations = material[idx].mean(axis=1) if material[idx].ndim == 2 else material[idx]
        self.length = float(self.stations[-1]-self.stations[0])
        self.log, self.lines, self.decisions, self.grasps = [], [], [], {}
        self.full_q = self.home.copy()
        # Joint PD tracking leaves a few mm of TCP error at rest: every Cartesian target is shifted
        # by a per-arm bias learned while holding still before a pinch.
        self.bias = {s: np.zeros(3) for s in ("left", "right")}

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
        self.env.step({s: {"joint_position_rad": self.q[s].tolist(), "gripper_position_m": self.g[s]} for s in self.q})
        self.world.scene.sim.fem_solver._ckpt.clear()  # Genesis keeps one FEM copy per substep otherwise.
        result = self.task.result
        k = len(self.log)
        row = dict(t=round((k+1)*DT, 3), phase=phase, gripper=dict(self.g),
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
        if result.terminated and result.reason:
            raise RuntimeError(f"task ended: {result.reason}")

    def solve(self, side, p, turn, seed=None):
        q = self.full_q.copy() if seed is None else seed
        q = self.ik.solve(side, (np.asarray(p)+self.bias[side], turn), q)
        self.full_q = q
        return q[self.robot._q_indices[side][:6]]

    def cartesian(self, side, targets, turn, phase):
        """TCP through the given points, one per control step; returns False when IK fails (reach limit)."""
        for p in targets:
            try:
                self.q[side] = self.solve(side, p, turn)
            except ValueError:
                return False
            self.step(phase)
        return True

    def smooth(self, a, b, speed):
        n = max(2, int(np.ceil(1.5*np.linalg.norm(b-a)/speed/DT)))
        u = np.linspace(0, 1, n+1)[1:, None]
        return a+(b-a)*(3*u**2-2*u**3)

    # ---------- grasp primitives ----------
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
        plans = {side: self.pose(side, s) for side, s in zip(sides, ss)}
        n = int(round(1./DT))
        start = {side: self.q[side].copy() for side in sides}
        g0 = {side: self.g[side] for side in sides}
        for k, u in enumerate(np.linspace(0, 1, n+1)[1:]):
            for side in sides:
                self.q[side] = start[side]+(plans[side][3]-start[side])*(10*u**3-15*u**4+6*u**5)
                self.g[side] = g0[side]+(self.args.open-g0[side])*min(1., 4*u)
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
        for u in np.linspace(0, 1, int(round(.4/DT))+1)[1:]:
            for side in sides:
                self.g[side] = self.args.open+(self.args.close-self.args.open)*u
            self.step(phase+":close")
        for _ in range(10):
            self.step(phase+":squeeze")
        out = []
        for side, s in zip(sides, ss):
            tcp, turn, flip, _ = plans[side]
            self.grasps[side] = dict(s=s, turn=turn, tcp=tcp.copy(), flip=flip)
            out.append(dict(side=side, s=s, flip=flip, tcp=tcp.round(4).tolist(), placement=record))
        return out

    def converge(self, sides, targets, phase, tolerance=.002, limit_s=4.):
        """Wait until the arms settle, add the remaining TCP error to their bias, repeat until within tolerance.

        One-shot corrections after settling (not a running integral): the IPC-coupled arm responds slowly,
        and an integral would overshoot the fingers into the rope and table.
        """
        previous = {side: self.tcp(side) for side in sides}
        for _ in range(int(limit_s/DT)):
            self.step(phase)
            now = {side: self.tcp(side) for side in sides}
            settled = all(np.linalg.norm(now[side]-previous[side])/DT < .003 for side in sides)
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
        for u in np.linspace(0, 1, int(round(.25/DT))+1)[1:]:
            self.g[side] = start+(self.args.open-start)*u
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
            reached = self.cartesian(pull_side, self.smooth(tcp, tcp+.05*direction, self.args.speed), turn, f"d{k}:pull")
            pulled += .05
            count = len(self.crossings())
            span = float(np.linalg.norm(self.contact_point(pull_side)-self.contact_point(anchor_side)))
            record["increments"].append(dict(t=self.log[-1]["t"], pulled_m=round(pulled, 3), crossings=count, band_distance_m=round(span, 3)))
            if not reached:
                record["stopped"] = "pull arm reach limit"
                break
            if count < count0:
                break
            if span >= .95*abs(action["s_pull"]-action["s_anchor"]):
                record["stopped"] = "band distance reached 0.95 of the rope between the grasps"
                break
        self.release(pull_side, cfg["lift"], f"d{k}:release")
        self.release(anchor_side, 0., f"d{k}:release")
        record["crossings_after"] = len(self.crossings())
        return record

    def straighten(self, k, cfg):
        a, b = .015, self.length-.015
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
            axis = np.r_[(pb-pa)[:2]/np.linalg.norm((pb-pa)[:2]), 0.]
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
        from topogym.planning.knot_untying.route_rule import choose  # noqa: F401 (same package, for provenance)
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
        for _ in range(int(1./DT)):
            self.step("settle_spawn")  # same 1 s relaxation the object-level runs used before the first grasp
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
            deadline = self.log[-1]["t"]+self.args.settle
            while self.log[-1]["t"] < deadline:
                self.step("final_settle")
                if self.log[-1]["stable_time_s"] >= self.task.config["stable_duration_s"]:
                    break
        except Exception as error:  # keep the evidence of any failed run
            self.decisions.append(dict(kind="error", error=f"{type(error).__name__}: {error}"))
            print("ERROR", error, flush=True)
        self.dump(partial=False)

    def dump(self, partial):
        result = self.task.result
        metrics = {k: v for k, v in result.metrics.items() if isinstance(v, (bool, int, float, str))}
        report = dict(variation=self.args.variation, robot="aloha", grasp="friction only (grasp_assist none)",
                      physics_dt_s=self.args.physics_dt, substeps=self.args.substeps, control_decimation=self.args.decimation,
                      close_cmd=self.args.close, open_cmd=self.args.open, build_s=self.build_s, wall_s=time.time()-self.started,
                      simulated_s=self.log[-1]["t"] if self.log else 0., partial=partial, decisions=self.decisions,
                      terminal_predicate_met=bool(metrics.get("stable_time_s", 0.) >= self.task.config["stable_duration_s"]),
                      env_task_success=bool(result.task_success), goal_complete_flag=bool(self.task.goal_complete),
                      final_metrics=metrics)
        out = self.args.output
        (out/"report.json").write_text(json.dumps(report, indent=1, default=float)+"\n")
        with (out/"steps.jsonl").open("w") as f:
            for r in self.log:
                f.write(json.dumps(r, default=float)+"\n")
        if self.lines:
            np.savez_compressed(out/"centerlines.npz", t=np.array([t for t, _ in self.lines]),
                                centerline_m=np.stack([l for _, l in self.lines]), station_s_m=self.stations)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variation", choices=sorted(TIERS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--physics-dt", type=float, default=.025)
    parser.add_argument("--substeps", type=int, default=40)
    parser.add_argument("--decimation", type=int, default=1)
    parser.add_argument("--close", type=float, default=.010, help="native gripper command when pinching the rope")
    parser.add_argument("--open", type=float, default=.027, help="native gripper command before a grasp (38 mm gap)")
    parser.add_argument("--speed", type=float, default=.04, help="average pull speed, m/s")
    parser.add_argument("--max-pull", type=float, default=.6)
    parser.add_argument("--max-decisions", type=int, default=8)
    parser.add_argument("--settle", type=float, default=10., help="max seconds to wait for the stable terminal window")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    Runner(args).run()


if __name__ == "__main__":
    main()
