"""Harbor policy service: private simulator, serialized deployment, trusted finalization."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import threading
import time

from .verify import digest


def parse(raw):
    def unique(pairs):
        value = {}
        for key, val in pairs:
            if key in value:
                raise ValueError("Duplicate key")
            value[key] = val
        return value

    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


PROTOCOL = "eai-policy/1.0"


def atomic_json(path, value):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(value, allow_nan=False, sort_keys=True))
    temporary.replace(path)


def select_submission(state, cutoff):
    """Only completed-before-cutoff candidates count; explicit seals are immutable."""
    eligible = [
        r for r in state["rounds"] if r["status"] == "completed" and r.get("completed_at", float("inf")) <= cutoff
    ]
    if state["sealed"]:
        return next((r for r in eligible if r["id"] == state.get("selected")), None)
    return eligible[-1] if eligible else None


class Runtime:
    def __init__(self, root, instance, residual, wall_clock_s):
        from ..trusted.session import Session
        from ..trusted.grade import grade, render_held_out

        self.evaluate = grade
        self.render_video = render_held_out
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.instance = json.loads(Path(instance).read_text())
        self.instance_sha = hashlib.sha256(Path(instance).read_bytes()).hexdigest()
        self.residual = Path(residual)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.cutoff = None
        self.wall_clock_s = wall_clock_s
        # the cutoff outlives a restart of the service: from the signal on, nothing runs the simulator for the agent
        self.cutoff_path = self.root / "cutoff.json"
        if self.cutoff_path.exists():
            self.cutoff = json.loads(self.cutoff_path.read_text())["cutoff"]
            self.stop.set()
        # Register before the expensive oracle preparation: collection must also terminate a nop run.
        signal.signal(signal.SIGUSR1, lambda *_: self.request_finalize())
        (self.root / "server.pid").write_text(str(os.getpid()))
        if hashlib.sha256(self.residual.read_bytes()).hexdigest() != self.instance["residual_sha256"]:
            raise ValueError("Evaluator asset differs from frozen instance")
        self.session = Session(
            self.root / "session", self.residual, bank=self.instance["bank"], wall_clock_s=wall_clock_s
        )
        if self.session.state["bank"] != self.instance["bank"]:
            raise ValueError("Recovered instance mismatch")
        if "native_started_at" not in self.session.state:
            self.session.state["native_started_at"] = None
            self.session.persist()

    def request_finalize(self):
        # Signal-safe: no lock acquisition, simulation, or filesystem work here.
        if self.cutoff is None:
            self.cutoff = time.time()
        self.stop.set()
        session = getattr(self, "session", None)
        if session is not None:
            session.stopping = True   # a deployment in progress runs no further case

    def call(self, operation, arguments):
        # A bounded HTTP worker pool plus one deployment lock; no concurrent simulator calls.
        if not self.lock.acquire(blocking=False):
            return {"error": "Evaluator busy"}
        try:
            if self.stop.is_set() or self.cutoff_path.exists() or (self.root / "final.json").exists():
                return {"error": "Session closed"}
            state = self.session.state
            if state["native_started_at"] is None:
                state["native_started_at"] = time.time()
                state["deadline"] = state["native_started_at"] + self.wall_clock_s
                self.session.persist()
            return self.session.call(operation, arguments)
        finally:
            self.lock.release()

    def finalize(self):
        with self.lock:
            if (self.root / "final.json").exists():
                return
            state = self.session.state
            cutoff = min(self.cutoff or time.time(), state["deadline"])
            final = {
                "schema": "landing-final/1",
                "protocol": PROTOCOL,
                "instance_sha256": self.instance_sha,
                "finalized": True,
                "infra_error": False,
                "no_submission": False,
                "success": False,
                "graded_by": "live",   # the sidecar's own held-out evaluation of the sealed policy (no replay of actions)
                "video_source": "render",   # replay.mp4: a rendered run after the verdict (video.json)
                "grade_sha256": None,
            }
            try:
                if state["infrastructure_error"]:
                    raise RuntimeError("Deployment infrastructure failure")
                chosen = select_submission(state, cutoff)
                if chosen is None:
                    final["no_submission"] = True
                else:
                    state.update(sealed=True, selected=chosen["id"])
                    self.session.persist()
                    self.session.audit({"operation": "trusted_finalize", "selected": chosen["id"], "cutoff": cutoff})
                    report = self.evaluate(self.session.root, self.residual)
                    final["grade_sha256"] = digest(report)
                    final["success"] = report["successes"] == len(report["episodes"])
            except Exception as error:
                final["infra_error"] = True
                # Trusted artifact only; no traceback or privileged diagnostics on the public socket.
                final["error"] = type(error).__name__
            atomic_json(self.root / "final.json", final)

    def watch(self):
        while not self.stop.wait(0.25):
            state = self.session.state
            if state["native_started_at"] is not None and time.time() >= state["deadline"]:
                self.request_finalize()
        try:
            if not self.cutoff_path.exists():
                atomic_json(self.cutoff_path, {"cutoff": self.cutoff or time.time()})
            self.finalize()
        except Exception as error:   # never leave the collect hook without a verdict to wait for
            if not (self.root / "final.json").exists():
                atomic_json(self.root / "final.json", {"schema": "landing-final/1", "protocol": PROTOCOL,
                                                       "instance_sha256": self.instance_sha, "finalized": True,
                                                       "infra_error": True, "no_submission": False, "success": False,
                                                       "graded_by": "live", "grade_sha256": None,
                                                       "error": type(error).__name__})
        self.video()

    def video(self):
        """After the verdict (PROTOCOL §4): render the held-out evaluation to /data/replay.mp4; never part of it."""
        if (self.root / "video.json").exists():
            return
        status = {"video": None}
        try:
            final = json.loads((self.root / "final.json").read_text())
            if final.get("no_submission"):
                status["reason"] = "no_submission: no graded episode"
            if final.get("grade_sha256") and not final.get("infra_error"):
                out, matches = self.render_video(self.session.root, self.residual)
                status.update(video=out.name, matches_graded=matches)
        except Exception as error:
            status["error"] = type(error).__name__
        atomic_json(self.root / "video.json", {**status, "done": True})


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"ready": True})
            elif self.path == "/spec":
                self.reply(
                    200, {"protocol": PROTOCOL, "task_type": "policy", "operations": ["describe", "deploy", "seal"]}
                )
            else:
                runtime.session.audit({"operation": "http", "path": self.path[:256], "outcome": "rejected"})
                self.reply(404, {"error": "Unknown route"})

        def unknown(self):
            runtime.session.audit({"operation": "http", "path": self.path[:256], "outcome": "rejected"})
            self.reply(404, {"error": "Unknown route"})

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = unknown   # every non-protocol path is 404 (PROTOCOL H.3)

        def do_POST(self):
            if self.path not in ("/describe", "/deploy", "/seal"):
                return self.unknown()
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < size <= 8192:
                    raise ValueError("Invalid body")
                args = parse(self.rfile.read(size))
                result = runtime.call(self.path[1:], args)
                self.reply(400 if "error" in result else 200, result)
            except (ValueError, TypeError, json.JSONDecodeError):
                runtime.session.audit({"operation": "http", "path": self.path[:256], "outcome": "rejected"})
                self.reply(400, {"error": "Request rejected"})
            except Exception:
                self.reply(503, {"error": "Evaluator unavailable"})

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass

    return Handler


def main():
    runtime = Runtime(
        os.environ.get("RCB_DATA", "/data"),
        os.environ["RCB_INSTANCE"],
        os.environ.get("RCB_RESIDUAL", "/opt/landing/residual.npz"),
        int(os.environ["RCB_WALL_CLOCK_S"]),
    )
    threading.Thread(target=runtime.watch, daemon=True).start()
    BoundedServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), handler(runtime)).serve_forever()


if __name__ == "__main__":
    main()
