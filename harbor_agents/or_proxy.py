#!/usr/bin/env python3
"""Local pass-through proxy between Codex and OpenRouter that repairs requests Gemini rejects.

Codex speaks the OpenAI Responses API. When a stream drops and Codex retries, it re-sends the whole
conversation, which then ends with the assistant's partial turn. Google's Gemini endpoint (via OpenRouter)
rejects such a body with HTTP 400 "Requests ending with a model turn are not supported." and Codex gives up.
This proxy sits on localhost inside the agent container; `POST .../responses` bodies whose `input` ends with a
model turn (assistant message, reasoning item or a function call with no output) get a short user message
appended before being forwarded. Everything else, including streaming (SSE) responses, is passed through as is.

Usage (inside the container):  python3 or_proxy.py <port> [<upstream base, default https://openrouter.ai/api>]
Codex is pointed at http://127.0.0.1:<port>/v1 via model_providers.openrouter.base_url. Standard library only.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://openrouter.ai/api"
CONTINUE_TEXT = "Continue from where you left off."
RATE_LIMIT_WAITS_S = (30, 60, 120, 240)          # ~7.5 min of patience per request on HTTP 429
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-connection",
              "content-length", "host", "accept-encoding"}


MODEL_ITEM_TYPES = {"reasoning", "function_call", "custom_tool_call", "web_search_call", "local_shell_call",
                    "computer_call", "mcp_call", "image_generation_call", "code_interpreter_call", "item_reference"}
DUMP_DIR = "/logs/agent"


def is_model_turn(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("role") == "assistant":
        return True
    return item.get("type") in MODEL_ITEM_TYPES


def describe(body: bytes) -> str:
    """One line about a request body: path-independent shape summary for the log."""
    try:
        payload = json.loads(body)
    except ValueError:
        return f"non-json body ({len(body)} bytes)"
    items = payload.get("input")
    if isinstance(items, list):
        last = items[-1] if items else None
        tail = f"{last.get('type')}/{last.get('role')}" if isinstance(last, dict) else repr(last)[:40]
        return f"input[{len(items)}] last={tail} stream={payload.get('stream')} prev={bool(payload.get('previous_response_id'))}"
    return f"keys={sorted(payload)[:8]}"


def repair(body: bytes, path: str) -> tuple[bytes, bool]:
    if "/responses" not in path:
        return body, False
    try:
        payload = json.loads(body)
    except ValueError:
        return body, False
    items = payload.get("input")
    if not (isinstance(items, list) and items and is_model_turn(items[-1])):
        return body, False
    items.append({"type": "message", "role": "user",
                  "content": [{"type": "input_text", "text": CONTINUE_TEXT}]})
    return json.dumps(payload).encode("utf-8"), True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = UPSTREAM

    def log_message(self, fmt, *args):  # quieter default log
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _forward(self, body: bytes | None) -> None:
        original = body
        body, fixed = repair(body or b"", self.path) if body else (body, False)
        if body:
            sys.stderr.write(f"or_proxy: {self.command} {self.path} {describe(body)}{' [REPAIRED]' if fixed else ''}\n")
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Accept-Encoding"] = "identity"
        req = urllib.request.Request(self.upstream + self.path, data=body, method=self.command, headers=headers)
        try:
            resp = None
            for attempt in range(len(RATE_LIMIT_WAITS_S) + 1):
                try:
                    resp = urllib.request.urlopen(req, timeout=600)
                    break
                except urllib.error.HTTPError as err:
                    resp = err
                    # Upstream rate limits (OpenRouter's shared Gemini capacity) are transient; Codex's own
                    # retries are seconds apart and give up, so wait here before handing the 429 back.
                    if err.code != 429 or attempt >= len(RATE_LIMIT_WAITS_S):
                        break
                    wait = RATE_LIMIT_WAITS_S[attempt]
                    sys.stderr.write(f"or_proxy: upstream 429, waiting {wait}s before retry {attempt + 1}\n")
                    import time
                    time.sleep(wait)
        except Exception as exc:  # noqa: BLE001
            self.send_response(502)
            msg = json.dumps({"error": {"message": f"or_proxy upstream failure: {exc!r}"}}).encode()
            self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close"); self.end_headers(); self.wfile.write(msg)
            return
        if resp.status >= 400 and original:
            # keep the offending request for post-mortem; /logs/agent is collected by Harbor
            try:
                import os, time
                os.makedirs(DUMP_DIR, exist_ok=True)
                with open(os.path.join(DUMP_DIR, f"or_proxy_{resp.status}_{int(time.time())}.json"), "wb") as fh:
                    fh.write(original)
                sys.stderr.write(f"or_proxy: upstream {resp.status}; request body dumped to {DUMP_DIR}\n")
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"or_proxy: could not dump request: {exc!r}\n")
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in HOP_BY_HOP:
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        self.close_connection = True

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._forward(self.rfile.read(length) if length else b"")

    def do_GET(self):
        self._forward(None)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    if len(sys.argv) > 2:
        Handler.upstream = sys.argv[2].rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    sys.stderr.write(f"or_proxy: listening on 127.0.0.1:{port} -> {Handler.upstream}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
