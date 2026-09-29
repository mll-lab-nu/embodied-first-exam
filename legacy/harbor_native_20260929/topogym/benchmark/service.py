"""Single-owner HTTP projection. Only actions, observations and robot queries."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import signal
import traceback

from . import wire
from .client import EpisodeOver
from .evidence import write_json


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            pass

        def reply(self, status, value, binary=False):
            data = value if binary else json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/x-rcb1" if binary else "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/spec":
                self.reply(200, session.spec)
            elif self.path == "/status":
                self.reply(200, session.status())
            else:
                self.reply(404, dict(error="Unknown endpoint"))

        def do_POST(self):
            if self.path not in {"/observe", "/submit", "/kinematics"}:
                self.reply(404, dict(error="Unknown endpoint"))
                return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
                    raise ValueError("One Content-Length required; chunked requests are unsupported")
                length = int(lengths[0])
                if length > wire.MAX_REQUEST:
                    self.reply(413, dict(error="Request too large"))
                    return
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError("Truncated body")
                binary = data.startswith(b"RCB1")
                meta, parts = wire.decode(data, limit=wire.MAX_REQUEST) if binary else (wire.json_loads(data), {})
                if self.path == "/kinematics":
                    if binary or not isinstance(meta, dict):
                        raise ValueError("kinematics requires JSON")
                    self.reply(200, session.kinematics(meta))
                else:
                    if self.path == "/submit" and not binary:
                        raise ValueError("submit requires RCB1")
                    result = session.execute(meta, parts, submit=self.path == "/submit")
                    self.reply(200, result, binary=True)
            except EpisodeOver as exc:
                self.reply(409, dict(error=str(exc)))
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
                if session.reason == "error":
                    self.reply(500, dict(error="Simulator failed; episode ended"))
                else:
                    self.reply(400, dict(error=str(exc)))
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                # A disconnect does not undo a completed action or permit retry.
                return
            except Exception:
                session.done, session.reason = True, "error"
                traceback.print_exc()
                self.reply(500, dict(error="Simulator failed; episode ended"))
    return Handler


def serve(instance, output, host="0.0.0.0", port=8000):
    from .session import Session
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    stopped = False
    session = None
    def stop(*_):
        nonlocal stopped
        stopped = True
        if session is not None:
            session.done = True
            if session.reason is None:
                session.reason = "timeout"
    signal.signal(signal.SIGUSR1, stop)
    signal.signal(signal.SIGTERM, stop)
    with Session(instance, output=output / "live") as session:
        # The socket opens only after all scene construction and calibration.
        with HTTPServer((host, port), handler_for(session)) as server:
            server.timeout = .5
            write_json(output / "ready.json", dict(ready=True, port=server.server_port))
            while not stopped:
                server.handle_request()
                if session.status()["reason"] == "timeout":
                    stopped = True
        session.save(output / "trajectory.npz")
        write_json(output / "live.json", session.verdict())
