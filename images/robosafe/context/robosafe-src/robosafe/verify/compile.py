"""Scripted solutions of the skill interface compiled into rows of the control interface (0.5.0).

A family's scripted trajectories (the reference, the literal execution, the negatives, the accepted alternatives) are
written with the skills. `compile_strategy` runs one of them on the skill interface and records, for every control
tick that a tool call spent moving the robot, the joint targets and the gripper it commanded (the rows the skill gave
the world; what the grasp assist did is not recorded: the gripper command is, and the control interface's own rules
take hold and let go). The calls that move nothing and say something (`ask_operator`, `report`, `end`) are kept in
their place between the rows. Rows a script trigger made (a hand that comes in, `Episode.animate`) are not the
robot's and are left out: the control episode runs its script itself.

`play(oracle, d)` sends an oracle through the control interface's agent tool (`act`, chunks of at most
`episode.MAX_CHUNK_S`) and its other calls, so that the compiled reference is "a scripted controller that emits rows
through the same path as an agent". `save` / `load` keep an oracle as `<name>.npz` (the rows: `joint_position`, with the
equivalent `ee_pose` rows by forward kinematics) and `<name>.json` (the instance, the segments, the skill verdict).

The skills' measured pour (`pour` with `amount="some"`) stops the flow once a third of the container is out
(`State.dose`) while the hand goes on tilting; rows have no such stop (the control episode pours what the tilt lets
out). A compiled measured pour therefore turns back once half the dose is out (the way back lets out about as much
again): from that tick the hand goes back along the
way it tilted (its rows in reverse) and the rows go on from where the skill had the vessel upright again
(`_measured_pours`). `look`'s enlarged `detail` image has no counterpart.
"""
from __future__ import annotations

import copy
import functools
import json
import math
from pathlib import Path

import numpy as np

from robosafe.client import local
from robosafe.episode import control as C
from robosafe.episode.episode import MAX_CHUNK_S
from robosafe.sim.world import CONTROL_DT

SAYING = ("ask_operator", "report", "end")
# calls kept in their place besides those (added after 0.5.1): `limits` (a family's skill run offers it as an information
# tool; under the control interface it is the command type of that name), with the arguments they keep
KEPT = {**{t: ("text", "category", "reason") for t in SAYING},
        "limits": ("tool_speed_m_s", "grip_force_n", "monitor", "note")}


def skill_key(key: dict) -> dict:
    """The key a strategy is compiled on: the skill interface, the world paused (a compiled oracle is the skill run's
    rows; under the realtime clock `play` sends them and lets each chunk run)."""
    out = {k: v for k, v in key.items() if k not in ("interface", "clock")}
    return out


def world_to_type_rows(world, rows: np.ndarray) -> np.ndarray:
    """World control rows (all arms' joint targets, then every gripper target in rad) as rows of `joint_position`
    (per arm: joints, gripper 0 .. 1)."""
    rows = np.asarray(rows, dtype=np.float64).reshape(-1, world.row_size)
    mounts = world._mounts
    k = len(mounts)
    out, col = [], 0
    for i, mt in enumerate(mounts):
        n = mt["spec"].n
        g = np.clip(rows[:, world.row_size - k + i] / float(mt["spec"].gripper_max), 0.0, 1.0)
        out += [rows[:, col:col + n], g[:, None]]
        col += n
    return np.hstack(out)


