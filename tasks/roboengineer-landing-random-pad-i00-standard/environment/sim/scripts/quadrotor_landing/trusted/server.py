"""Prototype deployment service. Not an eai-standard endpoint or a Harbor-native task yet."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from .session import Session


def parse(raw):
    def unique(pairs):
        value = {}
        for k, v in pairs:
            if k in value:
                raise ValueError("Duplicate key")
            value[k] = v
        return value

    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def handler(session):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= 8192 or self.path not in ("/describe", "/deploy", "/seal"):
                    raise ValueError()
                arguments = parse(self.rfile.read(n))
                answer = session.call(self.path[1:], arguments)
                code = 400 if "error" in answer else 200
            except (ValueError, TypeError, json.JSONDecodeError):
                session.audit({"operation": "http", "outcome": "rejected"})
                code, answer = 400, {"error": "Request rejected"}
            except Exception:
                code, answer = 503, {"error": "Evaluator unavailable"}
            body = json.dumps(answer, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.send_error(404)

        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

    return Handler


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--residual", type=Path, required=True)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--bind", default="127.0.0.1")
    a = p.parse_args()
    s = Session(a.root, a.residual)
    HTTPServer((a.bind, a.port), handler(s)).serve_forever()
