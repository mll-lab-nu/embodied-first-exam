"""Model gateway for one agent run: the harness talks to http://127.0.0.1:<port>, the gateway forwards to OpenRouter.
Both wire formats go through it: Anthropic Messages (Claude Code) and OpenAI Responses (Codex).

The adapter uploads this file into the task container and starts it before the harness. It
  1. holds the OpenRouter key (read from a file it deletes at start), so the harness's environment has only a
     placeholder token;
  2. pins what the harness cannot set itself: the model and OpenRouter's provider routing (e.g. only openai/flex, no
     fallbacks), plus a default `reasoning` setting when the request carries none; with --upstream set to ChatGPT's
     Codex backend (a ChatGPT login's access token as the key), config "headers" adds its account-id header and
     "strip_prefix" maps /v1/responses onto <base>/responses;
  3. waits out transient upstream failures (see RETRY_WINDOW_S below);
  4. logs every exchange (the last two request messages + the full raw response, and any retries) to a JSONL file in
     the trial's agent log directory, so empty replies, errors, rate-limit waits and served providers are on record;
     config "dump_requests": N also saves the first N request bodies, as sent upstream, to requests/<i>.json there.

Standard library only (python3 is in every task image). Streaming responses are relayed chunk by chunk.

    python3 llm_gateway.py --port 8787 --key-file F --log /logs/agent/gateway.jsonl \
        --config '{"model": "openai/gpt-6-luna", "provider": {"only": ["openai/flex"], "allow_fallbacks": false}}'
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8787)
ap.add_argument("--upstream", default="https://openrouter.ai/api")
ap.add_argument("--key-file", required=True)
ap.add_argument("--config", default="{}")
ap.add_argument("--log", required=True)
args = ap.parse_args()

with open(args.key_file) as f:
    KEY = f.read().strip()
os.remove(args.key_file)
CFG = json.loads(args.config)
UP = urllib.parse.urlparse(args.upstream)
CONN = http.client.HTTPSConnection if UP.scheme == "https" else http.client.HTTPConnection
LOCK = threading.Lock()
COUNT = [0]
# Hop-by-hop headers, plus the ones the gateway sets itself. Dropping accept-encoding keeps the logged bodies readable.
DROP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding",
        "upgrade", "content-length", "host", "authorization", "x-api-key", "accept-encoding"}

# Transient upstream failures. OpenAI's flex tier sheds load with rate-limit errors, and OpenRouter reports those
# either as an HTTP error or as an HTTP 200 whose body, or whose first stream event, is an error. The harness backs off
# and retries only on a real HTTP error status; a 200 carrying an error ends its session. So the gateway retries such
# failures itself for up to RETRY_WINDOW_S per request (short of the harness's own request timeout), and when the
# window runs out it answers with the matching HTTP status (429, 529, ...), which hands over to the harness's retry.
RETRY_WINDOW_S = float(CFG.get("retry_window_s", 240))
RETRYABLE = {408, 429, 500, 502, 503, 504, 520, 522, 524, 529}
ERROR_STATUS = {"invalid_request_error": 400, "authentication_error": 401, "permission_error": 403,
                "not_found_error": 404, "request_too_large": 413, "rate_limit_error": 429, "api_error": 500,
                "timeout_error": 504, "overloaded_error": 529}
STATUS_ERROR = {v: k for k, v in ERROR_STATUS.items()}
# Stream events that mean the reply itself has started; until one arrives the gateway holds the stream back, so an
# error event that comes first (after message_start / response.created) can still be retried or turned into an HTTP
# error status. Anthropic Messages events by name; OpenAI Responses events by prefix (response.output_*, ...).
CONTENT_EVENTS = {"content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"}
CONTENT_PREFIXES = ("response.output", "response.content_part", "response.reasoning", "response.function_call",
                    "response.completed", "response.incomplete")
ERROR_EVENTS = {"error", "response.failed"}
EVENT = re.compile(rb"^event:\s*(\S+)\s*$", re.M)
DATA = re.compile(rb"^data:\s*(.*)$", re.M)


def write_log(rec: dict) -> None:
    with LOCK, open(args.log, "a") as f:
        f.write(json.dumps(rec) + "\n")


def pin(body: bytes, rec: dict) -> bytes:
    try:
        d = json.loads(body)
    except ValueError:
        return body
    if not isinstance(d, dict) or "model" not in d:
        return body
    rec["model_requested"] = d.get("model")
    if CFG.get("model"):
        d["model"] = CFG["model"]
    if CFG.get("provider"):
        d["provider"] = CFG["provider"]
    if CFG.get("reasoning") and "thinking" not in d and "reasoning" not in d:
        d["reasoning"] = CFG["reasoning"]
    msgs = d.get("messages") or (d.get("input") if isinstance(d.get("input"), list) else [])
    rec.update(model=d.get("model"), provider=d.get("provider"), stream=d.get("stream"), n_messages=len(msgs),
               n_tools=len(d.get("tools") or []), max_tokens=d.get("max_tokens"), thinking=d.get("thinking"),
               reasoning=d.get("reasoning"), tail=msgs[-2:])
    return json.dumps(d).encode()


def error_of(data: bytes) -> tuple[str, str] | None:
    """(error type, message) when `data` is an error body: Anthropic's {"type": "error", "error": {...}} or
    OpenRouter's own {"error": {"code": ..., "message": ...}}; None otherwise."""
    try:
        d = json.loads(data)
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("error"), dict) or d.get("type") not in (None, "error"):
        return None
    e = d["error"]
    etype = e.get("type")
    if etype not in ERROR_STATUS:
        code = e.get("code")
        etype = STATUS_ERROR.get(code if isinstance(code, int) else 500, "api_error")
    return etype, str(e.get("message") or "")[:2000]


