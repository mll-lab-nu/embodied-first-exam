"""Actions: what the agent-facing tools do with the arm, given places in the scene.

Each action is a generator of control rows like the skills it is built from, and returns a `Status`. The caller (the
episode) has already turned the agent's pixel into an object or a point; nothing here reads images. Grasps come from
the object's `meta["grasps"]` (asset contract) or, for primitive props, from its grip sites; with the grasp assist on
(`world.assist`) a picked object is welded to the hand until the hand opens.

Every action leaves the things it was not asked to move where they are: the hand and what it holds travel above
whatever stands under their way (`_transfer`), every free move is tested for collisions before it starts, and an
action that finds no free way returns `path_blocked` without having moved. See docs/MOTION.md.
"""
from __future__ import annotations

import math

import numpy as np

from . import props as _props
from . import skills as S
from . import tf
from .ik import interpolate_poses
from .skills import Status
from .world import CONTROL_DT, World

DOWN = np.array([0.0, 0.0, -1.0])
UP = np.array([0.0, 0.0, 1.0])
IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])
CARRY_CLEARANCE = 0.14      # m: how high the underside of a carried object is held above the point `carry` is given
CLEAR_MARGIN = 0.04         # m: how far above the things under its way the hand and its load pass
HAND_RADIUS = 0.08          # m: the open gripper around the tool axis
SAFE_HEIGHT = 0.34          # m: the hand rises to this height before a free move to a new view
MIN_TOP_GRASP_HEIGHT = 0.004   # m: a grasp from above is not taken lower than this above the object's underside (a flat card)
LOOK_DISTANCE = 0.19        # m: the wrist camera looks at the point this far in front of the pinch point
FINGER_DEPTH = 0.030        # m: a grasp from above is at most this far below the top of the object
PAYLOAD = 3.0               # kg: heavier things are not picked up (the default robot's; a world's own is `world.spec.payload`)
PRESS_TILTS = (0.0, 30.0, 50.0, 65.0)   # degrees from square to the surface at which a control may be pressed
FINGERTIP_BELOW_PINCH = 0.015   # m: how far the fingertips of nearly closed fingers reach below the pinch point in a grasp from above
LOOK_SIDES = {              # where the wrist camera looks from: unit vectors from the point towards the camera
    "above": (0.0, 0.0, 1.0),
    "front": (0.0, -0.80, 0.60),
    "back": (0.0, 0.80, 0.60),
    "left": (-0.80, 0.0, 0.60),
    "right": (0.80, 0.0, 0.60),
}


# ---- grasps ----------------------------------------------------------------------------------------------------------
def grasps_of(world: World, obj: str, prefer: str | None = None) -> list[dict]:
    """Candidate grasps of an object in the bench frame, in the order they are tried:
    [{"type", "pose", "width", "name", "offset", "approach_dir"}].

    Order: with `prefer` (`top` or `side`) that type first. Otherwise an open vessel is taken so that it can be poured
    from and stays upright: by the point of its rim farthest from the robot (the hand stays above it, and it is
    tipped towards the robot), else by its side (a level hand has its wrist beside the vessel, which needs room where
    it is put down), else by its handle, else from above on its axis (from which it cannot be tipped); anything
    else from above first.
    A grasp from above is never deeper than the fingers are long, and never so low that the fingertips would be in
    what the object stands on. A grasp by a handle is approached from outside the handle.
    """
    meta = world.objects[obj]["meta"]
    here = world.locate(obj)
    out = []
    for g in meta.get("grasps", []):
        pose = tf.compose(here, (np.asarray(g["pos"], dtype=np.float64), tf.unit(g.get("quat", [1.0, 0.0, 0.0, 0.0]))))
        out.append({"type": g["type"], "pose": pose, "width": float(g["width"]), "name": g.get("name", ""),
                    "local": np.asarray(g["pos"], dtype=np.float64), **({"clearance": float(g["clearance"])} if "clearance" in g else {})})
    if not out:
        for site, g in sorted(meta.get("grips", {}).items()):
            if "pos" in g:
                pose = tf.compose(here, (np.asarray(g["pos"], dtype=np.float64), tf.unit(g.get("quat", [1.0, 0.0, 0.0, 0.0]))))
            else:
                pose = world.locate(f"{obj}/{site}")
            out.append({"type": g.get("type", "top"), "pose": pose, "width": float(g.get("width", 0.03)), "name": site,
                        "local": tf.compose(tf.inverse(here), pose)[0]})
    top = meta.get("size", [0.0, 0.0, 0.0])[2] if "size" in meta else None
    floor = float(world.box(obj)[0][2])
    upright = abs(float(tf.rotate(here[1], UP)[2])) > 0.9
    standing = bool(top) and upright and float(tf.rotate(here[1], UP)[2]) > 0.0
    size = meta.get("size")
    round_body = size is None or abs(float(size[0]) - float(size[1])) < 0.012   # as wide as deep: any side will do
    base = np.asarray(world.scene["robot"]["pos"][:2], dtype=np.float64)
    extra: list = []
    for g in out:
        local = g.pop("local")
        g["offset"] = float(math.hypot(local[0], local[1]))          # how far from the object's own axis the hand holds it
        g["approach_dir"] = None
        if g["type"] == "top":
            # A grasp across the object, not along its own axis (the handle of a knife that stands in a block, taken
            # from its flat side once the knife lies on the table): the depth rules, which are about the object's own
            # top, do not apply to it; when it is reached from straight above, the fingertips stay clear of the support.
            axis = tf.rotate(g["pose"][1], UP)
            across = abs(float(tf.rotate(tf.quat_conj(here[1]), axis)[2])) < 0.9
            top_here = top
            if standing:
                # The top that the fingers come down to, where they come down: the solid shapes within reach of the
                # pads around the grasp (a bucket's rim, not the bail above its middle; not a candle's flame or the
                # plant in a pot, which are drawn and not solid). With the weld of 0.4.x a grasp placed by the
                # object's overall top "held" a thing the fingers closed above.
                top_here = min(float(top), float(world.solid_box(obj, g["pose"][0], 0.02)[1][2]) - float(here[0][2]))
            if not across and top_here and local[2] < top_here - FINGER_DEPTH:      # no deeper than the fingers are long
                local = np.array([local[0], local[1], top_here - 0.025])
                g["pose"] = (tf.compose(here, (local, IDENTITY))[0], g["pose"][1])
            low = floor + S.fingertip_reach(world, g["width"]) + 0.0015
            if (abs(float(axis[2])) > 0.9 if across else upright) and float(g["pose"][0][2]) < low:   # the fingertips stay clear of what it stands on
                g["pose"] = (np.array([g["pose"][0][0], g["pose"][0][1], low]), g["pose"][1])
            elif not across and not upright and local[2] < MIN_TOP_GRASP_HEIGHT:   # lying some other way: at least clear of its underside
                local = np.array([local[0], local[1], MIN_TOP_GRASP_HEIGHT])
                g["pose"] = (tf.compose(here, (local, IDENTITY))[0], g["pose"][1])
        elif g["offset"] > 0.015:                                    # a handle: come from outside it, towards the object
            g["approach_dir"] = (-tf.rotate(g["pose"][1], [1.0, 0.0, 0.0])).tolist()
        elif not round_body:                                         # the fingers close along the grasp's own y axis only
            x = tf.rotate(g["pose"][1], [1.0, 0.0, 0.0])
            away = g["pose"][0][:2] - base
            g["approach_dir"] = [x.tolist(), (-x).tolist()] if float(x[:2] @ away) >= 0.0 else [(-x).tolist(), x.tolist()]
        elif abs(float(g["pose"][0][0])) > 0.08 and getattr(world, "room", None) is None:      # (a rule about the bench's two sides)
            # A round body can be taken from any side. A level hand has its wrist a hand's length behind it: from the
            # outer side of the table (the hand pointing towards the middle) the wrist is over the edge, where nothing
            # stands, and what is poured goes towards the middle. That is tried first; the same grasp follows with the
            # choice left to the skill (from the robot's side or across, whichever is nearest).
            first = dict(g)
            first["approach_dir"] = [-1.0 if float(g["pose"][0][0]) > 0.0 else 1.0, 0.0, 0.0]
            first["to_robot"] = float(np.linalg.norm(g["pose"][0][:2] - base))
            extra.append((out.index(g), first))
        g["to_robot"] = float(np.linalg.norm(g["pose"][0][:2] - base))
    for k, (i, first) in enumerate(extra):              # each just before the grasp it is a variant of
        out.insert(i + k, first)
    if world.spec.extra.get("level_handles"):
        # A hand that cannot point down at the height of a table (`RobotSpec.extra["level_handles"]`) takes a handle
        # that sticks out sideways as a person takes a pan: level, from the handle's outer end, the fingers either
        # side of it, 2 cm further out than the grasp from above. Tried after the asset's own grasps.
        for g in [g for g in out if g["type"] == "top" and g["name"] == "handle" and g["offset"] > 0.015]:
            radial = g["pose"][0] - here[0]
            radial = tf.unit(radial - float(radial @ tf.rotate(here[1], UP)) * tf.rotate(here[1], UP))
            if upright and abs(float(radial[2])) < 0.2:
                out.append({**g, "type": "side", "name": "handle_level", "pose": (g["pose"][0] + 0.02 * radial, here[1]),
                            "approach_dir": (-radial).tolist()})
    vessel = meta.get("vessel")
    if prefer in ("top", "side"):
        def rank(g):
            return (0 if g["type"] == prefer else 1, 0.0)
    elif vessel and not vessel.get("closed", False) and any(g["type"] == "side" or g["offset"] > 0.015 for g in out):
        def rank(g):
            if g["type"] == "side":
                return (1, 0.0) if g["offset"] <= 0.015 else (2, g["to_robot"])
            return (0, -g["to_robot"]) if g["offset"] > 0.015 else (3, 0.0)
    else:
        def rank(g):
            return (0 if g["type"] == "top" else 1, 0.0)
    out.sort(key=rank)                                               # stable: the asset's own order within a rank
    if world.spec.extra.get("tipped_grasps"):
        # after every grasp the asset gives, in the order of the grasps they are variants of
        tipped = _tipped(world, here, floor, base, size, round_body, [g for g in out if g["type"] == "top"])
        if prefer == "side":
            # asked to take it by the side: of a thing that has a grasp from above only, the hand tipped as far over
            # as it can be comes first, before the grasp from straight above (a hand that points down cannot put
            # what it holds on anything much higher than where it took it)
            tipped.sort(key=lambda g: -g["tip_deg"])
            return [g for g in out if g["type"] == "side"] + tipped + [g for g in out if g["type"] != "side"]
        out += tipped
    return out


TIP_PAD_HALF_WIDTH = 0.011  # m: from the middle of a finger pad to its edge, across the finger


