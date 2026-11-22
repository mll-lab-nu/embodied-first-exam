"""The ablation switches of this service (all off unless the sim service's environment sets them; nothing changes when
off). They act on the adaptation rounds only: the held-out evaluation of the selected policy, its replay check and the
video run exactly as without them.

  RCB_HIDE_SUCCESS=1  no success signal: POST /finish ends adaptation (it seals the given round, or else the latest
                      completed one); /spec says success_signal "hidden"; final.json adds ended_by, finish_time_s and
                      the private diagnostics hidden_success_seen / trial_hidden_success_seen (whether every
                      development case of the graded round / of any round met the success rule). A deployment's
                      feedback is the same as without the switch: it never holds a score or a success flag.
  RCB_STATE_QUERY=1   privileged state queries: every development episode also records the simulator's true state at
                      its telemetry times (state-trace.json beside its record); GET /state/entities lists the
                      entities and fields, POST /state/query answers their values for a completed round. A query runs
                      no simulation and changes nothing; final.json adds state_queries.
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
    "default every case of the round>, \"t\": <seconds, or [t0, t1], default every sample>} answers the true "
    "simulator state of that round's development episodes at their telemetry times: {\"round_id\", \"cases\": "
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

    def write(self, folder):
        value = {"t": self.times, "digest": self.digests}
        if self.store:
            value.update(state=self.states, static=self.static)
        tmp = os.path.join(folder, f".{TRACE}.tmp")
        with open(tmp, "w") as f:
            json.dump(value, f, allow_nan=False)
        os.replace(tmp, os.path.join(folder, TRACE))


# ---------------------------------------------------------------- the entities a family's rollout records

POSE = {"pos": "m [x, y, z]", "quat": "[w, x, y, z]"}
BODY = {**POSE, "lin_vel": "m/s [x, y, z]", "ang_vel": "rad/s [x, y, z]", "height_above_ground": "m"}
JOINTS = {"joint_pos": "{joint: rad}", "joint_vel": "{joint: rad/s}"}


def entities(instance):
    """{frame, quaternion_order, entities: {name: {kind, fields: {field: unit}, static}}} of this instance's family."""
    fam = instance.get("family", "landing")
    ents = {}

    def add(name, kind, fields, static=False, note=None):
        ents[name] = {"kind": kind, "fields": dict(fields), "static": static, **({"note": note} if note else {})}

    if fam == "go2":
        frame = ("MuJoCo world: z up, the floor at z = 0, the origin on the floor below the robot's start, +x the "
                 "start heading (within 0.025 rad)")
        add("robot", "robot", {**BODY, **JOINTS}, note="the trunk (base) body; joints without the encoder bias")
        for leg in ("FL", "FR", "RL", "RR"):
            add(f"foot_{leg}", "robot_link", {"pos": "m [x, y, z]"})
        if instance["bank"]["adaptation"][0].get("task") == "weave":
            for k in range(4):
                add(f"pole_{k}", "scene_feature", {"pos": "m [x, y, z] (axis at floor level)", "radius": "m",
                                                   "height": "m"}, static=True)
    elif fam in ("anycar-drift", "anycar-drift-v3"):
        frame = "the course's MuJoCo world: z up, the ground at z = 0; the coordinates of the course command"
        add("car", "robot", {**BODY, "joint_pos": "{steering: rad}", "joint_vel": "{wheel spin: rad/s}"},
            note="the chassis")
        for k in range(2):
            add(f"parked_car_{k}", "object", {**POSE, "size": "m [x, y, z] full extents of its collision box"},
                static=True)
        add("parking_slot", "scene_feature", {"pos": "m [x, y, z] (its centre)", "size": "m [length, width]"},
            static=True)
        add("curb", "scene_feature", {"pos": "m [x, y, z] (its centre)", "size": "m [x, y, z] full extents"},
            static=True)
    elif fam == "g1":
        frame = "MuJoCo world: z up, +x the walking direction, the robot starts near the origin"
        add("robot", "robot", {**BODY, **JOINTS},
            note="the pelvis (root); height_above_ground is above the terrain under it; joints without bias")
        for name in ("torso", "left_foot", "right_foot", "left_hand", "right_hand"):
            add(name, "robot_link", {**POSE, **({"ground_height": "m (terrain height below it)"}
                                                 if name.endswith("foot") else {})})
        add("terrain", "scene_feature", {"kind": "flat | slope | rough | steps", "parameters":
                                         "{slope (rise per m), rough_amplitude m, step_height m, step_width m}"},
            static=True, note="the course starts level; slope and rough begin at x = 1 m, steps at x = 1 m")
    elif fam == "neural-fly":
        frame = "MuJoCo world: z up, the frame of the telemetry's position and target_position"
        add("drone", "robot", {**BODY, "rotor_thrust": "N [4] (each rotor's realized thrust)"})
    elif fam == "landing":
        frame = "MuJoCo world: z up, the floor at z = 0, the frame of the observations' position and pad_position"
        add("drone", "robot", {**BODY, "rotor_thrust": "N [4] (each rotor's realized thrust)"},
            note="height_above_ground: the feet's clearance above the floor")
        add("pad", "scene_feature", {"pos": "m [x, y, z] (its centre)", "radius": "m"}, static=True)
    else:
        raise ValueError("no state table for this family")
    return {"frame": frame, "quaternion_order": "wxyz",
            "note": "true simulator state (no noise, no bias) at the telemetry times of each development episode",
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
