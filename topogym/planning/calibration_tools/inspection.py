"""Named contact readouts and bounded control-boundary event windows."""
from collections import deque
from copy import deepcopy
from uuid import uuid4

import numpy as np

from .contracts import positive_int


def contact_summary(world, entities, selected=None):
    # FEM volumes have vertices, not articulated rigid links. Their absence here
    # must not prevent numerical IPC inspection; coverage remains rigid-only.
    names = {link.idx: dict(entity=name, link=link.name) for name, entity in entities.items()
             for link in getattr(entity, "links", ())}
    selected = None if selected is None else set(selected)
    if selected is not None and not selected <= set(entities):
        raise ValueError("Unknown entity in contact filter")
    values = world.get("contacts", {})
    a = np.asarray(values.get("link_a", [])).reshape(-1)
    b = np.asarray(values.get("link_b", [])).reshape(-1)
    forces = np.asarray(values.get("force", [])).reshape(-1, 3)
    depths = np.asarray(values.get("penetration", [])).reshape(-1)
    if len({len(a), len(b), len(forces), len(depths)}) > 1:
        raise ValueError("Inconsistent native contact buffers")
    contacts = []
    for first, second, force, depth in zip(a, b, forces, depths):
        if first < 0 or second < 0:
            continue
        left, right = names.get(int(first)), names.get(int(second))
        if selected is not None and not any(v and v["entity"] in selected for v in (left, right)):
            continue
        contacts.append(dict(a=left or dict(native_link_index=int(first)),
                             b=right or dict(native_link_index=int(second)),
                             force_world_n=force.tolist(), force_norm_n=float(np.linalg.norm(force)),
                             penetration_m=float(depth), contact_position_world_m=None))
    return dict(physics_step=int(world["physics_step"]), contacts=contacts,
                coverage="native rigid contact buffer at sampled tick; no IPC or solver-substep completeness",
                contact_positions_available=False)


def event_summary(world, robot, targets, contacts):
    pairs = sorted(set(tuple(sorted((str(c["a"]), str(c["b"])))) for c in contacts["contacts"]))
    error = 0.
    fingers = {}
    for side, arm in robot.items():
        command = targets.get(side, {})
        if "joint_position_rad" in command:
            error = max(error, float(np.max(np.abs(np.asarray(command["joint_position_rad"])-arm["joint_position_rad"]))))
        fingers[side] = {key: value for key, value in arm.items() if key.startswith("finger_position_")}
    return dict(physics_step=int(world["physics_step"]), contact_pairs=pairs,
                maximum_joint_tracking_error_rad=error, fingers=fingers,
                grasp=world.get("grasp"), contact_count=len(contacts["contacts"]))


from .grasp_observation import GRASP_EVENTS

EVENTS = {"contact_changed", "tracking_error", "gripper_changed", "always"} | GRASP_EVENTS


def triggered(event, previous, current):
    name = event if isinstance(event, str) else event["name"]
    threshold = .05 if isinstance(event, str) else float(event.get("threshold", .05))
    if name not in EVENTS or not np.isfinite(threshold) or threshold < 0:
        raise ValueError("Unsupported event or threshold")
    if name in GRASP_EVENTS:
        hand = None if isinstance(event, str) else event.get("hand")
        return any(row["name"] == name and (hand is None or row["hand"] == hand)
                   for row in current.get("grasp_events", ()))
    if name == "always":
        return True
    if name == "tracking_error":
        return current["maximum_joint_tracking_error_rad"] > threshold
    if previous is None:
        return False
    if name == "contact_changed":
        return current["contact_pairs"] != previous["contact_pairs"]
    return any(not np.allclose(values[key], previous["fingers"][side][key], atol=threshold, rtol=0)
               for side, values in current["fingers"].items() for key in values)


class EventWindows:
    def __init__(self, emit, *, durable_events=False):
        self.emit = emit
        self.durable_events = durable_events
        self.watches = {}
        self.history = deque(maxlen=1001)
        self.pending = []

    def watch(self, events, before_steps=3, after_steps=3):
        if not isinstance(events, (list, tuple)) or not events:
            raise ValueError("events must be a nonempty list")
        for n in (before_steps, after_steps):
            if type(n) is not int or not 0 <= n <= 1000:
                raise ValueError("Event windows must be between 0 and 1000 control steps")
        for event in events:
            triggered(event, None, dict(maximum_joint_tracking_error_rad=0.))
        token = uuid4().hex
        self.watches[token] = dict(events=deepcopy(events), before=before_steps, after=after_steps)
        return dict(watch_id=token, frame_capture="numerical windows only; capture_frame explicitly for Nyx")

    def push(self, current):
        previous = self.history[-1] if self.history else None
        completed = []
        for pending in self.pending:
            pending["after"].append(deepcopy(current))
            if self.durable_events:
                self.emit("event_window_progress", window_id=pending["window_id"],
                          watch_id=pending["watch_id"], after=deepcopy(current),
                          after_count=len(pending["after"]))
            if len(pending["after"]) >= pending["remaining"]:
                completed.append(pending)
        for row in completed:
            self.emit("event_window", **row)
            self.pending.remove(row)
        for token, settings in self.watches.items():
            hits = [event for event in settings["events"] if triggered(event, previous, current)]
            if hits:
                row = dict(window_id=uuid4().hex, watch_id=token, events=hits,
                           before=list(self.history)[-settings["before"]:] if settings["before"] else [],
                           trigger=deepcopy(current), after=[], remaining=settings["after"])
                # Commit prehistory and the trigger before rendering or waiting
                # for another control step. Hard-kill recovery reads this event.
                if self.durable_events:
                    self.emit("event_window_triggered", **row)
                if settings["after"]:
                    # A bounded queue prevents persistent-contact watches growing indefinitely.
                    if len(self.pending) >= 1000:
                        old = self.pending.pop(0)
                        self.emit("event_window_incomplete", reason="pending_window_limit", **old)
                    self.pending.append(row)
                else:
                    self.emit("event_window", **row)
        self.history.append(deepcopy(current))

    def reset(self, reason):
        for row in self.pending:
            self.emit("event_window_incomplete", reason=reason, **row)
        self.pending.clear()
        self.history.clear()
