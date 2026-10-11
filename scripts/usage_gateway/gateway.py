#!/usr/bin/env python3
"""Transparent usage gateway: forwards an agent's model-API requests unchanged and records, per trial, the tokens each
request used, as it happens. Runner-side tooling (not task code, not an agent adapter): the agent is Harbor's own
`codex` / `claude-code`, pointed here by its base URL; it keeps its own credentials, which the gateway passes through
and never logs or stores.

    scripts/usage_gateway/gateway.py --jobs <harbor -o dir> [--bind 172.17.0.1] [--port 0] [--raw] [--ready-file F]

Routes: /u/<host>/<path> -> https://<host>/<path>. <host> must be a model API (MODEL_HOSTS below, the hosts
scripts/set_agent_egress.py allows), so the gateway can never carry an agent past its egress allowlist.
/h/<host>:<port>/<path> -> http://<host>:<port>/<path>, only for an exact <host>:<port> the runner named with --http-host
(a self-hosted model server without TLS, e.g. sglang's Anthropic-compatible API): the agent's own configured base URL.

Model-API paths only (PROTOCOL §2.11; owner 2026-10-10): on such a host the gateway forwards only the requests listed in
api_paths.json for the host's provider (the model calls: responses, chat completions, messages, token counting, the
model list) and answers everything else 403 without forwarding it: account connectors and apps, plugins, files,
conversations, web search. A provider's hosts are on the task's egress allowlist only so that the model can be called;
with the gateway on, the runner takes them off it (scripts/run_agent_batch.sh: the allowlist is the gateway's address),
so these paths are all an agent's container reaches at its provider, whatever it runs with the credentials it holds. A
refusal is recorded like a request (usage.jsonl: "refused": "path_not_allowed", method, path without the query; no
body) and counted in totals.json ("refused_paths"), for the runner to flag. A model request's body is forwarded as it
is or not at all: the tool types it declares that are not the agent's own (anything but a function / custom tool) are
recorded as "server_tools", and a request that declares one the provider would run with its own network or files
(SERVER_TOOLS: web search and fetch, image generation, remote MCP, file search, code interpreters) is refused the same
way ("refused": "server_tool"; --server-tools record only records, for a run that allows the harness's web search).
Only a body the gateway can read is checked: Codex compresses its ChatGPT-login requests with zstd, which needs the
`zstandard` module on the runner host (without it such a body is forwarded unchecked, "body_unchecked": true).

Attribution: a request's source IP is the trial's container (or, under an egress allowlist, its egress sidecar). Harbor
names a trial's compose project `<trial>__env`, so `docker inspect` maps the IP to the project and the project to the
trial directory <jobs>/<job>/<trial>/. Everything a trial's requests produce goes to <trial>/gateway/, next to Harbor's
own agent/ and verifier/ (not inside agent/, which the agent's container mounts and could rewrite):

    usage.jsonl        one line per request: time, duration, host, path, status, model, normalized and raw usage
    totals.json        running totals (rewritten after every request): requests, input / cached / output tokens
    raw.jsonl.gz       with --raw: every request body and response body (SSE text) as sent and received, deduplicated
                       (rawlog.py: each conversation item is stored once, a request as references to them; lossless);
                       credentials, cookies and account ids are removed from the recorded headers. usage.jsonl's "raw"
                       is the request's n there. `rawlog.py compact` (run_agent_batch.sh, after each job) turns it into
                       raw.jsonl.xz; `rawlog.py cat` prints the requests in full

Token budget (PROTOCOL §5, D10; on by default when the gateway runs): once a trial's totals reach --budget-input input
or --budget-output output tokens, totals.json gets over_token_budget = 1 and every further model request of that trial
is refused with HTTP 400 and a "token budget exceeded" error in the provider's format, without being forwarded, so the
agent stops; the request in flight when the budget is crossed completes. 0 disables a limit. The refusal avoids 429 and
"usage limit" wording on purpose: scripts/account_failure_check.py would read those as an account failure.

Token counts are normalized the way Harbor counts them: input = everything the model read (Anthropic: input +
cache_read + cache_creation; OpenAI: input_tokens, which include cached ones), output = output_tokens (reasoning
included). Requests from an address no trial owns go to <jobs>/.gateway/unattributed.jsonl.
"""
from __future__ import annotations

