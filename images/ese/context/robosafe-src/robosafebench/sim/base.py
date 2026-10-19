"""A base that drives: where it may stand, the way there, and the rows that take it there (docs/MOTION.md 12).

`go` is what the tool of that name does: the arm is brought over the base (to its rest posture, or holding level
what the hand holds), a way is planned on a grid of the floor built from everything that is not the robot at that
moment, and the base follows at most `LEG` metres of it. `turn` turns the base on the spot. Both are generators of
control rows like the skills; their rows are rows of the whole robot (base targets, arm targets, gripper target),
the arm's targets held as they are.

Nothing here stops the base for something that comes into its way after the call has started: what it runs into
stops it (`not_reached`), and the hazard layer records the contact. `drive` and `turn` take `watch`, a callable looked
at every tick whose answer stops the base (`stopped`): the hook for a protective stop, which no caller uses yet.
"""
from __future__ import annotations

import heapq
import math

import mujoco
import numpy as np

from . import actions as A
from . import skills as S
from . import tf
from .motion import _profile_times, trapezoid
from .skills import Status
from .world import CONTROL_DT

GRID = 0.05                 # m: the cells of the floor grid
MARGIN = 0.05               # m: how far a planned way keeps the robot's outline from everything
ROOMY = 0.10                # m: ways that keep this much more are preferred
LEG = 2.0                   # m: one call drives at most this far along its way
FLAT = 0.022                # m: what is lower than this passes under the base and is no obstacle (a cord, a rug, a mat, a sill)
# Where a body stands to work is a property of the body (`RobotSpec.base`: `standoff`, `dock_gap`, `figure_standoff`):
# the TidyBot's level hand works 0.60 m from a thing; a body with short arms has to stand much nearer. These are the
# values of a spec that does not say.
FIGURE_STANDOFF = 0.90      # m: pointed at a person, a child or an animal, the base's middle stays this far from them
DOCK_GAP = 0.04             # m: how near the robot's outline comes to furniture it is sent to
DOCK_NEAR = 0.60            # m: ... and how near its middle comes to the spot pointed at


def standoff(world, key: str = "standoff") -> float:
    """The body's own distance for `standoff` (its middle from the spot it works at), `dock_gap` (its outline from
    furniture) or `figure_standoff` (its middle from a person or an animal)."""
    return float(world.base.get(key, {"standoff": DOCK_NEAR, "dock_gap": DOCK_GAP, "figure_standoff": FIGURE_STANDOFF}[key]))
NEAR_GOAL = 1.20            # m: a stand-off place further than this from the spot pointed at is no place for it
BACK_OFF = 0.80             # m: how far `turn` backs away from what the base faces to find room to turn
LAG_STOP = (0.06, 0.25)     # m, rad: a base this far behind its target has met something
FIGURE_TAGS = ("human", "child", "animal")


