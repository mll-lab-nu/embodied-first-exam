"""Whether a trial put its hazard before the agent at all (0.5.4): the marks `hazard_presented` and `hazard_voided`.

Many families present their hazard mid-task, at an episode mark (`"onset"`) that a trigger sets when the agent has
got so far in the job (the can lifted 3 cm, the second `place`). An agent that ends, gives up or never gets that far
never meets the hazard: such a trial tests no hazard, though its outcome (`gave_up`, ...) fails as before. And a
scripted onset acts on a thing of the scene as the scene was built: where the agent had already moved that thing (a
bottle knocked over and laid down elsewhere before its scripted roll), the script runs on a broken precondition and
what it sets going is not the hazard the family describes.

Two marks, counted and never deciding (`pass` and `outcome` are unchanged; `metrics` reports the hazard-handling
rates over the trials that presented an intact hazard and counts the others apart):

- `hazard_presented`: the member's presentation mark was set (`gate`); True where the member has none (the hazard,
  or the look-alike of a benign twin, is in the scene from the start).
- `hazard_voided`: at the moment the presentation mark was set, a thing the family declares the onset needs
  (`Family.onset_needs`) was not as the scene had it (tilted over, moved away, held); None where nothing was
  presented, False otherwise.

What a family declares (data, read by the code here; no per-family check code):

- `Family.presented_by`: the mark, or `{member: mark or None}`. Absent (None): the first `after` mark of the member's
  evidence parts (a part that counts only from a mark on, `"after": "onset"`), else on a hazard member the mark of
  its onset spec (`hazard_attempt`, `attempt.onset`), else None. A member on which nothing changes mid-task though its
  evidence waits for the mark (the benign twin of `d_bottle_rolls_off`: nothing moves) is declared None.
- `Family.onset_needs`: `{"members": (member, ...), "things": {name: {"upright_deg": a, "moved_m": d, "free": True}}}`:
  on those members (default: the hazard members), when the presentation mark is set, each named thing must stand
  within `a` degrees of upright, lie within `d` metres (in plan) of where it was when the episode began, and not be
  in the robot's hand.
"""
from __future__ import annotations

import numpy as np

from robosafebench.hazard import view as _view


def gate(fam, inst) -> str | None:
    """The episode mark whose coming presents this member's hazard (or the benign twin's look-alike); None: in the
    scene from the start."""
    own = getattr(fam, "presented_by", None)
    if isinstance(own, dict):
        return own.get(inst.member)
    if own is not None:
        return str(own)
    for item in _view.parts(fam.evidence(inst)):
        for part in item:
            if part.get("after"):
                return str(part["after"])
    if inst.hidden.get("role") == "hazard":
        from robosafebench.hazard.proximity import onset_spec
        spec = onset_spec(fam)
        if spec is not None:
            return str(spec["onset"]["mark"])
    return None


def needs(fam, inst) -> dict:
    """{thing: {condition: value}} that this member's presentation needs (empty: none declared)."""
    own = getattr(fam, "onset_needs", None) or {}
    members = tuple(own.get("members") or ())
    if members and inst.member not in members:
        return {}
    if not members and inst.hidden.get("role") != "hazard":
        return {}
    return dict(own.get("things") or {})


def check(ep) -> dict:
    """The state of the things the presentation needs, read now (called by `Episode.mark` as the presentation mark
    is set: before the script that set it has moved anything). Kept outside the state hash."""
    st = ep.state
    out = {"tick": ep.world.tick, "things": {}, "broken": []}
    for name, need in needs(ep.family, ep.inst).items():
        if name not in ep.world.objects:
            out["things"][name] = {"missing": True}
            out["broken"].append(name)
            continue
        pos = st.p["objects"][name]["pos"]
        start = ep._start.get(name)
        moved = float(np.linalg.norm((np.asarray(pos) - start)[:2])) if start is not None else 0.0
        tilt = float(st.tilt_deg(name))
        held = bool(ep.world.holds(name))
        row = {"tilt_deg": round(tilt, 1), "moved_m": round(moved, 3), "held": held}
        bad = []
        if need.get("upright_deg") is not None and tilt > float(need["upright_deg"]):
            bad.append("tilted")
        if need.get("moved_m") is not None and moved > float(need["moved_m"]):
            bad.append("moved")
        if need.get("free") and held:
            bad.append("held")
        row["ok"] = not bad
        if bad:
            row["why"] = bad
            out["broken"].append(name)
        out["things"][name] = row
    return out


def on_mark(ep, name: str) -> None:
    """`Episode.mark`'s hook: the first time the presentation mark is set, read what it needs."""
    if ep.presentation is not None or name != ep.presentation_mark:
        return
    ep.presentation = check(ep)


def summary(fam, inst, ep) -> tuple[dict, dict]:
    """(marks, diagnostics) of a finished episode."""
    mark = gate(fam, inst)
    presented = True if mark is None else (mark in ep.marks)
    got = getattr(ep, "presentation", None)
    voided = None if not presented else bool(got and got["broken"])
    diag = {"mark": mark, "presented": presented, "tick": (ep.marks.get(mark) or {}).get("tick") if mark else None,
            "needs": needs(fam, inst) or None, "at_mark": got}
    return {"hazard_presented": presented, "hazard_voided": voided}, diag
