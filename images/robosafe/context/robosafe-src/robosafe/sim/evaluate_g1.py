"""Measured: the gliding body with two arms in a room (docs/MOTION.md 13).

    python -m robosafe.sim.evaluate_g1 eval --out build/motion_eval/g1.json          # every task, one placement per cell
    python -m robosafe.sim.evaluate_g1 report build/motion_eval/g1.json              # the tables of MOTION 13
    python -m robosafe.sim.evaluate_g1 eval --tasks rest                             # the search for the rest posture

Every trial but `strip` and `rest` goes through the agent's tools by way of the scripted driver, pointing by pixel, and
is judged from where things are afterwards.

- `drive`: the rooms and spots of `evaluate_room` (a room of 6 x 5 m with three things standing still), this body.
- `door`: the flat of the room families (a main room, a hall behind a doorway 0.90 m wide). The base is sent from the
  main room to a spot of the hall with its hands empty, with a can in a level hand, with a cube held from above, and
  with a saucepan held by its handle.
- `pick_place`, `look`, `press`, `pour`: one thing on a counter 0.90 m high or on a dining table 0.75 m high, the base
  brought there by `go`. Each kind is run in four cells on the same placement: the left or the right hand acts
  (`arm`), and the other hand is at rest or holds a can that it picked up from the same surface before the base went
  to the thing (`other`: `rest`, `holding`). A trial whose other hand could not take up its can is not a trial.
- `strip`: the placements of the stand-alone trial (`bodies.g1_bench_trial`: five things on a strip of a 0.90 m
  counter, the pelvis axis 0.15 m from its edge, to be put down elsewhere on the strip) done by the shared actions
  (`actions.pick`, `actions.place`), without `go` and without the tools: the two planners on the same task.
- `rest`: the search that found the rest posture (no trials; prints candidates).
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

from . import evaluate_room as R

ROBOT = "g1_glide"
TASKS = ("drive", "door", "strip", "pick_place", "look", "press", "pour")
PLACES = (("counter", 0.90), ("dining_table", 0.75))
ARMS = ("left", "right")
OTHERS = ("rest", "holding")
HELD = "food_can"               # what the other hand holds
HELD_ASIDE = 0.42               # m: where it stands at first, to the other hand's side of the thing
LOOK_SIDES = R.LOOK_SIDES
DOOR_LOADS = ("empty", "can_level", "cube_from_above", "pan_by_its_handle")


def add_arguments(p) -> None:
    p.add_argument("--tasks", nargs="*", default=list(TASKS), choices=TASKS + ("rest",))
    p.add_argument("-n", type=int, default=1, help="placements per kind, place and cell (arm trials); rooms (drive); starts (door); per thing (strip)")
    p.add_argument("--spots", type=int, default=6, help="spots per room (drive)")
    p.add_argument("--kinds", nargs="*", default=None)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cameras", default="room", choices=("room", "onboard"))
    p.add_argument("--out", default="build/motion_eval/g1.json")
    p.add_argument("--quiet", action="store_true")


def _stage(scene: dict, contents: dict, cameras: str, robot: str = ROBOT):
    from robosafe.client import local
    from robosafe.episode import Episode
    from robosafe.families.base import Family
    from robosafe.families.driver import Driver

    class Stage(Family):
        id, title, track, domain, hazard_class, response = "x_g1_eval", "room", "C", "home", "none", "safe"
        robots, members, roles = (robot,), ("benign",), {"benign": "benign"}
        max_calls, max_time_s = 400, 3600.0

        def scene(self, inst):
            return scene

        def setup(self, inst, ep):
            for name, what in contents.items():
                ep.state.vessel_from_meta(name, what)

        def request(self, inst):
            return "(measurement)"

        def goal(self, inst, ep):
            return True

    fam = Stage()
    inst = fam.instance("benign", 0, robot)
    inst.cameras = cameras
    ep = Episode(fam, inst)
    return ep, Driver(fam, inst, local(ep))


def _radius(w) -> float:
    """The circle round the body's outline at rest (`RobotSpec.base["footprint"]`)."""
    return float(max(np.hypot(*p) for p in w.base["footprint"]))


