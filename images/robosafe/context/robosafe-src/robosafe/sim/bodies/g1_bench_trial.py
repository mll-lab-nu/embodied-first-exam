"""The gliding G1's hands at a counter: one arm picks an ordinary thing up from a 0.90 m counter and puts it down
somewhere else on it, by a scripted controller written here.

    python -m robosafe.sim.bodies.g1_bench_trial -n 20 --out build/g1/bench_trial.json
    python -m robosafe.sim.bodies.g1_bench_trial -n 2 --pictures build/g1/trial      # frames of the first trial of each thing

This is not the bench's motion code (`robosafe.sim.skills`, `actions`), which needs a `World`; it is the least that
tells whether this body can do the work: joint-space interpolation between postures, a Jacobian inverse kinematics
(`g1_kin`) followed along straight lines, and the grasp assist as the bench has it: when the fingers have closed and
both pads touch the thing (or, for a thing too thin for that, the pinch point is inside its bounding box), the thing
is welded to the hand in the pose it has, and its weight is compensated like the arm's own; letting go removes the
weld. The things are the bench's own generated props (a food can, a mug, a bottle, a box, a spoon), taken by the grasps
their metadata names (`meta["grasps"]`): from above where the whole way has a solution, else from the side.

A trial succeeds when the thing ends within 3 cm of where it was to go, standing as it stood (tilted less than 15
degrees), on the counter and out of the hand, and nothing else failed on the way.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from robosafe.sim import props as _props

from . import g1_glide as G
from . import g1_kin as K
from . import gripper_parallel as _gripper

COUNTER = {"top": 0.90, "depth": 0.60, "width": 1.40}
STAND_OFF = 0.15                    # m: the counter's front edge ahead of the pelvis axis (the toes are 0.125 m ahead of it)
CONTROL_STEPS = 10                  # 0.02 s per control row, as on the bench
# the things: prop kind and parameters. Each is taken by the first of its own grasps (`meta["grasps"]`: those from
# above first, then those from the side) for which the whole way, there and to the goal, has a solution.
THINGS = {
    "can": ("food_can", {}),
    "mug": ("mug", {}),
    "bottle": ("bottle", {"preset": "water"}),
    "box": ("block", {"size": [0.06, 0.045, 0.09], "mass": 0.15}),
    "spoon": ("spoon", {}),
}
# where things stand and are put (m, the robot's frame, the left hand's side): 5 to 19 cm onto the counter
AREA = {"depth": (0.05, 0.19), "y": (0.04, 0.28)}
LIFT = 0.06                         # m: how far a thing is raised before it is carried across
ABOVE = 0.07                        # m: where a hand that comes from above starts its descent
VEL = np.array([1.5, 1.5, 1.5, 1.5, 2.0, 2.0, 2.0])     # rad/s, the bench's planned limits
ACC = np.array([4.0, 4.0, 4.0, 4.0, 6.0, 6.0, 6.0])


class Failed(Exception):
    pass


class Trial:
    def __init__(self, thing: str, start, goal, yaw: float, postures: dict, side: str = "left", cameras: bool = False):
        self.thing, self.side = thing, side
        self.start, self.goal, self.yaw = np.asarray(start, dtype=np.float64), np.asarray(goal, dtype=np.float64), float(yaw)
        kind, params = THINGS[thing]
        prop = _props.build(kind, params)
        self.meta = prop.meta
        top = COUNTER["top"]

        def extend(s):
            wb = s.worldbody
            s.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                          rgb1=[0.86, 0.89, 0.93], rgb2=[0.62, 0.66, 0.72], width=128, height=768)
            wb.add_geom(name="counter", type=mujoco.mjtGeom.mjGEOM_BOX, size=[COUNTER["depth"] / 2, COUNTER["width"] / 2, top / 2],
                        pos=[STAND_OFF + COUNTER["depth"] / 2, 0, top / 2], rgba=[0.80, 0.78, 0.74, 1], friction=[0.8, 0.005, 0.0001],
                        solref=[float(v) for v in _props.SOLREF.split()], solimp=[float(v) for v in _props.SOLIMP.split()])
            child = mujoco.MjSpec.from_file(prop.path) if prop.path else mujoco.MjSpec.from_string(prop.xml)
            root = list(child.worldbody.bodies)[0].name
            frame = wb.add_frame(pos=[self.start[0], self.start[1], top + 0.001], quat=[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)])
            s.attach(child, frame=frame, prefix="thing/")
            s.body("thing/" + root).add_freejoint(name="thing/free")
            eq = s.add_equality(name="grasp", type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY,
                                name1=f"{side}_gripper/palm", name2="thing/" + root, active=False)
            eq.solref = [0.004, 1.0]
            self._root = "thing/" + root
            if cameras:
                for name, pos, target in (("view", [-0.9, -1.3, 1.75], [0.35, 0.1, 0.95]), ("view_side", [0.4, -1.5, 1.15], [0.4, 0.0, 0.95])):
                    wb.add_camera(name=name, pos=pos, quat=G._look_at(pos, target), fovy=45.0)

        self.m, _ = G.build(extend=extend)
        self.ix = G.index(self.m)
        self.d = mujoco.MjData(self.m)
        self.arm = self.ix["arms"][side]
        self.other = "right" if side == "left" else "left"
        self.postures = {k: np.array(v if side == "left" else G.mirror(v)) for k, v in postures.items()}
        rest = postures["rest"]
        G.set_posture(self.m, self.d, self.ix, left=rest, right=G.mirror(rest))
        mujoco.mj_forward(self.m, self.d)
        # the planner's own copy of the model, in which the robot's shapes count as touching from 5 mm away
        self.plan_m, _ = G.build(extend=extend)
        K.set_margin(self.plan_m, G.index(self.plan_m), 0.005)
        self.chain = K.Chain(self.plan_m, G.index(self.plan_m), side)
        self.body = self.m.body(self._root).id
        self.weld = self.m.equality("grasp").id
        self.bodies = [b for b in range(self.m.nbody) if self._under(b, self.body)]
        self.geoms = {g for g in range(self.m.ngeom) if int(self.m.geom_bodyid[g]) in self.bodies}
        self.lead = np.array([-self.m.actuator_biasprm[a][2] / self.m.actuator_gainprm[a][0] for a in self.arm["act"]])
        self.q_cmd = self.d.qpos[self.arm["q"]].copy()
        self.grip = 0.0
        self.held = False
        self.log: list = []
        self.frames: list = []
        self._renderer = None
        self._cameras = cameras

    def _under(self, b: int, root: int) -> bool:
        while b not in (0, root):
            b = int(self.m.body_parentid[b])
        return b == root

    # ---- the simulation -----------------------------------------------------------------------------------------------------
    def tick(self, q_target, qd_target=None) -> None:
        d = self.d
        d.ctrl[self.arm["act"]] = q_target + (self.lead * qd_target if qd_target is not None else 0.0)
        d.ctrl[self.arm["grip_act"]] = _gripper.ctrl_of(self.grip)
        for _ in range(CONTROL_STEPS):
            mujoco.mj_step(self.m, d)
        self.q_cmd = np.asarray(q_target, dtype=np.float64).copy()
        if not np.all(np.isfinite(d.qpos)):
            raise Failed("unstable")

    def wait(self, seconds: float) -> None:
        for _ in range(int(round(seconds / (CONTROL_STEPS * self.m.opt.timestep)))):
            self.tick(self.q_cmd)

    def move_joints(self, q_goal, what: str = "move") -> None:
        """To a posture on free straight lines in joint space (`g1_kin.find_path` on the planner's copy)."""
        self.plan_sync()
        path = K.find_path(self.chain, self.q_cmd.copy(), q_goal, np.random.default_rng(0), ignore_bodies=[self._root] if self.held else [])
        if path is None:
            raise Failed(f"path_blocked:{what}")
        for q in path[1:]:
            self._joint_line(q)

    def _joint_line(self, q_goal, scale: float = 1.0) -> None:
        """A straight line in joint space, every joint in step, within the velocity and acceleration limits."""
        q0, q1 = self.q_cmd.copy(), np.asarray(q_goal, dtype=np.float64)
        dq = q1 - q0
        if np.max(np.abs(dq)) < 1e-5:
            return
        # the slowest joint sets the time of a smooth (cosine) ramp: peak speed pi/2 * d/T, peak acceleration pi^2/2 * d/T^2
        T = max(float(np.max(np.abs(dq) * (math.pi / 2) / (VEL * scale))), float(np.max(np.sqrt(np.abs(dq) * (math.pi ** 2 / 2) / (ACC * scale)))), 0.1)
        dt = CONTROL_STEPS * self.m.opt.timestep
        n = int(math.ceil(T / dt))
        for k in range(1, n + 1):
            f = 0.5 - 0.5 * math.cos(math.pi * k / n)
            fd = 0.5 * math.pi / (n * dt) * math.sin(math.pi * k / n)
            self.tick(q0 + f * dq, fd * dq)
        self.settle()

    def settle(self, tol: float = 0.01, seconds: float = 1.0) -> None:
        for _ in range(int(seconds / (CONTROL_STEPS * self.m.opt.timestep))):
            if float(np.max(np.abs(self.d.qpos[self.arm["q"]] - self.q_cmd))) < tol:
                return
            self.tick(self.q_cmd)
        raise Failed("not_reached")

    def plan_sync(self) -> None:
        """Put the planner's copy where the simulation is (same model, same order of joints)."""
        self.chain.d.qpos[:] = self.d.qpos
        mujoco.mj_kinematics(self.plan_m, self.chain.d)
        mujoco.mj_comPos(self.plan_m, self.chain.d)

    def tcp(self):
        s = self.arm["pinch"]
        return self.d.site_xpos[s].copy(), self.d.site_xmat[s].reshape(3, 3).copy()

    def line(self, q_start, p_from, p_to, rot, name: str):
        """Joint postures every 5 mm of a straight line of the pinch point, each solved from the one before, the hand's
        frame held at `rot`. Raises `Failed` where the line has no solution or runs into something (the robot itself
        or the counter; the hand may come nearer than the planner's 5 mm to the counter it works on, not into it)."""
        n = max(1, int(math.ceil(float(np.linalg.norm(p_to - p_from)) / 0.005)))
        way, q = [], np.asarray(q_start, dtype=np.float64)
        for k in range(1, n + 1):
            q = self.chain.solve(p_from + (p_to - p_from) * k / n, rot=rot, seed=q, iters=60)
            if q is None:
                raise Failed(f"ik:{name}")
            for a, b, dist in self.chain.touching(q, ignore_bodies=[self._root]):
                if {a, b} == {f"{self.side}_hand", "counter"} and dist > 0.0005:
                    continue
                raise Failed(f"path_blocked:{name}")
            way.append(q)
        return way

    def follow(self, way, speed: float = 0.10) -> None:
        """Follow postures that are 5 mm of the pinch point apart, at `speed` m/s."""
        dt = CONTROL_STEPS * self.m.opt.timestep
        per = max(1, int(round(0.005 / speed / dt)))
        prev = self.q_cmd.copy()
        for q in way:
            for j in range(1, per + 1):
                self.tick(prev + (q - prev) * j / per, (q - prev) / (per * dt))
            prev = q
        self.settle()

    # ---- the hand -----------------------------------------------------------------------------------------------------------
    def pads_touching(self) -> tuple:
        left = right = False
        for c in self.d.contact[:self.d.ncon]:
            pair = (int(c.geom1), int(c.geom2))
            if pair[0] in self.geoms or pair[1] in self.geoms:
                left |= self.arm["pads"]["left"] in pair
                right |= self.arm["pads"]["right"] in pair
        return left, right

    def opening(self) -> float:
        return _gripper.free_distance(self.m, self.d, self.arm["prefix"])

    def set_grip(self, target: float, seconds: float = 1.0) -> None:
        g0 = self.grip
        n = int(round(seconds / (CONTROL_STEPS * self.m.opt.timestep)))
        for k in range(1, n + 1):
            self.grip = g0 + (target - g0) * k / n
            self.tick(self.q_cmd)
        self.wait(0.3)

    def attach(self) -> bool:
        """The grasp assist: weld the thing to the hand in the pose it has now, if the hand has it."""
        left, right = self.pads_touching()
        if not (left and right):
            p, _ = self.tcp()
            lo, hi = self.box()
            if not (np.all(p >= lo - 0.006) and np.all(p <= hi + 0.006)):
                return False
        m, d = self.m, self.d
        palm = self.arm["palm"]
        rot = d.xmat[palm].reshape(3, 3)
        rel_p = rot.T @ (d.xpos[self.body] - d.xpos[palm])
        rel_q = np.zeros(4)
        neg = np.zeros(4)
        mujoco.mju_negQuat(neg, d.xquat[palm])
        mujoco.mju_mulQuat(rel_q, neg, d.xquat[self.body])
        m.eq_data[self.weld, 0:3] = 0.0
        m.eq_data[self.weld, 3:6] = rel_p
        m.eq_data[self.weld, 6:10] = rel_q
        m.eq_data[self.weld, 10] = 1.0
        d.eq_active[self.weld] = 1
        m.body_gravcomp[self.bodies] = 1.0           # the controller is told its payload
        self.held = True
        return True

    def detach(self) -> None:
        self.d.eq_active[self.weld] = 0
        self.m.body_gravcomp[self.bodies] = 0.0
        self.held = False

    def box(self):
        """The thing's bounding box in the world, from its shapes' own boxes."""
        m, d = self.m, self.d
        pts = []
        for g in self.geoms:
            if int(m.geom_group[g]) > 3:
                continue
            aabb, rot = m.geom_aabb[g], d.geom_xmat[g].reshape(3, 3)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        pts.append(d.geom_xpos[g] + rot @ (aabb[:3] + aabb[3:] * np.array([sx, sy, sz])))
        pts = np.array(pts)
        return pts.min(0), pts.max(0)

    def box_in_body(self):
        """The thing's bounding box in its own frame."""
        m, d = self.m, self.d
        pos, rot = self.thing_pose()
        pts = []
        for g in self.geoms:
            if int(m.geom_group[g]) > 3:
                continue
            aabb, grot = m.geom_aabb[g], d.geom_xmat[g].reshape(3, 3)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        pts.append(rot.T @ (d.geom_xpos[g] + grot @ (aabb[:3] + aabb[3:] * np.array([sx, sy, sz])) - pos))
        pts = np.array(pts)
        return pts.min(0), pts.max(0)

    def thing_pose(self):
        return self.d.xpos[self.body].copy(), self.d.xmat[self.body].reshape(3, 3).copy()

    # ---- the grasp ----------------------------------------------------------------------------------------------------------
    def grasps(self) -> list:
        """The thing's grasps in the world: those from above, then those from the side. Each: the pinch point, the
        direction the hand points in, the closing directions to try, the width between the pads."""
        pos, rot = self.thing_pose()
        lo, hi = self.box()
        tips = COUNTER["top"] + _gripper.DIMS.tip_reach + 0.002          # the fingertips stay 2 mm above the counter
        tops, sides = [], []
        for g in self.meta.get("grasps", []):
            r = np.zeros(9)
            mujoco.mju_quat2Mat(r, np.array(g.get("quat", [1.0, 0, 0, 0]), dtype=np.float64))
            p = pos + rot @ np.array(g["pos"], dtype=np.float64)
            y = rot @ r.reshape(3, 3)[:, 1]
            if g["type"] == "top":
                p[2] = max(p[2], tips)
                tops.append({"name": g["name"], "type": "top", "pos": p, "points": np.array([0.0, 0.0, -1.0]), "closings": (y, -y), "width": float(g["width"])})
            elif g["name"] == "body":                # a round body from the side, the hand level: straight ahead first,
                inward = -1.0 if self.side == "left" else 1.0       # then turned towards the middle of the robot, then away from it
                for deg in (0.0, 30.0, 60.0, 90.0, -30.0):
                    a = math.radians(deg) * inward
                    z = np.array([math.cos(a), math.sin(a), 0.0])
                    y = np.array([-math.sin(a), math.cos(a), 0.0])
                    sides.append({"name": f"{g['name']}@{deg:.0f}", "type": "side", "pos": p, "points": z, "closings": (y, -y), "width": float(g["width"])})
        if not tops and not sides:                   # a plain box: from above across its narrower side, 3 cm below its top
            ext = self.box_in_body()
            sx, sy = float(ext[1][0] - ext[0][0]), float(ext[1][1] - ext[0][1])
            y = rot[:, 0] if sx <= sy else rot[:, 1]
            tops.append({"name": "across", "type": "top", "pos": np.array([pos[0], pos[1], max(hi[2] - 0.03, tips)]),
                         "points": np.array([0.0, 0.0, -1.0]), "closings": (y, -y), "width": min(sx, sy)})
        # of several grasps from above (the points of a rim), the one nearest the robot first
        tops.sort(key=lambda g: float(g["pos"][0]))
        return [g for g in tops + sides if g["width"] <= _gripper.DIMS.opening - 0.004]

    def plan(self, g: dict, p0) -> dict | None:
        """The whole way with one grasp as joint postures: a posture before it, then straight lines of the pinch point
        to the grasp, up, across to over the goal, down, and away. None if some part has no solution or is blocked."""
        back = g["width"] / 2.0 + _gripper.DIMS.tip_reach + 0.012
        retreat = np.array([0.0, 0.0, ABOVE]) if g["type"] == "top" else -back * g["points"]
        shift = np.array([self.goal[0] - p0[0], self.goal[1] - p0[1], 0.0])
        up = np.array([0.0, 0.0, LIFT])
        points = {"before": g["pos"] + retreat, "grasp": g["pos"], "lifted": g["pos"] + up, "over": g["pos"] + shift + up,
                  "down": g["pos"] + shift + np.array([0.0, 0.0, 0.004])}
        points["withdrawn"] = points["down"] + retreat
        named = ("ready",) if g["type"] == "top" else ("ready_side_low", "ready_side")
        self.plan_sync()
        why = "ik:before"
        order = ("before", "grasp", "lifted", "over", "down", "withdrawn")
        for closing in g["closings"]:
            rot = K.frame(g["points"], closing)
            seeds = [self.postures[n] for n in named] + self.library().seeds(points["before"], tuple(g["points"]), tuple(np.round(closing, 6)), k=8, within=0.15)
            for seed in seeds:
                q = self.chain.solve(points["before"], rot=rot, seed=seed, iters=150)
                if q is None:
                    continue
                if not self.chain.free(q):
                    why = "path_blocked:before"
                    continue
                try:
                    lines = {}
                    for a, b in zip(order, order[1:]):
                        lines[b] = self.line(q, points[a], points[b], rot, b)
                        q = lines[b][-1]
                except Failed as e:
                    why = str(e)
                    continue
                return {"grasp": g, "rot": rot, "points": points, "lines": lines, "q_before": self._first(points["before"], rot, seed)}
        self._why = why
        return None

    def _first(self, pos, rot, seed):
        return self.chain.solve(pos, rot=rot, seed=seed, iters=150)

    _LIBRARY = None

    def library(self):
        """Random postures of the arm with where they put the hand, as seeds (made once per process and side)."""
        from .g1_measure import Library
        key = self.side
        if Trial._LIBRARY is None or Trial._LIBRARY[0] != key:
            Trial._LIBRARY = (key, Library(self.chain, 150000, np.random.default_rng(11)))
            self.plan_sync()
        return Trial._LIBRARY[1]

    # ---- the task -----------------------------------------------------------------------------------------------------------
    def run(self) -> dict:
        res = {"thing": self.thing, "start": [round(float(v), 3) for v in self.start], "goal": [round(float(v), 3) for v in self.goal],
               "yaw_deg": round(math.degrees(self.yaw), 1), "ok": False, "reason": "", "step": ""}
        step = "settle"
        try:
            self.wait(0.5)
            p0, r0 = self.thing_pose()
            up0 = r0[:, 2].copy()
            self.snap("start")
            step = "plan"
            plan, tried = None, []
            for g in self.grasps():
                self._why = ""
                plan = self.plan(g, p0)
                tried.append(f"{g['name']}: {'ok' if plan else self._why}")
                if plan:
                    break
            res["grasps_tried"] = tried
            if plan is None:
                raise Failed(tried[-1].split(": ", 1)[1] if tried else "no_grasp_fits")
            g = plan["grasp"]
            res["grasp"], res["grasp_type"] = g["name"], g["type"]
            step = "before"
            self.move_joints(plan["q_before"], "before")
            step = "approach"
            self.follow(plan["lines"]["grasp"], 0.08)
            self.snap("at_grasp")
            step = "close"
            self.set_grip(_gripper.TARGET_CLOSED, 1.2)
            res["opening_closed_mm"] = round(self.opening() * 1e3, 1)
            res["pads_touching"] = list(self.pads_touching())
            if not self.attach():
                raise Failed("nothing_grasped")
            step = "lift"
            self.follow(plan["lines"]["lifted"], 0.08)
            self.snap("lifted")
            step = "across"
            self.follow(plan["lines"]["over"], 0.12)
            step = "lower"
            self.follow(plan["lines"]["down"], 0.05)
            step = "release"
            self.detach()
            self.set_grip(0.0, 0.8)
            self.snap("released")
            step = "withdraw"
            self.follow(plan["lines"]["withdrawn"], 0.10)
            step = "home"
            self.move_joints(self.postures["rest"], "home")
            self.wait(1.0)
            self.snap("end")
            step = "judge"
            p1, r1 = self.thing_pose()
            off = float(np.hypot(p1[0] - self.goal[0], p1[1] - self.goal[1]))
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(r1[:, 2] @ up0)))))
            res.update({"off_goal_mm": round(off * 1e3, 1), "tilt_deg": round(tilt, 1), "height_change_mm": round(float(p1[2] - p0[2]) * 1e3, 1)})
            if off > 0.03:
                raise Failed("off_goal")
            if tilt > 15.0:
                raise Failed("fell_over")
            if abs(p1[2] - p0[2]) > 0.01:
                raise Failed("not_on_the_counter")
            res["ok"] = True
        except Failed as e:
            res["reason"] = str(e)
        res["step"] = step if not res["ok"] else "done"
        res["robot_seconds"] = round(float(self.d.time), 1)
        return res

    # ---- pictures -----------------------------------------------------------------------------------------------------------
    def snap(self, tag: str) -> None:
        if not self._cameras:
            return
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.m, 360, 480)
        tiles = []
        for cam in ("view", "view_side", "head", f"wrist_{self.side}"):
            self._renderer.update_scene(self.d, camera=cam)
            tiles.append(self._renderer.render().copy())
        self.frames.append((tag, np.concatenate(tiles, axis=1)))

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()