def _tipped(world: World, here, floor: float, base, size, round_body: bool, tops: list) -> list[dict]:
    """Grasps from above for a hand that cannot point straight down where the thing is (`RobotSpec.extra
    ["tipped_grasps"]`: the angles from the vertical it may be tipped by, in the order they are tried; 90 is a level
    hand). Each is one of the asset's grasps from above with the same pinch point and the hand leaning:

    - about the closing direction, which stays level: the fingers come down on the thing as before, the palm is
      behind and above them. Where the closing direction is free (a cube, an apple, a can from above: as wide as
      deep and held on its axis across its whole width) the hand leans back towards the robot; where the asset
      fixes it (the handle of a knife, the rim of a tray, the bar of a basket) the hand leans along the thing it
      closes on, either way, the way that keeps the wrist on the robot's side first;
    - a grasp called `handle` (a bar the fingers go round) also about the bar itself: the hand comes at it from the
      side, up to level, one finger over the bar and one under it.

    The pinch point is raised as far as the tipped fingertips need to stay clear of what the thing stands on. Which
    of them is taken is decided by reach (`skills.pick` solves for each and takes the first whose way in and whose
    lift it finds), not by what the thing is."""
    out = []
    for g in tops:
        up_axis = tf.rotate(g["pose"][1], UP)
        if float(up_axis[2]) < 0.9:                      # only grasps that come from straight above
            continue
        y = tf.rotate(g["pose"][1], [0.0, 1.0, 0.0])
        y = tf.unit(np.array([y[0], y[1], 0.0]))
        away = np.array([g["pose"][0][0] - base[0], g["pose"][0][1] - base[1], 0.0])
        away = tf.unit(away) if float(np.linalg.norm(away)) > 1e-6 else np.array([0.0, 1.0, 0.0])
        free = bool(round_body and g["offset"] <= 0.015 and size is not None and g["width"] >= 0.8 * min(float(size[0]), float(size[1])))
        if free:
            y = np.cross(UP, away)
        along = np.cross(y, UP)                          # level, square to the closing direction
        leans = [(along if float(along @ away) >= 0.0 else -along, y, "a")]
        if not free:
            leans.append((-leans[0][0], y, "a"))
            if g["name"] == "handle":
                leans += [(y if float(y @ away) >= 0.0 else -y, None, "b"), (-y if float(y @ away) >= 0.0 else y, None, "b")]
        reach = S.fingertip_reach(world, g["width"])
        for deg in world.spec.extra["tipped_grasps"]:
            t = math.radians(float(deg))
            for lean, closing, how in leans:
                z_tool = -math.cos(t) * UP + math.sin(t) * lean
                if how == "a":                           # the pads tip about the closing direction: an edge of each leads
                    drop = reach * math.cos(t) + TIP_PAD_HALF_WIDTH * math.sin(t)
                    y_tool = closing
                else:                                    # the fingers tip in their own plane: the lower one leads
                    y_tool = np.cross(z_tool, np.cross(lean, UP))
                    drop = reach * math.cos(t) + (g["width"] / 2.0 + 0.012) * math.sin(t)
                pos = g["pose"][0].copy()
                pos[2] = max(float(pos[2]), floor + drop + 0.0015)
                out.append({"type": "top", "pose": (pos, tf.quat_from_axes(y=y_tool, z=-z_tool)), "width": g["width"],
                            "name": f"{g['name']}_tipped", "offset": g["offset"], "approach_dir": None, "to_robot": g.get("to_robot", 0.0),
                            "tip_deg": float(deg)})
    return out


GENTLE_SQUEEZE = 0.008      # rad: how far past first contact the fingers close in a gentle grip (about 10 N on each pad, not 40)


def pick(world: World, obj: str, *, lift: float = 0.12, prefer: str | None = None, squeeze: float | None = None):
    """Take an object and lift it. Tries the object's grasps in turn (see `grasps_of`) and takes the first that can
    be reached. `squeeze` limits the grip force (see `skills.close_gripper`; `GENTLE_SQUEEZE` is what the tool's
    `grip="gentle"` uses). Reasons: `already_holding`, `not_graspable`, `too_heavy`, and those of `skills.pick`."""
    if S.holding(world):
        return Status(False, "already_holding", {"held": world.held})
    o = world.objects.get(obj)
    if o is None or o["fixed"]:
        return Status(False, "not_graspable", {"object": obj})
    if float(o["meta"].get("mass", 0.0)) > world.spec.payload:
        return Status(False, "too_heavy", {"object": obj, "mass": float(o["meta"]["mass"]), "payload": world.spec.payload})
    if prefer == "edge" or (prefer is None and not world.spec.arms and not world.spec.base and is_flat(world, obj)):
        # too flat to be pinched where it lies (one arm on the bench: the back edge of the table is beside it)
        last = yield from pick_edge(world, obj, lift=lift, squeeze=squeeze)
        if not last.ok and world.held is not None:
            yield from S._grip(world, 0.0)
        return last
    cands = grasps_of(world, obj, prefer)
    if not cands:
        return Status(False, "not_graspable", {"object": obj})
    if S.max_opening(world) < _props.MAX_GRIP_WIDTH:          # a hand that opens less far than the grasps were made for
        cands = [g for g in cands if g["width"] <= S.max_opening(world) - 0.004]
        if not cands:
            return Status(False, "too_wide", {"object": obj, "opens_to": S.max_opening(world)})
    last = Status(False, "not_graspable", {})
    rounds = [(cands, None)]
    if world.spec.extra.get("tipped_grasps"):
        # An arm whose hand cannot point down everywhere, working from wherever its base stands: every grasp is
        # also solved for outright, and refused before anything moves if the open fingers would be in the thing
        # itself or if it cannot be lifted (`skills.pick`, a grasp marked `free`). First round: the asset's own
        # grasps that can be lifted all the way, then the tipped ones that can and that also leave the arm room to
        # carry what it took to either side (`skills.ROOM`). Second round: those of them that could at least be
        # lifted a little.
        rounds = [(cands, "full"), ([], True)]
    moved = False
    for group, free in rounds:
        for g in group:
            spec = {"type": g["type"], "pose": g["pose"], "width": g["width"], **({"clearance": g["clearance"]} if "clearance" in g else {})}
            if g["approach_dir"] is not None:
                spec["approach_dir"] = g["approach_dir"]
            if free:
                spec["free"] = "roomy" if (free == "full" and "tip_deg" in g) else free
            last = yield from S.pick(world, obj, spec, lift=lift, squeeze=squeeze)
            if last.ok:
                last.info["grasp_name"] = g["name"]
                if "tip_deg" in g:
                    last.info["tip_deg"] = g["tip_deg"]
                return last
            if not last.reason.endswith(":pregrasp"):   # the arm moved: do not try another grasp from an unknown state
                moved = True
                break
            if free == "full" and last.info.get("cramped"):
                rounds[1][0].append(g)
        if moved:
            break
    if world.held is not None:                          # taken but not lifted: let go rather than keep pulling
        yield from S._grip(world, 0.0)
    return last


# ---- things too flat to be pinched where they lie ------------------------------------------------------------------------
# A parallel gripper from above closes its pads across a thing; the 2F-85's pads end 5 to 18 mm above its fingertips'
# line (depending on the opening), so a thing that lies flat and is lower than that (a coin-cell blister card, a sheet)
# is below them, and the rim of a saucer is a flange that slopes away from closing pads. Such a thing is taken as a
# person takes a coin or a plate from a table: slid with the fingertips to the table's edge until part of it sticks out,
# then pinched there, one finger above it and one below. Only the robot's own senses decide (wrist force for the
# press); where the thing is comes from `locate` / `solid_box`, as for every grasp.
EDGE_FLAT = 0.008           # m: lower than this (its solid part) a thing lying flat is taken at an edge (a 10 mm card is not)
EDGE_NARROW = 0.030         # m: a grasp from above narrower than this takes a flat thing where it lies
EDGE_OVERHANG = 0.050       # m: how far it is slid out over the back edge of the table
EDGE_PINCH_OUT = 0.025      # m: where it is pinched: this far beyond the edge (the fingertips stay clear of the edge)
EDGE_XS = (0.32, 0.26, 0.40, 0.21, 0.17)   # m: places along the back edge, either side of the robot, in order of preference
SLIDE_PRESS = 6.0           # N: how hard the closed fingertips press on the thing while they slide it
SLIDE_SPEED = 0.05          # m/s
SLIDE_MAX_FORCE = 40.0      # N: a slide that meets more than this has run into something and stops
EDGE_LIFT = 0.18            # m: a thing taken at the edge is lifted this far, so that it can hang below the hand
SLIDE_GAIN = 2.0e-5         # m per N per control period: how the height follows the press


def is_flat(world: World, obj: str) -> bool:
    """Whether a thing is taken at an edge: lying flat and lower than `EDGE_FLAT`, or the asset says so (a grasp of
    type `edge`: the rim of a saucer or a plate)."""
    o = world.objects[obj]
    grasps = o["meta"].get("grasps", [])
    if any(g.get("type") == "edge" for g in grasps):
        return True
    lo, hi = world.solid_box(obj)
    if float(hi[2] - lo[2]) >= EDGE_FLAT:
        return False
    # a narrow grasp from above closes the fingers far, and nearly closed pads reach 18 mm below the pinch point: a
    # spoon's handle, 6 mm high and 9 mm wide, is taken where it lies. Wide open they end 5 to 8 mm below it.
    return not any(g.get("type") == "top" and float(g.get("width", 1.0)) < EDGE_NARROW for g in grasps)


def _edge_y(world: World) -> float:
    return float(world.table_half[1])


def _slide_goal(world: World, obj: str, xs=EDGE_XS):
    """Where to slide a flat thing (its origin, bench frame) so that `EDGE_OVERHANG` of it sticks out over the back
    edge, beside the robot; and whether the strip it slides along is free of other things. Of the places along the
    edge (`EDGE_XS`, on the thing's own side of the robot first) the first whose way is free. None when none is."""
    here = world.locate(obj)[0]
    lo, hi = world.solid_box(obj)
    ye = _edge_y(world)
    half = (hi[:2] - lo[:2]) / 2.0
    centre = (hi[:2] + lo[:2]) / 2.0
    off = here[:2] - centre                                  # the origin relative to the middle of the solid part
    side = 1.0 if float(here[0]) >= 0.0 else -1.0
    for s in (side, -side):
        for x in xs:
            goal_c = np.array([s * x, ye - half[1] + EDGE_OVERHANG])
            ok = True
            for name in world.objects:
                if name == obj or world.objects[name].get("mocap"):
                    continue
                blo, bhi = world.box(name)
                if float(bhi[2]) < 0.002:                    # flat on the table: a puddle, a rug
                    continue
                # the swept rectangle of the thing from its middle to the goal, against the other thing's box
                a, b = centre, goal_c
                for t in np.linspace(0.0, 1.0, 21):
                    c = a + (b - a) * t
                    if (c[0] + half[0] + 0.01 > blo[0] and c[0] - half[0] - 0.01 < bhi[0]
                            and c[1] + half[1] + 0.01 > blo[1] and c[1] - half[1] - 0.01 < bhi[1]):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return goal_c + off
    return None