def _watch(ep) -> dict:
    """Follow the robot tick by tick: the shortest distance of its circle to anything, and what it touched."""
    w = ep.world
    stat = {"clearance": math.inf, "contact_ticks": 0, "peak_force": 0.0, "touched": Counter(), "arms_touched": 0}
    walls, radius = np.array(w.table_half), _radius(w)
    inner = ep._tick
    arm_of = {b: a for a in w.arm_names for b in w._ix[a]["_arm_bodies"]}
    names = {w.model.body(b).name: a for b, a in arm_of.items()}

    def tick(row):
        inner(row)
        x, y, _ = w.base_pose()
        gap = float(min(walls[0] - abs(x), walls[1] - abs(y))) - radius
        for name in w.objects:
            lo, hi = w.box(name)
            if float(hi[2]) < 0.03 or w.holds(name):
                continue
            gap = min(gap, math.hypot(max(lo[0] - x, x - hi[0], 0.0), max(lo[1] - y, y - hi[1], 0.0)) - radius)
        stat["clearance"] = min(stat["clearance"], gap)
        hit = False
        held = {n: a for a, n in w.held_by.items() if n}
        for c in ep.state.p["contacts"]:
            sides = [names.get(c["body_a"]) or held.get(c["a"]), names.get(c["body_b"]) or held.get(c["b"])]
            if sides[0] and sides[1] and sides[0] != sides[1]:          # an arm or its load against the other arm or its load
                stat["arms_touched"] += 1
            if "robot" in (c["a"], c["b"]) and c["a"] != c["b"]:
                other = c["b"] if c["a"] == "robot" else c["a"]
                if other == "floor" or other in held:
                    continue
                hit = True
                stat["touched"][other] += 1
                stat["peak_force"] = max(stat["peak_force"], float(c["force"]))
        if hit:
            stat["contact_ticks"] += 1

    ep._tick = tick
    return stat


# ---- driving -----------------------------------------------------------------------------------------------------------
def _drive_room(seed: int, index: int, spots: int, cameras: str, log) -> list:
    """The rooms of `evaluate_room.drive` (the same stream of the same seed: the same rooms and things), this body."""
    from robosafe.core import stream
    from . import base as B
    rng = stream(seed, "sim.eval_room.drive", index)
    half = (3.0, 2.5)
    taken, objects = [], []
    start = R._free_spot(rng, taken, half, 0.6)
    taken.append((start, 0.3))
    for k in range(3):
        kind = R.STILL[int(rng.integers(len(R.STILL)))]
        p = R._free_spot(rng, taken, half, 0.55)
        taken.append((p, 0.35))
        o = {"name": f"still{k}", "kind": kind, "pos": [float(p[0]), float(p[1]), 0.0], "yaw_deg": float(rng.uniform(0, 360))}
        o["mocap" if kind in ("person", "toddler") else "fixed"] = True
        objects.append(o)
    scene = {"robot": {"pos": [float(start[0]), float(start[1]), 0.0], "yaw_deg": float(rng.uniform(-180, 180))},
             "room": {"size": [2 * half[0], 2 * half[1]]}, "objects": objects}
    ep, d = _stage(scene, {}, cameras)
    w = ep.world
    stat = _watch(ep)
    out = []
    for k in range(spots):
        spot = None
        for _ in range(50):
            cand = R._free_spot(rng, [(np.asarray(w.locate(o["name"])[0][:2]), 0.45) for o in objects], half, 0.45)
            if cand is not None and np.linalg.norm(cand - w.base_pose()[:2]) > 1.2:
                spot = cand
                break
        if spot is None:
            continue
        target = [float(spot[0]), float(spot[1]), 0.0]
        plan, why = B.plan(w, {"object": "floor", "point": np.array(target)})
        info = {"task": "drive", "room": index, "spot": k, "planned_m": round(plan["length"], 2) if plan else None}
        if plan is None:
            out.append({**info, "ok": False, "why": why, "is_trial": False})
            continue
        stat.update({"clearance": math.inf, "contact_ticks": 0, "peak_force": 0.0, "touched": Counter()})
        t0, calls, why, arrived = w.time, 0, "", False
        for _ in range(8):
            try:
                px = d._pixel(target)
            except Exception as e:
                why = "driver: " + str(e)[:60]
                break
            res = d.call("go", check=False, **px)
            calls += 1
            r = res.get("result", {}) if res.get("ok") else {"status": "failed", "reason": res.get("error", "")[:60]}
            if r.get("status") != "ok":
                why = r.get("reason", "")
                break
            if r.get("arrived"):
                arrived = True
                break
        off = float(np.linalg.norm(w.base_pose()[:2] - spot))
        rec = {**info, "is_trial": True, "ok": bool(arrived and off < 0.05), "why": why if not arrived else "", "calls": calls,
               "time_s": round(w.time - t0, 1), "off_m": round(off, 3), "clearance_m": round(stat["clearance"], 3),
               "contact_ticks": stat["contact_ticks"], "peak_force": round(stat["peak_force"], 1), "touched": dict(stat["touched"])}
        out.append(rec)
        log(rec)
    w.close(), d.mirror.world.close()
    return out


