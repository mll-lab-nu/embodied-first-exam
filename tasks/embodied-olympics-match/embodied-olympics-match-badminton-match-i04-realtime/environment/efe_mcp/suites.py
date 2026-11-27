"""Tool kinds for suites whose service adds calls of its own to the RCB robot service (manifest "kind"), behind the same
server.

kind "eo-match": Embodied Olympics matches (embodied-olympics-match standard and realtime tasks): the seat's
eai-standard/3.0 service with the match extension (docs/protocol/standard_mode.md Part 5;
the service's eai_std/ layer at $SIM_URL). The tools of every RCB task, one per endpoint and with the same fields and
replies (rcb_tools.py): `spec`, `observe`, `submit` (rows are the match's JSON action objects, or numeric rows in a
type's layout; a hold chunk too); no `finish` (the match's rules end it: /finish is a 404), no `reset`, no
`kinematics`. The match's own calls are extra tools: `start` and `ready`, and `say` / `team` in a team format. The
declared deviations (/spec timing.deviations) stay the service's: the clock starts at the /start barrier, and
`last_s` > 0 returns the sport's frames of now. A call still running after 45 s is collected with
observe(operation=id), as in every task. The `game` command (the seat API /<SEAT>/<call>) is the same match through
another route; it has no tools.

Each kind gives: tools_for(m), adapter_for(m)."""
from __future__ import annotations
import json

import numpy as np

import workspace
from rcb_tools import RcbTools, ToolError, _jsonable

DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _obj(props=None, required=None):
    s = {"$schema": DRAFT, "type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = list(required)
    return s


# ---------------------------------------------------------------------------------------------------------- eo-match
EO_DROP = ("depth", "include_depth")          # no depth in a match (spec depth.modes = ["none"])


def eo_tools(m) -> list:
    """spec, observe, submit (the canonical tools, narrowed to a match) + start, ready (+ say, team)."""
    import schema
    rt = bool(m.get("realtime"))
    T = []
    for name in ("spec", "observe", "submit"):
        t = schema.tool(name)
        props = t["inputSchema"]["properties"]
        for k in EO_DROP:
            props.pop(k, None)
        if name == "observe":
            t["description"] += (" A match keeps no recording: `last_s` > 0 returns the sport's own frames of now "
                                 "(spec timing.deviations); `view` is the match's tiled image (game observe's) as a "
                                 ".png; meta.state is your seat's state, meta.observation the rest of the observation "
                                 "(tiles, query results). The sport's observe query and team_since go in `fields`.")
        if name == "submit":
            props["actions"] = {"type": "array", "minItems": 1,
                                "description": "rows: the match's JSON action objects ({\"type\": ..., fields}; "
                                               "`spec` action_types), or numeric rows in a type's `layout`"}
            props["interpolate"] = {"type": "string", "enum": ["hold"],
                                    "description": "\"hold\" with `seconds` and no rows: a hold chunk"}
            if not rt:
                props.pop("at", None)
            t["description"] = (
                "POST /submit: your action rows (the match's JSON action objects, `spec` action_types; or numeric "
                "rows in a type's `layout`), with these header fields (`entity` and others in `fields`). "
                + ("Realtime: answers at once; the rows become the plan of their entity from control step `at`. "
                   if rt else
                   "A turn-based match takes one action per turn; a lockstep match runs the rows, the world waiting "
                   "between submits. ")
                + "A hold chunk (`interpolate` \"hold\", `seconds`, no rows) lets time pass with the command in force "
                "(turn-based: waits up to `seconds` for your turn). The result's `step` repeats the reply's duration "
                "and `done`; meta carries `score`, `review_due` (send `ready`), `match_over` and your `state`. "
                "Before the start or while the world is frozen nothing runs (`ok` false, `not_now`).")
        T.append(t)
    T.append({"name": "start", "description": "POST /start (the match extension): you are ready; the match begins "
              "when every seat has started.", "inputSchema": _obj()})
    T.append({"name": "ready", "description": "POST /ready (the match extension): your review when `review_due`: why "
              "you played as you did and your plan, each at most 2000 characters.",
              "inputSchema": _obj({"why": {"type": "string", "maxLength": 2000},
                                   "plan": {"type": "string", "maxLength": 2000}}, ["why", "plan"])})
    if m.get("team"):
        T.append({"name": "say", "description": "POST /say (team formats): a message to your teammates, never shown "
                  "to the other side.", "inputSchema": _obj({"text": {"type": "string"}}, ["text"])})
        T.append({"name": "team", "description": "POST /team (team formats): your teammates' messages after seq "
                  "`since`.", "inputSchema": _obj({"since": {"type": "integer", "minimum": 0}})})
    for t in T:
        t["inputSchema"]["$schema"] = DRAFT
    return T


class EOMatch(RcbTools):
    """The RCB tools against the match's eai-standard service, plus its extension calls."""

    HEADER = ("dt", "at", "cameras", "video", "video_fps", "note")

    def submit(self, type, actions=None, actions_file=None, inline_cameras=None, **args):   # noqa: A002 (the wire's name)
        """Rows as the match takes them: a JSON body {type, rows, ...} (JSON action objects or numeric rows)."""
        self.connect()
        given = {**args, **(args.get("fields") or {})}
        if actions is None and actions_file is None and given.get("interpolate") == "hold" \
                and given.get("seconds") is not None:
            return self._hold(type, inline_cameras, args)
        if given.get("seconds") is not None:
            raise ToolError("`seconds` makes a hold chunk: interpolate \"hold\" and no rows (actions / actions_file)")
        if (actions is None) == (actions_file is None):
            raise ToolError("give the rows as `actions` or as `actions_file`, one of them (or, to let time pass, a "
                            "hold chunk: interpolate \"hold\" and `seconds`)")
        if actions_file:
            try:
                p = workspace.resolve_under_root(actions_file, must_exist=True)
            except ValueError as e:
                raise ToolError(str(e))
            if p.suffix == ".json":
                actions = json.loads(p.read_text())
            elif p.suffix == ".npy":
                actions = np.load(p, allow_pickle=False).tolist()
            elif p.suffix == ".csv":
                actions = np.loadtxt(p, delimiter=",", ndmin=2).tolist()
            else:
                raise ToolError("actions_file: .json, .npy or .csv")
        if isinstance(actions, dict):
            actions = [actions]
        if not isinstance(actions, list) or not actions:
            raise ToolError("actions: a list of rows (action objects or numeric rows)")
        self.n += 1
        body = {"type": type, "rows": actions, **self._fields(args, self.HEADER + ("interpolate",))}
        body.setdefault("note", f"efe-mcp:submit#{self.n}")
        return self._submitted(self._post_json_rcb1("/submit", body), inline_cameras)

    def _post_json_rcb1(self, path, body):
        import requests
        self._log(path, note=str(body.get("note", "")))
        try:
            r = requests.post(self.base + path, json=_jsonable(body), timeout=(5, self._timeout()))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            return self._lost(path, None, e)
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/x-rcb1"):
            return self._rcb1().decode(r.content)
        if r.status_code == 200:
            return {"reply": _jsonable(r.json())}
        return self._refusal(path, r)

    def reply(self, rep, inline=None):
        """The RCB reply, with the match's own image (part `view`, bytes of a PNG) written as a .png."""
        if isinstance(rep, dict):
            return rep, []
        meta, parts = rep
        pngs = {n: p for n, p in parts.items() if p.get("kind") == "bytes" and p.get("format") == "png"}
        res, extras = super().reply((meta, {n: p for n, p in parts.items() if n not in pngs}), inline)
        if pngs:
            w = workspace.Writer()
            for name, p in pngs.items():
                f = w.path(name.replace("/", "_"), "png")
                f.write_bytes(bytes(p["data"]))
                res["parts"][name] = {**{k: _jsonable(v) for k, v in p.items() if k not in ("data", "name", "len")},
                                      "file": str(f), "image": str(f)}
            w.prune()
        return res, extras

    def _ext(self, path, body):
        self.connect()
        return self.post_json(path, body), []

    def start(self, **_):
        return self._ext("/start", {})

    def ready(self, why, plan, **_):
        if len(why) > 2000 or len(plan) > 2000:
            raise ToolError("why and plan: at most 2000 characters each")
        return self._ext("/ready", {"why": why, "plan": plan})

    def say(self, text, **_):
        return self._ext("/say", {"text": text})

    def team(self, since=0, **_):
        return self._ext("/team", {"since": int(since)})


# --------------------------------------------------------------------------------------------------------- dispatch
KINDS = {"eo-match": (eo_tools, EOMatch)}


def _kind(m):
    k = m.get("kind")
    if k not in KINDS:
        raise ValueError(f"unknown tool kind {k!r}")
    return KINDS[k]


def tools_for(m):
    return _kind(m)[0](m)


def adapter_for(m):
    return _kind(m)[1](m)