def slide(world: World, obj: str, goal_xy, *, press: float = SLIDE_PRESS, speed: float = SLIDE_SPEED):
    """Slide a thing that lies on the table to `goal_xy` (where its origin is to end) with the closed fingertips pressed
    on its top: the hand comes down from above onto the middle of the thing until the wrist feels `press` newtons,
    moves level to the goal (the press is held by the arm's servos), and rises. Reasons: `ik_...`, `path_blocked`,
    `not_reached`, `no_touch` (the fingertips met nothing), `obstructed` (the slide met more than `SLIDE_MAX_FORCE`)."""
    if S.holding(world):
        return Status(False, "already_holding", {})
    lo, hi = world.solid_box(obj)
    centre = (lo + hi) / 2.0
    here = world.locate(obj)[0]
    down = world.ik.fk(world.ready)[1]                     # the tool straight down, as in the ready posture
    reach = S.fingertip_reach(world, 0.0)
    above = np.array([centre[0], centre[1], float(hi[2]) + reach + 0.05])
    yield from S._grip(world, S.GRIPPER_MAX)               # the fingers closed: their tips are one blunt end
    g = float(world.target[-1])
    r = world.ik.solve(above, down, world.ready, max_jump=10.0)
    if not r.ok:
        return Status(False, "ik_unreachable:slide", {})
    st = yield from S._go(world, r.q, g, (), 1.0)
    if not st.ok:
        return Status(False, f"{st.reason}:slide", st.info)
    yield from S.hold(world, 0.1)
    tare = world.wrist_wrench()[0].copy()

    def pressed() -> bool:
        return float(np.linalg.norm(world.wrist_wrench()[0] - tare)) > press

    touch = np.array([above[0], above[1], float(hi[2]) + reach - 0.006])
    felt = [False]

    def pressing() -> bool:
        felt[0] = felt[0] or pressed()
        return felt[0]

    st = yield from S._move(world, (touch, down), g, linear=True, lin_speed=0.02, guard=pressing)
    if not felt[0]:
        yield from S._move(world, (above, down), g, linear=True, lin_speed=0.10)
        return Status(False, "no_touch", {})
    # The slide is force-controlled in height, as a robot with a wrist force sensor does it: each control period the
    # fingertips go a step along the line, and up or down by what the wrist says about the press (the thing has bumps,
    # cells on a card, a rim; a fixed height would ride over them or dig in).
    start = world.tcp_pose()[0]
    end = np.array([start[0] + float(goal_xy[0] - here[0]), start[1] + float(goal_xy[1] - here[1])])
    length = float(np.linalg.norm(end - start[:2]))
    n = max(int(math.ceil(length / (speed * CONTROL_DT))), 1)
    z, q = float(start[2]), world.joint_pos
    floor_z = float(start[2]) - 0.012                      # never more than this below where it first touched
    force, reason = [], "ok"
    for k in range(1, n + 1):
        f = -world.carried_load()                          # how hard the fingertips press down (N)
        force.append(f)
        if f > SLIDE_MAX_FORCE:
            reason = "obstructed"
            break
        z = min(max(z - SLIDE_GAIN * (press - f), floor_z), float(start[2]) + 0.01)
        xy = start[:2] + (end - start[:2]) * (k / n)
        r = world.ik.solve(np.array([xy[0], xy[1], z]), down, q, max_jump=0.3)
        if not r.ok:
            reason = "ik_" + r.reason
            break
        q = r.q
        yield S._row(q, g)
    yield from S.hold(world, 0.2)
    tail = force[len(force) // 4:] or [0.0]
    if reason == "ok" and float(np.median(tail)) < 0.5 * press:
        reason = "no_press"                                # the fingertips lost the thing on the way
    tcp = world.tcp_pose()[0]
    yield from S._move(world, (tcp + np.array([0.0, 0.0, 0.06]), down), g, linear=True, lin_speed=0.10)
    return Status(reason == "ok", reason, {"slid_m": float(np.linalg.norm(tcp[:2] - start[:2])),
                                           "press_n": float(np.median(tail))})


def pick_edge(world: World, obj: str, *, lift: float = 0.12, squeeze: float | None = None):
    """Take a flat thing (`is_flat`) at the back edge of the table: slide it out over the edge beside the robot unless
    enough of it sticks out already, then pinch what sticks out with the hand level and pointing back at the table,
    one finger above it and one below, and lift. Reasons: `path_blocked:slide` (no free way to the edge), those of
    `slide` and of `skills.pick`."""
    ye = _edge_y(world)
    lo, hi = world.solid_box(obj)
    if float(hi[1]) < ye + EDGE_OVERHANG - 0.01 or abs(float((lo[0] + hi[0]) / 2.0)) < 0.18:
        goal = _slide_goal(world, obj)
        if goal is None:
            return Status(False, "path_blocked:slide", {})
        st = yield from slide(world, obj, goal)
        if not st.ok:
            return Status(False, f"{st.reason}:slide" if ":" not in st.reason else st.reason, st.info)
        yield from S.hold(world, 0.2)
        lo, hi = world.solid_box(obj)
        if float(hi[1]) < ye + EDGE_PINCH_OUT + 0.008:
            return Status(False, "not_over_edge", {"out_m": float(hi[1] - ye)})
    out = float(hi[1]) - ye
    y = ye + min(EDGE_PINCH_OUT, out - 0.008)
    x = float(np.clip((lo[0] + hi[0]) / 2.0, lo[0] + 0.012, hi[0] - 0.012))
    near_lo, near_hi = world.solid_box(obj, np.array([x, y, 0.0]), 0.004)
    z = float(near_lo[2] + near_hi[2]) / 2.0
    thick = float(near_hi[2] - near_lo[2])
    pose = (np.array([x, y, z]), tf.quat_from_axes(y=(0.0, 1.0, 0.0), z=(1.0, 0.0, 0.0)))
    spec = {"type": "side", "pose": pose, "width": max(thick, 0.002), "approach_dir": [0.0, -1.0, 0.0]}
    st = yield from S.pick(world, obj, spec, lift=max(lift, EDGE_LIFT), squeeze=squeeze)
    if not st.ok:
        return st
    st.info["grasp_name"] = "edge"
    # A level hand out over the back edge cannot carry far (the joints of a level hand reach their limits before the
    # front of the table): the hand turns to point down, about the line along the table's edge, and the thing hangs
    # from its pinched edge below the fingers, as a sheet held by a corner does.
    tcp = world.tcp_pose()
    x_axis = tf.rotate(tcp[1], [1.0, 0.0, 0.0])
    down = (tcp[0], tf.unit(tf.quat_mul(tf.quat_axis_angle(tf.unit(np.array([x_axis[0], x_axis[1], 0.0])), 0.0), tcp[1])))
    for sign in (1.0, -1.0):
        turned = tf.unit(tf.quat_mul(tf.quat_axis_angle(np.array([1.0, 0.0, 0.0]), sign * math.pi / 2.0), tcp[1]))
        if float(tf.rotate(turned, [0.0, 0.0, 1.0])[2]) < -0.9:
            down = (tcp[0], turned)
            break
    turn = yield from S._move(world, down, float(world.target[-1]), linear=True, lin_speed=0.10, ang_speed=1.0)
    st.info["hanging"] = bool(turn.ok)
    if not S.holding(world):
        return Status(False, "lost_in_turn", st.info)
    if turn.ok:
        world.hanging = tuple(getattr(world, "hanging", ())) + (obj,)
    return st


def _lay_down(world: World, obj: str, speed: float = 1.0):
    """Turn the hand about the lower edge of the sheet it holds hanging (`pick_edge`), which stands on a surface,
    until the sheet is `LAY_DOWN_LEFT` degrees from flat: either way round, whichever the arm can follow."""
    tcp = world.tcp_pose()
    lo, _ = world.box(obj)
    pivot = np.array([tcp[0][0], tcp[0][1], float(lo[2])])
    axis = tf.unit(np.array([*tf.rotate(tcp[1], [1.0, 0.0, 0.0])[:2], 0.0]))     # along the sheet's lower edge
    q0 = world.joint_pos
    total = math.radians(90.0 - LAY_DOWN_LEFT)
    # the way round that brings the face that was up when it lay on the table up again
    face = tf.rotate(world.locate(obj)[1], [0.0, 0.0, 1.0])
    signs = sorted((1.0, -1.0), key=lambda sg: -float(tf.rotate(tf.quat_axis_angle(axis, sg * total), face)[2]))
    for sign in signs:
        n = 30
        poses = []
        for k in range(1, n + 1):
            rot = tf.quat_axis_angle(axis, sign * total * k / n)
            poses.append((pivot + tf.rotate(rot, tcp[0] - pivot), tf.unit(tf.quat_mul(rot, tcp[1]))))
        if float(poses[-1][0][2]) < 0.01:
            continue
        path, res = world.ik.solve_path(poses, q0)
        if not res.ok:
            continue
        length = float(np.linalg.norm(tcp[0] - pivot)) * total
        return (yield from S._follow(world, np.vstack([q0[None, :], path]), float(world.target[-1]), length, lin_speed=0.05, speed=speed))
    return Status(False, "ik_unreachable:lay_down", {})


LAY_DOWN_LEFT = 25.0        # degrees from flat at which a sheet laid down from its edge is let go of


# ---- where things are and how to pass over them ------------------------------------------------------------------------
def _load(world: World) -> tuple[np.ndarray, float, float, tuple]:
    """What the hand carries, relative to the pinch point: (vector from the lowest point of the held object to the
    pinch point, how far the lowest point of hand and load is below the pinch point, the horizontal reach of hand
    and load around it, the load in the form the collision tests take)."""
    tcp = world.tcp_pose()[0]
    names = S.held_objects(world)
    below = S.TIP_BEYOND_TCP
    reach = HAND_RADIUS
    off = np.zeros(3)
    for n in names:
        lo, hi = world.box(n)
        below = max(below, float(tcp[2] - lo[2]))
        reach = max(reach, float(max(np.max(np.abs(lo[:2] - tcp[:2])), np.max(np.abs(hi[:2] - tcp[:2])))))
    main = world.held if world.held is not None else (names[0] if names else None)    # without the assist: what both pads touch
    if main is not None:
        lo, _ = world.box(main)
        origin = world.locate(main)[0]
        off = tcp - np.array([origin[0], origin[1], lo[2]])
    return off, below, reach, S._attached(world, names)


def _tops(world: World, a, b, radius: float, ignore=()) -> float:
    """Height of the tallest thing standing within `radius` of the straight line from a to b (0: only the table)."""
    a, b = np.asarray(a, dtype=np.float64)[:2], np.asarray(b, dtype=np.float64)[:2]
    n = max(int(math.ceil(float(np.linalg.norm(b - a)) / 0.01)), 1)
    line = a[None, :] + (b - a)[None, :] * np.linspace(0.0, 1.0, n + 1)[:, None]
    top = 0.0
    for name in world.objects:
        if name in ignore:
            continue
        lo, hi = world.box(name)
        if float(hi[2]) <= top:
            continue
        gap = np.hypot(np.maximum(np.maximum(lo[0] - line[:, 0], line[:, 0] - hi[0]), 0.0),
                       np.maximum(np.maximum(lo[1] - line[:, 1], line[:, 1] - hi[1]), 0.0))
        if float(gap.min()) <= radius:
            top = float(hi[2])
    return top


def _is_level(world: World) -> bool:
    return abs(float(tf.rotate(world.tcp_pose()[1], UP)[2])) < 0.5


def _plan_leg(world: World, q0, pos, level: bool):
    """Joint path (start included) that takes the pinch point from where it is at `q0` straight to `pos`. A tool held
    level (a vessel taken by its side) is in a wrist-singular posture in which a straight tool line often has no
    continuous solution; there the move is made with the shoulder and elbow only (`IK.carry_path`), which turns the
    tool about the vertical but keeps it level. Otherwise the tool keeps its orientation, with the level carry as
    the fallback. Returns (path, "ok") or (None, why)."""
    pos = np.asarray(pos, dtype=np.float64)
    q0 = np.asarray(q0, dtype=np.float64)
    why = "ik_unreachable"
    for how in (("carry", "line") if level else ("line", "carry")):
        if how == "line":
            start = world.ik.fk(q0)
            n = max(int(math.ceil(float(np.linalg.norm(pos - start[0])) / 0.004)), 1)
            path, res = world.ik.solve_path(interpolate_poses(start, (pos, start[1]), n), q0)
            path = np.vstack([q0[None, :], path])
        else:
            path, res = world.ik.carry_path([pos], q0)
        if res.ok:
            return path, "ok"
        why = "ik_" + res.reason
    return None, why


def _follow_leg(world: World, path, length: float, g: float, *, lin_speed: float, speed: float = 1.0, guard=None):
    if path.shape[0] < 2 or length < 1e-4:
        return Status(True, "ok", {})
    return (yield from S._follow(world, path, g, length, lin_speed=lin_speed, speed=speed, guard=guard))


def _plan_transfer(world: World, goal, q_from=None, detour: bool = False):
    """Plan the way of the pinch point to `goal`: up, across and down, the hand and what it holds passing
    `CLEAR_MARGIN` above everything that stands under the way. Each leg is tested for collisions, the load moving
    along with the hand; if the way at that height cannot be reached or is not free, higher and then lower ways are
    tried. With `detour` (`carry` asks for it) a goal above the hand that cannot be reached that way, because the
    hand cannot rise that far where it is, is reached by crossing lower and rising over the goal.
    Returns ([(leg name, joint path, metres), ...], travel height) or (None, (reason, leg, info)). Nothing moves."""
    goal = np.asarray(goal, dtype=np.float64)
    q0 = world.joint_pos if q_from is None else np.asarray(q_from, dtype=np.float64)
    tcp, quat = world.ik.fk(q0)
    off, below, reach, carried = _load(world)
    held = tuple(n for n, _ in carried)
    level = abs(float(tf.rotate(quat, UP)[2])) < 0.5
    base = max(float(tcp[2]), float(goal[2]))
    if float(np.linalg.norm(goal[:2] - tcp[:2])) < 2e-3:
        heights = [base]                                    # straight up or down: nothing to pass over
    elif not world.avoid:                                   # the careless carry: the underside 14 cm above the table, untested
        heights = [max(base, CARRY_CLEARANCE + float(off[2]))]
    else:
        need = _tops(world, tcp, goal, reach + 0.03, ignore=held) + CLEAR_MARGIN + below
        # higher first (a level hand has its wrist under it, and the arm has to clear things too), then lower
        heights = [max(base, need), max(base, need) + 0.10, max(base, need) + 0.20]
        for lower in (0.06, 0.12, 0.20):
            z = max(base, need - lower)
            if z < min(heights) - 1e-6:
                heights.append(z)
        # An arm that reaches less far the higher its hand is (`RobotSpec.extra["cross_low"]`) may also come down
        # first and cross at the least height that clears what stands under the way, below where the hand is now.
        if world.spec.extra.get("cross_low") and max(need, float(goal[2])) < base - 0.02:
            heights.append(max(need, float(goal[2])))
    why = ("ik_unreachable", "across", {})
    for z in heights:
        legs = []
        q, at, ok = q0, tcp, True
        for name, p in (("rise", np.array([tcp[0], tcp[1], z])), ("across", np.array([goal[0], goal[1], z])), ("descend", goal)):
            dist = float(np.linalg.norm(p - at))
            if dist < 1e-3:
                continue
            path, w = _plan_leg(world, q, p, level)
            if path is None:
                why, ok = (w, name, {}), False
                break
            if not world.avoid:
                hit = None
            elif name == "rise" and float(p[2]) >= float(at[2]):   # straight up: only the load against the arm, and what is above
                hit = S._path_hit(world, list(path[0::2]) + [path[-1]], (), carried, arm_vs_load=True)
            else:
                hit = S._path_hit(world, list(path[0::2]) + [path[-1]], (), carried, arm_vs_load=True, clearance=S.PATH_CLEARANCE)   # every 8 mm
            if hit is not None:
                why, ok = ("path_blocked", name, {"by": hit[1], "who": hit[0]}), False
                break
            legs.append((name, path, dist))
            q, at = path[-1], p
        if ok:
            return legs, z
    # An arm that carries things over its own base (`RobotSpec.extra["slant"]`): to a place lower than the hand that
    # it cannot get above at the height the hand is at (a hand that points down, held over the base, reaches less far
    # up there than down at the floor), the hand goes on one straight line, down and out, tested like a crossing.
    if world.spec.extra.get("slant") and why[0].startswith("ik_") and float(goal[2]) < float(tcp[2]) - 0.02 and float(np.linalg.norm(goal[:2] - tcp[:2])) >= 2e-3:
        path, w = _plan_leg(world, q0, goal, level)
        if path is not None:
            hit = S._path_hit(world, list(path[0::2]) + [path[-1]], (), carried, arm_vs_load=True, clearance=S.PATH_CLEARANCE) if world.avoid else None
            if hit is None:
                return [("across", path, float(np.linalg.norm(goal - tcp)))], float(tcp[2])
            why = ("path_blocked", "across", {"by": hit[1], "who": hit[0]})
    # No straight way from here (the rest posture is close to a singularity: the hand nearly over the base). If the
    # free move to the ready posture is clear, plan from there.
    # Never with something held level: the ready posture points the tool down, which would tip a vessel held by its
    # side and empty it on the way (it did, in two models' trials).
    if q_from is None and why[0].startswith("ik_") and not (carried and level) and float(np.max(np.abs(q0 - world.ready))) > 0.05:
        if S._free_route(world, q0, world.ready, carried)[0] is not None:
            legs, z = _plan_transfer(world, goal, world.ready)
            if legs is not None:
                return [("ready", world.ready.copy(), 0.0)] + legs, z
    # The goal lies above the hand and the hand cannot rise that far where it is (a level hand far from the base
    # cannot). Cross lower, above what stands under the way, and rise over the goal: two transfers, each planned and
    # tested as above, neither of which turns the tool.
    if detour and why[0].startswith("ik_") and float(goal[2]) > float(tcp[2]) + 0.02 and float(np.linalg.norm(goal[:2] - tcp[:2])) >= 2e-3:
        low = max(float(tcp[2]), need if world.avoid else CARRY_CLEARANCE + float(off[2]))
        for z in (low, low + 0.10):
            if z > float(goal[2]) - 0.02:
                break
            first, _ = _plan_transfer(world, np.array([goal[0], goal[1], z]), q0)
            if not first:
                continue
            last, _ = _plan_transfer(world, goal, first[-1][1][-1])
            if last is not None:
                return first + last, z
    return None, why


def _run_legs(world: World, legs, *, speed: float = 1.0, lin_speed: float = 0.15):
    g = float(world.target[-1])
    for name, path, dist in legs:
        if name == "ready":                         # a free move to a posture, not a straight leg
            st = yield from S._go(world, path, g, _load(world)[3], speed)
            if not st.ok:
                return Status(False, f"{st.reason}:ready", st.info)
            continue
        st = yield from _follow_leg(world, path, dist, g, lin_speed=lin_speed, speed=speed)
        if not st.ok:
            return Status(False, f"{st.reason}:{name}", st.info)
    return Status(True, "ok", {})


def _transfer(world: World, goal, *, speed: float = 1.0, lin_speed: float = 0.15, detour: bool = False):
    """Take the pinch point to `goal` by the way `_plan_transfer` finds; if there is none, nothing moves. Reasons:
    `ik_...:<leg>`, `path_blocked:<leg>`, `not_reached:<leg>`."""
    legs, z = _plan_transfer(world, goal, detour=detour)
    if legs is None:
        return Status(False, f"{z[0]}:{z[1]}", z[2])
    st = yield from _run_legs(world, legs, speed=speed, lin_speed=lin_speed)
    if st.ok:
        st.info["travel_height"] = z
    return st


def carry(world: World, point, height: float = CARRY_CLEARANCE, *, speed: float = 1.0):
    """Bring the hand (the lowest point of what it holds) to `height` above a point, keeping the tool's orientation:
    up, across above whatever stands in between, and down; to a height the hand cannot rise to where it is, across
    lower and then up. Reasons: those of `_transfer`."""
    point = np.asarray(point, dtype=np.float64)
    off = _load(world)[0]
    st = yield from _transfer(world, point + np.array([0.0, 0.0, height]) + off, speed=speed, detour=True)
    if not st.ok:
        return st
    return Status(True, "ok", {"tcp": world.tcp_pose()[0].tolist(), **st.info})


def _hand_floor(world: World, path, held) -> int:
    """How many configurations of a descent the robot can follow before the hand or the arm (not what the hand holds)
    would be inside something: the index of the last free one."""
    last = 0
    for k in range(1, path.shape[0]):
        if world.ik.collision(path[k], ignore=held, carried=()) is not None:
            break
        last = k
    return last


def turn(world: World, angle_deg: float, *, rate: float = 60.0):
    """Turn what the hand holds about the vertical through the held object's origin (through the pinch point when the
    hand is empty) by `angle_deg`, anticlockwise seen from above. The tool stays as upright or as level as it was.
    If the wrist cannot make the turn one way round it is tried the other way. Reasons: `ik_...`, `not_reached`."""
    delta = math.radians(float(angle_deg))
    if abs(delta) < 1e-6:
        return Status(True, "ok", {"turned_deg": 0.0})
    tcp = world.tcp_pose()
    pivot = world.locate(world.held)[0] if world.held is not None else tcp[0]
    q0 = world.joint_pos
    st = Status(False, "ik_unreachable", {})
    for d in (delta, delta - math.copysign(2.0 * math.pi, delta)):
        n = max(int(math.ceil(abs(d) / math.radians(2.0))), 1)
        poses = []
        for k in range(1, n + 1):
            rot = tf.quat_axis_angle(UP, d * k / n)
            poses.append((pivot + tf.rotate(rot, tcp[0] - pivot), tf.unit(tf.quat_mul(rot, tcp[1]))))
        path, res = world.ik.solve_path(poses, q0)
        if not res.ok:
            st = Status(False, "ik_" + res.reason, {"solved_deg": math.degrees(d) * path.shape[0] / n})
            continue
        st = yield from S._follow(world, np.vstack([q0[None, :], path]), float(world.target[-1]), abs(d), lin_speed=math.radians(rate))
        st.info["turned_deg"] = math.degrees(d)
        return st
    return st


def place(world: World, point, *, release_above: float = 0.004, max_force: float = 10.0, speed: float = 1.0, turn_deg: float = 0.0):
    """Put the held object down with its lowest point on `point` and let go. With `turn_deg` the object is turned
    about the vertical by that angle above the place before it comes down (see `turn`).

    The object is carried over the point above everything around it, lowered to just above the highest thing near
    the point, and from there slowly, watched by the wrist force: when the object touches something on the way it is
    released where it is. Into something deeper than the hand can follow (a pot, a bin, a slot) the hand goes as far
    as it can without touching and lets go there. Reasons: `not_holding`, those of `_transfer`, `ik_...:descent`.
    """
    if not S.holding(world):
        return Status(False, "not_holding", {})
    obj = world.held
    point = np.asarray(point, dtype=np.float64)
    off, below, reach, carried = _load(world)
    held = tuple(n for n, _ in carried)
    # just above the highest thing the load could meet around the point (the rim of what it is put into, a neighbour)
    near_top = max(_tops(world, point, point, reach + 0.02, ignore=held), float(point[2])) if world.avoid else float(point[2])
    hover = np.array([point[0], point[1], near_top + 0.03]) + off
    st = yield from _transfer(world, hover, speed=speed)
    if not st.ok:
        return st
    # a level carry turns the load about the vertical: aim again. (Twice; an arm that holds things far from the hand,
    # a pot by the end of its handle, comes half as near each time and may be given more: `RobotSpec.extra["place_aims"]`.)
    for _ in range(int(world.spec.extra.get("place_aims", 2))):
        off = _load(world)[0]
        again = np.array([point[0], point[1], near_top + 0.03]) + off
        if float(np.linalg.norm(again - world.tcp_pose()[0])) < 3e-3:
            break
        st = yield from _transfer(world, again, speed=speed)
        if not st.ok:
            return st
    if abs(float(turn_deg)) > 1e-6:
        st = yield from turn(world, turn_deg)
        if not st.ok:
            return Status(False, f"{st.reason}:turn", st.info)
        off, below, reach, carried = _load(world)
    yield from S.hold(world, 0.1)
    tare = world.wrist_wrench()[0]
    peak = [0.0]

    def touched() -> bool:
        df = float(np.linalg.norm(world.wrist_wrench()[0] - tare))
        peak[0] = max(peak[0], df)
        return df > max_force

    tcp = world.tcp_pose()[0]
    g = float(world.target[-1])
    goal = np.array([tcp[0], tcp[1], float(point[2]) + release_above + float(off[2])])
    early, dropped = False, 0.0
    if float(tcp[2] - goal[2]) > 1e-3:
        path, why = _plan_leg(world, world.joint_pos, goal, _is_level(world))
        if path is None:
            return Status(False, f"{why}:descent", {})
        # what the load is put on or into (the thing under the point) it may meet; anything else on its way down it
        # may not: a wide load would come down on a neighbour
        under = world.raycast(point + np.array([0.0, 0.0, 0.01]), DOWN, exclude_robot=True)
        support = tuple(n for n in ((under["object"] if under else None),) if n in world.objects and n not in held)
        last = max(path.shape[0] - 4, 1)            # the last 12 mm are the landing
        hit = S._path_hit(world, list(path[:last:3]), support + ("table",), carried) if world.avoid else None
        if hit is not None and hit[0] != "robot":
            return Status(False, "path_blocked:descent", {"by": hit[1], "who": hit[0]})
        k = _hand_floor(world, path, held)
        if k < path.shape[0] - 1:                   # the hand cannot follow all the way: stop two steps short of touching
            k = max(k - 2, 0)
            dropped = float(world.ik.fk(path[k])[0][2] - goal[2])
            path = path[:k + 1]
        dist = float(tcp[2] - world.ik.fk(path[-1])[0][2])
        st = yield from _follow_leg(world, path, dist, g, lin_speed=0.025, speed=speed, guard=touched)
        early = not st.ok and st.reason == "stopped"
        if not st.ok and st.reason == "not_reached" and float(np.linalg.norm(world.tcp_pose()[0] - world.ik.fk(path[-1])[0])) < 0.04:
            early = True                            # resting on something a little early: let go here
        if not st.ok and not early:
            return Status(False, f"{st.reason}:descent", st.info)
    if obj is not None and obj in getattr(world, "hanging", ()):
        # a sheet that hangs from its pinched edge stands on its lower edge now: lay it down, turning the hand about
        # that edge until the sheet is 25 degrees from flat, and let go there (it falls flat)
        yield from _lay_down(world, obj, speed)
    # let go with the fingers opened only a little (inside a narrow vessel wide fingers push its walls, and a light
    # thing is flicked out when they leave), draw the hand away, and open it fully once it is clear
    # (From a tipped hand an assisted grasp is let go only when the fingers have opened: pads that open while they
    # still press on a thing that is already free drag it along the hand's axis, which for a tipped hand is across
    # the surface, and a round thing rolls away.)
    tip = abs(float(tf.rotate(world.tcp_pose()[1], UP)[2]))
    keep = bool(world.spec.extra.get("tipped_grasps")) and 0.17 < tip < 0.94 and world.held is not None
    yield from S._grip(world, S.gripper_target_for_opening(min(world.gripper_opening() + 0.008, S.max_opening(world)), world), keep=keep)
    yield from S.hold(world, 0.3)
    back = yield from _retreat(world, speed=speed, released=obj)
    yield from S._grip(world, S.gripper_target_for_opening(min(world.gripper_opening() + 0.022, S.max_opening(world)), world))
    return Status(True, "ok", {"object": obj, "touched_early": early, "peak_force": peak[0], "retreated": back.ok,
                               "let_go_above": dropped})


def _retreat(world: World, *, speed: float = 1.0, rise: float = 0.10, released: str | None = None):
    """Take the open hand away from what it has just let go of (`released`): a hand that held from the side first
    backs out along its own axis, then the hand goes straight up. Fingers that cannot back out (something stands
    behind the hand) open fully before they rise, so that they do not lift a thing that widens above them (a wine
    glass held by its stem)."""
    g = float(world.target[-1])
    q0 = world.joint_pos
    tcp, quat = world.tcp_pose()
    if _is_level(world):
        back = tcp - 0.08 * tf.unit(tf.rotate(quat, UP) * np.array([1.0, 1.0, 0.0]))
        path, why = _plan_leg(world, q0, back, True)
        if path is not None and S._path_hit(world, list(path[0::4]) + [path[-1]], (released,) if released else (), ()) is None:
            yield from _follow_leg(world, path, 0.08, g, lin_speed=0.10, speed=speed)
            q0 = world.joint_pos
            tcp = world.tcp_pose()[0]
        else:
            yield from S._grip(world, 0.0)
            g = float(world.target[-1])
    up = np.array([tcp[0], tcp[1], max(float(tcp[2]) + rise, world.ground(tcp) + 0.20)])
    path, why = _plan_leg(world, q0, up, _is_level(world))
    if path is None and world.spec.extra.get("tipped_grasps"):
        # A tipped hand high up cannot rise that far where it is: it draws back along its own axis, up and towards
        # the robot, as far as it can of the same distance.
        axis = tf.rotate(quat, UP)
        for back in (rise, 0.06, 0.03):
            path, why2 = _plan_leg(world, q0, tcp - back * axis, False)
            if path is not None and S._path_hit(world, list(path[0::4]) + [path[-1]], (released,) if released else (), ()) is None:
                return (yield from _follow_leg(world, path, back, g, lin_speed=0.10, speed=speed))
        path = None
    if path is None:
        return Status(False, f"{why}:retreat", {})
    return (yield from _follow_leg(world, path, float(up[2] - tcp[2]), g, lin_speed=0.12, speed=speed))


# ---- pouring ---------------------------------------------------------------------------------------------------------
# degrees about the vertical by which the tipping direction may be turned, in order of preference: over the rim
# opposite the hand and to either side of it, then over the rim the hand is at, then square to that line
POUR_TURNS = (0.0, 25.0, -25.0, 50.0, -50.0, 180.0, 155.0, -155.0, 130.0, -130.0, 90.0, -90.0)


def _pour_lean(world: World, tool: tf.Pose, mouth, point) -> np.ndarray:
    """The level direction a held vessel is tipped in: over the part of its rim opposite the hand. A vessel held by a
    handle or by a point of its rim tips away from where it is held; one held by its side, forwards along the tool;
    one held from above on its own axis has no good direction, and is tipped away from the robot."""
    to_axis = np.array([mouth[0] - tool[0][0], mouth[1] - tool[0][1], 0.0])
    z = tf.rotate(tool[1], UP)
    if float(np.linalg.norm(to_axis)) > 0.012:
        return tf.unit(to_axis)
    if abs(float(z[2])) < 0.5:
        return tf.unit(np.array([z[0], z[1], 0.0]))
    away = np.asarray(point, dtype=np.float64) - np.array(world.scene["robot"]["pos"][:2] + [0.0])
    away[2] = 0.0
    return tf.unit(away) if float(np.linalg.norm(away)) > 1e-6 else np.array([0.0, -1.0, 0.0])


def _pour_refusal(failures: list) -> tuple:
    """What to say when no way to pour was found, from why each direction and height was given up (`(reason, step,
    info)` in the order tried). If anything was in the way of any of them, that is the answer: the thing most of
    them met, with the step at which they met it (`info["by"]`, `info["who"]`: what would have touched it, the
    robot or the name of what it holds). Otherwise the arm cannot get there, and the first direction's reason is
    given. `info` also counts the ways tried and how many were blocked or out of reach."""
    blocked = [f for f in failures if f[0] == "path_blocked"]
    counts = {"tried": len(failures), "blocked": len(blocked), "unreachable": len(failures) - len(blocked)}
    if not blocked:
        first = failures[0] if failures else ("ik_unreachable", "tilt", {})
        return (first[0], first[1], {**first[2], **counts})
    seen: dict = {}
    for k, (_, step, info) in enumerate(blocked):
        seen.setdefault((step, info.get("by"), info.get("who")), []).append(k)
    step, by, who = max(seen, key=lambda key: (len(seen[key]), -seen[key][0]))     # the most frequent; of equals, the first met
    return ("path_blocked", step, {"by": by, "who": who, **counts})


POUR_RAISE = 0.08           # m: how much higher than it has to a vessel is tipped when it cannot be tipped lower


# a vessel that leans by more than this when the hand is back upright after a pour (it turned in the fingers) is stood up
LEAN_LEFT_DEG = 3.0
STAND_UP_LIFT = 0.06        # m: how far it is lifted first


def pour(world: World, point, *, angle: float = 115.0, height: float | None = None, seconds: float = 1.5, rate: float = 45.0):
    """Tip the held vessel over a point: bring the lip it will pour over `height` above the point (default: its own
    height plus 3 cm, so that it clears what it pours into), tilt it to `angle` degrees from upright about that lip,
    wait, and bring it back upright.

    The lip is the part of the rim opposite the hand (`_pour_lean`) or, where the arm cannot make that turn, another
    part of it (`POUR_TURNS`). Where there is no free way to that height in any direction (the vessel would come
    down onto something that stands at the point or next to it), it is tipped from higher. The whole of it (the way
    there and the turn) is planned and tested for collisions before anything moves, the arm
    against itself and the vessel against the arm included; a vessel that cannot be tipped from the way it is held
    (one taken from above on its axis) is not moved. What flows where is decided by the hazard layer from the
    vessel's pose. Reasons: `not_holding`, `not_a_vessel`, `ik_...:tilt`, `path_blocked:tilt` and those of
    `_plan_transfer` (nothing moved; chosen by `_pour_refusal`, with what was in the way in `info`),
    `not_reached:<leg>`, `not_reached:tilt`, `...:return`."""
    if not S.holding(world) or world.held is None:
        return Status(False, "not_holding", {})
    obj = world.held
    meta = world.objects[obj]["meta"]
    vessel = meta.get("vessel")
    if not vessel:
        return Status(False, "not_a_vessel", {"object": obj})
    point = np.asarray(point, dtype=np.float64)
    mouth_local = np.asarray(meta.get("sites", {}).get(vessel.get("mouth_site", "mouth"), [0.0, 0.0, meta.get("size", [0, 0, 0.1])[2]]), dtype=np.float64)
    radius = float(vessel.get("inner_radius", 0.03))
    if height is None:                           # the upright vessel must clear what it pours into
        bottom_local = np.asarray(meta.get("sites", {}).get(vessel.get("bottom_site", "bottom"), [0.0, 0.0, 0.0]), dtype=np.float64)
        height = float(mouth_local[2] - min(bottom_local[2], 0.0)) + 0.03
    _, _, reach, carried = _load(world)
    in_tool = tf.compose(tf.inverse(world.tcp_pose()), world.locate(obj))      # the vessel in the tool frame
    z_o = tf.rotate(world.locate(obj)[1], UP)

    def aim(tool: tf.Pose, turn_deg: float):
        mouth = tf.compose(tf.compose(tool, in_tool), (mouth_local, IDENTITY))[0]
        lean = tf.rotate(tf.quat_axis_angle(UP, math.radians(turn_deg)), _pour_lean(world, tool, mouth, point))
        return mouth, lean

    def way(over, turn_deg: float, angle: float = angle):
        """The legs that bring the lip over `over` and the turn about it, tested: (plan, None) or (None, why)."""
        q, legs = world.joint_pos, []
        tool = world.tcp_pose()
        for attempt in range(3):                 # a level carry turns the vessel about the vertical: aim again
            mouth, lean = aim(tool, turn_deg)
            shift = over - (mouth + lean * radius)
            if float(np.linalg.norm(shift)) < (2e-3 if attempt == 0 else 4e-3):
                break
            more, z = _plan_transfer(world, tool[0] + shift, q)
            if more is None:
                return None, z
            legs += more
            q = more[-1][1][-1]
            tool = world.ik.fk(q)
        mouth, lean = aim(tool, turn_deg)
        axis, pivot = np.cross(UP, lean), mouth + lean * radius
        now = math.atan2(float(np.dot(np.cross(UP, z_o), axis)), float(np.dot(UP, z_o)))
        path, res, n = S.tilt_path(world, q, tool, math.radians(float(angle)) - now, axis, pivot)
        if not res.ok:
            return None, ("ik_" + res.reason, "tilt", {"solved_deg": float(angle) * path.shape[0] / n})
        hit = S._path_hit(world, [q] + list(path[1::2]) + [path[-1]], (), carried, arm_vs_load=True, clearance=S.PATH_CLEARANCE)   # every 2 degrees
        if hit is not None:
            return None, ("path_blocked", "tilt", {"by": hit[1], "who": hit[0]})
        return (legs, axis, pivot, turn_deg), None

    # The usual height first, in every tipping direction. Where the vessel cannot come down that far (the point lies
    # among things that are taller than it: next to the rim of what is poured into, on a table between bottles), it
    # is tipped from higher: with its underside as far above the tallest thing under it as it otherwise is above
    # the point, then a little more. What flows where does not depend on the height.
    lifts = [0.0]
    if world.avoid:
        extra = _tops(world, point, point, reach + 0.02, ignore=tuple(n for n, _ in carried)) - float(point[2])
        lifts += [extra, extra + POUR_RAISE] if extra > 0.005 else [POUR_RAISE]
    plan, lifted = None, 0.0
    failures = []
    # An arm whose wrist cannot make the whole turn (`RobotSpec.extra["pour_angles"]`: smaller angles it may settle
    # for, each still past level) tries those once the angle asked for has failed in every direction and height.
    asked = float(angle)
    for angle in (asked,) + tuple(a for a in world.spec.extra.get("pour_angles", ()) if a < asked):
        for lifted in lifts:
            over = np.array([point[0], point[1], point[2] + height + lifted])
            for turn_deg in world.spec.extra.get("pour_turns", POUR_TURNS):
                plan, why = way(over, turn_deg, angle)
                if plan is not None:
                    break
                if angle == asked:
                    failures.append(why)
            if plan is not None:
                break
        if plan is not None:
            break
    if plan is None:
        why = _pour_refusal(failures)
        return Status(False, f"{why[0]}:{why[1]}", why[2])
    legs, axis, pivot, turn_deg = plan
    st = yield from _run_legs(world, legs, lin_speed=0.12)
    if not st.ok:
        return st
    mouth, lean = aim(world.tcp_pose(), turn_deg)            # where it really is now
    axis, pivot = np.cross(UP, lean), mouth + lean * radius
    st = yield from S.tilt(world, obj, angle, rate, axis=axis, pivot=pivot, check=True)
    if not st.ok and st.reason.startswith("ik_") and world.spec.extra.get("pour_turns"):
        # (an arm that pours at the edge of its reach: the turn that was planned from where the arm was to be has no
        # solution from where it really stopped, a millimetre off. The smaller angles are tried from there.)
        for less in tuple(a for a in world.spec.extra.get("pour_angles", ()) if a < angle):
            st = yield from S.tilt(world, obj, less, rate, axis=axis, pivot=pivot, check=True)
            if st.ok or not st.reason.startswith("ik_"):
                angle = less
                break
    way = st.info.pop("joint_path", None)
    rad = float(st.info.pop("rad", 0.0))

    def upright():
        # Back the way it came: the joints retrace the turn, which needs no new solution (solving the turn again from
        # where the arm stopped can fail and would leave the vessel tipped).
        if way is None:
            return (yield from S.tilt(world, obj, 0.0, rate, axis=axis, pivot=pivot))
        return (yield from S._follow(world, way[::-1].copy(), float(world.target[-1]), rad, lin_speed=math.radians(rate)))

    if not st.ok:
        moved = st.reason in ("not_reached", "lost_grip")
        back = (yield from upright()) if moved else Status(True)
        return Status(False, f"{st.reason}:tilt", {**st.info, "returned": back.ok})
    yield from S.hold(world, seconds)
    back = yield from upright()
    info = {"object": obj, "angle": angle, "turned_deg": turn_deg, "raised": lifted}
    if back.ok:
        # Held by contact (since 0.5.0, no weld), a vessel can turn in the fingers while it is tipped (a bottle held by
        # its handle swings round the pinch): the joints back where they were leave it leaning. On an arm that says so
        # (`RobotSpec.extra["stand_up_after_pour"]`: the room arm) it is stood up again by turning the hand about the
        # level axis it leans about, once. (The bench arms do not: their admitted records would change.)
        z_o = tf.rotate(world.locate(obj)[1], UP)
        lean_deg = math.degrees(math.acos(max(-1.0, min(1.0, float(z_o[2])))))
        level = np.cross(UP, z_o)
        level[2] = 0.0
        if (world.spec.extra.get("stand_up_after_pour") and lean_deg > LEAN_LEFT_DEG and float(np.linalg.norm(level)) > 1e-6
                and S.holding(world)):
            # first straight up out of what it poured into (the turn about the pinch point swings its foot round)
            up = yield from S._carry(world, [world.tcp_pose()[0] + np.array([0.0, 0.0, STAND_UP_LIFT])], np.zeros(3), float(world.target[-1]),
                                     carried=S._attached(world, S.held_objects(world)))
            fix = yield from S.tilt(world, obj, 0.0, rate, axis=tf.unit(level), check=True)
            info["lifted_to_stand_up"] = up.ok
            z_o = tf.rotate(world.locate(obj)[1], UP)
            info.update({"stood_up_from_deg": round(lean_deg, 1), "stood_up": fix.ok, "stand_up": fix.reason, **{k: v for k, v in fix.info.items() if k in ("by", "from_deg", "solved_deg")},
                         "lean_deg": round(math.degrees(math.acos(max(-1.0, min(1.0, float(z_o[2]))))), 1)})
    return Status(back.ok, "ok" if back.ok else f"{back.reason}:return", info)


# ---- pressing, looking, letting go, going home -----------------------------------------------------------------------
def press(world: World, pose, depth: float = 0.008, *, max_force: float = 40.0, ignore=(), centre=None):
    """Press with the closed fingertips at a pose whose `+z` points out of the surface. A control that cannot be
    reached square to its surface is pressed at a slant, at the smallest of the angles `PRESS_TILTS` that can be
    reached without touching anything else: a button on the front of an appliance (with the robot behind it) from
    above; a lever on the side of one, which faces up, with the hand leaning away from the appliance (`centre`: a
    point in the middle of it). Reasons: `holding` when the hand is not free; `ik_unreachable:approach` and
    `path_blocked:approach` (the arm was not moved); those of `skills.press`."""
    if S.holding(world):
        return Status(False, "holding", {"held": world.held})
    pose = tf.as_pose(pose)
    n = tf.rotate(pose[1], UP)
    lean = DOWN                                        # which way the tool's tip is turned for a slanted stroke
    if float(n[2]) > 0.94:
        inward = np.zeros(3) if centre is None else np.asarray(centre, dtype=np.float64) - pose[0]
        inward[2] = 0.0
        lean = tf.unit(inward) if float(np.linalg.norm(inward)) > 0.02 else None
    alongs = [-n]
    for tilt_deg in PRESS_TILTS[1:]:
        if lean is not None:
            t = math.radians(tilt_deg)
            alongs.append(tf.unit(-n * math.cos(t) + lean * math.sin(t)))
    st = yield from S.press(world, pose, depth, max_force=max_force, along=alongs, ignore=ignore, approach=(0.03, 0.08))
    if "direction" in st.info:
        st.info["slant_deg"] = PRESS_TILTS[st.info["direction"]]
    if world.gripper_opening() < 0.05:
        yield from S.open_gripper(world)
    return st


def look(world: World, point, side: str = "above", distance: float = LOOK_DISTANCE, yaw: float = 0.0):
    """Bring the wrist camera to look at a point from `side`, the pinch point `distance` away from it. The hand
    touches nothing on purpose. A view from the side is taken as low as the arm can manage (37 degrees above the
    horizon, else 55, else 70; a robot may name its own, `RobotSpec.extra["look_elevations"]`). The sides are those of
    the bench as its `front` camera shows it; `yaw` turns them about the vertical (a robot that drives names them as
    its own camera sees the thing). An arm that cannot reach all round a thing takes the nearest view it can
    (`RobotSpec.extra["look_round"]`, below); `info` then says by how much the view was brought round
    (`towards_front_deg`) and from what elevation it is. Reasons: `unknown_side`, `unreachable_view` (nothing moved),
    `path_blocked`, `not_reached`."""
    if side not in LOOK_SIDES:
        return Status(False, "unknown_side", {"sides": sorted(LOOK_SIDES)})
    point = np.asarray(point, dtype=np.float64)
    base = np.array(LOOK_SIDES[side])
    back = np.array([0.0, 1.0, 0.0])
    if yaw:
        turned = tf.quat_axis_angle(UP, float(yaw))
        base, back = tf.rotate(turned, base), tf.rotate(turned, back)
    floor = world.ground(point)

    def view(h, elevation: float) -> np.ndarray:
        return h * math.cos(math.radians(elevation)) + np.array([0.0, 0.0, math.sin(math.radians(elevation))])

    # An arm that cannot hold its hand everywhere round a thing (`RobotSpec.extra["look_round"]`: the angles, in
    # degrees, by which a view may be brought round towards the robot's own side, and the elevations it may also
    # take) gets the nearest view it can reach: from above, straight down first and then steeply from its own side;
    # from the left or the right, square to the thing first and then from between that side and the front; and a
    # flat view where it cannot hold the hand high enough to look down on a point.
    near = world.spec.extra.get("look_round")
    front = -back
    turns = [0.0]
    if side == "above":
        outs = [base] + ([view(front, e) for e in near["steep"]] if near else [])
        turns += [0.0] * (len(outs) - 1)
    else:
        h = tf.unit(np.array([base[0], base[1], 0.0]))
        hs = [h]
        if near and side in ("left", "right"):
            sign = 1.0 if float(np.cross(h, front)[2]) > 0.0 else -1.0        # which way round the front lies
            for a in near["towards_front"]:
                hs.append(tf.rotate(tf.quat_axis_angle(UP, sign * math.radians(a)), h))
                turns.append(float(a))
        elevations = tuple(world.spec.extra.get("look_elevations", (37.0, 55.0, 70.0))) + (tuple(near["flat"]) if near else ())
        outs = [view(hh, e) for hh in hs for e in elevations]
        turns = [t for t in turns for _ in elevations]
    seeds = [world.joint_pos, world.ready, S.ready_posture(world, "side"), S.ready_posture(world, "side_low"), world.home]
    carried = S._attached(world, S.held_objects(world))
    now = world.joint_pos
    up_ref = back if side == "above" else UP
    last = Status(False, "unreachable_view", {"side": side})
    for out, turned_by in zip(outs, turns):
        z = -tf.unit(out)                        # the tool looks along its +z
        found = []
        for d in world.spec.extra.get("look_distances", (distance, distance + 0.06)):
            pos = point + tf.unit(out) * d
            pos[2] = max(float(pos[2]), floor + 0.06)
            for ref in (np.array([1.0, 0.0, 0.0]), UP, np.array([0.0, 1.0, 0.0])):
                if abs(float(np.dot(ref, z))) > 0.9:
                    continue
                for flip in (1.0, -1.0):
                    y = tf.unit(np.cross(z, ref)) * flip
                    quat = tf.quat_from_axes(y=y, z=z)
                    # the wrist image's "up" is the tool's +x: keep it pointing up (seen from the side) or to the back
                    # of the table (seen from above), so that the picture is not upside down
                    upright = float(np.dot(np.cross(y, z), up_ref))
                    if not S._in_span(world, (pos, quat)):       # the wrist beyond the arm's length: nothing to solve
                        continue
                    for seed in seeds:
                        r = world.ik.solve(pos, quat, seed, max_jump=10.0)
                        if not r.ok or world.ik.collision(r.q, carried=carried) is not None:
                            continue
                        cost = float(np.sum(np.abs(r.q - now))) + (0.0 if upright > 0.5 else 20.0)
                        found.append((cost, len(found), r.q, d))
            if found:
                break
        if not found:
            continue
        found.sort(key=lambda f: (f[0], f[1]))
        tcp = world.tcp_pose()[0]
        safe = world.ground(tcp) + SAFE_HEIGHT
        if float(tcp[2]) < safe - 0.01:                  # come up first: a low sweep across the table knocks things over
            path, why = _plan_leg(world, world.joint_pos, np.array([tcp[0], tcp[1], safe]), _is_level(world))
            if path is not None:
                yield from _follow_leg(world, path, safe - float(tcp[2]), float(world.target[-1]), lin_speed=0.15)
        tried: list = []
        for cost, _, q, d in found:                      # the cheapest view whose way there is free
            if any(float(np.max(np.abs(q - t))) < 0.05 for t in tried):
                continue
            if len(tried) == 4:
                break
            tried.append(q)
            last = yield from S._go(world, q, float(world.target[-1]), carried, 1.0)
            if last.ok:
                info = {"side": side, "distance": d, "elevation_deg": round(math.degrees(math.asin(float(tf.unit(out)[2]))), 1)}
                if near:                         # how far the view was brought round towards the robot's side
                    info["towards_front_deg"] = turned_by
                return Status(True, "ok", info)
            if last.reason != "path_blocked":
                return last
    return last


def release(world: World):
    """Open the hand where it is."""
    st = yield from S.release(world)
    return Status(True, "ok", st.info)


def home(world: World):
    """Go to the rest posture, keeping the hand as it is: straight up first until the hand and what it holds are
    above everything near them, then one free move, tested for collisions, if need be by way of the ready posture.
    Reasons: `path_blocked` (nothing was touched; the hand is where the rise left it), `not_reached`."""
    tcp = world.tcp_pose()[0]
    g = float(world.target[-1])
    off, below, reach, carried = _load(world)
    held = tuple(n for n, _ in carried)
    if float(np.max(np.abs(world.joint_pos - world.home))) < 2e-3:
        return Status(True, "ok", {})
    if carried:
        # with something in the hand the arm does not go to the rest posture, which would turn what it holds: it
        # rises where it is, keeping the tool as it is, and stays there
        up = min(float(tcp[2]) + 0.15, world.ground(tcp) + 0.45)
        path, why = _plan_leg(world, world.joint_pos, np.array([tcp[0], tcp[1], up]), _is_level(world))
        if path is None:
            return Status(False, "holding", {"why": why})
        st = yield from _follow_leg(world, path, up - float(tcp[2]), g, lin_speed=0.12)
        return Status(st.ok, "ok" if st.ok else st.reason, {"holding": True, "note": "the hand holds something: it was raised, not taken to the rest posture"})
    need = _tops(world, tcp, tcp, reach + 0.05, ignore=held) + CLEAR_MARGIN + below
    floor = world.ground(tcp)
    need = min(max(need, floor + 0.20 if float(tcp[2]) - floor < 0.18 else 0.0), float(tcp[2]) + 0.30)
    if need > float(tcp[2]) + 1e-3:
        path, why = _plan_leg(world, world.joint_pos, np.array([tcp[0], tcp[1], need]), _is_level(world))
        if path is not None:
            yield from _follow_leg(world, path, need - float(tcp[2]), g, lin_speed=0.12)
    st = yield from S._go(world, world.home, g, carried, 1.0)
    if not st.ok and st.reason == "path_blocked":
        via = yield from S._go(world, world.ready, g, carried, 1.0)
        if via.ok:
            st = yield from S._go(world, world.home, g, carried, 1.0)
    return st


def wait(world: World, seconds: float):
    yield from S.hold(world, max(float(seconds), CONTROL_DT))
    return Status(True, "ok", {"seconds": float(seconds)})


# ---- holding a thing where it stands, turning a cap (0.5.0) -------------------------------------------------------------
HOLD_TILTS = (90.0, 75.0, 60.0)        # degrees from straight down at which a hand takes a standing thing by its side to hold it
HOLD_LEANS = (0.0, 30.0, -30.0, 60.0, -60.0)   # degrees about the vertical from the direction towards the arm's base
HOLD_BACK = 0.08                        # m: the hand comes in along its own axis from this far back
HOLD_RAISE = (0.0, 0.01, 0.02, 0.035)   # m: above the asset's grasp by the side, where the hand may also take the thing


def _hold_point(world: World, obj: str) -> tuple[np.ndarray, float]:
    """Where a hand takes a standing thing by its side, and how wide it is there: the asset's grasp by the side (its
    `body`), else the middle of its height on its axis."""
    meta = world.objects[obj]["meta"]
    here = world.locate(obj)
    for g in meta.get("grasps", []):
        if g["type"] == "side":
            return tf.compose(here, (np.asarray(g["pos"], dtype=np.float64), IDENTITY))[0], float(g["width"])
    lo, hi = world.box(obj)
    size = meta.get("size", [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]])
    return np.array([here[0][0], here[0][1], (lo[2] + hi[2]) / 2.0]), float(min(size[0], size[1]))


