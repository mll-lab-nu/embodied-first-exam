"""Container loopback HTTP transport to a host Unix socket; no credentials here."""
import argparse
import json
import http.client
import os
from pathlib import Path
import selectors
import socket
import socketserver
import threading
import time
from uuid import uuid4

from .store import atomic_json


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, *, timeout=1):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def watch_budget(path, token, output, shutdown, *, interval=.1, on_failure=None):
    """Root publishes live counts; host disappearance cancels local work as well."""
    last, failed_since = None, None
    while not shutdown.is_set():
        connection = UnixConnection(path, timeout=.5)
        try:
            connection.request("GET", "/budget", headers={"Authorization": "Bearer " + token})
            response = connection.getresponse()
            if response.status != 200:
                raise OSError("Usage heartbeat failed")
            last = json.loads(response.read())
            last["published_at"] = time.time()
            atomic_json(output, last, mode=0o644)
            failed_since = None
            if last["closed"]:
                return
        except Exception:
            failed_since = failed_since or time.monotonic()
            if time.monotonic() - failed_since >= 1:
                # The manager may have published final state just before closing.
                try:
                    if json.loads(Path(output).read_text()).get("closed"):
                        return
                except (OSError, ValueError):
                    pass
                if on_failure:
                    on_failure(last)
                return
        finally:
            connection.close()
        shutdown.wait(interval)


def emergency_stop(last):
    from topogym.agents.rollout.client import call
    import pwd
    import signal
    snapshot = dict(last or {}, mode="observed", closed=True, budget_qualified=False,
                    usage_complete=False, failure_reason="usage_unavailable")
    snapshot["stop"] = snapshot.get("stop") or dict(stop_id=uuid4().hex, reason="usage_unavailable",
        dimensions=[], decision_at=time.time(), decision_monotonic_ns=time.monotonic_ns())
    atomic_json("/trial/rollout/usage_final.json", snapshot)
    try:
        call({"operation": "budget_stop", "snapshot": snapshot}, "/run/topogym/admin.sock")
    finally:
        # No provider credentials or host authority needed to stop local compute.
        uids = {pwd.getpwnam(name).pw_uid for name in ("agent", "policy")}
        for item in Path("/proc").iterdir():
            if item.name.isdigit():
                try:
                    fields = dict(line.split(":", 1) for line in (item / "status").read_text().splitlines())
                    if uids.intersection(map(int, fields["Uid"].split())):
                        os.kill(int(item.name), signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError):
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--token")
    parser.add_argument("--budget-file")
    args = parser.parse_args()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.socket(socket.AF_UNIX) as upstream, selectors.DefaultSelector() as selector:
                upstream.connect(args.socket)
                selector.register(self.request, selectors.EVENT_READ, upstream)
                selector.register(upstream, selectors.EVENT_READ, self.request)
                while True:
                    for key, _ in selector.select():
                        data = key.fileobj.recv(65536)
                        if not data:
                            return
                        key.data.sendall(data)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with Server(("127.0.0.1", 0), Handler) as server:
        Path(args.ready).write_text(json.dumps({"port": server.server_address[1]}))
        if args.budget_file:
            if not args.token:
                parser.error("Budget publisher requires trial token")
            thread = threading.Thread(target=watch_budget, args=(args.socket, args.token,
                args.budget_file, threading.Event()), kwargs={"on_failure": emergency_stop}, daemon=True)
            thread.start()
        server.serve_forever()


if __name__ == "__main__":
    main()
