"""Contract ② (docs/framework_zh.md §4.2): the one interface between the core and a sport (sports/<sport>/).

A sport's plugin module exports SPORT. The core calls only the functions below and never names a sport; a sport never
imports another sport. A sport answers four questions, one group of functions each (10 required):

  world        Sport.build(cfg) -> Match   Match.step() -> events   Match.state_digest() -> hex
  actions      Match.schema(seat)          Match.apply(seat, low_cmd) -> info
               optional high-level plugin: Sport.action_layer(level) -> ActionLayer whose lower() turns a high-level
               command into a low-level one (the episode log holds LOW-LEVEL commands only)
  referee      Match.phase() -> Phase      Match.scores() -> {side: n}   Match.tiebreaks() -> [(name, rule)]
               optional: to_move(), forfeit(), resume(), retire(), ranking()
  observation  Match.observe(seat, query) -> dict (own body + referee information, whitelisted in sport.toml)
               Match.cameras(seat, query) -> [camera definitions] (drawn by the task's renderer, renderers/)

Optional hooks have defaults in MatchBase; none of them is required by every sport, and the core never branches on a
sport. Stage-0 hooks (all optional): sides != seats (MatchConfig.sides, Match.entities: one act in flight per entity),
N sides with a classification (Match.ranking) and in-match retirement (Match.retire), a delayed effect
(ActionLayer.delay_steps), observation parameters (the `query` of observe/cameras), a team channel (core/channel.py,
declared in sport.toml) and a scored single format without an opponent (tiebreaks() == []).

Reply images (core 0.2.8, optional): Match.reply_views(seat, cmd, info) names the cameras (and optionally a short
strip of frames) that show the result of an action; the core snapshots them under the lock right after the action
took effect, draws them off the lock with the task's renderer (the path of the observation images) and attaches them
to the action's reply as `observation` (image_png_b64 + tiles, as /observe). In the turn protocol the core also tells
the sport whose review is due (Match.awaiting_review), so that a sport serving images only on turn can hold them
back from the other seats while the actor reviews.

Presentation (core 0.2.4, optional, spectators only): sports/<sport>/presentation/presentation.toml dresses the scene
of Sport.scene(cfg) for spectator renderers (renderers/presentation; e.g. fine visual meshes on a robot's bodies,
same kinematics). It is not part of the simulator directory and never reaches the players' images, unless the sport
declares `players` there (core 0.2.9): then the generator bundles it (and the models' files) into the simulator and
the players' images are drawn from it (core/observe.players_scene; a sport drawing its own images uses
renderers.players_model).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class MatchConfig:
    sport: str
    format: str                       # single | duel | team | multi (the sport declares which it supports)
    seats: tuple[str, ...]            # e.g. ("A", "B"); the HTTP addresses /<seat>/<endpoint>
    seed: int
    first: str | None = None          # the side that starts (serves / throws first; the rules say what that means)
    slowdown: float | None = None     # realtime only
    level: int | None = None          # scripted opponent level (single)
    action_level: str = "high"        # high | low
    play: str = "program"             # program | direct
    params: dict = field(default_factory=dict)
    sides: dict | None = None         # seat -> side; default: every seat is its own side
    renderer: str | None = None       # the renderer of the players' images (renderers/; None = the default)

    def side_of(self, seat: str) -> str:
        return (self.sides or {}).get(seat, seat)

    def side_list(self) -> list[str]:
        out: list[str] = []
        for s in self.seats:
            if self.side_of(s) not in out:
                out.append(self.side_of(s))
        return out

    def seats_of(self, side: str) -> list[str]:
        return [s for s in self.seats if self.side_of(s) == side]

    def to_json(self) -> dict:
        d = asdict(self)
        d["seats"] = list(self.seats)
        return d

    @staticmethod
    def from_json(d: dict) -> "MatchConfig":
        known = {f.name for f in fields(MatchConfig)}
        return MatchConfig(**{**{k: v for k, v in d.items() if k in known}, "seats": tuple(d["seats"])})


PLAYING, UNIT_OVER, FINISHED = "playing", "unit_over", "finished"


@dataclass
class Phase:
    state: str                        # PLAYING | UNIT_OVER | FINISHED
    review: tuple[str, ...] = ()      # seats that review before play resumes (realtime: usually all seats)
    reason: str = ""


class Refused(Exception):
    """An action the core must refuse: HTTP `code` (400 bad body, 409 wrong time) with `message`."""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code
        self.cause = ""                                       # parse_action: the hidden exception (logs only)


Tiebreak = tuple[str, Callable[["Match"], "str | None"]]      # (name, rule) -> winning side or None (undecided)


class Match(Protocol):
    k: int                                                    # [R] control steps (realtime) / actions (turn) so far
    dt: float                                                 # [R realtime] control step, seconds

    # world
    def step(self) -> list[dict]: ...                         # [R realtime] advance one control step; events
    def state_digest(self) -> str: ...                        # [R] hex digest of everything that affects the score
    # actions
    def schema(self, seat: str) -> dict: ...                  # [R] the low-level command types and ranges (/spec)
    def apply(self, seat: str, cmd: dict) -> dict: ...        # [R] a LOW-LEVEL command takes effect now; info
    # referee
    def phase(self) -> Phase: ...                             # [R]
    def scores(self) -> dict[str, float]: ...                 # [R] by side (informational: tiebreaks decide)
    def tiebreaks(self) -> list[Tiebreak]: ...                # [R] rulebook -> extra play -> last resort; [] = solo
    # observation
    def observe(self, seat: str, query: dict | None = None) -> dict: ...      # [R] own body + referee information
    def cameras(self, seat: str, query: dict | None = None) -> list[dict]: ...  # [R] camera definitions (renderers/)


class MatchBase:
    """Defaults of every optional hook (a sport subclasses this and overrides what it needs)."""
    k = 0
    dt = 0.0
    awaiting_review = None                                    # turn protocol, set by the core: the seat whose review
    #                                                           is due now (None: nobody's); never part of the digest

    # referee
    def resume(self) -> None:                                 # leaving a review: frozen-time work (next serve ...)
        pass

    def to_move(self):                                        # turn protocol: the seat whose turn it is
        return None

    def forfeit(self, seat, why) -> bool:                     # record a core decision inside the world (True)
        return False

    def retire(self, side, why) -> bool:                      # N sides: True = the match goes on without `side`
        return False

    def ranking(self):                                        # N sides: the classification, best first
        return None

    def unit(self) -> int:                                    # index of the current unit (acts of an old unit drop)
        return 0

    # actions
    def schema(self, seat) -> dict:
        return {}

    def entities(self, seat) -> tuple[str, ...]:              # what a seat commands; one act in flight per entity
        return ()

    # observation
    def cameras(self, seat, query=None) -> list[dict]:
        return []

    def render_state(self) -> dict:                           # what a renderer needs to draw the scene now
        return {}

    def camera_job(self, seat):                               # a sport that draws its own images: (job, meta)
        return None, {}

    def reply_views(self, seat, cmd, info) -> dict | None:
        """The images of an action's result for its reply (core 0.2.8), or None. Called under the lock right after
        Match.apply(seat, cmd) returned `info` (realtime: only for an act without a delayed effect); it must not change
        the match, and what it returns must follow from the match state and (seat, cmd, info) alone, so that a replay
        can draw the same images (python -m core.episode PLUGIN DIR --reply N).
          {"frames": [{"cameras": [camera definitions, as cameras()],
                       "state": render state (optional; default: render_state() now),
                       "label": short text (optional, e.g. "-200 ms"; shown in the tiles)}, ...],
           "order": "frame" (default: frame after frame) | "camera" (camera after camera: one strip per camera),
           "columns": tiles per row (default: sport.toml [observation] columns),
           "note": one line for the player (optional)}
        Drawn like the observation images: the task's renderer, the match scene (never a presentation scene),
        sport.toml [observation] frame_budget_ms for the whole reply image."""
        return None

    def final_fields(self) -> dict:                           # sport fields for final.json
        return {}

    def continuous_score(self):                               # sport.toml [score] from = "hook": {side: number},
        return None                                           # larger is better (core/score.py, core 0.2.14)

    def broadcast_frame(self):                                # spectator frame (never read back)
        return None


class ActionLayer(Protocol):
    level: str                                                # "high" | "low"
    worker: str | None                                        # Sport worker kind that runs prepare(), or None
    delay_steps: int                                          # realtime: the effect is delay_steps after lowering

    def parse(self, seat: str, body: dict, match: Match, ctx: dict) -> dict: ...
    #   validate a request body (raise Refused); ctx = core facts at the request (e.g. both chess clocks), which the
    #   plugin may copy into the command so that replay sees them. Realtime: parse runs off the world lock and
    #   Match.apply later, at the effect step, where the core checks again only that the unit (Match.unit) is the same,
    #   so apply re-checks whatever else may have changed meanwhile (the phase, whose turn, a body's state) and returns
    #   {"rejected": why} (counted) for a command that no longer holds
    def snapshot(self, seat: str, cmd: dict, match: Match, ordinal: int) -> Any: ...   # under the lock, for prepare
    def prepare(self, job: Any) -> Any: ...                   # off the lock (in `worker` if set); expensive planning
    def lower(self, seat: str, cmd: dict, prepared: Any, match: Match) -> tuple[dict, dict]: ...
    #   at the effect boundary, cheap: -> (low-level command for Match.apply, info for the reply)
    def reply(self, seat: str, cmd: dict, info: dict, match: Match) -> dict: ...


class LowLayer:
    """The identity layer: the request body, validated by `validate(seat, body, match, ctx) -> cmd`, is the command."""
    level = "low"
    worker = None
    delay_steps = 0

    def __init__(self, validate):
        self._validate = validate

    def schema(self, match, seat):                            # what /spec shows of this layer's commands
        return match.schema(seat)

    def parse(self, seat, body, match, ctx):
        return self._validate(seat, body, match, ctx)

    def snapshot(self, seat, cmd, match, ordinal):
        return None

    def prepare(self, job):
        return None

    def lower(self, seat, cmd, prepared, match):
        return cmd, {}

    def reply(self, seat, cmd, info, match):
        return info


def check_command(schema: dict, body: dict) -> dict:
    """Validate a request body against a Match.schema() and return the clean command (raises Refused).

    schema = {TYPE: {FIELD: {"type": "number"|"integer"|"boolean"|"enum"|"vector", "min", "max", "values", "len",
                             "unit", "doc", "default"}}}; the command is {"type": TYPE, FIELD: value, ...}."""
    if not isinstance(body, dict):
        raise Refused("the action must be a JSON object")
    kind = body.get("type")
    if kind not in schema:
        raise Refused(f"unknown action type {kind!r}; one of {sorted(schema)}")
    out: dict = {"type": kind}
    spec = schema[kind]
    extra = sorted(set(body) - set(spec) - {"type", "entity"})
    if extra:
        raise Refused(f"unknown field(s) {extra} for {kind}")
    for name, f in spec.items():
        if name not in body:
            if "default" in f:
                out[name] = f["default"]
                continue
            raise Refused(f"{kind} needs {name}")
        out[name] = _value(name, f, body[name])
    if "entity" in body:
        out["entity"] = str(body["entity"])
    return out


def _value(name, f, v):
    t = f.get("type", "number")
    if t == "boolean":
        if not isinstance(v, bool):
            raise Refused(f"{name} must be true or false")
        return v
    if t == "enum":
        if v not in f["values"]:
            raise Refused(f"{name} must be one of {f['values']}")
        return v
    if t == "vector":
        if not isinstance(v, list) or len(v) != f["len"]:
            raise Refused(f"{name} must be a list of {f['len']} numbers")
        return [_number(f"{name}[{i}]", f, x) for i, x in enumerate(v)]
    x = _number(name, f, v)
    if t == "integer":
        if x != int(x):
            raise Refused(f"{name} must be an integer")
        return int(x)
    return x


def _number(name, f, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, int) and v.bit_length() > 60) or \
            not math.isfinite(v):
        raise Refused(f"{name} must be a finite number")
    lo, hi = f.get("min", -math.inf), f.get("max", math.inf)
    if not lo <= v <= hi:
        raise Refused(f"{name} must be in [{lo}, {hi}]")
    return round(float(v), f.get("digits", 6))


# ------------------------------------------------------------------ request validation (core 0.2.11)
# Every request body is checked before an endpoint reads it (check_body), and every act body against the action
# layer's published schema before the layer parses it (check_action). A body that fails, or that makes the layer's
# parse raise ANY exception, is the player's own error: refused (HTTP 400, counted), never a technical failure.
BODY_MAX_DEPTH = 10            # nesting of lists / objects (the body object is depth 1)
BODY_MAX_ITEMS = 4096          # elements of one list, keys of one object
BODY_MAX_STR = 8192            # characters of one string (keys included)
BODY_MAX_ABS = 1e15            # |number|: no action of any sport needs more (and a huge integer overflows a float)
TYPE_MAX_STR = 64              # characters of the action type


def check_body(value, depth: int = 1) -> None:
    """Generic sanity of a decoded JSON request body (raises Refused): finite, bounded numbers; bounded strings, list
    lengths and nesting."""
    if depth > BODY_MAX_DEPTH:
        raise Refused(f"the request is nested deeper than {BODY_MAX_DEPTH} levels")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > BODY_MAX_STR:
            raise Refused(f"strings are limited to {BODY_MAX_STR} characters")
        return
    if isinstance(value, int):
        if value.bit_length() > 60 or abs(value) > BODY_MAX_ABS:
            raise Refused(f"numbers are limited to +-{BODY_MAX_ABS:g}")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) > BODY_MAX_ABS:
            raise Refused(f"numbers must be finite and within +-{BODY_MAX_ABS:g}")
        return
    if isinstance(value, (list, dict)):
        if len(value) > BODY_MAX_ITEMS:
            raise Refused(f"lists and objects are limited to {BODY_MAX_ITEMS} items")
        for k in value if isinstance(value, dict) else ():
            if not isinstance(k, str) or len(k) > BODY_MAX_STR:
                raise Refused("object keys must be strings")
        for x in value.values() if isinstance(value, dict) else value:
            check_body(x, depth + 1)
        return
    raise Refused("unsupported JSON value")


def _is_num(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float))


def _lens(spec_len) -> set | None:
    """A field's declared length: an int, or a text such as "1 or 2" (None: not declared)."""
    if isinstance(spec_len, int) and not isinstance(spec_len, bool):
        return {spec_len}
    if isinstance(spec_len, str):
        return {int(x) for x in spec_len.replace(",", " ").split() if x.isdigit()} or None
    return None