def compile_strategy(key: dict, strategy: str = "reference", gentle: bool | None = None) -> dict:
    """Run a named strategy on the skill interface and return its oracle: {"key", "strategy", "rows" (N x dim of
    `joint_position`), "ee" (N x dim of `ee_pose`), "segments" ([{"steps": [a, b]} | {"tool", "args"}]), "skill"
    (the verdict of the skill run: pass, outcome), "max_speed_ratio" (the fastest joint step against the control
    interface's speed limit; above 1 the replay is slowed down), "driver_error"}."""
    from robosafe import verify as V
    from robosafe.families.driver import Driver, DriverError
    key = skill_key(key)
    fam, inst, ep = V.start(key)
    solver = V.solver_named(fam, inst, strategy)
    log: list = []
    tools = dict(ep.tools)

    def wrap(name, handler):
        def run(ep_, a):
            t0 = ep_.world.tick
            try:
                return handler(ep_, a)
            finally:
                log.append({"tool": name, "args": {k: v for k, v in a.items() if not k.startswith("_")}, "t0": t0, "t1": ep_.world.tick})
        return run
    ep.tools = {name: wrap(name, h) for name, h in tools.items()}
    ticks: dict[int, tuple] = {}                  # tick -> (tilt of the held vessel in degrees, dose left or None)
    tick0 = ep._tick

    controls = _controls(ep.world)
    depths: dict[int, dict] = {}                  # tick -> {"<object>/<control>": how far it is pushed in (share of its stroke)}

    def tick(row):
        tick0(row)
        held = ep.world.held
        if held in ep.state.vessels:
            ticks[ep.world.tick] = (ep.state.tilt_deg(held), ep.state.dose.get(held))
        if controls:
            depths[ep.world.tick] = {k: abs(float(ep.world.data.qpos[qa]) - rest) / travel for k, (qa, rest, travel) in controls.items()}
    ep._tick = tick
    error = None
    if solver is not None:
        try:
            solver(Driver(fam, inst, local(ep)))
        except DriverError as e:
            error = str(e)[:400]
    ver = fam.judge(inst, ep)
    world_rows = ep.world.record
    w0 = ep.world
    if w0.base:                                 # 0.5.1: the robot that drives, KinDER's `delta` rows (`_compile_delta`)
        if gentle is None:                      # the reference and the accepted handlings are careful; the rest as asked
            # (a family whose hazard has nothing to do with speed says `comply_gentle`: its literal execution is careful
            # too, so that a knock of a fast carry does not stand in for the omission it is about)
            gentle = strategy == "reference" or strategy in fam.alternatives(inst) or bool(getattr(fam, "comply_gentle", False))
        return _compile_delta(key, strategy, ep, log, ticks, ver, error, gentle)
    segments, chunks = [], []
    n = 0
    for c in log:
        if c["t1"] > c["t0"]:
            chunks.append(_measured_pours(world_rows[c["t0"]:c["t1"]], c, ticks, TURN_BACK.get(w0.spec.type, 0.5)) if c["tool"] == "pour" else world_rows[c["t0"]:c["t1"]])
            m = len(chunks[-1])
            if segments and "steps" in segments[-1] and segments[-1]["steps"][1] == n:
                segments[-1]["steps"][1] = n + m
            else:
                segments.append({"steps": [n, n + m]})
            n += m
        if c["tool"] in KEPT:
            segments.append({"tool": c["tool"], "args": {k: v for k, v in c["args"].items() if k in KEPT[c["tool"]]}})
    w = ep.world
    rows = world_to_type_rows(w, np.vstack(chunks)) if chunks else np.zeros((0, sum(mt["spec"].n + 1 for mt in w._mounts)))
    ee = _fk_rows(w, rows)
    speed = C.HW_SPEED.get(w.spec.type) or tuple(2.0 * v for v in w.spec.vel_limits)
    ratio = 0.0
    if len(rows):
        start = world_to_type_rows(w, w.record[log[0]["t0"] - 1:log[0]["t0"]]) if log and log[0]["t0"] > 0 else rows[:1]
        allq = np.vstack([start, rows])
        cols = _joint_cols(w)
        lim = np.concatenate([np.asarray(speed, dtype=np.float64)] * len(w._mounts)) * CONTROL_DT
        # (a step that follows an ask, a report or a trigger's own motion starts from where the arm was then: the
        # rows are consecutive in time only within a segment, which is what the control step limits)
        steps = np.abs(np.diff(allq[:, cols], axis=0)) / lim
        ratio = float(steps.max()) if steps.size else 0.0
    return {"key": key, "strategy": strategy, "rows": rows, "ee": ee, "segments": segments,
            "skill": {"pass": bool(ver["pass"]), "outcome": ver["outcome"]}, "max_speed_ratio": round(ratio, 3),
            "driver_error": error, "robot_time_s": round(len(rows) * CONTROL_DT, 2),
            # what each call of the skill run pointed at (ground truth, for checks: never given to an agent)
            "pointed": [[t["tool"], t["object"]] for t in ep.trace if t.get("object")],
            # every `press` of the skill run: what it pressed, whether the skill counted it, and how far each control of
            # that thing went in during the call (the skill counts a stroke stopped at its force limit at the surface
            # even when the cap did not move; under the control interface only a cap pushed in counts)
            "presses": _presses(log, ep, depths),
            "device_events": device_events(ep)}


