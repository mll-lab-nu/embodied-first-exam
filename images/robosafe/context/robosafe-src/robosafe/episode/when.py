"""Conditions for script triggers. Each returns a callable(episode) -> bool, evaluated at the end of every call
(`Episode.on`) or after every control tick (`Episode.on_tick`, 0.5.1).

Under the control interface (0.5.0: no skills, a call is a control step or a chunk of them) the conditions that count
skill calls are read physically: the n-th `pick` is the n-th grasp the hand took, the n-th `place` the n-th time it let
go of something (`Control.events`); n calls are n times `CALL_S` seconds of robot time; `wait` time is the time the
command in force was held still (`Episode.waited`, kept by `Control.step` and by `wait`)."""
from __future__ import annotations

CALL_S = 3.0        # s of robot time that stand for one call under the control interface (a skill call takes 2 to 5 s)
EVENTS = ("pick", "place")


def _control(ep) -> bool:
    return getattr(ep, "control", None) is not None


def _calls_now(ep, since_tick: int = 0) -> float:
    """Calls made so far, or since a tick; under the control interface robot time divided by `CALL_S`."""
    return (ep.world.tick - since_tick) * ep.control_dt / CALL_S


def after_call(tool: str, n: int = 1, ok: bool | None = True):
    """The n-th call of a tool (successful ones only unless `ok` is None) has just finished or is in the past."""
    def cond(ep) -> bool:
        if _control(ep) and tool in EVENTS:
            return ep.control.events[tool] >= n
        return sum(1 for c in ep.calls if c["tool"] == tool and (ok is None or c["ok"] == ok)) >= n
    return cond


def calls(n: int):
    return lambda ep: (_calls_now(ep, ep.control.start_tick) >= n) if _control(ep) else len(ep.calls) >= n


def holding(obj: str | None = None):
    return lambda ep: ep.world.held is not None and (obj is None or ep.world.holds(obj))


def moved(obj: str, distance: float = 0.05):
    return lambda ep: ep.displacement(obj) > distance


def waited(mark: str, seconds: float):
    """At least `seconds` of `wait` time have passed since the mark was set."""
    return lambda ep: mark in ep.marks and ep.waited - ep.marks[mark]["waited"] >= seconds


def calls_since(mark: str, n: int):
    def cond(ep) -> bool:
        if mark not in ep.marks:
            return False
        if _control(ep):
            return _calls_now(ep, ep.marks[mark]["tick"]) >= n
        return len(ep.calls) - ep.marks[mark]["calls"] >= n
    return cond


def marked(mark: str):
    return lambda ep: mark in ep.marks


def arrived(name: str):
    """The scripted body set walking under that name (`Episode.walk`) has got to the end of its way."""
    return lambda ep: name in ep.arrived


def on_the_way(obj: str):
    """The scripted body is walking (`Episode.walk`) and has not got there yet."""
    return lambda ep: obj in ep.motions


def base_moved(distance: float, toward=None):
    """A robot that drives has got under way (0.5.1): its base stands more than `distance` metres from where it stood
    as the episode began, measured along the floor, or, with `toward` (a point `[x, y]` of the floor), the progress it
    has made in that direction (the distance from the start projected on the line to the point). It reads the base's
    pose alone, which every robot that drives has, whatever its tools are; turning on the spot is no progress. Look at it
    after every tick (`Episode.on_tick`) so that a change follows the base's motion inside the call that moves it."""
    import numpy as np
    def cond(ep) -> bool:
        if ep.base_start is None:
            return False
        here = ep.world.base_pose()[:2] - ep.base_start[:2]
        if toward is None:
            return float(np.hypot(here[0], here[1])) > distance
        u = np.asarray(toward, dtype=np.float64)[:2] - ep.base_start[:2]
        n = float(np.hypot(u[0], u[1]))
        return n > 1e-9 and float(np.dot(here, u)) / n > distance
    return cond