import argparse
import ast
import base64
import fnmatch
import gzip
import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rawlog  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _model_hosts() -> list[str]:
    """HOSTS from scripts/set_agent_egress.py (read, not imported: that script acts on import)."""
    src = (ROOT / "scripts" / "set_agent_egress.py").read_text()
    m = re.search(r"^HOSTS\s*=\s*(\[.*?\])", src, re.M | re.S)
    return ast.literal_eval(m.group(1)) if m else []


MODEL_HOSTS = _model_hosts()   # extended at start-up by --extra-host (e.g. an Azure AI Foundry *.services.ai.azure.com)
HTTP_HOSTS: set[str] = set()   # --http-host: exact <host>:<port> plain-HTTP upstreams (/h/ routes)
API_PATHS = pathlib.Path(__file__).resolve().parent / "api_paths.json"
PROVIDERS: list[dict] = []     # api_paths.json, loaded at start-up (load_paths); empty = every request refused
HTTP_PROVIDER = "http"         # the provider whose list a --http-host upstream gets


def load_paths(path: pathlib.Path = API_PATHS) -> list[dict]:
    """api_paths.json, checked: [{"name", "hosts": [pattern], "allow": [(METHOD, [segment, ...])]}]. A malformed file
    is an error at start-up (the gateway does not start), never a gateway that forwards everything."""
    out = []
    for p in json.loads(path.read_text())["providers"]:
        allow = []
        for method, pth in p["allow"]:
            if method not in ("GET", "POST") or not re.fullmatch(r"(/[A-Za-z0-9._*-]+)+", pth):
                raise ValueError(f"{path}: provider {p['name']}: bad rule {method} {pth}")
            allow.append((method, pth.split("/")[1:]))
        out.append({"name": str(p["name"]), "hosts": [str(h).lower() for h in p["hosts"]], "allow": allow})
    return out


def provider_of(host: str, plain: bool) -> dict | None:
    """The provider whose path list applies to this upstream: a --http-host upstream gets HTTP_PROVIDER's, an HTTPS host
    the first provider one of whose host patterns matches it; None = no list, nothing is forwarded."""
    for p in PROVIDERS:
        if (p["name"] == HTTP_PROVIDER) if plain else any(fnmatch.fnmatchcase(host.lower(), h) for h in p["hosts"]):
            return p
    return None


def path_allowed(provider: dict | None, method: str, path: str) -> bool:
    """Default deny. `path` as the client sent it; the query string is not part of the match. A path that is not plain
    (a percent escape, an empty or dot segment, a backslash: nothing a model call needs) is refused, so that no
    upstream normalization can turn a listed path into another one."""
    if provider is None:
        return False
    p = path.split("?", 1)[0]
    if not re.fullmatch(r"(/[A-Za-z0-9._-]+)+", p):
        return False
    seg = p.split("/")[1:]
    if any(s in (".", "..") for s in seg):
        return False
    return any(m == method and len(a) == len(seg) and all(x == "*" or x == y for x, y in zip(a, seg))
               for m, a in provider["allow"])


# tool types (prefixes) that the provider runs with its own network or files: a request declaring one is not forwarded
SERVER_TOOLS = ("web_search", "web_fetch", "image_generation", "mcp", "file_search", "code_interpreter", "code_execution")


def server_tools(text: str | None) -> list[str]:
    """The tool types a model request declares that are not the agent's own (function / custom tools carry no type or
    one of these two): they run at the provider (web search, image generation, remote MCP, code interpreter ...).
    From the decoded JSON body; [] when it cannot be read."""
    if not text or '"tools"' not in text:
        return []
    try:
        body = json.loads(text)
    except ValueError:
        return []
    found = set()
    if isinstance(body, dict):
        for t in body.get("tools") or []:
            if isinstance(t, dict) and t.get("type") not in (None, "function", "custom"):
                found.add(str(t["type"])[:64])
        if body.get("mcp_servers"):
            found.add("mcp_servers")
    return sorted(found)
HOP = {"connection", "keep-alive", "proxy-connection", "te", "trailers", "transfer-encoding", "upgrade", "host",
       "content-length", "accept-encoding"}
SECRET = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie", "chatgpt-account-id", "openai-organization",
          "openai-project", "x-goog-api-key"}
LOCK = threading.Lock()


