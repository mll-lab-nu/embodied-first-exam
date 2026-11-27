"""A task's own robot client with its HTTP sent through the efe-robot MCP server's endpoint tools (verification).

The module is the task's `rcb_client.py` (EFE_MCP_TOOLS_DIR, else /opt/tools), loaded unchanged, with its `requests`
replaced: every request it would send to the service goes to the endpoint tool of the same endpoint instead (GET /spec ->
`spec`, POST /observe -> `observe`, POST /submit -> `submit`, POST /reset -> `reset`, POST
/kinematics -> `kinematics`, POST /finish -> `finish`; GET /status, which has no tool, is answered from the meta of the
last reply, where its fields are; GET /operations/<id> likewise has none: the server re-queries it itself after a lost
reply, which reaches the client as the ConnectionError the request would have raised, and the record it fetched answers the
client's own GET /operations/<id>), with the client's request
fields passed unchanged (`fields`; a submit's rows as an .npy file, their dtype kept), and the tool's reply (the
service's meta, each part as a file) encoded back into the RCB1 bytes the client decodes. An oracle written for the
client therefore runs unchanged over the tools: the same requests reach the service, and the same replies reach the
oracle (arrays bit for bit), so the episode (trajectory, verdict) is the API path's.

With EFE_MCP_ORACLE=1, sitecustomize.py puts this module in place of `rcb_client` in every Python process."""
from __future__ import annotations
import importlib.util, json, os, pathlib, sys
from urllib.parse import urlsplit

import numpy as np

SERVER = os.environ.get("EFE_MCP_SERVER", "/opt/tools/efe_mcp/server.py")
TOOLS_DIR = os.environ.get("EFE_MCP_TOOLS_DIR") or "/opt/tools"
HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mcp_client_path():
    here = HERE / "mcp_client.py"
    return here if here.is_file() else pathlib.Path(SERVER).parent / "mcp_client.py"


_mc = _load("efe_mcp_client", _mcp_client_path())
McpClient, McpToolError = _mc.McpClient, _mc.McpToolError
if TOOLS_DIR not in sys.path:
    sys.path.append(TOOLS_DIR)               # rcb1 (the client imports it)
import rcb1                                  # noqa: E402
import requests as _requests                 # noqa: E402

_CLIENT = None
CALLS: list = []                             # the tools called, in order (tests read it)


def _client() -> McpClient:
    global _CLIENT
    if _CLIENT is None:
        pp = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != str(HERE)]
        env = {"PYTHONPATH": os.pathsep.join(pp) or TOOLS_DIR, "EFE_MCP_ORACLE": "0", "EFE_MCP_VIA": "oracle"}
        _CLIENT = McpClient(cmd=[sys.executable, SERVER], env=env)
    return _CLIENT


class _Response:
    def __init__(self, status: int, content: bytes = b"", ctype: str = "application/json"):
        self.status_code, self.content, self.headers = status, content, {"Content-Type": ctype}

    @property
    def text(self):
        return self.content.decode(errors="replace")

    def json(self):
        return json.loads(self.content.decode())

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _requests.exceptions.HTTPError(f"{self.status_code}: {self.text[:300]}", response=self)


def _json(status, obj):
    return _Response(status, json.dumps(obj).encode())


def _tool(name, **args):
    CALLS.append(name)
    try:
        out = _client().call(name, **args)
    except McpToolError as e:
        p = e.payload if isinstance(e.payload, dict) else {"error": str(e.payload)}
        cat = (p.get("failure") or {}).get("category")
        msg = str(p.get("error", ""))
        code = int(msg[:3]) if msg[:3].isdigit() else (404 if cat == "not_served" else 400)
        return None, _json(code, {"error": msg})
    if isinstance(out, dict) and isinstance(out.get("operation_result"), dict):
        out = out["operation_result"]
    if isinstance(out, dict) and out.get("episode_over"):
        body = {k: v for k, v in out.items() if k not in ("episode_over", "http_status", "path", "tool_s")}
        return None, _json(409, body)
    if isinstance(out, dict) and out.get("reply_lost"):
        # no reply reached the tool server: the client sees what it would have seen, the request failing (and, on the operations layer,
        # GET /operations/<id> answers from the record the server fetched)
        op = out.get("operation")
        if isinstance(op, dict) and (op.get("operation_id") or op.get("id")):
            _OPS[str(op.get("operation_id") or op.get("id"))] = op
        raise _requests.exceptions.ConnectionError(f"{out.get('path')}: the reply was lost ({out.get('error')})")
    return out, None