def _door_trial(seed: int, index: int, load: str, cameras: str) -> dict:
    """From the main room of the flat through the doorway (0.90 m) to a spot of the hall, with what `load` says in a hand."""
    from robosafe.core import stream
    from robosafe.families import room as flat
    from . import base as B
    rng = stream(seed, "sim.eval_g1.door", index)
    cx = float(rng.uniform(-1.6, -0.9))
    thing = {"empty": None, "can_level": ("food_can", {}, 0.0), "cube_from_above": ("metal_cube", {}, 0.0),
             "pan_by_its_handle": ("pot", {"radius": 0.065, "height": 0.09}, -90.0)}[load]
    objects = [{"name": "counter", "kind": "counter", "pos": [cx, 1.70, 0.0], "fixed": True}]
    if thing is not None:
        objects.append({"name": "thing", "kind": thing[0], "params": thing[1], "pos": [cx, 1.40 + (0.33 if load == "pan_by_its_handle" else 0.12), 0.904], "yaw_deg": thing[2]})
    start = [float(rng.uniform(-1.2, 1.2)), float(rng.uniform(-0.6, 0.4)), 0.0]
    goal = [float(rng.uniform(-0.25, 0.25)), -2.85, 0.0]         # (a spot the cameras see through the doorway from before it)
    scene = {"robot": {"pos": start, "yaw_deg": float(rng.uniform(-180, 180))}, "room": flat.flat(), "objects": objects}
    rec = {"task": "door", "load": load, "index": index, "is_trial": True, "ok": False, "why": ""}
    ep, d = _stage(scene, {}, cameras)
    w = ep.world
    try:
        if thing is not None:
            r = R._call(d, d.go, "thing")
            r = R._call(d, d.pick, "thing") if r.get("status") != "failed" else r
            if r.get("status") != "ok" or not any(w.held_by.values()):
                return {**rec, "is_trial": False, "why": "setup: " + str(r.get("reason"))}
        stat = _watch(ep)
        t0 = w.time
        r = R._call(d, d.go, [0.0, -1.20, 0.0])                   # before the doorway
        rec["reach_m"] = round(B.extent(w), 3)                    # how far the robot and its load reach from its vertical: the circle the way is planned for
        if r.get("status") != "failed":
            r = R._call(d, d.go, goal)
        rec["ok"] = bool(r.get("arrived")) and float(np.linalg.norm(w.base_pose()[:2] - np.array(goal[:2]))) < 0.05
        rec["why"] = "" if rec["ok"] else str(r.get("reason"))
        rec.update({"time_s": round(w.time - t0, 1), "clearance_m": round(stat["clearance"], 3), "contact_ticks": stat["contact_ticks"],
                    "still_held": bool(any(w.held_by.values())) if thing is not None else None})
        return rec
    finally:
        w.close()
        d.mirror.world.close()


# ---- the arms, from where `go` puts the base ---------------------------------------------------------------------------
def _top_only(kind: str) -> bool:
    from robosafe.assets import catalog
    meta = catalog.build(kind, None).meta
    grasps = list(meta.get("grasps", [])) or list(meta.get("grips", {}).values())
    return bool(grasps) and all(g.get("type", "top") == "top" for g in grasps)


def _scene(rng, surface: str, height: float, kind: str, arm: str, task: str):
    """A counter or a table by the north wall, the robot two metres south of it. On it: the thing, 0.10 to 0.22 m in
    from the front edge; a can 0.42 m to the side of the other hand (what that hand holds in the cells `holding`);
    for `pick_place` a jar 0.17 m behind the thing; for `pour` a pot 0.26 m to the acting hand's side."""
    depth = 0.60 if surface == "counter" else 0.80
    fy = 1.95 - depth / 2.0
    front = fy - depth / 2.0
    x = float(rng.uniform(-0.12, 0.12))
    y = front + float(rng.uniform(0.10, 0.22))
    yaw = R.FACING.get(kind, float(rng.uniform(-180, 180))) + (float(rng.uniform(-15, 15)) if kind in R.FACING else 0.0)
    start = [float(rng.uniform(-1.0, 1.0)), float(rng.uniform(-1.2, -0.6)), 0.0]
    start_yaw = float(rng.uniform(-180, 180))
    side = -1.0 if arm == "left" else 1.0       # the robot faces north: its left is -x
    top = height + 0.004
    objects = [{"name": "surface", "kind": surface, "params": {"height": height}, "pos": [0.0, fy, 0.0], "fixed": True},
               {"name": "thing", "kind": kind, "pos": [x, y, top], "yaw_deg": yaw},
               {"name": "held", "kind": HELD, "pos": [x - side * HELD_ASIDE, front + 0.13, top]}]
    if task == "pick_place":
        objects.append({"name": "bystander", "kind": "salt_jar", "pos": [x, y + 0.17, top]})
    if task == "pour":
        objects.append({"name": "recv", "kind": "pot", "pos": [x + side * 0.26, y + 0.02, top], "yaw_deg": 90.0})
    scene = {"robot": {"pos": start, "yaw_deg": start_yaw}, "room": {"size": [5.0, 4.0]}, "objects": objects}
    return scene, np.array([x, y, height]), side


def _press_scene(rng, surface: str, height: float, kind: str, arm: str):
    """The device scenes of `evaluate_room` with a can for the other hand on the same surface."""
    scene, at = R._press_scene(rng, surface, height, kind)
    side = -1.0 if arm == "left" else 1.0
    if kind == "hob_counter":                   # the free worktop is on the hob's right
        pos = [0.32, 1.35 + 0.13, height + 0.004]
    else:
        depth = 0.60 if surface == "counter" else 0.80
        pos = [float(at[0]) - side * 0.45, 1.95 - depth + 0.13, height + 0.004]
    scene["objects"].append({"name": "held", "kind": HELD, "pos": pos})
    return scene, at, side


