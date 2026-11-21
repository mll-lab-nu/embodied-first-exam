"""The reference solution's seat client in the MCP-only variant of an Embodied Olympics match (kind eo-match): the
task's own ro_client.py (core/client.py: the reference player's loop) with its Seat.call sent through the efe-robot
MCP server as tool calls (spec, status, start, observe, act, wait, ready, say) instead of HTTP. The tools write the
images as files; this client reads them back into the replies the player expects. sitecustomize.py puts it in place
of `ro_client` (solution/solve.sh sets EFE_MCP_ORACLE=1), so a passing oracle shows the match is playable through the
tools alone."""
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


_mc = _load("efe_mcp_client", pathlib.Path(SERVER).parent / "mcp_client.py")
real = _load("ro_client_real", _real_path())
_CLIENT = []


def _tool(name, **args):
    if not _CLIENT:
        here = str(HERE)
        pp = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.abspath(p) != here]
        env = {"PYTHONPATH": os.pathsep.join(pp), "EFE_MCP_ORACLE": "0"}
        _CLIENT.append(_mc.McpClient(cmd=[sys.executable, SERVER], env=env))
    try:
        out = _CLIENT[0].call(name, **args)
    except _mc.McpToolError as e:
        msg = str(e)
        code = 400 if msg.startswith("HTTP 400") else 429 if "rate limit" in msg else 409
        return {"error": msg, "http_status": code}
    if isinstance(out, dict) and isinstance(out.get("operation_result"), dict):
        out = out["operation_result"]
    return _with_images(out)


def _with_images(out):
    """The service's reply as the HTTP client gets it: image files back to base64, the tools' own keys removed."""
    if not isinstance(out, dict):
        return out
    out.pop("review_due", None)
    out.pop("match_over", None)
    out.pop("waited_game_s", None)
    ob = out.get("observation")
    if isinstance(ob, dict) and ob.get("image_file"):
        ob["image_png_b64"] = base64.b64encode(pathlib.Path(ob.pop("image_file")).read_bytes()).decode()
        for t in ob.get("tiles") or []:
            if isinstance(t, dict):
                t.pop("file", None)
    for k in [k for k in list(out) if k.endswith("_image_file")]:
        out[k[:-5] + "_b64"] = base64.b64encode(pathlib.Path(out.pop(k)).read_bytes()).decode()
    return out


class McpSeat(real.Seat):
    def call(self, ep: str, body: dict | None = None, tries: int = 20) -> dict:
        body = body or {}
        if ep == "spec":
            out = _tool("spec")
            return json.loads(pathlib.Path(out["spec_file"]).read_text()) if "spec_file" in out else out
        if ep in ("status", "start"):
            return _tool(ep)
        if ep == "wait":
            return _tool("wait") if "timeout_s" in body else _tool("wait", seconds=float(body.get("dt", 0.1)))
        if ep == "observe":
            return _tool("observe", **({"query": body["query"]} if body.get("query") else {}))
        if ep == "act":
            return _tool("act", action=body)
        if ep == "ready":
            return _tool("ready", why=body.get("why", ""), plan=body.get("plan", ""))
        if ep == "say":
            return _tool("say", text=body.get("text", ""))
        if ep == "team":
            return _tool("team", since=int(body.get("since", 0)))
        raise NotImplementedError(f"{ep}: no efe-robot tool for it")


def _wait_for(base: str, seat: str, deadline_s: float = 300) -> dict:
    return McpSeat(base, seat).call("spec")


real.Seat = McpSeat
real.wait_for = _wait_for
