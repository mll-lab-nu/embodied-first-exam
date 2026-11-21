"""The ablation switches of this service (all off unless the sim service's environment sets them; nothing changes when
off). They act on the adaptation rounds only: the held-out evaluation of the selected policy, its replay check and the
video run exactly as without them.

  RCB_HIDE_SUCCESS=1  no success signal: POST /finish ends adaptation (it seals the given round, or else the latest
                      completed one); /spec says success_signal "hidden"; final.json adds ended_by, finish_time_s and
                      the private diagnostics hidden_success_seen / trial_hidden_success_seen (whether every
                      development case of the graded round / of any round met the success rule). A deployment's
                      feedback is the same as without the switch: it never holds a score or a success flag.
  RCB_STATE_QUERY=1   privileged state queries: every development episode also records the simulator's state at its
                      telemetry times (state-trace.json beside its record): poses, velocities, sizes and boxes, the
                      robot's joints (a legged robot's: its joint encoders' readings, as in the telemetry); GET
                      /state/entities lists the entities and fields, POST /state/query answers their values for a
                      completed round. A query runs no simulation and changes nothing; final.json adds state_queries.
  RCB_STATE_OPS=1     more deployments, save and load: the round budget is 3 + RCB_RESET_BUDGET (every deployment
                      starts the development cases afresh, the reset); POST /save_state names a point of a completed
                      development episode (round, case, telemetry time) and POST /load_state makes the next deployment
                      continue that case from there with the new policy. A load re-simulates the saved path from the
                      frozen start (CPU MuJoCo is deterministic) and checks the state's digest at the saved time.
                      final.json adds rounds, round_budget, reset_budget, resets, saves, loads, episodes,
                      episodes_log, first_success and, on a success, resets_at_success / loads_at_success.
"""

import copy
import hashlib
import json
import math
import os

import numpy as np

HIDE_SUCCESS = os.environ.get("RCB_HIDE_SUCCESS") == "1"
STATE_QUERY = os.environ.get("RCB_STATE_QUERY") == "1"
STATE_OPS = os.environ.get("RCB_STATE_OPS") == "1"
RESET_BUDGET = int(os.environ.get("RCB_RESET_BUDGET", "0") or 0) if STATE_OPS else 0
ANY = HIDE_SUCCESS or STATE_QUERY or STATE_OPS
STANDARD_ROUNDS = 3
MAX_HANDLES = 32
TRACE = "state-trace.json"

FINISH_NOTE = (
    "no success signal (an ablation of this run): no response says whether a policy succeeds; POST /finish "
    "{\"round_id\": <completed round, optional>, \"summary\": <text, optional>} ends adaptation: the given round, or "
    "else the latest completed one, is the graded policy; every call after it is refused (409)")
QUERY_NOTE = (
    "privileged state (an ablation of this run): GET /state/entities lists the entities {name: {\"kind\", \"fields\": "
    "{field: unit}, \"static\"}} with \"frame\" and \"quaternion_order\"; POST /state/query {\"names\": [...], "
    "\"fields\": [...] (optional), \"round_id\": <completed round, default the latest>, \"case\": <case index, "
    "default every case of the round>, \"t\": <seconds, or [t0, t1], default every sample>} answers the "
    "simulator state of that round's development episodes at their telemetry times (the table's note says which "
    "fields are sensor readings): {\"round_id\", \"cases\": "
    "[{\"case\", \"t\": [...], \"state\": {name: {field: value per time (static: one value)}}}], \"state_queries\"}. "
    "It runs no simulation; every query is counted (state_queries)")
OPS_NOTE = (
    "more deployments, save and load (an ablation of this run): the round budget is {rounds}; every deployment starts "
    "the development cases afresh. POST /save_state {{\"round_id\", \"case\", \"t\"}} stores the state of that "
    "completed development episode at its telemetry time at or before t and answers {{\"handle\", \"t\", ...}} (the "
    "handle only; at most 32 are kept, the least recently used is dropped); POST /load_state {{\"handle\"}} makes the "
    "next deployment run only that case, from that state, with the deployed policy taking over there (the "
    "controller's run-time state carries over); {{\"handle\": null}} cancels it. A loaded deployment's feedback "
    "covers its whole episode, the saved path included. Saves and loads cost no round")


def initial_state():
    return {"state_queries": 0, "saves": 0, "loads": 0, "handles": [], "next_handle": 1, "pending": None,
            "finished": None, "ended_by": None}