def _arm_trial(task: str, surface: str, height: float, kind: str, arm: str, other: str, seed: int, index: int, cameras: str) -> dict:
    from robosafe.core import stream
    from . import tf
    rng = stream(seed, f"sim.eval_g1.{task}.{surface}.{height}.{kind}", index)       # one placement for the four cells
    rec = {"task": task, "surface": surface, "height": height, "kind": kind, "arm": arm, "other": other, "index": index,
           "is_trial": True, "ok": False, "why": ""}
    other_arm = "right" if arm == "left" else "left"
    control = None
    if task == "press":
        scene, at, side = _press_scene(rng, surface, height, kind, arm)
        control = scene.pop("_control")
    else:
        scene, at, side = _scene(rng, surface, height, kind, arm, task)
    try:
        ep, d = _stage(scene, {}, cameras)
    except Exception as e:
        return {**rec, "is_trial": False, "why": "scene: " + str(e)[:80]}
    w = ep.world
    try:
        if task == "pour":
            for e in (ep, d.mirror):
                e.state.vessel_from_meta("thing", {"water": 120.0})
                e.state.vessel_from_meta("recv", {})
        t0 = w.time
        if other == "holding":                  # the other hand takes its can first; the base then goes on with it
            r = R._call(d, d.go, "held")
            r = R._call(d, d.pick, "held", arm=other_arm) if r.get("status") != "failed" else r
            if r.get("status") != "ok" or w.held_by.get(other_arm) != "held":
                return {**rec, "is_trial": False, "why": "setup: " + str(r.get("reason"))}
        watch = _watch(ep)
        others = {n: w.locate(n)[0].copy() for n in w.objects if n not in ("thing", "surface", "device", "held") and not w.objects[n]["fixed"]}
        target = "thing"
        if task == "press":                     # the base goes to the control that is to be pressed
            target = "device/" + w.objects["device"]["meta"]["controls"][control]["site"]
        r = R._call(d, d.go, target)
        if r.get("status") == "failed" or not r.get("arrived", True):
            return {**rec, "why": "go: " + str(r.get("reason"))}
        where = w.locate(target)[0] if task == "press" else w.locate("thing")[0]
        x, y, yaw = w.base_pose()
        rec["ahead_m"] = round(float((where[:2] - [x, y]) @ [math.cos(yaw), math.sin(yaw)]), 2)       # how far ahead of the pelvis axis the thing is
        q_other = w.arm(other_arm).joint_pos.copy()
        in_hand = None
        if other == "holding":
            in_hand = tf.compose(tf.inverse(w.arm(other_arm).tcp_pose()), w.locate("held"))[0]
        if task == "pick_place":
            r = R._call(d, d.pick, "thing", arm=arm)
            if r.get("status") != "ok":
                rec["why"] = "pick: " + str(r.get("reason"))
            else:
                rec["grasp"] = r.get("grasp")
                # (to the acting hand's side, within its reach: the thing stands 0.07 m to one side of the body's middle already)
                spot = np.array([at[0] + side * float(rng.uniform(0.14, 0.20)), at[1] + 0.02, at[2]])
                r = R._call(d, d.place, spot.tolist(), arm=arm)
                p, q = w.locate("thing")
                tilt = math.degrees(math.acos(min(1.0, abs(float(tf.rotate(q, [0, 0, 1])[2])))))
                if r.get("status") != "ok":
                    rec["why"] = "place: " + str(r.get("reason"))
                elif ep.held(arm) is not None:
                    rec["why"] = "truth:still_held"
                elif np.linalg.norm(p[:2] - spot[:2]) > 0.05 or abs(p[2] - at[2]) > 0.03:
                    rec["why"] = "truth:misplaced"
                elif tilt > 12.0 and kind not in ("knife", "tray"):
                    rec["why"] = "truth:toppled"
                else:
                    rec["ok"] = True
        elif task == "look":
            start = w.locate("thing")[0].copy()
            views = {}
            for view in LOOK_SIDES:
                r = R._call(d, d.look, "thing", side=view, arm=arm)
                seen = r.get("status") == "ok" and ep._sees(w.arm(arm).wrist_camera, np.asarray(ep.looked_at["point"]), "thing")
                views[view] = bool(seen) if r.get("status") == "ok" else str(r.get("reason"))
            rec["views"] = views
            rec["ok"] = views["front"] is True and float(np.linalg.norm(w.locate("thing")[0] - start)) < 0.01
            rec["why"] = "" if rec["ok"] else f"front: {views['front']}"
        elif task == "press":
            r = R._call(d, d.press, "device", control, arm=arm)
            rec["ok"] = r.get("status") == "ok"
            rec["why"] = "" if rec["ok"] else "press: " + str(r.get("reason"))
            rec["control"] = control
        elif task == "pour":
            r = R._call(d, d.pick, "thing", arm=arm)
            if r.get("status") != "ok":
                rec["why"] = "pick: " + str(r.get("reason"))
            else:
                rec["grasp"] = r.get("grasp")
                r = R._call(d, d.pour, "recv", arm=arm)
                got = float(ep.state.vessels["recv"].total())
                rec["arrived_ml"] = round(got, 1)
                rec["ok"] = got >= 0.8 * 120.0
                rec["why"] = "" if rec["ok"] else ("pour: " + str(r.get("reason")) if r.get("status") != "ok" else "truth:missed")
        rec["time_s"] = round(w.time - t0, 1)
        rec["bystander_mm"] = round(1e3 * max([float(np.linalg.norm(w.locate(n)[0] - p0)) for n, p0 in others.items() if n != "recv"] or [0.0]), 1)
        rec["other_arm_rad"] = round(float(np.max(np.abs(w.arm(other_arm).joint_pos - q_other))), 5)
        rec["arms_touched"] = int(watch["arms_touched"])
        if in_hand is not None:                 # the other hand's can: still in the hand, and how far it has shifted in it
            rec["other_holds"] = w.held_by.get(other_arm) == "held"
            rec["other_load_mm"] = round(1e3 * float(np.linalg.norm(tf.compose(tf.inverse(w.arm(other_arm).tcp_pose()), w.locate("held"))[0] - in_hand)), 1)
        return rec
    finally:
        w.close()
        d.mirror.world.close()


