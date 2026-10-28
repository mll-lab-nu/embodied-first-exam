"""Loopback MCP and an observed Responses transport (no upstream source patch).

Only HTTP model requests are counted as model calls. Native usage notifications
are retained as evidence but are not added again to token totals.
"""

from __future__ import annotations

import contextvars
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import urllib.error
import urllib.request
from typing import Any, Callable

from humanclaw_bench.experiments.recorder import event, span
from .environment import EnvironmentBridge, tool_definitions
from .provider_errors import ProviderBackoff, provider_failure


def flattened_tools(tools, namespace=None):
    """Keep Responses namespaces; Pi currently sends flat function names."""
    for tool in tools:
        if tool.get("type") == "namespace":
            yield from flattened_tools(tool.get("tools", []), tool["name"])
        else:
            yield namespace, tool


def trace_payload(value: Any) -> Any:
    """Convert native base64 image blocks to the recorder's image references."""
    if isinstance(value, list):
        return [trace_payload(item) for item in value]
    if isinstance(value, dict):
        if value.get("type") == "image" and isinstance(value.get("data"), str):
            return {key: trace_payload(item) for key, item in value.items() if key != "data"} | {
                "image_url": f"data:{value.get('mimeType', 'image/png')};base64,{value['data']}"}
        return {key: trace_payload(item) for key, item in value.items()}
    return value