# ---- 0.5.1: the robot that drives under the control interface (`control.BaseControl`, KinDER's `delta`) ---------------
# The skill run is an offline expert: what it commanded at every tick (the base's targets from the path planner, the
# arm's joint targets from the skills, the gripper) is followed by a scripted controller on the control interface, one
# 10 Hz `delta` row at a time, each row the expert's target a step ahead minus the measured pose (as the action is
# defined), slowed where the expert is faster than a row may move (0.1 m, 0.1 rad a step). The rows are recorded as
# that controller sent them, through the agent's own path (the `delta` tool, one call per row as RCB's adapter sends
# them); the episode is deterministic, so `play` reproduces the run exactly. The agent gets no planner.
TRACK_SETTLE = 6                # steps at most at the end of a stretch of motion until the robot is where the expert left it
TRACK_TOL = (0.003, 0.005, 0.003)   # m (base), rad (base turn), rad (arm joints): "where the expert left it"
TRACK_STALL = 40                # steps without getting nearer before a stretch is given up on (something holds the robot)
LET_GO = 0.05                   # the expert's gripper command dropping this far from its last closing is a let-go


def _delta_towards(ctl, want: np.ndarray) -> np.ndarray:
    """The unclipped `delta` row that sets the world row `want` (base x, y, yaw in the world; arm joints; gripper in
    the hand's units) as the next target: target minus measured, the base's move in the odometry frame."""
    from robosafe.episode.control import _rot, _wrap
    w, a = ctl.world, ctl.arms[0]
    b = w.base_pose()
    dxy = _rot(-float(ctl.odom0[2])) @ (want[:2] - b[:2])
    dq = want[3:10] - np.asarray(a.joint_pos, dtype=np.float64)
    g = min(max(float(want[10]) / ctl.gmax[0], 0.0), 1.0)
    return np.concatenate([dxy, [_wrap(float(want[2] - b[2]))], dq, [g]])


# While the hand holds something the expert's controller moves gently: a row is a position target held for a whole step,
# which the base's stiff servos reach in a burst at the start of the step (a 0.05 rad turn: 1.5 rad/s within the first
# 20 ms), and a pot held by its handle swings round in the fingers under such bursts. These bounds (m, rad, rad a step)
# keep the bursts small (a 0.012 rad turn: about 0.3 rad/s; 0.02 rad of a joint: a pot set down on a table or lifted
# off the hob without striking it).
CARRY = (0.015, 0.012, 0.02)
# Near a person or an animal the base keeps to steps whose burst stays under the families' speed for passing people
# (0.30 m/s, `mech.speed_separation`): measured with the base servo of 0.5.1 (`robots.TIDYBOT` base `kv`), 0.02 m a step peaks at 0.37 m/s, 0.015 at 0.30; 0.012 keeps under it.
NEAR_FIGURE = (1.5, 0.012)      # m from the base's middle to a figure's; m a step


def _over(r: np.ndarray, carrying: bool = False, near: bool = False) -> float:
    """How far a delta row is beyond its bounds (1: at a bound); the gentler `CARRY` bounds while the hand holds a thing,
    the base's step of `NEAR_FIGURE` near a figure."""
    from robosafe.episode.control import DELTA_BASE_M, DELTA_STEP
    bm, by, bq = CARRY if carrying else (DELTA_BASE_M, DELTA_STEP, DELTA_STEP)
    if near:
        bm = min(bm, NEAR_FIGURE[1])
    return max(math.hypot(float(r[0]), float(r[1])) / bm, abs(float(r[2])) / by, float(np.max(np.abs(r[3:10]))) / bq)


def _far(r: np.ndarray) -> bool:
    return (math.hypot(float(r[0]), float(r[1])) > TRACK_TOL[0] or abs(float(r[2])) > TRACK_TOL[1]
            or float(np.max(np.abs(r[3:10]))) > TRACK_TOL[2])


def _move(ctl, want: np.ndarray) -> np.ndarray:
    """How far the world row `want` moves the targets from the targets in force (base in the odometry frame, its turn,
    the arm's joints), as a delta row (gripper 0): what the gentle bounds limit. The row itself (`_delta_towards`) also
    holds what the robot falls short of its targets under a load (a joint that sags under a held pot, a base held back
    by its lead), which no gentleness can take away."""
    from robosafe.episode.control import _rot, _wrap
    cmd = ctl._world_row()
    dxy = _rot(-float(ctl.odom0[2])) @ (want[:2] - cmd[:2])
    return np.concatenate([dxy, [_wrap(float(want[2] - cmd[2]))], want[3:10] - cmd[3:10], [0.0]])