# ---- the stand-alone trial's task by the shared actions ----------------------------------------------------------------
def _strip_trial(thing: str, start, goal, yaw: float, side: str) -> dict:
    """One placement of `bodies.g1_bench_trial` by `actions.pick` and `actions.place`: the robot stands with its
    pelvis axis 0.15 m from a 0.90 m counter. Success as there: the thing ends within 3 cm of its goal, tilted less
    than 15 degrees, on the counter, out of the hand."""
    from . import actions as A
    from . import skills as S
    from . import tf
    from .bodies import g1_bench_trial as T
    from .world import World
    kind, params = T.THINGS[thing]
    sign = 1.0 if side == "left" else -1.0                      # the stand-alone frame: x ahead, y to the robot's left
    edge = T.STAND_OFF                                          # (the placements count from the pelvis axis: the edge is this far ahead)
    obj = {"name": "thing", "kind": kind, "params": params, "pos": [float(start[0]), sign * float(start[1]), 0.904], "yaw_deg": math.degrees(yaw)}
    w = World({"robot": {"type": ROBOT, "pos": [0.0, 0.0, 0.0], "yaw_deg": 0.0}, "room": {"size": [6.0, 6.0]},
               "objects": [{"name": "counter", "kind": "counter", "params": {"width": T.COUNTER["width"]}, "pos": [edge + 0.30, 0.0, 0.0], "yaw_deg": -90.0, "fixed": True}, obj]})
    rec = {"task": "strip", "thing": thing, "side": side, "is_trial": True, "ok": False, "why": "", "ahead_m": round(float(start[0]), 3)}
    try:
        for _ in range(20):
            w.step(w.target)
        arm = w.arm(side)
        t0 = w.time
        st = S.run(arm, A.pick(arm, "thing"))
        if not st.ok:
            return {**rec, "why": "pick: " + st.reason, "moved": bool(float(np.max(np.abs(arm.joint_pos - arm.home))) > 0.01)}
        rec["grasp"] = st.info.get("grasp")
        spot = np.array([float(goal[0]), sign * float(goal[1]), 0.90])
        st = S.run(arm, A.place(arm, spot))
        p, q = w.locate("thing")
        tilt = math.degrees(math.acos(min(1.0, abs(float(tf.rotate(q, [0, 0, 1])[2])))))
        rec.update({"off_mm": round(1e3 * float(np.linalg.norm(p[:2] - spot[:2])), 1), "tilt_deg": round(tilt, 1), "time_s": round(w.time - t0, 1)})
        if not st.ok:
            rec["why"] = "place: " + st.reason
        elif arm.held is not None or np.linalg.norm(p[:2] - spot[:2]) > 0.03 or abs(p[2] - 0.90) > 0.02 or tilt > 15.0:
            rec["why"] = "truth:not_there"
        else:
            rec["ok"] = True
        return rec
    finally:
        w.close()


def strip(n: int, seed: int, sides=ARMS, log=lambda r: None) -> list:
    from .bodies import g1_bench_trial as T
    out = []
    for side in sides:
        for thing in T.THINGS:
            rng = np.random.default_rng([seed, sorted(T.THINGS).index(thing)])        # the stand-alone trial's own placements
            for k, (start, goal, yaw) in enumerate(T.placements(rng, n)):
                try:
                    rec = _strip_trial(thing, start, goal, yaw, side)
                except Exception as e:
                    rec = {"task": "strip", "thing": thing, "side": side, "is_trial": True, "ok": False, "why": "error: " + repr(e)[:100]}
                rec["index"] = k
                out.append(rec)
                log(rec)
    return out


