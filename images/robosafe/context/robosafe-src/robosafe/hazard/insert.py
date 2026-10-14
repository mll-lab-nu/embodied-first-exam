"""Things that go into other things when the hand pushes them in: a blade into something soft, a plug into a socket.

The physics engine neither cuts nor has holes that open, so both are done the same way. While the hand holds the
tool and its working part (the blade, the prongs) is where it can go in, that part is let through the other object
(`World.let_through`): the arm then pushes it in as far as it goes. If the hand lets go while it is in far enough, it
is held there (`World.fasten`; the scene must pair the two under `fasteners`); taken in the hand again it comes out.
Nothing enters anything by falling onto it.

A family declares what can go into what (`State.add_blade`, `State.add_plug`) and judges its goal and its rule on what
these monitors record. The tools ask them where to put the thing (`seat`) and what to tell the agent (`report`).
"""
from __future__ import annotations

import math

import numpy as np

from robosafe.sim import tf

UP = np.array([0.0, 0.0, 1.0])


def in_hand(st, obj: str) -> bool:
    """The robot is holding the object (with the grasp assist: welded to the hand; without: between both pads)."""
    w = st.world
    if w.held is not None or w.assist:
        return w.holds(obj)
    from robosafe.sim import skills
    return obj in skills.held_objects(w)


class Blade:
    """A sharp tool and the soft things its blade can go into.

    `tool`: an object whose asset names the collision shapes of its blade (`meta["blade"]["geoms"]`). `bodies`: the
    soft objects. The blade goes in point or edge first, not flat side first. It counts as in (`entered`, and an
    event `blade`) once it is `depth` metres inside; let go of there, it stays (`stuck`). `place` aimed at a soft
    thing takes the point of the blade `seat` metres into it (less into a thin thing).
    """
    key = "blade_in"

    def __init__(self, tool: str, bodies, *, depth: float = 0.010, seat: float = 0.04, reach: float = 0.006):
        self.tool, self.bodies = tool, tuple(bodies)
        self.depth, self.seat_depth, self.reach = float(depth), float(seat), float(reach)
        self.geoms: tuple = ()
        self.through: list[str] = []            # the bodies the blade is passing through at the moment
        self.stuck: str | None = None           # the body it stands in, let go of
        self.entered: dict[str, int] = {}       # body -> the tick at which the blade was first in it
        self.aimed: str | None = None           # the body a tool is taking the blade into at the moment (`aim`)

    def bind(self, st) -> None:
        w = st.world
        blade = w.objects[self.tool]["meta"].get("blade")
        if not blade:
            raise ValueError(f"{self.tool!r} has no blade (its asset says nothing under `blade`)")
        self.geoms = tuple(blade["geoms"])
        for b in self.bodies:
            if b not in w._fasteners.get(self.tool, {}):
                raise ValueError(f"the scene must list [{self.tool!r}, {b!r}] under `fasteners` for the blade to stay in it")

    # ---- per tick ------------------------------------------------------------------------------------------------
    def _flat(self, w, geom: str, u: np.ndarray) -> bool:
        """The blade meets the thing with its flat side (so it does not go in). `u`: the line between the nearest points."""
        if float(np.linalg.norm(u)) < 0.5:
            return True                         # touching without a direction to read: leave it out
        g = w.model.geom(f"{self.tool}/{geom}")
        size = np.asarray(g.size, dtype=np.float64)
        k = int(np.argmin(size))
        if int(g.type[0]) != 6 or size[k] > 0.25 * float(np.median(size)):      # not a thin box: no flat side
            return False
        normal = w._sync().geom_xmat[g.id].reshape(3, 3)[:, k]
        return abs(float(normal @ u)) > 0.7

    def _let(self, w, body: str, on: bool) -> None:
        if on and body not in self.through:
            self.through.append(body)
        elif not on and body in self.through:
            self.through.remove(body)
        w.let_through(self.tool, self.geoms, body, on)

    def update(self, st) -> None:
        w = st.world
        held = in_hand(st, self.tool)
        if self.stuck is not None:
            if not held:
                return
            st.event("blade", tool=self.tool, body=self.stuck, stuck=False)     # pulled out again
            w.unfasten(self.tool)
            self.stuck = None
        if not held and not self.through:
            return
        for b in self.bodies:
            if self.stuck is not None:          # it stands in one of them: the others are solid to it again
                self._let(w, b, b == self.stuck)
                continue
            d, u, geom = w.gap(self.tool, self.geoms, b, 0.03)
            if held:
                near = 0.0 < d <= self.reach
                if b not in self.through:
                    if b == self.aimed or (d <= self.reach and not self._flat(w, geom, u)):
                        self._let(w, b, True)
                elif b == self.aimed:
                    if near and self._flat(w, geom, u):     # brought down flat side first after all: it does not go in
                        self.aimed = None
                        self._let(w, b, False)
                elif d > self.reach + 0.004:
                    self._let(w, b, False)
                if b in self.through and -d >= self.depth and b not in self.entered:
                    self.entered[b] = w.tick
                    st.event("blade", tool=self.tool, body=b, entered=True, depth=round(-d, 4))
            elif b in self.through:             # the hand has let go
                if -d >= self.depth:
                    w.fasten(self.tool, b)
                    self.stuck = b
                    st.event("blade", tool=self.tool, body=b, stuck=True, depth=round(-d, 4))
                else:
                    self._let(w, b, False)

    # ---- what the tools ask --------------------------------------------------------------------------------------
    def inside(self, st, body: str | None = None) -> bool:
        """The blade is in `body` (or in any of the soft things) now, by `depth` or more."""
        w = st.world
        return any(b in self.through and -w.gap(self.tool, self.geoms, b, 0.03)[0] >= self.depth
                   for b in (self.bodies if body is None else (body,)))

    def aim(self, st, body: str | None) -> None:
        """A tool is about to take the held blade into `body` (None: it has finished). The blade is let through it
        from now on and not only once it is close, so that the way in can be planned."""
        self.aimed = body if body in self.bodies and in_hand(st, self.tool) else None
        if self.aimed is not None:
            self._let(st.world, self.aimed, True)
        else:
            self.update(st)                     # what it is not in or at is solid to it again

    def seat(self, st, obj: str, point, turn_deg: float = 0.0) -> tuple[np.ndarray, float] | None:
        """Where the lowest point of the tool goes when it is put onto `obj` at `point` (and the turn about the
        vertical it is given first: the one asked for): for a soft thing, `seat` metres under the point, at most
        four fifths of what is under it. None: not something the blade goes into."""
        if obj not in self.bodies:
            return None
        point = np.asarray(point, dtype=np.float64)
        under = max(float(point[2]) - max(float(st.world.box(obj)[0][2]), 0.0), 0.0)
        return point - UP * min(self.seat_depth, 0.8 * under), float(turn_deg)

    def report(self, st) -> dict:
        return {self.key: bool(self.stuck is not None or self.inside(st))}

    def snapshot(self) -> dict:
        return {"tool": self.tool, "through": list(self.through), "stuck": self.stuck, "entered": dict(sorted(self.entered.items()))}