# ---------------------------------------------------------------- the worker side: the hook a rollout calls

def _bytes(item):
    if isinstance(item, np.ndarray) or (isinstance(item, (list, tuple)) and all(
            isinstance(x, (int, float, np.floating, np.integer)) and not isinstance(x, bool) for x in item)):
        return np.asarray(item, dtype="<f8").tobytes()
    return json.dumps(item, sort_keys=True, default=lambda v: np.asarray(v).tolist()).encode()


def _value(v):
    if isinstance(v, dict):
        return {str(k): _value(x) for k, x in v.items()}
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return round(f, 6) if math.isfinite(f) else None
    if isinstance(v, np.ndarray):
        return _value(v.tolist())
    if isinstance(v, (list, tuple)):
        return [_value(x) for x in v]
    return v


def controller_state(controller):
    """A controller's run-time attributes (everything but its parameters), for a state digest."""
    skip = {"p", "policy", "path", "course"}
    return {k: v for k, v in sorted(vars(controller).items()) if k not in skip}


def _same(a, b):
    try:
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            return isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.shape == b.shape \
                and bool(np.array_equal(a, b))
        return type(a) is type(b) and bool(a == b)
    except Exception:
        return False


def carry(current, fresh_old, new):
    """The controller that takes over at a load: `new` (the new policy's controller as constructed) with every
    attribute that `current` changed since its own construction (`fresh_old`: the old policy's controller as
    constructed) copied over, i.e. the run-time state (phase, timers, integrators, observers) carries over and the
    parameters are the new policy's. A controller of another class (another policy schema) starts as constructed."""
    if type(current) is not type(new):
        return new
    for k, v in vars(current).items():
        if not _same(v, getattr(fresh_old, k, object())):
            setattr(new, k, copy.deepcopy(v))
    return new


class Hook:
    """Passed to a rollout as `ablation`. The rollout calls
      record(t, state, fingerprint, static=None) at each telemetry time, before that step's control: `state` is
          {entity: {field: value}} of the simulator's true state, `fingerprint` the items that make the simulation's
          future (physics, actuator and controller run-time state, random generator state);
      switch(t) at each control update: a policy file path when a later segment of the schedule starts at or before
          t (the rollout loads it and swaps its controller), else None.
    schedule: [[t_start, policy path], ...] of the segments after the first (the rollout's own policy)."""

    def __init__(self, schedule=(), store_states=False):
        self.schedule = sorted([float(t), str(p)] for t, p in schedule)
        self.store = store_states
        self.times, self.states, self.digests, self.static = [], [], [], {}

    def record(self, t, state, fingerprint, static=None):
        h = hashlib.sha256()
        for item in fingerprint:
            h.update(_bytes(item))
        self.times.append(round(float(t), 6))
        self.digests.append(h.hexdigest())
        if self.store:
            self.states.append(_value(state))
            if static and not self.static:
                self.static = _value(static)

    def switch(self, t):
        if self.schedule and float(t) >= self.schedule[0][0] - 1e-9:
            return self.schedule.pop(0)[1]
        return None

    @staticmethod
    def body_box(model, body, subtree=False):
        """(lo, hi) [3] m: the box of a MuJoCo body's geoms in the body's own frame (each geom's own box, geom_aabb, at
        its pose in the body); subtree: also the geoms of the bodies below it, at their rest pose (qpos0)."""
        return body_box(model, body, subtree)

    @staticmethod
    def geom_box(model, geoms):
        """(lo, hi) [3] m: the box of MuJoCo geoms of one body in that body's own frame."""
        return _box(_geom_corners(model, geoms))

    @staticmethod
    def world_box(lo, hi, pos, quat):
        """[[x, y, z] min, [x, y, z] max] m: the world-axis box around the box (lo, hi) of a frame at pos / quat."""
        return world_box(lo, hi, pos, quat)

    def write(self, folder):
        value = {"t": self.times, "digest": self.digests}
        if self.store:
            value.update(state=self.states, static=self.static)
        tmp = os.path.join(folder, f".{TRACE}.tmp")
        with open(tmp, "w") as f:
            json.dump(value, f, allow_nan=False)
        os.replace(tmp, os.path.join(folder, TRACE))


# ---------------------------------------------------------------- boxes of MuJoCo geometry (the recorders' size / bbox)

_SIGNS = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)], dtype=float)


