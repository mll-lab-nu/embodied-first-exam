"""The match extension of eai-standard/3.0 (docs/protocol/standard_mode.md Part 5): the standard endpoints and the match's
own calls, translated onto the match service's methods (the same methods the core's seat API /<SEAT>/<ep> calls).

    GET  /spec      the match's spec as an eai-standard spec (+ `match`: the core's own spec, as `game spec` gives it)
    GET  /status    the state, no images
    POST /observe   {cameras, last_s, video, query, team_since}: the observation as RCB1 (last/ and frames/ per camera);
                    it never waits and never lets time pass (eai-standard/3.0)
    POST /submit    {type, dt, at, entity, rows}: action rows (commands); realtime: a plan from step `at`;
                    {type, interpolate: "hold", seconds} without rows: a hold chunk (eai-standard/3.0)
    POST /start     extension: you are ready (the core's `start`)
    POST /ready     extension: {why, plan}, your review (the core's `ready`)
    POST /say       extension (team formats): {text}
    POST|GET /team  extension (team formats): {since}

Every answer's meta carries the match: `score`, `review_due`, `match_over` (and `phase`, `world`, `state`: the core's
state of the seat). Three clocks, one per core service: realtime (core/realtime.py, the realtime layer's clock: /submit answers at
once, the rows become a plan), lockstep (core/lockstep.py, standard mode: /submit executes the rows, the world waits) and
turn (core/turn.py: one action per turn, a review after each).

eai-standard/3.0: /observe is a read that answers at once (`seconds` > 0 is a 400); time passes only through /submit,
and a rows-free hold chunk {"type", "interpolate": "hold", "seconds": n} lets it pass without a new command (lockstep:
the core's wait for n game seconds; realtime: the plan of the entity cleared from `at` for n seconds, the command in
force kept; turn-based: a wait of up to n real seconds for your turn). The match keeps no record of earlier frames:
`last_s` > 0 answers with the sport's own frames of now (a declared deviation, /spec timing.deviations)."""
from __future__ import annotations

import base64
import json
import math
import os
import threading
import time
import traceback
from pathlib import Path

import numpy as np

from core.sport import Refused

from . import pngdec, rcb1

try:                                      # core >= 0.2.x: the body check of the seat API (size, finite numbers)
    from core.sport import check_body
except ImportError:  # pragma: no cover
    check_body = None

PROTOCOL = "eai-standard/3.0"
HOLD_HINT = ('observe never lets time pass (eai-standard/3.0): to let n seconds pass, submit a hold chunk {"type": <type>, '
             '"interpolate": "hold", "seconds": n} with no rows; the match keeps no recorder: last_s = n answers with '
             "the sport's own frames of now")
HOLD_HINT_RT = ("observe reads the recorder only and never waits (eai-standard/3.0): send last_s = n for the last n seconds "
                "already recorded (0: the current frame)")
MAX_REQUEST_BYTES = 8 << 20
MAX_JSON_ROWS = 1000
MAX_CHUNK_S = 10.0                        # game seconds a chunk may cover
TURN_WAIT_MAX_S = 60.0                    # turn-based: max_chunk_s, the real seconds a hold chunk may wait for your turn
MAX_AHEAD_S = 10.0                        # realtime: `at` at most this far ahead (game seconds)
MAX_VIDEO_FPS = 30                        # video_fps lies in [1, 30] (eai-standard/3.0); the match renders the
                                          # sport's own frames, so the value is checked, then not used
RECENT_EFFECTS = 64
STATE_KEYS_SKIP = {"team_messages", "ready", "retired"}
_MISSING = object()


