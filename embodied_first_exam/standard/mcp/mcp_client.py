"""A minimal MCP stdio client for the efe-robot server (tests and verification).

    from mcp_client import McpClient
    c = McpClient()                                  # spawns python3 /opt/tools/efe_mcp/server.py
    c.call("describe_robot")
    c.call("move_robot", goals=[{"target": "arm", "gripper": 1}])

call() resolves a pending operation by calling observe(operation=...) until it completes, so it returns the final
result; a tool error raises McpToolError."""
from __future__ import annotations
import json, os, pathlib, subprocess, sys, threading

HERE = pathlib.Path(__file__).resolve().parent


class McpToolError(RuntimeError):
    def __init__(self, payload):
        super().__init__(payload.get("error") if isinstance(payload, dict) else str(payload))
        self.payload = payload


class McpClient:
    def __init__(self, cmd=None, env=None, log=None):
        cmd = cmd or [sys.executable, str(HERE / "server.py")]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log or sys.stderr,
                                  env={**os.environ, **(env or {})}, text=True, bufsize=1)
        self.i = 0
        self.lock = threading.Lock()
        self.info = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                "clientInfo": {"name": "efe-mcp-client", "version": "0.1"}})
        self.notify("notifications/initialized")
        self.tools = {t["name"]: t for t in self.request("tools/list")["tools"]}

    def notify(self, method, params=None):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})}) + "\n")
        self.p.stdin.flush()

    def request(self, method, params=None):
        with self.lock:
            self.i += 1
            rid = self.i
            self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}) + "\n")
            self.p.stdin.flush()
            while True:
                line = self.p.stdout.readline()
                if not line:
                    raise RuntimeError("the MCP server exited")
                msg = json.loads(line)
                if msg.get("id") == rid:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg["result"]

    def call_raw(self, name, **args):
        return self.request("tools/call", {"name": name, "arguments": args})

    def call(self, name, **args):
        r = self.call_raw(name, **args)
        payload = json.loads(r["content"][0]["text"])
        if r.get("isError"):
            raise McpToolError(payload)
        while isinstance(payload, dict) and payload.get("pending"):
            r = self.call_raw("observe", operation=payload["operation"])
            payload = json.loads(r["content"][0]["text"])
            if r.get("isError"):
                raise McpToolError(payload)
        return payload

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()
