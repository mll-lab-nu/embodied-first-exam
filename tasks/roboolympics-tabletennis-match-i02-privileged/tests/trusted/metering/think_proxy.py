#!/usr/bin/env python3
"""Model-traffic proxy that runs in a task's sim sidecar and meters the agent's thinking.

In interactive mode ("thinking costs sim time") the agent's harness talks to this proxy instead of
the model API: Codex (OpenAI Responses via OpenRouter) or Claude Code (Anthropic Messages, on a Claude
subscription). The proxy
  * holds the real credentials (from its own environment: `OPENROUTER_API_KEY` for OpenRouter,
    `CLAUDE_CODE_OAUTH_TOKEN` for Anthropic); the agent container only has placeholders, so the agent
    cannot bypass the meter;
  * routes by request: Anthropic-style requests (an `anthropic-version` header, or a /v1/messages path)
    go to https://api.anthropic.com with the subscription token as Bearer; /backend-api/* (Codex logged in with a
    ChatGPT subscription, see harbor_agents/codex_chatgpt_think.py) goes to https://chatgpt.com with the sidecar's
    CODEX_ACCESS_TOKEN / CODEX_ACCOUNT_ID; everything else goes to OpenRouter (or Azure, THINK_OPENAI_ROUTE). A seat
    on THINK_OPENAI_ROUTE=chatgpt gets the ChatGPT backend only: any other request is refused (403);
  * follows no upstream redirect: a 30x goes back to the agent, never with the real credentials to another host;
  * forwards everything to OpenRouter unchanged, except the model-turn repair that Gemini needs
    (same rule as harbor_agents/or_proxy.py);
  * reads the `usage` of every completed response (streamed or not) and keeps cumulative counts:
    requests, input, cached input, output and reasoning tokens;
  * publishes the counts atomically to `THINK_USAGE_FILE` (default /data/think_usage.json) and on
    `GET /think/usage`, which the game service reads to turn "tokens since the last observation"
    into simulated time and to check that every decision follows a new model call (see think_clock.py);
  * logs every request to `THINK_CALLS_FILE` (default /data/think_calls.jsonl) for the cheating audit (rules 5.6):
    sequence number, start/end time, the client's address, User-Agent and harness session headers, the route, the
    model, the HTTP status, its usage, and an excerpt of what the model emitted (tool calls, text). Never the
    credentials or the request body;
  * with THINK_CLIENT_HOST set (multi-seat duels), serves only that compose service;
  * forwards only the model endpoints the harnesses use (ALLOWED_PATHS: Messages, Responses, the ChatGPT backend's
    Codex endpoints); any other path is refused (403) and logged as blocked. It locks the seat's model: THINK_MODEL
    (comma-separated names or fnmatch patterns, provider prefixes ignored; per seat RO_SEAT_ENV_THINK_MODEL_<seat>), or
    else the first model the seat used; a request for another model is refused (403). It strips server-side tools
    the provider would run on the agent's behalf (web search / fetch, code execution, remote MCP, file search,
    OpenRouter plugins and the `:online` model suffix): the model reaches nothing outside the game through the meter.

Usage (inside the sidecar):  python3 think_proxy.py [port=18090]
Standard library only.
"""
from __future__ import annotations

import json
import re
import uuid
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("THINK_UPSTREAM", "https://openrouter.ai/api")
ANTHROPIC_UPSTREAM = os.environ.get("THINK_ANTHROPIC_UPSTREAM", "https://api.anthropic.com")
CHATGPT_UPSTREAM = os.environ.get("THINK_CHATGPT_UPSTREAM", "https://chatgpt.com")   # Codex on a ChatGPT subscription
# THINK_CHATGPT_MODEL (per seat: RO_SEAT_ENV_THINK_CHATGPT_MODEL_<seat>, from players.toml `deployment` of a ChatGPT
# subscription player) pins the seat's ChatGPT-backend calls to that model: a request the model lock admitted is sent
# with this model (rec["model_alias"] keeps the name the agent sent). The harness can then use its own slug for the
# model family (Codex 0.158.0 has metadata for "gpt-6-sol", none for "gpt-6.1-sol") while the backend serves the pinned
# model ("gpt-6.1-sol"). Empty: no pin.
CHATGPT_MODEL = os.environ.get("THINK_CHATGPT_MODEL", "").strip()


def chatgpt_pin(body: bytes, rec: dict) -> bytes:
    """The ChatGPT backend's pinned model (THINK_CHATGPT_MODEL) in place of the model the agent named."""
    try:
        d = json.loads(body)
    except ValueError:
        return body
    if not isinstance(d, dict) or not isinstance(d.get("model"), str) or d["model"] == CHATGPT_MODEL:
        return body
    rec["model_alias"] = d["model"]
    d["model"] = CHATGPT_MODEL
    return json.dumps(d).encode()
