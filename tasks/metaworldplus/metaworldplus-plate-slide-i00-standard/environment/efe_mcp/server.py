#!/usr/bin/env python3
"""EFE Robot MCP server (efe-robot), MCP over stdio: newline-delimited JSON-RPC 2.0.

    python3 /opt/tools/efe_mcp/server.py [--manifest PATH] [--max-block-s 45]

Tools (schema/tools.json, narrowed to the task by its manifest; rcb_tools.py): one per agent-facing endpoint of the
task's robot service -- spec, observe, submit, finish, reset (where the task has a reset budget), kinematics (where the
service offers it) -- the request fields and the reply as the service's client sends and receives them
(docs/protocol/standard_mode.md "MCP tools"); a service with calls of its own adds their tools (suites.py: an
Embodied Olympics match's start, ready, say, team). Images, depth and video are written under /app/obs; results carry
paths and the service's meta, and `tool_s` (the wall time the call took in this server, the request included). A call that runs longer than
--max-block-s returns {"pending": true, "operation": id}; `observe(operation=id)` waits for it. Realtime mode: no tool
holds the clock (submit answers at once, as the service does). A tool the manifest does not list but /spec shows the
service has (kinematics, reset) is added at the first call, with a tools/list_changed notification.

Standard library + numpy + requests (+ pillow for images), what every standard agent container has.
The server does not contact the robot before the first tools/call.

Call log (EFE_MCP_LOG, default /logs/agent/efe-mcp.jsonl, the agent's log directory the runner collects): a `server` line when the log is opened (this process, the process that started it), one line per tool
call, and one `sim` line per request to the robot service, written before the request is sent."""
from __future__ import annotations
import argparse, json, os, pathlib, sys, threading, time, traceback, uuid

sys.dont_write_bytecode = True     # no __pycache__ next to the server (a task's environment/efe_mcp/, /opt/tools)
VIA = os.environ.get("EFE_MCP_VIA", "")[:32]      # who started this server, if not the agent's harness (call log)


def _proc(pid: int) -> dict:
    """A process's name and command line (/proc), for the call log's `server` line."""
    out = {"pid": pid}
    try:
        out["comm"] = pathlib.Path(f"/proc/{pid}/comm").read_text().strip()[:32]
        out["cmd"] = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()[:160]
    except OSError:
        pass
    return out


PARENT = _proc(os.getppid())      # read at start-up: the process that started this server (the harness, or a script)
CTX = threading.local()           # the tool call a worker thread runs (its `sim` lines name it)

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SERVER_NAME = "efe-robot"
SERVER_VERSION = "1.0.0"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
METHODS = {"spec": "spec_"}       # tool -> adapter method, where they differ (RcbTools.spec is the /spec it read)


class Ops:
    """Runs one tool call at a time in a worker thread; a call longer than max_block returns as pending."""

    def __init__(self, max_block: float, collect: str = "observe"):
        self.max_block = max_block
        self.collect = collect      # the tool that collects a pending call (its `operation` argument)
        self.cur = None             # (op id, thread, box)
        self.done: dict[str, dict] = {}

    def _finish_cur(self, timeout):
        if not self.cur:
            return True
        oid, th, box = self.cur
        th.join(timeout)
        if th.is_alive():
            return False
        self.done[oid] = box
        self.cur = None
        return True

    def run(self, name, fn, kwargs):
        if not self._finish_cur(self.max_block):
            oid = self.cur[0]
            return {"pending": True, "operation": oid, "busy": True,
                    "note": f"operation {oid} ({self.cur[2]['tool']}) is still running; call {self.collect}(operation=\"{oid}\")"}, []
        oid = uuid.uuid4().hex[:8]
        box = {"tool": name, "t0": time.time()}

        def work():
            CTX.tool = name
            try:
                box["result"] = fn(**kwargs)
            except BaseException as e:   # reported to the agent, never raised in the loop
                box["error"] = e
                box["tb"] = traceback.format_exc()
        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.cur = (oid, th, box)
        if self._finish_cur(self.max_block):
            return self.take(oid)
        return {"pending": True, "operation": oid,
                "note": f"{name} is still executing after {self.max_block:.0f} s; call {self.collect}(operation=\"{oid}\") for its result"}, []

    def take(self, oid):
        box = self.done.pop(oid)
        if "error" in box:
            raise box["error"]
        return box["result"]

    def wait_for(self, oid):
        if oid in self.done:
            return self.take(oid)
        if self.cur and self.cur[0] == oid:
            if self._finish_cur(self.max_block):
                return self.take(oid)
            return {"pending": True, "operation": oid, "note": f"still executing; call {self.collect}(operation=\"{oid}\") again"}, []
        raise KeyError(oid)


