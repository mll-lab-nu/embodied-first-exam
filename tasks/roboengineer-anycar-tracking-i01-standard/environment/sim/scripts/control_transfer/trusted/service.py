"""Private policy service: bounded HTTP, no filesystem API, trusted signal finalization."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, os, signal, threading, time
from pathlib import Path
from .session import Session

PROTOCOL = "eai-policy/1.1"
OPERATIONS = ("describe", "deploy", "seal", "result")


def parse(raw):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("Duplicate JSON key")
            d[k] = v
        return d

    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))


class Runtime:
    def __init__(self, root, instance, wall):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.cutoff = None
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "server.pid").write_text(str(os.getpid()))
        spec = json.loads(Path(instance).read_text())
        if spec.get("private_asset"):
            import hashlib

            if hashlib.sha256(Path(spec["private_asset"]).read_bytes()).hexdigest() != spec["private_asset_sha256"]:
                raise ValueError("Private asset mismatch")
        self.session = Session(root, spec, wall)
        if (root / "cutoff.json").exists():
            self.cutoff = self.session.close()
            self.stop.set()
        signal.signal(signal.SIGUSR1, lambda *_: self.request_finalize())

    def request_finalize(self):
        # From the signal (or the service's own deadline) on, nothing runs the simulator for the agent (PROTOCOL H.4):
        # the cutoff is persisted, a deployment's running episode worker is killed (its round cannot count), and an
        # error here never takes the service (PID 1) down before it has written final.json.
        try:
            if self.cutoff is None:
                self.cutoff = self.session.close()
        except Exception:
            self.cutoff = self.cutoff or time.time()
        finally:
            self.stop.set()
            self.session.stop_worker()

    def call(self, op, args):
        if not self.lock.acquire(blocking=False):
            return {"error": "Evaluator busy"}
        try:
            if self.stop.is_set() or (self.session.root / "final.json").exists():
                return {"error": "Session closed"}
            return self.session.call(op, args)
        finally:
            self.lock.release()

    def watch(self):
        while not self.stop.wait(0.5):
            deadline = self.session.state["deadline"]
            if deadline and time.time() > deadline:
                self.request_finalize()
        try:
            with self.lock:
                final = self.session.finalize(self.cutoff)
            if not (self.session.root / "video.json").exists():
                self.session.render_video(final)   # after the verdict, never part of it (PROTOCOL §4)
        except Exception as error:   # no final.json: the collect hook times out and the trial is infrastructure
            self.session.audit({"operation": "watch", "status": "crashed", "error": type(error).__name__})


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
                self.reply(200, {"protocol": PROTOCOL, "task_type": "policy", "operations": list(OPERATIONS)})
            else:
                runtime.session.audit({"operation": "http", "path": self.path[:256], "outcome": "rejected"})
                self.reply(404, {"error": "Unknown route"})

        def unknown(self):
            runtime.session.audit({"operation": "http", "path": self.path[:256], "outcome": "rejected"})
            self.reply(404, {"error": "Unknown route"})

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = unknown   # every non-protocol path is 404 (PROTOCOL H.3)

        def do_POST(self):
            if self.path not in tuple("/" + o for o in OPERATIONS):
                return self.unknown()
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < size <= 12 * 1024**2:
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
        os.environ.get("RCB_DATA", "/data"), os.environ["RCB_INSTANCE"], int(os.environ["RCB_WALL_CLOCK_S"])
    )
    threading.Thread(target=runtime.watch, daemon=True).start()
    BoundedServer(("0.0.0.0", int(os.environ.get("RCB_PORT", "8000"))), handler(runtime)).serve_forever()


if __name__ == "__main__":
    main()