# OpenAI-style requests (Codex) go to OpenRouter unless THINK_OPENAI_ROUTE=azure: then to an Azure AI Foundry resource
# (AZURE_AI_ENDPOINT, e.g. https://<res>.services.ai.azure.com/models, key AZURE_AI_API_KEY), /v1/... -> /openai/v1/...,
# the model's provider prefix dropped ("openai/gpt-6-astra" -> deployment "gpt-6-astra").
# THINK_OPENAI_ROUTE=azure_sol is a second Azure resource with the same wire (an Azure OpenAI resource, e.g.
# https://<res>.openai.azure.com/): its own AZURE_SOL_ENDPOINT, AZURE_SOL_API_KEY and AZURE_SOL_DEPLOYMENTS. A seat's
# route is set per seat (THINK_OPENAI_ROUTE_<seat>, core/launch.py), and only that seat's proxy gets its variables.
# On azure_sol the deployments are pinned: a request for a model that is not one of AZURE_SOL_DEPLOYMENTS goes to them
# anyway (rec["model_alias"] keeps the name the agent sent). The agent can then use its harness's own name for the
# model family (Codex knows "gpt-6-sol" and has its metadata) while the resource serves its deployment ("gpt-6.1-sol").
# THINK_OPENAI_ROUTE=chatgpt: the seat plays on a ChatGPT subscription only. Its proxy forwards the ChatGPT backend
# (/backend-api/*) and refuses every other request (OpenRouter / Azure / Anthropic paths) before any credential is
# touched, so a program in that seat cannot reach another provider with a task-wide key (core/launch.py also drops those
# keys from the seat's proxy).
AZURE_ROUTES = {"azure": ("AZURE_AI_ENDPOINT", "AZURE_AI_API_KEY", "AZURE_DEPLOYMENTS"),
                "azure_sol": ("AZURE_SOL_ENDPOINT", "AZURE_SOL_API_KEY", "AZURE_SOL_DEPLOYMENTS")}
ROUTE = os.environ.get("THINK_OPENAI_ROUTE", "openrouter").strip().lower()
AZURE = ROUTE in AZURE_ROUTES
AZURE_ROUTE = ROUTE if AZURE else "azure"
AZURE_ENDPOINT_VAR, AZURE_KEY_VAR, AZURE_POOL_VAR = AZURE_ROUTES[AZURE_ROUTE]
AZURE_PINNED = AZURE_ROUTE == "azure_sol"
CHATGPT_ONLY = ROUTE == "chatgpt"
AZURE_BASE = os.environ.get(AZURE_ENDPOINT_VAR, "").strip().rstrip("/").removesuffix("/models")
USAGE_FILE = os.environ.get("THINK_USAGE_FILE", "/data/think_usage.json")
CALLS_FILE = os.environ.get("THINK_CALLS_FILE") or (USAGE_FILE.replace("think_usage", "think_calls").rsplit(".json", 1)[0] + ".jsonl"
                                                   if "think_usage" in os.path.basename(USAGE_FILE)
                                                   else os.path.join(os.path.dirname(USAGE_FILE) or ".", "think_calls.jsonl"))
SESSION_HEADERS = ("x-claude-code-session-id", "session_id", "conversation_id", "originator", "x-app", "openai-beta")
EXCERPT_MAX = 2000
ACT_RE = re.compile(os.environ.get("THINK_ACT_REGEX", r"\bgame\s+act\b"))
CONTINUE_TEXT = "Continue from where you left off."
MODEL_ITEM_TYPES = {"reasoning", "function_call", "custom_tool_call", "web_search_call", "local_shell_call",
                    "computer_call", "mcp_call", "image_generation_call", "code_interpreter_call", "item_reference"}
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-connection",
              "content-length", "host", "accept-encoding", "authorization", "x-api-key", "api-key", "chatgpt-account-id"}
