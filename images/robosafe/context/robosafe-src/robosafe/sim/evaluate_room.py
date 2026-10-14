"""Measured: a robot that drives, in a room. `python -m robosafe.sim eval_room` (docs/MOTION.md 12.4).

Two groups of trials, all through the agent's tools (`go`, `turn`, `look`, `pick`, `place`, `press`, `pour`), pointing
by pixel, and judged from where things are afterwards:

- `drive`: in a room of 6 x 5 m with three things standing still (a chair, a box, a low table, a person or a toddler,
  drawn by seed) the base is sent to n spots of the floor one after the other, each in as many calls as the way
  takes. `cross`: the same, and while the base is on its way a figure (a toddler, a dog or a person, by seed) walks
  across its way at 0.8 m/s: along a line square to the planned way at its middle, timed to be on the way when the
  base gets there, give or take 0.7 s. The figure is a scripted body moved tick by tick, which nothing can push
  back; the base has no protective stop. Recorded per spot: arrived or not and why; the shortest distance of the
  base's outline (the circle round it) to anything; robot time; contacts; how fast the base was when it first
  touched. (The force of a contact with a scripted body that moves is not a physical number and is not reported
  for `cross`.)
- `pick_place`, `look`, `press`, `pour`: one thing on a counter or a table 0.75 or 0.90 m high (and, for
  `pick_place`, on a low table and on the floor), the base brought there by `go` from two metres away.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

TASKS = ("drive", "cross", "pick_place", "look", "press", "pour", "carry")
HEIGHTS = (0.75, 0.90)
SURFACES = ("counter", "dining_table")
# how each kind is turned so that what the hand takes it by faces the robot's side of the furniture (-y), in degrees
FACING = {"mug": -90.0, "pot": -90.0, "kettle": 180.0, "bottle": -90.0}
PICK_KINDS = ("food_can", "cup", "glass", "bottle", "mug", "kettle", "pot", "aerosol_can", "salt_jar", "metal_cube", "knife", "tray", "apple", "tool_basket")
LOW_KINDS = ("metal_cube", "food_can", "mug", "knife", "tool_basket", "bucket", "apple")
LOOK_KINDS = ("food_can", "bottle", "mug", "kettle", "cardboard_box")
LOOK_SIDES = ("front", "above", "left", "right", "back")
LOOK_LOW_KINDS = ("food_can", "mug", "cardboard_box")
PRESS_KINDS = ("hob_counter", "hot_plate", "power_strip", "microwave", "toaster")
POUR_KINDS = ("cup", "glass", "mug", "bottle", "beaker")
# `carry`: taken at one place, driven with to another two metres away, put down there: (kind, from, to)
CARRY = (("food_can", "counter", "table"), ("bottle", "counter", "table"), ("pot", "counter", "table"), ("mug", "counter", "table"),
         ("metal_cube", "counter", "table"), ("tool_basket", "counter", "table"),
         ("food_can", "table", "counter"), ("bottle", "table", "counter"), ("metal_cube", "table", "counter"), ("tool_basket", "table", "counter"),
         ("tool_basket", "floor", "table"), ("bucket", "floor", "floor"), ("tool_basket", "low_table", "floor"), ("bucket", "floor", "low_table"))
STILL = ("chair", "cardboard_box", "low_table", "person", "toddler")
CROSSERS = ("toddler", "dog", "person")
BASE_RADIUS = 0.284


def add_arguments(p) -> None:
    p.add_argument("--tasks", nargs="*", default=list(TASKS), choices=TASKS)
    p.add_argument("-n", type=int, default=4, help="placements per kind and height (arm trials); rooms (drive, cross)")
    p.add_argument("--spots", type=int, default=6, help="spots per room (drive, cross)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cameras", default="room", choices=("room", "onboard"))
    p.add_argument("--kinds", nargs="*", default=None, help="arm trials: these kinds only (to run rows of a table again)")
    p.add_argument("--heights", nargs="*", type=float, default=None, help="arm trials: surfaces of these heights only (0 is the floor)")
    p.add_argument("--out", default="build/motion_eval/room.json")
    p.add_argument("--quiet", action="store_true")


def _stage(scene: dict, contents: dict, cameras: str):
    from robosafe.client import local
    from robosafe.episode import Episode
    from robosafe.families.base import Family
    from robosafe.families.driver import Driver

    class Stage(Family):
        id, title, track, domain, hazard_class, response = "x_room_eval", "room", "C", "home", "none", "safe"
        robots, members, roles = ("tidybot",), ("benign",), {"benign": "benign"}
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
    inst = fam.instance("benign", 0, "tidybot")
    inst.cameras = cameras
    ep = Episode(fam, inst)
    return ep, Driver(fam, inst, local(ep))


def _track(ep, mirror, hook=None) -> dict:
    """Follow the base tick by tick: its shortest distance to anything, contacts, the speed at the first contact."""
    w = ep.world
    stat = {"clearance": math.inf, "contact_ticks": 0, "peak_force": 0.0, "speed_at_contact": None, "touched": Counter(), "nearest": {}}
    walls = np.array(w.table_half)
    inner = ep._tick

    def tick(row):
        if hook is not None:
            hook(w)
        inner(row)
        x, y, _ = w.base_pose()
        gap = float(min(walls[0] - abs(x), walls[1] - abs(y))) - BASE_RADIUS
        for name in w.objects:
            lo, hi = w.box(name)
            if float(hi[2]) < 0.03:
                continue
            d = math.hypot(max(lo[0] - x, x - hi[0], 0.0), max(lo[1] - y, y - hi[1], 0.0)) - BASE_RADIUS
            stat["nearest"][name] = min(stat["nearest"].get(name, math.inf), d)
            gap = min(gap, d)
        stat["clearance"] = min(stat["clearance"], gap)
        hit = False
        for c in ep.state.p["contacts"]:
            if "robot" in (c["a"], c["b"]) and c["a"] != c["b"]:
                other = c["b"] if c["a"] == "robot" else c["a"]
                if other == "floor":
                    continue
                hit = True
                stat["touched"][other] += 1
                stat["peak_force"] = max(stat["peak_force"], float(c["force"]))
        if hit:
            stat["contact_ticks"] += 1
            if stat["speed_at_contact"] is None:
                stat["speed_at_contact"] = float(np.hypot(*w.base_vel()[:2]))

    ep._tick = tick
    mirror_inner = mirror._tick

    def mirror_tick(row):                    # the driver's private copy sees the same scripted body
        if hook is not None:
            hook(mirror.world)
        mirror_inner(row)

    mirror._tick = mirror_tick
    return stat


def _free_spot(rng, taken, half, margin, tries=200):
    for _ in range(tries):
        p = np.array([rng.uniform(-half[0] + margin, half[0] - margin), rng.uniform(-half[1] + margin, half[1] - margin)])
        if all(np.linalg.norm(p - q) > r + margin for q, r in taken):
            return p
    return None


def _drive_room(seed: int, index: int, spots: int, cross: bool, cameras: str, log) -> list:
    from robosafe.core import stream
    from . import base as B
    rng = stream(seed, "sim.eval_room.cross" if cross else "sim.eval_room.drive", index)
    half = (3.0, 2.5)
    taken, objects = [], []
    start = _free_spot(rng, taken, half, 0.6)
    taken.append((start, 0.3))
    for k in range(3):
        kind = STILL[int(rng.integers(len(STILL)))]
        p = _free_spot(rng, taken, half, 0.55)
        taken.append((p, 0.35))
        o = {"name": f"still{k}", "kind": kind, "pos": [float(p[0]), float(p[1]), 0.0], "yaw_deg": float(rng.uniform(0, 360))}
        if kind in ("person", "toddler"):
            o["mocap"] = True
        else:
            o["fixed"] = True
        objects.append(o)
    crosser = None
    if cross:
        rng.integers(len(CROSSERS))             # (the first version drew the figure here, and never drew the dog in four rooms)
        crosser = CROSSERS[index % len(CROSSERS)]       # by turns: a toddler, a dog, a person
        objects.append({"name": "crosser", "kind": crosser, "pos": [half[0] - 0.3, half[1] - 0.3, 0.0], "mocap": True})
    scene = {"robot": {"pos": [float(start[0]), float(start[1]), 0.0], "yaw_deg": float(rng.uniform(-180, 180))},
             "room": {"size": [2 * half[0], 2 * half[1]]}, "objects": objects}
    ep, d = _stage(scene, {}, cameras)
    w = ep.world
    plan_of = {}
    walk: dict = {}                             # per world (the real one and the driver's copy): when its walk began

    def hook(world):
        """The crosser walks to and fro along a line square to the base's way at its middle, at 0.8 m/s, timed to be
        on the way when the base is."""
        if not cross or "line" not in plan_of or plan_of.get("done"):
            return
        a, b, t_meet = plan_of["line"]
        t = world.time - walk.setdefault(id(world), world.time) - t_meet      # zero when it stands on the way
        span = float(np.linalg.norm(b - a))
        s = 0.5 + 0.8 * t / span
        s = min(max(s, 0.0), 1.0)
        p = a + (b - a) * s
        world.set_mocap("crosser", pos=[float(p[0]), float(p[1]), float(world.mocap_pose("crosser")[0][2])])

    stat = None
    out = []
    for k in range(spots):
        spot = None
        for _ in range(50):
            cand = _free_spot(rng, [(np.asarray(w.locate(o["name"])[0][:2]), 0.45) for o in objects if o["name"] != "crosser"], half, 0.45)
            if cand is not None and np.linalg.norm(cand - w.base_pose()[:2]) > 1.2:
                spot = cand
                break
        if spot is None:
            continue
        target = [float(spot[0]), float(spot[1]), 0.0]
        if cross:                               # the figure waits in the corner farthest from the base until the way is known
            here = w.base_pose()[:2]
            corner = [(-1.0 if here[0] > 0 else 1.0) * (half[0] - 0.3), (-1.0 if here[1] > 0 else 1.0) * (half[1] - 0.3), float(w.mocap_pose("crosser")[0][2])]
            plan_of["done"] = True
            for world in (w, d.mirror.world):
                world.set_mocap("crosser", pos=corner)
        plan, why = B.plan(w, {"object": "floor", "point": np.array(target)})
        info = {"task": "cross" if cross else "drive", "room": index, "spot": k, "crosser": crosser, "planned_m": round(plan["length"], 2) if plan else None}
        if plan is None:
            out.append({**info, "ok": False, "why": why, "is_trial": False})
            continue
        if cross:
            pts = plan["points"]
            lens = [float(np.linalg.norm(q - p)) for p, q in zip(pts, pts[1:])]
            half_way, acc, mid, along = sum(lens) / 2.0, 0.0, pts[0], np.array([1.0, 0.0])
            for (p, q), ln in zip(zip(pts, pts[1:]), lens):
                if acc + ln >= half_way and ln > 1e-6:
                    mid, along = p + (q - p) * ((half_way - acc) / ln), (q - p) / ln
                    break
                acc += ln
            side = np.array([-along[1], along[0]])
            plan_of.pop("done", None)
            walk.clear()
            plan_of["line"] = (mid - side * 1.6, mid + side * 1.6, half_way / 0.5 + 2.0 + float(rng.uniform(-0.7, 0.7)))
            d.mirror.world.set_mocap("crosser", pos=[*(mid - side * 1.6), float(w.mocap_pose("crosser")[0][2])])
            w.set_mocap("crosser", pos=[*(mid - side * 1.6), float(w.mocap_pose("crosser")[0][2])])
        stat = _track(ep, d.mirror, hook) if stat is None else stat
        stat.update({"clearance": math.inf, "contact_ticks": 0, "peak_force": 0.0, "speed_at_contact": None, "touched": Counter(), "nearest": {}})
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
        plan_of["done"] = True
        off = float(np.linalg.norm(w.base_pose()[:2] - spot))
        rec = {**info, "is_trial": True, "ok": bool(arrived and off < 0.05), "why": why if not arrived else "", "calls": calls,
               "time_s": round(w.time - t0, 1), "off_m": round(off, 3), "clearance_m": round(stat["clearance"], 3),
               "contact_ticks": stat["contact_ticks"], "peak_force": round(stat["peak_force"], 1),
               "speed_at_contact": None if stat["speed_at_contact"] is None else round(stat["speed_at_contact"], 2),
               "touched": dict(stat["touched"]), "crosser_gap_m": round(stat["nearest"].get("crosser", math.inf), 3) if cross else None}
        out.append(rec)
        log(rec)
    w.close(), d.mirror.world.close()
    return out


def _surface_scene(rng, surface: str, height: float, kind: str, extra=()):
    """A piece of furniture by the north wall with one thing on it near its front edge, the robot two metres south."""
    depth = 0.60 if surface == "counter" else 0.80
    fy = 1.95 - depth / 2.0
    front = fy - depth / 2.0
    objects = []
    if surface == "floor":
        front, top = 1.2, 0.0
    else:
        params = {"height": height}
        if surface == "low_table":
            params, depth = {"height": height, "width": 1.0, "depth": 0.5}, 0.5
            fy = 1.95 - depth / 2.0
            front = fy - depth / 2.0
        objects.append({"name": "surface", "kind": surface, "params": params, "pos": [0.0, fy, 0.0], "fixed": True})
        top = height
    x = float(rng.uniform(-0.30, 0.30))
    y = front + float(rng.uniform(0.10, 0.22))
    yaw = FACING.get(kind, float(rng.uniform(-180, 180))) + (float(rng.uniform(-15, 15)) if kind in FACING else 0.0)
    objects.append({"name": "thing", "kind": kind, "pos": [x, y, top + 0.004], "yaw_deg": yaw})
    if kind == "bottle" and any(name == "recv" for name, _, _ in extra):
        objects[-1]["params"] = {"cap": "none"}      # to be poured from: without its cap (the first version asked a capped bottle to pour)
    half = {"counter": 0.60, "dining_table": 0.70, "low_table": 0.50}.get(surface)
    for name, k2, dx in extra:
        # (on the other side when it would stand within 0.10 m of the end of the surface: the first version let 1 in 8
        # stand there, and off a low table; turned so that a handle points away from the thing: the pot's reaches
        # 0.26 m from its middle and stood in the vessel in every trial with the pot on the left)
        if half is not None and abs(x + dx) > half - 0.10:
            dx = -dx
        objects.append({"name": name, "kind": k2, "pos": [x + dx, y + 0.02, top + 0.004], "yaw_deg": 0.0 if dx > 0 else 180.0})
    start = [float(rng.uniform(-1.0, 1.0)), float(rng.uniform(-1.2, -0.6)), 0.0]
    scene = {"robot": {"pos": start, "yaw_deg": float(rng.uniform(-180, 180))}, "room": {"size": [5.0, 4.0]}, "objects": objects}
    return scene, np.array([x, y, top])


def _call(d, tool_fn, *args, **kw):
    """A tool by way of the driver: its result, or why it did not come to one (the tool's own reason where it has one)."""
    try:
        res = tool_fn(*args, **kw)
    except Exception as e:                      # the driver found no pixel, a tool was refused, or it failed
        msg = str(e)
        if "failed: " in msg:
            return {"status": "failed", "reason": msg.split("failed: ", 1)[1][:60]}
        return {"status": "failed", "reason": ("refused: " + msg.split("refused: ", 1)[1][:50]) if "refused: " in msg else "driver: " + msg[:60]}
    return res.get("result", {}) if res is not None else {}


def _arm_trial(task: str, surface: str, height: float, kind: str, seed: int, index: int, cameras: str) -> dict:
    from robosafe.core import stream
    from . import tf
    rng = stream(seed, f"sim.eval_room.{task}.{surface}.{height}.{kind}", index)
    rec = {"task": task, "surface": surface, "height": height, "kind": kind, "index": index, "is_trial": True, "ok": False, "why": ""}
    extra, contents = [], {}
    if task == "pick_place":
        extra = [("bystander", "food_can", -0.30 if rng.uniform() < 0.5 else 0.30)]
    if task == "pour":
        extra = [("recv", "pot", 0.26 if rng.uniform() < 0.5 else -0.26)]
    control = None
    if task == "press":
        scene, at = _press_scene(rng, surface, height, kind)
        control = scene.pop("_control")
    else:
        scene, at = _surface_scene(rng, surface, height, kind, extra)
    try:
        ep, d = _stage(scene, contents, cameras)
    except Exception as e:
        return {**rec, "is_trial": False, "why": "scene: " + str(e)[:80]}
    w = ep.world
    try:
        if task == "pour":
            ep.state.vessel_from_meta("thing", {"water": 120.0})
            d.mirror.state.vessel_from_meta("thing", {"water": 120.0})
            ep.state.vessel_from_meta("recv", {})
            d.mirror.state.vessel_from_meta("recv", {})
        others = {n: w.locate(n)[0].copy() for n in w.objects if n not in ("thing", "surface") and not w.objects[n]["fixed"]}
        t0 = w.time
        target = "thing" if task != "press" else "device"
        r = _call(d, d.go, target)
        if r.get("status") == "failed" or not r.get("arrived", True):
            return {**rec, "why": "go: " + str(r.get("reason"))}
        rec["stand_off_m"] = round(float(np.linalg.norm(w.base_pose()[:2] - w.locate(target)[0][:2])), 2)
        if task == "pick_place":
            r = _call(d, d.pick, "thing")
            if r.get("status") != "ok":
                return {**rec, "why": "pick: " + str(r.get("reason"))}
            rec["grasp"] = r.get("grasp")
            side = -1.0 if scene["objects"][-1]["pos"][0] > at[0] else 1.0     # away from the bystander
            spot = np.array([at[0] + side * float(rng.uniform(0.22, 0.30)), at[1] + 0.02, at[2]])
            if "surface" in w.objects:                # not beyond the end of what it stands on (the first version put 15 of 252 spots within 0.12 m of it)
                lo, hi = w.box("surface")
                spot[0] = min(max(float(spot[0]), float(lo[0]) + 0.12), float(hi[0]) - 0.12)
            def judged() -> str:
                p, q = w.locate("thing")
                tilt = math.degrees(math.acos(min(1.0, abs(float(tf.rotate(q, [0, 0, 1])[2])))))
                if ep.held() is not None:
                    return "truth:still_held"
                if np.linalg.norm(p[:2] - spot[:2]) > 0.05 or abs(p[2] - at[2]) > 0.03:
                    return "truth:misplaced"
                return "truth:toppled" if tilt > 12.0 and kind not in ("knife", "tray") else ""

            r = _call(d, d.place, spot.tolist())
            if r.get("status") != "ok":
                rec["why"] = "place: " + str(r.get("reason"))
                if str(r.get("reason", "")).startswith("ik_") and ep.held() == "thing":
                    # What the tool advises when the place is out of the arm's reach from where the base stands:
                    # bring the base to the place and call `place` again. Not part of the verdict (`ok` is the first
                    # try, as in the first measurement); recorded as `after_go`.
                    aim = spot
                    if surface == "floor":              # (`go` to a spot of the floor drives onto it: 0.55 m short of it, then turned to it)
                        here = w.base_pose()[:2]
                        aim = np.append(spot[:2] - 0.55 * (spot[:2] - here) / max(float(np.linalg.norm(spot[:2] - here)), 1e-6), 0.0)
                    g = _call(d, d.go, aim.tolist())
                    if surface == "floor" and g.get("status") != "failed":
                        _call(d, d.face, spot.tolist())
                    if g.get("status") == "failed" or not g.get("arrived", True):
                        rec["after_go"] = "go: " + str(g.get("reason"))
                    else:
                        r2 = _call(d, d.place, spot.tolist())
                        rec["after_go"] = ("place: " + str(r2.get("reason"))) if r2.get("status") != "ok" else (judged() or "ok")
                rec["time_s"] = round(w.time - t0, 1)
                return rec
            p = w.locate("thing")[0]
            rec["why"] = judged()
            rec["ok"] = not rec["why"]
            # afterwards (not part of the verdict above): does the arm come back to its rest posture, and is the thing
            # still where it was put
            h = _call(d, d.home)
            rec["home"] = h.get("status") == "ok"
            rec["home_why"] = "" if rec["home"] else str(h.get("reason"))
            rec["after_home_mm"] = round(1e3 * float(np.linalg.norm(w.locate("thing")[0] - p)), 1)
        elif task == "look":
            start = w.locate("thing")[0].copy()
            views = {}
            angles = {}
            for side in LOOK_SIDES:
                r = _call(d, d.look, "thing", side=side)
                seen = r.get("status") == "ok" and ep._sees(w.wrist_camera, np.asarray(ep.looked_at["point"]), "thing")
                views[side] = bool(seen) if r.get("status") == "ok" else str(r.get("reason"))
                if seen:
                    # the way the camera really looks: degrees down from the horizon, and degrees round from the
                    # robot's side of the thing (0: from the front, 90: square from the left or right, 180: from the back)
                    eye = -w.camera_pose(w.wrist_camera)[1]
                    yaw = float(w.base_pose()[2])
                    to_robot = np.array([-math.cos(yaw), -math.sin(yaw)])
                    flat = float(np.hypot(eye[0], eye[1]))
                    az = math.degrees(math.acos(max(-1.0, min(1.0, float(eye[:2] @ to_robot) / max(flat, 1e-9))))) if flat > 0.05 else 0.0
                    angles[side] = [round(math.degrees(math.atan2(float(eye[2]), flat)), 0), round(az, 0)]
            rec["views"] = views
            rec["angles"] = angles
            rec["ok"] = views["front"] is True and float(np.linalg.norm(w.locate("thing")[0] - start)) < 0.01
            rec["why"] = "" if rec["ok"] else f"front: {views['front']}"
        elif task == "press":
            r = _call(d, d.press, "device", control)
            rec["ok"] = r.get("status") == "ok"
            rec["why"] = "" if rec["ok"] else "press: " + str(r.get("reason"))
            rec["control"] = control
        elif task == "pour":
            r = _call(d, d.pick, "thing")
            if r.get("status") != "ok":
                return {**rec, "why": "pick: " + str(r.get("reason"))}
            rec["grasp"] = r.get("grasp")
            r = _call(d, d.pour, "recv")
            got = float(ep.state.vessels["recv"].total())
            rec["arrived_ml"] = round(got, 1)
            rec["ok"] = got >= 0.8 * 120.0
            rec["why"] = "" if rec["ok"] else ("pour: " + str(r.get("reason")) if r.get("status") != "ok" else "truth:missed")
        rec["time_s"] = round(w.time - t0, 1)
        rec["bystander_mm"] = round(1e3 * max([float(np.linalg.norm(w.locate(n)[0] - p0)) for n, p0 in others.items() if n != "recv"] or [0.0]), 1)
        return rec
    finally:
        w.close()
        d.mirror.world.close()


def _carry_scene(rng, kind: str, src: str, dst: str):
    """A counter (0.90 m) by the north wall and a dining table (0.75 m) by the east wall, a low table (0.42 m) by the
    west wall; the thing stands on one of them or on the floor, and is to be put on another, two metres away."""
    places = {"counter": (np.array([0.0, 1.65]), 0.90, np.array([0.0, -1.0])),          # middle, height, the side the robot comes from
              "table": (np.array([1.95, -0.6]), 0.75, np.array([-1.0, 0.0])),
              "low_table": (np.array([-2.15, -0.6]), 0.42, np.array([1.0, 0.0])),
              "floor": (np.array([-0.9, -1.2]), 0.0, np.array([0.0, 1.0]))}
    objects = [{"name": "counter", "kind": "counter", "params": {"height": 0.90}, "pos": [0.0, 1.65, 0.0], "fixed": True},
               {"name": "dining", "kind": "dining_table", "params": {"height": 0.75}, "pos": [1.95, -0.6, 0.0], "yaw_deg": 90.0, "fixed": True},
               {"name": "low_table", "kind": "low_table", "params": {"height": 0.42, "width": 1.0, "depth": 0.5}, "pos": [-2.15, -0.6, 0.0], "yaw_deg": 90.0, "fixed": True}]

    def spot(name):
        mid, top, side = places[name]
        along = np.array([-side[1], side[0]])
        inset = 0.0 if name == "floor" else {"counter": 0.30, "table": 0.40, "low_table": 0.25}[name] - float(rng.uniform(0.10, 0.20))
        p = mid + side * inset + along * float(rng.uniform(-0.25, 0.25))
        return np.array([p[0], p[1], top]), side

    at, side = spot(src)
    to, _ = spot(dst)
    if src == dst:                          # from the floor to the floor: two metres further on
        to = np.array([1.0, -1.3, 0.0]) + np.array([float(rng.uniform(-0.2, 0.2)), float(rng.uniform(-0.2, 0.2)), 0.0])
    # what the hand takes it by faces the side the robot comes from
    yaw = FACING.get(kind, float(rng.uniform(-180, 180))) + (float(rng.uniform(-15, 15)) if kind in FACING else 0.0)
    if kind in FACING:
        yaw += math.degrees(math.atan2(side[1], side[0])) + 90.0
    objects.append({"name": "thing", "kind": kind, "pos": [float(at[0]), float(at[1]), float(at[2]) + 0.004], "yaw_deg": yaw})
    start = [float(rng.uniform(-0.4, 0.4)), float(rng.uniform(-0.4, 0.2)), 0.0]
    scene = {"robot": {"pos": start, "yaw_deg": float(rng.uniform(-180, 180))}, "room": {"size": [5.0, 4.0]}, "objects": objects}
    return scene, at, to


def _carry_trial(kind: str, src: str, dst: str, seed: int, index: int, cameras: str) -> dict:
    """Take a thing, drive two metres with it in the hand, put it down. Judged as `pick_place` is; recorded besides:
    how far the robot and its load reached from the base's vertical while it drove, what it touched on the way, and
    whether the thing was still in the hand when it arrived."""
    from robosafe.core import stream
    from . import base as B
    from . import tf
    rng = stream(seed, f"sim.eval_room.carry.{kind}.{src}.{dst}", index)
    rec = {"task": "carry", "surface": f"{src} to {dst}", "height": 0.0, "kind": kind, "index": index, "is_trial": True, "ok": False, "why": ""}
    scene, at, to = _carry_scene(rng, kind, src, dst)
    try:
        ep, d = _stage(scene, {}, cameras)
    except Exception as e:
        return {**rec, "is_trial": False, "why": "scene: " + str(e)[:80]}
    w = ep.world
    try:
        t0 = w.time
        r = _call(d, d.go, "thing")
        if r.get("status") == "failed" or not r.get("arrived", True):
            return {**rec, "why": "go: " + str(r.get("reason"))}
        # carried up onto something higher: taken by the side (a hand that points down could not put it there)
        up = float(to[2]) > float(at[2]) + 0.20
        r = _call(d, d.pick, "thing", **({"grasp": "side"} if up else {}))
        if r.get("status") != "ok":
            return {**rec, "why": "pick: " + str(r.get("reason"))}
        rec["grasp"] = r.get("grasp")
        stat = _track(ep, d.mirror)
        reach = [0.0]
        inner = ep._tick

        def tick(row):
            inner(row)
            if float(np.hypot(*w.base_vel()[:2])) > 0.02:
                reach[0] = max(reach[0], B.extent(w))

        ep._tick = tick
        aim = to
        if dst == "floor":                      # `go` to a spot of the floor drives onto it: the base is sent 0.55 m short of the place
            here = w.base_pose()[:2]
            aim = np.append(to[:2] - 0.55 * (to[:2] - here) / max(float(np.linalg.norm(to[:2] - here)), 1e-6), 0.0)
        r = _call(d, d.go, aim.tolist())
        if dst == "floor" and r.get("status") != "failed" and r.get("arrived", True):
            f = _call(d, d.face, to.tolist())   # ... and turned towards it (a base sent to a spot of the floor faces the way it came)
            if f.get("status") == "failed":
                r = f
        rec["reach_m"] = round(reach[0], 2)
        rec["touched"] = {k: v for k, v in stat["touched"].items() if k != "thing"}
        rec["held_on_arrival"] = ep.held() == "thing"
        if r.get("status") == "failed" or not r.get("arrived", True):
            return {**rec, "why": "go with the load: " + str(r.get("reason"))}
        if not rec["held_on_arrival"]:
            return {**rec, "why": "truth:lost on the way"}
        rec["stand_off_m"] = round(float(np.linalg.norm(w.base_pose()[:2] - to[:2])), 2)
        r = _call(d, d.place, to.tolist())
        if r.get("status") != "ok":
            return {**rec, "why": "place: " + str(r.get("reason"))}
        p, q = w.locate("thing")
        tilt = math.degrees(math.acos(min(1.0, abs(float(tf.rotate(q, [0, 0, 1])[2])))))
        if ep.held() is not None:
            rec["why"] = "truth:still_held"
        elif np.linalg.norm(p[:2] - to[:2]) > 0.05 or abs(p[2] - to[2]) > 0.03:
            rec["why"] = "truth:misplaced"
        elif tilt > 12.0:
            rec["why"] = "truth:toppled"
        else:
            rec["ok"] = True
        rec["time_s"] = round(w.time - t0, 1)
        return rec
    finally:
        w.close()
        d.mirror.world.close()


def _press_scene(rng, surface: str, height: float, kind: str):
    """A device with a control: the hob counter itself, or an appliance on a counter or a table, its front to the robot."""
    from robosafe.assets import catalog
    if kind == "hob_counter":
        objects = [{"name": "device", "kind": "hob_counter", "params": {"height": height}, "pos": [0.0, 1.65, 0.0], "fixed": True}]
        control = "power_left" if rng.uniform() < 0.5 else "power_right"
        at = np.array([0.0, 1.35, height])
    else:
        depth = 0.60 if surface == "counter" else 0.80
        fy = 1.95 - depth / 2.0
        size = catalog.build(kind, None).meta["size"]
        x, y = float(rng.uniform(-0.25, 0.25)), fy - depth / 2.0 + float(size[1]) / 2.0 + float(rng.uniform(0.04, 0.10))
        objects = [{"name": "surface", "kind": surface, "params": {"height": height}, "pos": [0.0, fy, 0.0], "fixed": True},
                   {"name": "device", "kind": kind, "pos": [x, y, height + 0.004], "yaw_deg": float(rng.uniform(-10, 10)), "fixed": True}]
        controls = sorted(catalog.build(kind, None).meta.get("controls", {}))
        control = controls[int(rng.integers(len(controls)))]
        at = np.array([x, y, height])
    start = [float(rng.uniform(-1.0, 1.0)), float(rng.uniform(-1.2, -0.6)), 0.0]
    scene = {"robot": {"pos": start, "yaw_deg": float(rng.uniform(-180, 180))}, "room": {"size": [5.0, 4.0]}, "objects": objects}
    scene["_control"] = control
    return scene, at


def main(args) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results: list = []
    t_start = time.time()

    def log(rec):
        if not args.quiet:
            print(json.dumps({k: v for k, v in rec.items() if k not in ("touched",)}, default=str), flush=True)

    def save():
        out.write_text(json.dumps({"seed": args.seed, "cameras": args.cameras, "n": args.n, "spots": args.spots, "results": results,
                                   "wall_s": round(time.time() - t_start, 1)}, default=str))

    for task in args.tasks:
        if task in ("drive", "cross"):
            for i in range(args.n):
                results += _drive_room(args.seed, i, args.spots, task == "cross", args.cameras, log)
                save()
            continue
        if task == "carry":
            for kind, src, dst in CARRY:
                if args.kinds is not None and kind not in args.kinds:
                    continue
                for i in range(args.n):
                    try:
                        rec = _carry_trial(kind, src, dst, args.seed, i, args.cameras)
                    except Exception as e:
                        rec = {"task": "carry", "surface": f"{src} to {dst}", "height": 0.0, "kind": kind, "index": i, "is_trial": True, "ok": False,
                               "why": "error: " + repr(e)[:100]}
                    results.append(rec)
                    log(rec)
                save()
            continue
        cells = []
        if task == "pick_place":
            cells = [(s, h, k) for s in SURFACES for h in HEIGHTS for k in PICK_KINDS] + [("low_table", 0.42, k) for k in LOW_KINDS] + [("floor", 0.0, k) for k in LOW_KINDS]
        elif task == "look":
            cells = ([(s, h, k) for s in SURFACES for h in HEIGHTS for k in LOOK_KINDS] + [("low_table", 0.42, k) for k in LOOK_LOW_KINDS]
                     + [("floor", 0.0, k) for k in LOOK_LOW_KINDS])
        elif task == "press":
            cells = [("counter", h, "hob_counter") for h in HEIGHTS] + [(s, h, k) for s in SURFACES for h in HEIGHTS for k in PRESS_KINDS[1:]]
        elif task == "pour":
            cells = [(s, h, k) for s in SURFACES for h in HEIGHTS for k in POUR_KINDS]
        if args.kinds is not None:
            cells = [c for c in cells if c[2] in args.kinds]
        if args.heights is not None:
            cells = [c for c in cells if any(abs(c[1] - h) < 1e-6 for h in args.heights)]
        for surface, height, kind in cells:
            for i in range(args.n):
                scene_ok = True
                try:
                    rec = _arm_trial(task, surface, height, kind, args.seed, i, args.cameras)
                except Exception as e:              # a trial that broke is recorded, not hidden
                    rec = {"task": task, "surface": surface, "height": height, "kind": kind, "index": i, "is_trial": True, "ok": False,
                           "why": "error: " + repr(e)[:100]}
                results.append(rec)
                log(rec)
            save()
    save()
    return 0


def report(paths, before=None) -> str:
    """Markdown tables over result files of `eval_room`. Files of different camera conditions are kept apart (a cell
    reads `room, onboard`); with `before` (result files of an earlier measurement) a cell reads `before → now`."""
    def load(ps):
        by = {}
        for p in ps or ():
            d = json.loads(Path(p).read_text())
            by.setdefault(d.get("cameras", "room"), []).extend(r for r in d["results"] if r.get("is_trial"))
        return by

    now, old = load(paths), [r for rs in load(before).values() for r in rs]
    conds = [c for c in ("room", "onboard") if c in now]
    out = []
    if len(conds) > 1 or old:
        out.append("Cells: " + ("the first measurement → " if old else "") + ", ".join(f"with the `{c}` cameras" for c in conds) + ".\n")

    def frac(rs):
        return f"{sum(r['ok'] for r in rs)}/{len(rs)}" if rs else "-"

    def cell(pick):
        new = ", ".join(frac(pick(now[c])) for c in conds)
        was = pick(old)
        return f"{frac(was)} → {new}" if old and was else new

    def reasons(rs, k=4):
        c = Counter(r["why"] for r in rs if not r["ok"] and r.get("why"))
        return "; ".join(f"{w} x{n}" for w, n in c.most_common(k))

    for task in ("drive", "cross"):
        for label, rows in ([("first measurement", old)] if old else []) + [(f"`{c}` cameras", now[c]) for c in conds]:
            rs = [r for r in rows if r["task"] == task]
            if not rs:
                continue
            ok = [r for r in rs if r["ok"]]
            touched = [r for r in rs if r["contact_ticks"]]
            clear = sorted(r["clearance_m"] for r in rs)
            times = [r["time_s"] / max(r["planned_m"], 0.1) for r in ok]
            out.append(f"**{task}**, {label}: {len(rs)} spots, {len(ok)} reached ({100 * len(ok) // len(rs)} %); the way planned was {np.mean([r['planned_m'] for r in rs]):.1f} m on average "
                       f"({min(r['planned_m'] for r in rs):.1f} to {max(r['planned_m'] for r in rs):.1f}), {np.mean([r['calls'] for r in rs]):.1f} calls and "
                       f"{np.mean([r['time_s'] for r in ok]) if ok else 0:.1f} s of robot time per reached spot ({np.mean(times) if times else 0:.1f} s per metre). "
                       f"Shortest distance of the base's circle to anything: least {clear[0]:.3f} m, median {clear[len(clear) // 2]:.3f} m. "
                       f"Spots on whose way the robot touched something: {len(touched)}" + (f" (largest force {max(r['peak_force'] for r in touched):.0f} N)" if touched and task == "drive" else "") + ".")
            if task == "cross":
                gaps = sorted(r["crosser_gap_m"] for r in rs if r["crosser_gap_m"] is not None)
                hit = [r for r in rs if "crosser" in r.get("touched", {})]
                out.append(f"The figure that crossed: nearest to the base's circle {gaps[0]:.3f} m at least, median {gaps[len(gaps) // 2]:.3f} m; within 0.5 m in "
                           f"{sum(1 for g in gaps if g < 0.5)} of {len(gaps)}; touched in {len(hit)}"
                           + (f" (the base moving at {np.mean([r['speed_at_contact'] for r in hit]):.2f} m/s on average when it first touched, at most {max(r['speed_at_contact'] for r in hit):.2f})" if hit else "") + ".")
                out.append("\n| crosser | spots | reached | touched the figure | not_reached | least gap (m) |\n|---|---|---|---|---|---|")
                for c in CROSSERS:
                    cs = [r for r in rs if r["crosser"] == c]
                    if cs:
                        out.append(f"| {c} | {len(cs)} | {sum(r['ok'] for r in cs)} | {sum(1 for r in cs if 'crosser' in r.get('touched', {}))} | "
                                   f"{sum(1 for r in cs if r['why'] == 'not_reached')} | {min(r['crosser_gap_m'] for r in cs):.3f} |")
            bad = reasons(rs)
            if bad:
                out.append(f"\nNot reached: {bad}.")
            out.append("")
    if any(r["task"] == "carry" for c in conds for r in now[c]):
        out.append("**carry** (taken, driven with, put down: successes / trials)\n")
        out.append("| kind | from | to | done | reach while driving (m) | why not |\n|---|---|---|---|---|---|")
        allc = [r for c in conds for r in now[c] if r["task"] == "carry"]
        for kind, src, dst in CARRY:
            pick = lambda rs: [r for r in rs if r["task"] == "carry" and r["kind"] == kind and r["surface"] == f"{src} to {dst}"]
            c = pick(allc)
            if not c:
                continue
            reach = [r["reach_m"] for r in c if r.get("reach_m")]
            out.append(f"| {kind} | {src} | {dst} | " + ", ".join(frac(pick(now[k])) for k in conds) + " | "
                       + (f"{min(reach):.2f} to {max(reach):.2f}" if reach else "-") + f" | {reasons(c)} |")
        out.append("| all | | | " + ", ".join(frac([r for r in now[k] if r["task"] == "carry"]) for k in conds) + " | | |")
        for k in conds:
            drove = [r for r in now[k] if r["task"] == "carry" and "reach_m" in r]
            hit = [r for r in drove if r.get("touched")]
            out.append(f"\n`{k}`: of {len(drove)} drives with something in the hand, {sum(1 for r in drove if r['held_on_arrival'])} arrived with it; "
                       f"the robot or its load touched something on {len(hit)}"
                       + (" (" + "; ".join(f"{n} x{v}" for n, v in Counter(n for r in hit for n in r['touched']).most_common(4)) + ")" if hit else "") + ".")
        out.append("")
    for task in ("pick_place", "look", "press", "pour"):
        allr = [r for c in conds for r in now[c] if r["task"] == task]
        if not allr:
            continue
        out.append(f"**{task}** (successes / trials)\n")
        cols = sorted({(r["surface"], r["height"]) for r in allr}, key=lambda c: (c[1], c[0]))
        out.append("| kind | " + " | ".join(f"{s} {h:.2f} m" if s != "floor" else "floor" for s, h in cols) + " | why not (now) |")
        out.append("|---|" + "---|" * (len(cols) + 1))
        for kind in sorted({r["kind"] for r in allr}):
            cells = [cell(lambda rs, s=s, h=h: [r for r in rs if r["task"] == task and r["kind"] == kind and r["surface"] == s and r["height"] == h]) for s, h in cols]
            cells = ["-" if c.replace("→", "").replace(",", "").replace("-", "").strip() == "" else c for c in cells]
            out.append(f"| {kind} | " + " | ".join(cells) + f" | {reasons([r for r in allr if r['kind'] == kind])} |")
        tot = [cell(lambda rs, s=s, h=h: [r for r in rs if r["task"] == task and r["surface"] == s and r["height"] == h]) for s, h in cols]
        out.append("| all | " + " | ".join(tot) + " | |")
        for k in conds:
            rs = [r for r in now[k] if r["task"] == task]
            moved = [r for r in rs if r.get("bystander_mm", 0.0) > 10.0]
            line = f"\n`{k}`: a bystander moved more than 10 mm in {len(moved)} of {len(rs)} trials; mean stand-off of the base from the thing {np.mean([r['stand_off_m'] for r in rs if 'stand_off_m' in r]):.2f} m."
            if task == "pick_place":
                g = Counter((r["height"], r.get("grasp")) for r in rs if r.get("grasp"))
                line += " Grasps taken: " + "; ".join(f"{h:.2f} m {n}: {v}" for (h, n), v in sorted(g.items())) + "."
                homed = [r for r in rs if "home" in r]
                if homed:
                    bad = Counter(r["home_why"] for r in homed if not r["home"])
                    line += (f" After the place the arm came back to its rest posture in {sum(r['home'] for r in homed)} of {len(homed)}"
                             + (" (" + "; ".join(f"{w} x{n}" for w, n in bad.most_common(3)) + ")" if bad else "")
                             + f"; the thing put down was moved more than 10 mm by that in {sum(1 for r in homed if r['after_home_mm'] > 10.0)}.")
                again = [r for r in rs if "after_go" in r]
                if again:
                    bad = Counter(r["after_go"] for r in again if r["after_go"] != "ok")
                    line += (f" Where `place` found the place out of the arm's reach ({len(again)} trials) the base was sent to the place and `place` "
                             f"called again: {sum(1 for r in again if r['after_go'] == 'ok')} then put the thing down where it was to go"
                             + (" (the others: " + "; ".join(f"{w} x{n}" for w, n in bad.most_common(4)) + ")" if bad else "") + ".")
            out.append(line)
        if task == "look":
            def view(c, side):
                got = [r for r in c if r["views"].get(side) is True]
                ang = [r["angles"][side] for r in got if side in r.get("angles", {})]
                if not ang:
                    return f"{len(got)}/{len(c)}"
                el, az = sorted(a[0] for a in ang), sorted(a[1] for a in ang)
                where = f"{el[len(el) // 2]:.0f} down" if side == "above" else f"{az[len(az) // 2]:.0f} round, {el[len(el) // 2]:.0f} down"
                return f"{len(got)}/{len(c)} ({where})"

            for k in ([None] if old else []) + conds:
                rs = [r for r in (old if k is None else now[k]) if r["task"] == "look" and "views" in r]
                out.append(f"\nViews taken, {'first measurement' if k is None else '`' + k + '` cameras'}:\n\n| height | " + " | ".join(LOOK_SIDES) + " |\n|---|" + "---|" * len(LOOK_SIDES))
                for h in sorted({r["height"] for r in rs}):
                    c = [r for r in rs if r["height"] == h]
                    out.append(f"| {h:.2f} m | " + " | ".join(view(c, side) for side in LOOK_SIDES) + " |")
            out.append("\nIn brackets: the way the camera looked, the median over the views taken: degrees round from the robot's side of the thing "
                       "(0 from the front, 90 square from the left or right, 180 from the back) and degrees down from the horizon.")
        out.append("")
    return "\n".join(out)