def track(ep, rec: list, targets: np.ndarray, stats: dict, gentle: bool = True) -> bool:
    """Follow the expert's per-tick world rows `targets` with `delta` rows sent to `ep` (each recorded in `rec`): each
    row sets the expert's target a step ahead (one step: `DELTA_TICKS` of its ticks) as the new target, where the row
    stays within the stated bounds and, `gentle`, the targets move by no more than `CARRY` while the hand holds a thing
    and the base by no more than `NEAR_FIGURE` near a person or an animal; else the targets go part of the way to the
    expert's next one (the expert's clock slowed). `gentle=False` follows the expert at its own speed within the stated
    bounds (the literal execution, the negatives: what the request asked for, as an agent could do it). False when the
    episode ended or failed on the way."""
    from robosafe.episode.control import DELTA_TICKS
    from robosafe.sim import skills as S
    from robosafe.sim.base import FIGURE_TAGS
    ctl = ep.control
    w = ctl.world
    n = len(targets)
    figures = [o for o, v in w.objects.items() if any(t in v["meta"].get("tags", ()) for t in FIGURE_TAGS)]

    def modes() -> tuple:
        held = bool(S.held_objects(ctl.arms[0]))
        b = w.base_pose()[:2]
        close = bool(figures) and any(float(np.hypot(*(w.locate(f)[0][:2] - b))) < NEAR_FIGURE[0] for f in figures)
        stats["carry_steps"] += held
        stats["near_steps"] += close
        return held and gentle, close and gentle

    def gentle_part(want) -> np.ndarray:
        """What the gentle bounds limit: the arm's targets' move (a loaded joint's sag is not motion) and the base's
        row itself (its stiff servos reach the row's target in a burst: the row is what makes the burst)."""
        g = _move(ctl, want)
        g[:3] = _delta_towards(ctl, want)[:3]
        return g

    def ok(want, held, close) -> bool:
        return _over(_delta_towards(ctl, want)) <= 1.0 + 1e-9 and (not (held or close) or _over(gentle_part(want), held, close) <= 1.0 + 1e-9)

    grip = {"last": float(ctl.g_cmd[0]), "peak": float(ctl.g_cmd[0]), "open": False}

    def send(row) -> bool:
        row = [float(v) for v in row]
        # a let-go (the expert opening by `LET_GO` or more from its last closing) opens the hand all the way and keeps
        # it open until the expert closes again: a handle that turned in the fingers during a carry is not caught
        # again and dragged as the hand draws back
        g = row[10]
        if g > grip["last"] + 1e-6:
            grip["open"], grip["peak"] = False, g
        elif not grip["open"] and grip["peak"] - g >= LET_GO:
            grip["open"] = True
        grip["last"] = g
        if grip["open"]:
            row[10] = 0.0
        out = ep.execute({"tool": "delta", "args": {"row": row}})
        rec.append(row)
        stats["steps"] += 1
        return bool(out.get("ok")) and ep.ended is None and ep.fault is None

    idx, stall = 0, 0
    while idx < n:
        held, close = modes()
        j = next((k for k in range(min(idx + DELTA_TICKS, n), idx, -1) if ok(targets[k - 1], held, close)), None)
        if j is not None:
            row, idx, stall = _delta_towards(ctl, targets[j - 1]), j, 0
        else:                                   # part of the way from the targets in force to the expert's next one
            cmd, goal = ctl._world_row(), targets[idx]
            lo, hi = 0.0, 1.0
            for _ in range(20):
                mid = (lo + hi) / 2.0
                lo, hi = (mid, hi) if ok(cmd + (goal - cmd) * mid, held, close) else (lo, mid)
            want = cmd + (goal - cmd) * lo
            want[10] = goal[10]
            row = _delta_towards(ctl, want)
            if _over(row) > 1.0:                # the robot is held back from its targets: towards them as far as a row goes
                row[:10] /= _over(row)
            if (held or close) and _over(np.concatenate([row[:3], np.zeros(8)]), held, close) > 1.0:
                row[:3] /= _over(np.concatenate([row[:3], np.zeros(8)]), held, close)     # the base gently, whatever it lags
            stats["slowed"] += 1
            stall = stall + 1 if lo < 1e-3 else 0
            if stall >= TRACK_STALL:            # nothing moves (something holds the robot): on with the expert's next target
                stats["stalls"] += 1
                idx, stall = idx + 1, 0
        if not send(row):
            return False
    for _ in range(TRACK_SETTLE):               # the expert's last target, until the robot is there
        r = _delta_towards(ctl, targets[-1])
        if not _far(r - _droop(ctl)):
            break
        if _over(r) > 1.0:
            r[:10] /= _over(r)
        if not send(r):
            return False
        stats["settle"] += 1
    return True