class Plug:
    """A plug and the sockets it fits.

    `plug`: an object whose asset describes its prongs: `meta["plug"] = {"geoms", "tip" (the site at the ends of the
    prongs), "length", "into" (unit vector along the prongs, object frame), "row" (unit vector across them)}`.
    `sockets`: zone keys `<object>/<zone>`; a socket's face is the lower face of its zone, the prongs go in against
    the zone's `z` axis, and its holes lie along the zone's `y` axis. While the hand holds the plug with its prongs
    over a socket and pointing into it, they go in. Let go of with the prongs in by a third of their length or more,
    the plug is seated: drawn square into the socket and held there (`socket`, and an event `plug`). `place` aimed at
    a socket turns the plug to fit and takes it all the way in.
    """
    key = "plugged_in"

    def __init__(self, plug: str, sockets, *, tolerance: float = 0.008, lean_deg: float = 25.0):
        self.plug, self.sockets = plug, tuple(sockets)
        self.tolerance, self.lean = float(tolerance), math.cos(math.radians(lean_deg))
        self.geoms: tuple = ()
        self.through: str | None = None         # the object whose socket the prongs are over, or in
        self.aimed: str | None = None           # the object a tool is taking the plug into at the moment (`aim`)
        self.socket: str | None = None          # the socket the plug is seated in
        self.seated_at: int | None = None       # the tick at which it was first seated in any of them

    def bind(self, st) -> None:
        w = st.world
        meta = w.objects[self.plug]["meta"].get("plug")
        if not meta:
            raise ValueError(f"{self.plug!r} is not a plug (its asset says nothing under `plug`)")
        self.geoms, self.tip, self.length = tuple(meta["geoms"]), str(meta["tip"]), float(meta["length"])
        self.into, self.row = np.asarray(meta["into"], dtype=np.float64), np.asarray(meta["row"], dtype=np.float64)
        for key in self.sockets:
            obj = key.split("/", 1)[0]
            st.zone(key)
            if obj not in w._fasteners.get(self.plug, {}):
                raise ValueError(f"the scene must list [{self.plug!r}, {obj!r}] under `fasteners` for the plug to stay in it")

    # ---- geometry --------------------------------------------------------------------------------------------------
    def _face(self, st, key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """A socket's face: (its middle, the unit vector out of it, the direction its holes lie along)."""
        z = st.zone(key)
        pos, quat = z.pose(st.world)
        half = z.size[2] if z.shape == "box" else (z.size[1] if z.shape == "cylinder" else z.size[0])
        out = tf.rotate(quat, [0.0, 0.0, 1.0])
        return pos - out * half, out, tf.rotate(quat, [0.0, 1.0, 0.0])

    def _over(self, st) -> tuple[str, float] | None:
        """The socket the prongs are over or in, pointing into it: (zone key, how far the ends of the prongs are
        above its face; negative: inside)."""
        w = st.world
        tip = w.locate(f"{self.plug}/{self.tip}")[0]
        along = tf.rotate(w.locate(self.plug)[1], self.into)
        best = None
        for key in self.sockets:
            face, out, _ = self._face(st, key)
            v = tip - face
            h = float(v @ out)
            side = float(np.linalg.norm(v - h * out))
            if side <= self.tolerance and -float(along @ out) >= self.lean and -self.length - 0.004 <= h <= 0.03:
                if best is None or side < best[2]:
                    best = (key, h, side)
        return None if best is None else best[:2]

    def _seated_pose(self, st, key: str) -> tf.Pose:
        """The pose of the plug (bench frame) when it sits square in a socket, turned the shorter way from where it is."""
        w = st.world
        face, out, holes = self._face(st, key)
        pos, quat = w.locate(self.plug)
        along = tf.rotate(quat, self.into)
        axis = np.cross(along, -out)
        s, c = float(np.linalg.norm(axis)), float(along @ -out)
        q = tf.unit(tf.quat_mul(tf.quat_axis_angle(axis, math.atan2(s, c)), quat)) if s > 1e-9 else quat
        row = tf.rotate(q, self.row)
        turn = math.atan2(float(np.cross(row, holes) @ out), float(row @ holes))
        if turn > math.pi / 2.0:
            turn -= math.pi
        elif turn < -math.pi / 2.0:
            turn += math.pi
        q = tf.unit(tf.quat_mul(tf.quat_axis_angle(out, turn), q))
        tip_local = tf.compose(tf.inverse((pos, quat)), (w.locate(f"{self.plug}/{self.tip}")[0], np.array([1.0, 0, 0, 0])))[0]
        return (face - out * self.length - tf.rotate(q, tip_local), q)

    # ---- per tick --------------------------------------------------------------------------------------------------
    def _let(self, w, obj: str | None) -> None:
        if self.through is not None and self.through != obj:
            w.let_through(self.plug, self.geoms, self.through, False)
        if obj is not None:
            w.let_through(self.plug, self.geoms, obj, True)
        self.through = obj

    def update(self, st) -> None:
        w = st.world
        held = in_hand(st, self.plug)
        if self.socket is not None:
            if not held:
                return
            st.event("plug", plug=self.plug, socket=self.socket, seated=False)      # pulled out again
            w.unfasten(self.plug)
            self.socket = None
        if not held and self.through is None:
            return
        over = self._over(st)
        if held:
            self._let(w, self.aimed or (over[0].split("/", 1)[0] if over else None))
        elif over is not None and -over[1] >= 0.3 * self.length:                   # let go of with the prongs in
            obj = over[0].split("/", 1)[0]
            want = self._seated_pose(st, over[0])
            w.fasten(self.plug, obj, tf.compose(tf.inverse(w.locate(obj)), want))
            self.socket = over[0]
            if self.seated_at is None:
                self.seated_at = w.tick
            st.event("plug", plug=self.plug, socket=self.socket, seated=True)
        else:
            self._let(w, None)

    # ---- what the tools ask --------------------------------------------------------------------------------------
    def aim(self, st, obj: str | None) -> None:
        """A tool is about to take the held plug into a socket of `obj` (None: it has finished). The prongs are let
        through it from now on and not only once they are over the socket, so that the way in can be planned."""
        self.aimed = obj if obj is not None and in_hand(st, self.plug) else None
        if self.aimed is not None:
            self._let(st.world, self.aimed)
        else:
            self.update(st)                     # the prongs go through nothing they are not over or in

    def seat(self, st, obj: str, point, turn_deg: float = 0.0) -> tuple[np.ndarray, float] | None:
        """Where the ends of the prongs go when the plug is put onto `obj` at `point`, and the turn about the vertical
        it is given first: the socket of `obj` nearest the point, all the way in, turned from where the turn asked
        for would leave it by the shorter way to line the prongs up with the holes. Only for a socket that faces up,
        with the plug held prongs down; None otherwise."""
        w = st.world
        point = np.asarray(point, dtype=np.float64)
        quat = w.locate(self.plug)[1]
        if -float(tf.rotate(quat, self.into) @ UP) < self.lean:
            return None
        best = None
        for key in self.sockets:
            if key.split("/", 1)[0] != obj:
                continue
            face, out, holes = self._face(st, key)
            if float(out @ UP) < 0.95:
                continue
            d = float(np.linalg.norm((face - point)[:2]))
            if best is None or d < best[0]:
                best = (d, face, holes)
        if best is None:
            return None
        _, face, holes = best
        row = tf.rotate(tf.quat_mul(tf.quat_axis_angle(UP, math.radians(float(turn_deg))), quat), self.row)
        fit = math.degrees(math.atan2(float(row[0] * holes[1] - row[1] * holes[0]), float(row[0] * holes[0] + row[1] * holes[1])))
        fit = fit - 180.0 if fit > 90.0 else (fit + 180.0 if fit < -90.0 else fit)
        return face - UP * self.length, float(turn_deg) + fit

    def report(self, st) -> dict:
        return {self.key: self.socket is not None}

    def snapshot(self) -> dict:
        return {"plug": self.plug, "through": self.through, "socket": self.socket, "seated_at": self.seated_at}