def _rot(quat):
    w, x, y, z = np.asarray(quat, dtype=float) / np.linalg.norm(quat)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _geom_corners(model, geoms, pos=(0.0, 0.0, 0.0), rot=np.eye(3)):
    """The corners of each geom's own box (geom_aabb: centre, half sizes), in its body's frame moved by (pos, rot)."""
    pts = []
    for g in geoms:
        c, h = np.asarray(model.geom_aabb[g][:3]), np.asarray(model.geom_aabb[g][3:])
        local = np.asarray(model.geom_pos[g]) + (c + _SIGNS * h) @ _rot(model.geom_quat[g]).T
        pts.append(np.asarray(pos) + local @ np.asarray(rot).T)
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def _box(pts):
    return (pts.min(0), pts.max(0)) if len(pts) else (np.zeros(3), np.zeros(3))


def body_box(model, body, subtree=False):
    bodies = [b for b in range(model.nbody) if b == body or (subtree and _below(model, b, body))]
    pts = []
    for b in bodies:
        pos, rot = np.zeros(3), np.eye(3)
        k = b
        while k != body:        # the rest pose of b in the frame of `body`
            r = _rot(model.body_quat[k])
            pos, rot = np.asarray(model.body_pos[k]) + r @ pos, r @ rot
            k = int(model.body_parentid[k])
        pts.append(_geom_corners(model, [g for g in range(model.ngeom) if model.geom_bodyid[g] == b], pos, rot))
    return _box(np.concatenate(pts))


def _below(model, b, body):
    while b > 0:
        b = int(model.body_parentid[b])
        if b == body:
            return True
    return False


def world_box(lo, hi, pos, quat):
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    pts = np.asarray(pos, dtype=float) + ((lo + hi) / 2 + _SIGNS * (hi - lo) / 2) @ _rot(quat).T
    return [pts.min(0), pts.max(0)]


# ---------------------------------------------------------------- the entities a family's rollout records

POSE = {"pos": "m [x, y, z]", "quat": "[w, x, y, z]"}
BODY = {**POSE, "lin_vel": "m/s [x, y, z]", "ang_vel": "rad/s [x, y, z]", "height_above_ground": "m"}
BOX = {"size": "m [x, y, z] full extents along the body axes", "bbox": "m [[x, y, z] min, [x, y, z] max], world axes"}
ENCODERS = {"joint_pos": "{joint: rad} (encoder reading)", "joint_vel": "{joint: rad/s} (encoder reading)"}


def entities(instance):
    """{frame, quaternion_order, entities: {name: {kind, fields: {field: unit}, static}}} of this instance's family."""
    fam = instance.get("family", "landing")
    ents = {}

    def add(name, kind, fields, static=False, note=None):
        ents[name] = {"kind": kind, "fields": dict(fields), "static": static, **({"note": note} if note else {})}

    if fam == "go2":
        frame = ("MuJoCo world: z up, the floor at z = 0, the origin on the floor below the robot's start, +x the "
                 "start heading (within 0.025 rad)")
        add("robot", "robot", {**BODY, **ENCODERS, **BOX},
            note="the trunk (base) body; joint_pos / joint_vel: the joint encoders' readings, the telemetry's q / dq "
                 "at the same time; size / bbox: the trunk body's own geometry")
        if instance["bank"]["adaptation"][0].get("task") == "weave":
            for k in range(4):
                add(f"pole_{k}", "scene_feature", {"pos": "m [x, y, z] (axis at floor level)", **BOX}, static=True)
    elif fam in ("anycar-drift", "anycar-drift-v3"):
        frame = "the course's MuJoCo world: z up, the ground at z = 0; the coordinates of the course command"
        add("car", "robot", {**BODY, "joint_pos": "{steering: rad}", "joint_vel": "{wheel spin: rad/s}", **BOX},
            note="the chassis; size / bbox: the car body with its wheels at rest")
        for k in range(2):
            add(f"parked_car_{k}", "object", {**POSE, **BOX}, static=True, note="size / bbox: its collision box")
        add("parking_slot", "scene_feature", {"pos": "m [x, y, z] (its centre)", **BOX}, static=True,
            note="the painted bay on the ground: size = [length, width, 0]")
        add("curb", "scene_feature", {"pos": "m [x, y, z] (its centre)", **BOX}, static=True)
    elif fam == "g1":
        frame = "MuJoCo world: z up, +x the walking direction, the robot starts near the origin"
        add("robot", "robot", {**BODY, **ENCODERS, **BOX},
            note="the pelvis (root); height_above_ground is above the ground under it; joint_pos / joint_vel: the "
                 "joint encoders' readings (joint_pos: the telemetry's values at the same time); size / bbox: the "
                 "pelvis body's own geometry")
    elif fam == "neural-fly":
        frame = "MuJoCo world: z up, the frame of the telemetry's position and target_position"
        add("drone", "robot", {**BODY, **BOX})
    elif fam == "landing":
        frame = "MuJoCo world: z up, the floor at z = 0, the frame of the observations' position and pad_position"
        add("drone", "robot", {**BODY, **BOX}, note="height_above_ground: the feet's clearance above the floor")
        add("pad", "scene_feature", {"pos": "m [x, y, z] (its centre, on the floor)", **BOX}, static=True)
    else:
        raise ValueError("no state table for this family")
    return {"frame": frame, "quaternion_order": "wxyz",
            "note": "the simulator's state at the telemetry times of each development episode"
                    + ("; the robot's joint_pos / joint_vel are its joint encoders' readings" if fam in ("go2", "g1")
                       else ""),
            "entities": ents}