# Azure deployment failover (program play tasks): AZURE_DEPLOYMENTS lists replicas of one model (e.g.
# "gpt-6-astra,gpt-6-astra-2,gpt-6-astra-3"; empty = no failover). Each deployment has its own per-minute token
# limit, and Azure may report an exceeded limit inside an HTTP 200 stream. When a deployment answers 429/503, or its
# stream opens with a rate-limit failure, the request is sent to the next deployment before any byte reaches the agent;
# the proxy then stays on the deployment that worked. Switches are recorded (rec["azure_failovers"],
# USAGE["azure_failovers"]); they are not model failures and do not count as rate_limit_retries.
AZURE_POOL = [d.strip() for d in os.environ.get(AZURE_POOL_VAR, "").split(",") if d.strip()]
AZURE_CURRENT = [0]
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Follow no redirect: a 30x goes back to the client as it is, so the credentials this proxy adds (Authorization,
    api-key, chatgpt-account-id) never travel to a host the redirect names."""
    def redirect_request(self, *a, **kw):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)            # replaces the default (following) redirect handler
AZURE_RATE_WORDS = ("rate limit", "rate_limit", "too_many_requests", "server_is_overloaded", '"429"')


def azure_peek(resp, limit=1 << 20):
    '''Read whole SSE events until one that is not response.created / response.in_progress. Returns the bytes read
    and, if that event is a rate-limit / overload failure, a short reason (else None).'''
    buf, seen = b"", 0
    read = getattr(resp, "read1", resp.read)
    while len(buf) < limit:
        chunk = read(65536)
        if not chunk:
            return buf, None
        buf += chunk
        events = buf.replace(b"\r\n", b"\n").split(b"\n\n")[:-1]
        for ev in events[seen:]:
            seen += 1
            payload = b"\n".join(l[5:].strip() for l in ev.split(b"\n") if l.startswith(b"data:"))
            try:
                d = json.loads(payload) if payload and payload != b"[DONE]" else {}
            except ValueError:
                d = {}
            t = d.get("type", "") if isinstance(d, dict) else ""
            if t in ("response.created", "response.in_progress", ""):
                continue
            text = json.dumps(d).lower()
            if t in ("error", "response.failed") and any(k in text for k in AZURE_RATE_WORDS):
                err = (d.get("response") or {}).get("error") or d.get("error") or {}
                return buf, f"{t} ({(err.get('code') if isinstance(err, dict) else '') or 'rate limit'})"
            return buf, None
    return buf, None


class PrefixedResponse:
    '''A response whose first bytes were already read by azure_peek.'''
    def __init__(self, resp, head):
        self.resp, self.head = resp, head
        self.status, self.headers = resp.status, resp.headers

    def read1(self, n=-1):
        if self.head:
            out, self.head = self.head, b""
            return out
        return getattr(self.resp, "read1", self.resp.read)(n)

    read = read1

    def close(self):
        self.resp.close()


RATE_LIMIT_WAITS_S = tuple(float(x) for x in os.environ.get("THINK_RETRY_WAITS_S", "").split(",") if x.strip())

LOCK = threading.Lock()
USAGE = {"requests": 0, "responses_with_usage": 0, "input_tokens": 0, "cached_input_tokens": 0,
         "output_tokens": 0, "reasoning_tokens": 0, "updated_at": 0.0,
         "model_calls_completed": 0, "in_flight": 0, "last_completed_at": 0.0,
         "epoch": uuid.uuid4().hex, "failed_model_calls": 0,
         "rate_limit_retries": 0, "last_response_seq": None, "blocked_requests": 0,
         "act_calls_completed": 0, "last_act_call_at": 0.0, "last_act_response_seq": None, "last_act_started_at": 0.0}


def publish() -> None:
    tmp = USAGE_FILE + ".tmp"
    os.makedirs(os.path.dirname(USAGE_FILE) or ".", exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(USAGE, f)
    os.replace(tmp, USAGE_FILE)


def azure_model(body: bytes) -> bytes:
    """Azure deployments are named without the provider prefix the agent uses for OpenRouter."""
    try:
        d = json.loads(body)
    except ValueError:
        return body
    if isinstance(d, dict) and isinstance(d.get("model"), str) and "/" in d["model"]:
        d["model"] = d["model"].rsplit("/", 1)[1]
        return json.dumps(d).encode()
    return body


def is_model_call(method: str, path: str) -> bool:
    """A model turn: Anthropic Messages (not count_tokens), OpenAI Responses / Chat Completions (OpenRouter or the
    ChatGPT backend). Model listings, token counting and telemetry are not."""
    if method != "POST":
        return False
    p = path.split("?")[0]
    if "count_tokens" in p:
        return False
    return p.endswith(("/v1/messages", "/responses", "/chat/completions"))


# Anti-cheat (audit 2026-10-08, G4): the proxy is no open forwarder with the real credentials.
ALLOWED_PATHS = {("POST", "/v1/messages"), ("POST", "/v1/messages/count_tokens"), ("POST", "/v1/responses"),
                 ("POST", "/v1/chat/completions"), ("POST", "/openai/v1/responses"),
                 ("POST", "/backend-api/codex/responses"), ("GET", "/backend-api/codex/models"), ("GET", "/v1/models"),
                 ("POST", "/v1/responses/compact"), ("POST", "/backend-api/codex/responses/compact")}   # Codex compaction
SERVER_TOOL_PREFIXES = ("web_search", "web_fetch", "code_execution", "bash_code_execution",
                        "text_editor_code_execution", "code_interpreter", "file_search", "mcp")   # tool "type"s
STRIP_KEYS = ("mcp_servers", "plugins", "web_search_options", "container", "tool_resources")
MODEL_LOCK = [m.strip() for m in os.environ.get("THINK_MODEL", "").split(",") if m.strip()]
FIRST_MODEL: list = []                                       # without THINK_MODEL: the first model this seat used


def path_allowed(method: str, path: str) -> bool:
    return (method, path.split("?")[0].rstrip("/") or "/") in ALLOWED_PATHS


def bare_model(name) -> str:
    """'openrouter/openai/gpt-x:online' -> 'gpt-x' (provider prefixes and OpenRouter variants dropped)."""
    return str(name or "").rsplit("/", 1)[-1].split(":", 1)[0].strip().lower()


def model_allowed(name) -> bool:
    import fnmatch
    m = bare_model(name)
    if not m:
        return True                                          # no model named (listings): nothing to lock
    if MODEL_LOCK:
        return any(fnmatch.fnmatchcase(m, bare_model(p)) for p in MODEL_LOCK)
    with LOCK:
        if not FIRST_MODEL:
            FIRST_MODEL.append(m)
        return m == FIRST_MODEL[0]


def strip_server_tools(payload: dict) -> list:
    """Remove the provider-run tools and options from a request (in place); returns what was removed."""
    gone = []
    tools = payload.get("tools")
    if isinstance(tools, list):
        keep = []
        for t in tools:
            kind = str(t.get("type", "")) if isinstance(t, dict) else ""
            if kind.lower().startswith(SERVER_TOOL_PREFIXES):       # client tools (function, custom) stay
                gone.append(kind)
            else:
                keep.append(t)
        if len(keep) != len(tools):
            payload["tools"] = keep
            if not keep:
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
    for k in STRIP_KEYS:
        if k in payload:
            gone.append(k)
            payload.pop(k)
    model = payload.get("model")
    if isinstance(model, str) and ":online" in model:
        payload["model"] = model.replace(":online", "")
        gone.append(":online")
    if isinstance(payload.get("models"), list):              # OpenRouter fallback models: another model
        gone.append("models")
        payload.pop("models")
    return gone


def screen(method: str, path: str, body: bytes | None, rec: dict) -> tuple[int, str, bytes | None]:
    """Before anything is forwarded: (0, "", body to send) or (http status, reason, None) for a refusal."""
    if not path_allowed(method, path):
        return 403, "path not allowed (only the model endpoints of the harnesses)", None
    if not body:
        return 0, "", body
    try:
        payload = json.loads(body)
    except ValueError:
        return 400, "request body is not JSON", None
    if not isinstance(payload, dict):
        return 400, "request body is not a JSON object", None
    if not model_allowed(payload.get("model")):
        return 403, "model not allowed for this seat", None
    gone = strip_server_tools(payload)
    if gone:
        rec["stripped"] = gone
        return 0, "", json.dumps(payload).encode()
    return 0, "", body


def log_call(rec: dict) -> None:
    line = json.dumps(rec, default=str)
    with LOCK:
        with open(CALLS_FILE, "a") as f:
            f.write(line + "\n")


def _allowed_client(addr: str) -> bool:
    """Multi-seat duels: THINK_CLIENT_HOST names the only compose service allowed to use this proxy, so one seat
    cannot think on (or hide its thinking behind) the other seat's meter. Unset: anyone (single-player tasks)."""
    host = os.environ.get("THINK_CLIENT_HOST")
    if not host:
        return True
    try:
        import socket
        return addr in {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except OSError:
        return False


class Excerpt:
    """What the model emitted in one response, from its stream or JSON body: tool calls and text, truncated."""
    def __init__(self):
        self.parts: list[str] = []
        self.n = 0

    def add(self, s) -> None:
        if not s or self.n >= EXCERPT_MAX:
            return
        s = str(s)[: EXCERPT_MAX - self.n]
        self.parts.append(s); self.n += len(s)

    def feed_event(self, ev: dict) -> None:
        t = ev.get("type", "")
        if t == "content_block_start":                                   # Anthropic
            cb = ev.get("content_block") or {}
            if cb.get("type") in ("tool_use", "server_tool_use"):
                self.add(f"[tool {cb.get('name')}] ")
        elif t == "content_block_delta":
            d = ev.get("delta") or {}
            self.add(d.get("partial_json") or d.get("text"))
        elif t == "response.output_item.done":                            # OpenAI Responses
            it = ev.get("item") or {}
            if it.get("type") in ("function_call", "custom_tool_call"):
                self.add(f"[tool {it.get('name')}] {it.get('arguments') or it.get('input') or ''} ")
            elif it.get("type") == "local_shell_call":
                self.add(f"[shell] {json.dumps(it.get('action'))} ")
        elif t == "response.output_text.delta":
            self.add(ev.get("delta"))

    def feed_body(self, obj: dict) -> None:
        for cb in obj.get("content") or []:                              # Anthropic, non-streamed
            if cb.get("type") == "tool_use":
                self.add(f"[tool {cb.get('name')}] {json.dumps(cb.get('input'))} ")
            elif cb.get("type") == "text":
                self.add(cb.get("text"))
        for it in obj.get("output") or []:                               # Responses, non-streamed
            self.feed_event({"type": "response.output_item.done", "item": it})

    def text(self) -> str:
        return "".join(self.parts)


def account(usage: dict) -> None:
    """Add one response's usage (Responses API or Chat Completions shape)."""
    if not isinstance(usage, dict):
        return 0
    inp = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    out = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    det_in = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    det_out = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    cached = int(det_in.get("cached_tokens", 0) or 0)
    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:   # Anthropic shape
        cached = int(usage.get("cache_read_input_tokens", 0) or 0)
        inp += cached + int(usage.get("cache_creation_input_tokens", 0) or 0)
    with LOCK:
        USAGE["responses_with_usage"] += 1
        USAGE["input_tokens"] += inp
        USAGE["cached_input_tokens"] += cached
        USAGE["output_tokens"] += out
        USAGE["reasoning_tokens"] += int(det_out.get("reasoning_tokens", 0) or 0)
        USAGE["updated_at"] = time.time()
        publish()
    return out


class AnthropicStream:
    """Collects one Messages stream's usage: input from message_start, final output from message_delta."""
    def __init__(self):
        self.usage: dict = {}

    def feed(self, line: bytes, excerpt: "Excerpt | None" = None) -> None:
        if not line.startswith(b"data:"):
            return
        try:
            ev = json.loads(line[5:].strip() or b"{}")
        except ValueError:
            return
        if excerpt is not None:
            excerpt.feed_event(ev)
        if ev.get("type") == "message_start":
            self.usage.update((ev.get("message") or {}).get("usage") or {})
        elif ev.get("type") == "message_delta" and ev.get("usage"):
            self.usage.update(ev["usage"])


def is_anthropic(path: str, headers) -> bool:
    """Codex (OpenRouter) only uses /v1/responses (and /v1/models); Claude Code uses /v1/messages*, /api/*
    and always sends anthropic-version."""
    if path.startswith("/v1/responses") or path.startswith("/v1/chat"):
        return False
    return bool(headers.get("anthropic-version")) or path.startswith(("/v1/messages", "/v1/complete", "/api/"))


def usage_from_sse_line(line: bytes) -> dict | None:
    if not line.startswith(b"data:"):
        return None
    data = line[5:].strip()
    if not data or data == b"[DONE]":
        return None
    try:
        ev = json.loads(data)
    except ValueError:
        return None
    if ev.get("type") in ("response.completed", "response.done", "response.incomplete"):
        return (ev.get("response") or {}).get("usage")
    if "usage" in ev and ev.get("object", "").startswith("chat.completion"):
        return ev.get("usage")
    return None


def repair(body: bytes, path: str) -> bytes:
    if "/responses" not in path:
        return body
    try:
        payload = json.loads(body)
    except ValueError:
        return body
    items = payload.get("input")
    if isinstance(items, list) and items and isinstance(items[-1], dict) and (
            items[-1].get("role") == "assistant" or items[-1].get("type") in MODEL_ITEM_TYPES):
        items.append({"type": "message", "role": "user", "content": [{"type": "input_text", "text": CONTINUE_TEXT}]})
        return json.dumps(payload).encode()
    return body


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("think_proxy: %s\n" % (fmt % args))

    def _json(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if not _allowed_client(self.client_address[0]):
            self.send_error(403, "not your seat's proxy"); return
        if self.path.rstrip("/") == "/think/usage":
            with LOCK:
                return self._json(200, dict(USAGE))
        return self._forward(None)

    def do_POST(self):
        if not _allowed_client(self.client_address[0]):
            self.send_error(403, "not your seat's proxy"); return
        n = int(self.headers.get("Content-Length") or 0)
        return self._forward(self.rfile.read(n) if n else b"")

    def _forward(self, body: bytes | None) -> None:
        pre = {}
        code, why, body = screen(self.command, self.path, body, pre)
        if not code and CHATGPT_ONLY and not self.path.startswith("/backend-api/"):
            code, why = 403, "route chatgpt: only the ChatGPT backend (/backend-api/*) is forwarded for this seat"
        if code:                                               # refused before any credential is touched
            rec = {"t0": round(time.time(), 3), "client": self.client_address[0], "method": self.command,
                   "path": self.path.split("?")[0][:200], "user_agent": self.headers.get("User-Agent", ""),
                   "model_call": False, "status": code, "blocked": why, "t1": round(time.time(), 3)}
            with LOCK:
                USAGE["blocked_requests"] = USAGE.get("blocked_requests", 0) + 1
                rec["epoch"] = USAGE["epoch"]
                publish()
            log_call(rec)
            return self._json(code, {"error": {"type": "think_proxy_refused", "message": f"think_proxy: {why}"}})
        chatgpt = self.path.startswith("/backend-api/")          # Codex logged in with a ChatGPT subscription
        anthropic = not chatgpt and is_anthropic(self.path, self.headers)
        azure = AZURE and not chatgpt and not anthropic
        name = "CODEX_ACCESS_TOKEN" if chatgpt else ("CLAUDE_CODE_OAUTH_TOKEN" if anthropic else
                                                      (AZURE_KEY_VAR if azure else "OPENROUTER_API_KEY"))
        key = os.environ.get(name, "")
        if body and azure:
            body = azure_model(body)
        elif body and chatgpt and CHATGPT_MODEL:               # after the model lock admitted the agent's name
            body = chatgpt_pin(body, pre)
        elif body and not anthropic and not chatgpt:
            body = repair(body, self.path)
        model_call = is_model_call(self.command, self.path)
        rec = {"t0": round(time.time(), 3), "client": self.client_address[0], "method": self.command,
               "path": self.path.split("?")[0], "route": "chatgpt" if chatgpt else ("anthropic" if anthropic else (AZURE_ROUTE if azure else "openrouter")),
               "user_agent": self.headers.get("User-Agent", ""), "model_call": model_call,
               "session": {h: self.headers.get(h) for h in SESSION_HEADERS if self.headers.get(h)}, **pre}
        try:
            rec["model"] = (json.loads(body) or {}).get("model") if body else None
        except (ValueError, AttributeError):
            rec["model"] = None
        with LOCK:
            USAGE["requests"] += 1
            rec["seq"] = USAGE["requests"]
            rec["epoch"] = USAGE["epoch"]
            if model_call:
                USAGE["in_flight"] += 1
            publish()  # publish in-flight and request count before the carrying response can trigger a tool
        try:
            if not key or (azure and not AZURE_BASE):
                rec["status"] = 500
                rec["error"] = "missing_upstream_credentials"
                return self._json(500, {"error": {"message": f"think_proxy: {name} (and {AZURE_ENDPOINT_VAR}) not set in the sidecar"}})
            self._forward_upstream(body, chatgpt, anthropic, key, rec, azure)
        except Exception as exc:
            rec["error"] = type(exc).__name__
            rec["completed"] = False
            self.close_connection = True
        finally:
            with LOCK:
                if model_call:
                    USAGE["in_flight"] -= 1
                    if rec.get("status") == 200 and rec.get("completed"):
                        USAGE["model_calls_completed"] += 1
                        USAGE["last_completed_at"] = time.time()
                        USAGE["last_response_seq"] = rec["seq"]
                        if rec.get("has_act"):
                            USAGE["act_calls_completed"] += 1
                            USAGE["last_act_call_at"] = time.time()
                            USAGE["last_act_response_seq"] = rec["seq"]
                            USAGE["last_act_started_at"] = rec["t0"]
                    else:
                        USAGE["failed_model_calls"] += 1
                    publish()
            rec["t1"] = round(time.time(), 6)
            rec["epoch"] = USAGE["epoch"]
            log_call(rec)

    def _forward_upstream(self, body, chatgpt: bool, anthropic: bool, key: str, rec: dict, azure: bool = False) -> None:
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        if azure:                                              # Azure AI Foundry: api-key header, no bearer
            headers["api-key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"      # the agent's placeholder credential is dropped above
        headers["Accept-Encoding"] = "identity"
        if anthropic:                                          # subscription (OAuth) auth needs its beta flag
            betas = [b.strip() for b in headers.pop("anthropic-beta", headers.pop("Anthropic-Beta", "")).split(",") if b.strip()]
            if "oauth-2025-04-20" not in betas:
                betas.append("oauth-2025-04-20")
            headers["anthropic-beta"] = ",".join(betas)
        if chatgpt:                                            # the subscription's account, not the agent's placeholder
            headers["chatgpt-account-id"] = os.environ.get("CODEX_ACCOUNT_ID", "")
        base = CHATGPT_UPSTREAM if chatgpt else (ANTHROPIC_UPSTREAM if anthropic else UPSTREAM)
        url = base.rstrip("/") + self.path                     # /v1/responses -> OpenRouter, /v1/messages -> Anthropic
        if azure:                                              # /v1/responses -> <resource>/openai/v1/responses
            url = AZURE_BASE + "/openai" + (self.path if self.path.startswith("/v1") else "/v1" + self.path)
        req = urllib.request.Request(url, data=body, method=self.command, headers=headers)
        resp = None
        if azure and AZURE_POOL and self.command == "POST" and body:
            try:
                resp = self._azure_failover(url, body, headers, rec)
            except Exception as exc:  # noqa: BLE001
                rec["status"] = 502; rec["error"] = repr(exc)[:200]
                return self._json(502, {"error": {"message": f"think_proxy upstream failure: {exc!r}"}})
        try:
            for attempt in (range(len(RATE_LIMIT_WAITS_S) + 1) if resp is None else ()):
                try:
                    resp = OPENER.open(req, timeout=600); break
                except urllib.error.HTTPError as err:
                    resp = err
                    if err.code != 429 or attempt >= len(RATE_LIMIT_WAITS_S):
                        break
                    with LOCK:
                        USAGE["rate_limit_retries"] += 1
                        publish()
                    rec.setdefault("retries", []).append({"status": 429, "at": time.time(),
                                                           "wait_s": RATE_LIMIT_WAITS_S[attempt]})
                    err.close()
                    time.sleep(RATE_LIMIT_WAITS_S[attempt])
        except Exception as exc:  # noqa: BLE001
            rec["status"] = 502; rec["error"] = repr(exc)[:200]
            return self._json(502, {"error": {"message": f"think_proxy upstream failure: {exc!r}"}})
        rec["status"] = resp.status
        if chatgpt:                                            # subscription usage (x-codex-primary-used-percent, ...)
            limits = {k.lower(): v for k, v in resp.headers.items() if k.lower().startswith("x-codex-")}
            if limits:
                rec["codex_limits"] = limits
                with LOCK:
                    USAGE["codex_limits"] = limits
                    publish()
        self.send_response(resp.status)
        ctype = resp.headers.get("Content-Type", "")
        for k, v in resp.headers.items():
            if k.lower() not in HOP_BY_HOP:
                self.send_header(k, v)
        self.send_header("Connection", "close"); self.end_headers()
        audit = ResponseAudit(self.path, anthropic)
        streamed = "event-stream" in ctype
        whole = bytearray()
        read = getattr(resp, "read1", resp.read)
        rec["completed"] = False
        try:
            while True:
                chunk = read(4096)  # never wait for a full 4 KB while SSE bytes are already available
                if not chunk:
                    break
                rec.setdefault("upstream_first_byte_at", time.time())
                self.wfile.write(chunk); self.wfile.flush()
                rec.setdefault("downstream_first_byte_at", time.time())
                if streamed:
                    audit.feed(chunk)
                else:
                    whole.extend(chunk)
                    if whole.lstrip().startswith((b"event:", b"data:")):
                        streamed = True
                        audit.feed(bytes(whole))
                        whole.clear()
                if audit.terminal:
                    rec["upstream_terminal_at"] = time.time()
                    break
            if streamed:
                audit.finish()
            else:
                try:
                    audit.body(json.loads(whole))
                except (ValueError, TypeError):
                    audit.failed = True
            rec["completed"] = bool(resp.status == 200 and audit.success and not audit.failed)
        finally:
            resp.close()
            rec["output_tokens"] = account(audit.usage) if audit.usage else 0
            rec["excerpt"] = audit.excerpt.text()
            rec["response_id"] = audit.response_id
            rec["tool_calls"] = audit.tools
            rec["has_act"] = bool(rec.get("completed") and audit.has_act())
            rec["stream_error"] = audit.failed or not audit.success
            self.close_connection = True


    def _azure_failover(self, url, body, headers, rec):
        '''Send to the current deployment; on 429/503 or an in-stream rate-limit failure, try the next one.'''
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return None
        if data.get("model") not in AZURE_POOL:
            if not AZURE_PINNED:
                return None                                # not a pooled model: the ordinary path
            rec["model_alias"] = data.get("model")         # pinned route: served by the pool's deployment
        n = len(AZURE_POOL)
        start = AZURE_CURRENT[0]
        resp = None
        for i in range(n):
            idx = (start + i) % n
            data["model"] = AZURE_POOL[idx]
            payload = json.dumps(data).encode()
            h = dict(headers); h["Content-Length"] = str(len(payload))
            req = urllib.request.Request(url, data=payload, method="POST", headers=h)
            last = i == n - 1
            try:
                resp = OPENER.open(req, timeout=600)
            except urllib.error.HTTPError as err:
                resp = err
                if err.code in (429, 503) and not last:
                    err.close()
                    self._azure_switch(rec, idx, f"HTTP {err.code}")
                    continue
                break
            if data.get("stream") and not last:
                head, failed = azure_peek(resp)
                if failed:
                    resp.close()
                    self._azure_switch(rec, idx, failed)
                    continue
                resp = PrefixedResponse(resp, head)
            break
        AZURE_CURRENT[0] = AZURE_POOL.index(data["model"])
        rec["azure_deployment"] = data["model"]
        return resp

    def _azure_switch(self, rec, idx, reason):
        rec.setdefault("azure_failovers", []).append({"from": AZURE_POOL[idx], "reason": reason, "at": time.time()})
        with LOCK:
            USAGE["azure_failovers"] = USAGE.get("azure_failovers", 0) + 1
            publish()


class ResponseAudit:
    """Parse SSE boundaries independently of network chunks; count only a successful terminal event."""
    def __init__(self, path, anthropic=False):
        self.path, self.anthropic = path, anthropic
        self.buf = b""
        self.data = []
        self.success = self.failed = self.terminal = False
        self.usage = {}
        self.response_id = None
        self.excerpt = Excerpt()
        self.tools = []
        self.chat_choices = {}
        self.chat_tools = {}
        self.anthropic_tools = {}
        self.anthropic_stop = None

    def has_act(self):
        # Intent is read only from emitted tool arguments, never ordinary assistant text.
        # This is an operational gate, not authentication of which harness made the request.
        return self.success and not self.failed and any(
            ACT_RE.search(json.dumps(tool.get("arguments") or tool.get("input") or tool.get("action")
                                     or (tool.get("function") or {}).get("arguments") or "",
                                     ensure_ascii=False)) for tool in self.tools)

    def body(self, obj):
        if not isinstance(obj, dict):
            self.failed = True
            return
        self.response_id = obj.get("id", self.response_id)
        self.usage.update(obj.get("usage") or {})
        self.excerpt.feed_body(obj)
        if "output" in obj:
            self.tools = [it for it in obj["output"] if it.get("type") in ("function_call", "custom_tool_call", "local_shell_call")]
        self.tools += [it for it in obj.get("content", []) if it.get("type") == "tool_use"]
        self.tools += [it for ch in obj.get("choices", []) for it in (ch.get("message") or {}).get("tool_calls", [])]
        self.tools += [{"function": ch["message"]["function_call"]} for ch in obj.get("choices", [])
                       if (ch.get("message") or {}).get("function_call")]
        if self.anthropic:
            self.success = obj.get("stop_reason") in ("end_turn", "tool_use", "stop_sequence") and obj.get("type") == "message"
        elif "/chat/completions" in self.path:
            self.success = bool(obj.get("choices")) and all(c.get("finish_reason") in ("stop", "tool_calls", "function_call") for c in obj["choices"])
        else:
            self.success = obj.get("status") == "completed"
        self.failed |= bool(obj.get("error"))
        self.terminal = True

    def event(self, data):
        if data == b"[DONE]":
            self.terminal = True
            self.success |= ("/chat/completions" in self.path and bool(self.chat_choices)
                             and all(self.chat_choices.values()))
            self.tools += list(self.chat_tools.values())
            return
        try:
            ev = json.loads(data)
        except ValueError:
            self.failed = True
            return
        if not isinstance(ev, dict):
            self.failed = True
            return
        t = ev.get("type", "")
        self.excerpt.feed_event(ev)
        if t == "message_start":
            message = ev.get("message") or {}
            self.response_id = message.get("id")
            self.usage.update(message.get("usage") or {})
        elif t == "message_delta":
            self.usage.update(ev.get("usage") or {})
            self.anthropic_stop = (ev.get("delta") or {}).get("stop_reason", self.anthropic_stop)
        elif t == "content_block_start":
            cb = ev.get("content_block") or {}
            if cb.get("type") == "tool_use":
                self.anthropic_tools[ev.get("index", 0)] = dict(cb)
        elif t == "content_block_delta":
            tool = self.anthropic_tools.get(ev.get("index", 0))
            delta = ev.get("delta") or {}
            if tool is not None and delta.get("type") == "input_json_delta":
                tool["_json"] = tool.get("_json", "") + delta.get("partial_json", "")
        elif t == "message_stop":
            self.terminal = True
            self.success = self.anthropic_stop in ("end_turn", "tool_use", "stop_sequence")
            for tool in self.anthropic_tools.values():
                if "_json" in tool:
                    try:
                        tool["input"] = json.loads(tool.pop("_json"))
                    except ValueError:
                        self.failed = True
                self.tools.append(tool)
        elif t in ("response.completed", "response.done"):
            response = ev.get("response") or {}
            self.body(response)
        elif t in ("error", "response.failed", "response.incomplete") or ev.get("error"):
            self.failed = self.terminal = True
            self.usage.update((ev.get("response") or {}).get("usage") or {})
        elif t == "response.output_item.done":
            it = ev.get("item") or {}
            if it.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                self.tools.append(it)
        if ev.get("object", "").startswith("chat.completion"):
            self.response_id = ev.get("id", self.response_id)
            self.usage.update(ev.get("usage") or {})
            for choice in ev.get("choices", []):
                ci = choice.get("index", 0)
                self.chat_choices.setdefault(ci, False)
                reason = choice.get("finish_reason")
                if reason is not None:
                    self.chat_choices[ci] = reason in ("stop", "tool_calls", "function_call")
                    self.failed |= not self.chat_choices[ci]
                delta = choice.get("delta") or {}
                self.excerpt.add(delta.get("content"))
                calls = delta.get("tool_calls") or []
                if delta.get("function_call"):
                    calls = calls + [{"index": 0, "function": delta["function_call"]}]
                for fragment in calls:
                    tool = self.chat_tools.setdefault((ci, fragment.get("index", 0)),
                                                       {"type": "function", "function": {"name": "", "arguments": ""}})
                    if fragment.get("id"):
                        tool["id"] = fragment["id"]
                    for field in ("name", "arguments"):
                        tool["function"][field] += (fragment.get("function") or {}).get(field, "")
                    self.excerpt.add(json.dumps(fragment))

    def feed(self, chunk):
        self.buf += chunk
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            self.line(line.rstrip(b"\r"))

    def line(self, line):
        if not line:
            if self.data:
                self.event(b"\n".join(self.data))
                self.data = []
        elif line.startswith(b"data:"):
            self.data.append(line[5:].lstrip(b" "))

    def finish(self):
        if self.buf:
            self.line(self.buf.rstrip(b"\r"))
            self.buf = b""
        self.line(b"")



def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18090
    publish()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    sys.stderr.write(f"think_proxy: listening on :{port} -> {UPSTREAM}; usage -> {USAGE_FILE}\n")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