class LocalServices:
    """Stateless Streamable HTTP MCP and per-request Responses observation."""

    def __init__(self, bridge: EnvironmentBridge, *, upstream_url: str | None = None,
                 api_key: str | None = None, azure: bool = True, timeout: float = 600,
                 responder: Callable | None = None, harness: str = "native",
                 model_options: dict[str, Any] | None = None,
                 pi_profile: dict[str, Any] | None = None, deadline: float = float("inf")):
        """Bind authenticated loopback endpoints and capture the session trace context."""
        self.bridge, self.upstream_url = bridge, upstream_url
        self.api_key, self.azure, self.timeout = api_key, azure, timeout
        self.responder = responder
        self.harness = harness
        self.model_options = model_options or {}
        self.pi_profile = pi_profile
        self.deadline = deadline
        self.backoff = ProviderBackoff()
        self.call_names: dict[str, str] = {}
        self.requested_calls: set[str] = set()
        self.bearer = secrets.token_urlsafe(32)
        self.context = contextvars.copy_context()
        self.closed = threading.Event()
        self.calls = 0
        self.usage: list[dict[str, Any]] = []
        self.exposed: set[str] = set()
        self.tools_listed = threading.Event()
        self._lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            """Serve only the loopback MCP and observed Responses endpoints."""
            protocol_version = "HTTP/1.1"

            def handle(self):
                """Tolerate clients closing idle connections during native process shutdown."""
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError):
                    pass  # A native session may close its idle MCP connection.

            def log_message(self, *_args):
                """Keep HTTP access logs from retaining authorization headers."""
                pass  # Request headers, including credentials, never enter logs.

            def do_GET(self):
                """Decline an unsolicited MCP notification stream in stateless mode."""
                self.send_json(405, {"error": "No server-initiated SSE stream"})

            def do_DELETE(self):
                """Acknowledge stateless session cleanup."""
                self.send_json(200, {})

            def do_POST(self):
                """Give each request its own inherited trace context."""
                service.context.copy().run(self.post)

            def send_json(self, status, body):
                """Write a length-delimited JSON response."""
                encoded = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def post(self):
                """Authenticate, bound and parse a local request before dispatch."""
                if self.headers.get("Authorization") != f"Bearer {service.bearer}":
                    self.send_json(401, {"error": "Local session token required"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 128 * 1024 * 1024:
                        raise ValueError("Invalid request length")
                    if self.headers.get("Content-Encoding", "identity") != "identity":
                        raise ValueError("Compressed model requests are unsupported by this adapter")
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError("Expected a JSON object")
                except (ValueError, UnicodeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                    return
                if self.path == "/mcp":
                    service.mcp(self, payload)
                elif self.path == "/v1/responses":
                    service.responses(self, payload)
                else:
                    self.send_json(404, {"error": "Unknown local endpoint"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        """Start the loopback HTTP service without changing the caller context."""
        self.thread.start()
        return self

    def __exit__(self, *_args):
        """Close pending MCP requests and stop accepting local connections."""
        self.closed.set()
        self.bridge.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def mcp(self, handler, message):
        """Implement stateless Streamable HTTP initialization, tool listing and calls."""
        method, ident = message.get("method"), message.get("id")
        if ident is None:
            handler.send_json(202, {})
            return
        params = message.get("params") or {}
        error = None
        if method == "initialize":
            version = params.get("protocolVersion")
            if version not in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}:
                version = "2025-03-26"
            result = {"protocolVersion": version, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "humanclaw-environment", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.bridge.tool_definitions() if hasattr(self.bridge, "tool_definitions") else tool_definitions()}
            self.tools_listed.set()
            event("mcp.tools_listed", name="environment.mcp", data={"count": len(result["tools"])})
        elif method == "tools/call":
            future = self.bridge.submit(params.get("name", ""), params.get("arguments", {}))
            try:
                while True:
                    try:
                        result = future.result(timeout=0.2)
                        break
                    except FutureTimeout:
                        if self.closed.is_set():
                            future.cancel()
                            raise RuntimeError("Episode closed")
            except Exception:
                # The owning thread logs and propagates the actual infrastructure error.
                result = {"isError": True, "content": [{"type": "text", "text":
                    "Environment execution failed; this episode has been terminated."}]}
        else:
            result = None
            error = {"code": -32601, "message": "Method not found"}
        handler.send_json(200, {"jsonrpc": "2.0", "id": ident,
                               **({"error": error} if error else {"result": result})})

    def responses(self, handler, payload):
        """Record each HTTP attempt, forward its stream and retain raw usage."""
        if self.pi_profile:
            delay = self.backoff.remaining()
            if delay:
                event("model.retry_wait", kind="transport", name="responses", data={"seconds": delay})
            try:
                self.backoff.wait(self.closed, self.deadline)
            except (TimeoutError, InterruptedError) as exc:
                event("model.request_rejected", kind="transport", name="responses", data={"reason": "episode_closed"})
                handler.send_json(408, {"error": {"code": "episode_closed", "message": str(exc)}})
                return
        native_payload = payload
        payload = dict(payload)
        if self.model_options.get("send_max_tokens") is False:
            payload.pop("max_output_tokens", None)
        elif self.model_options.get("max_tokens"):
            limit = int(self.model_options["max_tokens"])
            payload["max_output_tokens"] = min(limit, int(payload.get("max_output_tokens") or limit))
        if self.model_options.get("send_temperature") is False:
            payload.pop("temperature", None)
        elif "temperature" in self.model_options:
            payload["temperature"] = self.model_options["temperature"]
        with self._lock:
            self.calls += 1
            index = self.calls
            self.usage.append({})
        with span("model.responses", kind="model", input=trace_payload(payload), attributes={
            "model": payload.get("model"), "boundary": "provider_http_request",
            "transport": "responses", "request_index": index,
            "synthetic": self.responder is not None,
            "effective_reasoning_effort": (payload.get("reasoning") or {}).get("effort"),
            "effective_max_output_tokens": payload.get("max_output_tokens"),
        }) as call:
            if native_payload != payload:
                event("model.request_normalized", kind="transport", name="responses",
                      data={"native_request": trace_payload(native_payload),
                            "effective_max_output_tokens": payload.get("max_output_tokens"),
                            "effective_temperature": payload.get("temperature")})
            for namespace, tool in flattened_tools(payload.get("tools", [])):
                name = tool.get("name") or tool.get("type", "unknown")
                if namespace:
                    name = namespace + "__" + name
                # Names sent by the two native clients have different MCP prefixes.
                canonical = self.canonical_name(name)
                event("capability.exposed", kind="tool", name=canonical,
                      data={"native_name": name, "boundary": "provider_request", "definition": tool})
                self.exposed.add(canonical)
            response = None
            headers_sent = False
            try:
                if self.pi_profile:
                    caps = self.pi_profile["model_capabilities"]
                    effort = (payload.get("reasoning") or {}).get("effort")
                    if effort not in caps["effort_map"].values():
                        raise ValueError("Pi delivered an undeclared reasoning effort")
                    def image_count(value):
                        """Count images in the effective provider payload without changing it."""
                        if isinstance(value, dict):
                            return int(value.get("type") == "input_image") + sum(image_count(v) for v in value.values())
                        return sum(map(image_count, value)) if isinstance(value, list) else 0
                    count = image_count(payload.get("input", []))
                    if self.pi_profile["context_management"] and not 0 <= count <= caps["max_images"]:
                        raise ValueError("Pi outgoing image count violates the declared context budget")
                    event("model.embodied_parameters", kind="transport", name="responses", data={
                        "request_index": index, "delivered_effort": effort, "image_count": count,
                        "max_output_tokens": payload.get("max_output_tokens"),
                        "image_budget_owner": "pi_projection" if self.pi_profile["context_management"] else "native"})
                if self.model_options.get("model") and payload.get("model") != self.model_options["model"]:
                    raise ValueError("Native harness requested a model outside the configured comparison")
                if self.responder is not None:
                    events = self.responder(payload, index)
                else:
                    if not self.upstream_url or not self.api_key:
                        raise ValueError("Responses URL and API credential are required for live calls")
                    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
                    headers["api-key" if self.azure else "Authorization"] = (
                        self.api_key if self.azure else "Bearer " + self.api_key)
                    request = urllib.request.Request(self.upstream_url,
                        data=json.dumps(payload).encode(), headers=headers, method="POST")
                    response = urllib.request.urlopen(request, timeout=self.timeout)
                    events = self._response_events(response)
                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")
                handler.send_header("Connection", "close")
                handler.end_headers()
                headers_sent = True
                handler.close_connection = True
                completed = False
                for item in events:
                    event("provider.stream", kind="transport", name="responses", data=trace_payload(item))
                    tool_call = item.get("item") or {}
                    if tool_call.get("type") in {"function_call", "custom_tool_call"}:
                        name = tool_call.get("name", "unknown")
                        if tool_call.get("namespace"):
                            name = tool_call["namespace"] + "__" + name
                        for ident in (tool_call.get("call_id"), tool_call.get("id")):
                            if ident:
                                self.call_names[ident] = self.canonical_name(name)
                        if item.get("type") == "response.output_item.done":
                            self.record_tool_request(tool_call)
                    if item.get("type") in {"response.completed", "response.incomplete", "response.failed"}:
                        result = item.get("response", {})
                        for output in result.get("output", []):
                            self.record_tool_request(output)
                        call.set_output(trace_payload(result))
                        call.set_usage(result.get("usage") or {})
                        self.usage[index - 1] = result.get("usage") or {}
                        completed = True
                        if item["type"] != "response.completed":
                            call.fail({"type": item["type"], "details": result.get("error") or result.get("incomplete_details")})
                            failure = provider_failure(error=result.get("error"), incomplete=result.get("incomplete_details"))
                            call.set_attribute("provider_failure", failure)
                            if self.pi_profile:
                                self.backoff.failed(failure, response.headers if response is not None else None)
                        elif self.pi_profile:
                            self.backoff.succeeded()
                    if item.get("type") == "error":
                        call.fail(item)
                        failure = provider_failure(error=item.get("error") or item)
                        call.set_attribute("provider_failure", failure)
                        if self.pi_profile:
                            self.backoff.failed(failure, response.headers if response is not None else None)
                    encoded = json.dumps(item).encode()
                    handler.wfile.write(b"data: " + encoded + b"\n\n")
                    handler.wfile.flush()
                if not completed:
                    call.fail({"type": "IncompleteResponse", "message": "No terminal response event"})
            except urllib.error.HTTPError as exc:
                # Retain provider error body/status, never authorization headers.
                body = exc.read()
                call.set_attribute("http_status", exc.code)
                try:
                    decoded = json.loads(body)
                except (ValueError, UnicodeError):
                    decoded = {}
                failure = provider_failure(status=exc.code, error=decoded.get("error") if isinstance(decoded, dict) else None)
                call.set_attribute("provider_failure", failure)
                if self.pi_profile:
                    self.backoff.failed(failure, exc.headers)
                call.set_output({"body": body.decode("utf-8", errors="replace")})
                call.fail({"type": "ProviderHTTPError", "status": exc.code})
                handler.send_json(exc.code, {"error": {"message": body.decode("utf-8", errors="replace")}})
            except Exception as exc:
                call.fail(exc)
                if not headers_sent:
                    try:
                        handler.send_json(502, {"error": {"message": "Responses transport failed"}})
                    except OSError:
                        pass
                else:
                    try:
                        handler.wfile.write(b'data: {"type":"error","message":"Responses transport failed"}\n\n')
                        handler.wfile.flush()
                    except OSError:
                        pass
            finally:
                if response is not None:
                    response.close()

    def canonical_name(self, name):
        """Join native exposure names to benchmark tools or harness namespaces."""
        if name.startswith("mcp__humanclaw__"):
            return name[len("mcp__humanclaw__"):]
        return self.harness + "." + name

    def record_tool_request(self, item):
        """Count provider requests even when native execution is not observable."""
        if item.get("type") not in {"function_call", "custom_tool_call"}:
            return
        ident = item.get("call_id") or item.get("id")
        if not ident:
            return
        with self._lock:
            if ident in self.requested_calls:
                return
            self.requested_calls.add(ident)
            if item.get("id"):
                self.requested_calls.add(item["id"])
            name = item.get("name", "unknown")
            if item.get("namespace"):
                name = item["namespace"] + "__" + name
            canonical = self.canonical_name(name)
            self.call_names[ident] = canonical
            arguments = item.get("arguments", item.get("input"))
            try:
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            except ValueError:
                parsed = arguments
            if canonical in {tool["name"] for tool in tool_definitions()} and isinstance(parsed, dict):
                request_id = parsed.get("request_id")
                if isinstance(request_id, str):
                    self.bridge.provider_requests.setdefault((canonical, request_id), []).append(ident)
            event("tool.requested", kind="tool", name=canonical,
                  data={"native_call_id": ident, "arguments": parsed, "boundary": "provider_response"})

    @staticmethod
    def _response_events(response):
        """Decode JSON or SSE provider responses without dropping terminal usage."""
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            result = json.load(response)
            yield {"type": "response.completed", "response": result}
            return
        data = []
        for line in response:
            line = line.decode("utf-8").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                value = "\n".join(data)
                data.clear()
                if value != "[DONE]":
                    yield json.loads(value)
        if data and "\n".join(data) != "[DONE]":
            yield json.loads("\n".join(data))