def stream_head(buf: bytes) -> tuple[str, tuple[str, str] | None] | None:
    """Look at the complete events in `buf`: ("content", None) once the reply has started, ("error", (type, message))
    when an error event comes first, None while only message_start / ping / comments have arrived."""
    for ev in buf.replace(b"\r\n", b"\n").split(b"\n\n")[:-1]:
        m = EVENT.search(ev)
        d = DATA.search(ev)
        name = m.group(1).decode() if m else ""
        if not name and d:                          # an OpenAI-style stream may carry the type in the data only
            try:
                name = str((json.loads(d.group(1)) or {}).get("type") or "")
            except ValueError:
                name = ""
        if name in CONTENT_EVENTS or name.startswith(CONTENT_PREFIXES):
            return "content", None
        if name in ERROR_EVENTS:
            err = error_of(d.group(1)) if d else None
            if err is None and d:
                try:                                # response.failed: {"response": {"error": {"code", "message"}}}
                    e = ((json.loads(d.group(1)) or {}).get("response") or {}).get("error") or {}
                    code = e.get("code")
                    err = (STATUS_ERROR.get(code if isinstance(code, int) else 0) or
                           ("rate_limit_error" if "rate" in str(code).lower() else "api_error"), str(e.get("message") or "")[:2000])
                except ValueError:
                    err = None
            return "error", err or ("api_error", "stream error event")
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet; the JSONL log is the record
        pass

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(200, b"ok", "text/plain")
            return
        self._forward(None)

    def do_POST(self):
        self._forward(self.rfile.read(int(self.headers.get("Content-Length") or 0)))

    def _reply(self, code: int, data: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _attempt(self, body: bytes | None, headers: dict):
        """One upstream request. Returns ("ok", status, resp headers, conn, resp, head bytes) for a reply to relay
        (for a stream: the part read so far, the rest is still in `resp`), or ("fail", status, error type, message,
        raw bytes) for an upstream failure."""
        conn = CONN(UP.netloc, timeout=900)
        try:
            path = self.path   # e.g. Codex posts /v1/responses; ChatGPT's backend serves <base>/responses
            if CFG.get("strip_prefix") and path.startswith(CFG["strip_prefix"]):
                path = path[len(CFG["strip_prefix"]):]
            conn.request(self.command, UP.path.rstrip("/") + path, body=body, headers=headers)
            resp = conn.getresponse()
            hdrs = resp.getheaders()
            if resp.status == 200 and "text/event-stream" in (resp.getheader("Content-Type") or ""):
                head = bytearray()
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    head += chunk
                    seen = stream_head(bytes(head))
                    if seen and seen[0] == "error":
                        conn.close()
                        etype, msg = seen[1]
                        return "fail", ERROR_STATUS.get(etype, 500), etype, msg, bytes(head)
                    if seen:
                        break
                return "ok", resp.status, hdrs, conn, resp, bytes(head)
            data = resp.read()
            conn.close()
            err = error_of(data)
            if resp.status == 200 and err:
                return "fail", ERROR_STATUS.get(err[0], 500), err[0], err[1], data
            if resp.status in RETRYABLE:
                etype, msg = err or (STATUS_ERROR.get(resp.status, "api_error"), data[:500].decode("utf-8", "replace"))
                return "fail", resp.status, etype, msg, data
            return "ok", resp.status, hdrs, None, None, data
        except Exception as exc:  # noqa: BLE001
            conn.close()
            return "fail", 502, "api_error", f"model gateway: upstream unreachable ({exc!r})"[:500], b""

    def _forward(self, body: bytes | None) -> None:
        with LOCK:
            COUNT[0] += 1
            i = COUNT[0]
        rec = {"i": i, "t": round(time.time(), 3), "method": self.command, "path": self.path}
        if body:
            body = pin(body, rec)
            if i <= int(CFG.get("dump_requests") or 0):   # full request bodies (the credential is a header, never here)
                d = os.path.join(os.path.dirname(args.log), "requests"); os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, f"{i:03d}.json"), "wb") as f:
                    f.write(body)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in DROP}
        headers["Authorization"] = "Bearer " + KEY
        headers.update(CFG.get("headers") or {})   # e.g. ChatGPT's backend wants the account id with the login token
        headers["Host"] = UP.netloc
        if body is not None:
            headers["Content-Length"] = str(len(body))
        t0 = time.time()
        retries, wait = [], 5.0
        while True:
            res = self._attempt(body, headers)
            if res[0] == "ok":
                break
            _, status, etype, msg, raw = res
            retries.append({"t": round(time.time(), 3), "status": status, "error": etype, "message": msg[:300]})
            retryable = status in RETRYABLE
            if not retryable or time.time() - t0 + wait > RETRY_WINDOW_S:
                rec.update(status=status, latency_s=round(time.time() - t0, 2), retries=retries,
                           retry_wait_s=round(sum(r.get("wait_s", 0) for r in retries), 1),
                           response=raw.decode("utf-8", "replace"), gave_up=retryable)
                write_log(rec)
                err = {"type": "error", "error": {"type": etype, "message": msg or f"upstream error {status}"}}
                self._reply(status, json.dumps(err).encode(), "application/json",
                            {"retry-after": "20"} if retryable else None)
                return
            nap = wait * random.uniform(0.8, 1.2)
            retries[-1]["wait_s"] = round(nap, 1)
            time.sleep(nap)
            wait = min(wait * 2, 60.0)
        _, status, hdrs, conn, resp, head = res
        if retries:
            rec.update(retries=retries, retry_wait_s=round(sum(r.get("wait_s", 0) for r in retries), 1))
        self.send_response(status)
        for k, v in hdrs:
            if k.lower() not in DROP:
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        out = bytearray(head)
        try:
            if head:
                self.wfile.write(b"%x\r\n%s\r\n" % (len(head), head))
                self.wfile.flush()
            while resp is not None:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                out += chunk
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            rec["client_gone"] = True
        finally:
            if conn is not None:
                conn.close()
        rec.update(status=status, latency_s=round(time.time() - t0, 2), response=out.decode("utf-8", "replace"))
        write_log(rec)


ThreadingHTTPServer.daemon_threads = True
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
