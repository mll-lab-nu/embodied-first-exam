"""Authenticated MCP and a transparent, per-HTTP-attempt model meter."""
from __future__ import annotations

import contextvars
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import threading
import urllib.error
import urllib.request

from humanclaw_bench.experiments.recorder import event, span
from humanclaw_bench.harnesses.services import flattened_tools, trace_payload
from .protocol import mcp_result


def provider_headers(headers):
    """Keep scheduling/retry semantics and request IDs without copying secrets."""
    return {key: value for key, value in headers.items()
            if key.lower() in {"x-request-id", "apim-request-id", "retry-after", "retry-after-ms",
                               "x-should-retry", "x-codex-turn-state", "openai-processing-ms"}
            or key.lower().startswith("x-ratelimit-")}


class MeteredService:
    """Serve authenticated common tools and meter actual provider HTTP attempts."""
    def __init__(self, bridge, *, upstream_url, api_key, azure=True, timeout=600,
                 allowed_models=(), responder=None):
        """Bind the loopback gateway to one run and one allowed model manifest."""
        self.bridge, self.upstream_url = bridge, upstream_url.rstrip("/")
        self.api_key, self.azure, self.timeout = api_key, azure, timeout
        self.allowed_models, self.responder = set(allowed_models), responder
        self.bearer = secrets.token_urlsafe(32)
        self.context = contextvars.copy_context()
        self.contexts = {}
        self.calls, self.usage = 0, []
        self.call_names, self.requested_calls, self.exposed = {}, set(), set()
        self.tools_listed = threading.Event()
        self.closed = threading.Event()
        self._lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            """Handle public gateway requests inside the correct recorded context."""
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                """Suppress unstructured access logs that could duplicate sensitive headers."""
                pass

            def handle(self):
                """Tolerate a disconnected client without exposing server tracebacks."""
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def send_json(self, status, value, headers=None):
                """Send a framed JSON response and approved provider response headers."""
                raw = json.dumps(value, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, val in (headers or {}).items():
                    self.send_header(key, val)
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                """Reject unsolicited notification-stream requests."""
                self.send_json(405, {"error": "No unsolicited notification stream"})

            def do_DELETE(self):
                """Acknowledge stateless MCP session cleanup."""
                self.send_json(200, {})

            def do_POST(self):
                """Authenticate the session and restore its causal trace context."""
                if self.headers.get("Authorization") != "Bearer " + service.bearer:
                    self.send_json(401, {"error": "Session authentication required"})
                    return
                context = service.contexts.get(self.headers.get("X-Bench-Context"), service.context)
                context.copy().run(self.post)

            def post(self):
                """Validate and route common tool, MCP and model requests."""
                try:
                    size = int(self.headers.get("Content-Length", 0))
                    if not 0 < size <= 128 * 1024 * 1024:
                        raise ValueError("Invalid request size")
                    if self.headers.get("Content-Encoding", "identity") != "identity":
                        raise ValueError("Compressed request is unsupported")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError("Expected JSON object")
                except (ValueError, UnicodeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                    return
                if self.path == "/mcp":
                    service.mcp(self, payload)
                elif self.path in {"/v1/responses", "/v1/responses/compact", "/v1/chat/completions"}:
                    service.model(self, payload, self.path.removeprefix("/v1"))
                elif self.path == "/tools/call":
                    # Same envelope and dispatcher as MCP. The run_id must be
                    # supplied explicitly on the lower-level JSON transport.
                    if payload.get("run_id") != service.bridge.run_id:
                        self.send_json(400, {"error": "Wrong run_id"})
                        return
                    args = dict(payload.get("arguments") or {})
                    args.update(request_id=payload.get("request_id"), observation_id=payload.get("observation_id"))
                    result = service.await_tool(payload.get("tool_name"), args)
                    self.send_json(200, result)
                else:
                    self.send_json(404, {"error": "Unknown public endpoint"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def register_context(self):
        """Associate a local client with its current role or tool span."""
        key = secrets.token_urlsafe(24)
        self.contexts[key] = contextvars.copy_context()
        return key

    def __enter__(self):
        # Compute nodes may inherit an outbound HTTP proxy. Local SDK clients
        # must reach this session's loopback gateway directly, while the
        # gateway retains the cluster proxy for actual provider requests.
        """Start the gateway with loopback exemptions from inherited proxies."""
        self._proxy_exclusions = {key: os.environ.get(key) for key in ("NO_PROXY", "no_proxy")}
        hosts = [host.strip() for value in self._proxy_exclusions.values()
                 for host in (value or "").split(",") if host.strip()]
        exclusions = ",".join(dict.fromkeys([*hosts, "127.0.0.1", "localhost"]))
        os.environ.update(NO_PROXY=exclusions, no_proxy=exclusions)
        self.thread.start()
        return self

    def __exit__(self, *_):
        """Close the gateway and restore prior proxy exclusions."""
        self.closed.set()
        self.bridge.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        for key, value in self._proxy_exclusions.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def await_tool(self, name, arguments):
        """Wait for owner-thread execution without retrying uncertain actions."""
        future = self.bridge.submit(name, arguments)
        while True:
            try:
                return future.result(timeout=.2)
            except FutureTimeout:
                if self.closed.is_set():
                    future.cancel()
                    raise RuntimeError("Session closed; never retry an uncertain physical execution")

    def mcp(self, handler, message):
        """Implement MCP initialization, discovery and shared tool dispatch."""
        method, ident = message.get("method"), message.get("id")
        if ident is None:
            handler.send_json(202, {})
            return
        params, error = message.get("params") or {}, None
        if method == "initialize":
            version = params.get("protocolVersion", "2025-03-26")
            result = {"protocolVersion": version, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "libero-common-tools", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.bridge.definitions}
            self.tools_listed.set()
            event("mcp.tools_listed", name="libero.mcp", data={"tools": self.bridge.definitions})
        elif method == "tools/call":
            result = mcp_result(self.await_tool(params.get("name"), params.get("arguments", {})))
        else:
            result, error = None, {"code": -32601, "message": "Unknown method"}
        handler.send_json(200, {"jsonrpc": "2.0", "id": ident,
                               **({"error": error} if error else {"result": result})})

    def canonical_name(self, name):
        """Map native namespaced tools back to the common catalog names."""
        for tool in self.bridge.catalog:
            if name == tool or name.endswith("__" + tool):
                return tool
        return name

    def _observe_response(self, value):
        """Extract original usage and native tool-call identities."""
        payload = value.get("response", value)
        usage = payload.get("usage") if isinstance(payload, dict) else None
        item = value.get("item") or {}
        if item.get("type") in {"function_call", "custom_tool_call"}:
            name = self.canonical_name(item.get("name", "unknown"))
            for key in (item.get("id"), item.get("call_id")):
                if key:
                    self.call_names[key] = name
        return usage

    def model(self, handler, payload, endpoint):
        """Forward one actual provider attempt and preserve its response and usage."""
        if self.allowed_models and payload.get("model") not in self.allowed_models:
            event("model.request_rejected", kind="transport", name=endpoint,
                  data={"reason": "model_outside_manifest", "forwarded": False, "request": trace_payload(payload)})
            handler.send_json(400, {"error": "Model outside experiment manifest"})
            return
        with self._lock:
            index = self.calls
            self.calls += 1
            self.usage.append({})
        with span("model" + endpoint.replace("/", "."), kind="model", input=trace_payload(payload),
                  attributes={"boundary": "provider_http_request", "request_index": index,
                              "model": payload.get("model"), "transport": endpoint,
                              "stream": payload.get("stream", False)}) as call:
            for namespace, tool in flattened_tools(payload.get("tools", [])):
                tool = tool.get("function", tool)
                name = self.canonical_name(tool.get("name", tool.get("type", "unknown")))
                self.exposed.add(name)
                event("capability.exposed", kind="tool", name=name,
                      data={"native_namespace": namespace, "definition": tool})
            usage, response, headers_sent = None, None, False
            raw_chunks = []
            try:
                if self.responder:
                    raw, content_type = self.responder(endpoint, payload)
                    import io
                    response = io.BytesIO(raw)
                    status, response_headers = 200, {}
                else:
                    headers = {"Content-Type": "application/json"}
                    for key, value in handler.headers.items():
                        if key.lower().startswith(("openai-", "x-openai-", "x-codex-", "x-stainless-")) or key.lower() in {
                                "originator", "session_id", "x-client-request-id"}:
                            headers[key] = value
                    headers["api-key" if self.azure else "Authorization"] = self.api_key if self.azure else "Bearer " + self.api_key
                    request = urllib.request.Request(self.upstream_url + endpoint,
                        data=json.dumps(payload).encode(), headers=headers, method="POST")
                    response = urllib.request.urlopen(request, timeout=self.timeout)
                    status = response.status
                    content_type = response.headers.get("Content-Type", "application/json")
                    response_headers = provider_headers(response.headers)
                call.set_attribute("provider_headers", response_headers)
                call.set_attribute("http_status", status)
                if "text/event-stream" in content_type:
                    handler.send_response(status)
                    handler.send_header("Content-Type", content_type)
                    handler.send_header("Connection", "close")
                    for key, value in response_headers.items():
                        handler.send_header(key, value)
                    handler.end_headers()
                    handler.close_connection = True
                    headers_sent = True
                    sse_data, terminal = [], False
                    for line in response:
                        raw_chunks.append(line)
                        handler.wfile.write(line)
                        handler.wfile.flush()
                        if line.startswith(b"data:"):
                            sse_data.append(line[5:].strip())
                        elif not line.strip() and sse_data:
                            data = b"\n".join(sse_data)
                            sse_data = []
                            if data == b"[DONE]":
                                if endpoint == "/chat/completions":
                                    terminal = True
                                continue
                            value = json.loads(data)
                            event("provider.stream", kind="transport", name=endpoint, data=trace_payload(value))
                            found = self._observe_response(value)
                            if found is not None:
                                usage = found
                            if value.get("type") in {"response.completed", "response.incomplete", "response.failed"}:
                                terminal = True
                            if value.get("type") in {"error", "response.failed"} or value.get("error"):
                                call.fail(value)
                    call.set_output({"raw_sse": b"".join(raw_chunks)})
                    if not terminal:
                        call.fail("Provider stream ended without a terminal event")
                        call.set_attribute("stream_incomplete", True)
                else:
                    raw = response.read()
                    value = json.loads(raw)
                    usage = self._observe_response(value)
                    call.set_output({"response": trace_payload(value)})
                    if value.get("error") or value.get("status") == "failed":
                        call.fail(value)
                    handler.send_json(status, value, response_headers)
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = {"error": raw.decode(errors="replace")}
                call.set_attribute("http_status", exc.code)
                response_headers = provider_headers(exc.headers)
                call.set_attribute("provider_headers", response_headers)
                call.fail(body)
                call.set_output(body)
                usage = self._observe_response(body)
                handler.send_json(exc.code, body, response_headers)
            except Exception as exc:
                call.fail(exc)
                if raw_chunks:
                    call.set_output({"raw_sse": b"".join(raw_chunks)})
                    call.set_attribute("stream_incomplete", True)
                if not headers_sent:
                    handler.send_json(502, {"error": {"message": str(exc), "type": type(exc).__name__}})
            finally:
                if usage is not None:
                    call.set_usage(usage)
                    self.usage[index] = usage
                else:
                    call.set_attribute("usage_missing", True)
                if response is not None:
                    response.close()