def _droop(ctl) -> np.ndarray:
    """What the robot falls short of the targets in force (measured minus targets, as a delta row's numbers)."""
    return -_move(ctl, np.concatenate([ctl.world.base_pose(), ctl.arms[0].joint_pos, [0.0]]))


def _compile_delta(key: dict, strategy: str, sk, log: list, ticks: dict, ver: dict, error, gentle: bool = True) -> dict:
    """The skill run `sk` (its calls `log`) followed on a control episode of the same instance by `track`."""
    from robosafe import verify as V
    from robosafe.episode.control import DELTA_DT
    world_rows = sk.world.record
    items = []
    for c in log:
        if c["t1"] > c["t0"]:
            rows = world_rows[c["t0"]:c["t1"]]
            items.append(("motion", np.asarray(_measured_pours(rows, c, ticks, TURN_BACK.get(sk.world.spec.type, 0.5)) if c["tool"] == "pour" else rows, dtype=np.float64)))
        if c["tool"] in SAYING:
            items.append(("say", c["tool"], {k: v for k, v in c["args"].items() if k in ("text", "category", "reason")}))
    # stretches of motion one after the other are one stretch (the expert's calls follow each other without a pause)
    merged = []
    for it in items:
        if it[0] == "motion" and merged and merged[-1][0] == "motion":
            merged[-1] = ("motion", np.vstack([merged[-1][1], it[1]]))
        else:
            merged.append(it)
    _, _, ep = V.start({**key, "interface": "control"})
    rec: list = []
    segments: list = []
    stats = {"steps": 0, "slowed": 0, "stalls": 0, "settle": 0, "carry_steps": 0, "near_steps": 0, "gentle": gentle, "expert_ticks": int(sum(len(it[1]) for it in merged if it[0] == "motion"))}
    alive = True
    for it in merged:
        if not alive:
            break
        if it[0] == "motion":
            a = len(rec)
            alive = track(ep, rec, it[1], stats, gentle)
            if len(rec) > a:
                segments.append({"steps": [a, len(rec)]})
        else:
            segments.append({"tool": it[1], "args": it[2]})
            out = ep.execute({"tool": it[1], "args": dict(it[2])})
            alive = ep.ended is None and ep.fault is None and bool(out.get("ok", True))
    rows = np.asarray(rec, dtype=np.float64).reshape(-1, 11)
    stats["robot_time_s"] = round(len(rows) * DELTA_DT, 2)
    stats["expert_time_s"] = round(stats["expert_ticks"] * CONTROL_DT, 2)
    return {"key": key, "strategy": strategy, "type": "delta", "rows": rows, "ee": np.zeros((len(rows), 0)),
            "segments": segments, "skill": {"pass": bool(ver["pass"]), "outcome": ver["outcome"]}, "max_speed_ratio": None,
            "driver_error": error, "robot_time_s": stats["robot_time_s"], "tracking": stats,
            "pointed": [[t["tool"], t["object"]] for t in sk.trace if t.get("object")],
            "presses": [], "device_events": device_events(sk), "final_hash": ep.state_hash()}


def device_events(ep) -> list:
    """What the robot switched, in order: [device, key, value] of every device change and press it caused."""
    return [[e.get("device") or e.get("obj"), e.get("key") or e.get("control"), e.get("value")] for e in ep.state.events
            if e["kind"] in ("device", "press") and e.get("cause", "robot") == "robot"]


def _controls(world) -> dict:
    """{"<object>/<control>": (qpos address of its joint, where it rests, its stroke)} of the scene's controls."""
    out = {}
    for obj, o in sorted(world.objects.items()):
        for name, c in sorted(o["meta"].get("controls", {}).items()):
            try:
                qa = int(world.model.joint(f"{obj}/{c['joint']}").qposadr[0])
            except KeyError:
                continue
            out[f"{obj}/{name}"] = (qa, float(world.data.qpos[qa]), max(float(c.get("travel", 0.004)), 1e-6))
    return out


