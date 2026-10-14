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
from pathlib import Path

import numpy as np

from robosafe.client import local
from robosafe.episode import control as C
from robosafe.episode.episode import MAX_CHUNK_S
from robosafe.sim.world import CONTROL_DT

SAYING = ("ask_operator", "report", "end")


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


def compile_strategy(key: dict, strategy: str = "reference") -> dict:
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
        if c["tool"] in SAYING:
            segments.append({"tool": c["tool"], "args": {k: v for k, v in c["args"].items() if k in ("text", "category", "reason")}})
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
def _cached(key_json: str, strategy: str) -> dict:
    return compile_strategy(json.loads(key_json), strategy)


def oracle(key: dict, strategy: str = "reference") -> dict:
    """The compiled strategy for this instance (computed once per process)."""
    return copy.deepcopy(_cached(json.dumps(skill_key(key), sort_keys=True), strategy))


def play(orc: dict, d, typ: str = "joint_position") -> None:
    """Send an oracle through the control interface: its rows as `act` chunks of at most `MAX_CHUNK_S` (rows one
    control step apart), its other calls as they are. `typ="ee_pose"` sends the rows' poses instead."""
    rows = orc["rows"] if typ == "joint_position" else orc["ee"]
    per = int(round(MAX_CHUNK_S / CONTROL_DT))
    from robosafe.families.driver import Driver
    robot = d.robot if isinstance(d, Driver) else d          # a driver's own copy of the episode is not needed here
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
    np.savez_compressed(path.with_suffix(".npz"), joint_position=orc["rows"], ee_pose=orc["ee"])
    meta = {k: v for k, v in orc.items() if k not in ("rows", "ee")}
    meta["format"] = "robosafe-oracle/1"
    meta["control_dt"] = CONTROL_DT
    path.with_suffix(".json").write_text(json.dumps(meta, indent=1))


def load(path: Path) -> dict:
    path = Path(path)
    meta = json.loads(path.with_suffix(".json").read_text())
    z = np.load(path.with_suffix(".npz"))
    return {**meta, "rows": z["joint_position"], "ee": z["ee_pose"]}
