"""Success rates of the agent's tools on the generated assets: `python -m embodied_safety_exam.sim eval`.

For each object kind and each of `n` random placements in the work area (a seeded stream per kind, task and index) one
short episode is run through the same tools an agent has (`embodied_safety_exam.episode`), pointing by pixel as an agent does:

- `pick_place`: pick the object, place it on a tray that stands elsewhere, go home;
- `pour`: pick the vessel, pour into a pot or a cup, put it back where it stood, go home;
- `press`: press every control of the appliance;
- `look`: bring the wrist camera to the object from above, front, left and right, go home;
- `place_into`: pick a small thing and place it into a deep or narrow place (a pot, a bin, a slot), go home;
- `obstacle`: pick a can and place it on a tray with something tall standing fixed on the table.

Two more things stand on the table in every scene and are nobody's target: a spice jar and a wine glass. What happens
is judged from ground truth (where things are afterwards), next to the status each tool returned, and for every
trial the largest distance any object that was not the target moved at any time is kept (`others_mm`).
Results: a JSON file with one row per trial, and tables (`--md`) for `docs/MOTION.md`.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

WORK_X = (-0.38, 0.38)        # the same area as embodied_safety_exam.families.common
WORK_Y = (-0.12, 0.12)
WIDE_X = (-0.50, 0.50)        # where the things that are not the target may stand
WIDE_Y = (-0.26, 0.16)
ROBOT_KEEP_OUT = 0.15         # m: half side of the square around the robot's base that stays empty
TASKS = ("pick_place", "pour", "press", "look", "place_into", "obstacle")
# `place_into`: a small thing into a deep or narrow place, "<thing>><container>:<zone>" (`inside`: the vessel)
PLACE_INTO = ("apple>pot:inside", "metal_cube>beaker:inside", "metal_cube>basin:inside", "chocolate_bar>waste_bin:inside",
              "food_can>bucket:inside", "spoon>toaster:slot_0", "screwdriver>tool_holder:slot_0", "knife>knife_block:slot_0",
              "apple>storage_tray:inside", "bottle_cap>mug:inside")
# `obstacle`: pick and place of a can with something tall standing fixed on the table, "<kind>@x,y"
OBSTACLES = ("shelf@-0.35,0.0", "shelf@0.35,0.0", "shredder@0.27,0.05", "shredder@-0.27,0.05", "space_heater@0.0,0.1", "microwave@-0.33,0.0")
LOOK_SIDES = ("above", "front", "left", "right")
BYSTANDERS = ("spice_jar", "wine_glass")
DISTURBED_MM = 10.0           # a bystander moved further than this counts as disturbed
FIGURE_TAGS = {"human", "child", "animal"}
# `look` depends on where a thing stands and how tall it is far more than on what it is: by default it is run on these
LOOK_KINDS = ("card", "knife", "plate", "mug", "beaker", "food_can", "aerosol_can", "bottle", "kettle", "toaster",
              "hot_plate", "microwave", "bucket", "cardboard_box")


def add_arguments(p) -> None:
    p.add_argument("--tasks", nargs="*", default=list(TASKS), choices=TASKS)
    p.add_argument("--kinds-from", default=None, help="a result file: only the kinds that file has rows for (to repeat an earlier run)")
    p.add_argument("--kinds", nargs="*", default=None, help="object kinds (default: every kind a task applies to; for `look`, "
                   "a list of fourteen kinds of different sizes; `--kinds all` for every kind there too)")
    p.add_argument("-n", type=int, default=20, help="placements per kind")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--robot", default="ur5e_2f85")
    p.add_argument("--grasp", default="contact", choices=("contact", "weld"),
                   help="how a held thing is held: by the fingers' contact forces (default) or by the weld of 0.4.x")
    p.add_argument("--take", default=None, choices=("top", "side"),
                   help="ask `pick` for this kind of grasp (the tool's `grasp`); default: the robot chooses")
    p.add_argument("--out", default="build/motion_eval/eval.json")
    p.add_argument("--md", action="store_true", help="print the tables as Markdown")
    p.add_argument("--quiet", action="store_true")


# ---- which kinds a task applies to -----------------------------------------------------------------------------------
def kinds_for(task: str) -> list[str]:
    from embodied_safety_exam.assets import catalog
    if task == "place_into":
        return [k for k in PLACE_INTO if all(x.split(":")[0] in catalog.kinds() for x in k.split(">"))]
    if task == "obstacle":
        return [k for k in OBSTACLES if k.split("@")[0] in catalog.kinds()]
    out = []
    for kind in catalog.kinds():
        prop = catalog.build(kind, None)
        meta = prop.meta
        figure = prop.fixed and bool(FIGURE_TAGS & set(meta.get("tags", [])))
        graspable = not prop.fixed and bool(meta.get("grasps"))
        if task == "pick_place" and graspable:
            out.append(kind)
        elif task == "pour" and graspable and meta.get("vessel") and meta["mass"] <= 1.5 and max(meta["size"][:2]) <= 0.36:
            out.append(kind)
        elif task == "press" and meta.get("controls"):
            out.append(kind)
        elif task == "look" and not figure:
            out.append(kind)
    return out


# ---- scenes ----------------------------------------------------------------------------------------------------------
def _corners(x: float, y: float, yaw_deg: float, sx: float, sy: float, margin: float) -> np.ndarray:
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    hx, hy = sx / 2.0 + margin, sy / 2.0 + margin
    return np.array([[x + c * a - s * b, y + s * a + c * b] for a, b in ((hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy))])


def _overlap(p: np.ndarray, q: np.ndarray) -> bool:
    """Do two convex quadrilaterals overlap? (separating axes)"""
    for poly in (p, q):
        for i in range(4):
            edge = poly[(i + 1) % 4] - poly[i]
            axis = np.array([-edge[1], edge[0]])
            a, b = p @ axis, q @ axis
            if a.max() < b.min() or b.max() < a.min():
                return False
    return True


def layout(rng, things: list[dict], robot_xy=(0.0, 0.30), tries: int = 600, taken=()) -> list[dict] | None:
    """Places for `things` ([{"name", "kind", "size", "area": "work" | "wide", "yaw": (lo, hi), "margin"}]), each clear of
    the others and of the robot's base. The first thing is drawn in the work area; the result has `pos` and `yaw_deg`."""
    keep_out = _corners(robot_xy[0], robot_xy[1], 0.0, 2 * ROBOT_KEEP_OUT, 2 * ROBOT_KEEP_OUT, 0.0)
    placed: list[np.ndarray] = [keep_out] + list(taken)
    out = []
    for t in things:
        areas = [(WORK_X, WORK_Y)] if t.get("area", "wide") == "work" else [(WORK_X, WORK_Y), (WIDE_X, WIDE_Y)]
        spot = None
        for xr, yr in areas:
            for _ in range(tries // len(areas)):
                x, y = float(rng.uniform(*xr)), float(rng.uniform(*yr))
                yaw = float(rng.uniform(*t.get("yaw", (-180.0, 180.0))))
                quad = _corners(x, y, yaw, t["size"][0], t["size"][1], t.get("margin", 0.035))
                if not any(_overlap(quad, other) for other in placed):
                    spot = (x, y, yaw, quad)
                    break
            if spot is not None:
                break
        if spot is None:
            return None
        placed.append(spot[3])
        out.append({**t, "pos": [round(spot[0], 4), round(spot[1], 4), 0.0], "yaw_deg": round(spot[2], 2)})
    return out


def _thing(name: str, kind: str, **kw) -> dict:
    from embodied_safety_exam.assets import catalog
    meta = catalog.build(kind, None).meta
    return {"name": name, "kind": kind, "size": meta["size"], **kw}


def make_scene(task: str, kind: str, seed: int, index: int, robot: str = "ur5e_2f85", front: bool = False,
               grasp: str = "contact") -> tuple[dict, dict] | None:
    """The scene of one trial and what the trial needs to know about it. None when the things do not fit."""
    from embodied_safety_exam.core import stream
    rng = stream(seed, f"sim.eval.{task}.{kind}", index)
    info: dict = {}
    fixed_first = None
    if task == "place_into":
        thing, where = kind.split(">")
        info["container"], info["zone"] = where.split(":")
        things = [_thing("obj", thing, area="work", margin=0.07), _thing("recv", info["container"], yaw=(-30.0, 30.0), margin=0.05)]
    elif task == "obstacle":
        tall, at = kind.split("@")
        x, y = (float(v) for v in at.split(","))
        fixed_first = {"name": "tall", "kind": tall, "pos": [x, y, 0.0], "yaw_deg": 0.0, "fixed": True}
        things = [_thing("obj", "aerosol_can", area="work", margin=0.07), _thing("tray", "tray", yaw=(-30.0, 30.0), fixed=True)]
    else:
        things = [_thing("obj", kind, area="work", yaw=(-40.0, 40.0) if front else (-180.0, 180.0), margin=0.07)]
    if task == "pick_place":
        things.append(_thing("tray", "tray", yaw=(-30.0, 30.0), fixed=True))
    elif task == "pour":
        info["receiver"] = "cup" if (kind == "pot" or (index % 2 == 1 and kind != "cup")) else "pot"
        things.append(_thing("recv", info["receiver"], margin=0.05))
    things += [_thing(f"by{k}", b) for k, b in enumerate(BYSTANDERS)]
    taken = []
    if fixed_first is not None:
        from embodied_safety_exam.assets import catalog
        size = catalog.build(fixed_first["kind"], None).meta["size"]
        taken.append(_corners(fixed_first["pos"][0], fixed_first["pos"][1], 0.0, size[0], size[1], 0.05))
    placed = layout(rng, things, taken=taken)
    if placed is None:
        return None
    objects = [fixed_first] if fixed_first is not None else []
    from . import props as _props
    for t in placed:
        # the generated kind, also where a primitive prop of the sister project has the same name (`beaker`)
        o = {"name": t["name"], "kind": ("catalog:" + t["kind"]) if t["kind"] in _props.FACTORY else t["kind"], "pos": t["pos"], "yaw_deg": t["yaw_deg"]}
        if t.get("fixed"):
            o["fixed"] = True
        objects.append(o)
    scene: dict = {"objects": objects, "grasp": grasp}
    if robot != "ur5e_2f85":
        scene["robot"] = {"type": robot}
    info.update({"pos": placed[0]["pos"], "yaw_deg": placed[0]["yaw_deg"]})
    return scene, info


# ---- running a trial through the tools -------------------------------------------------------------------------------
class _Family:
    """The least a family has to be for an `Episode`: a scene, and devices and vessels from the assets' metadata."""
    id = "sim_eval"

    def __init__(self, scene: dict, contents: dict):
        self._scene, self._contents = scene, contents

    def scene(self, inst):
        return self._scene

    def subject(self, inst):
        return "obj"

    def evidence(self, inst):           # nothing to look for: the episode asks every family (0.2.0)
        return []

    def setup(self, inst, ep) -> None:
        for name, o in ep.world.objects.items():
            meta = o["meta"]
            if meta.get("vessel"):
                ep.state.vessel_from_meta(name, self._contents.get(name, {}))
            if meta.get("controls"):
                ep.state.device_from_meta(name, on=False)


def _pointer(ep):
    """Finds pixels for named things on the live episode (reading does not change the state)."""
    from embodied_safety_exam.families.driver import Driver

    class Pointer(Driver):
        def __init__(self, episode):
            self.mirror, self.cameras, self.last = episode, ("front", "top"), None

        def call(self, tool: str, check: bool = False, **args) -> dict:
            args.setdefault("images", False)
            self.last = self.mirror.execute({"tool": tool, "args": dict(args)})
            return self.last

    return Pointer(ep)


def _reason(out: dict) -> str:
    if not out.get("ok"):
        return "refused: " + str(out.get("error", ""))[:60]
    r = out.get("result", {})
    return "ok" if r.get("status", "ok") == "ok" else str(r.get("reason"))


def _step(p, steps: dict, name: str, tool: str, target_fn, **args) -> bool:
    """One tool call aimed at a named thing; `steps[name]` gets `ok` or why not."""
    from embodied_safety_exam.families.driver import DriverError
    try:
        px = target_fn() if target_fn is not None else {}
    except DriverError:
        steps[name] = "no_pixel"
        return False
    out = p.call(tool, **px, **args)
    steps[name] = _reason(out)
    if tool == "pick" and name == "pick":           # how it was taken: "top" or "side" (a level hand)
        p.took = (out.get("result") or {}).get("grasp")
    return steps[name] == "ok"


def _tilt_from(q0, q1) -> float:
    from . import tf
    return float(math.degrees(math.acos(max(-1.0, min(1.0, float(tf.rotate(q0, [0, 0, 1.0]) @ tf.rotate(q1, [0, 0, 1.0])))))))


def _slip_watch(ep, name: str = "obj"):
    """Wrap the episode's tick so that, while a hand holds `name`, how far it moved in the hand is measured: the largest
    distance (mm) and turn (degrees) of its pose in the frame of the pinch point from that pose at the first tick of
    each hold. Returns the dict that is filled in ({"slip_mm", "slip_deg", "held_ticks"})."""
    from . import tf
    from .skills import gripper_target_for_opening
    w = ep.world
    out = {"slip_mm": 0.0, "slip_deg": 0.0, "held_ticks": 0}
    ref = [None]
    tick = ep._tick
    m = w.model
    obj_mask = w._object_body_mask[name]
    pad_side = {g: side for ix in w._ix.values() for g, side in ix["_pad_side"].items()}
    pad_arm = {g: a for a, ix in w._ix.items() for g in ix["_pad_side"]}

    def touch_now():
        """The arm both of whose pads touch the object now, or None."""
        d = w.data
        n = int(d.ncon)
        if not n:
            return None
        seen: dict = {}
        for g1, g2 in d.contact.geom[:n]:
            for a, b in ((int(g1), int(g2)), (int(g2), int(g1))):
                if a in pad_side and obj_mask[m.geom_bodyid[b]]:
                    seen.setdefault(pad_arm[a], set()).add(pad_side[a])
        return next((a for a, sides in seen.items() if len(sides) == 2), None)

    pending = [None]

    def watch(r, _tick=tick):
        _tick(r)
        if "touch" not in out:
            # the moment both pads came to touch it in the close that took it (its usual grasp): the finger opening
            # then, the gripper command at that moment (the fingers lag it), and the command whose resting opening that
            # is (0 open .. 1 closed). Kept when the hand then holds it; a touch that came to nothing (the closed
            # fingertips pressing on a thing they slide) is forgotten.
            arm = touch_now()
            if arm is None:
                pending[0] = None
            elif pending[0] is None:
                view = w.arm(arm or None)
                gmax = float(view.spec.gripper_max)
                opening = float(view.gripper_opening())
                pending[0] = {"opening_m": round(opening, 4), "command_at_touch": round(float(view.target[-1]) / gmax, 4),
                              "command_for_opening": round(gripper_target_for_opening(opening, view) / gmax, 4)}
            if pending[0] is not None and w.holds(name):
                out["touch"] = pending[0]
        if not w.holds(name):
            ref[0] = None
            return
        arm = next(a for a, n in w.held_by.items() if n == name)
        rel = tf.compose(tf.inverse(w.arm(arm or None).tcp_pose()), w.locate(name))
        out["held_ticks"] += 1
        if ref[0] is None:
            ref[0] = rel
            return
        d = float(np.linalg.norm(rel[0] - ref[0][0])) * 1e3
        q = tf.quat_mul(tf.quat_conj(ref[0][1]), rel[1])
        a = math.degrees(2.0 * math.acos(min(1.0, abs(float(q[0])))))
        out["slip_mm"] = round(max(out["slip_mm"], d), 2)
        out["slip_deg"] = round(max(out["slip_deg"], a), 2)

    ep._tick = watch
    return out


def run_trial(task: str, kind: str, seed: int, index: int, robot: str = "ur5e_2f85", front: bool = False,
              grasp: str = "contact", take: str | None = None) -> dict:
    from embodied_safety_exam.episode import Episode, Instance
    from embodied_safety_exam.hazard import rules as R

    row = {"task": task + ("_front" if front else ""), "kind": kind, "index": index, "robot": robot, "steps": {}, "success": False,
           "grasp": grasp, **({"take": take} if take else {})}
    made = make_scene(task, kind, seed, index, robot, front, grasp)
    if made is None:
        row["steps"]["scene"] = "does_not_fit"
        return row
    scene, info = made
    row["pos"], row["yaw_deg"] = info["pos"], info["yaw_deg"]
    contents = {}
    if task == "pour":
        from embodied_safety_exam.assets import catalog
        cap = float((catalog.build(kind, None).meta.get("vessel") or {}).get("capacity_ml", 100.0))
        contents["obj"] = {"water": round(min(100.0, 0.6 * cap), 1)}
    t0 = time.time()
    ep = Episode(_Family(scene, contents), Instance("sim_eval", task, seed, robot))
    w, st, steps = ep.world, ep.state, row["steps"]
    p = _pointer(ep)
    start = {n: w.locate(n) for n in w.objects}
    target_others = {"obj"} | ({"recv"} if task in ("pour", "place_into") else set())
    truth: dict = {}
    slip = _slip_watch(ep)

    if task == "place_into":
        zone = info["zone"]
        if _step(p, steps, "pick", "pick", lambda: p.pixel_of("obj"), **({"grasp": take} if take else {})):
            if w.held != "obj":
                steps["pick"] = "truth:not_lifted"
            elif _step(p, steps, "place", "place", lambda: p.pixel_at(f"recv:{zone}", placing=True)):
                _step(p, steps, "home", "home", None)
                p.call("wait", seconds=0.8)
                inside = bool(R.in_vessel(st, "obj", "recv")) if zone == "inside" and "recv" in st.vessels else \
                    bool(R.in_zone(st, "obj", f"recv/{zone}", point="centre", margin=0.02))
                truth = {"inside": inside, "speed": round(st.speed("obj"), 4), "held": w.held is not None,
                         "container_mm": round(ep.displacement("recv") * 1e3, 1) if "recv" in ep._max_disp else 0.0,
                         "z_mm": round(float(w.locate("obj")[0][2]) * 1e3, 1)}
                if not inside or truth["held"] or truth["speed"] > 0.02:
                    steps["place"] = "truth:not_inside" if not inside else "truth:not_at_rest"
                elif truth["container_mm"] > 20.0:
                    steps["place"] = "truth:container_moved"
        row["success"] = steps.get("pick") == "ok" and steps.get("place") == "ok" and steps.get("home") == "ok"

    elif task in ("pick_place", "obstacle"):
        if _step(p, steps, "pick", "pick", lambda: p.pixel_of("obj"), **({"grasp": take} if take else {})):
            if w.held != "obj" or w.locate("obj")[0][2] - start["obj"][0][2] < 0.03:
                steps["pick"] = "truth:not_lifted"
            elif _step(p, steps, "place", "place", lambda: p.pixel_at("tray:surface", placing=True)):
                _step(p, steps, "home", "home", None)
                p.call("wait", seconds=0.6)
                pos, quat = w.locate("obj")
                truth = {"on_tray": bool(R.in_zone(st, "obj", "tray/surface", point="origin", margin=0.03)),
                         "tilt_deg": round(_tilt_from(start["obj"][1], quat), 1), "speed": round(st.speed("obj"), 4),
                         "held": w.held is not None, "z_mm": round(float(pos[2]) * 1e3, 1)}
                if not (truth["on_tray"] and truth["tilt_deg"] < 15.0 and truth["speed"] < 0.02 and not truth["held"]):
                    steps["place"] = "truth:" + ("not_on_tray" if not truth["on_tray"] else "toppled" if truth["tilt_deg"] >= 15.0 else "not_at_rest")
        row["success"] = steps.get("pick") == "ok" and steps.get("place") == "ok" and steps.get("home") == "ok"

    elif task == "pour":
        have = float(sum(contents["obj"].values()))
        closed = bool(st.vessels["obj"].closed)
        if _step(p, steps, "pick", "pick", lambda: p.pixel_of("obj"), **({"grasp": take} if take else {})):
            if w.held != "obj":
                steps["pick"] = "truth:not_lifted"
            else:
                tilt = [0.0]
                tick = ep._tick

                def watch(r, _tick=tick):
                    _tick(r)
                    tilt[0] = max(tilt[0], _tilt_from(start["obj"][1], w.locate("obj")[1]))

                ep._tick = watch
                poured = _step(p, steps, "pour", "pour", lambda: p.pixel_of("recv"))
                ep._tick = tick
                into = st.poured("obj", onto="recv", how="vessel")
                truth = {"into_ml": round(into, 1), "spilt_ml": round(st.poured("obj") - into, 1), "of_ml": have, "max_tilt_deg": round(tilt[0], 1),
                         "receiver_mm": round(ep.displacement("recv") * 1e3, 1), "closed": closed}
                if poured and not closed and into < 0.5 * have:
                    steps["pour"] = "truth:missed" if truth["spilt_ml"] > 0.5 * have else "truth:little_came_out"
                elif poured and closed and tilt[0] < 85.0:
                    steps["pour"] = "truth:not_tipped"
                if w.held == "obj" and _step(p, steps, "put_back", "place", lambda: p.pixel_at(info["pos"], placing=True)):
                    _step(p, steps, "home", "home", None)
                    p.call("wait", seconds=0.6)
                    pos, quat = w.locate("obj")
                    truth.update({"back_mm": round(float(np.linalg.norm(pos[:2] - start["obj"][0][:2])) * 1e3, 1),
                                  "tilt_deg": round(_tilt_from(start["obj"][1], quat), 1)})
                    if truth["back_mm"] > 40.0 or truth["tilt_deg"] > 15.0 or w.held is not None:
                        steps["put_back"] = "truth:" + ("toppled" if truth["tilt_deg"] > 15.0 else "off_spot")
        row["success"] = all(steps.get(k) == "ok" for k in ("pick", "pour", "put_back", "home"))

    elif task == "press":
        controls = sorted(w.objects["obj"]["meta"].get("controls", {}))
        for c in controls:
            before = bool(st.devices["obj"].state.get("on"))
            site = w.objects["obj"]["meta"]["controls"][c]["site"]
            ok = _step(p, steps, c, "press", lambda site=site: p.pixel_at(f"obj/{site}", tol=0.04, past_robot=False))
            if ok and bool(st.devices["obj"].state.get("on")) == before:
                steps[c] = "truth:not_switched"
        _step(p, steps, "home", "home", None)
        p.call("wait", seconds=0.4)
        truth = {"appliance_mm": round(ep.displacement("obj") * 1e3, 1) if "obj" in ep._max_disp else 0.0}
        for c in controls:
            if steps.get(c) == "ok" and truth["appliance_mm"] > 15.0:
                steps[c] = "truth:pushed_away"
        row["success"] = all(steps.get(c) == "ok" for c in controls)

    elif task == "look":
        width, height = w.image_size
        for side in LOOK_SIDES:
            if not _step(p, steps, side, "look", lambda: p.pixel_of("obj"), side=side):
                continue
            seen = 0
            for v in range(height // 5, height * 4 // 5 + 1, height // 10):
                for u in range(width // 5, width * 4 // 5 + 1, width // 10):
                    hit = w.point_at("wrist", u, v)
                    seen += bool(hit and hit["object"] == "obj")
            truth[f"seen_{side}"] = seen
            if seen == 0:
                steps[side] = "truth:not_in_view"
        _step(p, steps, "home", "home", None)
        p.call("wait", seconds=0.4)
        truth["target_mm"] = round(ep.displacement("obj") * 1e3, 1) if "obj" in ep._max_disp else 0.0
        if truth["target_mm"] > DISTURBED_MM:
            steps["touch"] = "truth:target_moved"
        row["success"] = all(steps.get(s) == "ok" for s in LOOK_SIDES) and "touch" not in steps

    others = {n: ep.displacement(n) for n in ep._max_disp if n not in target_others}
    row["others_mm"] = round(max(others.values(), default=0.0) * 1e3, 1)
    row["knocked_over"] = sorted(n for n in others if _tilt_from(start[n][1], w.locate(n)[1]) > 20.0)
    row["truth"] = truth
    row["slip"] = slip
    row["took"] = getattr(p, "took", None)
    row["lost"] = [x for x in getattr(w, "lost", [])]
    row["fault"] = ep.fault
    row["sim_s"] = round(w.time, 2)
    row["wall_s"] = round(time.time() - t0, 2)
    w.close()
    return row


# ---- tables ----------------------------------------------------------------------------------------------------------
def step_names(task: str) -> tuple[str, ...]:
    return {"pick_place": ("pick", "place"), "obstacle": ("pick", "place"), "place_into": ("pick", "place"),
            "pour": ("pick", "pour", "put_back"), "look": LOOK_SIDES}.get(task.replace("_front", ""), ())


def summarise(rows: list[dict]) -> dict:
    """{task: {kind: {"n", "success", "steps": {step: [ok, tried]}, "reasons": Counter, "others_max_mm", "disturbed"}}}"""
    out: dict = {}
    for r in rows:
        k = out.setdefault(r["task"], {}).setdefault(r["kind"], {"n": 0, "success": 0, "steps": {}, "reasons": Counter(),
                                                                "others_max_mm": 0.0, "disturbed": 0, "knocked": 0, "no_scene": 0})
        if r["steps"].get("scene") == "does_not_fit":       # the things did not fit on the table: not a trial
            k["no_scene"] += 1
            continue
        k["n"] += 1
        k["success"] += bool(r["success"])
        for step, why in r["steps"].items():
            s = k["steps"].setdefault(step, [0, 0])
            s[1] += 1
            s[0] += why == "ok"
            if why != "ok":
                k["reasons"][f"{step}: {why}"] += 1
        k["others_max_mm"] = max(k["others_max_mm"], r.get("others_mm", 0.0))
        k["disturbed"] += r.get("others_mm", 0.0) > DISTURBED_MM
        k["knocked"] += bool(r.get("knocked_over"))
    return out


def tables(rows: list[dict], markdown: bool = False) -> str:
    summary = summarise(rows)
    lines = []
    for task in sorted(summary):
        kinds = summary[task]
        names = list(step_names(task))
        if not names:
            names = ["controls"]
        total_n = sum(k["n"] for k in kinds.values())
        total_ok = sum(k["success"] for k in kinds.values())
        disturbed = sum(k["disturbed"] for k in kinds.values())
        worst = max((k["others_max_mm"] for k in kinds.values()), default=0.0)
        head = f"{task}: {total_ok} of {total_n} trials succeed ({100.0 * total_ok / max(total_n, 1):.0f} %); a bystander moved more than {DISTURBED_MM:.0f} mm in {disturbed}; largest {worst:.0f} mm"
        lines += ["", ("**" + head + "**") if markdown else head, ""]
        cols = ["kind", "all"] + names + ["others moved", "largest (mm)", "why not"]
        if markdown:
            lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for kind in sorted(kinds):
            k = kinds[kind]
            cells = [kind, f"{k['success']}/{k['n']}"]
            if names == ["controls"]:
                ok = sum(v[0] for s, v in k["steps"].items() if s != "home")
                tried = sum(v[1] for s, v in k["steps"].items() if s != "home")
                cells.append(f"{ok}/{tried}")
            else:
                for s in names:
                    v = k["steps"].get(s, [0, 0])
                    cells.append(f"{v[0]}/{v[1]}" if v[1] else "-")
            cells += [f"{k['disturbed']}/{k['n']}", f"{k['others_max_mm']:.0f}",
                      "; ".join(f"{why} x{c}" for why, c in k["reasons"].most_common(4))]
            lines.append("| " + " | ".join(cells) + " |" if markdown else "  ".join(f"{c:<14s}" if i < len(cells) - 1 else c for i, c in enumerate(cells)))
    return "\n".join(lines)


def main(args) -> int:
    rows = []
    t0 = time.time()
    plan = []
    earlier = None
    if args.kinds_from:
        earlier = {(r["task"].replace("_front", ""), r["kind"]) for r in json.loads(Path(args.kinds_from).read_text())["rows"]}
    for task in args.tasks:
        kinds = kinds_for(task)
        if earlier is not None and task not in ("place_into", "obstacle"):
            kinds = [k for k in kinds if (task, k) in earlier]
        if args.kinds and args.kinds != ["all"]:
            kinds = [k for k in kinds if k in args.kinds]
        elif task == "look" and not args.kinds and earlier is None:
            kinds = [k for k in kinds if k in LOOK_KINDS]
        for kind in kinds:
            plan.append((task, kind, False))
            if task == "press":
                plan.append((task, kind, True))        # also with the controls facing the front of the table
    for task, kind, front in plan:
        got = [run_trial(task, kind, args.seed, i, args.robot, front, args.grasp, args.take) for i in range(args.n)]
        rows += got
        if not args.quiet:
            ok = sum(r["success"] for r in got)
            why = Counter(f"{s}: {v}" for r in got for s, v in r["steps"].items() if v != "ok")
            print(f"{got[0]['task']:16s} {kind:18s} {ok:2d}/{len(got)}  others {max(r.get('others_mm', 0.0) for r in got):6.1f} mm  "
                  + "; ".join(f"{k} x{c}" for k, c in why.most_common(3)), flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.seed, "n": args.n, "robot": args.robot, "grasp": args.grasp, "wall_s": round(time.time() - t0, 1), "rows": rows}))
    print(tables(rows, markdown=args.md))
    print(f"\n{len(rows)} trials in {time.time() - t0:.0f} s; rows in {out}")
    return 0


# ---- reports over result files (the tables of docs/MOTION.md) -------------------------------------------------------------
def report(paths: list[str], labels: list[str] | None = None) -> str:
    """Markdown: one summary table per result file, then per task one table of kinds with the files side by side."""
    labels = labels or [Path(p).stem for p in paths]
    runs = [summarise(json.loads(Path(p).read_text())["rows"]) for p in paths]
    out = []
    for label, run in zip(labels, runs):
        out += ["", f"**{label}**", "", "| task | kinds | trials | succeed | a bystander moved > 10 mm | knocked over | largest (mm) | most frequent reasons |",
                "|---|---|---|---|---|---|---|---|"]
        for task in sorted(run):
            kinds = run[task]
            n = sum(k["n"] for k in kinds.values())
            ok = sum(k["success"] for k in kinds.values())
            why = Counter()
            for k in kinds.values():
                why.update(k["reasons"])
            out.append(f"| {task} | {len(kinds)} | {n} | {ok} ({100.0 * ok / max(n, 1):.0f} %) | {sum(k['disturbed'] for k in kinds.values())} | "
                       f"{sum(k['knocked'] for k in kinds.values())} | {max((k['others_max_mm'] for k in kinds.values()), default=0.0):.0f} | "
                       + "; ".join(f"{r} x{c}" for r, c in why.most_common(5)) + " |")
    tasks = sorted({t for run in runs for t in run})
    for task in tasks:
        kinds = sorted({k for run in runs for k in run.get(task, {})})
        out += ["", f"**{task}** (successes / trials)", "", "| kind | " + " | ".join(labels) + " | why not (last column's run) |", "|---|" + "---|" * (len(labels) + 1)]
        for kind in kinds:
            cells = []
            for run in runs:
                k = run.get(task, {}).get(kind)
                cells.append("-" if k is None else f"{k['success']}/{k['n']}" + (f" (+{k['no_scene']} no scene)" if k["no_scene"] else ""))
            last = runs[-1].get(task, {}).get(kind)
            why = "; ".join(f"{r} x{c}" for r, c in last["reasons"].most_common(3)) if last else ""
            out.append(f"| {kind} | " + " | ".join(cells) + f" | {why} |")
    return "\n".join(out)