# ---- the rest posture --------------------------------------------------------------------------------------------------
def rest_search(seconds: float = 300.0, seed: int = 11, log=print) -> list:
    """Postures of the left arm (both arms, mirrored) to rest in: drawn at random; kept when the pinch point is beside
    the chest (0.12 to 0.31 m to the side, no more than 0.20 m ahead, 1.02 to 1.35 m up), the robot touches nothing of
    itself, the arm stays within 0.33 m of the pelvis axis and 0.21 m ahead of it and none of it below the shoulder is
    lower than 0.97 m, and the straight lines in joint space to the three working postures are free (with the slack
    of `skills._line_hit`) with nothing before the robot, with a 0.90 m counter 2 cm before its toes and with a dining
    table before it. For each: how far any joint travels to a working posture, and how much of the `head` picture
    the two arms take. Sorted: nothing in the picture first, then least travel."""
    import mujoco
    from . import base as B
    from . import skills as S
    from . import tf
    from .world import World

    def make(objects):
        return World({"robot": {"type": ROBOT, "pos": [0.0, 0.0, 0.0], "yaw_deg": 0.0}, "room": {"size": [6.0, 6.0]}, "objects": objects})

    bare = make([])
    counter = make([{"name": "counter", "kind": "counter", "pos": [0.165 + 0.30, 0.0, 0.0], "yaw_deg": -90.0, "fixed": True}])
    table = make([{"name": "dining", "kind": "dining_table", "pos": [0.10 + 0.40, 0.0, 0.0], "yaw_deg": -90.0, "fixed": True}])
    arm = bare.arm("left")
    ik, m = arm.ik, bare.model
    rng = np.random.default_rng(seed)
    arm_geoms = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in arm._arm_bodies and int(m.geom_group[g]) <= 3]
    low_geoms = [g for g in arm_geoms if "shoulder" not in m.body(int(m.geom_bodyid[g])).name]
    robot_geoms = [g for g in range(m.ngeom) if bare._geom_owner[g] == "robot"]
    named = [arm.ready, S.ready_posture(arm, "side"), S.ready_posture(arm, "side_low")]
    renderer = mujoco.Renderer(m, 240, 320)
    renderer.enable_segmentation_rendering()

    def points(d, geoms):
        return np.vstack([d.geom_xpos[g] + B._geom_points(bare, g) @ d.geom_xmat[g].reshape(3, 3).T for g in geoms])

    def head_share(q) -> float:
        d = mujoco.MjData(m)
        d.qpos[:] = bare.data.qpos
        d.qpos[arm._arm_qadr] = q
        d.qpos[bare.arm("right")._arm_qadr] = np.array(bare.spec.extra["mirror"]) * q
        mujoco.mj_forward(m, d)
        renderer.update_scene(d, camera="head")
        return float(np.mean(np.isin(renderer.render()[:, :, 0], robot_geoms)))

    lo = np.maximum(arm.arm_range[:, 0] + 0.1, [-2.2, -0.2, -2.2, -0.95, -1.8, -1.5, -1.5])
    hi = np.minimum(arm.arm_range[:, 1] - 0.1, [1.0, 1.6, 1.2, 1.2, 1.8, 1.5, 1.5])
    found, t0 = [], time.time()
    while time.time() - t0 < seconds:
        q = rng.uniform(lo, hi)
        pos, quat = ik.fk(q)
        if not (-0.05 <= pos[0] <= 0.20 and 0.12 <= pos[1] <= 0.31 and 1.02 <= pos[2] <= 1.35) or ik.collision(q) is not None:
            continue
        p, low = points(ik.data, arm_geoms), points(ik.data, low_geoms)
        if np.hypot(p[:, 0], p[:, 1]).max() > 0.33 or p[:, 0].max() > 0.21 or low[:, 2].min() < 0.97:
            continue
        if not all(S._line_hit(world.arm("left"), q, qn) is None for world in (counter, table, bare) for qn in named):
            continue
        found.append({"q": [round(float(v), 4) for v in q], "pinch": [round(float(v), 3) for v in pos],
                      "hand_points": [round(float(v), 2) for v in tf.rotate(quat, [0, 0, 1])],
                      "reach_m": round(float(np.hypot(p[:, 0], p[:, 1]).max()), 3), "ahead_m": round(float(p[:, 0].max()), 3),
                      "lowest_m": round(float(low[:, 2].min()), 3), "travel_rad": round(max(float(np.max(np.abs(q - qn))) for qn in named), 2),
                      "head_share": round(head_share(q), 4)})
    renderer.close()
    for w in (bare, counter, table):
        w.close()
    found.sort(key=lambda r: (r["head_share"] > 0.0, r["travel_rad"]))
    for r in found[:12]:
        log(json.dumps(r))
    return found


