#!/usr/bin/env python3
"""EFE Robot MCP server (efe-robot), MCP over stdio: newline-delimited JSON-RPC 2.0.

    python3 /opt/tools/efe_mcp/server.py [--manifest PATH] [--max-block-s 45]

Tools: describe_robot, observe, move_robot, locomote, execute_trajectory, wait, signal (schema/tools.v0.json, narrowed
to the robot of the manifest). Conventions: the robot base frame at the start of each call (+X forward, +Y left,
+Z up), metres / radians, quaternions wxyz, gripper 0 = open .. 1 = closed. Images, depth and video are written under
/app/obs; results carry paths and small JSON. A call that runs longer than --max-block-s returns
{"pending": true, "operation": id}; `wait(operation=id)` (or any later call) waits for it.

Standard library + numpy (+ pillow for images); the robot is reached through the task's own /opt/tools/rcb_client.py.
The server does not contact the robot before the first tools/call."""
from __future__ import annotations
import argparse, json, os, pathlib, sys, threading, time, traceback, uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SERVER_NAME = "efe-robot"
SERVER_VERSION = "0.1.0"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


class Ops:
    """Runs one tool call at a time in a worker thread; a call longer than max_block returns as pending."""

    def __init__(self, max_block: float):
        self.max_block = max_block
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
                    "note": f"operation {oid} ({self.cur[2]['tool']}) is still running; call wait(operation=\"{oid}\")"}, []
        oid = uuid.uuid4().hex[:8]
        box = {"tool": name, "t0": time.time()}

        def work():
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
                "note": f"{name} is still executing after {self.max_block:.0f} s; call wait(operation=\"{oid}\") for its result"}, []

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
            return {"pending": True, "operation": oid, "note": "still executing; call wait again"}, []
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
            from rcb_adapter import RcbAdapter
            self.adapter = RcbAdapter(self.manifest)
        else:
            import suites
            self.adapter = suites.adapter_for(self.manifest)
        self.ops = Ops(max_block)
        self.log = None
        self.out = sys.stdout
        self.wlock = threading.Lock()

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
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": self.manifest.get("server_instructions") or
                    "Robot control tools. Call describe_robot first. Frame: the robot base at the start of each call "
                    "(+X forward, +Y left, +Z up), m and rad, quaternions wxyz, gripper 0 open 1 closed. Images are "
                    "files under /app/obs: open them with your file-viewing tool."}
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

    def log_call(self, name, args, t0, out):
        """One line per tool call in the call log (EFE_MCP_LOG, default /logs/agent/efe-mcp.jsonl, the agent's log
        directory the runner collects): what the robot was told through this server (scripts/mcp_only.py audit)."""
        try:
            if self.log is None:
                p = pathlib.Path(os.environ.get("EFE_MCP_LOG") or "/logs/agent/efe-mcp.jsonl")
                if not p.parent.is_dir():
                    self.log = False
                    return
                self.log = open(p, "a", buffering=1)
            if not self.log:
                return
            small = {k: (f"<{len(v)} rows>" if isinstance(v, list) and k in ("rows", "native_rows") else v)
                     for k, v in args.items()}
            txt = (out.get("content") or [{}])[0].get("text", "")
            self.log.write(json.dumps({"ts": round(t0, 3), "dur_s": round(time.time() - t0, 3), "tool": name,
                                       "args": small, "error": bool(out.get("isError")),
                                       "pending": '"pending":true' in txt[:200]}, default=str) + "\n")
        except Exception:      # the log never breaks a call
            pass

    def call(self, name, args):
        t0 = time.time()
        out = self._call(name, args)
        self.log_call(name, args, t0, out)
        return out

    def _call(self, name, args):
        from rcb_adapter import ToolError
        try:
            if name not in self.by_name:
                raise ToolError(f"unknown tool {name!r}")
            self.schema.validate_args(self.by_name[name]["inputSchema"], args)
            if name == "wait" and args.get("operation"):
                try:
                    result, extras = self.ops.wait_for(args["operation"])
                except KeyError:
                    raise ToolError(f"no pending operation {args['operation']!r}")
                if not (isinstance(result, dict) and result.get("pending")) and float(args.get("seconds") or 0) > 0:
                    more, extras2 = self.ops.run("wait", self.adapter.wait,
                                                 {k: v for k, v in args.items() if k != "operation"})
                    result = {"operation_result": result, "then": more}
                    extras = list(extras) + list(extras2)
            else:
                fn = getattr(self.adapter, name)
                result, extras = self.ops.run(name, fn, args)
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