def _rcb1_reply(out: dict) -> _Response:
    """The tool's reply (meta + part files) as the RCB1 bytes the service sent."""
    parts = []
    for name, info in (out.get("parts") or {}).items():
        kind, f = info["kind"], info["file"]
        extra = {k: v for k, v in info.items() if k not in ("kind", "file", "image", "len")}
        if kind == "array":
            a = np.load(f, allow_pickle=False)
            parts.append((name, "array", np.ascontiguousarray(a).tobytes(), extra))
        elif kind == "json":
            parts.append((name, "json", json.dumps(json.loads(pathlib.Path(f).read_text())).encode(), extra))
        else:
            parts.append((name, kind, pathlib.Path(f).read_bytes(), extra))
    _LAST_META.update(out.get("meta") or {})
    return _Response(200, rcb1.encode(out.get("meta") or {}, parts), "application/x-rcb1")


_N = [0]
_LAST_META: dict = {"done": False, "reason": None}       # GET /status: the fields every reply's meta carries
_OPS: dict = {}                                          # GET /operations/<id>: the records fetched after a lost reply


def _post(url, data=None, json=None, **_):          # noqa: A002 (requests' own keyword)
    path = urlsplit(url).path
    if path in ("/observe", "/submit", "/reset"):
        meta, parts = rcb1.decode(bytes(data)) if data else ({}, {})
        if path == "/submit" and not any(p.get("kind") == "array" for p in parts.values()):
            fields = {k: v for k, v in meta.items() if k != "type"}   # a hold chunk (hold()): no rows
            out, err = _tool("submit", type=meta["type"], fields=fields)
        elif path == "/submit":
            arr = next(p["data"] for p in parts.values() if p.get("kind") == "array")
            d = pathlib.Path(os.environ.get("EFE_MCP_WORKSPACE", "/app")) / "oracle_rows"
            d.mkdir(parents=True, exist_ok=True)
            _N[0] += 1
            f = d / f"rows_{_N[0]:05d}.npy"
            np.save(f, np.asarray(arr), allow_pickle=False)
            fields = {k: v for k, v in meta.items() if k != "type"}
            out, err = _tool("submit", type=meta["type"], actions_file=str(f), fields=fields)
        else:
            out, err = _tool(path[1:], fields=meta)
        if err is not None:
            return err
        if "reply" in out:                          # a JSON answer
            return _json(200, out["reply"])
        return _rcb1_reply(out)
    if path == "/kinematics":
        out, err = _tool("kinematics", body=json or {})
    elif path == "/finish":
        out, err = _tool("finish")
    else:
        return _json(404, {"error": f"no tool for POST {path}"})
    if err is not None:
        return err
    out.pop("tool_s", None)
    return _json(200, out)


def _get(url, **_):
    path = urlsplit(url).path
    if path == "/spec":
        out, err = _tool("spec")
        if err is not None:
            return err
        return _json(200, json.loads(pathlib.Path(out["spec_file"]).read_text()))
    if path == "/status":
        return _json(200, {k: v for k, v in _LAST_META.items() if k not in ("proprio", "cameras")})
    if path.startswith("/operations/"):
        op = _OPS.get(path.rsplit("/", 1)[1])
        if op is None or op.get("known") is False:
            return _json(404, {"error": "unknown operation"})
        return _json(200, op)
    return _json(404, {"error": f"no tool for GET {path}"})


class _RequestsViaTools:
    """In place of the client's `requests`: get / post go to the endpoint tools; everything else is requests'."""

    def __getattr__(self, k):
        return getattr(_requests, k)

    get = staticmethod(_get)
    post = staticmethod(_post)


real = _load("rcb_client", os.path.join(TOOLS_DIR, "rcb_client.py"))
real.requests = _RequestsViaTools()
real.CALLS = CALLS
