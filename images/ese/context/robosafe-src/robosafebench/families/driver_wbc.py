"""The scripted controller of the walking G1 (`g1_wbc`, control interface): a family's scripted trajectories, written
with the names of the skill interface (`go`, `turn`, `face`, `wait`, ...), carried out as rows of `whole_body` sent
through the agent's own tool `act`.

`WholeBodyDriver` is what `Driver(...)` gives for an instance on the walking G1 (`Driver.__new__`). It keeps the
private copy of the episode every driver keeps and reads from it where the robot is (the pelvis) and where things
are: a scripted solution knows the scene; it acts only through `act`, the same path as an agent. In place of a pixel
it names its target (`{"target": ...}`): the control interface takes no pixels.

- `go` (one call of the skill: at most `LEG` metres of the way) plans the way as the skill does (`robosafebench.sim.base.plan`
  on the copy: the same grid, the same clearance round the body's outline), and walks it: turn on the spot towards
  each long leg, walk along it with the heading and the sideways error corrected every chunk, slow down into the
  last point, stand. At the end it faces the thing it was sent to and closes up to it (`base._dock`'s distance), as
  the skill does. `speed`: `normal` walks at `SPEEDS["normal"]`, `slow` at `SPEEDS["slow"]`.
- `turn` turns on the spot by the angle, `face` towards a place (the skill's names; `Driver.face` calls `turn`).
- Everything else (`observe`, `wait`, `ask`, `report`, `end`) is sent as it is.

The commands are recomputed from the copy every chunk (`CHUNK_FAR` far from the goal, `CHUNK_NEAR` near it) and
change by at most `ACCEL` per control step within a chunk (BiGym's teleoperation recorded 0.7 m/s per s).
"""
from __future__ import annotations

import math

import numpy as np

from robosafebench.sim import base as B
from robosafebench.sim.world import CONTROL_DT

from .driver import Driver, DriverError

SPEEDS = {"normal": 0.5, "slow": 0.25}      # m/s: walking speed asked of the controller
WZ_MAX = 0.6                    # rad/s: turning rate
ACCEL = (1.0, 1.0, 2.0)         # m/s^2, m/s^2, rad/s^2: how fast the command changes within a chunk
CHUNK_FAR, CHUNK_NEAR = 0.5, 0.2   # s: one `act` per chunk; the command is recomputed from the copy after each
LEG = B.LEG                     # m: one `go` walks at most this far along its way (the skill's leg)
TOL_PASS, TOL_END = 0.15, 0.04  # m: a point on the way counts as passed / the last point as reached
TOL_YAW = math.radians(4.0)
MIN_WALK = 0.06                 # m/s: a smaller velocity command stands (the Balance policy takes over below 0.05)
SETTLE_S = 0.6                  # s of standing after a stop
LEAN_ERR = 0.02                 # m: a reach that misses its spot by more than this is made again leaning (`lean`) ...
LEAN_PITCH, LEAN_HEIGHT = 0.25, 0.68   # rad, m: ... the torso leaned forward and the pelvis lowered (the arm's reach
                                       # over a counter: the elbow straightens no further than -1.05 rad)
# m: where the held thing's middle may be while walking (`carry`): ahead of the pelvis axis, to the working hand's
# side, the hand's height; the nearest to the axis the arm reaches is taken
CARRY_SPOTS = tuple((a, s, z) for a in (0.18, 0.21, 0.24, 0.27, 0.30) for s in (0.0, 0.04, 0.08, 0.12) for z in (1.0, 1.1, 0.95))
CARRY_Z = 1.0
CARRY_UP = 0.10                 # m: the hand goes up this much where it is before it moves across (`carry`)
CARRY_HAND_AHEAD = 0.24         # m: the hand at least this far ahead of the pelvis axis while carrying
# Explicit purse-transfer expert mode: choose a narrow, low posture from the
# actual arm and load geometry. The ordinary expert and contact rules stay as
# they are.
TRANSFER_SPOTS = tuple((a, s, z) for a in (0.21, 0.24, 0.27, 0.30, 0.33, 0.36)
                       for s in (0.12, 0.16, 0.20, 0.24) for z in (0.9, 0.95, 0.85, 1.0, 1.1))
PICK_SHORT = 0.05               # m: a level hand this far short of the spot behind the grip: the pick's fallback
STAND_HEIGHT = 0.74             # m: the pelvis upright (BiGym's standing height)
STILL_MPS = 0.01                # m/s: standing still, before `end(done)` (the goals ask under 0.02)
BACK_OFF = (0.20, 0.40)         # m: steps straight back tried when no way leads from where it stands (`_step_back`)


def _wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


