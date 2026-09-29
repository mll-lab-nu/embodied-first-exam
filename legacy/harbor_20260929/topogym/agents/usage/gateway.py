"""Bounded HTTP/SSE proxy; real credentials and authoritative receipts stay here.

The Harbor adapter serves this over a Unix socket. Only the loopback relay is in
the agent network namespace. Provider routes and credentials cannot be changed
by a model request. Unsupported protocols fail closed.
"""
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import socket
from socketserver import ThreadingMixIn
import threading
import time
from uuid import uuid4

from .sources import PROTOCOLS
from .sources.base import validate_url
from .types import BudgetStopped, CapacityUnavailable

ROUTES = {name: protocol.route for name, protocol in PROTOCOLS.items()}
MAX_BODY = 64 * 1024 * 1024


class UnixHTTPServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind assumes an IP tuple.
        self.socket.bind(self.server_address)
        self.server_name, self.server_port = "localhost", 0


class Gateway:
    def __init__(self, service, *, protocol, upstream_url, api_key, socket_path=None,
                 address=("127.0.0.1", 0), timeout=120, default_output_cap=8192, route_id="primary", model=None):
        if protocol not in PROTOCOLS:
            raise ValueError("Unsupported provider protocol")
        parsed = validate_url(upstream_url)
        self.service, self.protocol, self.upstream = service, protocol, parsed
        self.provider_protocol, self.route_id = PROTOCOLS[protocol], route_id
        self.api_key, self.token = api_key, secrets.token_urlsafe(32)
        self.timeout, self.default_output_cap = timeout, default_output_cap
        self.model = model
        self.connections, self.lock = {}, threading.RLock()
        self.closing = threading.Event()
        self.socket_path = Path(socket_path) if socket_path else None
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass  # Never log prompts, keys or request headers.

            def do_GET(self):
                if self.path == "/budget" and hmac.compare_digest(
                        self.headers.get("Authorization", ""), "Bearer " + gateway.token):
                    if gateway.service.error:
                        gateway._reply(self, 503, "Usage watchdog failed")
                        return
                    data = json.dumps(gateway.service.ledger.snapshot()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(data)
                    self.close_connection = True
                    return
                self.send_error(404)

            def do_POST(self):
                gateway.handle(self)

        if self.socket_path:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            self.server = UnixHTTPServer(str(self.socket_path), Handler)
            self.socket_path.chmod(0o666)  # auth is per-trial; mount directory is read-only
        else:
            class TCPServer(ThreadingMixIn, HTTPServer):
                daemon_threads = True
            self.server = TCPServer(address, Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def _reply(self, handler, status, reason):
        data = json.dumps({"error": {"message": reason, "type": "topogym_usage_error"}}).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(data)
        handler.close_connection = True

    def handle(self, handler):
        identifier, connection, responded = None, None, False
        handler.connection.settimeout(self.timeout)
        try:
            credential = handler.headers.get("Authorization", "").removeprefix("Bearer ")
            credential = handler.headers.get("x-api-key", credential)
            if not hmac.compare_digest(credential, self.token):
                self._reply(handler, 401, "Invalid trial credential")
                return
            if self.closing.is_set() or self.service.stopped.is_set() or self.service.ledger.snapshot()["closed"]:
                self._reply(handler, 409, "Trial budget is closed")
                return
            route = self.provider_protocol.request_path(handler.path)
            if handler.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked request bodies are unsupported")
            size = int(handler.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError("Invalid model request size")
            raw = handler.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request body")
            body = json.loads(raw)
            if self.model is not None and (not isinstance(body, dict) or body.get("model") != self.model):
                self.service.fail("usage_unavailable")
                self._reply(handler, 400, "Request model differs from the frozen trial model")
                return
            prepared = self.provider_protocol.prepare_request(handler.path, body,
                self.service.ledger.snapshot()["remaining"]["output_tokens"],
                default_output_cap=self.default_output_cap)
            source = self.provider_protocol.new_receipt_source(uuid4().hex)
            self.service.ledger.admit(source.request_id, source=source.name, output_bound=prepared.output_bound,
                input_bound=prepared.input_bound, model=body["model"], route_id=self.route_id)
            identifier = source.request_id
            connection_type = http.client.HTTPSConnection if self.upstream.scheme == "https" else http.client.HTTPConnection
            connection = connection_type(self.upstream.hostname, self.upstream.port, timeout=self.timeout)
            with self.lock:
                self.connections[connection] = None
            self.service.ledger.mark_sent(identifier)
            connection.connect()
            with self.lock:
                self.connections[connection] = connection.sock
            if self.closing.is_set() or self.service.stopped.is_set():
                raise RuntimeError("Gateway closed before upstream send")
            data = json.dumps(body).encode()
            headers = self.provider_protocol.build_headers(self.api_key, handler.headers)
            connection.request("POST", self.upstream.path.rstrip("/") + route, data, headers)
            response = connection.getresponse()
            source.receipt_details["upstream_request_id"] = response.getheader("x-request-id") or response.getheader("request-id")
            if response.status != 200:
                self.service.fail("usage_incomplete", request_id=identifier)
                self._reply(handler, 502, f"Provider returned HTTP {response.status}; usage is unconfirmed")
                return
            is_stream = "text/event-stream" in response.getheader("Content-Type", "")
            if is_stream:
                handler.send_response(200)
                handler.send_header("Content-Type", "text/event-stream")
                handler.send_header("Connection", "close")
                handler.end_headers()
                responded = True
                event_lines, event_size = [], 0
                while True:
                    line = response.readline(MAX_BODY + 1)
                    if not line:
                        break
                    event_size += len(line)
                    if event_size > MAX_BODY:
                        raise ValueError("Oversized SSE event")
                    event_lines.append(line)
                    if line in {b"\n", b"\r\n"}:
                        payload = b"\n".join(part[5:].strip() for part in event_lines if part.startswith(b"data:"))
                        if payload and payload != b"[DONE]":
                            event = source.feed(json.loads(payload))
                            if event is not None:
                                self.service.record(event)
                        handler.wfile.write(b"".join(event_lines))
                        handler.wfile.flush()
                        event_lines, event_size = [], 0
                        if self.service.stopped.is_set():
                            break
                if not source.done:
                    self.service.fail("usage_incomplete", request_id=identifier)
            else:
                data = response.read(MAX_BODY + 1)
                if len(data) > MAX_BODY:
                    raise ValueError("Oversized provider response")
                event = source.feed(json.loads(data), streaming=False)
                self.service.record(event)
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(data)))
                handler.send_header("Connection", "close")
                handler.end_headers()
                responded = True
                handler.wfile.write(data)
        except CapacityUnavailable:
            self._reply(handler, 429, "Budget is reserved by in-flight requests; retry after settlement")
        except BudgetStopped:
            if identifier:
                try:
                    self.service.ledger.release_unsent(identifier)
                except ValueError:
                    pass
            self.service.notify_stop()
            self._reply(handler, 409, "Trial budget exhausted")
        except Exception:
            self.service.fail("usage_incomplete" if identifier else "usage_unavailable", request_id=identifier)
            if not responded:
                try:
                    self._reply(handler, 502, "Model usage could not be verified")
                except OSError:
                    pass
        finally:
            handler.close_connection = True
            if connection is not None:
                with self.lock:
                    self.connections.pop(connection, None)
                connection.close()

    def cancel(self):
        self.closing.set()
        with self.lock:
            for connection, transport in list(self.connections.items()):
                # HTTPConnection drops .sock after a Connection: close response;
                # its HTTPResponse still owns the same transport while reading.
                if transport:
                    try:
                        transport.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                connection.close()

    def close(self):
        self.cancel()
        self.server.shutdown()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.lock:
                if not self.connections:
                    break
            time.sleep(.01)
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.socket_path:
            self.socket_path.unlink(missing_ok=True)