def _point(ep, target):
    """A point of the bench: `[x, y(, z)]`, or an object's position as it is now."""
    import numpy as np
    if isinstance(target, str):
        return np.asarray(ep.state.pos(target), dtype=np.float64)
    return np.asarray(target, dtype=np.float64)


def tcp_progress(fraction: float, toward, start=None):
    """The hand has made `fraction` of its way towards a target (0.5.1, table-scale movers): the progress of the TCP
    from `start` (default: where the TCP was the first time this condition was looked at, i.e. at rest as the episode
    begins) projected on the line to `toward` (a point, or an object: where it stands then), in plan (x, y), over
    the length of that line. It reads the TCP alone, whatever the interface; holding still makes no progress. Look at
    it after every tick (`Episode.on_tick`)."""
    import numpy as np
    memo: dict = {}

    def cond(ep) -> bool:
        tcp = np.asarray(ep.state.pos("tcp"), dtype=np.float64)
        if "a" not in memo:
            memo["a"] = (np.asarray(start, dtype=np.float64) if start is not None else tcp.copy())[:2]
            memo["b"] = _point(ep, toward)[:2]
        a, b = memo["a"], memo["b"]
        u = b - a
        n = float(np.hypot(u[0], u[1]))
        return n > 1e-9 and float(np.dot(tcp[:2] - a, u)) / (n * n) >= float(fraction)
    return cond


def hand_travelled(distance: float, since: str | None = None):
    """The hand (TCP) has travelled `distance` metres along its path in all, or since an episode mark (0.5.1)."""
    return lambda ep: (ep.path - (ep.marks[since]["path"] if since else 0.0)) >= distance if (since is None or since in ep.marks) else False


def lifted(obj: str, dz: float = 0.02, by: str | None = None):
    """The object has been raised `dz` metres above where it stood when the episode began (0.5.1); with `by="hand"`,
    only while a hand of the robot holds it (not knocked up or tipped over)."""
    if by not in (None, "hand"):
        raise ValueError("`by` is None or 'hand'")
    return lambda ep: ep.lift(obj) >= dz and (by is None or ep.world.holds(obj))


def still(seconds: float, since: str | None = None, speed: float = 0.02):
    """The hand has been still for `seconds` of robot time without a break (0.5.1): its TCP moved slower than `speed`
    m/s on every control tick, counted from the mark `since` when one is given (nothing counts before it is set).
    Read from the TCP alone, so it holds the same under every interface (a skill's `wait`, a held command, or a slow
    stand); look at it after every tick (`Episode.on_tick`), so the change comes while the robot is still."""
    import numpy as np
    memo = {"last": None, "run": 0, "tick": None}

    def cond(ep) -> bool:
        if since is not None and since not in ep.marks:
            return False
        tick = ep.world.tick
        if memo["tick"] == tick:
            return memo["run"] * ep.control_dt >= seconds
        tcp = np.asarray(ep.state.pos("tcp"), dtype=np.float64)
        moved = memo["last"] is None or float(np.linalg.norm(tcp - memo["last"])) > speed * ep.control_dt
        memo["run"] = 0 if moved else memo["run"] + 1
        memo["last"], memo["tick"] = tcp.copy(), tick
        return memo["run"] * ep.control_dt >= seconds
    return cond


def sim_time(seconds: float):
    """Robot time has reached `seconds` (0.5.1; the second option for a mover's start: time passes only while a call
    runs, but a `wait` counts too, so a start that must follow the robot's work keys off its motion instead)."""
    return lambda ep: ep.world.time >= seconds

def at_rest(obj: str):
    """The object is not held and moves slower than 5 cm/s (`rules.at_rest`; 0.5.1, for `Episode.then`: what a
    script does after a thing it set falling has come to rest)."""
    from robosafe.hazard import rules as R
    return lambda ep: R.at_rest(ep.state, obj)


def all_of(*conds):
    return lambda ep: all(c(ep) for c in conds)


def any_of(*conds):
    return lambda ep: any(c(ep) for c in conds)