class WholeBodyDriver(Driver):
    """`Driver` for the walking G1: the skill names, carried out as rows of `whole_body` through `act`."""

    # ---- targets by name instead of pixels -------------------------------------------------------------------------
    def pixel_of(self, obj: str) -> dict:
        return {"target": obj}

    def pixel_at(self, target, tol: float = 0.03, past_robot: bool = True, placing: bool = False) -> dict:
        return {"target": target}

    def _pixel(self, target, placing: bool = False) -> dict:
        return {"target": target}

    # ---- calls ---------------------------------------------------------------------------------------------------------
    def call(self, tool: str, check: bool = True, **args) -> dict:
        if tool == "go":
            out = self._go(args.get("target"), args.get("speed", "normal"))
        elif tool == "turn":
            out = self._turn(math.radians(float(args.get("deg", 0.0))), args.get("speed", "normal"))
        elif tool in ("look", "pick", "place", "move", "pour", "press", "release", "home"):
            raise DriverError(f"{tool!r} is a skill of the arm; the walking G1's scripted controller does not have it")
        else:
            return super().call(tool, check=check, **args)
        self.last = out
        if check and out.get("result", {}).get("status") == "failed":
            raise DriverError(f"{tool}({args}) failed: {out['result'].get('reason')}")
        return out

    # ---- the robot as the copy has it ------------------------------------------------------------------------------------
    @property
    def world(self):
        return self.mirror.world

    def pose(self) -> np.ndarray:
        """x, y of the pelvis and its heading (from its orientation)."""
        p = self.mirror.control.pelvis()
        return np.array([float(p["pos"][0]), float(p["pos"][1]), float(p["yaw"])])

    def fallen(self) -> bool:
        return self.world.fell_at is not None

    def _act(self, cmds: np.ndarray) -> dict:
        """Send rows: each row the command in force with vx, vy, wz replaced (the arms and the grippers as they are)."""
        if self._rt():          # realtime: the row in force once the coming think gap has run
            hold = self._predict()[4]
        else:
            typ, hold = self.mirror.hold()
        rows = np.repeat(hold[None, :], len(cmds), axis=0)
        rows[:, [0, 1, 3]] = cmds
        out = super().call("act", type="whole_body", rows=[[float(v) for v in r] for r in rows], dt=CONTROL_DT, images=False)
        return out

    def _chunk(self, want, seconds: float) -> None:
        """One chunk of `seconds` towards the command `want` (vx, vy, wz), the change limited by `ACCEL` per step."""
        if self._rt():          # realtime: from the command the coming think gap leaves in force
            cur = self._predict()[3]
        else:
            cur = np.asarray(self.mirror.command("whole_body")[[0, 1, 3]], dtype=np.float64)
        want = np.asarray(want, dtype=np.float64)
        if float(np.hypot(want[0], want[1])) < MIN_WALK and abs(float(want[2])) < 0.05:
            want = np.zeros(3)
        n = max(int(round(seconds / CONTROL_DT)), 1)
        step = np.array(ACCEL) * CONTROL_DT
        cmds = []
        for _ in range(n):
            cur = cur + np.clip(want - cur, -step, step)
            cmds.append(cur.copy())
        self._act(np.array(cmds))

    def settle(self, limit: float = STILL_MPS, most: float = 4.0) -> float:
        """Stand until the walking speed (the pelvis's mean over 0.5 s, `World.base_vel`) is under `limit`, at most
        `most` seconds; returns the speed. A body that walks sways and coasts a little after a stop: a goal that asks
        it to stand still is read after this."""
        w = self.world
        t0 = w.time
        if self._rt():
            return self._settle_rt(limit, most)
        speed = float(np.hypot(*w.base_vel()[:2]))
        while speed >= limit and w.time - t0 < most and not self.fallen():
            self._chunk((0.0, 0.0, 0.0), CHUNK_NEAR)
            speed = float(np.hypot(*w.base_vel()[:2]))
        return speed

    def _settle_rt(self, limit: float, most: float) -> float:
        """Realtime `settle`: the plan run out, then `RT_SETTLE_S` of standing (a `wait`: the G1 often takes a balancing
        step about a second after it stops, and the call that follows comes after a think gap, which the robot spends
        standing), then standing on, half a second a call, until the speed is under `limit`, at most `most` s."""
        w = self.world
        self._run_out()
        t0 = w.time
        super().call("wait", seconds=self.RT_SETTLE_S)
        speed = float(np.hypot(*w.base_vel()[:2]))
        while speed >= limit and w.time - t0 < most and not self.fallen():
            super().call("wait", seconds=0.5)
            speed = float(np.hypot(*w.base_vel()[:2]))
        return speed

    def end(self, reason: str, text: str = "", **kw):
        if reason == "done" and not self.fallen():
            self.settle()
        return super().end(reason, text, **kw)

    def stand(self, seconds: float = SETTLE_S) -> None:
        """Stop (the velocity brought to zero at `ACCEL`) and stand."""
        self._chunk((0.0, 0.0, 0.0), seconds)

    # ---- the realtime clock (0.5.4) ------------------------------------------------------------------------------------
    # Under `clock = "realtime"` an `act` does not run inside the call: its rows become the plan and the call returns at
    # once; the agent's time before the next call (the think gap) runs the plan, and once the plan has run out the robot
    # holds its command with the walking velocity zero (`WholeBodyControl.hold`: it stops). Sent as when paused, every
    # short chunk of walking would end in a stop for the rest of the gap and start again from standing: the G1 walks a
    # few centimetres a call and runs out of calls (0.5.3's reference under 1 s of thinking used up `max_calls` at about
    # 180 s of robot time, `gave_up`). So under this clock a walking plan lasts through the coming gap and `RT_HORIZON_S`
    # past it (the gap expected as long as the last one: the latency the driver has seen), worked out on the pose
    # predicted step by step from the commands (where the plan still to run leaves the robot when the gap ends, then the
    # law of walking of `walk_to` / `turn_to`), and it ends standing (the velocity brought to zero at `ACCEL`), so a call
    # that comes later than expected finds the robot stopped, never walking on. The next call replaces what is left of
    # it. Nothing here runs under the paused clock.
    RT_HORIZON_S = CHUNK_FAR        # s: a walking plan runs this far past the expected end of the coming gap
    RT_TRIES = 60                   # calls one walk or turn may take under the realtime clock ...
    RT_FROM_REST = 6                # ... of which at most this many start from standing short of the goal (a correction)
    # How the pelvis follows the velocity command (vx, vy, wz), the driver's model of its body for the prediction: a lag
    # of `RT_TAU` s to `RT_GAIN` of the command, fitted on the paused control interface (ramps at `ACCEL` to 0.06 ..
    # 0.5 m/s, 0.2 m/s sideways, 0.15 .. 0.6 rad/s; tools of lane rt054-g1, probe/lagcal.json: 0.5 m/s commanded for
    # 1.49 m walked 1.20 m)
    RT_TAU = (0.30, 0.10, 0.10)
    RT_GAIN = (0.85, 0.70, 0.95)
    # m: the furthest a walking plan goes on its own through the expected gap (the walking speed asked for is capped at
    # this over the gap's length, never below `SPEEDS["slow"]` / 2): the longer the agent thinks, the slower it walks,
    # so the way it has not seen yet stays short; up to 2.4 s of thinking `normal` keeps its 0.5 m/s
    RT_OPEN_M = 1.2
    # m: under the realtime clock a walk aims at `TOL_END` and counts as there within this: a correction from standing
    # (a short step of `MIN_WALK`) is not reliable on the walking controller (it sways back as often as it steps on)
    RT_TOL_END = 0.08
    RT_GAPS = 4                     # the coming gap is expected as long as the longest of the last this many
    RT_NEAR = (0.30, 0.30)          # m, rad: a stop short of the goal nearer than this counts as one from which it corrects
    RT_SETTLE_S = 1.0               # s of standing before the speed is read for `end(done)`

    def _rt(self) -> bool:
        return getattr(self.mirror, "clock", "paused") == "realtime"

    def _gap_ticks(self) -> int:
        """The control ticks the coming think gap is expected to run: as many as the longest of the last `RT_GAPS`
        gaps ran (the copy's calls carry them): a plan made for the longest recent gap is cut short by a call that
        comes sooner, and does not run out before one that comes later."""
        ticks = [int((c.get("clock") or {}).get("ticks", 0)) for c in self.mirror.calls[-self.RT_GAPS:]]
        return max(ticks, default=0)

    def _move(self, x: float, y: float, yaw: float, vm, cmd) -> tuple:
        """The pelvis one control step on under the command `cmd` (vx, vy, wz), its velocity `vm` (body frame) following
        the command as `RT_TAU` and `RT_GAIN` model it. Returns (x, y, yaw, vm)."""
        vm = vm + (np.array(self.RT_GAIN) * np.asarray(cmd, dtype=np.float64) - vm) * (CONTROL_DT / np.array(self.RT_TAU))
        c, s = math.cos(yaw), math.sin(yaw)
        return (x + (c * float(vm[0]) - s * float(vm[1])) * CONTROL_DT, y + (s * float(vm[0]) + c * float(vm[1])) * CONTROL_DT,
                yaw + float(vm[2]) * CONTROL_DT, vm)

    def _predict(self) -> tuple:
        """Realtime: (x, y, yaw, command, hold row, velocity) once the coming gap has run: the plan still to run for the
        gap's ticks, then the hold (the row in force, the velocity zero); the pose is the copy's, moved on by the commands
        from the velocity it has now (`_move`)."""
        x, y, yaw = (float(v) for v in self.pose())
        p = self.mirror.control.pelvis()
        vm = np.array([float(p["v"][0]), float(p["v"][1]), float(p["wz"])])
        row = np.array(self.mirror.control.row, dtype=np.float64)
        plan = self.mirror.plan
        if not plan and not np.any(row[[0, 1, 3]]):     # standing: its sway is no velocity
            vm = np.zeros(3)
        n = self._gap_ticks()
        for k in range(n):
            if k < len(plan) and plan[k][0] != "hold":
                row = np.array(plan[k][1], dtype=np.float64)
            else:
                row[[0, 1, 3]] = 0.0
            x, y, yaw, vm = self._move(x, y, yaw, vm, row[[0, 1, 3]])
        if len(plan) <= n:                          # the plan has run out within the gap: the next one starts from the hold
            row[[0, 1, 3]] = 0.0
        hold = row.copy()
        hold[[0, 1, 3]] = 0.0
        return x, y, yaw, row[[0, 1, 3]].copy(), hold, vm

    def _rollout(self, law) -> list:
        """Realtime: the commands of one walking plan: from the predicted end of the gap, `law(x, y, yaw)` (the wanted
        (vx, vy, wz), or None once there) on the predicted pose, the change limited by `ACCEL` per step, through the
        gap's length and `RT_HORIZON_S` more (at most 400 steps), then brought to zero."""
        x, y, yaw, cur, _, vm = self._predict()
        step = np.array(ACCEL) * CONTROL_DT
        n = min(self._gap_ticks() + int(round(self.RT_HORIZON_S / CONTROL_DT)), 400)
        cmds = []
        for _ in range(n):
            want = law(x, y, yaw)
            there = want is None
            want = np.zeros(3) if there else np.asarray(want, dtype=np.float64)
            if float(np.hypot(want[0], want[1])) < MIN_WALK and abs(float(want[2])) < 0.05:
                want = np.zeros(3)
            cur = cur + np.clip(want - cur, -step, step)
            cmds.append(cur.copy())
            x, y, yaw, vm = self._move(x, y, yaw, vm, cur)
            if there and not np.any(cur):
                break
        while np.any(cur) and len(cmds) < 500:      # it ends standing
            cur = cur + np.clip(-cur, -step, step)
            cmds.append(cur.copy())
        return cmds

    def _rt_loop(self, law, there, state=None, near=None) -> tuple:
        """Realtime: a plan a call (`_rollout` of `law`) until the plan in force ends within the coming gap with the
        robot standing where `there(x, y, yaw)` holds (the pose predicted for the end of the gap: the call that comes
        then finds it there), at most `RT_TRIES` calls, of which at most `RT_FROM_REST` start from standing short of it.
        `state["hist"]`, where the law keeps it, is where the law stood at each step: the walk goes on from where it
        stands when the next call is due. It then lets the plan run out (a short `wait`: its gap runs the rest), so that
        what comes next reads the robot standing where it is. Returns the pose then (x, y, yaw)."""
        from_rest = 0
        for _ in range(self.RT_TRIES):
            x, y, yaw, cur = self._predict()[:4]
            if self.fallen():
                return tuple(float(v) for v in self.pose())
            if len(self.mirror.plan) <= self._gap_ticks() and not np.any(cur):     # it will stand before the next call
                if self.mirror.plan and there(x, y, yaw):
                    x, y, yaw = self._run_out()         # predicted there: let the plan run out and look
                if there(x, y, yaw) or from_rest >= self.RT_FROM_REST:
                    return self._run_out()
                if near is None or near(x, y, yaw):     # a stop short of it (a gap longer than expected is none)
                    from_rest += 1
            if state is not None:
                state["hist"] = []
            cmds = self._rollout(law)
            if state is not None and state["hist"]:
                state["i"] = state["hist"][min(self._gap_ticks(), len(state["hist"]) - 1)]
            self._act(np.array(cmds))
        self._act(np.zeros((int(round(SETTLE_S / CONTROL_DT)), 3)))       # out of calls for it: stand
        return self._run_out()

    def _run_out(self) -> tuple:
        """Realtime: a short `wait` if a plan is still to run (the think gap before it runs the plan), so that the copy
        has the robot as the plan leaves it. Returns the pose (x, y, yaw)."""
        if self.mirror.plan and not self.fallen():
            super().call("wait", seconds=0.1)
        return tuple(float(v) for v in self.pose())

    def _walk_way_rt(self, way, speed: str = "normal", heading: float | None = None) -> bool:
        """Realtime `walk_to` along `way` (points of the floor: the last stopped at within `TOL_END`, the others passed
        within `TOL_PASS`, as `_go` walks a leg): the law of `walk_to` on the predicted pose. Returns whether it got to
        the last point."""
        v_max = SPEEDS[speed]
        gap_s = self._gap_ticks() * CONTROL_DT
        if gap_s > 0.0:
            v_max = min(v_max, max(self.RT_OPEN_M / gap_s, SPEEDS["slow"] / 2.0))
        way = [np.asarray(p, dtype=np.float64)[:2] for p in way]
        state = {"i": 0, "hist": []}

        def law(x, y, yaw):
            i = state["i"] if not state["hist"] else state["hist"][-1]
            while True:
                last = i == len(way) - 1
                e = way[i] - np.array([x, y])
                dist = float(np.linalg.norm(e))
                if dist >= (TOL_END if last else TOL_PASS):
                    break
                if last:
                    state["hist"].append(i)
                    return None
                i += 1
            state["hist"].append(i)
            c, s = math.cos(yaw), math.sin(yaw)
            eb = np.array([c * e[0] + s * e[1], -s * e[0] + c * e[1]])
            want_yaw = math.atan2(e[1], e[0]) if heading is None or dist > 0.4 else heading
            yaw_err = _wrap(want_yaw - yaw)
            if dist > 0.30 and abs(yaw_err) > 0.5:          # far and facing away: turn on the spot first
                return (0.0, 0.0, float(np.clip(1.5 * yaw_err, -WZ_MAX, WZ_MAX)))
            if last:                                        # slow down into the point (about 0.5 m/s^2)
                v = min(v_max, math.sqrt(max(2.0 * 0.5 * (dist - 0.02), 0.0)), 0.6 * dist + 0.05)
            else:
                v = v_max
            vx = v * eb[0] / dist
            vy = float(np.clip(v * eb[1] / dist if dist < 0.4 else 0.8 * eb[1], -0.2, 0.2))
            wz = float(np.clip(1.5 * yaw_err, -WZ_MAX, WZ_MAX)) if (dist > 0.15 or heading is not None) else 0.0
            if 0.0 < math.hypot(vx, vy) < MIN_WALK:          # a step too small to walk: the smallest that walks
                k = MIN_WALK / math.hypot(vx, vy)
                vx, vy = vx * k, vy * k
            return (vx, vy, wz)

        goal = way[-1]
        x, y, _ = self._rt_loop(law, lambda x, y, h: float(np.linalg.norm(goal - np.array([x, y]))) < self.RT_TOL_END, state,
                                near=lambda x, y, h: float(np.linalg.norm(goal - np.array([x, y]))) < self.RT_NEAR[0])
        return float(np.linalg.norm(goal - np.array([x, y]))) < self.RT_TOL_END + 0.02

    def _turn_to_rt(self, yaw: float, wz_max: float) -> bool:
        """Realtime `turn_to`: the turning law of `turn_to` on the predicted heading."""
        def law(x, y, h):
            err = _wrap(yaw - h)
            return None if abs(err) < TOL_YAW else (0.0, 0.0, float(np.clip(1.5 * err, -wz_max, wz_max)))
        h = self._rt_loop(law, lambda x, y, h: abs(_wrap(yaw - h)) < TOL_YAW, near=lambda x, y, h: abs(_wrap(yaw - h)) < self.RT_NEAR[1])[2]
        return abs(_wrap(yaw - h)) < 2.0 * TOL_YAW

    # ---- walking ------------------------------------------------------------------------------------------------------
    def turn_to(self, yaw: float, speed: str = "normal") -> bool:
        wz_max = WZ_MAX * (0.5 if speed == "slow" else 1.0)
        if self._rt():
            return self._turn_to_rt(yaw, wz_max)
        for _ in range(80):
            if self.fallen():
                return False
            err = _wrap(yaw - self.pose()[2])
            if abs(err) < TOL_YAW:
                break
            self._chunk((0.0, 0.0, float(np.clip(1.5 * err, -wz_max, wz_max))), CHUNK_NEAR if abs(err) < 0.4 else CHUNK_FAR)
        self.stand(0.3)
        return abs(_wrap(yaw - self.pose()[2])) < 2.0 * TOL_YAW

    def walk_to(self, goal, speed: str = "normal", last: bool = True, heading: float | None = None, _again: int = 0) -> bool:
        """Walk to a point of the floor; `last`: stop there (else pass it within `TOL_PASS`). Returns whether it got
        there."""
        if self._rt():
            return self._walk_way_rt([goal], speed, heading=heading)
        v_max = SPEEDS[speed]
        goal = np.asarray(goal, dtype=np.float64)[:2]
        tol = TOL_END if last else TOL_PASS
        for _ in range(400):
            if self.fallen():
                return False
            x, y, yaw = self.pose()
            e = goal - np.array([x, y])
            dist = float(np.linalg.norm(e))
            if dist < tol:
                break
            c, s = math.cos(yaw), math.sin(yaw)
            eb = np.array([c * e[0] + s * e[1], -s * e[0] + c * e[1]])
            want_yaw = math.atan2(e[1], e[0]) if heading is None or dist > 0.4 else heading
            yaw_err = _wrap(want_yaw - yaw)
            if dist > 0.30 and abs(yaw_err) > 0.5:          # far and facing away: turn on the spot first
                self._chunk((0.0, 0.0, float(np.clip(1.5 * yaw_err, -WZ_MAX, WZ_MAX))), CHUNK_NEAR)
                continue
            if last:                                        # slow down into the point (about 0.5 m/s^2)
                v = min(v_max, math.sqrt(max(2.0 * 0.5 * (dist - 0.02), 0.0)), 0.6 * dist + 0.05)
            else:
                v = v_max
            vx = v * eb[0] / dist
            vy = float(np.clip(v * eb[1] / dist if dist < 0.4 else 0.8 * eb[1], -0.2, 0.2))
            wz = float(np.clip(1.5 * yaw_err, -WZ_MAX, WZ_MAX)) if (dist > 0.15 or heading is not None) else 0.0
            if 0.0 < math.hypot(vx, vy) < MIN_WALK:          # a step too small to walk: the smallest that walks
                k = MIN_WALK / math.hypot(vx, vy)
                vx, vy = vx * k, vy * k
            self._chunk((vx, vy, wz), CHUNK_FAR if dist > 1.0 else CHUNK_NEAR)
        if last:
            self.stand()
            off = float(np.linalg.norm(goal - self.pose()[:2]))
            if off >= tol + 0.02 and _again < 2 and not self.fallen():
                # it coasted past or stopped short: once more, slowly, from where it stands
                return self.walk_to(goal, "slow", last=True, heading=heading, _again=_again + 1)
        return float(np.linalg.norm(goal - self.pose()[:2])) < tol + 0.02

    # ---- the skill names ------------------------------------------------------------------------------------------------
    def _result(self, status: str, reason: str, **info) -> dict:
        robot = self.robot_state()
        return {"ok": True, "result": {"status": status, "reason": reason, **info}, "robot": robot}

    def robot_state(self) -> dict:
        x, y, yaw = self.pose()
        return {"time_s": round(self.world.time, 2), "base_position_m": [round(x, 2), round(y, 2)],
                "base_heading_deg": round(math.degrees(yaw), 1)}

    def _turn(self, angle: float, speed: str = "normal") -> dict:
        start = self.pose()[2]
        ok = self.turn_to(_wrap(start + angle), speed)
        turned = math.degrees(_wrap(self.pose()[2] - start))
        if self.fallen():
            return self._result("failed", "fell", turned_deg=round(turned, 1))
        return self._result("ok" if ok else "failed", "ok" if ok else "not_reached", turned_deg=round(turned, 1))

    def _hit(self, target) -> dict:
        w = self.world
        point = self.where(target)
        name = target.split(":", 1)[0].split("/", 1)[0] if isinstance(target, str) else None
        point = np.asarray(point, dtype=np.float64)
        if name is None and len(point) > 2 and point[2] > 0.3:
            # a spot above the floor (on a table): the thing whose top it is on, as a pixel on that top would name it
            for n in sorted(w.objects):
                lo, hi = (np.asarray(v) for v in w.box(n))
                if lo[0] <= point[0] <= hi[0] and lo[1] <= point[1] <= hi[1] and hi[2] - 0.10 <= point[2] <= hi[2] + 0.15:
                    name = n
                    break
        return {"object": name if name in w.objects else "floor", "point": point}

    def _go(self, target, speed: str = "normal") -> dict:
        if speed not in SPEEDS:
            raise DriverError(f"speed is one of {sorted(SPEEDS)}")
        w = self.world
        hit = self._hit(target)
        plan, why = B.plan(w, hit)
        if plan is None and why == "no_way" and self._tuck():
            # the arm still out where it worked (the way has to keep the reach of the arm clear): drawn in first
            plan, why = B.plan(w, hit)
        for back in BACK_OFF:
            if plan is not None or why != "no_way":
                break
            # standing closer to something than a way would pass it (stood before a counter to work at it, the thing
            # in the hand over its top): a step straight back first, the heading kept, as a person would
            if self._step_back(back, speed):
                plan, why = B.plan(w, hit)
        start = self.pose()
        if plan is None:
            return self._result("failed", why, arrived=False)
        pts, total = [np.asarray(p, dtype=np.float64) for p in plan["points"]], float(plan["length"])
        info = {"arrived": False, "remaining_m": round(total, 2), "moved_m": 0.0, "kind": plan["kind"]}
        # the way, cut at LEG metres
        way, left = [], LEG
        for a, b in zip(pts, pts[1:]):
            seg = float(np.linalg.norm(b - a))
            if seg < 1e-6:
                continue
            if left <= 1e-6:
                break
            part = min(seg, left)
            way.append(a + (b - a) * (part / seg))
            left -= part
        done = LEG - left
        remaining = max(total - done, 0.0)
        if self._rt() and way:              # realtime: the leg's points walked as one way, without a stop at each
            ok = self._walk_way_rt(way, speed)
            if self.fallen():
                return self._result("failed", "fell", **info)
            if not ok:
                info.update(remaining_m=round(max(float(np.linalg.norm(pts[-1] - self.pose()[:2])), remaining), 2))
                return self._result("failed", "not_reached", **{**info, "moved_m": round(float(np.linalg.norm(self.pose()[:2] - start[:2])), 2)})
            way = []
        for i, p in enumerate(way):
            ok = self.walk_to(p, speed, last=(i == len(way) - 1))
            if self.fallen():
                return self._result("failed", "fell", **info)
            if not ok and i == len(way) - 1:
                info.update(remaining_m=round(max(float(np.linalg.norm(pts[-1] - self.pose()[:2])), remaining), 2))
                return self._result("failed", "not_reached", **{**info, "moved_m": round(float(np.linalg.norm(self.pose()[:2] - start[:2])), 2)})
        info["moved_m"] = round(float(np.linalg.norm(self.pose()[:2] - start[:2])), 2)
        if remaining > 0.02:
            info["remaining_m"] = round(remaining, 2)
            return self._result("ok", "ok", **info)
        if plan["face"] is not None:
            here = self.pose()
        d = plan["face"] - here[:2] if plan["face"] is not None else None
        if d is not None and float(np.linalg.norm(d)) > 0.05:
            self.turn_to(math.atan2(d[1], d[0]), speed)
        if plan["dock"]:
            self._dock(plan["face"], plan.get("thing"), speed)
        if self.fallen():
            return self._result("failed", "fell", **info)
        info.update(arrived=True, remaining_m=0.0, moved_m=round(float(np.linalg.norm(self.pose()[:2] - start[:2])), 2))
        return self._result("ok", "ok", **info)

    def _tuck(self) -> bool:
        """Draw the working arm in for walking: home with an empty hand, the carrying posture with something in it
        (`carry`). Returns whether it moved the arm."""
        h = self.HAND
        _, hold = self.mirror.hold()
        q_now = hold[self.ARM_COLS[h]]
        if self.world.held_by.get(h) is None:
            empty = self.__dict__.get("_empty_transfer_posture")
            if empty is not None:
                # This expert has already withdrawn along its checked placing
                # route to a compact, self-clear posture. Keep that posture
                # instead of taking an unchecked shortcut to ordinary home.
                return False
            home = np.array(self.world.arm(h).home)
            if float(np.max(np.abs(q_now - home))) < 1e-3:
                return False
            self.arm_home(h)
            return True
        x, y, yaw = self.pose()
        self.carry(h, self._frame([math.cos(yaw), math.sin(yaw)])[2])
        return float(np.max(np.abs(self.mirror.hold()[1][self.ARM_COLS[h]] - q_now))) > 1e-3

    def _step_back(self, dist: float, speed: str) -> bool:
        """Walk `dist` straight back, the heading kept, if the spot there is clear of everything (`B.hits` with the
        planner's margin; the way back from where it stands is not checked: it is the way it came). Returns whether it
        stepped."""
        w = self.world
        x, y, yaw = self.pose()
        spot = np.array([x - math.cos(yaw) * dist, y - math.sin(yaw) * dist])
        if B.hits(w, [float(spot[0]), float(spot[1]), w.base_pose()[2]], clearance=B.MARGIN) is not None:
            return False
        self.walk_to(spot, "slow", last=True, heading=yaw)
        return not self.fallen()

    def _dock(self, spot, thing, speed: str) -> None:
        """Close up to what stands at `spot`, as the skill does (`base._dock`): straight ahead until the outline is the
        body's `dock_gap` from something or the middle is the working distance from the spot."""
        w = self.world
        x, y, yaw = w.base_pose()
        ahead = np.array([math.cos(yaw), math.sin(yaw)])
        far = float((np.asarray(spot, dtype=np.float64)[:2] - np.array([x, y])) @ ahead) - B.working_distance(w, thing)
        step, run = 0.01, 0.0
        while run + step <= far + 1e-9 and B.hits(w, [x + ahead[0] * (run + step), y + ahead[1] * (run + step), yaw],
                                                  clearance=B.standoff(w, "dock_gap")) is None:
            run += step
        if run > TOL_END:
            self.walk_to(np.array([x, y]) + ahead * run, "slow" if speed == "slow" else "normal", last=True, heading=yaw)

    def walk_into(self, thing: str, beyond: float = 0.25) -> None:
        """Walk up to a thing (`go`) and on into it, slowly, straight at its middle (the admission check of the contact
        marks: `verify/bump.py`). Stops once the copy's contact log has a contact with it, or `beyond` past the gap."""
        # the check bumps a thing; it does not walk over a cord to get there (a thing on the floor that does not collide,
        # `visual_only`: walking over it is a hazard of its own, and would set `attempted` in a family about it)
        w = self.world
        if (w.objects[thing].get("meta") or {}).get("visual_only"):
            raise DriverError(f"{thing!r} lies flat and does not collide: it is walked over, not into")
        plan, _ = B.plan(w, self._hit(thing))
        if plan is not None:
            pts = [np.asarray(p, dtype=np.float64)[:2] for p in plan["points"]]
            half = float(max(np.hypot(*q) for q in w.base["footprint"]))
            for n, o in w.objects.items():
                if not (o.get("meta") or {}).get("visual_only") or n == thing:
                    continue
                lo, hi = (np.asarray(v)[:2] for v in w.box(n))
                for a, b in zip(pts, pts[1:]):
                    for t in np.linspace(0.0, 1.0, 41):
                        q = a + (b - a) * t
                        if np.all(q >= lo - half) and np.all(q <= hi + half):
                            raise DriverError(f"the way to {thing!r} crosses {n!r}")
        for _ in range(6):                  # leg after leg (one `go` walks at most `LEG`), as `Driver.go` does
            out = self._go(thing, "slow")
            if out["result"]["status"] == "failed" or out["result"].get("arrived"):
                break
        if out["result"]["status"] == "failed" and not self.fallen():
            raise DriverError(f"go({thing!r}): {out['result']['reason']}")
        w = self.world
        lo, hi = w.box(thing)
        c = (np.asarray(lo) + np.asarray(hi))[:2] / 2.0
        # aimed at what of it stands up (a dock's post, not its mat: a foot on the mat is no contact of the marks)
        from robosafebench.hazard.contact import walked_on
        m, sd = w.model, w._sync()
        kind = w.objects[thing].get("kind")
        solid = [g for g in range(m.ngeom) if w._geom_owner[g] == thing and (m.geom_contype[g] or m.geom_conaffinity[g])]
        upright = [g for g in solid if not walked_on(kind, m.geom(g).name, thing)]
        if upright and len(upright) < len(solid):
            c = np.mean([sd.geom_xpos[g][:2] for g in upright], axis=0)
        x, y, yaw = self.pose()
        self.turn_to(math.atan2(c[1] - y, c[0] - x), "slow")
        start = self.pose()[:2]
        # on until the contact log has a contact with it (a foot on a mat the robot walks on is none), at most through
        # to its far side and `beyond` further
        most = beyond + 0.6 + float(np.linalg.norm((np.asarray(hi) - np.asarray(lo))[:2])) / 2.0
        for _ in range(int(most / (0.15 * CHUNK_NEAR)) + 1):
            if self.fallen() or float(np.linalg.norm(self.pose()[:2] - start)) > most:
                break
            log = self.mirror.contact_log
            if any(e["kind"] == "object" and e["with"] == thing for e in list(log.done) + list(log.open.values())):
                break
            self._chunk((0.15, 0.0, 0.0), CHUNK_NEAR)
        self.stand()

    # ---- the arms ---------------------------------------------------------------------------------------------------
    ARM_COLS = {"left": slice(5, 12), "right": slice(12, 19)}
    GRIP_COL = {"left": 19, "right": 20}

    def _rows(self, rows) -> dict:
        """Send whole rows (the walking velocity zero unless the rows say otherwise)."""
        return super().call("act", type="whole_body", rows=[[float(v) for v in r] for r in rows], dt=CONTROL_DT, images=False)

    def arm_ik(self, side: str, pos, quat, q0=None, iters: int = 80, free=None) -> tuple[np.ndarray, float, float]:
        """Joint targets of one arm that put its pinch point at `pos` with the tool frame `quat` (room frame), the body
        as it stands now in the copy: damped least squares on a scratch copy. `free`: an axis (room frame) about which
        the hand may turn away from `quat` (the fingers pitched about the direction they close in still close across
        the grip). Returns (q, position error, angle error)."""
        import mujoco
        from robosafebench.sim import tf
        w = self.world
        m = w.model
        d = self.__dict__.get("_ik_data")
        if d is None:
            d = self.__dict__["_ik_data"] = mujoco.MjData(m)
        ix = w._ix[side]
        qadr, dadr, site = ix["_arm_qadr"], ix["_arm_dadr"], ix["tcp_site"]
        lo, hi = ix["arm_range"][:, 0] + 0.02, ix["arm_range"][:, 1] - 0.02
        d.qpos[:] = w.data.qpos
        q = np.array(self.mirror.command("whole_body")[self.ARM_COLS[side]] if q0 is None else q0, dtype=np.float64)
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        pos, quat = np.asarray(pos, dtype=np.float64), tf.unit(quat)
        proj = None if free is None else np.eye(3) - np.outer(tf.unit(free), tf.unit(free))
        pe = re = float("inf")
        for _ in range(iters):
            d.qpos[qadr] = q
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            ep = pos - d.site_xpos[site]
            er = tf.rotvec(tf.mat_to_quat(d.site_xmat[site].reshape(3, 3)), quat)
            if proj is not None:
                er = proj @ er
            pe, re = float(np.linalg.norm(ep)), float(np.linalg.norm(er))
            if pe < 5e-4 and re < 5e-3:
                break
            mujoco.mj_jacSite(m, d, jp, jr, site)
            jac = np.vstack([jp[:, dadr], (jr[:, dadr] if proj is None else proj @ jr[:, dadr])])
            err = np.concatenate([ep, 0.5 * er])
            lam = 1e-4 + 0.02 * float(err @ err)
            dq = jac.T @ np.linalg.solve(jac @ jac.T + lam * np.eye(6), err)
            big = float(np.max(np.abs(dq)))
            if big > 0.15:
                dq *= 0.15 / big
            q = np.clip(q + dq, lo, hi)
        return q, pe, re

    def tcp(self, side: str):
        return self.world.arm(side).tcp_pose()

    def arm_to(self, side: str, q, seconds: float = 1.0, grip: float | None = None) -> None:
        """Move one arm's joint targets on a straight line in joint space to `q` (smoothstep in time), and the gripper
        to `grip`, the body standing."""
        _, hold = self.mirror.hold()
        q0 = hold[self.ARM_COLS[side]].copy()
        g0 = float(hold[self.GRIP_COL[side]])
        n = max(int(round(seconds / CONTROL_DT)), 1)
        rows = []
        for k in range(1, n + 1):
            s = k / n
            s = s * s * (3.0 - 2.0 * s)
            r = hold.copy()
            r[self.ARM_COLS[side]] = q0 + (np.asarray(q) - q0) * s
            if grip is not None:
                r[self.GRIP_COL[side]] = g0 + (grip - g0) * s
            rows.append(r)
        for k in range(0, len(rows), 500):
            self._rows(rows[k:k + 500])

    def reach(self, side: str, pos, quat, seconds: float = 1.2, tries: int = 3, tol: float = 0.01, free=None) -> float:
        """Bring the pinch point to `pos` (room frame) with the tool frame `quat`: solve, move, measure where the hand
        is (the arm sags under its weight: its servos are soft and nothing compensates gravity), aim again by the
        error. Returns the remaining error (m)."""
        if self.__dict__.get("_transfer_placing", False):
            return self._transfer_reach(side, pos, quat, seconds, tries, tol, free)
        aim = np.asarray(pos, dtype=np.float64).copy()
        err = float("inf")
        for k in range(tries):
            q, pe, re = self.arm_ik(side, aim, quat, free=free)
            self.arm_to(side, q, seconds if k == 0 else 0.4)
            self.arm_to(side, q, 0.3)                     # let it settle on the targets
            got = self.tcp(side)[0]
            e = np.asarray(pos) - got
            err = float(np.linalg.norm(e))
            if err < tol:
                break
            aim = aim + e
        return err

    def _transfer_reach(self, hand, pos, quat, seconds, tries, tol, free):
        """Place a purse using an IK branch whose arm/load path is clear.

        A low carry pose is on a different IK branch from the high shelf reach.
        Reusing just that seed could command a joint limit and then lean the
        knees into the shelf. These are expert planning checks, not exemptions
        from the contact verifier.
        """
        aim = np.asarray(pos, dtype=np.float64).copy()
        for attempt in range(tries):
            current = np.asarray(self.mirror.command("whole_body")[self.ARM_COLS[hand]])
            actual = self.world.data.qpos[self.world._ix[hand]["_arm_qadr"]].copy()
            seeds = [current, np.asarray(self.world.arm(hand).home)]
            for pitch, roll in ((0.35, -0.35), (0.65, -0.5), (0.3, -0.7), (-0.1, -0.5), (0.8, -0.2)):
                seed = current.copy()
                seed[:2] = pitch, roll
                seeds.append(seed)
            candidates = []
            for seed in seeds:
                q, pe, re = self.arm_ik(hand, aim, quat, q0=seed, iters=120, free=free)
                if pe >= 0.01 or re >= 0.05 or not self._transfer_self_clear(hand, q):
                    continue
                if not all(self._transfer_self_clear(hand, start + (q - start) * s)
                           for start in (actual,) for s in np.linspace(0.1, 1.0, 10)):
                    continue
                candidates.append((pe + 0.1 * re, float(np.linalg.norm(q - current)), q))
            if not candidates:
                if attempt:
                    return float(np.linalg.norm(np.asarray(pos) - self.tcp(hand)[0]))
                raise DriverError("place: no clear arm and load path to the next waypoint")
            q = min(candidates, key=lambda c: (c[1], c[0]))[2]
            # Among accurate clear solutions prefer the nearby branch, then
            # move gently: tiny FK residual differences must not produce a
            # large elbow swing while the purse is over its support.
            duration = max(seconds, 10.0 * float(np.max(np.abs(q - current))))
            waypoints = self.__dict__.get("_transfer_waypoints")
            if waypoints is not None:
                waypoints.append(q.copy())
            self.arm_to(hand, q, duration)
            self.arm_to(hand, q, 0.3)
            error = np.asarray(pos) - self.tcp(hand)[0]
            err = float(np.linalg.norm(error))
            if err < tol:
                break
            aim += error
        return err

    def grip(self, side: str, value: float, seconds: float = 0.6) -> None:
        _, hold = self.mirror.hold()
        self.arm_to(side, hold[self.ARM_COLS[side]], seconds, grip=value)

    def arm_home(self, side: str, seconds: float = 1.2) -> None:
        self.arm_to(side, np.array(self.world.arm(side).home), seconds)

    # ---- the skill names of the arm, as the scripted controller does them --------------------------------------------
    HAND = "right"                  # the hand that works (the body stands with the spot before its right shoulder)
    AHEAD = 0.36                    # m: the pinch point this far ahead of the pelvis axis ...
    BESIDE = 0.15                   # ... and this far to the working hand's side
    TIP = 0.037                     # m: how far the closed fingertips reach past the pinch point

    def _frame(self, fwd):
        from robosafebench.sim import tf
        fwd = np.array([float(fwd[0]), float(fwd[1]), 0.0])
        fwd /= max(float(np.linalg.norm(fwd)), 1e-9)
        left = np.array([-fwd[1], fwd[0], 0.0])
        level = tf.quat_from_axes(y=np.cross(np.array([0.0, 0.0, 1.0]), fwd), z=fwd)      # level hand, closing across
        return fwd, left, level

    def stand_before(self, point, fwd, ahead: float | None = None, speed: str = "normal", beside: float | None = None) -> None:
        """Walk to where the working hand has `point` `ahead` before it (the body facing `fwd`) and face `fwd`."""
        fwd, left, _ = self._frame(fwd)
        ahead = self.AHEAD if ahead is None else ahead
        beside = self.BESIDE if beside is None else beside
        side = -1.0 if self.HAND == "right" else 1.0
        spot = np.asarray(point, dtype=np.float64)[:2] - fwd[:2] * ahead - left[:2] * side * beside
        yaw = math.atan2(fwd[1], fwd[0])
        if float(np.linalg.norm(spot - self.pose()[:2])) > 0.30:
            out = self._go([float(spot[0]), float(spot[1]), 0.0], speed)
            for _ in range(3):
                if out["result"].get("arrived") or out["result"]["status"] == "failed":
                    break
                out = self._go([float(spot[0]), float(spot[1]), 0.0], speed)
        self.turn_to(yaw, speed)
        self.walk_to(spot, "slow", last=True, heading=yaw)
        self.turn_to(yaw, speed)

    def press(self, obj: str, control: str, **kw):
        from robosafebench.sim import tf
        w = self.world
        site = w.objects[obj]["meta"]["controls"][control]["site"]
        p = w.locate(f"{obj}/{site}")[0]
        push = tf.rotate(w.locate(obj)[1], [0.0, 1.0, 0.0])        # into the front of the counter
        fwd, left, level = self._frame(push)
        self.stand_before(p, fwd)
        h = self.HAND
        self.grip(h, 1.0, 0.4)                                     # a closed hand: the fingertips press
        pre = p - fwd * (self.TIP + 0.06)
        self.reach(h, pre, level)
        # the fingertips brought to the cap 1 cm short of it (the arm sags: aimed again by the error), then in through
        # the button's travel (`travel` of the control, 4 mm, and a little more: the aim grows by what the cap holds back)
        travel = float(w.objects[obj]["meta"]["controls"][control].get("travel", 0.004))
        self.reach(h, p - fwd * (self.TIP + 0.010), level, seconds=0.6, tries=3, tol=0.004)
        self.reach(h, p - fwd * (self.TIP - travel - 0.004), level, seconds=0.6, tries=3, tol=0.003)
        self.stand(0.4)
        self.reach(h, pre, level, seconds=0.6, tries=1)
        self.arm_home(h)
        self.grip(h, 0.0, 0.4)
        on = w.objects[obj]["meta"].get("burners")
        return self._result("ok", "ok")

    def lean(self, pitch: float, height: float, seconds: float = 1.0) -> None:
        """Lean the torso (`pitch`, + forward) and set the pelvis height, smoothly, standing."""
        _, hold = self.mirror.hold()
        if abs(float(hold[4]) - pitch) < 1e-6 and abs(float(hold[2]) - height) < 1e-6:
            return
        n = max(int(round(seconds / CONTROL_DT)), 1)
        rows = []
        for k in range(1, n + 1):
            s = k / n
            s = s * s * (3.0 - 2.0 * s)
            r = hold.copy()
            r[4] = hold[4] + (pitch - hold[4]) * s
            r[2] = hold[2] + (height - hold[2]) * s
            rows.append(r)
        self._rows(rows)
        self.stand(0.4)

    def upright(self) -> None:
        self.lean(0.0, STAND_HEIGHT)

    def reach_leaning(self, side: str, pos, quat, seconds: float = 1.2, free=None) -> float:
        """`reach`, and if it misses by more than `LEAN_ERR`, again leaning forward and lower (`LEAN_PITCH`,
        `LEAN_HEIGHT`): a spot low over a counter is out of the upright arm's reach."""
        err = self.reach(side, pos, quat, seconds, free=free)
        if err > LEAN_ERR and abs(float(self.mirror.hold()[1][4]) - LEAN_PITCH) > 1e-6:
            self.lean(LEAN_PITCH, LEAN_HEIGHT)
            err = self.reach(side, pos, quat, seconds, free=free)
        return err

    def pick(self, obj: str, **kw):
        from robosafebench.sim import tf
        w = self.world
        grips = w.objects[obj]["meta"].get("grips") or {}
        site = sorted(grips)[0] if grips else None
        g = w.locate(f"{obj}/{site}")[0] if site else w.locate(obj)[0]
        c = w.locate(obj)[0]
        a = (c - g)[:2] if site else (c[:2] - self.pose()[:2])
        if float(np.linalg.norm(a)) < 1e-3:
            # a grip on the thing's own axis (a ball, a jar, a bottle): the level side grasp, from where the robot stands,
            # at the height of the middle of the thing (the site may sit on its top)
            a = c[:2] - self.pose()[:2]
            g = c.copy()
        fwd, left, level = self._frame(a)
        self.stand_before(g, fwd, beside=kw.get("grasp_beside_m"))
        h = self.HAND
        self.__dict__["_safe_transfer"] = bool(kw.get("safe_transfer", False))
        self.__dict__["_empty_transfer_posture"] = None
        self.grip(h, 0.0, 0.3)
        free = None
        pregrasp = float(kw.get("pregrasp_m", 0.10))
        if self.reach(h, g - fwd * pregrasp, level) > PICK_SHORT:
            # short of the spot behind the grip (a grip low over a counter): the fingers may pitch about the direction
            # they close in, and the body leans forward and lower if the arm is short of it still
            free = left
            if site:                                        # where the grip is now (the arm may have nudged the thing)
                g, c = w.locate(f"{obj}/{site}")[0], w.locate(obj)[0]
                if float(np.linalg.norm((c - g)[:2])) >= 1e-3:
                    fwd, left, level = self._frame((c - g)[:2])
                    free = left
            self.reach_leaning(h, g - fwd * pregrasp, level, free=free)
            if site:
                g = w.locate(f"{obj}/{site}")[0]
        self.reach(h, g + fwd * 0.005, level, seconds=0.8, free=free)
        self.grip(h, 1.0, 0.8)
        self.stand(0.4)
        if w.held_by.get(h) != obj:
            self.grip(h, 0.0, 0.3)
            self.upright()
            raise DriverError(f"pick({obj!r}): the hand did not take hold of it (holding {w.held_by.get(h)!r})")
        now = self.tcp(h)[0]
        # taken with the fingers pitched (`free`): it is carried and put down as the hand holds it, turned only about
        # the vertical with the body (a heavy thing held by a thin handle slips out of a hand that turns it level)
        self.__dict__["_held_tilt"] = None if free is None else self._tilt(h, level)
        self.reach(h, now + np.array([0.0, 0.0, 0.06]), self._held_quat(level), seconds=0.8, tries=2)
        self.upright()
        if self.__dict__.get("_safe_transfer", False) and w.held_by.get(h) != obj:
            raise DriverError(f"pick({obj!r}): the grasp was lost while lifting")
        self.carry(h, level)
        if self.__dict__.get("_safe_transfer", False) and w.held_by.get(h) != obj:
            raise DriverError(f"pick({obj!r}): the grasp was lost while drawing the load in")
        return self._result("ok", "ok", holding=obj)

    def carry(self, h: str, level) -> None:
        """The held thing drawn in before the chest for walking, narrow enough for a doorway: of the places for its
        middle in `CARRY_SPOTS` (ahead of the pelvis axis, to the working hand's side, the hand's height), the nearest to
        the axis that the arm reaches with the hand held as it took the thing; failing all, the hand 0.30 m ahead and
        `BESIDE` to the side."""
        w = self.world
        x, y, yaw = self.pose()
        fwd, left, lv = self._frame([math.cos(yaw), math.sin(yaw)])
        side = -1.0 if h == "right" else 1.0
        now = self.tcp(h)[0]
        held = w.held_by.get(h)
        off = (w.locate(held)[0] - now) if held else np.zeros(3)      # the thing's middle from the pinch point
        quat = self._held_quat(lv)
        base = np.array([x, y, 0.0])
        to = base + fwd * 0.30 + left * side * self.BESIDE
        to[2] = max(float(now[2]), CARRY_Z)
        safe = self.__dict__.get("_safe_transfer", False)
        spots = TRANSFER_SPOTS if safe else CARRY_SPOTS
        found = False
        for ahead, aside, z in sorted(spots, key=lambda c: (math.hypot(c[0], c[1]), abs(c[2] - CARRY_Z))):
            cand = base + fwd * ahead + left * side * aside - np.array([off[0], off[1], 0.0])
            cand[2] = z
            if not safe and float((cand - base) @ fwd) < CARRY_HAND_AHEAD:
                continue                    # the hand itself no nearer the body (a long thing held by its end)
            q, pe, re = self.arm_ik(h, cand, quat, iters=120)
            # In safe-transfer mode the actual arm AND load geometry replaces
            # the forward-only heuristic. Keep the footprint small enough for
            # the scene's 0.90 m door and the existing planner margin.
            clear = not safe
            if safe and pe < 0.01 and re < 0.05 and self._transfer_self_clear(h, q, max_radius=0.39):
                start = w.data.qpos[w._ix[h]["_arm_qadr"]].copy()
                clear = all(self._transfer_self_clear(h, start + (q - start) * s)
                            for s in np.linspace(0.1, 1.0, 10))
            if pe < 0.01 and re < 0.05 and clear:
                to = cand
                found = True
                break
        if safe and not found:
            raise DriverError("carry: no self-clear transfer posture")
        if safe:
            # Use the checked joint-space path. Re-solving after an unrelated
            # upward excursion can pick a different elbow branch or never lower
            # to the pose that was checked.
            self.arm_to(h, q, seconds=1.6)
            self.arm_to(h, q, seconds=0.3)
            return
        # up first, where it is (out of whatever it was taken from: a block, a rack), then across to the carrying place
        up = now.copy()
        up[2] = max(float(now[2]) + CARRY_UP, float(to[2]))
        self.reach(h, up, quat, seconds=0.8, tries=1)
        self.reach(h, np.array([to[0], to[1], up[2]]) if up[2] > to[2] + 1e-6 else to, quat, seconds=1.0, tries=2)

    def _transfer_self_clear(self, hand: str, q, max_radius: float | None = None) -> bool:
        """Scratch collision check of the working arm against the other arm/body.

        A centimetre is a planner allowance for tracking error, not a contact or
        damage exemption. MuJoCo's physical exclusion pairs remain in force.
        Every model option is restored before a real control row can run.
        """
        import mujoco
        from robosafebench.sim import tf
        w, log = self.world, self.mirror.contact_log
        m, d = w.model, self.__dict__.get("_transfer_data")
        if d is None:
            d = self.__dict__["_transfer_data"] = mujoco.MjData(m)
        part = list(log.parts).index(hand)
        d.qpos[:] = w.data.qpos
        d.qpos[w._ix[hand]["_arm_qadr"]] = q
        mujoco.mj_kinematics(m, d)
        held = w.held_by.get(hand)
        if held:
            rel = tf.compose(tf.inverse(self.tcp(hand)), w.locate(held))
            site = w._ix[hand]["tcp_site"]
            tool = (d.site_xpos[site].copy(), tf.mat_to_quat(d.site_xmat[site].reshape(3, 3)))
            pos, quat = tf.compose(tool, rel)
            adr = int(m.jnt_qposadr[m.body_jntadr[w.objects[held]["body_id"]]])
            d.qpos[adr:adr + 3], d.qpos[adr + 3:adr + 7] = pos, quat
        flags, margin = int(m.opt.enableflags), float(m.opt.o_margin)
        try:
            m.opt.enableflags = flags | int(mujoco.mjtEnableBit.mjENBL_OVERRIDE)
            m.opt.o_margin = 0.01
            mujoco.mj_kinematics(m, d)
            mujoco.mj_collision(m, d)
        finally:
            m.opt.enableflags, m.opt.o_margin = flags, margin
        for c in d.contact:
            if c.dist >= 0.01:
                continue
            a, b = int(c.geom1), int(c.geom2)
            pa, pb = log.gpart[a], log.gpart[b]
            if pa >= 0 and pb >= 0 and pa != pb and part in (pa, pb):
                return False
            if held:
                for load, other in ((a, b), (b, a)):
                    if (w._geom_owner[load] == held and log.gpart[other] >= 0
                            and int(m.geom_bodyid[other]) not in w._hand_bodies):
                        return False
        if max_radius is not None:
            centre = w.base_pose()[:2]
            radius = float(max(np.hypot(*p) for p in w.base["footprint"]))
            for g in range(m.ngeom):
                if w._geom_owner[g] == "robot" and int(m.geom_bodyid[g]) != w._base_body and int(m.geom_group[g]) <= 3:
                    pts = d.geom_xpos[g] + B._geom_points(w, g) @ d.geom_xmat[g].reshape(3, 3).T
                    radius = max(radius, float(np.max(np.linalg.norm(pts[:, :2] - centre, axis=1))) + .005)
            if held:
                lo, hi = [], []
                for g in w._object_geoms[held]:
                    rot = d.geom_xmat[g].reshape(3, 3)
                    mid = d.geom_xpos[g] + rot @ m.geom_aabb[g, :3]
                    half = np.abs(rot) @ m.geom_aabb[g, 3:]
                    lo.append(mid - half); hi.append(mid + half)
                low, high = np.min(lo, axis=0), np.max(hi, axis=0)
                radius = max(radius, max(float(np.linalg.norm(np.array([x, y]) - centre))
                                        for x in (low[0], high[0]) for y in (low[1], high[1])))
            if radius > max_radius:
                return False
        return True

    def _tilt(self, h: str, level):
        """The hand's orientation now relative to the level frame `level` it was aiming at."""
        from robosafebench.sim import tf
        z3 = np.zeros(3)
        return tf.compose(tf.inverse((z3, level)), (z3, self.tcp(h)[1]))[1]

    def _held_quat(self, level):
        """`level`, or, for a thing taken with the fingers pitched, the hand as it took it, turned to `level`'s heading."""
        from robosafebench.sim import tf
        tilt = self.__dict__.get("_held_tilt")
        return level if tilt is None else tf.compose((np.zeros(3), level), (np.zeros(3), tilt))[1]

    def place(self, target, **kw):
        w = self.world
        h = self.HAND
        held = w.held_by.get(h)
        if held is None:
            raise DriverError("place: the hand holds nothing")
        spot = self.where(target)
        if self.__dict__.get("_safe_transfer", False):
            return self._place_transfer(spot, held, kw.get("support"))
        x, y, _ = self.pose()
        fwd, left, level = self._frame(spot[:2] - np.array([x, y]))
        tcp = self.tcp(h)[0]
        pos = w.locate(held)[0]
        lead = float(np.linalg.norm((pos - tcp)[:2]))             # the thing's middle this far ahead of the hand
        drop = float(tcp[2] - w.box(held)[0][2])                   # the hand this far above the thing's bottom
        hand_at = np.asarray(spot, dtype=np.float64) - fwd * lead
        self.stand_before(hand_at, fwd)
        level = self._held_quat(self._frame(fwd)[2])
        self.reach_leaning(h, hand_at + np.array([0.0, 0.0, drop + 0.05]), level)
        self.reach(h, hand_at + np.array([0.0, 0.0, drop + 0.005]), level, seconds=0.8, tries=2)
        self.grip(h, 0.0, 0.5)
        self.stand(0.3)
        now = self.tcp(h)[0]
        self.reach(h, now + np.array([0.0, 0.0, 0.08]) - fwd * 0.05, level, seconds=0.8, tries=1)
        self.upright()
        self.arm_home(h)
        self.__dict__["_held_tilt"] = None
        return self._result("ok", "ok")

    def _place_transfer(self, spot, held, support):
        """Move the actual purse above its support, then lower it before release.

        A nominal TCP offset is insufficient after a pitched grasp and gravity
        sag. Use bounded translations of the measured load centre and bottom.
        The old 15 cm intermediate lift could exceed this arm's workspace.
        Neither these waypoints nor their tolerances alter contact grading.
        """
        from robosafebench.sim import tf
        w, hand = self.world, self.HAND
        spot = np.asarray(spot, dtype=np.float64)
        if support not in w.objects or not w.objects[support]["fixed"]:
            raise DriverError("place: the transfer needs its named fixed support")
        support_low, support_high = w.box(support)
        fwd, left, level = self._frame(spot[:2] - self.pose()[:2])
        lead = float(np.linalg.norm((w.locate(held)[0] - self.tcp(hand)[0])[:2]))
        hand_at = spot - fwd * lead
        side = -1.0 if hand == "right" else 1.0
        for ahead in (self.AHEAD, 0.40, 0.44, 0.48):
            stance = hand_at[:2] - fwd[:2] * ahead - left[:2] * side * self.BESIDE
            yaw = math.atan2(fwd[1], fwd[0])
            if B.hits(w, [float(stance[0]), float(stance[1]), yaw], clearance=B.MARGIN) is None:
                break
        else:
            raise DriverError("place: no clear body stance outside the support")
        self.stand_before(hand_at, fwd, ahead=ahead)
        self.stand()
        self.__dict__["_transfer_placing"] = True
        self.__dict__["_transfer_waypoints"] = [self.mirror.command("whole_body")[self.ARM_COLS[hand]].copy()]

        def state():
            if w.held_by.get(hand) != held:
                raise DriverError("place: the purse left the hand before reaching its support")
            return w.locate(held)[0], float(w.box(held)[0][2] - spot[2])

        def fully_over_support():
            low, high = w.box(held)
            return bool(np.all(low[:2] >= np.asarray(support_low[:2]) + 0.005)
                        and np.all(high[:2] <= np.asarray(support_high[:2]) - 0.005))

        def step(delta, lowering=False):
            now, quat = self.tcp(hand)
            delta = np.asarray(delta, dtype=np.float64)
            limit = 0.012 if lowering else 0.04
            delta *= min(1.0, limit / max(float(np.linalg.norm(delta)), 1e-9))
            # Keep the real grasp's orientation where possible. If that IK
            # branch is unavailable, a checked gradual level turn is another
            # physical control, with the hold checked again on the next step.
            rotation = float(np.linalg.norm(tf.rotvec(quat, level)))
            gentle = tf.slerp(quat, level, min(1.0, 0.1 / max(rotation, 1e-9)))
            orientations = (quat, gentle) if lowering else (quat, tf.slerp(quat, level, 0.5), level)
            for aim_quat in orientations:
                try:
                    return self.reach(hand, now + delta, aim_quat, seconds=1.6 if lowering else 0.8, tries=2, tol=0.006)
                except DriverError:
                    pass
            raise DriverError("place: no clear bounded load step; keeping the grip closed")

        def raise_load():
            for _ in range(12):
                _, gap = state()
                if gap >= 0.06:
                    return
                step([0.0, 0.0, 0.07 - gap])
            raise DriverError("place: load has not cleared the support edge")

        raise_load()
        for _ in range(20):
            centre, _ = state()
            error = spot[:2] - centre[:2]
            if float(np.linalg.norm(error)) < 0.012:
                break
            raise_load()
            step([error[0], error[1], 0.0])
        else:
            raise DriverError("place: the purse is not above the intended support")
        for _ in range(24):
            centre, gap = state()
            error = spot[:2] - centre[:2]
            # Once the actual load is down and fully over the requested
            # support, release it. Do not drag a supported purse to chase the
            # nominal spot after a small grip/sag displacement.
            if -0.01 <= gap <= 0.008 and fully_over_support():
                break
            if gap <= 0.02 and not fully_over_support():
                raise_load()
            step([error[0], error[1], 0.004 - gap], lowering=True)
        else:
            raise DriverError("place: the purse is not supported; keeping the grip closed")
        self.grip(hand, 0.0, 0.5)
        self.stand(0.3)
        # Empty-hand withdrawal reverses the measured placing route. Its
        # start is the narrow carry posture, not the ordinary rest command
        # whose straight path can cross the torso from this IK branch.
        self._transfer_withdraw(hand)
        self.__dict__["_held_tilt"] = None
        self.__dict__["_safe_transfer"] = False
        self.__dict__["_transfer_placing"] = False
        self.__dict__["_transfer_waypoints"] = None
        return self._result("ok", "ok")

    def _transfer_withdraw(self, hand):
        """Return the empty arm along checked waypoints to its carry posture."""
        waypoints = self.__dict__["_transfer_waypoints"]
        # The last target is already in force. Do not re-chase that loaded
        # servo target after opening the grip; start toward the previous
        # waypoint and check that path from the arm's current measured pose.
        for q in reversed(waypoints[:-1]):
            actual = self.world.data.qpos[self.world._ix[hand]["_arm_qadr"]].copy()
            if not all(self._transfer_self_clear(hand, actual + (q - actual) * s)
                       for s in np.linspace(0.1, 1.0, 10)):
                raise DriverError("place: no clear reverse path for the empty arm")
            current = self.mirror.command("whole_body")[self.ARM_COLS[hand]]
            self.arm_to(hand, q, max(1.0, 10.0 * float(np.max(np.abs(q - current)))))
            self.arm_to(hand, q, 0.3)
        q = waypoints[0]
        if not self._transfer_self_clear(hand, q, max_radius=0.39):
            raise DriverError("place: empty carry posture is not clear and compact")
        self.__dict__["_empty_transfer_posture"] = q.copy()
