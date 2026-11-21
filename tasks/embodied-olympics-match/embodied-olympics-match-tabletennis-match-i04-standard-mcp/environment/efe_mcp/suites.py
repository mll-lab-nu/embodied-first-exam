"""Tool kinds for suites whose service is not the RCB robot service (manifest "kind"), behind the same server.

kind "eo-match": Embodied Olympics matches (embodied-olympics-match standard tasks): the seat service at
$SIM_URL/$SEAT/ (lockstep `eai-standard/2.x` sports and the turn-based `eai-standard-turn`). One tool per `game`
command, with the same names (spec, status, start, observe, act, wait, ready; say / team for team formats), so the
task text's `game X` reads as the tool X. Results are the service's replies with the images written as PNG files
under /app/obs/ (the full view and one file per tile at native size); `inline_tiles` returns tiles in the result.

Each kind gives: tools_for(m), adapter_for(m), instruction_section(m), transform_instruction(s, m, task)."""
from __future__ import annotations
import base64, io, json, os, re, threading, time, urllib.error, urllib.request

import workspace
from rcb_adapter import ToolError, _jsonable

DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _obj(props=None, required=None):
    s = {"$schema": DRAFT, "type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = list(required)
    return s


# ---------------------------------------------------------------------------------------------------------- eo-match
def eo_turn(m) -> bool:
    return bool(m.get("turn"))


def eo_tools(m) -> list:
    turn = eo_turn(m)
    mw = float(m.get("max_wait_s", 10))
    T = []
    T.append({"name": "spec", "description": "The sport (`game spec`): actions (types, fields, ranges), cameras with "
              "their intrinsics and poses, units, rules, timing. Saved whole as a JSON file under /app/obs/ "
              "(`spec_file`, read it with your file-reading tool); returned inline too when it is small.",
              "inputSchema": _obj()})
    T.append({"name": "status", "description": "The current state, no images (`game status`).", "inputSchema": _obj()})
    T.append({"name": "start", "description": "You are ready (`game start`); the match begins when every seat has "
              "started.", "inputSchema": _obj()})
    T.append({"name": "observe", "description": "The state and the camera images (`game observe`). The image is "
              "written as PNG files under /app/obs/: the whole view, and one file per tile at its native size "
              "(pixel coordinates in a tile file are that camera's own image coordinates). The result lists the tiles "
              "(camera, frame, size, file); `inline_tiles` returns those tiles (by index) in the result as images.",
              "inputSchema": _obj({
                  "query": {"type": "object", "description": "the sport's observe query, if `spec` describes one"},
                  "inline_tiles": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 8,
                                   "description": "indices of tiles to return as images in the result"}})})
    T.append({"name": "act", "description": "One action (`game act JSON`): an object with `type` and the fields "
              "`spec` lists for it (the sport's shortcuts are actions of that type). A refused action returns the "
              "service's error (400: invalid, nothing happens; 409: not now).",
              "inputSchema": _obj({"action": {"type": "object", "description": "the action, e.g. {\"type\": ...}"}},
                                  ["action"])})
    if turn:
        T.append({"name": "wait", "description": "Block until it is your turn, a review is due or the match is over "
                  "(`game wait`). Also collects a pending operation (`operation`).",
                  "inputSchema": _obj({"operation": {"type": "string", "description": "a pending operation's id"}})})
    else:
        T.append({"name": "wait", "description": f"Let the world run for `seconds` of game time (at most {mw:g}; "
                  "`game wait DT` in steps of at most 1 s). It stops early when the world freezes for a review or "
                  "the match ends. Also collects a pending operation (`operation`).",
                  "inputSchema": _obj({"seconds": {"type": "number", "minimum": 0.01, "maximum": mw,
                                                   "description": "game seconds to let pass (default 0.1)"},
                                       "operation": {"type": "string", "description": "a pending operation's id"}})})
    T.append({"name": "ready", "description": "Your review (`game ready \"WHY\" \"PLAN\"`): why you played as you "
              "did and your plan, each at most 2000 characters.",
              "inputSchema": _obj({"why": {"type": "string"}, "plan": {"type": "string"}}, ["why", "plan"])})
    if m.get("team"):
        T.append({"name": "say", "description": "A message to your teammates (`game say`), never shown to the other "
                  "side.", "inputSchema": _obj({"text": {"type": "string"}}, ["text"])})
        T.append({"name": "team", "description": "Your teammates' messages after seq `since` (`game team`).",
                  "inputSchema": _obj({"since": {"type": "integer", "minimum": 0}})})
    return T