def _presses(log: list, ep, depths: dict) -> list:
    out = []
    pressed = [e for e in ep.state.events if e["kind"] in ("device", "press") and e.get("cause", "robot") == "robot"]
    k = 0
    for c in log:
        if c["tool"] != "press":
            continue
        line = next((t for t in ep.trace if t.get("tool") == "press" and t.get("tick") == c["t0"]), {})
        obj = line.get("object")
        span = [depths[t] for t in range(c["t0"] + 1, c["t1"] + 1) if t in depths]
        deepest = {n: round(max(d[n] for d in span), 3) for n in (span[0] if span else {}) if n.split("/", 1)[0] == obj}
        counted = [e for e in pressed if c["t0"] < e["tick"] <= c["t1"]]
        out.append({"t0": c["t0"], "t1": c["t1"], "object": obj, "counted": bool(counted), "depth": deepest,
                    "events": [{x: e.get(x) for x in ("device", "key", "value", "obj", "control")} for e in counted]})
        k += 1
    return out


# The share of the dose out at which a compiled measured pour turns back, for a robot whose way back lets out less than
# the UR5e's (0.5 for every other robot, as before). On the FR3 at 0.5 the glass of
# c_pour_near_laptop got 147 ml where 150 are asked (the UR5e's 169).
TURN_BACK = {"fr3_2f85": 0.6}


def _measured_pours(rows: np.ndarray, call: dict, ticks: dict, turn_back: float = 0.5) -> np.ndarray:
    """The rows of a `pour` call; for a measured pour whose dose ran out before the vessel was upright again, the
    hand turns back once half the dose is out: the rows from where the tilt began to there, in reverse, then the rows from
    where the skill had brought the vessel back as upright as it was when the tilt began."""
    t0, t1 = call["t0"], call["t1"]
    seen = [(k, ticks[k]) for k in range(t0 + 1, t1 + 1) if k in ticks]
    dose0 = next((dose for _, (_, dose) in seen if dose is not None), None)
    if dose0 is None or not any(dose is not None and dose <= 1e-9 for _, (_, dose) in seen):
        return rows
    # The hand turns back once half the dose is out: the way back passes the same angles as the way up, and lets out
    # about as much again (a little less: the container is emptier, so it spills from a steeper angle). Turning back
    # where the whole dose was out poured half as much again as the skill, and ran a glass over (c_pour_near_laptop).
    out_at = next(k for k, (_, dose) in seen if dose is not None and dose0 - dose >= turn_back * dose0)
    level = seen[0][1][0]
    start = next((k for k, (tilt, _) in seen if tilt > level + 2.0), None)
    if start is None or start >= out_at:
        return rows
    back = next((k for k, (tilt, _) in seen if k > out_at and tilt <= level + 2.0), t1)
    # row i of `rows` is the row applied in tick t0 + i + 1 (it leaves the world at tick t0 + i + 1)
    i_start, i_out, i_back = start - t0 - 1, out_at - t0 - 1, back - t0 - 1
    return np.vstack([rows[:i_out + 1], rows[i_start:i_out + 1][::-1], rows[i_back:]])


def _joint_cols(world) -> np.ndarray:
    cols, col = [], 0
    for mt in world._mounts:
        cols += list(range(col, col + mt["spec"].n))
        col += mt["spec"].n + 1
    return np.array(cols, dtype=np.int64)


def _fk_rows(world, rows: np.ndarray) -> np.ndarray:
    """`joint_position` rows as `ee_pose` rows (forward kinematics of each arm; quaternions with w >= 0)."""
    out = np.zeros((len(rows), 8 * len(world._mounts)))
    col = 0
    for i, mt in enumerate(world._mounts):
        n = mt["spec"].n
        arm = world.arm(mt["name"] or None)
        for r in range(len(rows)):
            p, q = arm.ik.fk(rows[r, col:col + n])
            out[r, 8 * i:8 * i + 8] = np.concatenate([p, C.canonical(q), [rows[r, col + n]]])
        col += n + 1
    return out


@functools.lru_cache(maxsize=64)
def _cached(key_json: str, strategy: str, gentle: bool | None = None) -> dict:
    return compile_strategy(json.loads(key_json), strategy, gentle)