def _check_field(kind: str, name: str, f, v) -> None:
    """The shape of one declared field (ranges and meaning stay with the layer's parse)."""
    if not isinstance(f, dict):
        return
    t, where = f.get("type", "number"), f"{kind}.{name}"
    if t in ("number", "integer"):
        if not _is_num(v):
            raise Refused(f"{where} must be a number")
    elif t == "boolean":
        if not isinstance(v, bool):
            raise Refused(f"{where} must be true or false")
    elif t == "enum":
        if isinstance(v, (list, dict)):
            raise Refused(f"{where} must be one of {f.get('values')}")
    elif t == "vector":
        lens = _lens(f.get("len"))
        if not isinstance(v, list) or (lens and len(v) not in lens) or not all(_is_num(x) for x in v):
            raise Refused(f"{where} must be a list of {f.get('len', 'some')} numbers")
    elif t == "rows":
        lens, top = _lens(f.get("len")), f.get("max_rows")
        if not isinstance(v, list) or (isinstance(top, int) and len(v) > top) or not all(
                isinstance(r, list) and (not lens or len(r) in lens) and all(_is_num(x) for x in r) for r in v):
            raise Refused(f"{where} must be a list of rows of {f.get('len', 'some')} numbers"
                          + (f", at most {top} rows" if isinstance(top, int) else ""))
    elif t == "list":
        if not isinstance(v, list):
            raise Refused(f"{where} must be a list")
    elif t == "object":
        if not isinstance(v, dict):
            raise Refused(f"{where} must be an object")
        keys = f.get("keys")
        if isinstance(keys, (list, tuple)) and set(v) - set(keys):
            raise Refused(f"{where}: unknown key(s) {sorted(set(v) - set(keys))[:8]}; the keys are {list(keys)}")