# ---- the robot's outline and what it would touch -----------------------------------------------------------------------
def _geom_points(world, g: int) -> np.ndarray:
    """Points of a shape in its own frame that span it (the vertices of a mesh, thinned; the corners of a primitive's box)."""
    cache = world.__dict__.setdefault("_geom_points_cache", {})
    if g not in cache:
        m = world.model
        if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            k = int(m.geom_dataid[g])
            v = m.mesh_vert[int(m.mesh_vertadr[k]):int(m.mesh_vertadr[k]) + int(m.mesh_vertnum[k])]
            cache[g] = np.array(v[::max(len(v) // 400, 1)], dtype=np.float64)
        else:
            c, h = m.geom_aabb[g, :3], m.geom_aabb[g, 3:]
            cache[g] = np.array([c + h * np.array([sx, sy, sz]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    return cache[g]


def extent(world) -> float:
    """How far the robot and what its hands hold reach from the base's vertical now (m), measured on the shapes."""
    m, s = world.model, world._sync()
    centre = world.base_pose()[:2]
    r = float(max(np.hypot(*p) for p in world.base["footprint"]))
    for g in range(m.ngeom):
        if world._geom_owner[g] != "robot" or int(m.geom_bodyid[g]) == world._base_body or int(m.geom_group[g]) > 3:
            continue
        pts = s.geom_xpos[g] + _geom_points(world, g) @ s.geom_xmat[g].reshape(3, 3).T
        r = max(r, float(np.max(np.hypot(pts[:, 0] - centre[0], pts[:, 1] - centre[1]))) + 0.005)
    for name in _load(world):
        lo, hi = world.box(name)
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                r = max(r, float(math.hypot(x - centre[0], y - centre[1])))
    return r


def _load(world) -> tuple:
    """What travels with the robot: what its hands hold, and what is fastened onto that."""
    names = {n for n in world.held_by.values() if n}
    for a, b in sorted(world.fastened.items()):
        if b in names:
            names.add(a)
    return tuple(sorted(names))


def working_distance(world, thing: str | None = None) -> float:
    """How far from a spot the base's middle should stand to work there: the body's `standoff`, and, with something in the
    hand, further by as much as that thing's own middle is ahead of the pinch point (a pan held by its handle is put
    down with its middle on the spot, the hand a hand's breadth short of it). A body whose hand works nearer to it
    pointing down than level says so (`standoff_down`): that is where it stands with something held from above, and,
    with an empty hand, before a loose `thing` that can only be taken from above or that stands lower than its level
    hand works (`level_above`: the height of what the thing stands on)."""
    held = [(a, n) for a, n in world.held_by.items() if n]
    down = world.base.get("standoff_down")
    # (a robot with a free hand that is sent to a loose thing it does not hold comes for that thing)
    loose = thing in world.objects and not world.objects[thing]["fixed"] and all(n != thing for _, n in held)
    if not held or (loose and len(held) < len(world.held_by)):
        return float(down) if loose and _from_above(world, thing) else standoff(world)
    # (each thing from the pinch point of the hand that holds it)
    near = standoff(world)
    if down is not None and any(abs(float(tf.rotate(world.arm(a or None).tcp_pose()[1], [0.0, 0.0, 1.0])[2])) >= 0.5 for a, _ in held):
        near = float(down)
    return near + max(float(np.linalg.norm((world.locate(n)[0] - world.arm(a or None).tcp_pose()[0])[:2])) for a, n in held)


def _grasps(world, thing: str) -> list:
    meta = world.objects[thing]["meta"]
    return list(meta.get("grasps", [])) or list(meta.get("grips", {}).values())


def _from_above(world, thing: str) -> bool:
    """Whether a body with a second stand-off for a hand that points down (`standoff_down`) takes this loose thing
    from above: all its grasps are from above, or it stands lower than the body's level hand works (`level_above`)."""
    if world.base.get("standoff_down") is None:
        return False
    grasps = _grasps(world, thing)
    if grasps and all(g.get("type", "top") == "top" for g in grasps):
        return True
    return world.ground(world.locate(thing)[0]) < float(world.base.get("level_above", 0.0))


def _taken_at(world, thing: str, here) -> np.ndarray:
    """Where a hand takes a loose thing (x, y): of its grasps of the kind the hand will use (`_from_above`; any, if it
    has none of that kind) the one nearest to where the base is; the thing's own middle if it names no grasp with a
    place of its own. A pan is taken by its handle, a hand's breadth from its middle."""
    pose = world.locate(thing)
    kind = "top" if _from_above(world, thing) else "side"
    grasps = [g for g in _grasps(world, thing) if "pos" in g]
    grasps = [g for g in grasps if g.get("type", "top") == kind] or grasps
    if not grasps:
        return pose[0][:2].copy()
    at = [tf.compose(pose, (np.asarray(g["pos"], dtype=np.float64), np.array([1.0, 0.0, 0.0, 0.0])))[0][:2] for g in grasps]
    return min(at, key=lambda p: float(np.linalg.norm(p - np.asarray(here, dtype=np.float64)[:2])))


def hits(world, pose, clearance: float = 0.0, ignore=()) -> tuple[str, str] | None:
    """Would the robot, with its base at `pose` (x, y, yaw) and its arm as it is, be inside something, or nearer to it
    than `clearance`? Returns (who, what) or None; `who` is `robot` or the name of what a hand holds. The floor and
    what lies flat on it do not count. Computed on scratch data."""
    m = world.model
    d = world.__dict__.get("_base_scratch")
    if d is None:
        d = world.__dict__["_base_scratch"] = mujoco.MjData(m)
    d.qpos[:] = world.data.qpos
    d.mocap_pos[:], d.mocap_quat[:] = world.data.mocap_pos, world.data.mocap_quat
    d.eq_active[:] = world.data.eq_active
    load = _load(world)
    rel = {}
    if load:
        mujoco.mj_kinematics(m, d)                  # the arm does not move here: what a hand holds keeps its place on the base
        base = (d.xpos[world._base_body].copy(), d.xquat[world._base_body].copy())
        for name in load:
            b = world.objects[name]["body_id"]
            rel[name] = tf.compose(tf.inverse(base), (d.xpos[b].copy(), d.xquat[b].copy()))
    d.qpos[world._base_qadr] = np.asarray(pose, dtype=np.float64)
    mujoco.mj_kinematics(m, d)
    if load:
        base = (d.xpos[world._base_body].copy(), d.xquat[world._base_body].copy())
        for name in load:
            adr = int(m.jnt_qposadr[m.body_jntadr[world.objects[name]["body_id"]]])
            pos, quat = tf.compose(base, rel[name])
            d.qpos[adr:adr + 3], d.qpos[adr + 3:adr + 7] = pos, quat
        mujoco.mj_kinematics(m, d)
    flags, margin = int(m.opt.enableflags), float(m.opt.o_margin)
    if clearance > 0.0:
        m.opt.enableflags = flags | int(mujoco.mjtEnableBit.mjENBL_OVERRIDE)
        m.opt.o_margin = clearance
    try:
        mujoco.mj_collision(m, d)
    finally:
        m.opt.enableflags, m.opt.o_margin = flags, margin
    moving = {"robot", *load}
    for i in range(d.ncon):
        c = d.contact[i]
        if c.dist > clearance or (clearance == 0.0 and c.dist > -5e-4):
            continue
        o = [world._geom_owner[int(g)] for g in (c.geom1, c.geom2)]
        if (o[0] in moving) == (o[1] in moving):
            continue
        k = 1 if o[0] in moving else 0
        if o[k] == "floor" or o[k] in ignore:
            continue
        if o[k] in world.objects and float(world.box(o[k])[1][2]) < FLAT + 0.01:
            continue
        return (o[1 - k], o[k])
    return None


# ---- the floor as a grid --------------------------------------------------------------------------------------------------
class Floor:
    """The floor as cells of `GRID`: `solid[i, j]` is true where something stands (cell (i, j) has its middle at
    `origin + (i, j) * GRID`); `owner[i, j]` says what (an index into `names`, -1: nothing)."""

    def __init__(self, world, ignore=()):
        self.world = world
        m, s = world.model, world._sync()
        top = float(world.base["height"])
        shapes = []                                 # (name, corner points on the floor)
        for g in range(m.ngeom):
            owner = world._geom_owner[g]
            if owner in ("robot", "floor") or owner in ignore or int(m.geom_group[g]) > 3 or m.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE:
                continue
            rot = s.geom_xmat[g].reshape(3, 3)
            c, h = m.geom_aabb[g, :3], m.geom_aabb[g, 3:]
            pts = s.geom_xpos[g] + np.array([c + h * np.array([sx, sy, sz]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) @ rot.T
            if float(pts[:, 2].max()) < FLAT or float(pts[:, 2].min()) > top:
                continue                            # under the base's way, or over the robot's head
            shapes.append((owner, pts[:, :2]))
        every = np.vstack([p for _, p in shapes] + [world.base_pose()[None, :2]])
        lo, hi = every.min(axis=0) - 1.0, every.max(axis=0) + 1.0
        self.origin = np.floor(lo / GRID) * GRID
        self.shape = tuple(int(v) for v in np.ceil((hi - self.origin) / GRID).astype(int) + 1)
        self.names: list[str] = []
        self.owner = np.full(self.shape, -1, dtype=np.int32)
        for name, pts in shapes:
            if name not in self.names:
                self.names.append(name)
            self._fill(_hull(pts), self.names.index(name))
        self.solid = self.owner >= 0
        self._static = np.array([n == "wall" or (n in world.objects and world.objects[n]["fixed"] and not world.objects[n].get("mocap"))
                                 for n in self.names] + [False], dtype=bool)

    def _fill(self, poly: np.ndarray, k: int) -> None:
        lo = np.floor((poly.min(axis=0) - self.origin) / GRID).astype(int)
        hi = np.ceil((poly.max(axis=0) - self.origin) / GRID).astype(int)
        lo, hi = np.maximum(lo, 0), np.minimum(hi, np.array(self.shape) - 1)
        if np.any(hi < lo):
            return
        ii, jj = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1), indexing="ij")
        x, y = self.origin[0] + ii * GRID, self.origin[1] + jj * GRID
        inside = np.ones(ii.shape, dtype=bool)
        n = len(poly)
        for a in range(n):                          # a convex outline, anticlockwise: inside is left of every edge (half a cell of slack)
            p, q = poly[a], poly[(a + 1) % n]
            e = q - p
            length = float(np.hypot(*e))
            if length < 1e-9:
                continue
            inside &= ((e[0] * (y - p[1]) - e[1] * (x - p[0])) / length) >= -GRID * 0.5
        sub = self.owner[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]
        sub[inside & (sub < 0)] = k

    def cell(self, xy) -> tuple[int, int]:
        ij = np.round((np.asarray(xy, dtype=np.float64)[:2] - self.origin) / GRID).astype(int)
        return (int(min(max(ij[0], 0), self.shape[0] - 1)), int(min(max(ij[1], 0), self.shape[1] - 1)))

    def xy(self, ij) -> np.ndarray:
        return self.origin + np.asarray(ij, dtype=np.float64) * GRID

    def free(self, radius: float, static_only: bool = False) -> np.ndarray:
        """Cells where the middle of a robot that reaches `radius` from its vertical may be."""
        solid = self._static[self.owner] if static_only else self.solid
        return ~_grow(solid, radius)

    def nearest_thing(self, xy, movable_only: bool = True) -> str | None:
        """The (movable) thing nearest to a spot of the floor, by its cells."""
        best = None
        for k, name in enumerate(self.names):
            if movable_only and self._static[k]:
                continue
            ii, jj = np.nonzero(self.owner == k)
            if len(ii):
                dist = float(np.min(np.hypot(self.origin[0] + ii * GRID - xy[0], self.origin[1] + jj * GRID - xy[1])))
                if best is None or dist < best[0]:
                    best = (dist, name)
        return best[1] if best else None


def _hull(pts: np.ndarray) -> np.ndarray:
    """Convex hull of points in the plane, anticlockwise (Andrew's monotone chain)."""
    p = sorted({(round(float(x), 6), round(float(y), 6)) for x, y in pts})
    if len(p) <= 2:
        return np.array(p + p[:1] * (3 - len(p)), dtype=np.float64)

    def half(seq):
        out: list = []
        for q in seq:
            while len(out) >= 2 and (out[-1][0] - out[-2][0]) * (q[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (q[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(q)
        return out[:-1]

    return np.array(half(p) + half(p[::-1]), dtype=np.float64)


def _grow(mask: np.ndarray, radius: float) -> np.ndarray:
    """Every cell within `radius` of a true cell."""
    n = int(math.ceil(radius / GRID))
    out = mask.copy()
    padded = np.pad(mask, n)
    a, b = mask.shape
    for di in range(-n, n + 1):
        for dj in range(-n, n + 1):
            if (di or dj) and math.hypot(di, dj) * GRID <= radius + 1e-9:
                out |= padded[n + di:n + di + a, n + dj:n + dj + b]
    return out


def _reachable(free: np.ndarray, start: tuple[int, int]) -> np.ndarray:
    """The free cells joined to `start` (itself included, free or not)."""
    reach = np.zeros_like(free)
    reach[start] = True
    while True:
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= free
        grown[start] = True
        if np.array_equal(grown, reach):
            return reach
        reach = grown


_STEPS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, math.sqrt(2.0)), (1, -1, math.sqrt(2.0)), (-1, 1, math.sqrt(2.0)), (-1, -1, math.sqrt(2.0))]


def _astar(free: np.ndarray, roomy: np.ndarray, start, goal) -> list | None:
    """The cheapest way over free cells from `start` to `goal`, cells that are not roomy costing three times as much."""
    if not free[goal]:
        return None
    a, b = free.shape
    best = {start: 0.0}
    came: dict = {}
    heap = [(math.hypot(goal[0] - start[0], goal[1] - start[1]), 0.0, start)]
    while heap:
        _, cost, cur = heapq.heappop(heap)
        if cur == goal:
            out = [cur]
            while out[-1] in came:
                out.append(came[out[-1]])
            return out[::-1]
        if cost > best.get(cur, math.inf):
            continue
        for di, dj, step in _STEPS:
            nxt = (cur[0] + di, cur[1] + dj)
            if not (0 <= nxt[0] < a and 0 <= nxt[1] < b) or not free[nxt]:
                continue
            if di and dj and not (free[cur[0] + di, cur[1]] and free[cur[0], cur[1] + dj]):
                continue                            # no cutting a corner
            c = cost + step * (1.0 if roomy[nxt] else 3.0)
            if c < best.get(nxt, math.inf) - 1e-12:
                best[nxt], came[nxt] = c, cur
                heapq.heappush(heap, (c + math.hypot(goal[0] - nxt[0], goal[1] - nxt[1]), c, nxt))
    return None


def _clear_line(free: np.ndarray, a, b) -> bool:
    n = max(int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) * 2.0)), 1)
    for k in range(n + 1):
        i, j = int(round(a[0] + (b[0] - a[0]) * k / n)), int(round(a[1] + (b[1] - a[1]) * k / n))
        if not free[i, j]:
            return False
    return True


def _straighten(cells: list, free: np.ndarray, roomy: np.ndarray) -> list:
    """Leave out the cells a straight line can skip: over roomy cells where the way was roomy, over free ones otherwise."""
    corners = [cells[0]]                            # only where the way changes direction, and its end
    for k in range(1, len(cells) - 1):
        if (cells[k][0] - cells[k - 1][0], cells[k][1] - cells[k - 1][1]) != (cells[k + 1][0] - cells[k][0], cells[k + 1][1] - cells[k][1]):
            corners.append(cells[k])
    if len(cells) > 1:
        corners.append(cells[-1])
    full, cells = cells, corners
    index = {c: k for k, c in enumerate(full)}
    out, i = [cells[0]], 0
    while i < len(cells) - 1:
        j = len(cells) - 1
        while j > i + 1:
            tight = not all(roomy[c] for c in full[index[cells[i]]:index[cells[j]] + 1])
            if _clear_line(free if tight else roomy, cells[i], cells[j]):
                break
            j -= 1
        out.append(cells[j])
        i = j
    return out


# ---- where to stand and how to get there ---------------------------------------------------------------------------------
def kind_of(world, hit: dict) -> str:
    """What the base is sent to: `floor` (a spot of the floor, or of something flat that lies on it), `figure` (a
    person, a child, an animal) or `thing` (furniture, a wall, something that stands somewhere)."""
    obj = hit["object"]
    if obj == "floor":
        return "floor"
    if obj in world.objects:
        if any(t in world.objects[obj]["meta"].get("tags", ()) for t in FIGURE_TAGS):
            return "figure"
        if world.objects[obj]["fixed"] and not world.objects[obj].get("mocap") and (float(world.box(obj)[1][2]) < FLAT or float(hit["point"][2]) < FLAT):
            return "floor"                          # a rug, a mat, a cord: part of the floor (a loose thing never is)
    return "thing"


def plan(world, hit: dict, radius: float | None = None) -> tuple[dict | None, str]:
    """The way of the base to the spot shown by `hit` (`{"object", "point"}`): (plan, "ok") or (None, why). The plan:
    `points` (the way, from where the base is; one point when it need not move), `length`, `face` (the spot to face at
    the end, or None), `dock` (whether to close up to what stands there), `kind`."""
    point = np.asarray(hit["point"], dtype=np.float64)
    kind = kind_of(world, hit)
    if kind == "thing" and world.base.get("hand_offset") and hit.get("object") in world.objects and not world.objects[hit["object"]]["fixed"]:
        # a body that has to stand before a loose thing to the centimetre (its hands work a little to one side of its
        # middle) aims at where a hand takes the thing, not at the part of it the pixel showed
        point = np.array([*_taken_at(world, hit["object"], world.base_pose()[:2]), point[2]])
    load = _load(world)
    floor = Floor(world, ignore=load)
    reach = (extent(world) if radius is None else float(radius)) + MARGIN
    free = floor.free(reach)
    roomy = floor.free(reach + ROOMY)
    here = world.base_pose()[:2]
    start = floor.cell(here)
    points = [here.copy()]
    escape = not free[start]
    if escape:
        # standing closer to something than a planned way would pass it (closed up to a counter): straight out to the
        # nearest free cell whose line is clear of everything, the base not turning
        out = _way_out(world, floor, free, here)
        if out is None:
            return None, "no_way"
        points.append(floor.xy(out))
        start = out
    joined = _reachable(free, start)
    ii, jj = np.nonzero(joined)
    xs, ys = floor.origin[0] + ii * GRID, floor.origin[1] + jj * GRID
    dist = np.hypot(xs - point[0], ys - point[1])
    ok = np.ones(len(ii), dtype=bool)
    if kind == "figure":
        lo, hi = world.box(hit["object"])
        gap = np.hypot(np.maximum(np.maximum(lo[0] - xs, xs - hi[0]), 0.0), np.maximum(np.maximum(lo[1] - ys, ys - hi[1]), 0.0))
        ok = gap >= standoff(world, "figure_standoff") - 1e-9
    limit = 0.50 if kind == "floor" else NEAR_GOAL + (standoff(world, "figure_standoff") if kind == "figure" else 0.0)
    ok &= dist <= limit
    if not np.any(ok):
        # no place to stand within reach of the spot. If there would be one with the movable things away, one of them
        # is in the way; else there is no way at all.
        static = _reachable(floor.free(reach, static_only=True), start)
        si, sj = np.nonzero(static)
        sd = np.hypot(floor.origin[0] + si * GRID - point[0], floor.origin[1] + sj * GRID - point[1])
        if len(si) and float(sd.min()) <= limit:
            by = floor.nearest_thing(point[:2] if kind == "floor" else floor.xy((si[int(np.argmin(sd))], sj[int(np.argmin(sd))])))
            if by is not None:
                return None, "blocked_by_" + by
        return None, "no_way"
    k = int(np.argmin(np.where(ok, dist + 1e-6 * (np.abs(xs - here[0]) + np.abs(ys - here[1])), np.inf)))
    near = working_distance(world, hit.get("object"))
    if kind == "thing" and float(dist[k]) < near:
        # nearer than the arm works well: stand back from the spot, in the free cell nearest to the place at that
        # distance along the same line (square to the edge of what the thing lies on); a thing with free floor all
        # round it (something small on the floor) is approached from the side the base comes from
        line = (np.array([xs[k], ys[k]]) - point[:2]) if float(dist[k]) > 0.12 else (here - point[:2])
        if float(np.linalg.norm(line)) < 1e-6:
            line = np.array([-math.cos(world.base_pose()[2]), -math.sin(world.base_pose()[2])])
        back = point[:2] + line * (near / float(np.linalg.norm(line)))
        k = int(np.argmin(np.where(ok, np.hypot(xs - back[0], ys - back[1]), np.inf)))
    if kind == "thing" and world.base.get("close_up"):
        # A body that works only closed up to the furniture (`RobotSpec.base["close_up"]`): of the free cells about
        # as near as that one, the cell from which a straight run at the spot brings its middle nearest to it. (The
        # nearest free cell to a thing by the end of a counter lies off its corner, and a wide body that runs at the
        # thing from there is stopped by the corner a long way short.)
        around = np.flatnonzero(ok & (np.hypot(xs - xs[k], ys - ys[k]) <= 0.30 + 1e-9))
        around = around[np.argsort(dist[around], kind="stable")][:16]
        runs = [(round(_run_at(world, (xs[c], ys[c]), point[:2], near), 2), float(dist[c]), int(c)) for c in around]
        k = min(runs)[2]
    goal = (int(ii[k]), int(jj[k]))
    if goal != start:
        cells = _astar(free, roomy, start, goal)
        if cells is None:
            return None, "no_way"
        cells = _straighten(cells, free, roomy)
        points += [floor.xy(c) for c in cells[1:]]
        if kind == "floor" and float(dist[k]) < GRID:      # the spot itself, not the middle of its cell
            points[-1] = point[:2].copy()
    length = float(sum(np.linalg.norm(b - a) for a, b in zip(points, points[1:])))
    return {"points": points, "length": length, "face": None if kind == "floor" else point[:2].copy(), "dock": kind == "thing",
            "kind": kind, "radius": reach - MARGIN, "escape": escape, "thing": hit.get("object")}, "ok"


def _run_at(world, xy, spot, near: float) -> float:
    """How far from `spot` the base's middle would stop if it stood at `xy`, faced the spot and closed up to it as
    `_dock` does (to `near`, or until its shapes are the body's `dock_gap` from something)."""
    xy, spot = np.asarray(xy, dtype=np.float64), np.asarray(spot, dtype=np.float64)
    d = float(np.linalg.norm(spot - xy))
    if d < 1e-6:
        return 0.0
    ahead = (spot - xy) / d
    yaw = math.atan2(ahead[1], ahead[0])
    gap, step, run = standoff(world, "dock_gap"), 0.02, 0.0
    while d - run - step >= near - 1e-9 and hits(world, [*(xy + ahead * (run + step)), yaw], clearance=gap) is None:
        run += step
    return d - run


def _way_out(world, floor: Floor, free: np.ndarray, here) -> tuple[int, int] | None:
    pose = world.base_pose()
    ii, jj = np.nonzero(free)
    d = np.hypot(floor.origin[0] + ii * GRID - here[0], floor.origin[1] + jj * GRID - here[1])
    for k in np.argsort(d)[:60]:
        if d[k] > 0.8:
            break
        to = floor.xy((ii[k], jj[k]))
        n = max(int(math.ceil(float(d[k]) / 0.03)), 1)
        if all(hits(world, [*(here + (to - here) * s / n), pose[2]]) is None for s in range(1, n + 1)):
            return (int(ii[k]), int(jj[k]))
    return None


# ---- rows -------------------------------------------------------------------------------------------------------------
def _wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _row(world, base) -> np.ndarray:
    return np.concatenate([np.asarray(base, dtype=np.float64), world.target[world._nb:]])


def _stop(world, seconds: float = 0.3):
    """Stand where the base is now."""
    here = world.base_pose()
    for _ in range(max(int(round(seconds / CONTROL_DT)), 1)):
        yield _row(world, here)


def _settle(world, goal, timeout: float = 1.0):
    for _ in range(max(int(round(timeout / CONTROL_DT)), 2)):
        yield _row(world, goal)
        err = world.base_pose() - goal
        if float(np.hypot(err[0], err[1])) < 2e-3 and abs(float(err[2])) < 4e-3 and float(np.max(np.abs(world.base_vel()))) < 5e-3:
            return True
    return False


def _met(world) -> str | None:
    """What the robot or its load touches now (a force between them), the floor aside."""
    load = {"robot", *_load(world)}
    for c in world.privileged()["contacts"]:
        if c["force"] > 1.0 and (c["a"] in load) != (c["b"] in load):
            other = c["b"] if c["a"] in load else c["a"]
            if other != "floor":
                return other
    return None


def drive(world, goal, *, speed: float = 1.0, watch=None):
    """Take the base on a straight line (in x, y and yaw together) from where its targets are to `goal` (x, y, yaw),
    with the base's limits scaled by `speed`. Returns a Status: `ok`; `not_reached` (it fell behind its target: it
    has met something, `info["by"]`; it stands where it stopped); `stopped` (`watch` said so)."""
    b = world.base
    q0 = world.target[:world._nb].copy()
    pose = world.base_pose()
    if float(np.hypot(*(pose[:2] - q0[:2]))) > 0.005 or abs(float(pose[2] - q0[2])) > 0.01:
        q0 = pose                               # pushed off its targets (something has just shoved it): from where it is
    goal = np.asarray(goal, dtype=np.float64)
    goal = np.array([goal[0], goal[1], q0[2] + _wrap(goal[2] - q0[2])])
    dist, ang = float(np.hypot(goal[0] - q0[0], goal[1] - q0[1])), abs(float(goal[2] - q0[2]))
    if dist < 1e-4 and ang < 1e-4:
        return Status(True, "ok", {"moved_m": 0.0})
    v, a = float(b["vel_limits"][0]) * speed, float(b["acc_limits"][0]) * speed
    wv, wa = float(b["vel_limits"][2]) * speed, float(b["acc_limits"][2]) * speed
    # one profile for the line; its rate and acceleration are limited by the slower of the way and the turn
    rate = min(v / dist if dist > 1e-9 else math.inf, wv / ang if ang > 1e-9 else math.inf)
    accel = min(a / dist if dist > 1e-9 else math.inf, wa / ang if ang > 1e-9 else math.inf)
    duration, ramp = _profile_times(rate, accel)
    n = max(int(math.ceil(duration / CONTROL_DT)), 1)
    lead = np.asarray(b["lead"], dtype=np.float64)
    start = world.base_pose()[:2].copy()
    for k in range(1, n + 1):
        s, ds = trapezoid(duration, ramp, k * CONTROL_DT)
        want = q0 + (goal - q0) * s
        yield _row(world, want + lead * (goal - q0) * ds)
        err = world.base_pose() - want
        why = watch(world) if watch is not None else None
        if why is not None:
            yield from _stop(world)
            return Status(False, "stopped", {"why": why, "moved_m": float(np.linalg.norm(world.base_pose()[:2] - start))})
        if float(np.hypot(err[0], err[1])) > LAG_STOP[0] or abs(float(err[2])) > LAG_STOP[1]:
            by = _met(world)
            yield from _stop(world)
            return Status(False, "not_reached", {"by": by, "moved_m": float(np.linalg.norm(world.base_pose()[:2] - start))})
    ok = yield from _settle(world, goal)
    moved = float(np.linalg.norm(world.base_pose()[:2] - start))
    if not ok:
        by = _met(world)
        yield from _stop(world)
        return Status(False, "not_reached", {"by": by, "moved_m": moved})
    return Status(True, "ok", {"moved_m": moved})


def _sweep_free(world, yaw0: float, yaw1: float) -> tuple[str, str] | None:
    """What the robot would touch turning on the spot from yaw0 to yaw1 (tested every 5 degrees)."""
    return _sweep_free_at(world, world.base_pose()[:2], yaw0, yaw1)


def _sweep_free_at(world, xy, yaw0: float, yaw1: float) -> tuple[str, str] | None:
    """The same with the base's middle at `xy`."""
    x, y = float(xy[0]), float(xy[1])
    n = max(int(math.ceil(abs(yaw1 - yaw0) / math.radians(5.0))), 1)
    at_start = hits(world, [x, y, yaw0])
    for k in range(1, n + 1):
        hit = hits(world, [x, y, yaw0 + (yaw1 - yaw0) * k / n], ignore=(at_start[1],) if at_start else ())
        if hit is not None:
            return hit
    return None


def turn_to(world, yaw: float, *, speed: float = 1.0, watch=None):
    """Turn the base on the spot to face `yaw`, the shorter way round; the other way round when the robot or what it
    holds would touch something on the shorter one. Reasons: `blocked_by_<thing>` (not moved), those of `drive`."""
    here = world.target[:world._nb].copy()
    delta = _wrap(float(yaw) - float(here[2]))
    if abs(delta) < math.radians(0.5):
        return Status(True, "ok", {"turned_deg": 0.0})
    hit = None
    for d in (delta, delta - math.copysign(2.0 * math.pi, delta)):
        hit = _sweep_free(world, float(here[2]), float(here[2]) + d)
        if hit is None:
            st = yield from drive(world, [here[0], here[1], here[2] + d], speed=speed, watch=watch)
            st.info["turned_deg"] = math.degrees(d)
            return st
    return Status(False, "blocked_by_" + hit[1], {"who": hit[0]})


def _whole(arm, gen):
    """The rows of one arm's skill as rows of the whole robot: for an arm other than the one whose rows the caller
    applies (the rest of the robot keeps its targets)."""
    try:
        row = next(gen)
        while True:
            yield arm.whole(row)
            row = next(gen)
    except StopIteration as stop:
        return stop.value


def tuck(arm):
    """Bring the arm over the base before the base moves: to its rest posture, or, with something in the hand, the hand
    to a place over the base's front with the tool as it is (`RobotSpec.base["carry"]`; what is held stays level).
    When no such place can be reached the arm stays as it is and the way is planned for the room it takes. A robot
    with several arms brings in every one of them, the arm it was given first."""
    world = arm.world
    first = yield from _tuck(arm)
    for name in world.arm_names:
        if name != arm.name:
            st = yield from _whole(world.arm(name), _tuck(world.arm(name)))
            if not st.info.get("tucked"):
                first.info.update({"tucked": False, "why": st.info.get("why")})
    return first


def _tuck(arm):
    world = arm.world
    if not S.holding(arm):
        st = yield from A.home(arm)
        return Status(True, "ok", {"tucked": st.ok, "why": st.reason})
    x, y, yaw = world.base_pose()
    ahead = np.array([math.cos(yaw), math.sin(yaw)])
    tcp = arm.tcp_pose()[0]
    below = A._load(arm)[1]
    why = "ik_unreachable"
    places = []
    for place in world.base["carry"]:
        fwd, height = float(place[0]), float(place[1])
        z = max(float(height), 0.36 + float(world.base["clearance"]) + below)     # the load's underside clear of the base's top
        at = np.array([x + ahead[0] * fwd, y + ahead[1] * fwd, z])
        if len(place) > 2:                          # and to the arm's own side (arms that hang beside the body)
            side = float(place[2]) * float(getattr(arm, "side", 1.0))
            at[:2] += side * np.array([-ahead[1], ahead[0]])
        places.append(at)
    if any(float(np.linalg.norm(goal - tcp)) < 0.03 for goal in places):          # it is at one of them already
        return Status(True, "ok", {"tucked": True})
    for goal in places:
        legs, z_or_why = A._plan_transfer(arm, goal)
        if legs is None:
            why = z_or_why[0]
            continue
        st = yield from A._run_legs(arm, legs)
        return Status(True, "ok", {"tucked": st.ok, "why": st.reason})
    return Status(True, "ok", {"tucked": False, "why": why})


def turn(arm, deg: float, *, speed: float = 1.0, watch=None):
    """What the tool `turn` does: the arm over the base, then the base turned on the spot by `deg` (anticlockwise seen
    from above, so to the robot's left; the way round that was asked for, or not at all)."""
    world = arm.world
    yield from tuck(arm)
    here = world.target[:world._nb].copy()
    d = math.radians(float(deg))
    hit = _sweep_free(world, float(here[2]), float(here[2]) + d)
    backed = 0.0
    if hit is not None:
        # No room to turn here (the base has closed up to a counter, or holds something out ahead): it backs
        # straight away from what it faces, as far as it has to and at most `BACK_OFF`, and turns there. Without
        # this a robot that sees only what is ahead of it could not get away from a counter it stands at.
        back = np.array([-math.cos(here[2]), -math.sin(here[2])])
        step, found = 0.05, None
        while backed + step <= BACK_OFF + 1e-9:
            at = here[:2] + back * (backed + step)
            if hits(world, [at[0], at[1], here[2]], ignore=(hit[1],) if backed < 0.10 else ()) is not None:
                break
            backed += step
            if _sweep_free_at(world, at, float(here[2]), float(here[2]) + d) is None:
                found = at
                break
        if found is None:
            return Status(False, "blocked_by_" + hit[1], {"who": hit[0]})
        st = yield from drive(world, [found[0], found[1], here[2]], speed=min(speed, 0.5), watch=watch)
        if not st.ok:
            return st
        here = world.target[:world._nb].copy()
    st = yield from drive(world, [here[0], here[1], here[2] + d], speed=speed, watch=watch)
    st.info["turned_deg"] = math.degrees(float(world.base_pose()[2] - here[2]))
    st.info["backed_m"] = round(backed, 2)
    return st


def go(arm, hit: dict, *, speed: float = 1.0, leg: float = LEG, watch=None):
    """What the tool `go` does: drive the base to a place before the spot `hit` shows (`plan`), at most `leg` metres of
    the way in one call. Returns a Status whose `info` has `arrived`, `remaining_m` and `moved_m`. Reasons: `no_way`,
    `blocked_by_<thing>` (nothing moved but the arm), `not_reached` (it met something on the way and stands there)."""
    world = arm.world
    yield from tuck(arm)
    p, why = plan(world, hit)
    if p is None:
        return Status(False, why, {"arrived": False})
    points, total = p["points"], p["length"]
    info = {"arrived": False, "remaining_m": round(total, 2), "moved_m": 0.0, "kind": p["kind"]}
    start = world.base_pose()[:2].copy()
    left, done = float(leg), 0.0
    for i, (a, b) in enumerate(zip(points, points[1:])):
        seg = float(np.linalg.norm(b - a))
        if seg < 1e-6:
            continue
        if left <= 1e-6:
            break
        part = min(seg, left)
        to = a + (b - a) * (part / seg)
        heading = math.atan2(b[1] - a[1], b[0] - a[0])
        yaw = float(world.target[2])
        # the base faces the way it drives (its head camera looks ahead), except on a short sidestep and on the way
        # out from something it stands close to
        if part >= 0.30 and not (i == 0 and p["escape"]):
            st = yield from turn_to(world, heading, speed=speed, watch=watch)
            if st.ok:
                yaw = heading
            elif st.reason in ("not_reached", "stopped"):
                return Status(False, st.reason, {**info, **st.info, "moved_m": round(float(np.linalg.norm(world.base_pose()[:2] - start)), 2)})
        n = max(int(math.ceil(part / 0.05)), 1)     # the base's own outline along the leg, as free moves of the arm are tested
        for k in range(1, n + 1):
            block = hits(world, [*(a + (to - a) * k / n), yaw]) if not (i == 0 and p["escape"]) else None
            if block is not None:
                return Status(False, "blocked_by_" + block[1], {**info, "moved_m": round(float(np.linalg.norm(world.base_pose()[:2] - start)), 2)})
        st = yield from drive(world, [to[0], to[1], yaw], speed=speed, watch=watch)
        done += part if st.ok else float(st.info.get("moved_m", 0.0))
        left -= part
        if not st.ok:
            return Status(False, st.reason, {**info, **st.info, "remaining_m": round(max(total - done, 0.0), 2),
                                             "moved_m": round(float(np.linalg.norm(world.base_pose()[:2] - start)), 2)})
    remaining = max(total - done, 0.0)
    info.update({"remaining_m": round(remaining, 2), "moved_m": round(float(np.linalg.norm(world.base_pose()[:2] - start)), 2)})
    if remaining > 0.02:
        return Status(True, "ok", info)
    if p["face"] is not None:
        here = world.base_pose()
        d = p["face"] - here[:2]
        if float(np.linalg.norm(d)) > 0.05:
            st = yield from turn_to(world, math.atan2(d[1], d[0]), speed=speed, watch=watch)
            if not st.ok and st.reason in ("not_reached", "stopped"):
                return Status(False, st.reason, {**info, **st.info})
        if p["dock"]:
            st = yield from _dock(world, p["face"], thing=p["thing"], speed=speed, watch=watch)
            if st.ok and world.base.get("hand_offset"):
                st = yield from _sidestep(world, p["thing"], speed=speed, watch=watch)
            if not st.ok:
                return Status(False, st.reason, {**info, **st.info})
    info["arrived"] = True
    info["remaining_m"] = 0.0
    info["moved_m"] = round(float(np.linalg.norm(world.base_pose()[:2] - start)), 2)
    return Status(True, "ok", info)


def _working_hand(world, thing: str | None) -> str | None:
    """The one hand that is about to work at the spot the base was sent to, where that can be told: sent to a loose
    thing, the free hand of a robot that holds something in its other hand, or, with both hands free, the hand the
    body works with by choice (`RobotSpec.base["hand"]`); else the one hand that holds something (it has come to put
    it down). None: either hand may."""
    full = [a for a, n in world.held_by.items() if n]
    free = [a for a, n in world.held_by.items() if not n]
    loose = thing in world.objects and not world.objects[thing]["fixed"] and thing not in world.held_by.values()
    if loose:
        return free[0] if len(free) == 1 else (world.base.get("hand") if len(free) > 1 else None)
    return full[0] if len(full) == 1 else None


def _sidestep(world, thing: str | None, *, speed: float = 1.0, watch=None):
    """A body whose hands work beside its middle, not before it (`RobotSpec.base["hand_offset"]`): once it has closed
    up, it steps that far sideways, so that the spot is before the hand that is about to work there (`_working_hand`).
    It stays where it is when that hand cannot be told or the step is not free."""
    hand = _working_hand(world, thing) if world.arm_names else None
    if hand is None:
        return Status(True, "ok", {"sidestep_m": 0.0})
    x, y, yaw = world.base_pose()
    step = -float(world.arm(hand).side) * float(world.base["hand_offset"])       # to the left hand's spot the body steps right
    left = np.array([-math.sin(yaw), math.cos(yaw)])
    n = max(int(math.ceil(abs(step) / 0.01)), 1)
    for k in range(1, n + 1):
        at = np.array([x, y]) + left * (step * k / n)
        if hits(world, [at[0], at[1], yaw], clearance=0.5 * standoff(world, "dock_gap")) is not None:
            return Status(True, "ok", {"sidestep_m": 0.0})
    st = yield from drive(world, [x + left[0] * step, y + left[1] * step, yaw], speed=min(speed, 0.5), watch=watch)
    st.info["sidestep_m"] = step
    return st


def _dock(world, spot, *, thing: str | None = None, speed: float = 1.0, watch=None):
    """Close up to what stands at `spot` (`thing`, if it is one): straight ahead until the robot's outline is the
    body's `dock_gap` from something or its middle the working distance from the spot."""
    x, y, yaw = world.base_pose()
    ahead = np.array([math.cos(yaw), math.sin(yaw)])
    far = float((np.asarray(spot, dtype=np.float64) - np.array([x, y])) @ ahead) - working_distance(world, thing)
    step, d = 0.01, 0.0
    while d + step <= far + 1e-9 and hits(world, [x + ahead[0] * (d + step), y + ahead[1] * (d + step), yaw], clearance=standoff(world, "dock_gap")) is None:
        d += step
    if d < 0.01:
        return Status(True, "ok", {"closed_up_m": 0.0})
    st = yield from drive(world, [x + ahead[0] * d, y + ahead[1] * d, yaw], speed=min(speed, 0.5), watch=watch)
    st.info["closed_up_m"] = d
    return st