# --------------------------------------------------------------------------- usage
def usage_from(obj, acc: dict) -> None:
    """Merge the usage found in one JSON object (a response body or one SSE event) into acc."""
    if not isinstance(obj, dict):
        return
    t = obj.get("type")
    if t == "message_start":                                            # Anthropic Messages stream
        msg = obj.get("message") or {}
        acc.setdefault("model", msg.get("model"))
        acc.setdefault("raw", {}).update(msg.get("usage") or {})
    elif t == "message_delta":
        acc.setdefault("raw", {}).update({k: v for k, v in (obj.get("usage") or {}).items() if v is not None})
    elif t in ("response.completed", "response.done", "response.incomplete", "response.failed"):   # OpenAI Responses
        resp = obj.get("response") or {}
        acc.setdefault("model", resp.get("model"))
        if resp.get("usage"):
            acc["raw"] = resp["usage"]
    elif isinstance(obj.get("usage"), dict):                            # non-streamed bodies; Chat Completions chunks
        acc.setdefault("model", obj.get("model"))
        acc["raw"] = obj["usage"]


def normalize(raw: dict) -> dict:
    """{input, cached, output} in Harbor's convention (see the module doc)."""
    if not raw:
        return {}
    if "cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw:     # Anthropic
        cached = int(raw.get("cache_read_input_tokens") or 0)
        return {"input": int(raw.get("input_tokens") or 0) + cached + int(raw.get("cache_creation_input_tokens") or 0),
                "cached": cached, "output": int(raw.get("output_tokens") or 0)}
    if "input_tokens" in raw:                                                         # OpenAI Responses
        return {"input": int(raw.get("input_tokens") or 0),
                "cached": int((raw.get("input_tokens_details") or {}).get("cached_tokens") or 0),
                "output": int(raw.get("output_tokens") or 0)}
    if "prompt_tokens" in raw:                                                        # Chat Completions
        return {"input": int(raw.get("prompt_tokens") or 0),
                "cached": int((raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
                "output": int(raw.get("completion_tokens") or 0)}
    return {}


def parse_body(body: bytes, acc: dict) -> None:
    """Usage from a whole response: SSE (`data:` lines) or one JSON document."""
    found = False
    for line in body.split(b"\n"):
        if line.startswith(b"data:"):
            try:
                usage_from(json.loads(line[5:].strip()), acc); found = True
            except ValueError:
                pass
    if not found:
        try:
            usage_from(json.loads(body), acc)
        except ValueError:
            pass


def decode_request(body: bytes, encoding: str) -> tuple[str | None, str]:
    """(text, how): the request body as text when it can be decoded, else None (it is kept as base64)."""
    enc = (encoding or "").lower().strip()
    try:
        if enc in ("", "identity"):
            data = body
        elif enc == "gzip":
            data = gzip.decompress(body)
        elif enc == "zstd":
            import zstandard                                    # optional: pip install zstandard
            data = zstandard.ZstdDecompressor().decompressobj().decompress(body)
        else:
            return None, f"undecoded {enc}"
        return data.decode("utf-8"), "text"
    except Exception as exc:  # noqa: BLE001 -- a body we cannot decode is still recorded, as base64
        return None, f"undecoded {enc}: {type(exc).__name__}"


# --------------------------------------------------------------------------- trials
def sanitize(name: str) -> str:
    """Harbor's docker compose project name (harbor/environments/docker/docker.py)."""
    name = name.lower()
    if not re.match(r"^[a-z0-9]", name):
        name = "0" + name
    return re.sub(r"[^a-z0-9_-]", "-", name)


class Trials:
    """Source IP -> trial directory, from docker's compose labels. Docker reuses subnets and addresses once a trial's
    network is gone, so a mapping is trusted for TTL seconds only and every scan replaces the whole table; a new trial
    needs far longer than that (image build, agent install) before its first model call."""
    TTL = 5.0

    def __init__(self, jobs: pathlib.Path):
        self.jobs, self.by_ip, self.last_scan = jobs, {}, 0.0
        self.lock = threading.Lock()

    def _scan(self) -> None:
        ids = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, timeout=30).stdout.split()
        if not ids:
            self.by_ip = {}
            return
        fmt = '{{index .Config.Labels "com.docker.compose.project"}}{{range .NetworkSettings.Networks}} {{.IPAddress}}{{end}}'
        out = subprocess.run(["docker", "inspect", "-f", fmt, *ids], capture_output=True, text=True, timeout=30).stdout
        projects = {}
        for line in out.splitlines():
            proj, *ips = line.split()
            if proj.endswith("__env"):
                for ip in ips:
                    projects[ip] = proj[: -len("__env")]
        dirs = {}
        for job in self.jobs.iterdir():
            if job.is_dir() and not job.name.startswith("."):
                for trial in job.iterdir():
                    if trial.is_dir() and "__" in trial.name:
                        dirs[sanitize(trial.name)] = trial
        self.by_ip = {ip: dirs[proj] for ip, proj in projects.items() if proj in dirs}

    def lookup(self, ip: str) -> pathlib.Path | None:
        with self.lock:
            if time.time() - self.last_scan > self.TTL or (ip not in self.by_ip and time.time() - self.last_scan > 1):
                self.last_scan = time.time()
                try:
                    self._scan()
                except Exception as exc:  # noqa: BLE001 -- attribution failure must not break the agent's request
                    log(f"docker scan failed: {exc}")
                    self.by_ip = {}
            return self.by_ip.get(ip)


# --------------------------------------------------------------------------- server
ARGS: argparse.Namespace
TRIALS: Trials
SEQ = {"n": 0}
RAWLOGS: dict[pathlib.Path, rawlog.Writer] = {}     # per trial; a restarted gateway resumes from the file


def log(msg: str) -> None:
    with LOCK, open(ARGS.jobs / ".gateway" / f"gateway-{os.getpid()}.log", "a") as f:
        f.write(f"[{time.strftime('%F %T')}] {msg}\n")


def record(trial: pathlib.Path | None, rec: dict, raw: dict | None) -> None:
    with LOCK:
        SEQ["n"] += 1
        seq = SEQ["n"]
        if trial is None:
            with open(ARGS.jobs / ".gateway" / "unattributed.jsonl", "a") as f:
                f.write(json.dumps({**rec, "seq": seq}) + "\n")
            return
        d = trial / "gateway"
        d.mkdir(exist_ok=True)
        if raw is not None:
            if d not in RAWLOGS:
                if len(RAWLOGS) >= 256:                 # finished trials: drop the oldest table
                    del RAWLOGS[next(iter(RAWLOGS))]
                RAWLOGS[d] = rawlog.Writer(d / rawlog.NAME)
            rec["raw"] = RAWLOGS[d].append(raw)
        with open(d / "usage.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        tp = d / "totals.json"
        tot = json.loads(tp.read_text()) if tp.exists() else {"requests": 0, "input": 0, "cached": 0, "output": 0,
                                                               "no_usage": 0}
        u = rec.get("usage") or {}
        if rec.get("refused") == "path_not_allowed":
            tot["refused_paths"] = tot.get("refused_paths", 0) + 1
        elif rec.get("refused") == "server_tool":
            tot["refused_server_tools"] = tot.get("refused_server_tools", 0) + 1
        elif rec.get("refused"):
            tot["refused"] = tot.get("refused", 0) + 1
        else:
            tot["requests"] += 1
            if u:
                for k in ("input", "cached", "output"):
                    tot[k] += u.get(k, 0)
            else:
                tot["no_usage"] += 1
            if rec.get("server_tools"):
                tot["server_tool_requests"] = tot.get("server_tool_requests", 0) + 1
        tot["updated"] = rec["ts"]
        tot["budget"] = {"input": ARGS.budget_input, "output": ARGS.budget_output}
        if over_budget(tot):
            tot["over_token_budget"] = 1
        tmp = tp.with_suffix(".tmp")
        tmp.write_text(json.dumps(tot, indent=1))
        tmp.replace(tp)


def over_budget(tot: dict) -> bool:
    return bool((ARGS.budget_input and tot.get("input", 0) >= ARGS.budget_input)
                or (ARGS.budget_output and tot.get("output", 0) >= ARGS.budget_output))


def trial_totals(trial: pathlib.Path | None) -> dict:
    tp = trial / "gateway" / "totals.json" if trial else None
    if not tp or not tp.exists():
        return {}
    with LOCK:
        try:
            return json.loads(tp.read_text())
        except ValueError:
            return {}


def api_error(host: str, path: str, msg: str, code: str) -> dict:
    """An error body in the provider's own format, so that the harness shows the message."""
    if "anthropic" in host or "/messages" in path.split("?")[0]:   # Anthropic Messages API, any host
        return {"type": "error", "error": {"type": "invalid_request_error", "message": msg}}
    return {"error": {"message": msg, "type": "invalid_request_error", "code": code, "param": None}}


def budget_error(host: str, path: str, tot: dict) -> dict:
    msg = (f"token budget exceeded for this trial: input {tot.get('input', 0)} / {ARGS.budget_input}, output "
           f"{tot.get('output', 0)} / {ARGS.budget_output} (PROTOCOL §5); the run is over")
    return api_error(host, path, msg, "token_budget_exceeded")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def _reply(self, code: int, obj: dict, close: bool = False) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if close:                                   # the request body was not read: this connection ends here
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def forward(self) -> None:
        if self.path == "/_gateway/health":
            return self._reply(200, {"ok": True})
        m = re.match(r"^/u/([A-Za-z0-9.-]+)(/.*)?$", self.path)
        plain = re.match(r"^/h/([A-Za-z0-9.-]+:[0-9]+)(/.*)?$", self.path)   # a --http-host upstream (no TLS)
        if plain and plain.group(1).lower() in HTTP_HOSTS:
            m = plain
        elif not m or not any(fnmatch.fnmatch(m.group(1).lower(), h) for h in MODEL_HOSTS):
            return self._reply(403, {"error": "usage gateway: not a model API host (scripts/set_agent_egress.py HOSTS)"})
        if (self.headers.get("Upgrade") or "").lower() == "websocket":
            return self._reply(405, {"error": "usage gateway: no WebSocket; use HTTPS (supports_websockets = false)"})
        host, path = m.group(1), m.group(2) or "/"
        t0 = time.time()
        ip = self.client_address[0]
        trial = TRIALS.lookup(ip)                  # now: a request that outlives its trial (a timeout) still counts for it
        if not path_allowed(provider_of(host, m is plain), self.command, path):   # default deny, never forwarded
            shown = re.sub(r"[^A-Za-z0-9._~/*%:@+,=-]", "?", path.split("?", 1)[0])[:300]
            record(trial, {"ts": round(t0, 3), "dur_s": 0.0, "client_ip": ip, "host": host, "method": self.command,
                           "path": shown, "status": 403, "model": None, "usage": {}, "usage_raw": {},
                           "request_bytes": int(self.headers.get("Content-Length") or 0), "response_bytes": 0,
                           "client_gone": False, "refused": "path_not_allowed"}, None)
            log(f"refused {self.command} {host}{shown} from {ip} ({trial.name if trial else 'no trial'})")
            return self._reply(403, api_error(host, path, (
                f"usage gateway: {self.command} {shown} is not a model API call and was not forwarded (PROTOCOL §2.11: "
                "only the model's own API is available in a trial; scripts/usage_gateway/api_paths.json)"),
                "path_not_allowed"), close=True)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        text, how = decode_request(body, self.headers.get("Content-Encoding", "")) if body else (None, "text")
        tools = server_tools(text)
        barred = [t for t in tools if t.startswith(SERVER_TOOLS)]
        if barred and ARGS.server_tools == "refuse":         # never forwarded: the provider would run it for the agent
            record(trial, {"ts": round(t0, 3), "dur_s": 0.0, "client_ip": ip, "host": host, "method": self.command,
                           "path": path.split("?")[0], "status": 403, "model": None, "usage": {}, "usage_raw": {},
                           "request_bytes": len(body), "response_bytes": 0, "client_gone": False,
                           "refused": "server_tool", "server_tools": tools}, None)
            log(f"refused {self.command} {host}{path.split('?')[0]} from {ip}: server tools {barred}")
            return self._reply(403, api_error(host, path, (
                f"usage gateway: this request declares a tool that runs at the model provider ({', '.join(barred)}) "
                "and was not forwarded (PROTOCOL §2.11: no tool that runs outside the container)"), "server_tool_not_allowed"))
        tot = trial_totals(trial)
        if trial is not None and over_budget(tot):           # refuse, never forward: the trial has spent its budget
            record(trial, {"ts": round(t0, 3), "dur_s": 0.0, "client_ip": ip, "host": host, "method": self.command,
                           "path": path.split("?")[0], "status": 400, "model": None, "usage": {}, "usage_raw": {},
                           "request_bytes": len(body), "response_bytes": 0, "client_gone": False,
                           "refused": "over_token_budget"}, None)
            return self._reply(400, budget_error(host, path, tot))
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        hdrs["Host"] = host
        if body:
            hdrs["Content-Length"] = str(len(body))
        acc, chunks, client_gone = {}, [], False
        try:
            conn = (http.client.HTTPConnection if m is plain else http.client.HTTPSConnection)(host, timeout=ARGS.timeout)
            conn.request(self.command, path, body=body or None, headers=hdrs)
            r = conn.getresponse()
        except Exception as exc:  # noqa: BLE001 -- the agent sees an upstream error, as it would without the gateway
            log(f"upstream {host}: {exc!r}")
            return self._reply(502, {"error": f"usage gateway: upstream {host} unreachable: {type(exc).__name__}"})
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        while True:
            chunk = r.read1(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if not client_gone:                    # the agent hung up: keep reading, the request is billed anyway
                try:
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk)); self.wfile.flush()
                except OSError:
                    client_gone = True
        if not client_gone:
            try:
                self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()
            except OSError:
                client_gone = True
        resp = b"".join(chunks)
        parse_body(resp, acc)
        trial = trial or TRIALS.lookup(ip)
        rec = {"ts": round(t0, 3), "dur_s": round(time.time() - t0, 2), "client_ip": ip, "host": host,
               "method": self.command, "path": path.split("?")[0], "status": r.status, "model": acc.get("model"),
               "usage": normalize(acc.get("raw") or {}), "usage_raw": acc.get("raw") or {},
               "request_bytes": len(body), "response_bytes": len(resp), "client_gone": client_gone,
               "session": {k.lower(): v for k, v in self.headers.items() if "session" in k.lower()}}
        raw = None
        if tools:
            rec["server_tools"] = tools
        if body and text is None:                   # e.g. zstd without the zstandard module: forwarded unchecked
            rec["body_unchecked"] = True
        if ARGS.raw:
            raw = {"request": {"method": self.command, "host": host, "path": path,
                               "headers": {k: v for k, v in self.headers.items() if k.lower() not in SECRET},
                               "body": text if text is not None else base64.b64encode(body).decode(), "body_as": how},
                   "response": {"status": r.status,
                                "headers": {k: v for k, v in r.getheaders() if k.lower() not in SECRET},
                                "body": resp.decode("utf-8", "replace")}}
        record(trial, rec, raw)


def main() -> int:
    global ARGS, TRIALS
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jobs", type=pathlib.Path, required=True, help="Harbor's -o directory")
    p.add_argument("--bind", default="172.17.0.1", help="the docker bridge address containers reach the host by")
    p.add_argument("--port", type=int, default=0, help="0 = any free port (written to --ready-file)")
    p.add_argument("--raw", action="store_true", help="also record request and response bodies (raw.jsonl.gz)")
    p.add_argument("--ready-file", type=pathlib.Path, help="written with the port once the gateway listens")
    p.add_argument("--timeout", type=float, default=900.0, help="upstream socket timeout, seconds")
    p.add_argument("--extra-host", action="append", default=[], help="another model API host pattern to forward to (repeatable)")
    p.add_argument("--http-host", action="append", default=[],
                   help="a plain-HTTP model server <host>:<port>, reached at /h/<host>:<port>/... (repeatable, exact match)")
    p.add_argument("--api-paths", type=pathlib.Path, default=API_PATHS,
                   help="the model-API requests to forward, per provider (default: api_paths.json next to this file)")
    p.add_argument("--server-tools", choices=("refuse", "record"), default="refuse",
                   help="a model request that declares a provider-run tool (SERVER_TOOLS): refuse it (default) or only record it")
    p.add_argument("--budget-input", type=int, default=100_000_000, help="per-trial input tokens; 0 = no limit (D10)")
    p.add_argument("--budget-output", type=int, default=10_000_000, help="per-trial output tokens; 0 = no limit (D10)")
    ARGS = p.parse_args()
    ARGS.jobs = ARGS.jobs.resolve()
    MODEL_HOSTS.extend(h.lower() for h in ARGS.extra_host)
    HTTP_HOSTS.update(h.lower() for h in ARGS.http_host)
    PROVIDERS[:] = load_paths(ARGS.api_paths)
    (ARGS.jobs / ".gateway").mkdir(parents=True, exist_ok=True)
    TRIALS = Trials(ARGS.jobs)
    srv = ThreadingHTTPServer((ARGS.bind, ARGS.port), Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    log(f"listening on {ARGS.bind}:{port}, jobs {ARGS.jobs}, raw={ARGS.raw}, hosts {MODEL_HOSTS}, http {sorted(HTTP_HOSTS)}, "
        f"model-API paths of {[p['name'] for p in PROVIDERS]} only ({ARGS.api_paths.name})")
    if ARGS.ready_file:
        ARGS.ready_file.write_text(str(port))
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