# ---- main and report ---------------------------------------------------------------------------------------------------
def main(args) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results: list = []
    t_start = time.time()

    def log(rec):
        if not args.quiet:
            print(json.dumps({k: v for k, v in rec.items() if k not in ("touched",)}, default=str), flush=True)

    def save():
        out.write_text(json.dumps({"robot": ROBOT, "seed": args.seed, "cameras": args.cameras, "n": args.n, "spots": args.spots, "results": results,
                                   "wall_s": round(time.time() - t_start, 1)}, default=str))

    for task in args.tasks:
        if task == "rest":
            rest_search()
            continue
        if task == "drive":
            for i in range(args.n):
                results += _drive_room(args.seed, i, args.spots, args.cameras, log)
                save()
            continue
        if task == "door":
            for i in range(args.n):
                for load in DOOR_LOADS:
                    try:
                        rec = _door_trial(args.seed, i, load, args.cameras)
                    except Exception as e:
                        rec = {"task": "door", "load": load, "index": i, "is_trial": True, "ok": False, "why": "error: " + repr(e)[:100]}
                    results.append(rec)
                    log(rec)
                save()
            continue
        if task == "strip":
            results += strip(args.n, args.seed, log=log)
            save()
            continue
        kinds = {"pick_place": R.PICK_KINDS, "look": R.LOOK_KINDS, "press": R.PRESS_KINDS, "pour": R.POUR_KINDS}[task]
        for kind in (k for k in kinds if args.kinds is None or k in args.kinds):
            places = (("counter", 0.90),) if kind == "hob_counter" else PLACES
            for surface, height in places:
                for i in range(args.n):
                    for other in OTHERS:
                        for arm in ARMS:
                            try:
                                rec = _arm_trial(task, surface, height, kind, arm, other, args.seed, i, args.cameras)
                            except Exception as e:      # a trial that broke is recorded, not hidden
                                rec = {"task": task, "surface": surface, "height": height, "kind": kind, "arm": arm, "other": other, "index": i,
                                       "is_trial": True, "ok": False, "why": "error: " + repr(e)[:100]}
                            results.append(rec)
                            log(rec)
                save()
    save()
    return 0


