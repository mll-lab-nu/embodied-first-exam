"""Contract ① (docs/framework_zh.md §4.1), the envelope: the seat-facing HTTP layer shared by both protocols:
/<SEAT>/<endpoint>, the caller's address must be that seat's container (SEAT_HOSTS=A=seat_a,B=seat_b; without it only
localhost), per seat at most `open_requests` open requests and `rate_per_s` requests per second, JSON bodies up to 64
KiB. A service maps endpoints to methods returning (status, body).

Limits (core 0.3.0): the service's `limits` (core/acts.derive_limits: from the control period, the slowdown and the
seat's robots, never below the floors SLOTS = 4 open requests and RATE = 20 per second, the limits before 0.3.0; the
turn protocol and a service without `limits` keep the floors). Arrival (core 0.3.0): every request of an authorized
seat is first passed to the service's `arrive(seat)` (the start barrier, core/phases.py), if it has one.

The budget (core 0.2.16) belongs to the authenticated seat: the seat a request names in its path, once the caller's
address is allowed to be that seat. A request for a seat its address may not be is refused (403) before it spends
anything, so a seat never spends another seat's budget. Before a request is read, an address may hold the budget of
every seat it may be (4 open connections and 20 per second per such seat); an address that may be no seat is refused.
Cores <= 0.2.15 charged a connection to the first seat its address may be: without SEAT_HOSTS every local seat shared
the first seat's budget (a team format's local seats got 429s). Every refusal for the budget is a bare 429 (no body),
which never reached the match: core/client.py retries it. Every such refusal is counted in the seat's stats
(final.json seats.<seat>: http_429_rate, http_429_open, http_429_conn; FWTEST 10-19)."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl

from . import deploys
from .sport import Refused, check_body

SLOTS, RATE = 4, 20                       # per seat: open requests, requests per second (the floors; core 0.3.0)


def seat_limits(service, seats) -> dict:
    """{seat: (open requests, requests per second)}: the service's derived limits, the floors without them."""
    lim = getattr(service, "limits", None) or {}
    return {s: (int((lim.get(s) or {}).get("open_requests", SLOTS)), int((lim.get(s) or {}).get("rate_per_s", RATE)))
            for s in seats}


RESOLVE_TTL_S = 30.0                      # a seat host's addresses are looked up again after this long
_resolved: dict = {}                      # host -> (monotonic time of the lookup, {addresses})
_resolve_lock = threading.Lock()


def host_addresses(host, fresh_s: float | None = None) -> set:
    """The addresses of a seat's container, looked up at most once per RESOLVE_TTL_S (FWTEAM 10-20: the accept thread
    looked up every seat's host for every connection, about 0.35 ms each through Docker's DNS; one seat flooding the
    server with connections then slowed every other seat's requests in the accept queue). A failed lookup is retried
    after 1 s; `fresh_s`: the age a cached answer may have (seat_allowed looks up again after a miss, at most once a
    second, so a container that changed its address is let in)."""
    now = time.monotonic()
    with _resolve_lock:
        hit = _resolved.get(host)
    ttl = fresh_s if fresh_s is not None else (RESOLVE_TTL_S if hit and hit[1] else 1.0)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except OSError:
        addrs = set()
    with _resolve_lock:
        _resolved[host] = (now, addrs)
    return addrs


def seat_allowed(seat, addr, hosts):
    if seat not in hosts:
        return addr in ("127.0.0.1", "::1")
    if addr in host_addresses(hosts[seat]):
        return True
    return addr in host_addresses(hosts[seat], fresh_s=1.0)   # a miss: looked up again, at most once a second