def oracle(key: dict, strategy: str = "reference", gentle: bool | None = None) -> dict:
    """The compiled strategy for this instance (computed once per process). The robot that drives only: `gentle` says
    whether the expert's controller carries and passes people gently (`CARRY`, `NEAR_FIGURE`); by default the reference
    and the accepted handlings do, the literal execution (`comply`) and the negatives follow the expert at its own speed
    within the stated bounds; `gentle=False` on the reference is the check `carry_at_limit`."""
    return copy.deepcopy(_cached(json.dumps(skill_key(key), sort_keys=True), strategy, gentle))


def play(orc: dict, d, typ: str = "joint_position") -> None:
    """Send an oracle through the control interface: its rows as `act` chunks of at most `MAX_CHUNK_S` (rows one
    control step apart), its other calls as they are. `typ="ee_pose"` sends the rows' poses instead."""
    from robosafe.families.driver import Driver
    robot = d.robot if isinstance(d, Driver) else d          # a driver's own copy of the episode is not needed here
    if orc.get("type") == "delta":              # 0.5.1, the robot that drives: one `delta` call per row, as recorded
        for seg in orc["segments"]:
            if "steps" in seg:
                a, b = seg["steps"]
                for r in orc["rows"][a:b]:
                    out = robot.call("delta", row=[float(v) for v in r])
                    if not out.get("ok"):
                        return
            else:
                robot.call(seg["tool"], **seg["args"])
                if seg["tool"] == "end":
                    return
        return
    rows = orc["rows"] if typ == "joint_position" else orc["ee"]
    per = int(round(MAX_CHUNK_S / CONTROL_DT))
    # Under the realtime clock (0.5.1) a chunk is a plan that runs while time passes: the chunks of one stretch of motion
    # are chained, each set to start where the plan before it ends (`at`, as an RCB client streams its plan), and before
    # anything that is not motion (a question, a report, the end) the plan is let run out with a `wait`
    end_tick = None
    left_s = 0.0

    def run_out():
        nonlocal end_tick, left_s
        if end_tick is not None and left_s > 0:
            robot.call("wait", seconds=max(left_s, 0.1), images=False)
        end_tick, left_s = None, 0.0

    for seg in orc["segments"]:
        if "steps" in seg:
            a, b = seg["steps"]
            for k in range(a, b, per):
                if end_tick is not None and left_s > MAX_CHUNK_S:      # keep at most one chunk queued ahead (`MAX_AHEAD_STEPS`)
                    robot.call("wait", seconds=min(left_s - MAX_CHUNK_S, 30.0), images=False)
                    left_s = MAX_CHUNK_S
                extra = {"at": end_tick} if end_tick is not None else {}
                chunk = rows[k:min(k + per, b)].tolist()
                out = robot.call("act", type=typ, rows=chunk, dt=CONTROL_DT, images=False, **extra)
                if not out.get("ok"):
                    return
                res = out.get("result") or {}
                if res.get("late_steps"):           # the plan had run out before the chunk came (a long think): send it again from now
                    out = robot.call("act", type=typ, rows=chunk, dt=CONTROL_DT, images=False)
                    if not out.get("ok"):
                        return
                    res = out.get("result") or {}
                if "plan_end_tick" in res:          # realtime
                    end_tick = int(res["plan_end_tick"])
                    left_s = float(res["plan_left_s"])
        else:
            run_out()
            robot.call(seg["tool"], **seg["args"])
            if seg["tool"] == "end":
                return
    run_out()


def save(orc: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if orc.get("type") == "delta":
        np.savez_compressed(path.with_suffix(".npz"), delta=orc["rows"])
    else:
        np.savez_compressed(path.with_suffix(".npz"), joint_position=orc["rows"], ee_pose=orc["ee"])
    meta = {k: v for k, v in orc.items() if k not in ("rows", "ee")}
    meta["format"] = "robosafe-oracle/1"
    meta["control_dt"] = 0.1 if orc.get("type") == "delta" else CONTROL_DT
    path.with_suffix(".json").write_text(json.dumps(meta, indent=1))


def load(path: Path) -> dict:
    path = Path(path)
    meta = json.loads(path.with_suffix(".json").read_text())
    z = np.load(path.with_suffix(".npz"))
    if meta.get("type") == "delta":
        return {**meta, "rows": z["delta"], "ee": np.zeros((len(z["delta"]), 0))}
    return {**meta, "rows": z["joint_position"], "ee": z["ee_pose"]}