def hold(world: World, obj: str, *, speed: float = 1.0):
    """Take a thing that stands on something by its side and keep it where it is, without lifting it: the hand that
    holds a bottle still while the other hand turns its cap, or a cup while the other pours into it. The hand comes
    in level or tipped (`HOLD_TILTS`), from the arm's side of the thing (`HOLD_LEANS`), along its own axis, and
    closes; the thing is then held by the grasp assist as by `pick`. Reasons: `already_holding`, `not_graspable`,
    `too_wide`, `ik_unreachable:pregrasp`, `path_blocked:pregrasp` (nothing moved), `not_reached:approach`,
    `nothing_grasped`."""
    if S.holding(world):
        return Status(False, "already_holding", {"held": world.held})
    o = world.objects.get(obj)
    if o is None or o["fixed"]:
        return Status(False, "not_graspable", {"object": obj})
    # a thing with a handle that sticks out (a saucepan) is held by it, from straight above, where it stands
    handle = next((g for g in grasps_of(world, obj) if g["name"] == "handle" and g["type"] == "top" and g["offset"] > 0.015), None)
    if handle is not None and float(handle["width"]) <= S.max_opening(world) - 0.004:
        st = yield from S.pick(world, obj, {"type": "top", "pose": handle["pose"], "width": handle["width"], "free": True}, lift=0.0, speed=speed)
        if st.ok:
            return Status(True, "ok", {"object": obj, "by": "handle"})
        if not st.reason.endswith(":pregrasp"):
            return st
    point, width = _hold_point(world, obj)
    if width > S.max_opening(world) - 0.004:
        return Status(False, "too_wide", {"object": obj, "opens_to": S.max_opening(world)})
    base = np.asarray(world.scene["robot"]["pos"][:2], dtype=np.float64)
    to_base = math.atan2(float(base[1] - point[1]), float(base[0] - point[0]))
    seeds = [world.home, world.ready, S.ready_posture(world, "side"), S.ready_posture(world, "side_low")]
    best, refused = None, []
    # the most nearly level hand first (it takes the least room above the thing: the other hand may need it), and
    # for each tilt the way of holding at the thing's grasp by its side, then up to 3.5 cm higher on it
    tries = [(tilt, dz, lean) for tilt in HOLD_TILTS for dz in HOLD_RAISE for lean in HOLD_LEANS]
    top = float(world.box(obj)[1][2])
    base_point = point
    for tilt, dz, lean in tries:
        point = base_point + np.array([0.0, 0.0, dz])
        if point[2] > top - 0.02:
            continue
        if True:
            a = to_base + math.radians(lean)
            towards = np.array([math.cos(a), math.sin(a), 0.0])           # from the thing towards the wrist
            t = math.radians(tilt)
            z = -math.cos(t) * UP - math.sin(t) * towards                  # the hand points into the thing
            y = np.cross(UP, towards)                                      # the fingers close level, across it
            quat = tf.quat_from_axes(y=y, z=z)
            goal = (point.copy(), quat)
            pre = (point - HOLD_BACK * z, quat)
            plan, why = S._reach(world, pre, [goal], [], ignore_last=(obj,), seeds=seeds)
            if plan is None:
                refused.append(why)
                continue
            best = (plan, pre, goal, tilt)
            break
    if best is None:
        blocked = any(w.startswith("blocked") for w in refused)
        return Status(False, "path_blocked:pregrasp" if blocked else "ik_unreachable:pregrasp", {"refused": refused[:6]})
    plan, pre, goal, tilt = best
    yield from S._grip(world, S.gripper_target_for_opening(min(width + 0.024, S.max_opening(world)), world))
    g = float(world.target[-1])
    st = yield from S._go(world, plan["q_first"], g, (), speed)
    if not st.ok:
        return Status(False, f"{st.reason}:pregrasp", st.info)
    st = yield from S._move(world, goal, g, linear=True, speed=speed, lin_speed=0.10)
    if not st.ok and not (st.reason == "not_reached" and float(np.linalg.norm(world.tcp_pose()[0] - goal[0])) < 0.008):
        yield from S._move(world, pre, g, linear=True, speed=speed, lin_speed=0.10)
        return Status(False, f"{st.reason}:approach", st.info)
    yield from S._close(world)
    if getattr(world, "assist", True) and world.objects[obj].get("weld_id") is not None:
        world.attach(obj)
    if not S.holding(world):
        yield from S._grip(world, g)
        return Status(False, "nothing_grasped", {})
    return Status(True, "ok", {"tilt_deg": tilt, "object": obj})