class BadRequest(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------------------------------- pure helpers
def flatten(obj, prefix="", out=None, limit=512):
    """The numeric leaves of the seat's state (dotted names, list indices in brackets): meta.proprio."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return out
    if isinstance(obj, (int, float)):
        if math.isfinite(float(obj)):
            out.append((prefix, float(obj)))
        return out
    if isinstance(obj, dict):
        for k in sorted(obj, key=str):
            if prefix == "" and k in STATE_KEYS_SKIP:
                continue
            flatten(obj[k], f"{prefix}.{k}" if prefix else str(k), out, limit)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}[{i}]", out, limit)
    return out


def columns_of(fields) -> list | None:
    """The float32 row layout of an action type, from a core schema {FIELD: {"type": number|integer|boolean|enum|
    vector, ...}}: [(field, kind, n, spec)], or None when a field has no numeric form."""
    if not isinstance(fields, dict):
        return None
    cols = []
    for name, f in fields.items():
        if not isinstance(f, dict):
            return None
        t = f.get("type")
        if t in ("number", "integer", "boolean"):
            cols.append((name, t, 1, f))
        elif t == "enum" and isinstance(f.get("values"), list) and f["values"]:
            cols.append((name, t, 1, f))
        elif t == "vector" and isinstance(f.get("len"), int) and f["len"] > 0:
            cols.append((name, t, int(f["len"]), f))
        else:
            return None
    return cols


def layout_names(cols) -> list:
    out = []
    for name, _t, n, _f in cols:
        out += [name] if n == 1 else [f"{name}[{i}]" for i in range(n)]
    return out


def row_from_floats(kind, cols, row) -> dict:
    """One float32 row -> an action object. All columns of a field with a default NaN = that default (omitted)."""
    out, i = {"type": kind}, 0
    for name, t, n, f in cols:
        v = [float(x) for x in row[i:i + n]]
        i += n
        if all(math.isnan(x) for x in v):
            if "default" in f:
                continue
            raise BadRequest(f"{kind}.{name}: NaN (only a field with a default may be left out, all its columns NaN)")
        if any(not math.isfinite(x) for x in v):
            raise BadRequest(f"{kind}.{name}: not a finite number")
        if t == "vector":
            out[name] = v
            continue
        x = v[0]
        if t == "number":
            out[name] = x
        elif t == "integer":
            if x != int(x):
                raise BadRequest(f"{kind}.{name}: an integer is required")
            out[name] = int(x)
        elif t == "boolean":
            if x not in (0.0, 1.0):
                raise BadRequest(f"{kind}.{name}: 0 or 1 is required")
            out[name] = bool(x)
        else:                                            # enum: the index into `values`
            if x != int(x) or not 0 <= int(x) < len(f["values"]):
                raise BadRequest(f"{kind}.{name}: an index into {f['values']} is required")
            out[name] = f["values"][int(x)]
    return out


def cam_size(cam: dict) -> tuple[int, int]:
    """(width, height) of a camera definition: width / height (renderers/base.py CameraDef) or tile_px (the sports that
    draw their own sheet: table tennis, badminton)."""
    if "width" in cam:
        return int(cam["width"]), int(cam["height"])
    w, h = cam["tile_px"]
    return int(w), int(h)


def calibration(cam: dict) -> dict | None:
    """intrinsic_cv / extrinsic_cv / cam2world_gl of a core camera definition (renderers/base.py CameraDef: pos, lookat,
    up, fovy_deg, width, height; or position, forward, up, fovy_deg, tile_px; pinhole, u right, v down)."""
    try:
        pos = np.asarray(cam["pos"] if "pos" in cam else cam["position"], float)
        fwd = np.subtract(cam["lookat"], pos) if "lookat" in cam else np.asarray(cam["forward"], float)
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, cam.get("up", (0, 0, 1)))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        w, h = cam_size(cam)
        f = (h / 2) / math.tan(math.radians(float(cam.get("fovy_deg", 45.0))) / 2)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not all(np.isfinite(v).all() for v in (pos, fwd, right, up)):
        return None
    R = np.stack([right, -up, fwd])                      # world -> camera, OpenCV axes (x right, y down, z forward)
    ext = np.concatenate([R, (-R @ pos)[:, None]], axis=1)
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R.T, pos
    gl = T @ np.diag([1.0, -1.0, -1.0, 1.0])
    return {"intrinsic_cv": [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]], "extrinsic_cv": ext.tolist(),
            "cam2world_gl": gl.tolist(), "image_size": [w, h]}


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x


# ---------------------------------------------------------------------------------------------------- the adapter
class Adapter:
    def __init__(self, svc, data: Path | None = None, seat: str | None = None):
        self.svc = svc
        builtin = {x.split("=", 1)[0].strip() for x in os.environ.get("RO_BUILTIN_SEATS", "").split(",") if "=" in x}
        players = [s for s in svc.cfg.seats if s not in builtin] or list(svc.cfg.seats)
        self.seat = seat or os.environ.get("EAI_STD_SEAT") or players[0]
        if self.seat not in svc.cfg.seats:
            raise ValueError(f"EAI_STD_SEAT {self.seat!r} is not a seat of this match")
        self.clock = "turn" if svc.protocol == "turn" else ("lockstep" if hasattr(svc, "may_step") else "realtime")
        self.protocol = PROTOCOL
        self.dt = None if self.clock == "turn" else float(svc.m.dt)
        self.lock = threading.Lock()
        self.calls = self.chunk_id = self.obs_id = 0
        self.t_first = None
        self.wall_s = float(os.environ.get("RCB_WALL_CLOCK_S", "0") or 0) or None
        self.tl = threading.local()
        self.effects: list = []                          # realtime: effect records not yet reported to the agent
        self.effect_log = {"rows": 0, "late_rows": 0, "late_steps": 0, "dropped_rows": 0, "refused_rows": 0}
        self.plan: dict = {}                             # realtime: entity -> [row, ...] by step
        self.dispatchers: dict = {}
        data = Path(data or os.environ.get("RCB_DATA", "/data"))
        try:
            self.log_f = open(data / "eai_std_calls.jsonl", "a", buffering=1)
        except OSError:
            self.log_f = None
        if hasattr(svc, "seen"):                         # realtime cores: the reaction report's `seen` (core 0.2.18)
            orig = svc.state

            def state(seat, *a, **kw):                   # a state the dispatcher's act reply carries never reached
                internal = getattr(self.tl, "internal", False) and seat == self.seat   # the agent
                prev = svc.seen.get(seat, _MISSING) if internal else None
                out = orig(seat, *a, **kw)
                if internal:
                    if prev is _MISSING:
                        svc.seen.pop(seat, None)
                    else:
                        svc.seen[seat] = prev
                return out
            svc.state = state

    # ------------------------------------------------------------------ bookkeeping
    def log(self, **row):
        if self.log_f is not None:
            try:
                self.log_f.write(json.dumps(jsonable({"t": round(time.time(), 4), **row}), default=str) + "\n")
            except (OSError, ValueError):
                pass

    def first_request(self):
        if self.t_first is None:
            with self.lock:
                if self.t_first is None:
                    self.t_first = time.monotonic()
                    self.log(ev="first_request")

    def core(self, ep, body=None, post=True):
        """One call of the match service's own handler, with the seat API's error mapping (core/http.py)."""
        svc = self.svc
        try:
            if post:
                body = {} if body is None else body
                if check_body is not None:
                    check_body(body)
            fn = svc.routes(post).get(ep)
            if fn is None:
                return 404, {"error": "unknown endpoint"}
            code, out = fn(self.seat, body)
        except Refused as exc:
            code, out = exc.code, {"error": str(exc)}
        except (ValueError, TypeError, KeyError, OverflowError):
            code, out = 400, {"error": "invalid request"}
        except BlockingIOError as exc:
            code, out = 429, {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            svc.failure(ep, exc)
            code, out = 500, {"error": "technical failure"}
        if hasattr(svc, "public"):
            out = svc.public(out)
        return code, out

    @staticmethod
    def now_of(out) -> dict | None:
        if not isinstance(out, dict):
            return None
        st = out.get("now") if isinstance(out.get("now"), dict) else out.get("state")
        return st if isinstance(st, dict) else None

    def over(self) -> bool:
        return self.svc.phase == "over"

    def review_due(self) -> bool:
        svc = self.svc
        if self.clock == "turn":
            return svc.phase == "play" and getattr(svc, "review_due", None) == self.seat
        if svc.phase != "review":
            return False
        try:
            return self.seat in svc.due() and not svc.seats[self.seat].ready
        except Exception:  # noqa: BLE001
            return False

    def planned_rows(self) -> int:
        unit = self.svc.m.unit()
        return sum(1 for rows in self.plan.values() for r in rows if r["unit"] == unit)

    def meta(self, now: dict | None, **extra) -> dict:
        svc = self.svc
        with svc.cond:
            k = int(svc.m.k)
            phase, reason = svc.phase, svc.reason
            try:
                scores = jsonable(svc.m.scores())
            except Exception:  # noqa: BLE001
                scores = None
            due = self.review_due()
            rt = {}
            if self.clock == "realtime":
                lag = 0.0
                if phase == "running" and svc.anchor is not None:
                    a, k0 = svc.anchor
                    lag = max(0.0, time.monotonic() - (a + (k - k0 + 1) * svc.period))
                rt = {"running": phase == "running", "planned_steps": self.planned_rows(), "lag_s": round(lag, 4)}
        t = time.monotonic()
        time_s = 0.0 if self.t_first is None else t - self.t_first
        st = now or {}
        pro = flatten(st)
        with self.lock:
            self.calls += 1
            calls = self.calls
        m = {"protocol": self.protocol, "step": k, "control_steps": k, "physics_steps": None,
             "sim_time_s": None if self.dt is None else round(k * self.dt, 6), "calls": calls,
             "time_s": round(time_s, 3),
             "time_left_s": None if self.wall_s is None else round(max(0.0, self.wall_s - time_s), 3),
             "done": phase == "over", "reason": reason if phase == "over" else None,
             "proprio": {"layout": [n for n, _ in pro], "now": [v for _, v in pro]},
             "stopped": None,
             # the match (owner 2026-11-25): in every answer
             "score": scores, "side": svc.cfg.side_of(self.seat), "review_due": bool(due) and phase != "over",
             "match_over": phase == "over", "phase": phase, "world": st.get("world"), "state": st, **rt}
        if self.clock == "realtime" and "effects" not in extra:
            m["effects"] = self.take_effects()          # the planned rows' effects since the last answer (the realtime plan)
        m.update(extra)
        return jsonable(m)

    # ------------------------------------------------------------------ spec / status
    def spec(self) -> dict:
        code, core = self.core("spec", None, post=False)
        if code != 200:
            raise BadRequest(core.get("error", "spec unavailable"), code)
        svc = self.svc
        schema = self.schema_of(core)
        with svc.cond:
            try:
                entities = [str(e) for e in svc.m.entities(self.seat)]
            except Exception:  # noqa: BLE001
                entities = []
        types = {}
        for kind, fields in schema.items():
            cols = columns_of(fields)
            types[kind] = {"kind": "command", "interpolable": False, "fields": fields,
                           "dim": None if cols is None else sum(c[2] for c in cols),
                           "layout": None if cols is None else layout_names(cols),
                           "rows": ("JSON action objects (RCB1 part `actions` of kind json, or `rows` of a JSON body)"
                                    + ("" if cols is None else "; or float32 rows in `layout` order (an enum as the index "
                                       "of its value, a boolean as 0 / 1; all columns of a field with a default NaN = "
                                       "that default)"))}
        cams = {}
        for c in core.get("cameras") or []:
            if isinstance(c, dict) and c.get("name"):
                cal = calibration(c) or {}
                try:
                    size = dict(zip(("width", "height"), cam_size(c)))
                except (KeyError, TypeError, ValueError):
                    size = {}
                cams[str(c["name"])] = {**size, **{k: c[k] for k in ("fovy_deg", "focal_px", "principal_point_px")
                                                   if k in c},
                                        **({"intrinsic_cv": cal["intrinsic_cv"],
                                            "pose_at_spec": {"extrinsic_cv": cal["extrinsic_cv"],
                                                             "cam2world_gl": cal["cam2world_gl"]}} if cal else {})}
        types_note = ("the types of the match's schema (spec match.actions); a type the task text names besides "
                         "them (e.g. a toss) is sent the same way, as JSON rows; the match checks every row when it is "
                         "sent (an invalid row: 400 in standard mode, meta.effects `code` 400 in realtime)")
        out = {"protocol": self.protocol, "simulator": "embodied-olympics core",
               "sport": svc.sport.name, "revision": core.get("revision"), "seat": self.seat, "side": core.get("side"),
               "format": core.get("format"), "action_level": core.get("action_level"),
               "control_hz": None if not self.dt else round(1.0 / self.dt, 6), "physics_substeps": None,
               "control_dt": self.dt, "max_chunk_s": self.max_chunk_s, "max_chunk_rows": MAX_JSON_ROWS,
               "max_video_fps": MAX_VIDEO_FPS,
               "max_request_bytes": MAX_REQUEST_BYTES, "entities": entities,
               "cameras": cams, "action_types": {**types, "not_yet": []}, "action_types_note": types_note,
               "proprio_layout": None,
               "proprio_note": ("meta.proprio = the numeric leaves of meta.state (your seat's state as the match gives "
                                "it), each answer with its own layout (lists such as events change its length); no "
                                "per-frame proprio part"),
               "depth": {"modes": ["none"], "default": "none"},
               "budget": {"reset": 0, "steps": None, "wall_clock_s": self.wall_s,
                          "clock": "time_s counts from your first request to the service (any endpoint, the "
                                   "/<SEAT>/ API included); the match's own clocks are in `timing` and `match`"},
               "timing": self.timing(core),
               "endpoints": ENDPOINTS, "finish": "not offered (404): the match's rules end the episode",
               "reset": "not offered (404): one match", "kinematics": "not offered (404)",
               "rate_limit": "20 requests per second and 4 open requests for your seat, the /<SEAT>/ API included; "
                             "a refusal is a 429 with an empty body (retry more slowly)",
               "seat_api": f"/{self.seat}/<call> (the `game` command): the same match, the core's own calls",
               "match": core}
        if getattr(svc, "channel", None) is not None and svc.channel.enabled:
            out["team_channel"] = core.get("team_channel")
        return jsonable(out)

    def schema_of(self, core: dict) -> dict:
        """The action schema: the spec's `actions`, or, where the sport's spec text replaces it with a description
        (soccer_ssl: sport.toml [spec] actions), the action layer's own schema (core/service.py public_spec's source)."""
        if isinstance(core.get("actions"), dict):
            return core["actions"]
        layer = getattr(self.svc, "layer", None)
        try:
            with self.svc.cond:
                out = layer.schema(self.svc.m, self.seat) if hasattr(layer, "schema") else {}
        except Exception:  # noqa: BLE001
            out = {}
        return out if isinstance(out, dict) else {}

    def timing(self, core) -> dict:
        ct = core.get("timing") or {}
        if self.clock == "turn":
            return {"realtime": False, "clock": "turn", "chess_clock": core.get("clock"), "start": core.get("start"),
                    "rule": "one action per turn (/submit, one row), then your review (/ready); a hold chunk "
                            "{type, interpolate: hold, seconds: n} waits for your turn (at most n real seconds)",
                    "deviations": DEVIATIONS["turn"]}
        base = {"control_dt": self.dt, "review_timeout_s": ct.get("review_timeout_s"),
                "review_timeout_rule": ct.get("review_timeout_rule"), "start": core.get("start"),
                "reaction_delay_steps": ct.get("reaction_delay_steps"), "effect_delay_steps": ct.get("effect_delay_steps")}
        if self.clock == "lockstep":
            return {"realtime": False, "clock": "lockstep", **base, "rule": ct.get("rule"),
                    "submit": "the rows run one after the other: row i takes effect at the control step the world is "
                              "at when it is sent, then the world advances dt (rows x dt in all); /submit returns "
                              "after the last row's dt",
                    "deviations": DEVIATIONS["lockstep"]}
        S = float(ct.get("slowdown") or self.svc.slowdown)
        return {"realtime": True, "clock": "realtime", "slowdown": S, "wall_s_per_control_step": self.dt * S,
                "max_ahead_steps": int(round(MAX_AHEAD_S / self.dt)), **base, "policy": ct.get("policy"),
                "deviations": DEVIATIONS["realtime"]}

    def status(self) -> dict:
        code, out = self.core("status", None, post=False)
        now = self.now_of(out) or (out if code == 200 and isinstance(out, dict) else {})
        return self.meta(now, ok=code == 200)

    # ------------------------------------------------------------------ requests
    def parse_submit(self, body: bytes, ctype: str) -> dict:
        if ctype.startswith("application/x-rcb1"):
            try:
                hdr, parts = rcb1.decode(body)
            except Exception as exc:  # noqa: BLE001
                raise BadRequest(f"malformed RCB1 body: {exc}")
            a = parts.get("actions")
            if a is None and isinstance(hdr, dict) and hdr.get("seconds") is not None:
                return {"hdr": hdr, "rows": None, "hold": self.hold_seconds(hdr)}   # a rows-free hold chunk
            if a is None:
                raise BadRequest("an RCB1 /submit needs a part `actions` (array float32 (T, dim), or json: a list of "
                                 "action objects)")
            rows = a["data"] if a["kind"] in ("json", "array") else None
            if a["kind"] == "array":
                rows = np.asarray(rows)
                if rows.ndim == 1:
                    rows = rows[None, :]
                if rows.ndim != 2:
                    raise BadRequest("actions: a (T, dim) array")
        else:
            try:
                hdr = json.loads(body or b"{}")
            except ValueError:
                raise BadRequest("malformed JSON body")
            if not isinstance(hdr, dict):
                raise BadRequest("a JSON object is required")
            rows = hdr.get("rows", hdr.get("actions"))
            if isinstance(rows, dict):
                rows = [rows]
        if not isinstance(hdr, dict):
            raise BadRequest("the header must be a JSON object")
        if hdr.get("seconds") is not None:              # a rows-free hold chunk (eai-standard/3.0)
            if rows is not None and len(rows) > 0:
                raise BadRequest("a chunk has either rows or `seconds` (a hold chunk without rows), not both")
            return {"hdr": hdr, "rows": None, "hold": self.hold_seconds(hdr)}
        if rows is None or len(rows) == 0:
            raise BadRequest("a chunk with no rows")
        if len(rows) > MAX_JSON_ROWS:
            raise BadRequest(f"at most {MAX_JSON_ROWS} rows")
        return {"hdr": hdr, "rows": rows}

    @property
    def max_chunk_s(self) -> float:
        """The one cap of a chunk and of a hold chunk (eai-standard/3.0): game seconds; turn-based, where a chunk is one
        action and a hold chunk waits for your turn, the real seconds that wait may take."""
        return TURN_WAIT_MAX_S if self.clock == "turn" else MAX_CHUNK_S

    @staticmethod
    def frame_step(parts: list) -> int | None:
        """The control step of an answer's newest image (meta.frame_step), from its frame_step part(s)."""
        steps = [np.frombuffer(p[2], dtype=p[3]["dtype"]) for p in parts
                 if p[1] == "array" and (p[0] == "frame_step" or p[0].startswith("frame_step/"))]
        steps = [int(np.max(a)) for a in steps if len(a)]
        return max(steps) if steps else None

    def newest_step(self, parts: list) -> int | None:
        """meta.frame_step of an answer (eai-standard/3.0: every answer with images): its frame_step part(s), else, for
        a sport whose observation names no view steps (soccer, soccer SSL, foosball), the step the core is at now
        (the images are of now); None without images or without a step clock (turn-based)."""
        newest = self.frame_step(parts) if parts else None
        if newest is None and any(p[0].startswith("last/") for p in parts or ()):
            k = getattr(getattr(self.svc, "m", None), "k", None) if self.dt else None
            newest = int(k) if isinstance(k, (int, np.integer)) else None
        return newest

    def hold_seconds(self, hdr: dict) -> float:
        """A hold chunk's `seconds`: interpolate "hold", a finite number in (0, max_chunk_s]."""
        if hdr.get("interpolate") != "hold":
            raise BadRequest('a chunk without rows is a hold chunk: {"type": <type>, "interpolate": "hold", "seconds": n}')
        n = hdr.get("seconds")
        limit = self.max_chunk_s
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 < n <= limit + 1e-9:
            raise BadRequest(f"a hold chunk's seconds: a finite number in (0, max_chunk_s = {limit:g}]")
        return float(n)

    def build_rows(self, req) -> dict:
        hdr, raw = req["hdr"], req["rows"]
        if req.get("hold") is not None:
            return self.build_hold(req)
        if hdr.get("interpolate") not in (None, "linear", "hold"):
            raise BadRequest("interpolate: linear | hold (the match's rows are commands, never interpolated: either "
                             "keeps each command in force until the next)")
        code, spec = self.core("spec", None, post=False)
        schema = self.schema_of(spec if code == 200 else {})
        kind = hdr.get("type")
        entity = hdr.get("entity")
        if entity is not None and not isinstance(entity, (str, int)):
            raise BadRequest("entity must be a string")
        if isinstance(kind, str) and "@" in kind:        # "<type>@<entity>": the shared clients have no entity argument
            kind, _, ent = kind.partition("@")
            if not kind or not ent or (entity is not None and str(entity) != ent):
                raise BadRequest("type: <type> or <type>@<entity> (one entity, as the header's `entity` if both)")
            entity = ent
        rows = []
        for i, r in enumerate(raw):
            if isinstance(r, dict):
                row = dict(r)
                row.setdefault("type", kind)
                if kind is None:
                    kind = row.get("type")
            else:
                if kind not in schema:
                    raise BadRequest(f"type: one of {sorted(schema)} (a numeric row needs the chunk's type)")
                cols = columns_of(schema[kind])
                if cols is None:
                    raise BadRequest(f"{kind} has no numeric layout: send JSON action objects")
                vals = np.asarray(r, dtype=np.float64).reshape(-1)
                if vals.size != sum(c[2] for c in cols):
                    raise BadRequest(f"row {i}: {kind} rows have {sum(c[2] for c in cols)} columns "
                                     f"(spec action_types.{kind}.layout), got {vals.size}")
                row = row_from_floats(kind, cols, vals)
            if row.get("type") != kind:
                raise BadRequest(f"row {i}: one chunk is one action type ({kind!r}, got {row.get('type')!r})")
            if entity is not None:
                if "entity" in row and str(row["entity"]) != str(entity):
                    raise BadRequest(f"row {i}: one chunk commands one entity ({entity!r})")
                row["entity"] = entity
            rows.append(row)
        ents = {str(r.get("entity", "")) for r in rows}
        if len(ents) > 1:
            raise BadRequest("one chunk commands one entity (header `entity`)")
        if not isinstance(kind, str) or not kind:
            raise BadRequest("type: the chunk's action type (spec action_types, or a type the task text names)")
        # the values are the match's to check (core.sport.parse_action, when each row is sent): some depend on the
        # state at that moment (a toss only on your own service), so a plan is never refused for them in advance
        dt = hdr.get("dt")
        n = 1
        if self.clock != "turn":
            if dt is None:
                dt = self.dt
            if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt <= 0 or dt > 0.5:
                raise BadRequest("dt: a finite number in (0, 0.5] seconds, a multiple of the control step")
            n = int(round(dt / self.dt))
            if n < 1 or abs(n * self.dt - dt) > 1e-6 * max(1.0, dt):
                raise BadRequest(f"dt must be a multiple of the control step {self.dt:g} s")
            if len(rows) * n * self.dt > MAX_CHUNK_S + 1e-9:
                raise BadRequest(f"a chunk covers at most max_chunk_s = {MAX_CHUNK_S:g} s")
        elif len(rows) != 1:
            raise BadRequest("turn-based: one action (one row) per /submit; your review follows it")
        at = hdr.get("at")
        if at is not None and (isinstance(at, bool) or not isinstance(at, int) or at < 0):
            raise BadRequest("at: a control step (a non-negative integer)")
        if at is not None and self.clock == "turn":
            raise BadRequest("at: not in a turn-based match")
        return {"type": kind, "rows": rows, "n": n, "dt": None if self.clock == "turn" else n * self.dt, "at": at,
                "entity": str(rows[0].get("entity", "")), "note": hdr.get("note"),
                **self.view_args(hdr, default_video="none", images_default=False)}

    def build_hold(self, req) -> dict:
        """A validated hold chunk: its type (one of the schema's, `<type>@<entity>` too) and entity, no rows."""
        hdr = req["hdr"]
        code, spec = self.core("spec", None, post=False)
        schema = self.schema_of(spec if code == 200 else {})
        kind, entity = hdr.get("type"), hdr.get("entity")
        if entity is not None and not isinstance(entity, (str, int)):
            raise BadRequest("entity must be a string")
        if isinstance(kind, str) and "@" in kind:
            kind, _, ent = kind.partition("@")
            if not kind or not ent or (entity is not None and str(entity) != ent):
                raise BadRequest("type: <type> or <type>@<entity> (one entity, as the header's `entity` if both)")
            entity = ent
        if not isinstance(kind, str) or not kind or (schema and kind not in schema):
            raise BadRequest(f"type: one of {sorted(schema)} (a hold chunk names the type it holds)")
        at = hdr.get("at")
        if at is not None and (isinstance(at, bool) or not isinstance(at, int) or at < 0):
            raise BadRequest("at: a control step (a non-negative integer)")
        if at is not None and self.clock != "realtime":
            raise BadRequest("at: a hold chunk starts now in this match")
        return {"type": kind, "rows": [], "hold": req["hold"], "n": 1, "dt": self.dt, "at": at,
                "entity": "" if entity is None else str(entity), "note": hdr.get("note"),
                **self.view_args(hdr, default_video="none", images_default=False)}

    def view_args(self, hdr, default_video="frames", images_default=True) -> dict:
        cams = hdr.get("cameras")
        if cams is not None and (not isinstance(cams, list) or not all(isinstance(c, str) for c in cams)):
            raise BadRequest("cameras: a list of camera names")
        video = hdr.get("video", default_video)
        if video not in ("mp4", "frames", "both", "none"):
            raise BadRequest("video: mp4 | frames | both | none")
        fps = hdr.get("video_fps")
        if fps is not None and (isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps)
                                or not 1 <= fps <= MAX_VIDEO_FPS):
            raise BadRequest(f"video_fps: a number in [1, max_video_fps = {MAX_VIDEO_FPS}]")
        depth = hdr.get("depth", "none")
        if depth not in ("none", False, None) or hdr.get("include_depth"):
            raise BadRequest("no depth in this service (spec depth.modes)")
        query = hdr.get("query")
        if query is not None and not isinstance(query, dict):
            raise BadRequest("query: a JSON object (the sport's observation query, spec match)")
        images = (cams is None and images_default) or bool(cams)
        return {"cameras": cams, "video": video, "query": query, "images": images,
                "team_since": hdr.get("team_since")}

    # ------------------------------------------------------------------ images
    def view_parts(self, obs: dict, cameras, video) -> tuple[list, dict]:
        """The core's observation (one PNG of tiles + `tiles`) -> RCB1 parts: last/<cam>, frames/<cam>,
        frame_step/<cam> (and frame_step / frame_time_s when every camera has the same steps), view (the PNG)."""
        obs = dict(obs or {})
        b64 = obs.pop("image_png_b64", None)
        info = {"observation": obs}
        if not b64:
            return [], info
        png = base64.b64decode(b64)
        parts = [("view", "bytes", png, {"format": "png", "note": "the core's own image (game observe's)"})]
        tiles = obs.get("tiles") or []
        try:
            img = pngdec.decode(png)
        except Exception as exc:  # noqa: BLE001
            info["degraded"] = f"image not decoded ({exc}); the view part has it"
            return parts, info
        vs = obs.get("view_steps") if isinstance(obs.get("view_steps"), list) else []
        by_cam, steps = {}, {}
        if not tiles:
            tiles = self.grid_tiles(img.shape[0], img.shape[1])
            if tiles:
                info["tiles_from"] = "the spec's cameras, one row each, frames left to right (the sport's own sheet)"
        if not tiles:
            tiles = [{"camera": "view", "x": 0, "y": 0, "width": img.shape[1], "height": img.shape[0]}]
        count = {}
        for t in tiles:
            count[str(t.get("camera", "view"))] = count.get(str(t.get("camera", "view")), 0) + 1
        seen = {}
        for i, t in enumerate(tiles):
            cam = str(t.get("camera", f"tile{i}"))
            try:
                x, y, w, h = int(t["x"]), int(t["y"]), int(t["width"]), int(t["height"])
            except (KeyError, TypeError, ValueError):
                continue
            j = seen.get(cam, 0)
            seen[cam] = j + 1
            by_cam.setdefault(cam, []).append(np.ascontiguousarray(img[y:y + h, x:x + w]))
            s = None
            if len(vs) == len(tiles):
                s = vs[i]
            elif isinstance(t.get("frame"), int) and 0 <= t["frame"] < len(vs):
                s = vs[t["frame"]]
            elif len(vs) == count[cam]:
                s = vs[j]
            elif len(vs) == 1:
                s = vs[0]
            steps.setdefault(cam, []).append(s)
        if cameras is not None:
            unknown = sorted(set(cameras) - set(by_cam))
            if unknown:
                info["unknown_cameras"] = unknown
            by_cam = {c: v for c, v in by_cam.items() if c in cameras}
        same = None
        for cam, frames in by_cam.items():
            parts.append(rcb1.array_part(f"last/{cam}", frames[-1]))
            if video in ("frames", "both", "mp4") and len({f.shape for f in frames}) == 1:
                parts.append(rcb1.array_part(f"frames/{cam}", np.stack(frames)))
            st = steps.get(cam) or []
            if st and all(isinstance(s, int) for s in st):
                parts.append(rcb1.array_part(f"frame_step/{cam}", np.asarray(st, dtype=np.int64)))
                same = st if same is None or same == st else False
            else:
                same = False
        if same and self.dt:
            parts.append(rcb1.array_part("frame_step", np.asarray(same, dtype=np.int64)))
            parts.append(rcb1.array_part("frame_time_s", np.asarray(same, dtype=np.float64) * self.dt))
        if video == "mp4":
            info["degraded"] = "no mp4 encoder in this service: frames instead"
        info["cameras"] = self.calibration_now(list(by_cam))
        return parts, info

    def grid_tiles(self, H, W) -> list:
        """A sport that draws its own sheet names no tiles (table tennis, badminton: one row per camera of the spec, in
        its order, frames left to right). The tiles of that layout when the image has exactly its size, else []."""
        if not hasattr(self, "_spec_cams"):
            code, sp = self.core("spec", None, post=False)
            cams = sp.get("cameras") if code == 200 and isinstance(sp.get("cameras"), list) else []
            try:
                self._spec_cams = [(str(c["name"]), *cam_size(c)) for c in cams]
            except (KeyError, TypeError, ValueError):
                self._spec_cams = []
        cams = self._spec_cams
        if not cams or len({(w, h) for _, w, h in cams}) != 1:
            return []
        w, h = cams[0][1], cams[0][2]
        if H != len(cams) * h or W % w or W < w:
            return []
        return [{"camera": name, "x": c * w, "y": r * h, "width": w, "height": h, "frame": c}
                for r, (name, _, _) in enumerate(cams) for c in range(W // w)]

    def calibration_now(self, names) -> dict:
        svc = self.svc
        out = {}
        try:
            with svc.cond:
                cams = svc.m.cameras(self.seat) if callable(getattr(svc.m, "cameras", None)) else []
        except Exception:  # noqa: BLE001
            cams = []
        for c in cams or []:
            d = c if isinstance(c, dict) else getattr(c, "to_dict", lambda: {})()
            if d.get("name") in names:
                cal = calibration(d)
                if cal:
                    out[d["name"]] = cal
        return out

    def observation(self, args, after_now=None):
        """(code, meta extra, parts, now): the core's observe (images) or, without images, its status."""
        if not args["images"]:
            if after_now is not None:
                return 200, {}, [], after_now
            body = None
            code, out = self.core("status", body, post=False)
            return code, {}, [], self.now_of(out) or (out if code == 200 else None)
        body = {}
        if args.get("query") is not None:
            body["query"] = args["query"]
        if args.get("team_since") is not None:
            body["team_since"] = args["team_since"]
        code, out = self.core("observe", body)
        now = self.now_of(out)
        if code != 200:
            return code, {"error": out.get("error")}, [], now
        with self.lock:
            self.obs_id += 1
        parts, info = self.view_parts(out.get("observation") or {}, args["cameras"], args["video"])
        return 200, info, parts, now

    # ------------------------------------------------------------------ /observe
    def observe(self, hdr: dict) -> tuple[int, dict, list]:
        """eai-standard/3.0: a read, answered at once; it never waits and never lets time pass (`seconds` > 0: 400, a
        hold chunk does that). last_s = 0 the observation of now; the match keeps no record of earlier frames, so
        last_s = n answers with the sport's own frames of now too (meta.last_s: the robot seconds they span; a declared
        deviation)."""
        args = self.view_args(hdr)
        seconds = hdr.get("seconds", 0)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise BadRequest("seconds: a finite number >= 0")
        if seconds > 0:
            raise BadRequest(HOLD_HINT_RT if self.clock == "realtime" else HOLD_HINT)
        last_s = hdr.get("last_s", 0)
        if isinstance(last_s, bool) or not isinstance(last_s, (int, float)) or not math.isfinite(last_s) or last_s < 0:
            raise BadRequest("last_s: a finite number >= 0")
        k0 = int(self.svc.m.k)
        code, info, parts, now = self.observation(args)
        if code == 409 and self.over():                 # the match is over: the final state, no images (2.x: 200)
            code, info, parts = 200, {}, []
        elif code == 409 and self.clock == "turn":       # before the start: the state, no images
            code, info = 200, {"not_now": info.get("error")}
        if code != 200:
            return code, self.meta(now, **info), []
        part = next((p for p in parts if p[0] == "frame_step"), None) \
            or next((p for p in parts if p[0].startswith("frame_step/")), None)
        steps = np.frombuffer(part[2], dtype=part[3]["dtype"]) if part is not None and part[1] == "array" else None
        covered, newest = 0.0, None
        if steps is not None and len(steps) and self.dt:
            newest = int(np.max(steps))
            covered = round(float(newest - int(np.min(steps))) * self.dt, 4) if last_s > 0 else 0.0
        if newest is None:
            newest = self.newest_step(parts)
        extra = {"obs_id": self.obs_id, "last_s": covered, **({"frame_step": newest} if newest is not None else {}), **info}
        self.log(ev="observe", last_s=last_s, k=k0, images=bool(parts))
        return 200, self.meta(now, **extra), parts

    def watch(self, seconds, team_since=None) -> tuple[int, dict | None, dict]:
        """Let `seconds` of game time pass (ceil(seconds / control_dt) control steps): the core's wait, in calls of at
        most 1 s; it stops early at a freeze or the end (the core's wait returns then)."""
        svc, dt = self.svc, self.dt
        steps = int(math.ceil(seconds / dt - 1e-6))
        per = max(1, int(math.floor(1.0 / dt + 1e-9)))
        left, now, unit = steps, None, svc.m.unit()
        while left > 0:
            m = min(left, per)
            body = {"dt": (m - 0.5) * dt}                # the core waits ceil(d / dt) steps: exactly m
            if team_since is not None:
                body["team_since"] = team_since
            k = int(svc.m.k)
            code, out = self.core("wait", body)
            if code != 200:
                return code, self.now_of(out), {"error": out.get("error")}
            now = self.now_of(out)
            left -= max(0, int(svc.m.k) - k) if self.clock == "realtime" else m
            if svc.phase != "running" or svc.m.unit() != unit:
                break
        return 200, now, {"watch_steps_asked": steps, "watch_stopped": None if left <= 0 else
                          ("match_over" if self.over() else "frozen" if svc.phase != "running" else "unit_over")}

    # ------------------------------------------------------------------ /submit
    def submit(self, req: dict) -> tuple[int, dict, list]:
        if self.over():
            raise BadRequest("the match is over", 409)
        with self.lock:
            self.chunk_id += 1
            cid = self.chunk_id
        if req.get("hold") is not None:
            code, meta, parts = self.submit_hold(req, cid)
        elif self.clock == "realtime":
            code, meta, parts = self.submit_realtime(req, cid)
        else:
            code, meta, parts = self.submit_sync(req, cid)
        newest = self.newest_step(parts)
        if newest is not None and isinstance(meta, dict) and "frame_step" not in meta:
            meta = {**meta, "frame_step": newest}   # eai-standard/3.0: every answer with images
        return code, meta, parts

    def submit_hold(self, req, cid):
        """A rows-free hold chunk (eai-standard/3.0). Lockstep: n game seconds pass with the commands in force (the core's
        wait: max(1, round(n / control_dt)) control steps, as the layers' hold), answered after them; turn-based: a wait of at most n real seconds for your turn; realtime: answered at
        once, the entity's plan from `at` (default now) is cleared for n seconds, the command in force kept."""
        svc, n = self.svc, req["hold"]
        k0, t0 = int(svc.m.k), time.monotonic()
        if self.clock == "realtime":
            ent = req["entity"]
            with svc.cond:
                k, unit, phase = int(svc.m.k), svc.m.unit(), svc.phase
                if phase != "running":
                    not_now = ("the world is frozen for the reviews: send /ready" if phase == "review" else
                               "the match has not started: send /start")
                    return 200, self.meta(None, chunk_id=cid, type=req["type"], hold=True, ok=False, not_now=not_now,
                                          executed_rows=0, start_step=None, plan_end_step=None, end_step=None,
                                          duration_s=0.0, planned_duration_s=round(n, 6)), []
                at = k if req["at"] is None else req["at"]
                if at < k:
                    at = k
                if at > k + int(round(MAX_AHEAD_S / self.dt)):
                    raise BadRequest(f"at: at most max_ahead_steps = {int(round(MAX_AHEAD_S / self.dt))} steps ahead")
                steps = max(1, int(round(n / self.dt)))
                old = self.plan.get(ent, [])
                replaced = sum(1 for r in old if r["step"] >= at and r["unit"] == unit)
                self.plan[ent] = [r for r in old if r["step"] < at and r["unit"] == unit]
                svc.cond.notify_all()
            self.log(ev="submit", clock="realtime", chunk_id=cid, k=k, at=at, entity=ent, type=req["type"], hold_s=n)
            parts, info, now = [], {}, None
            if req["images"]:
                code, info, parts, now = self.observation(req)
            if now is None:
                code, out = self.core("status", None, post=False)
                now = self.now_of(out) or (out if code == 200 else None)
            return 200, self.meta(now, chunk_id=cid, type=req["type"], hold=True, ok=True, executed_rows=0,
                                  start_step=at, late_steps=0, late_rows=0, replaced_rows=replaced,
                                  plan_end_step=at + steps, end_step=at + steps, entity=ent,
                                  duration_s=round(steps * self.dt, 6), planned_duration_s=round(n, 6),
                                  effects=self.take_effects(), plan=[], clipped=[], n_clipped=0, **info), parts
        phase = svc.phase
        if (phase != "running") if self.clock == "lockstep" else (phase == "prepare"):
            not_now = ("the world is frozen for the reviews: send /ready" if phase == "review" else
                       "the match has not started: send /start")   # (§29: nothing runs, ok false)
            self.log(ev="submit", clock=self.clock, chunk_id=cid, type=req["type"], hold_s=n, not_now=phase)
            return 200, self.meta(None, chunk_id=cid, type=req["type"], hold=True, ok=False, not_now=not_now,
                                  executed_rows=0, control_steps_chunk=0, duration_s=0.0,
                                  planned_duration_s=round(n, 6), effects=[], plan=[], clipped=[], n_clipped=0), []
        if self.clock == "turn":
            body = {"timeout_s": float(n)}
            if req.get("team_since") is not None:
                body["team_since"] = req["team_since"]
            code, out = self.core("wait", body)
            if code != 200:
                return code, self.meta(self.now_of(out), error=out.get("error"), chunk_id=cid), []
            now, watch = self.now_of(out), {"waited_for": "your turn", "waited_s": round(time.monotonic() - t0, 3)}
        else:
            # max(1, round(n / control_dt)) control steps, as every layer's hold chunk (rcb_service, rcb_limited)
            code, now, watch = self.watch(max(1, int(round(n / self.dt))) * self.dt, req.get("team_since"))
            if code != 200:
                return code, self.meta(now, error=watch.get("error"), chunk_id=cid), []
        parts, info = [], {}
        if req["images"] and not self.over():
            code, info, parts, onow = self.observation(req)
            now = onow or now
        k1 = int(svc.m.k)
        dur = round(time.monotonic() - t0, 6) if self.clock == "turn" else round((k1 - k0) * self.dt, 6)
        self.log(ev="submit", clock=self.clock, chunk_id=cid, type=req["type"], hold_s=n, k0=k0, k1=k1)
        return 200, self.meta(now, chunk_id=cid, type=req["type"], hold=True, executed_rows=0, ok=True, effects=[],
                              control_steps_chunk=k1 - k0, duration_s=dur, planned_duration_s=round(n, 6),
                              plan=[], clipped=[], n_clipped=0, **watch, **info), parts

    def submit_sync(self, req, cid):
        """Lockstep and turn: the rows run now, one after the other (lockstep: each row then dt of game time)."""
        svc = self.svc
        k0 = int(svc.m.k)
        effects, now, reply_obs, ok, not_now = [], None, None, True, None
        if req["at"] is not None:
            if req["at"] < k0:
                raise BadRequest(f"at = {req['at']} has passed (the world is at step {k0}; in lockstep nothing "
                                 "passes while you think)")
            if req["at"] > k0 + int(round(MAX_AHEAD_S / self.dt)):
                raise BadRequest("at: too far ahead")
            if (req["at"] - k0 + len(req["rows"]) * req["n"]) * self.dt > MAX_CHUNK_S + 1e-9:
                raise BadRequest(f"a chunk covers at most max_chunk_s = {MAX_CHUNK_S:g} s, the wait until `at` "
                                 f"included (the world is at step {k0})")
            if req["at"] > k0:
                code, now, w = self.watch((req["at"] - k0) * self.dt)
                if code != 200:
                    return code, self.meta(now, error=w.get("error")), []
        executed = 0
        for i, row in enumerate(req["rows"]):
            code, out = self.core("act", row)
            now = self.now_of(out) or now
            if code == 200:
                executed += 1
                eff = {"row": i, **(out.get("took_effect") or {})}
                for key in ("clock_forfeit", "accepted"):
                    if key in out:
                        eff[key] = out[key]
                if self.clock == "turn":
                    eff.update({k: v for k, v in out.items() if k not in ("state", "observation")})
                effects.append(eff)
                if isinstance(out.get("observation"), dict) and out["observation"].get("image_png_b64"):
                    reply_obs = out["observation"]
            elif code == 409:
                if self.over():
                    break
                ok, not_now = False, out.get("error")
                break
            elif code == 400 and i == 0 and executed == 0 and len(req["rows"]) == 1:
                return 400, self.meta(now, error=out.get("error"), chunk_id=cid), []
            elif code in (400, 429):
                effects.append({"row": i, "code": code, "error": out.get("error")})
            else:
                return code, self.meta(now, error=out.get("error"), chunk_id=cid), []
            if self.clock == "lockstep" and req["n"] > 1 and not self.over():
                code, wnow, w = self.watch((req["n"] - 1) * self.dt)
                now = wnow or now
                if code != 200 or svc.phase != "running":
                    break
        parts, info = [], {}
        if reply_obs is not None:
            parts, info = self.view_parts(reply_obs, req["cameras"], "frames")
            info["images_of"] = "the result of this action"
        elif req["images"] and not self.over():
            code, info, parts, onow = self.observation(req)
            now = onow or now
        k1 = int(svc.m.k)
        self.log(ev="submit", clock=self.clock, chunk_id=cid, type=req["type"], rows=len(req["rows"]), k0=k0, k1=k1,
                 executed=executed, ok=ok, effects=effects)
        planned = None if self.clock == "turn" else round(len(req["rows"]) * req["n"] * self.dt, 6)
        return 200, self.meta(now, chunk_id=cid, type=req["type"], executed_rows=executed, ok=ok,
                              **({"not_now": not_now} if not_now else {}), effects=effects,
                              control_steps_chunk=k1 - k0, duration_s=None if self.clock == "turn" else round((k1 - k0) * self.dt, 6),
                              planned_duration_s=planned, plan=[], clipped=[], n_clipped=0, **info), parts

    def submit_realtime(self, req, cid):
        """Realtime: answers at once; the rows become the plan of their entity from control step `at`
        (default: the next one), replacing what was planned from `at` on; rows whose step has run are dropped."""
        svc = self.svc
        ent = req["entity"]
        with svc.cond:
            k, unit, phase = int(svc.m.k), svc.m.unit(), svc.phase
            if phase == "over":
                raise BadRequest("the match is over", 409)
            if phase != "running":
                not_now = ("the world is frozen for the reviews: send /ready" if phase == "review" else
                           "the match has not started: send /start")
                self.log(ev="submit", clock="realtime", chunk_id=cid, k=k, not_now=phase)
                return 200, self.meta(None, chunk_id=cid, type=req["type"], ok=False, not_now=not_now,
                                      executed_rows=0, start_step=None, late_steps=0, plan_end_step=None,
                                      end_step=None, duration_s=0.0,
                                      planned_duration_s=round(len(req["rows"]) * req["n"] * self.dt, 6)), []
            at = k if req["at"] is None else req["at"]
            if at > k + int(round(MAX_AHEAD_S / self.dt)):
                raise BadRequest(f"at: at most max_ahead_steps = {int(round(MAX_AHEAD_S / self.dt))} steps ahead")
            new = []
            for i, row in enumerate(req["rows"]):
                s = at + i * req["n"]
                if s >= k:
                    new.append({"step": s, "body": row, "unit": unit, "chunk_id": cid, "row": i,
                                "t_submit": time.monotonic(), "k_submit": k})
            late = len(req["rows"]) - len(new)
            old = self.plan.get(ent, [])
            replaced = sum(1 for r in old if r["step"] >= at and r["unit"] == unit)
            self.plan[ent] = [r for r in old if r["step"] < at and r["unit"] == unit] + new
            plan_end = self.plan[ent][-1]["step"] if self.plan[ent] else None
            svc.cond.notify_all()
        self.ensure_dispatcher(ent)
        self.log(ev="submit", clock="realtime", chunk_id=cid, k=k, at=at, entity=ent, type=req["type"],
                 rows=len(req["rows"]), kept=len(new), late=late, replaced=replaced, n=req["n"])
        parts, info, now = [], {}, None
        if req["images"]:
            code, info, parts, now = self.observation(req)
        if now is None:
            code, out = self.core("status", None, post=False)
            now = self.now_of(out) or (out if code == 200 else None)
        return 200, self.meta(now, chunk_id=cid, type=req["type"], ok=True, executed_rows=0,
                              start_step=new[0]["step"] if new else None, late_steps=late * req["n"],
                              late_rows=late, replaced_rows=replaced, plan_end_step=plan_end,
                              end_step=plan_end, entity=ent,
                              duration_s=round(len(new) * req["n"] * self.dt, 6),
                              planned_duration_s=round(len(req["rows"]) * req["n"] * self.dt, 6),
                              effects=self.take_effects(), plan=[], clipped=[], n_clipped=0, **info), parts

    def take_effects(self) -> list:
        with self.lock:
            out, self.effects = self.effects, []
        return out

    def ensure_dispatcher(self, ent):
        with self.lock:
            if ent in self.dispatchers and self.dispatchers[ent].is_alive():
                return
            th = threading.Thread(target=self.dispatch_loop, args=(ent,), daemon=True, name=f"eai-std-{ent}")
            self.dispatchers[ent] = th
            th.start()

    def dispatch_loop(self, ent):
        """Realtime: hand each planned row to the match at its step (after step - 1 has run), one at a time per entity
        (the core's one act per entity in flight); the core applies it at the next control-step boundary once its
        preparation is done."""
        svc = self.svc
        self.tl.internal = True
        while True:
            with svc.cond:
                while True:
                    if svc.phase == "over":
                        dropped = sum(len(v) for v in self.plan.values())
                        if dropped:
                            self.effect_log["dropped_rows"] += dropped
                            self.log(ev="plan_dropped", why="match_over", rows=dropped)
                        self.plan.clear()
                        return
                    rows = self.plan.get(ent) or []
                    unit = svc.m.unit()
                    stale = [r for r in rows if r["unit"] != unit]
                    if stale:
                        self.plan[ent] = rows = [r for r in rows if r["unit"] == unit]
                        self.effect_log["dropped_rows"] += len(stale)
                        self.log(ev="plan_dropped", why="unit_over", entity=ent, rows=len(stale))
                    if rows and svc.phase == "running" and rows[0]["step"] <= svc.m.k:
                        row = rows.pop(0)
                        break
                    svc.cond.wait(0.05)
                k_disp, t_disp = int(svc.m.k), time.monotonic()
            code, out = self.core("act", row["body"])
            te = out.get("took_effect") if isinstance(out, dict) else None
            eff_step = te.get("step") if isinstance(te, dict) else None
            rec = {"chunk_id": row["chunk_id"], "row": row["row"], "entity": ent, "planned_step": row["step"],
                   "dispatched_at_step": k_disp, "code": code}
            if eff_step is not None:
                rec["effect_step"] = int(eff_step)
                rec["late_steps"] = max(0, int(eff_step) - row["step"])
                rec["took_effect"] = te
            else:
                rec["error"] = out.get("error") if isinstance(out, dict) else None
            with self.lock:
                self.effects.append(rec)
                del self.effects[:-RECENT_EFFECTS]
                self.effect_log["rows"] += 1
                if rec.get("late_steps"):
                    self.effect_log["late_rows"] += 1
                    self.effect_log["late_steps"] += rec["late_steps"]
                if eff_step is None:
                    self.effect_log["refused_rows"] += 1
            self.log(ev="effect", wall_dispatch=round(t_disp, 4), wall_done=round(time.monotonic(), 4), **rec)

    # ------------------------------------------------------------------ extension endpoints
    def ext(self, ep, body: dict) -> tuple[int, dict]:
        """/start, /ready, /say, /team: the core's own call; its reply with the match meta."""
        if ep in ("say", "team") and not (getattr(self.svc, "channel", None) is not None and self.svc.channel.enabled):
            return 404, {"error": "no team channel in this match (team formats only)"}
        if ep == "start":
            body = {}
        elif ep == "ready":
            body = {"why": body.get("why", ""), "plan": body.get("plan", "")}
        elif ep == "say":
            body = {"text": body.get("text")}
        elif ep == "team":
            body = {"since": body.get("since", 0)}
        code, out = self.core(ep, body)
        self.log(ev=ep, code=code)
        reply = {k: v for k, v in (out or {}).items() if k not in ("now", "state")}
        return code, {**reply, "ok": code == 200, "meta": self.meta(self.now_of(out))}


ENDPOINTS = {
    "GET /spec": "this spec",
    "GET /status": "{step, control_steps, done, reason, time_s, time_left_s, score, review_due, match_over, phase, world, "
                   "state, ...}",
    "POST /observe": "RCB1 or JSON {cameras, last_s, video, query, team_since} -> RCB1: last/<cam>, frames/<cam>, "
                     "frame_step/<cam>, view (the core's PNG); meta.state, meta.observation; at once, no time passes "
                     "(seconds > 0: 400)",
    "POST /submit": "RCB1 (header {type, dt, at, entity, cameras, video, note} + part `actions`: float32 (T, dim) or "
                    "json [action, ...]) or JSON {type, dt, at, entity, rows: [...]} -> RCB1; a hold chunk: {type, "
                    "interpolate: \"hold\", seconds: n} without rows",
    "POST /start": "extension: you are ready (the match begins when every seat has started); JSON {} -> JSON "
                   "{accepted, ok, meta}",
    "POST /ready": "extension: your review {why, plan} (each at most 2000 characters) -> JSON {accepted, ok, meta}",
    "POST /say": "extension, team formats: {text} -> JSON {sent, ok, meta}",
    "POST /team": "extension, team formats: {since} -> JSON {messages, ok, meta} (GET /team?since=N too)",
}

REQUEST_LIMIT = {"rule": "Part 1: a request body up to 64 MiB",
                 "here": "at most max_request_bytes = 8 MiB (above it: 413)",
                 "why": "a match's requests are commands and small images; the seat server bounds what one seat may send"}
RATE_LIMIT = {"rule": "Part 1: every request is answered",
              "here": "a seat with too many requests in flight is refused 429 (empty body: retry more slowly); a "
                      "request from a host the seat is not bound to is a 403 (seat not authorized)",
              "why": "several seats share one world; one seat must not slow the others down or act for another"}

DEVIATIONS = {
    "realtime": [
        {"rule": "3.0: the clock starts at the first /submit",
         "here": "the clock starts when every seat has sent /start (the start barrier) and runs one control step every "
                 "control_dt x S seconds of wall time",
         "why": "a match is a contest of several seats; its start is the core's barrier, and results are comparable "
                "only under it"},
        {"rule": "realtime: the clock runs until the episode ends",
         "here": "after every unit (a point) the world freezes until every due seat has sent /ready (at most "
                 "review_timeout_s of real time, else that side loses: ready_timeout); the plan is cleared at a freeze",
         "why": "the frozen review is part of Embodied Olympics' rules; acts of a finished unit never take effect"},
        {"rule": "realtime: a row takes effect at its control step",
         "here": "a row is handed to the match at its step (after step - 1 ran) and takes effect at the first "
                 "control-step boundary after its preparation (the platform's planning of a high-level action): "
                 "normally that step, later when the preparation takes longer than one control period "
                 "(meta.effects: effect_step, late_steps); one row per entity in flight, the next waits for the "
                 "previous row's effect",
         "why": "the core applies an act only after it is prepared, at a boundary; preparing rows ahead of time would "
                "change the platform's behaviour and the results' comparability"},
        {"rule": "realtime: behind the clock by more than 0.5 s the service drops the debt (a stall)",
         "here": "the core runs missed steps back to back and records how late (final.json sim_lag); the match is "
                 "voided as infrastructure past the integrity limits (README)",
         "why": "the core's clock, unchanged"},
        {"rule": "3.0: /observe last_s = n returns the frames a recorder kept of the last n seconds",
         "here": "there is no recorder: /observe returns the sport's own frames of now (e.g. 4 frames 40 ms apart; "
                 "meta.last_s says what they span), no video",
         "why": "the core renders images only on observation, within its camera budget"},
        {"rule": "3.0: a hold chunk holds the current target for n seconds",
         "here": "it clears the entity's plan from `at` for n seconds; the command in force stays (zero-order hold)",
         "why": "the match's actions are commands, not targets"},
        {"rule": "realtime: /submit answers with the frames of now",
         "here": "with images only when `cameras` is given (a render costs the clock)", "why": "camera budget"},
        {"rule": "standard: `linear` / `hold` interpolation between rows",
         "here": "every action type is a command (one row, one control step), never interpolated; the last "
                 "command stays in force as the sport defines it (zero-order hold)",
         "why": "the match's actions are commands, not targets"},
    ],
    "lockstep": [
        {"rule": "3.0: /observe last_s = n returns the frames recorded during the last n seconds of /submit",
         "here": "the sport's own frames of now (meta.last_s says what they span); a hold chunk answers with the "
                 "observation at its end, no video", "why": "the core renders images only on observation"},
        {"rule": "standard: the episode runs until it ends", "here": "after every unit the world freezes for /ready (at "
         "most review_timeout_s of real time)", "why": "Embodied Olympics' rules"},
        {"rule": "standard: `linear` / `hold` interpolation", "here": "commands only, never interpolated",
         "why": "the match's actions are commands"},
    ],
    "turn": [
        {"rule": "standard: /submit executes a chunk of rows", "here": "one action per turn, then /ready",
         "why": "a turn-based match"},
        {"rule": "3.0: a hold chunk {type, interpolate: hold, seconds: n} holds the current target for n seconds",
         "here": "it waits up to n real seconds for your turn (n at most max_chunk_s, real seconds here)",
         "why": "nothing moves between turns"},
        {"rule": "3.0: /observe last_s = n returns the frames recorded in the last n seconds",
         "here": "the sport's own frames of now", "why": "the core renders images only on observation"},
    ],
}
for _clock in DEVIATIONS.values():
    _clock += [REQUEST_LIMIT, RATE_LIMIT]
