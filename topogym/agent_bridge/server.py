"""Loopback HTTP transport and browser console. Genesis stays on one thread."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

from .session import Session


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, factory, output, **options):
        if address[0] != "127.0.0.1":
            raise ValueError("The local bridge only binds 127.0.0.1")
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="genesis-owner")
        try:
            self.session = self.worker.submit(Session, factory, output, **options).result()
            super().__init__(address, Handler)
        except BaseException:
            self.worker.shutdown()
            if hasattr(self, "session"):
                self.session.finish("Server initialization failed; simulator cannot be resumed")
            raise

    def server_close(self):
        self.worker.shutdown(wait=True)
        self.session.finish("Server stopped; live simulator cannot be resumed")
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_data(self, data, content_type="application/json", status=200):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def local_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed:
            raise ValueError("Invalid Host")
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://"+h for h in allowed}:
            raise ValueError("Cross-origin requests are disabled")

    def do_GET(self):
        try:
            self.local_request()
            path = urlsplit(self.path).path
            session = self.server.session
            if path == "/":
                self.send_data(Path(__file__).with_name("dashboard.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/v1/session":
                self.send_data(session.snapshot())
            elif path == "/v1/prompt":
                self.send_data(dict(prompt=session.prompt()))
            elif path.startswith("/artifacts/"):
                target = session.artifact(unquote(path[len("/artifacts/"):]))
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(target.stat().st_size))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with target.open("rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            else:
                self.send_data({"error": "Unknown endpoint"}, status=404)
        except (ValueError, OSError) as exc:
            self.send_data({"error": str(exc)}, status=400)

    def do_POST(self):
        try:
            self.local_request()
            if self.headers.get("X-TopoGym") != "1" or self.headers.get_content_type() != "application/json":
                raise ValueError("POST requires application/json and X-TopoGym: 1")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2_000_000:
                raise ValueError("JSON request must contain 1..2000000 bytes")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            path = urlsplit(self.path).path
            session = self.server.session
            if path == "/v1/segments":
                result = self.server.worker.submit(session.submit, **payload).result()
            elif path.startswith("/v1/usage/"):
                result = session.usage(path.rsplit("/", 1)[-1], **payload)
            elif path == "/v1/finish":
                result = session.finish(**payload)
            else:
                self.send_data({"error": "Unknown endpoint"}, status=404)
                return
            self.send_data(result)
        except (ValueError, TypeError, KeyError) as exc:
            self.send_data({"error": str(exc)}, status=409)
        except Exception as exc:
            self.send_data({"error": f"Server error: {type(exc).__name__}: {exc}"}, status=500)