class EOMatch:
    """The seat's calls (the core's own client rules: at most 20 requests per second, a bare 429 retried slowly)."""
    MIN_GAP_S = 0.06

    def __init__(self, m: dict):
        self.m = m
        self.base = os.environ.get(m.get("url_env", "SIM_URL"), m.get("url", "http://localhost:8000")).rstrip("/")
        self.seat = os.environ.get(m.get("seat_env", "SEAT"), m.get("seat", "A"))
        self.last = 0.0
        self.lock = threading.Lock()
        self.turn = eo_turn(m)
        self.on_sim = None          # the server's call log: one record per request to the service, before it is sent

    # -- HTTP
    def http(self, ep, body=None, timeout=600, tries=20):
        for i in range(tries):
            with self.lock:
                time.sleep(max(0.0, self.last + self.MIN_GAP_S - time.monotonic()))
                self.last = time.monotonic()
            req = urllib.request.Request(f"{self.base}/{self.seat}/{ep}",
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            if self.on_sim is not None:
                try:
                    self.on_sim({"sim": f"/{self.seat}/{ep}", "method": "GET" if body is None else "POST"})
                except Exception:       # the record never breaks a call
                    pass
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code == 429 and not raw and i + 1 < tries:          # the HTTP layer's limit, not the match's
                    time.sleep(0.25 * (i + 1))
                    continue
                try:
                    out = json.loads(raw)
                except ValueError:
                    out = {"error": str(e)}
                out["http_status"] = e.code
                return out
            except urllib.error.URLError as e:
                if isinstance(e.reason, (BrokenPipeError, ConnectionResetError, ConnectionRefusedError)) and i + 1 < tries:
                    time.sleep(0.25 * (i + 1))
                    continue
                raise ToolError(f"the match service did not answer ({e.reason})", "internal")
        raise ToolError("the match service kept refusing (rate limit)", "internal")

    def checked(self, ep, body=None):
        out = self.http(ep, body)
        if out.get("http_status"):
            st = out.get("now") or out.get("state")
            msg = f"HTTP {out['http_status']}: {out.get('error') or out}"
            if isinstance(st, dict):
                msg += " | state: " + json.dumps(self.small_state(st))[:1500]
            raise ToolError(msg, "invalid" if out["http_status"] == 400 else "not_now")
        return out

    @staticmethod
    def small_state(st):
        return {k: st[k] for k in ("phase", "world", "done", "reason", "your_turn", "awaiting_review", "ready",
                                   "step", "t_sim", "score", "scores", "clock_left_s") if k in st}

    # -- images
    def images(self, out: dict, inline=None):
        """The reply's base64 images as files (PNG); tiles cropped at native size. Returns MCP image extras."""
        extras = []
        w = workspace.Writer()
        ob = out.get("observation")
        if isinstance(ob, dict) and ob.get("image_png_b64"):
            raw = base64.b64decode(ob.pop("image_png_b64"))
            tag = "reply" if ob.get("of") else "view"
            p = w.path(tag, "png")
            p.write_bytes(raw)
            ob["image_file"] = str(p)
            tiles = ob.get("tiles") or []
            if tiles:
                from PIL import Image
                im = Image.open(io.BytesIO(raw))
                im.load()
                for i, t in enumerate(tiles):
                    try:
                        x, y, tw, th = int(t["x"]), int(t["y"]), int(t["width"]), int(t["height"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    name = f"{tag}_t{i}_{t.get('camera', 'cam')}" + (f"_f{t['frame']}" if t.get("frame") is not None else "")
                    crop = im.crop((x, y, x + tw, y + th))
                    tp = w.path(name, "png")
                    crop.save(tp, format="PNG")
                    t["file"] = str(tp)
                    if inline and i in inline:
                        buf = io.BytesIO()
                        crop.save(buf, format="PNG")
                        extras.append({"type": "image", "data": base64.b64encode(buf.getvalue()).decode(),
                                       "mimeType": "image/png"})
        for k in [k for k in list(out) if k.endswith("_image_b64")]:
            if out[k]:
                p = w.path(k[:-10], "png")
                p.write_bytes(base64.b64decode(out.pop(k)))
                out[k[:-4] + "_file"] = str(p)
            else:
                out.pop(k)
        w.prune()
        return extras

    def finish(self, out: dict, inline=None):
        extras = self.images(out, inline)
        st = out.get("now") if isinstance(out.get("now"), dict) else out.get("state") if isinstance(out.get("state"), dict) else out
        if isinstance(st, dict):
            if self.turn:
                due = bool(st.get("awaiting_review")) and bool(st.get("your_turn", True))
            else:
                due = st.get("phase") == "review" and not (st.get("ready") or {}).get(self.seat)
            out["review_due"] = bool(due) and not st.get("done")
            if st.get("done"):
                out["match_over"] = True
        return _jsonable(out), extras

    # -- tools
    def spec(self, **_):
        out = self.checked("spec")
        w = workspace.Writer()
        p = w.path("spec", "json")
        p.write_text(json.dumps(out, indent=1))
        txt = json.dumps(out)
        res = {"spec_file": str(p)}
        if len(txt) <= 24000:
            res["spec"] = out
        else:
            res["summary"] = {k: out[k] for k in ("protocol", "timing", "start", "actions", "seats", "sport")
                              if k in out and len(json.dumps(out[k])) < 8000}
            res["keys"] = sorted(out)
            res["note"] = "the spec is long: the whole of it is in spec_file"
        return res, []

    def status(self, **_):
        return self.finish(self.checked("status"))

    def start(self, **_):
        return self.finish(self.checked("start", {}))

    def observe(self, query=None, inline_tiles=None, **_):
        return self.finish(self.checked("observe", {"query": query} if query else {}), inline_tiles)

    def act(self, action, **_):
        return self.finish(self.checked("act", action))

    def wait(self, seconds=None, **_):
        if self.turn:
            while True:
                out = self.checked("wait", {"timeout_s": 60})
                st = out.get("state") or {}
                if st.get("done") or st.get("your_turn") or st.get("awaiting_review"):
                    return self.finish(out)
        left = float(seconds if seconds is not None else 0.1)
        if left > float(self.m.get("max_wait_s", 10)) + 1e-9:
            raise ToolError(f"seconds: at most {self.m.get('max_wait_s', 10)}")
        waited, out = 0.0, {}
        while left > 1e-9:
            d = min(1.0, left)
            out = self.checked("wait", {"dt": round(d, 6)})
            left -= d
            waited += d
            st = out.get("now") or {}
            if st.get("done") or st.get("world") == "frozen":
                break
        out["waited_game_s"] = round(waited, 3)
        return self.finish(out)

    def ready(self, why, plan, **_):
        if len(why) > 2000 or len(plan) > 2000:
            raise ToolError("why and plan: at most 2000 characters each")
        return self.finish(self.checked("ready", {"why": why, "plan": plan}))

    def say(self, text, **_):
        return self.finish(self.checked("say", {"text": text}))

    def team(self, since=0, **_):
        return self.finish(self.checked("team", {"since": int(since)}))

    def signal(self, **_):
        raise ToolError("no signal tool in this task")


# owner decision D145, in a match's terms (generate.py RULE)
EO_RULE = ("You may write and run code to compute; every robot command and observation must go through the efe-robot "
           "MCP tools; code must not contact the simulator. Each command or observation is a tool call you make "
           "yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is "
           "checked against the server's.")


def eo_section(m) -> str:
    turn = eo_turn(m)
    rows = [("`game spec`", "`spec()`: the whole spec is also saved as a JSON file (`spec_file`)"),
            ("`game status`", "`status()`"),
            ("`game start`", "`start()`"),
            ("`game wait`" if turn else "`game wait DT`",
             "`wait()`: blocks until it is your turn (or a review is due, or the match is over)" if turn else
             f"`wait(seconds)`: up to {float(m.get('max_wait_s', 10)):g} game seconds in one call; it stops early "
             "when the world freezes for a review or the match ends"),
            ("`game observe`", "`observe(query?, inline_tiles?)`: images as PNG files (the view and one file per "
             "tile, native size)"),
            ("`game act JSON` and the sport's shortcuts", "`act(action)`, e.g. `act({\"type\": ..., ...})`"),
            ("`game ready \"WHY\" \"PLAN\"`", "`ready(why, plan)`")]
    if m.get("team"):
        rows += [("`game say \"TEXT\"`", "`say(text)`"), ("`game team [SINCE]`", "`team(since?)`")]
    L = ["## Robot tools (MCP server `efe-robot`)"]
    L.append(_wrap("You play only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` "
                   "tools, for example `mcp__efe-robot__act`). " + EO_RULE + " Where this text names a `game` "
                   "command or its HTTP call (the `game` command is not installed here), use the tool of the same "
                   "name:"))
    L.append("")
    L.append("| `game` command | Tool |")
    L.append("|---|---|")
    L += [f"| {a} | {b} |" for a, b in rows]
    L.append("")
    b = ["Images are files: `observe` (and an action whose reply shows its result) writes them under `/app/obs/`; "
         "open a tile file with your file-reading tool (pixel coordinates in it are the camera's own), or ask for "
         "tiles in the result with `inline_tiles`.",
         "Every result is the service's reply (the state is under `now` or `state`), plus `review_due` (a review is "
         "due from you now: send `ready`) and `match_over`. A refused call returns the service's error (400: an "
         "invalid action, nothing happens; 409: not now). The tools keep under the service's request rate "
         "themselves.",
         "One tool call runs at a time. A call still executing after 45 s returns `{\"pending\": true, "
         "\"operation\": id}`: call `wait(operation=id)` for its result.",
         "Nothing needs to be saved: the server records every tool call, and the service records the match."]
    L += [_wrap(x, "- ", "  ") for x in b]
    if m.get("notes"):
        L.append("")
        L.append(_wrap("**Notes.** " + str(m["notes"])))
    return "\n".join(L) + "\n"


def _wrap(t, first="", rest=""):
    import textwrap
    t = re.sub(r"`[^`]*`", lambda mm: mm.group(0).replace(" ", "\0"), t)
    return textwrap.fill(t, 120, initial_indent=first, subsequent_indent=rest, break_long_words=False,
                         break_on_hyphens=False).replace("\0", " ")


GAME_REF = [   # the task text's `game ...` references -> the tools
    (r'`game ready "WHY" "PLAN"`', "`ready(why, plan)`"),
    (r"`game act JSON`", "`act(action)`"),
    (r"`game wait DT`", "`wait(seconds)`"),
    (r"`game (spec|status|start|wait|observe|ready|say|team)`", r"`\1`"),
]
SECTION_RE = r"(?ms)^## {h}\n.*?(?=^## |\Z)"


def eo_transform_instruction(s: str, m: dict, task) -> str:
    lines = s.split("\n")
    if lines and lines[0].startswith("# ") and "MCP" not in lines[0]:
        lines[0] += " — MCP tools only"
    s = "\n".join(lines)
    # the program section: how you play here; the container's tooling line goes
    def prog(mm):
        sec = mm.group(0)
        sec = re.sub(r"(?s)^## Write a program\n.*?(?=\n- |\n\n)", "## How you play\nYou play by calling the "
                     "`efe-robot` tools yourself, one call at a time (`## Robot tools` below). Only you send `start` "
                     "and `ready`.", sec, count=1)
        sec = re.sub(r"(?ms)^- Your container:.*?(?=^- |^\n|^#|\Z)", "", sec)
        return sec
    s = re.sub(SECTION_RE.format(h="Write a program"), prog, s, count=1)
    for a, b in (("your thinking, your program's computation and", "your thinking and"),
                 ("(`POST /wait`, at most DT game seconds, then it stops again)",
                  "(at most the game seconds you give, then it stops again)"),
                 ("so a program has to keep calling", "so you have to keep calling"),
                 ("(your program's log, `game status`)", "(`status`)"),
                 ("and prepare your program first", "first"),
                 ("tool calls, your programs and your reviews all count", "tool calls and your reviews all count")):
        s = s.replace(a, b)
    for a, b in GAME_REF:
        s = re.sub(a, b, s)
    s = re.sub(r"`game (\w+)[^`]*`", lambda mm: f"`act` (type `{mm.group(1)}`)", s)    # the sport's shortcuts
    s = re.sub(SECTION_RE.format(h="Interface"), lambda mm: eo_section(m) + "\n", s, count=1)
    return s


# --------------------------------------------------------------------------------------------------------- dispatch
KINDS = {"eo-match": (eo_tools, EOMatch, eo_section, eo_transform_instruction)}


def _kind(m):
    k = m.get("kind")
    if k not in KINDS:
        raise ValueError(f"unknown tool kind {k!r}")
    return KINDS[k]


def tools_for(m):
    return _kind(m)[0](m)


def adapter_for(m):
    return _kind(m)[1](m)


def instruction_section(m):
    return _kind(m)[2](m)


def transform_instruction(s, m, task):
    return _kind(m)[3](s, m, task)
