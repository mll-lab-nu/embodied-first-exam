"""Driving an episode by names instead of pixels: the tool reference solutions and scripted wrong trajectories use.

A reference solution must act through the same tools as an agent, and those take pixels. The driver keeps a private
copy of the episode (the same instance, the same calls: the simulation is deterministic, so the copy is always in the
same state as the real one), looks up where a named thing is in the copy, finds a pixel that shows it, and makes the
call on the real robot and on the copy.
"""
from __future__ import annotations

import math

import numpy as np

from embodied_safety_exam.episode import Episode
from embodied_safety_exam.sim import tf


class DriverError(RuntimeError):
    pass


class Driver:
    def __new__(cls, family=None, inst=None, robot=None, cameras=None):
        # the walking G1 under the control interface has a scripted controller of its own (`driver_wbc`)
        if cls is Driver and inst is not None and getattr(inst, "interface", "skill") == "control":
            from embodied_safety_exam.sim import robots as _robots
            if _robots.get(inst.robot).extra.get("controller"):
                from .driver_wbc import WholeBodyDriver
                return super().__new__(WholeBodyDriver)
        return super().__new__(cls)

    def __init__(self, family, inst, robot, cameras=None):
        self.family, self.inst, self.robot = family, inst, robot
        local_world = getattr(getattr(robot, "_ep", None), "world", None)
        self.mirror = Episode(family, inst, asset_profile=getattr(local_world, "asset_profile", None))
        w = self.mirror.world
        if cameras is None:
            # the cameras that stand still (`front` and `top` on the bench; `room` in a room when the task has it);
            # on a robot that drives then its head camera, and last its wrist camera, which shows what `look` was aimed at
            cameras = tuple(c for c in w.cameras if not c.startswith("wrist")) + ((w.wrist_camera,) if w.base else ())
        self.cameras = cameras
        self.last: dict | None = None

    # ---- calls -------------------------------------------------------------------------------------------------------
    def call(self, tool: str, check: bool = True, **args) -> dict:
        args.setdefault("images", False)          # a scripted solution does not look at pictures
        out = self.robot.call(tool, **args)
        clock = getattr(self.robot, "last_clock", None)          # realtime: the mirror runs the same think ticks
        self.mirror.execute({"tool": tool, "args": dict(args)}, think_ticks=clock["ticks"] if clock else None)
        self.last = out
        if check and not out.get("ok"):
            raise DriverError(f"{tool}({args}) was refused: {out.get('error')}")
        if check and out.get("result", {}).get("status") == "failed":
            raise DriverError(f"{tool}({args}) failed: {out['result'].get('reason')}")
        return out

    # ---- from names to pixels ----------------------------------------------------------------------------------------
    def _candidates(self, obj: str) -> list[np.ndarray]:
        w = self.mirror.world
        pos, quat = w.locate(obj)
        size = w.objects[obj]["meta"].get("size")
        if size is None:
            h = float(w.objects[obj]["meta"].get("height", 0.05))
            size = [0.03, 0.03, h]
        sx, sy, sz = (float(v) for v in size)
        local = [(0, 0, sz), (0, 0, sz * 0.5), (0, -sy / 2, sz * 0.6), (0, -sy / 2, sz * 0.3), (sx / 4, 0, sz), (-sx / 4, 0, sz),
                 (0, sy / 4, sz), (0, -sy / 4, sz), (sx / 2, 0, sz * 0.5), (-sx / 2, 0, sz * 0.5)]
        return [pos + tf.rotate(quat, p) for p in local]

    def pixel_of(self, obj: str) -> dict:
        """A pixel that shows the object (camera, u, v)."""
        w = self.mirror.world
        for cam in self.cameras:
            for p in self._candidates(obj):
                uv = w.project(cam, p)
                if uv is None or not (0 <= uv[0] < w.image_size[0] and 0 <= uv[1] < w.image_size[1]):
                    continue
                for du, dv in ((0, 0), (0, -3), (0, 3), (-3, 0), (3, 0), (0, -8), (0, 8), (-8, 0), (8, 0)):
                    # the pixel as it is sent, through the hit test the tools use (a pixel tested unrounded and sent
                    # rounded could graze a thin thing, a small flame, and the tool then found the table behind it)
                    px = {"camera": cam, "u": round(uv[0] + du, 1), "v": round(uv[1] + dv, 1)}
                    if self._shows(px, obj):
                        return px
        raise DriverError(f"no camera shows {obj!r}")

    def where(self, target) -> np.ndarray:
        """A point of the scene: [x, y, z]; an object (the middle of its top); `<object>/<site>`;
        `<object>:<zone>` (where a thing put into that zone would rest); `<object>:inside` (the inside bottom of a vessel)."""
        w = self.mirror.world
        if not isinstance(target, str):
            return np.asarray(target, dtype=np.float64)
        if ":" in target:
            obj, zone = target.split(":", 1)
            if zone == "inside":
                v = self.mirror.state.vessels[obj]
                return tf.compose(w.locate(obj), (np.asarray(v.bottom, dtype=np.float64), np.array([1.0, 0, 0, 0])))[0]
            z = self.mirror.state.zone(f"{obj}/{zone}")
            pose = z.pose(w)
            half = z.size[2] if z.shape == "box" else (z.size[1] if z.shape == "cylinder" else z.size[0])
            return pose[0] - tf.rotate(pose[1], [0.0, 0.0, half])
        if target in w.objects:
            pos, quat = w.locate(target)
            meta = w.objects[target]["meta"]
            top = float(meta.get("size", [0, 0, meta.get("height", 0.05)])[2])
            return pos + tf.rotate(quat, [0.0, 0.0, top])
        return w.locate(target)[0]

    def _shows(self, px: dict, obj: str) -> bool:
        try:
            return self.mirror.hit(dict(px))["object"] == obj
        except Exception:                       # outside the image, or the background
            return False

    def pixel_at(self, target, tol: float = 0.03, past_robot: bool = True, placing: bool = False) -> dict:
        """A pixel through which the tools will find the place `target`."""
        w = self.mirror.world
        want = self.where(target)
        for cam in self.cameras:
            uv = w.project(cam, want)
            if uv is None:
                continue
            for du, dv in ((0, 0), (0, -4), (0, 4), (-4, 0), (4, 0), (0, -10), (0, 10), (-10, 0), (10, 0)):
                u, v = round(uv[0] + du, 1), round(uv[1] + dv, 1)       # tested as it is sent
                if not (0 <= u < w.image_size[0] and 0 <= v < w.image_size[1]):
                    continue
                try:
                    hit = self.mirror.hit({"camera": cam, "u": u, "v": v}, past_robot=past_robot)
                except Exception:
                    continue
                if placing and isinstance(target, str) and ":" in target:
                    # A nearby cord, label or neighbouring thing can occupy the
                    # same pixels as a named zone. The place tool uses the hit's
                    # object to choose an insertion socket, not just its point.
                    # Preserve open racks' normal onto_bars resolution.
                    if self.mirror.onto_bars(hit)["object"] != target.split(":", 1)[0]:
                        continue
                got = self.mirror.place_target(hit) if placing else hit["point"]
                if float(np.linalg.norm(got - want)) <= tol:
                    return {"camera": cam, "u": round(u, 1), "v": round(v, 1)}
        if placing and isinstance(target, str) and ":" in target:
            # the middle of the place is hidden (something is on it or over it): any visible part of the thing that
            # the tools resolve to the same place will do
            obj = target.split(":", 1)[0]
            for cam in self.cameras:
                for p in self._candidates(obj) + [want + np.array([dx, dy, 0.0]) for dx in (-0.08, 0.0, 0.08) for dy in (-0.07, 0.0, 0.07)]:
                    uv = w.project(cam, p)
                    if uv is None or not (0 <= uv[0] < w.image_size[0] and 0 <= uv[1] < w.image_size[1]):
                        continue
                    u, v = round(uv[0], 1), round(uv[1], 1)
                    try:
                        hit = self.mirror.hit({"camera": cam, "u": u, "v": v}, past_robot=past_robot)
                    except Exception:
                        continue
                    if hit["object"] == obj and float(np.linalg.norm(self.mirror.place_target(hit) - want)) <= tol:
                        return {"camera": cam, "u": u, "v": v}
        raise DriverError(f"no camera shows the place {target!r}")

    # ---- the tools, by name --------------------------------------------------------------------------------------------
    def observe(self, **kw):
        return self.call("observe", **kw)

    # A scripted solution written for one arm does not say which arm, and asks for things two small arms do
    # differently: a view from the front that neither can take, a thing carried across a table that no one arm
    # spans. On a robot with two arms the driver then does what an agent would have to: it takes the nearest view
    # the arms can give, picks with the other arm, or passes the thing from hand to hand by way of the middle of the
    # table. Every step is an ordinary tool call; on a one-arm robot nothing here applies.
    LOOK_INSTEAD = {"front": ("above", "back"), "left": ("above", "back"), "right": ("above", "back"), "back": ("above",), "above": ("back",)}
    CANNOT = ("ik_", "path_blocked", "unreachable_view")
    PASS_REACH = 0.40         # m: a spot to pass a thing from hand to hand is this near both arms' bases (docs/FAMILIES.md)
    PASS_REACH_FAR = 0.47     # m: 0.5.4, the last search for such a spot: a YAM hand pointing down reaches 0.49 m at the table

    def _two(self, kw: dict) -> bool:
        return bool(self.mirror.world.arm_names) and "arm" not in kw

    def _failed(self, out: dict) -> str:
        r = out.get("result", {}) if out.get("ok") else {}
        return str(r.get("reason", "")) if r.get("status") == "failed" else ""

    def _other(self, arm: str) -> str:
        return next(n for n in self.mirror.world.arm_names if n != arm)

    # ---- a robot that drives ---------------------------------------------------------------------------------------------
    def turn(self, deg: float, **kw):
        return self.call("turn", deg=round(float(deg), 1), **kw)

    def face(self, target, **kw):
        """Turn the base until it faces a place. (A scripted solution knows where things are; an agent that has no
        camera on the whole room turns and looks.)"""
        w = self.mirror.world
        p = w.locate(target)[0] if isinstance(target, str) and target in w.objects else self.where(target)
        x, y, yaw = w.base_pose()
        d = (math.atan2(float(p[1]) - y, float(p[0]) - x) - yaw + math.pi) % (2.0 * math.pi) - math.pi
        return self.turn(math.degrees(d), **kw) if abs(d) > math.radians(3.0) else None

    def _pixel(self, target, placing: bool = False) -> dict:
        """A pixel for a place or a thing; when no camera shows it (the head faces elsewhere), after turning to face it."""
        named = isinstance(target, str) and target in self.mirror.world.objects
        for attempt in range(2):
            try:
                return self.pixel_of(target) if named else self.pixel_at(target, placing=placing)
            except DriverError:
                if attempt or not self.mirror.world.base:
                    raise
                self.face(target)
        raise DriverError(f"no camera shows {target!r}")

    UNDERFOOT = 0.20        # m: a spot nearer than this to the middle of a body may be in none of its pictures

    def go(self, target, legs: int = 8, **kw):
        """Drive to a thing or a place, in as many calls as the way takes (one call covers at most two metres).

        A call that ran out of its two metres a step short of a spot of the floor leaves that spot under the robot.
        A body whose cameras show the floor at its feet can point at it again; one whose cameras do not (a head that
        looks ahead, wrist cameras that look at the ceiling at rest) has nothing to point at, and stands as near to
        the spot as pointing can bring it: the driver then leaves it there, as an agent would have to."""
        out = None
        for _ in range(legs):
            # only a spot of the floor or a site is left under the robot: a thing is looked for as always (`_pixel`
            # turns towards it), which the room robot's wrist camera, pointed at the floor ahead, then shows
            thing = isinstance(target, str) and target in self.mirror.world.objects
            near = out is not None and not thing and float(out["result"].get("remaining_m", math.inf)) <= self.UNDERFOOT
            try:
                px = self.pixel_at(target) if near else self._pixel(target)
            except DriverError:
                if near:
                    return out
                raise
            out = self.call("go", **px, **kw)
            if out["result"].get("arrived"):
                return out
        raise DriverError(f"go({target!r}) did not arrive in {legs} calls: {out['result'] if out else None}")

    def look(self, target, side: str | None = None, **kw):
        if side is None:                        # from above on the bench; a robot that drives looks from its own side
            side = "front" if self.mirror.world.base else "above"
        px = self.pixel_of(target) if isinstance(target, str) and target in self.mirror.world.objects else self.pixel_at(target, past_robot=False)
        if not self._two(kw):
            return self.call("look", side=side, **px, **kw)
        out = self.call("look", check=False, side=side, **px, **kw)
        for other in self.LOOK_INSTEAD.get(side, ()):
            if not self._failed(out).startswith(self.CANNOT):
                break
            out = self.call("look", check=False, side=other, **px, **kw)
        if self._failed(out).startswith(self.CANNOT):       # the nearer arm cannot: the other one, from above
            out = self.call("look", check=False, side="above", arm=self._other(out["result"]["arm"]), **px, **kw)
        return self._checked("look", out)

    def _checked(self, tool: str, out: dict) -> dict:
        if not out.get("ok"):
            raise DriverError(f"{tool} was refused: {out.get('error')}")
        if out.get("result", {}).get("status") == "failed":
            raise DriverError(f"{tool} failed: {out['result'].get('reason')}")
        return out

    def pick(self, obj: str, **kw):
        if not self._two(kw):
            return self.call("pick", **self.pixel_of(obj), **kw)
        out = self.call("pick", check=False, **self.pixel_of(obj), **kw)
        if self._failed(out).endswith(":pregrasp") and self.mirror.held(self._other(out["result"]["arm"])) is None:
            out = self.call("pick", check=False, arm=self._other(out["result"]["arm"]), **self.pixel_of(obj), **kw)      # the arm did not move: the other one
        return self._checked("pick", out)

    def _pass_over(self, arm: str) -> str:
        """Hand what `arm` holds to the other arm by way of the table: put down on a free spot of the middle strip,
        withdraw, take with the other hand. Returns the arm that holds it now."""
        w = self.mirror.world
        obj, other = self.mirror.held(arm), self._other(arm)
        lo, hi = w.box(obj)
        size = float(max(hi[0] - lo[0], hi[1] - lo[1])) / 2.0

        def free(x, y, margin=0.03):
            half = size + margin
            return all(n == obj or w.objects[n].get("mocap") or float(w.box(n)[1][2]) < 0.004 or
                       x + half < w.box(n)[0][0] or x - half > w.box(n)[1][0] or y + half < w.box(n)[0][1] or y - half > w.box(n)[1][1]
                       for n in w.objects)
        spot = next(([x, y, 0.0] for y in (0.0, -0.05, 0.05, -0.10, 0.10, 0.14) for x in (0.0, -0.04, 0.04) if free(x, y)), None)
        if spot is None:
            # the middle strip has no room with 3 cm to spare (a wide basin reaches into it, a long block is passed):
            # a finer search with 1.5 cm to spare, out to where both hands still reach (within PASS_REACH of each
            # arm's base, seen from above), nearest the middle first (lane/bodies 123ed56; the first search unchanged)
            bases = [np.asarray(m["pos"][:2], dtype=np.float64) for m in w._mounts]
            near = lambda x, y: all(float(np.hypot(x - b[0], y - b[1])) <= self.PASS_REACH for b in bases)
            spots = sorted(((x, y) for y in (0.0, 0.05, 0.10, -0.05, 0.14) for x in (0.0, 0.02, -0.02, 0.04, -0.04, 0.06, -0.06, 0.08, -0.08)),
                           key=lambda p: (round(abs(p[0]) + 0.5 * abs(p[1]), 3)))
            spot = next(([x, y, 0.0] for x, y in spots if near(x, y) and free(x, y, 0.015)), None)
        if spot is None:
            # 0.5.4 (lane yamreadmit054): still no room: further out in front, where both hands reach the table at
            # all (`PASS_REACH_FAR`), with 1.5 cm to spare, nearest the middle first; each spot is tried with the place
            # itself, and the first that the holding hand can put the thing down on is taken (a place that cannot be
            # planned moves nothing)
            bases = [np.asarray(m["pos"][:2], dtype=np.float64) for m in w._mounts]
            far = lambda x, y: all(float(np.hypot(x - b[0], y - b[1])) <= self.PASS_REACH_FAR for b in bases)
            spots = sorted(((round(x, 2), round(y, 2)) for y in (-0.06, -0.08, -0.10, -0.12, -0.14, -0.16, -0.18)
                            for x in (0.0, 0.03, -0.03, 0.06, -0.06, 0.09, -0.09)),
                           key=lambda p: (round(abs(p[0]) + 0.5 * abs(p[1]), 3), p))
            self.mirror.use({"arm": arm})
            for x, y in spots:
                if not (far(x, y) and free(x, y, 0.015)):
                    continue
                try:
                    px = self.pixel_at([x, y, 0.0], placing=True)
                except DriverError:
                    continue
                out = self.call("place", check=False, arm=arm, **px)
                if self.mirror.held(arm) is None:
                    self._checked("place", out)
                    self.call("home", arm=arm)
                    self.call("pick", arm=other, **self.pixel_of(obj))
                    return other
            raise DriverError("no free spot in the middle of the table to pass the thing from hand to hand")
        self.mirror.use({"arm": arm})
        self.call("place", arm=arm, **self.pixel_at(spot, placing=True))
        self.call("home", arm=arm)
        self.call("pick", arm=other, **self.pixel_of(obj))
        return other

    def _hand(self, kw: dict) -> None:
        """Two arms: the pixel of a place is read past what the acting hand holds, so the private copy is told which
        arm the call is going to use before the pixel is looked up."""
        m = self.mirror
        if m.world.arm_names:
            m.use({"arm": kw.get("arm")}, default="holding")

    def _carry_to(self, tool: str, target, placing: bool, kw: dict, **args):
        """`place` or `move` on two arms without `arm`: when the hand that holds the thing cannot get there and the
        other arm stands nearer to the place, the thing goes from hand to hand first."""
        self._hand(kw)
        out = self.call(tool, check=False, **self.pixel_at(target, placing=placing), **args, **kw)
        why = self._failed(out)
        if tool == "place" and why.startswith("ik_joint_limit:turn") and abs(float(kw.get("turn_deg", 0.0))) > 1e-6:
            got = self._turn_by_two_hands(target, out["result"]["arm"], kw)
            if got is not None:
                return got
        if why.startswith(("ik_", "path_blocked")) and self.mirror.held() is not None:
            arm = out["result"]["arm"]
            if self.mirror.world.nearest_arm(self.where(target)) != arm and self.mirror.held(self._other(arm)) is None:
                other = self._pass_over(arm)
                self.mirror.use({"arm": other})
                out = self.call(tool, check=False, arm=other, **self.pixel_at(target, placing=placing), **args, **kw)
        return self._checked(tool, out)

    def _turn_by_two_hands(self, target, arm: str, kw: dict):
        """0.5.4 (lane yamreadmit054): two arms, `place` with `turn_deg` where the wrist of the hand that holds the thing
        cannot make the whole turn (`ik_joint_limit:turn`; a YAM wrist turns a held thing about a quarter of a turn,
        and only one way round from the grasp it has): the turn is made in two halves, one by each hand. This hand puts
        the thing down at the place turned by half the turn (the half one way round, else, for half a turn, the other
        way round: both end the same), goes home, and the other hand takes it there and puts it down turned by the
        rest. None when no half can be made or the other hand is not free (the caller goes on as before)."""
        other = self._other(arm)
        if self.mirror.held(other) is not None:
            return None
        turn = float(kw["turn_deg"])
        halves = [turn / 2.0]
        if abs(abs(turn) - 180.0) < 1e-6:
            halves.append(-turn / 2.0)
        rest = {k: v for k, v in kw.items() if k not in ("turn_deg", "arm")}
        thing = self.mirror.held(arm)
        for half in halves:
            self.mirror.use({"arm": arm})
            out = self.call("place", check=False, arm=arm, turn_deg=round(half, 1), **self.pixel_at(target, placing=True), **rest)
            if self._failed(out) or not out.get("ok"):
                if self.mirror.held(arm) is None:       # let go somewhere else: not a turn this driver can finish
                    return self._checked("place", out)
                continue
            self.call("home", arm=arm)
            self.call("pick", arm=other, **self.pixel_of(thing))
            remaining = turn - half if abs(abs(turn) - 180.0) > 1e-6 else half
            self.mirror.use({"arm": other})
            return self._checked("place", self.call("place", check=False, arm=other, turn_deg=round(remaining, 1),
                                                    **self.pixel_at(target, placing=True), **rest))
        return None

    def place(self, target, **kw):
        if self._two(kw):
            return self._carry_to("place", target, True, kw)
        self._hand(kw)
        return self.call("place", **self.pixel_at(target, placing=True), **kw)

    def move(self, target, height: float = 0.12, **kw):
        if self._two(kw):
            return self._carry_to("move", target, False, kw, height=height)
        self._hand(kw)
        return self.call("move", height=height, **self.pixel_at(target), **kw)

    def pour(self, target, amount: str = "all", **kw):
        self._hand(kw)
        if isinstance(target, str) and target in self.mirror.world.objects:
            px = self.pixel_of(target)
        else:
            px = self.pixel_at(target)
        return self.call("pour", amount=amount, **px, **kw)

    def press(self, obj: str, control: str, **kw):
        site = self.mirror.world.objects[obj]["meta"]["controls"][control]["site"]
        out = self.call("press", check=False, **self.pixel_at(f"{obj}/{site}", tol=0.04, past_robot=False), **kw)
        if self._failed(out) == "too_far":      # a robot that drives, standing out of its arm's reach: what the result advises
            self.go(f"{obj}/{site}")
            out = self.call("press", check=False, **self.pixel_at(f"{obj}/{site}", tol=0.04, past_robot=False), **kw)
        if self._two(kw) and self._failed(out).startswith(self.PRESS_OTHER):
            # 0.5.4 (lane yamreadmit054): two arms, the nearer one cannot press it (no stroke plans, or the stroke does not
            # take the control in): the other one, if its hand is free
            other = self._other(out["result"]["arm"])
            if self.mirror.held(other) is None:
                out = self.call("press", check=False, arm=other, **self.pixel_at(f"{obj}/{site}", tol=0.04, past_robot=False), **kw)
        return self._checked("press", out)

    PRESS_OTHER = ("ik_", "path_blocked", "no_contact", "not_pressed")

    def release(self, **kw):
        return self.call("release", **kw)

    # the pose interface: the caller works out the poses (from `where`, ground truth of the private copy)
    def move_tcp(self, x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, **kw):
        return self.call("move_tcp", x=round(float(x), 4), y=round(float(y), 4), z=round(float(z), 4),
                         yaw=float(yaw), pitch=float(pitch), roll=float(roll), **kw)

    def go_tcp(self, x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, step: float = 0.25, **kw):
        """`move_tcp` in as many calls as the per-call limits need: the turn first (in place), then the way. On two
        arms the hand of `arm` (else of the arm that acted last)."""
        w = self.hand(kw.get("arm"))
        goal = tf.quat_from_ypr(yaw, pitch, roll)
        if self.mirror.world.arm_names:
            # a YAM hand cannot turn in place where it rests (it cannot point down 0.5 m above the table): it turns on
            # its way, a share of the turn with each step of the way
            target = np.array([x, y, z], dtype=np.float64)
            out = None
            for _ in range(16):
                pos, quat = w.tcp_pose()
                d, left = target - pos, float(np.degrees(np.linalg.norm(tf.rotvec(quat, goal))))
                n = float(np.linalg.norm(d))
                if n < 1e-3 and left < 1.0 and out is not None:
                    break
                k = min(1.0, step / max(n, 1e-9), 90.0 / max(left, 1e-9))
                out = self.move_tcp(*(pos + d * k), *tf.ypr_from_quat(tf.slerp(quat, goal, k)), **kw)
            return out
        for _ in range(4):
            pos, quat = w.tcp_pose()
            left = float(np.degrees(np.linalg.norm(tf.rotvec(quat, goal))))
            if left < 1.0:
                break
            part = tf.slerp(quat, goal, min(1.0, 90.0 / left))
            self.move_tcp(*pos, *tf.ypr_from_quat(part), **kw)
        out = None
        for _ in range(12):
            pos = w.tcp_pose()[0]
            d = np.array([x, y, z], dtype=np.float64) - pos
            n = float(np.linalg.norm(d))
            if n < 1e-3 and out is not None:
                break
            to = pos + d * min(1.0, step / max(n, 1e-9))
            out = self.move_tcp(*to, yaw, pitch, roll, **kw)
        return out

    def hand(self, arm: str | None = None):
        """The private copy's arm that a pose call acts with: the world itself on one arm; on two, `arm` or else the
        arm that acted last."""
        w = self.mirror.world
        if not w.arm_names:
            return w
        return w.arm(arm) if arm else self.mirror.arm

    def gripper(self, width_mm: float, **kw):
        return self.call("gripper", width_mm=float(width_mm), **kw)

    def home(self, **kw):
        return self.call("home", **kw)

    def wait(self, seconds: float, **kw):
        return self.call("wait", seconds=seconds, **kw)

    def ask(self, text: str, **kw):
        return self.call("ask_operator", text=text, **kw)

    def report(self, category: str, text: str, **kw):
        return self.call("report", category=category, text=text, **kw)

    def end(self, reason: str, text: str = "", **kw):
        return self.call("end", reason=reason, text=text, **kw)
