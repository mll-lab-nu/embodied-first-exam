"""Generic public MCP access, shared by discovery and broker-admitted dispatch."""
from __future__ import annotations

import json
import os
import time

from .broker import encoded
from .discovery import http_request


class MCPAccess:
    """Maintain one ordinary Streamable HTTP session per bootstrap access handle."""

    def __init__(self, handle, deadline):
        """Store access settings without exposing credentials or session headers."""
        self.handle, self.deadline = handle, deadline
        self.session, self.version, self.initialized = None, "2025-03-26", False
        self.sequence = 0

    def exchange(self, method, params=None, *, notification=False):
        """Send JSON-RPC and accept JSON or a finite response event stream."""
        self.sequence += 1
        ident = "hc-" + str(self.sequence)
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            message["id"] = ident
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": self.version}
        if self.handle.get("credential_env"):
            headers["Authorization"] = "Bearer " + os.environ[self.handle["credential_env"]]
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        data, response_headers = http_request(self.handle["root"], method="POST", headers=headers,
            body=encoded(message).encode(), timeout=max(.01, min(60, self.deadline - time.monotonic())))
        session = next((v for k, v in response_headers.items() if k.lower() == "mcp-session-id"), None)
        if session:
            self.session = session
        if notification:
            return None
        if data.lstrip().startswith(b"{"):
            result = json.loads(data)
        else:
            items = [json.loads(line[6:]) for line in data.splitlines() if line.startswith(b"data: ")]
            result = next((item for item in items if item.get("id") == ident), {})
        if result.get("id") != ident or "error" in result or "result" not in result:
            raise RuntimeError("MCP request did not complete: " + encoded(result))
        return result["result"]

    def call(self, method, params=None):
        """Initialize once, then use the public protocol without target-specific mappings."""
        if not self.initialized:
            result = self.exchange("initialize", {"protocolVersion": self.version, "capabilities": {},
                "clientInfo": {"name": "humanclaw-public-discovery", "version": "1"}})
            self.version = result["protocolVersion"]
            self.exchange("notifications/initialized", notification=True)
            self.initialized = True
        return self.exchange(method, params)