def check_action(schema, body) -> None:
    """An act body against the action layer's published schema, before the layer parses it (raises Refused). The
    type, if given, must be a short string; for a type the schema names, each declared field that is present must
    have its shape (number, boolean, scalar enum value, vector / rows lengths, list, object keys). Unknown types and
    fields, ranges and defaults stay with the layer's parse (a layer may take an implicit type)."""
    if not isinstance(body, dict):
        raise Refused("the action must be a JSON object")
    kind = body.get("type")
    if kind is not None and (not isinstance(kind, str) or len(kind) > TYPE_MAX_STR):
        raise Refused(f"type must be a string of at most {TYPE_MAX_STR} characters")
    spec = schema.get(kind) if isinstance(schema, dict) and kind is not None else None
    if isinstance(spec, dict):
        for name, f in spec.items():
            if name in body:
                _check_field(kind, name, f, body[name])


def parse_action(layer, seat: str, body, match, ctx: dict):
    """What the core runs for every act (and core.local for built-in players): check_body, check_action against the
    layer's schema (what /spec shows), then layer.parse. ANY exception on the way is the player's own error: Refused
    (HTTP 400); a malformed action never ends a match as a technical failure. The exception's text is not shown to
    the player; the caller may log it (`Refused.cause`). A seat without entities (Match.entities) may not name one
    (core 0.2.13): realtime acts are one in flight per (seat, entity)."""
    try:
        check_body(body)
        check_action(layer.schema(match, seat) if hasattr(layer, "schema") else {}, body)
        if "entity" in body and not match.entities(seat):
            raise Refused("unknown field entity: this seat commands no entities")
        return layer.parse(seat, body, match, ctx)
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001
        err = Refused("invalid action: the action layer could not read it (see /spec for the command schema)")
        err.cause = f"{type(exc).__name__}: {str(exc)[:200]}"
        raise err from exc


