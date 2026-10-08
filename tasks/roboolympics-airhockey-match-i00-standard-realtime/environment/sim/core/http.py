"""Contract ① (docs/framework_zh.md §4.1), the envelope: the seat-facing HTTP layer shared by both protocols: /<SEAT>/<endpoint>, the caller's address must be that seat's
container (SEAT_HOSTS=A=seat_a,B=seat_b; without it only localhost), at most 4 open requests and 20 per second per
seat, JSON bodies up to 64 KiB. A service maps endpoints to methods returning (status, body)."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .sport import Refused, check_body


def seat_allowed(seat, addr, hosts):
    if seat not in hosts:
        return addr in ("127.0.0.1", "::1")
    try:
        return addr in {a[4][0] for a in socket.getaddrinfo(hosts[seat], None)}
    except OSError:
        return False


def make_server(service, seats, hosts, port=8000):
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
            bits = self.path.strip("/").split("/")
            if len(bits) != 2 or bits[0] not in seats or not seat_allowed(bits[0], self.client_address[0], hosts):
                return self.send(403, {"error": "seat not authorized"})
            seat, ep = bits
            try:                                # the request itself: any problem is the caller's (400), never a failure
                body = {}
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
            self.send(code, out)

        def do_GET(self):
            self.dispatch(False)

        def do_POST(self):
            self.dispatch(True)

    class Bounded(ThreadingHTTPServer):
        daemon_threads = True

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.slots = {s: threading.BoundedSemaphore(4) for s in seats}
            self.arrivals = {s: [] for s in seats}

        def process_request(self, request, addr):
            seat = next((s for s in seats if seat_allowed(s, addr[0], hosts)), None)
            if seat is not None:
                now = time.monotonic()
                self.arrivals[seat] = [t for t in self.arrivals[seat] if now - t < 1]
            if seat is None or len(self.arrivals[seat]) >= 20 or not self.slots[seat].acquire(False):
                try:
                    request.settimeout(.1)
                    request.sendall(b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass
                self.shutdown_request(request)
                return
            self.arrivals[seat].append(time.monotonic())
            try:
                super().process_request(request, (addr[0], addr[1], seat))
            except Exception:
                self.slots[seat].release()
                raise

        def process_request_thread(self, request, addr):
            try:
                super().process_request_thread(request, addr[:2])
            finally:
                self.slots[addr[2]].release()

    return Bounded(("0.0.0.0", port), Handler)
