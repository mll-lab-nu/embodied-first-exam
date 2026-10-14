"""Snapshot / restore of a privileged Session for authoring-time lookahead (the deliverable is only the rows)."""
import copy
import mujoco


def snapshot(s):
    d = copy.copy(s.data)
    return dict(data=d, checker=copy.deepcopy(s.checker), steps=s.steps, n=len(s.actions), peaks=dict(s._peaks),
                raw_yaw=s._raw_yaw, yaw_accum=s._yaw_accum)


def restore(s, snap):
    s.data = copy.copy(snap["data"])
    s.checker = copy.deepcopy(snap["checker"])
    s.steps = snap["steps"]
    del s.actions[snap["n"]:]
    s._peaks = dict(snap["peaks"])
    s._raw_yaw = snap["raw_yaw"]
    s._yaw_accum = snap["yaw_accum"]