def make_server(service, seats, hosts, port=8000):
    limits = seat_limits(service, seats)
    arrive = getattr(service, "arrive", None)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def send(self, code, value):
            raw = json.dumps(value, default=float).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def dispatch(self, post):
            path, _, self.qs = self.path.partition("?")          # a GET may carry ?team_since=N (core 0.2.20)
            bits = path.strip("/").split("/")
            if not post and bits == ["over"]:   # Embodied First Exam: whether the result is final (no seat, no arrival:
                return self.send(200, {"over": getattr(service, "phase", None) == "over"})   # the session's end on it)
            if len(bits) != 2 or bits[0] not in seats or not seat_allowed(bits[0], self.client_address[0], hosts):
                return self.send(403, {"error": "seat not authorized"})
            seat, ep = bits
            if arrive is not None:              # core 0.3.0: any request of a seat is its arrival (the start barrier)
                try:
                    arrive(seat)
                except Exception:  # noqa: BLE001     (a record: never refuse a request for it)
                    traceback.print_exc()
            why = self.server.admit(seat)       # the authenticated seat's own budget, never another seat's
            if why:
                self.server.note(seat, "http_429_" + why)   # FWTEST 10-19: every budget refusal is counted
                return self.too_many()
            try:
                self.handle_seat(seat, ep, post)
            finally:
                self.server.release(seat)

        def too_many(self):
            try:                                # read a small body first: closing on unread data may reset the reply
                n = int(self.headers.get("Content-Length", "0"))
                if 0 < n <= 65536:
                    self.rfile.read(n)
            except (ValueError, OSError):
                pass
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

        def handle_seat(self, seat, ep, post):
            try:                                # the request itself: any problem is the caller's (400), never a failure
                body = {}
                if not post and self.qs:            # GET parameters: small integers only (team_since, since)
                    for key, val in parse_qsl(self.qs[:256], keep_blank_values=False)[:4]:
                        if key in ("team_since", "since"):
                            if not val.isdigit() or len(val) > 12:
                                raise Refused(f"{key} must be a non-negative integer (a seq)")
                            body[key] = int(val)
                if post:
                    n = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= n <= 65536:
                        raise Refused("request too large (at most 64 KiB)")
                    body = json.loads(self.rfile.read(n) or b"{}")
                    if not isinstance(body, dict):
                        raise Refused("JSON object required")
                    check_body(body)
            except Refused as exc:
                return self.send(exc.code, {"error": str(exc)})
            except Exception:  # noqa: BLE001
                return self.send(400, {"error": "malformed request: a JSON object of at most 64 KiB required"})
            deploys.bind(deploys.from_headers(self.headers) if ep in ("act", "ready", "start", "resign") else None)   # D3; ready: the review comes from the agent's shell (core 0.2.39); start: its row's source (FWTEST 10-19: was always program_raw)
            try:
                fn = service.routes(post).get(ep)
                code, out = (404, {"error": "unknown endpoint"}) if fn is None else fn(seat, body)
            except Refused as exc:
                code, out = exc.code, {"error": str(exc)}
                if exc.cause:
                    print(f"refused {seat}/{ep}: {exc.cause}", file=sys.stderr, flush=True)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                code, out = 400, {"error": "invalid request"}
                print(f"invalid request {seat}/{ep}: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr,
                      flush=True)
            except BlockingIOError as exc:                              # core/workers.py: our own text
                code, out = 429, {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                service.failure(ep, exc)
                code, out = 500, {"error": "technical failure"}         # the details stay in the logs (G9)
            self.send(code, service.public(out) if hasattr(service, "public") else out)   # no hidden seed

        def do_GET(self):
            self.dispatch(False)

        def do_POST(self):
            self.dispatch(True)

    class Bounded(ThreadingHTTPServer):
        daemon_threads = True

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.lock = threading.Lock()
            self.slots = {s: threading.BoundedSemaphore(limits[s][0]) for s in seats}
            self.arrivals = {s: [] for s in seats}
            self.open = {}                      # address -> connections not yet closed
            self.recent = {}                    # address -> connection times in the last second

        def admit(self, seat):
            """A request of the authenticated seat: its own open requests and rate (in a handler thread). None when
            admitted, else why not: "rate" (rate_per_s) or "open" (open_requests)."""
            with self.lock:
                now = time.monotonic()
                self.arrivals[seat] = [t for t in self.arrivals[seat] if now - t < 1]
                if len(self.arrivals[seat]) >= limits[seat][1]:
                    return "rate"
                if not self.slots[seat].acquire(False):
                    return "open"
                self.arrivals[seat].append(now)
                return None

        def note(self, seat, key):
            """Count a refusal in the seat's stats (final.json seats.<seat>; FWTEST 10-19: before, a 429 of the HTTP
            budget left no record anywhere). Never fails a request."""
            st = (getattr(service, "seats", None) or {}).get(seat)
            if st is None or not hasattr(st, "count"):
                return
            with self.lock:
                st.count(key)

        def release(self, seat):
            self.slots[seat].release()

        def process_request(self, request, addr):
            # before the request is read: the address may hold the budget of every seat it may be, no more
            mine = [s for s in seats if seat_allowed(s, addr[0], hosts)]
            n_open, n_rate = sum(limits[s][0] for s in mine), sum(limits[s][1] for s in mine)
            with self.lock:
                now = time.monotonic()
                recent = [t for t in self.recent.get(addr[0], ()) if now - t < 1]
                ok = bool(mine) and len(recent) < n_rate and self.open.get(addr[0], 0) < n_open
                if ok:
                    self.recent[addr[0]] = recent + [now]
                    self.open[addr[0]] = self.open.get(addr[0], 0) + 1
                elif recent:
                    self.recent[addr[0]] = recent
                else:
                    self.recent.pop(addr[0], None)
            if not ok:
                if len(mine) == 1:                 # FWTEST 10-19: the address's connection budget, counted per seat
                    self.note(mine[0], "http_429_conn")
                try:
                    request.settimeout(.1)
                    request.sendall(b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, addr)
            except Exception:
                self.closed(addr[0])
                raise

        def closed(self, host):
            with self.lock:
                left = self.open.get(host, 0) - 1
                if left > 0:
                    self.open[host] = left
                else:
                    self.open.pop(host, None)

        def process_request_thread(self, request, addr):
            try:
                super().process_request_thread(request, addr)
            finally:
                self.closed(addr[0])

    return Bounded(("0.0.0.0", port), Handler)