def plan(table, body, rounds):
    """A /state/query body -> (plan, None) or (None, the 400's body). rounds: {round id: [case indices]} of the
    completed rounds in their order."""
    ents = table["entities"]
    extra = sorted(set(body) - {"names", "fields", "round_id", "case", "t"})
    if extra:
        return None, {"error": f"unknown keys {extra}", "keys": ["names", "fields", "round_id", "case", "t"]}
    if not rounds:
        return None, {"error": "no completed round yet: deploy first"}
    names = body.get("names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        return None, {"error": "names must be a non-empty list of entity names", "names": list(ents)}
    names = list(dict.fromkeys(names))
    bad = [n for n in names if n not in ents]
    if bad:
        return None, {"error": "unknown names", "unknown": bad, "names": list(ents)}
    fields = body.get("fields")
    if fields is None:
        want = {n: list(ents[n]["fields"]) for n in names}
    else:
        if not isinstance(fields, list) or not fields or not all(isinstance(f, str) for f in fields):
            return None, {"error": "fields must be a non-empty list of field names, or left out for all of them"}
        have = {f for n in names for f in ents[n]["fields"]}
        bad = [f for f in dict.fromkeys(fields) if f not in have]
        if bad:
            return None, {"error": "unknown fields for these names", "unknown": bad,
                          "fields": {n: list(ents[n]["fields"]) for n in names}}
        want = {n: [f for f in dict.fromkeys(fields) if f in ents[n]["fields"]] for n in names}
    rid = body.get("round_id", list(rounds)[-1])
    if type(rid) not in (int, str) or rid not in rounds:
        return None, {"error": "round_id must be a completed round", "rounds": list(rounds)}
    case = body.get("case")
    if case is not None and (type(case) is not int or case not in rounds[rid]):
        return None, {"error": "case must be a case index of that round", "cases": rounds[rid]}
    t = body.get("t")
    ok = t is None or (type(t) in (int, float) and math.isfinite(t)) or (
        isinstance(t, list) and len(t) == 2 and all(type(x) in (int, float) and math.isfinite(x) for x in t)
        and t[0] <= t[1])
    if not ok:
        return None, {"error": "t must be a time in seconds, a window [t0, t1], or left out for every sample"}
    return {"names": want, "round_id": rid, "cases": [case] if case is not None else rounds[rid], "t": t}, None


def answer(table, p, traces):
    """traces: {case: the case's state-trace.json value} -> the query's answer."""
    ents = table["entities"]
    out = []
    for case in p["cases"]:
        tr = traces[case]
        times = tr["t"]
        t = p["t"]
        if t is None:
            idx = list(range(len(times)))
        elif isinstance(t, list):
            idx = [i for i, x in enumerate(times) if t[0] - 1e-9 <= x <= t[1] + 1e-9]
        else:
            idx = [min(range(len(times)), key=lambda i: abs(times[i] - t))] if times else []
        state = {}
        for name, fields in p["names"].items():
            if ents[name]["static"]:
                src = tr["static"].get(name, {})
                state[name] = {f: src[f] for f in fields if f in src}
            else:
                state[name] = {f: [tr["state"][i].get(name, {}).get(f) for i in idx] for f in fields}
        out.append({"case": case, "t": [times[i] for i in idx], "state": state})
    return {"round_id": p["round_id"], "cases": out}
