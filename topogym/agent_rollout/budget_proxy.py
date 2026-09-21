"""Metered HTTP Responses transport for Codex; all inference fails closed.

Only the trusted worker holds the real OpenAI key. The local agent gets a
temporary proxy credential. Unsupported inference routes are never forwarded.
"""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .token_budget import TokenBudgetExhausted, natural

COUNT_FIELDS = {"model", "input", "instructions", "tools", "tool_choice", "parallel_tool_calls",
                "previous_response_id", "conversation", "reasoning", "text", "truncation", "personality"}
TRANSPORT_FIELDS = {"stream", "store", "include", "metadata", "prompt_cache_key", "prompt_cache_retention",
                    "max_output_tokens", "service_tier", "safety_identifier", "user", "temperature",
                    "top_p", "top_logprobs", "stream_options", "max_tool_calls", "client_metadata"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "API redirects are disabled", headers, fp)


class BudgetProxy:
    def __init__(self, key, model, budget, *, max_output_tokens=8192, timeout_s=600, transport=None):
        if not key:
            raise ValueError("Set CODEX_API_KEY or OPENAI_API_KEY for token-budgeted evaluation")
        self.key, self.model, self.budget = key, model, budget
        self.output_cap = natural(max_output_tokens, "max_output_tokens", 1)
        self.timeout_s = timeout_s
        self.token = secrets.token_urlsafe(32)
        self.transport = transport or self._open
        self.request_lock = threading.Lock()
        self.closed = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def _open(self, path, payload):
        # No automatic retries, redirects to arbitrary URLs, or client-supplied auth headers.
        request = Request("https://api.openai.com/v1" + path, data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json", "Accept-Encoding": "identity"})
        return build_opener(NoRedirect()).open(request, timeout=self.timeout_s)

    def prepare(self, original):
        self.budget.require_ready()
        if not isinstance(original, dict) or original.get("model") != self.model:
            raise ValueError("Proxy only accepts the configured model")
        unknown = set(original) - COUNT_FIELDS - TRANSPORT_FIELDS
        if unknown:
            raise ValueError(f"Unsupported request fields for token accounting: {sorted(unknown)}")
        payload = copy.deepcopy(original)
        # Server-side tools may grow the input inside a single HTTP request. Only
        # client-executed tools can be covered by count-before-every-request.
        def check_tools(items):
            for tool in items:
                if tool.get("type") == "namespace":
                    check_tools(tool.get("tools", []))
                elif tool.get("type") not in ("function", "custom", "local_shell"):
                    raise ValueError(f"Unmetered hosted tool is disabled: {tool.get('type')}")
        check_tools(payload.get("tools", []))
        if payload.get("conversation"):
            raise ValueError("Mutable server conversations are not supported by strict accounting")
        payload["instructions"] = (payload.get("instructions") or "") + "\n\n" + self.budget.notice()
        payload["store"] = False
        payload["truncation"] = "disabled"
        count_payload = {k: v for k, v in payload.items() if k in COUNT_FIELDS}
        with self.transport("/responses/input_tokens", count_payload) as response:
            input_tokens = json.load(response)["input_tokens"]
        if self.closed.is_set():
            raise RuntimeError("Attempt closed during input counting; no generation was sent")
        cap = min(self.output_cap, natural(payload.get("max_output_tokens", self.output_cap),
                                           "max_output_tokens", 1))
        request, cap = self.budget.reserve(input_tokens, cap)
        payload["max_output_tokens"] = cap
        return request, payload

    def _handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # No credentials or request content in server access logs.

            def fail(self, message, status=400):
                data = json.dumps(dict(error=dict(message=message, type="topogym_budget_error"))).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.fail("Only POST /v1/responses is enabled; WebSockets and other routes are disabled", 404)

            def do_POST(self):
                if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + proxy.token):
                    self.fail("Invalid local proxy credential", 401)
                    return
                if self.path != "/v1/responses":
                    proxy.budget.stop("unsupported_endpoint", f"Unmetered endpoint blocked: {self.path}")
                    self.fail(proxy.budget.reason)
                    return
                if not proxy.request_lock.acquire(blocking=False):
                    self.fail("Only one model request can be in flight", 409)
                    return
                started, request = False, None
                try:
                    if self.headers.get("Content-Encoding", "identity") != "identity":
                        raise ValueError("Disable Codex request compression for token accounting")
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 64 * 1024 * 1024:
                        raise ValueError("Expected a JSON request body of at most 64 MiB")
                    request, payload = proxy.prepare(json.loads(self.rfile.read(length)))
                    if proxy.closed.is_set():
                        raise RuntimeError("Attempt closed before generation")
                    with proxy.transport("/responses", payload) as upstream:
                        streaming = payload.get("stream", False)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
                        self.end_headers()
                        started = True
                        if streaming:
                            final = False
                            event_lines = []
                            for line in upstream:
                                if line.startswith(b"data:"):
                                    event_lines.append(line[5:].strip())
                                if not line.strip() and event_lines:
                                    raw = b"\n".join(event_lines)
                                    event_lines = []
                                    if raw != b"[DONE]":
                                        event = json.loads(raw)
                                        if event.get("type") in ("response.completed", "response.incomplete", "response.failed"):
                                            proxy.budget.complete(request, event["response"].get("usage"))
                                            final = True
                                self.wfile.write(line)
                                self.wfile.flush()
                                if final:
                                    break
                            if not final:
                                raise RuntimeError("Response stream ended without a final usage receipt")
                        else:
                            data = upstream.read()
                            proxy.budget.complete(request, json.loads(data).get("usage"))
                            self.wfile.write(data)
                except Exception as exc:
                    if isinstance(exc, HTTPError):
                        message = f"OpenAI HTTP {exc.code}: {exc.read(8192).decode(errors='replace')}"
                    else:
                        message = f"{type(exc).__name__}: {exc}"
                    message = message.replace(proxy.key, "[REDACTED]").replace(proxy.token, "[REDACTED]")
                    unsettled = request and proxy.budget.calls[request-1]["state"] != "complete"
                    code = "token_budget_exhausted" if isinstance(exc, TokenBudgetExhausted) else (
                        "usage_unknown" if unsettled else "provider_error")
                    proxy.budget.stop(code, message)
                    if not started:
                        try:
                            self.fail(message)
                        except OSError:
                            pass
                finally:
                    self.close_connection = True
                    proxy.request_lock.release()

        return Handler

    def close(self):
        self.closed.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.budget.snapshot()["reserved"]:
            self.budget.stop("usage_unknown", "Attempt ended with an unsettled model request; reservation retained")
