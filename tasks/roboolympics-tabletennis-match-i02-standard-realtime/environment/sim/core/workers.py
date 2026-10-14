"""Worker processes for slow per-seat work outside the world lock (rendering, planning): one process per (kind, seat),
one request in flight. The sport answers Sport.worker_init(kind, seat, cfg) and Sport.worker_call(obj, kind, job);
the kind "camera" is the core's own: the sport's camera definitions drawn by the task's renderer (core/observe.py)."""
from __future__ import annotations

import json
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time


def _send(f, obj):
    b = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    f.write(struct.pack("<Q", len(b)) + b)
    f.flush()


def _read(f, n, deadline):
    buf = b""
    fd = f.fileno()
    while len(buf) < n:
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                raise TimeoutError("worker timed out")
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError("worker closed")
        buf += chunk
    return buf


def _recv(f, deadline=None):
    (n,) = struct.unpack("<Q", _read(f, 8, deadline))
    return pickle.loads(_read(f, n, deadline))


def affinity(name: str):
    """Pin this process to the CPUs in environment variable `name` (e.g. "4-7,9"), if set."""
    v = os.environ.get(name, "")
    if v:
        cpus = set()
        for part in v.split(","):
            a = part.split("-")
            cpus.update(range(int(a[0]), int(a[-1]) + 1))
        os.sched_setaffinity(0, cpus)


class ProcessWorker:
    def __init__(self, plugin: str, kind: str, seat: str, cfg: dict, timeout: float = 30.0):
        self.timeout, self.lock = timeout, threading.Lock()
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.proc = subprocess.Popen([sys.executable, "-m", "core.workers", plugin, kind, seat, json.dumps(cfg)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=root)
        if _recv(self.proc.stdout, time.monotonic() + 120) != "ready":
            self.close()
            raise RuntimeError("worker startup failed")

    def call(self, job, wait: bool = False):
        """One job; a second one in flight is refused (BlockingIOError) unless `wait` (then it queues)."""
        if not self.lock.acquire(blocking=wait):
            raise BlockingIOError("one request per seat and worker may be in flight")
        try:
            _send(self.proc.stdin, job)
            ok, value = _recv(self.proc.stdout, time.monotonic() + self.timeout)
            if not ok:
                raise RuntimeError(value)
            return value
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def main(plugin, kind, seat, cfg_json):
    from .episode import load_plugin
    from .sport import MatchConfig
    affinity(f"RO_{kind.upper()}_{seat}_CPUS")
    sport = load_plugin(plugin)
    cfg = MatchConfig.from_json(json.loads(cfg_json))
    if kind == "camera":
        from .observe import CameraWorker, players_scene
        obj = CameraWorker(players_scene(sport, plugin, cfg), cfg.renderer)
        call = lambda o, k, job: o.draw_job(job)  # noqa: E731  (observation or reply images)
    else:
        obj = sport.worker_init(kind, seat, cfg)
        call = sport.worker_call
    out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)                                   # stray prints of the simulator go to stderr
    sys.stdout = sys.stderr
    _send(out, "ready")
    while True:
        try:
            job = _recv(sys.stdin.buffer)
        except EOFError:
            return
        t0 = time.monotonic()
        try:
            res = call(obj, kind, job)
            res["worker_s"] = time.monotonic() - t0
            _send(out, (True, res))
        except Exception as exc:  # noqa: BLE001
            _send(out, (False, repr(exc)))


if __name__ == "__main__":
    main(*sys.argv[1:])