class Server:
    def __init__(self, manifest_path: str, max_block: float):
        self.manifest = json.loads(pathlib.Path(manifest_path).read_text())
        import schema
        self.schema = schema
        self.tools = schema.tools_for(self.manifest)
        self.by_name = {t["name"]: t for t in self.tools}
        kind = self.manifest.get("kind", "rcb")
        if kind == "rcb":
            from rcb_tools import RcbTools
            self.adapter = RcbTools(self.manifest)
        else:
            import suites
            self.adapter = suites.adapter_for(self.manifest)
        self.ops = Ops(max_block, "observe")
        self._checked_spec = False
        self.log = None
        self.llock = threading.Lock()
        self.out = sys.stdout
        self.wlock = threading.Lock()
        if hasattr(self.adapter, "on_sim"):
            self.adapter.on_sim = self.log_sim

    def send(self, msg):
        with self.wlock:
            self.out.write(json.dumps(msg, separators=(",", ":")) + "\n")
            self.out.flush()

    def handle(self, req):
        method, rid = req.get("method"), req.get("id")
        if rid is None:                       # a notification: nothing to answer
            return None
        if method == "initialize":
            want = (req.get("params") or {}).get("protocolVersion")
            return {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": self.manifest.get("server_instructions") or
                    "The robot service's endpoints as tools (spec, observe, submit, finish; reset and kinematics "
                    "where the task has them): the request fields and the reply as the service's own client sends "
                    "and receives them. Call spec first. Images are files under /app/obs: open them with your "
                    "file-reading tool."}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            p = req.get("params") or {}
            return self.call(p.get("name"), p.get("arguments") or {})
        if method in ("resources/list", "prompts/list"):
            return {method.split("/")[0]: []}
        raise LookupError(method)

    def _write(self, rec):
        """One line of the call log (the module docstring); the log never breaks a call."""
        try:
            with self.llock:
                if self.log is None:
                    p = pathlib.Path(os.environ.get("EFE_MCP_LOG") or "/logs/agent/efe-mcp.jsonl")
                    if not p.parent.is_dir():
                        self.log = False
                        return
                    self.log = open(p, "a", buffering=1)
                    self.log.write(json.dumps({"ts": round(time.time(), 3), "server": SERVER_VERSION, "pid": os.getpid(),
                                               "parent": PARENT, **({"via": VIA} if VIA else {})}) + "\n")
                if self.log:
                    self.log.write(json.dumps({**rec, "pid": os.getpid()}, default=str) + "\n")
        except Exception:
            pass

    def log_sim(self, rec):
        """A request to the robot service, before it is sent (RcbTools.on_sim)."""
        self._write({"ts": round(time.time(), 3), **rec, "tool": getattr(CTX, "tool", "")})

    def log_call(self, name, args, t0, out):
        """One line per tool call: what the robot was told through this server."""
        try:
            small = {k: (f"<{len(v)} rows>" if isinstance(v, list) and k in ("rows", "native_rows") else v)
                     for k, v in args.items()}
            txt = (out.get("content") or [{}])[0].get("text", "")
        except Exception:
            return
        self._write({"ts": round(t0, 3), "dur_s": round(time.time() - t0, 3), "tool": name, "args": small,
                     "error": bool(out.get("isError")), **({"via": VIA} if VIA else {}),
                     "pending": '"pending":true' in txt[:200]})

    def call(self, name, args):
        t0 = time.time()
        out = self._call(name, args)
        self.log_call(name, args, t0, out)
        return out

    def _maybe_finish_tool(self):
        """/spec shows an endpoint whose tool the manifest does not list (kinematics: spec `kinematics`; reset: a reset
        budget): add the tool and tell the client (notifications/tools/list_changed)."""
        spec = getattr(self.adapter, "spec", None)
        if self.manifest.get("kind", "rcb") != "rcb" or not isinstance(spec, dict) or self._checked_spec:
            return
        self._checked_spec = True
        want = []
        if "kinematics" in spec:
            want.append("kinematics")
        if isinstance(spec.get("budget"), dict) and (spec["budget"].get("reset") or 0) > 0:
            want.append("reset")
        new = [n for n in want if n not in self.by_name]
        for n in new:
            t = self.schema.tool(n)
            t["inputSchema"]["$schema"] = self.schema.DRAFT
            self.tools.append(t)
            self.by_name[n] = t
        if new:
            self.send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})

    def _call(self, name, args):
        from rcb_tools import ToolError
        t0 = time.time()
        try:
            if name not in self.by_name:
                raise ToolError(f"unknown tool {name!r}")
            self.schema.validate_args(self.by_name[name]["inputSchema"], args)
            if name == "observe" and args.get("operation"):
                try:
                    result, extras = self.ops.wait_for(args["operation"])
                except KeyError:
                    raise ToolError(f"no pending operation {args['operation']!r}")
            else:
                fn = getattr(self.adapter, METHODS.get(name, name), None) or getattr(self.adapter, name)
                result, extras = self.ops.run(name, fn, args)
            if isinstance(result, dict):
                result["tool_s"] = round(time.time() - t0, 3)
            self._maybe_finish_tool()
            content = [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}] + list(extras or [])
            return {"content": content, "isError": False}
        except ToolError as e:
            return {"content": [{"type": "text", "text": json.dumps({"error": str(e), "failure": {"category": e.category}})}],
                    "isError": True}
        except Exception as e:      # an unexpected failure: the message, the call can be retried
            if type(e).__name__ == "EpisodeOver":   # the client's: the episode has ended (success, time, error)
                return {"content": [{"type": "text", "text": json.dumps({"episode_over": True, "reason": str(e)})}],
                        "isError": False}
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            return {"content": [{"type": "text", "text": json.dumps({"error": f"{type(e).__name__}: {e}",
                                                                      "failure": {"category": "internal"}})}],
                    "isError": True}

    def serve(self):
        real_stdout = sys.stdout
        sys.stdout = sys.stderr          # anything printed by the client library must not reach the protocol stream
        self.out = real_stdout
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self.send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
                continue
            reqs = req if isinstance(req, list) else [req]
            for r in reqs:
                try:
                    res = self.handle(r)
                    if res is not None:
                        self.send({"jsonrpc": "2.0", "id": r.get("id"), "result": res})
                except LookupError as e:
                    self.send({"jsonrpc": "2.0", "id": r.get("id"), "error": {"code": -32601, "message": f"method not found: {e}"}})
                except Exception as e:
                    self.send({"jsonrpc": "2.0", "id": r.get("id"), "error": {"code": -32603, "message": str(e)}})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.environ.get("EFE_MCP_MANIFEST") or str(HERE / "manifest.json"))
    ap.add_argument("--max-block-s", type=float, default=float(os.environ.get("EFE_MCP_MAX_BLOCK_S", "45")))
    ap.add_argument("--print-tools", action="store_true", help="print the narrowed tool list and exit")
    a = ap.parse_args(argv)
    s = Server(a.manifest, a.max_block_s)
    if a.print_tools:
        print(json.dumps(s.tools, indent=1))
        return 0
    s.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