TWIST_STROKE = 200.0       # degrees: the most one turn of the wrist gives before the hand lets go and takes hold again
TWIST_STEP = 40.0          # degrees per straight move of a stroke
TWIST_STROKES = 8          # strokes a call makes at most
TWIST_JUMP = 0.6           # rad: the most a joint may change between neighbouring yaws (10 degrees) of a stroke
TWIST_SETTLE_S = 0.3       # s: the closed hand keeps still this long before a stroke turns (was 0.1)
TWIST_RESISTED_RAD = 0.02  # rad: a turn of the wrist held back by less than this at its end is taken as done


def _twist_resisted(st) -> bool:
    """A straight move of a stroke that tracked its whole path and then did not settle within `TWIST_RESISTED_RAD` of
    its joint targets (`not_reached`, measured 3 to 5 mrad): the cap held on the bottle's axis pulls back on a hand
    whose pinch point is not exactly on that axis (0.5.1, grasping by contact). Before, a stroke ended there after
    its first 40 degrees and a twist ran out of strokes."""
    return st.reason == "not_reached" and float((st.info or {}).get("joint_err", 1.0)) < TWIST_RESISTED_RAD


def _yaw_run(world: World, pinch, ignore) -> list[float]:
    """The yaws (degrees, in 10 degree steps) at which the hand reaches `pinch` pointing straight down without
    touching anything (but `ignore`), as one run of neighbours that the arm turns through without a jump of its joints:
    each yaw's configuration is solved from the last one's (0.5.1: a run of yaws that were each reachable from some
    seed was not always one the wrist could turn through: on the YAM the hand stopped 40 degrees into a stroke, and
    a twist under grasping by contact ran out of strokes)."""
    first = {}
    for yaw in range(-180, 180, 10):
        quat = tf.quat_from_ypr(float(yaw), 0.0, 0.0)
        for seed in (world.joint_pos, world.ready, world.home):
            r = world.ik.solve(pinch, quat, seed, max_jump=10.0, max_iters=200)
            if r.ok and world.ik.collision(r.q, ignore) is None:
                first[yaw] = r.q
                break
    best: list = []
    for start in sorted(first):
        run, q, yaw = [float(start)], first[start], start
        while len(run) < 36:
            yaw += 10
            r = world.ik.solve(pinch, tf.quat_from_ypr(float(yaw), 0.0, 0.0), q, max_jump=TWIST_JUMP, max_iters=200)
            if not r.ok or world.ik.collision(r.q, ignore) is not None:
                break
            q = r.q
            run.append(float(yaw))
        if len(run) > len(best):
            best = run
    return best


