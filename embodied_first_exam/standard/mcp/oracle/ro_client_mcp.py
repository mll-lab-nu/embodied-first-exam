"""The reference solution's seat client in the MCP-only variant of an Embodied Olympics match (kind eo-match): the
task's own ro_client.py (core/client.py: the reference player's loop) with its Seat.call sent through the efe-robot
MCP server instead of the seat API: spec, observe, submit (an action: one JSON row; the player's wait: a hold chunk),
start, ready, say, team; GET /status is answered from observe's meta.state. The tools write the images as files; this
client reads them back into the replies the player expects (state, observation with its PNG). sitecustomize.py puts it
in place of `ro_client` (solution/solve.sh sets EFE_MCP_ORACLE=1), so a passing oracle shows the match is playable
through the tools alone."""
from __future__ import annotations
import base64, importlib.util, json, os, pathlib, sys

SERVER = os.environ.get("EFE_MCP_SERVER", "/opt/tools/efe_mcp/server.py")
HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _real_path() -> pathlib.Path:
    """The task's own ro_client.py: the first one on sys.path (the oracle runs from /solution) that is not this one."""
    if os.environ.get("EFE_MCP_RO_CLIENT"):
        return pathlib.Path(os.environ["EFE_MCP_RO_CLIENT"])
    for d in [os.getcwd()] + sys.path:
        p = pathlib.Path(d or ".") / "ro_client.py"
        if p.is_file() and p.resolve().parent != HERE:
            return p
    return pathlib.Path("/solution/ro_client.py")


_mc = _load("efe_mcp_client", HERE / "mcp_client.py" if (HERE / "mcp_client.py").is_file()       # the solution's copy
            else pathlib.Path(SERVER).parent / "mcp_client.py")
real = _load("ro_client_real", _real_path())
_CLIENT = []


def _tool(name, **args):
    if not _CLIENT:
        here = str(HERE)
        pp = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != here]
        env = {"PYTHONPATH": os.pathsep.join(pp), "EFE_MCP_ORACLE": "0", "EFE_MCP_VIA": "oracle"}
        _CLIENT.append(_mc.McpClient(cmd=[sys.executable, SERVER], env=env))
    try:
        out = _CLIENT[0].call(name, **args)
    except _mc.McpToolError as e:
        msg = str(e)                          # the tools' refusal: "<HTTP status> <path>: <the service's error>"
        code = int(msg[:3]) if msg[:3].isdigit() else 409
        return {"error": msg, "http_status": code}
    if isinstance(out, dict) and out.get("reply_lost"):     # no reply reached the tool server: the seat API's error
        import urllib.error
        raise urllib.error.URLError(f"{out.get('path')}: the reply was lost ({out.get('error')})")
    if isinstance(out, dict) and isinstance(out.get("operation_result"), dict):
        out = out["operation_result"]
    return _with_images(out)


def _with_images(out):
    """A tool's result as the seat API's reply: the match state under both `state` and `now` (the turn-based and the
    lockstep / realtime spelling), the observation with the `view` image back as base64."""
    if not isinstance(out, dict):
        return out
    if out.get("episode_over"):              # a 409 after the end: the seat API's final state
        st = {"done": True, **{k: out[k] for k in ("reason", "won", "winner", "scores") if k in out}}
        return {**out, "state": st, "now": st}
    if "error" in out and "http_status" in out:
        return out
    meta = out.get("meta") if isinstance(out.get("meta"), dict) else {}
    st = meta.get("state") if isinstance(meta.get("state"), dict) else {}
    reply = {k: v for k, v in out.items() if k not in ("meta", "parts", "step", "tool_s")}
    reply.update(state=st, now=st)
    view = (out.get("parts") or {}).get("view")
    if isinstance(view, dict) and view.get("file"):
        ob = dict(meta.get("observation") or {})
        ob["image_png_b64"] = base64.b64encode(pathlib.Path(view["file"]).read_bytes()).decode()
        reply["observation"] = ob
    for k in ("ok", "not_now", "effects", "score"):
        if k in meta:
            reply.setdefault(k, meta[k])
    if meta.get("effects"):
        te = meta["effects"][0]
        reply["took_effect"] = {k: v for k, v in te.items() if k != "row"}
    return reply


_TYPE = []


def _hold_type():
    """The type a hold chunk names (the first of the spec's action types) and its cap, the spec's max_chunk_s."""
    if not _TYPE:
        sp = _tool("spec")
        spec = sp.get("spec") or {}
        if not spec.get("action_types") and sp.get("spec_file"):
            spec = json.loads(pathlib.Path(sp["spec_file"]).read_text())
        types = [t for t in (spec.get("action_types") or {}) if t != "not_yet"]
        cap = spec.get("max_chunk_s")
        _TYPE.extend([types[0] if types else "hold", float(cap) if isinstance(cap, (int, float)) and cap > 0 else 10.0])
    return _TYPE[0], _TYPE[1]


class McpSeat(real.Seat):
    def call(self, ep: str, body: dict | None = None, tries: int = 20) -> dict:
        body = body or {}
        if ep == "spec":
            out = _tool("spec")
            sp = json.loads(pathlib.Path(out["spec_file"]).read_text()) if "spec_file" in out else out.get("spec", out)
            return sp.get("match") or sp
        if ep == "status":                   # no status tool: the state comes back with every result
            return _tool("observe", cameras=[]).get("state") or {}
        if ep in ("start", "ready", "say", "team"):
            args = {"why": body.get("why", ""), "plan": body.get("plan", "")} if ep == "ready" else \
                {"text": body.get("text", "")} if ep == "say" else {"since": int(body.get("since", 0))} if ep == "team" \
                else {}
            return _tool(ep, **args)
        if ep == "wait":                     # a hold chunk: turn-based, a wait for your turn; else dt game seconds
            secs = float(body["timeout_s"]) if "timeout_s" in body else float(body.get("dt", 0.1))
            typ, cap = _hold_type()          # a longer wait is the player's loop's: it waits again
            return _tool("submit", type=typ, interpolate="hold", seconds=min(secs, cap))
        if ep == "observe":
            return _tool("observe", **({"fields": {"query": body["query"]}} if body.get("query") else {}))
        if ep == "act":
            return _tool("submit", type=str(body.get("type", "")), actions=[body])
        raise NotImplementedError(f"{ep}: no efe-robot tool for it")


def _wait_for(base: str, seat: str, deadline_s: float = 300) -> dict:
    return McpSeat(base, seat).call("spec")


real.Seat = McpSeat
real.wait_for = _wait_for