class SchemaLayer(LowLayer):
    """The default low level: the body is checked against Match.schema(seat); `ctx_keys` copies core facts (e.g. the
    chess clocks) into the command so that the replay sees them."""

    def __init__(self, ctx_keys: tuple[str, ...] = ()):
        super().__init__(None)
        self.ctx_keys = ctx_keys

    def parse(self, seat, body, match, ctx):
        cmd = check_command(match.schema(seat), body)
        ents = tuple(match.entities(seat))
        if ents and cmd.get("entity", ents[0]) not in ents:
            raise Refused(f"entity must be one of {list(ents)}")
        if ents:
            cmd.setdefault("entity", ents[0])
        for k in self.ctx_keys:
            cmd[k] = ctx.get(k)
        return cmd


class Sport(Protocol):
    name: str
    protocol: str                     # "realtime" | "turn"
    revision: str                     # bump on any change that alters play
    source_dirs: list[str]            # whose files enter source_sha (the plugin dir; the core adds itself)

    def build(self, cfg: MatchConfig) -> Match: ...
    def action_layer(self, level: str) -> ActionLayer: ...
    def spec(self, cfg: MatchConfig, seat: str, match: Match) -> dict: ...
    # optional: the scene for renderers, worker processes (render / plan), built-in players
    def scene(self, cfg: MatchConfig): ...                    # renderers.base.Scene (needed when cameras() is used);
    #                                                           the MATCH scene: the base of the presentation scene
    #                                                           (sports/<s>/presentation) and the players' images
    #                                                           unless that declares `players`
    def worker_init(self, kind: str, seat: str, cfg: MatchConfig) -> Any: ...
    def worker_call(self, obj: Any, kind: str, job: Any) -> dict: ...
    def players(self) -> dict: ...                            # {name: factory(spec, seat, seed) -> built-in player}


def sha_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=float).encode()).hexdigest()