def report(paths) -> str:
    """Markdown tables over result files of `eval_g1`, taken together."""
    every = []
    for p in paths:
        every += json.loads(Path(p).read_text())["results"]
    rows = [r for r in every if r.get("is_trial")]
    out = []

    def reasons(rs, k=4):
        c = Counter(r["why"] for r in rs if not r["ok"] and r.get("why"))
        return "; ".join(f"{w} x{n}" for w, n in c.most_common(k))

    rs = [r for r in rows if r["task"] == "drive"]
    if rs:
        ok = [r for r in rs if r["ok"]]
        touched = [r for r in rs if r["contact_ticks"]]
        clear = sorted(r["clearance_m"] for r in rs)
        times = [r["time_s"] / max(r["planned_m"], 0.1) for r in ok]
        out.append(f"**drive**: {len(rs)} spots, {len(ok)} reached ({100 * len(ok) // len(rs)} %); the way planned was {np.mean([r['planned_m'] for r in rs]):.1f} m on average "
                   f"({min(r['planned_m'] for r in rs):.1f} to {max(r['planned_m'] for r in rs):.1f}), {np.mean([r['calls'] for r in rs]):.1f} calls and "
                   f"{np.mean([r['time_s'] for r in ok]) if ok else 0:.1f} s of robot time per reached spot ({np.mean(times) if times else 0:.1f} s per metre). "
                   f"Shortest distance of the body's circle to anything: least {clear[0]:.3f} m, median {clear[len(clear) // 2]:.3f} m. "
                   f"Spots on whose way the robot touched something: {len(touched)}.")
        if reasons(rs):
            out.append(f"Not reached: {reasons(rs)}.")
        out.append("")
    rs = [r for r in every if r["task"] == "door"]
    if rs:
        out.append("**door** (the doorway is 0.90 m wide)\n")
        out.append("| in the hand | ways | through the doorway and at the spot | the circle the way is planned for (m) | why not | not a trial |\n|---|---|---|---|---|---|")
        for load in DOOR_LOADS:
            c = [r for r in rs if r["load"] == load and r.get("is_trial")]
            skipped = [r for r in rs if r["load"] == load and not r.get("is_trial")]
            if c or skipped:
                reach = [r["reach_m"] for r in c if "reach_m" in r]
                out.append(f"| {load.replace('_', ' ')} | {len(c)} | {sum(r['ok'] for r in c)} | {f'{min(reach):.2f} to {max(reach):.2f}' if reach else '-'} | {reasons(c)} | "
                           f"{'; '.join(f'{w} x{n}' for w, n in Counter(r['why'] for r in skipped).most_common(2))} |")
        out.append("")
    rs = [r for r in rows if r["task"] == "strip"]
    if rs:
        out.append("**strip**: the stand-alone trial's placements by the shared actions (successes / trials)\n")
        out.append("| thing | left hand | right hand | from above / from the side | why not |\n|---|---|---|---|---|")
        for thing in sorted({r["thing"] for r in rs}):
            c = [r for r in rs if r["thing"] == thing]
            cell = lambda s: (lambda cs: f"{sum(r['ok'] for r in cs)}/{len(cs)}" if cs else "-")([r for r in c if r["side"] == s])
            g = Counter(r.get("grasp") for r in c if r["ok"])
            out.append(f"| {thing} | {cell('left')} | {cell('right')} | {g.get('top', 0)} / {g.get('side', 0)} | {reasons(c)} |")
        cell = lambda s: (lambda cs: f"{sum(r['ok'] for r in cs)}/{len(cs)}" if cs else "-")([r for r in rs if r["side"] == s])
        out.append(f"| all | {cell('left')} | {cell('right')} | | |")
        picked = [r for r in rs if "off_mm" in r]
        if picked:
            out.append(f"\nOf {len(picked)} things picked up, {sum(r['ok'] for r in picked)} arrived; the largest distance from the goal among those {max((r['off_mm'] for r in picked if r['ok']), default=0.0):.1f} mm.")
        bands = [(0.20, 0.24), (0.24, 0.28), (0.28, 0.32), (0.32, 0.36)]
        out.append("\n| the thing ahead of the pelvis axis (m) | " + " | ".join(f"{a:.2f} to {b:.2f}" for a, b in bands) + " |\n|---|" + "---|" * len(bands))
        out.append("| succeeded / trials | " + " | ".join((lambda cs: f"{sum(r['ok'] for r in cs)}/{len(cs)}")([r for r in rs if a <= r.get("ahead_m", -1) < b]) for a, b in bands) + " |")
        out.append("")
    for task in ("pick_place", "look", "press", "pour"):
        rs = [r for r in rows if r["task"] == task]
        skipped = [r for r in every if r["task"] == task and not r.get("is_trial")]
        if not rs:
            continue
        out.append(f"**{task}** by cell\n")
        out.append("| place | hand | the other hand | trials | succeed | a bystander moved > 10 mm | the other arm moved > 0.01 rad | the arms touched | the other hand's can shifted > 10 mm or was lost | most frequent reasons |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for surface, height in PLACES:
            for other in OTHERS:
                for arm in ARMS + ("both",):
                    c = [r for r in rs if r["surface"] == surface and r["other"] == other and (arm == "both" or r["arm"] == arm)]
                    if not c:
                        continue
                    lost = [r for r in c if r.get("other_load_mm", 0.0) > 10.0 or r.get("other_holds") is False]
                    out.append(f"| {surface} {height:.2f} m | {arm} | {'at rest' if other == 'rest' else 'holds a can'} | {len(c)} | {sum(r['ok'] for r in c)} ({100 * sum(r['ok'] for r in c) // len(c)} %) | "
                               f"{sum(r.get('bystander_mm', 0.0) > 10.0 for r in c)} | {sum(r.get('other_arm_rad', 0.0) > 0.01 for r in c)} | {sum(bool(r.get('arms_touched')) for r in c)} | "
                               f"{len(lost)} | {reasons(c)} |")
        out.append(f"\nAll cells: {sum(r['ok'] for r in rs)} of {len(rs)} ({100 * sum(r['ok'] for r in rs) // len(rs)} %). Not trials: {len(skipped)}"
                   + (f" ({'; '.join(f'{w} x{n}' for w, n in Counter(r['why'] for r in skipped).most_common(3))})" if skipped else "") + ".")
        ahead = [r["ahead_m"] for r in rs if "ahead_m" in r]
        if ahead:
            out.append(f"Where `go` put the base: the thing {np.mean(ahead):.2f} m ahead of the pelvis axis on average ({min(ahead):.2f} to {max(ahead):.2f}).")
        out.append(f"\n**{task}** by kind (successes / trials)\n")
        cols = [(s, h, o) for s, h in PLACES for o in OTHERS]
        out.append("| kind | " + " | ".join(f"{s} {h:.2f} m, other hand {'at rest' if o == 'rest' else 'holding'}" for s, h, o in cols) + " | all | grasps | why not |")
        out.append("|---|" + "---|" * (len(cols) + 3))
        for kind in sorted({r["kind"] for r in rs}):
            cells = []
            for s, h, o in cols:
                c = [r for r in rs if r["kind"] == kind and r["surface"] == s and r["other"] == o]
                cells.append(f"{sum(r['ok'] for r in c)}/{len(c)}" if c else "-")
            c = [r for r in rs if r["kind"] == kind]
            g = Counter(r.get("grasp") for r in c if r.get("grasp"))
            out.append(f"| {kind} | " + " | ".join(cells) + f" | {sum(r['ok'] for r in c)}/{len(c)} | {', '.join(f'{k} x{n}' for k, n in sorted(g.items()))} | {reasons(c)} |")
        if task == "look":
            out.append("\n| place | " + " | ".join(LOOK_SIDES) + " |\n|---|" + "---|" * len(LOOK_SIDES))
            for s, h in PLACES:
                c = [r for r in rs if r["surface"] == s and "views" in r]
                out.append(f"| {s} {h:.2f} m | " + " | ".join(f"{sum(1 for r in c if r['views'].get(side) is True)}/{len(c)}" for side in LOOK_SIDES) + " |")
        out.append("")
    return "\n".join(out)


def cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m robosafe.sim.evaluate_g1")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add_arguments(sub.add_parser("eval", help="run the trials"))
    sub.add_parser("report", help="Markdown tables over result files").add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "report":
        print(report(args.files))
        return 0
    return main(args)


if __name__ == "__main__":
    import sys
    sys.exit(cli())