def placements(rng: np.random.Generator, n: int) -> list:
    """`n` random starts, goals at least 12 cm from them, and turns about the vertical."""
    out = []
    while len(out) < n:
        a = np.array([STAND_OFF + rng.uniform(*AREA["depth"]), rng.uniform(*AREA["y"])])
        b = np.array([STAND_OFF + rng.uniform(*AREA["depth"]), rng.uniform(*AREA["y"])])
        if np.linalg.norm(a - b) >= 0.12:
            out.append((a, b, float(rng.uniform(-math.pi, math.pi))))
    return out


def main() -> None:
    from .g1_measure import POSTURES
    ap = argparse.ArgumentParser(description="One-arm pick and place at a 0.90 m counter by the gliding G1 (scripted).")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--things", nargs="*", default=sorted(THINGS))
    ap.add_argument("--side", default="left", choices=G.SIDES)
    ap.add_argument("--out", type=Path, default=Path("build/g1/bench_trial.json"))
    ap.add_argument("--pictures", type=Path, default=None)
    args = ap.parse_args()
    results = []
    for thing in args.things:
        rng = np.random.default_rng([args.seed, sorted(THINGS).index(thing)])
        for i, (start, goal, yaw) in enumerate(placements(rng, args.n)):
            if args.side == "right":
                start, goal = start * np.array([1.0, -1.0]), goal * np.array([1.0, -1.0])
            t = Trial(thing, start, goal, yaw, POSTURES, side=args.side, cameras=bool(args.pictures) and i == 0)
            r = t.run()
            r["trial"] = i
            results.append(r)
            print(json.dumps(r), flush=True)
            if t.frames:
                from PIL import Image
                args.pictures.mkdir(parents=True, exist_ok=True)
                Image.fromarray(np.concatenate([f for _, f in t.frames], axis=0)).save(args.pictures / f"{thing}_{args.side}.png")
            t.close()
    summary = {}
    for thing in args.things:
        rs = [r for r in results if r["thing"] == thing]
        reasons: dict = {}
        for r in rs:
            if not r["ok"]:
                key = f"{r['reason']} ({r['step']})"
                reasons[key] = reasons.get(key, 0) + 1
        summary[thing] = {"n": len(rs), "ok": sum(r["ok"] for r in rs), "failures": reasons,
                          "robot_seconds_mean": round(float(np.mean([r["robot_seconds"] for r in rs if r["ok"]] or [0.0])), 1)}
    out = {"side": args.side, "seed": args.seed, "stand_off": STAND_OFF, "counter": COUNTER, "area": AREA, "summary": summary, "trials": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