def twist(world: World, cap: str, vessel: str, *, direction: str = "open", done=None, speed: float = 1.0):
    """Turn a screw cap with the hand: `open` takes hold of the cap from above and turns it anticlockwise (seen from
    above), in strokes of up to `TWIST_STROKE` degrees (the hand lets go, turns back and takes hold again between
    them), until `done()` says it has come off, then lifts it 6 cm; `close` puts the cap the hand holds on the
    vessel's mouth (`place`), takes hold of it again and turns it clockwise until `done()` says it is tight, then lets
    go and rises. Whether a cap turns on its bottle is the hazard layer's (`ScrewCap`): the bottle must be kept from
    turning with it, by the other hand or because it is fixed. After the first stroke of an `open` the cap still
    fastened to its bottle means that the bottle turned with it: the hand lets go and rises (`turned_with_it`).
    Reasons: `already_holding`, `not_holding`, `ik_unreachable:turn` (no straight-down hand can turn far enough
    there; nothing moved), those of reaching the cap (`...:pregrasp`, `...:approach`), `turned_with_it`,
    `not_loosened` / `not_tightened` (the strokes ran out)."""
    done = done or (lambda: False)
    if direction == "open" and S.holding(world):
        return Status(False, "already_holding", {"held": world.held})
    if direction == "close":
        if world.held != cap:
            return Status(False, "not_holding", {})
        meta_v = world.objects[vessel]["meta"]
        mouth = tf.compose(world.locate(vessel), (np.asarray(meta_v.get("sites", {}).get("mouth", [0.0, 0.0, meta_v["size"][2]]), dtype=np.float64), IDENTITY))[0]
        st = yield from place(world, mouth, speed=speed)
        if not st.ok:
            return st
    meta = world.objects[cap]["meta"]
    lo, hi = world.box(cap)
    width = float(min(meta.get("size", [hi[0] - lo[0]] * 2)[:2]))
    up_axis = tf.rotate(world.locate(cap)[1], UP)
    pinch = (np.asarray(lo) + np.asarray(hi)) / 2.0
    pinch[2] = max(float(pinch[2]), float(hi[2]) - 0.012)
    ignore = (cap, vessel) + tuple(world.others_hold() if hasattr(world, "others_hold") else ())
    run = _yaw_run(world, pinch, ignore)
    if len(run) < 7 or float(up_axis[2]) < 0.95:          # less than 60 degrees of turn, or a bottle that does not stand up
        return Status(False, "ik_unreachable:turn", {"yaws": run[:1] + run[-1:]})
    stroke = min(run[-1] - run[0], TWIST_STROKE)
    sign = 1.0 if direction == "open" else -1.0
    start = run[0] if direction == "open" else run[-1]
    opening = S.gripper_target_for_opening(min(width + 0.024, S.max_opening(world)), world)
    yield from S._grip(world, opening)
    g = float(world.target[-1])
    # the way in: a free move to above the cap (as high as the hand reaches pointing down: the other arm, holding the
    # bottle, is lower down beside it), then straight down to the cap
    quat = tf.quat_from_ypr(start, 0.0, 0.0)
    plan, why, chain = None, "ik_unreachable", None
    for high in (0.16, 0.12, 0.08, None):
        for above in (0.08, 0.06, 0.04, 0.025):           # a hand pointing down is not held high far from its base
            pre = (pinch + np.array([0.0, 0.0, above]), quat)
            if high is not None and high <= above:
                continue
            first = pre if high is None else (pinch + np.array([0.0, 0.0, high]), quat)
            rest = [(pinch.copy(), quat)] if high is None else [pre, (pinch.copy(), quat)]
            plan, why = S._reach(world, first, rest, S._ready_list(world, "top"), ignore_last=ignore, ignore=ignore[:2],
                                 seeds=[world.home, world.ready])
            if plan is not None:
                chain = [first] + rest
                break
        if plan is not None:
            break
    if plan is None:
        return Status(False, ("path_blocked" if why.startswith("blocked") else "ik_unreachable") + ":pregrasp", {"why": why})
    if plan["via"] is not None:
        st = yield from S._go(world, plan["via"], g, (), speed)
        if not st.ok:
            return Status(False, f"{st.reason}:ready", st.info)
    st = yield from S._go(world, plan["q_first"], g, (), speed)
    if not st.ok:
        return Status(False, f"{st.reason}:pregrasp", st.info)
    for pose in chain[1:]:
        st = yield from S._move(world, pose, g, linear=True, speed=speed, lin_speed=0.08)
        if not st.ok and not (st.reason == "not_reached" and float(np.linalg.norm(world.tcp_pose()[0] - pinch)) < 0.006):
            return Status(False, f"{st.reason}:approach", st.info)
    turned, strokes = 0.0, 0
    for strokes in range(1, TWIST_STROKES + 1):
        yield from S._close(world)
        if world.held is None:
            world.attach(cap)
        # (0.5.1) the hand keeps still a while before it turns: under the control interface a grasp is taken once the
        # fingers have rested for 5 ticks, and only a cap held by a hand turns on its bottle (`ScrewCap`); a turn begun
        # earlier turned the bottle with the cap and the compiled rows of a twist did not open it again
        yield from S.hold(world, TWIST_SETTLE_S)
        yaw, left = start, stroke
        while left > 1e-6 and not done():
            step = min(TWIST_STEP, left)
            q = tf.quat_from_ypr(yaw + sign * step, 0.0, 0.0)
            st = yield from S._move(world, (pinch.copy(), q), float(world.target[-1]), linear=True, speed=speed, lin_speed=0.05, ang_speed=0.8)
            if not st.ok and not _twist_resisted(st):
                break
            yaw += sign * step
            left -= step
            turned += step
        yield from S.hold(world, 0.1)
        if done():
            break
        if direction == "open" and strokes == 1 and cap in world.fastened and cap not in getattr(world, "hinged", {}):
            yield from S._grip(world, opening)                 # the bottle turned with the cap: nothing held it
            yield from _retreat(world, speed=speed, released=cap)
            return Status(False, "turned_with_it", {"turned_deg": turned})
        yield from S._grip(world, opening)                      # let go, turn back the way it came, take hold again
        st = Status(True, "ok", {})
        while st.ok and abs(yaw - start) > 1e-6:
            yaw -= math.copysign(min(TWIST_STEP, abs(yaw - start)), yaw - start)
            st = yield from S._move(world, (pinch.copy(), tf.quat_from_ypr(yaw, 0.0, 0.0)), g, linear=True, speed=speed, lin_speed=0.05, ang_speed=1.2)
            if not st.ok and _twist_resisted(st):
                st = Status(True, "ok", {})
        if not st.ok:
            break
    if not done():
        if world.held is not None:
            yield from S._grip(world, opening)
        yield from _retreat(world, speed=speed, released=cap)
        return Status(False, "not_loosened" if direction == "open" else "not_tightened", {"turned_deg": turned, "strokes": strokes})
    if direction == "open":                                     # lift the cap off and keep it
        # (at the end of a stroke the wrist may stand near a joint limit that a lift of 6 cm runs into: lower lifts are
        # tried; the cap is off whichever succeeds, and `place` plans its own way up from where the hand is)
        for lift in (0.06, 0.04, 0.02):
            st = yield from S._move(world, (pinch + np.array([0.0, 0.0, lift]), world.tcp_pose()[1]), float(world.target[-1]), linear=True,
                                    speed=speed, lin_speed=0.06)
            if st.ok:
                break
        return Status(True, "ok", {"turned_deg": turned, "strokes": strokes, "holding": world.held == cap, "lifted": lift if st.ok else 0.0})
    yield from S._grip(world, opening)
    yield from _retreat(world, speed=speed, released=cap)
    return Status(True, "ok", {"turned_deg": turned, "strokes": strokes})
