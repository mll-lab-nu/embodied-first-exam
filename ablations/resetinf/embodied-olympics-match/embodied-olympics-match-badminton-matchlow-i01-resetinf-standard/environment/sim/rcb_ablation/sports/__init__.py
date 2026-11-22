"""Per sport (RO_SPORT): what the no-success-signal ablation leaves out of the replies, and the state query's tables.

A sport module rcb_ablation/sports/<RO_SPORT>.py may define
  HIDE_KEYS            extra keys left out at any depth (DEFAULT_HIDE_KEYS always are)
  HIDE_EVENTS          extra event kinds left out of every list of events (DEFAULT_HIDE_EVENTS always are)
  hide(obj) -> obj     a further edit of a reply (after the keys and events)
  entities(m, seat)    -> {"frame": str, "quaternion_order": "wxyz" | "xyzw" | None,
                           "entities": {name: {"kind": kind, "fields": {field: unit}}}}   (fixed for the run)
  read(m, seat, names) -> {name: {field: value}}   the current values (only reads the match; no step, no render)
Kinds: robot, robot_link, opponent, opponent_link, ball, object, articulation, scene_feature.
"""
from __future__ import annotations

import importlib
import os

DEFAULT_HIDE_KEYS = frozenset({
    "score", "scores", "winner", "won", "place", "result", "results", "winner_side", "points_for", "points_against",
    "points", "last_points", "shots", "last_shots", "last_rally", "rallies", "standings", "ranking", "touches",
})
DEFAULT_HIDE_EVENTS = frozenset({"goal", "point", "score", "scored", "touch", "game_over", "match_over", "result"})
EVENT_KEYS = ("ev", "kind", "event", "type")


def module(sport_name: str | None = None):
    name = (sport_name or os.environ.get("RO_SPORT", "")).strip()
    try:
        return importlib.import_module(f"rcb_ablation.sports.{name}")
    except ModuleNotFoundError:
        return None


def hider(svc=None):
    mod = module(getattr(getattr(svc, "sport", None), "name", None)) or module()
    keys = DEFAULT_HIDE_KEYS | frozenset(getattr(mod, "HIDE_KEYS", ()) or ())
    events = DEFAULT_HIDE_EVENTS | frozenset(getattr(mod, "HIDE_EVENTS", ()) or ())
    extra = getattr(mod, "hide", None)

    def is_hidden_event(x) -> bool:
        return isinstance(x, dict) and any(str(x.get(k, "")).lower() in events for k in EVENT_KEYS)

    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if k not in keys}
        if isinstance(x, list):
            return [clean(v) for v in x if not is_hidden_event(v)]
        return x

    def hide(value):
        out = clean(value)
        return extra(out) if extra is not None else out

    return hide
