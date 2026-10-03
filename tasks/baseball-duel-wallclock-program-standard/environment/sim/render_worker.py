"""Camera rendering in its own PROCESS for the wall-clock baseball server.

MuJoCo's render call holds the Python GIL (table tennis measured up to 50 ms stalls of a 10 ms pacing loop when
rendering in a thread; the 8 baseball tiles take ~0.2 s on CPU/OSMesa), so the observe images are drawn in a separate
process: it owns its own scene, MjData, OpenGL (osmesa) context and renderer, receives the frames' display data (ball
centre, the executed swing's parameters, time since release; bbrt.RT.snapshots) and returns the PNG.
"""
from __future__ import annotations

import io
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _send(f, obj, deadline=None) -> None:
    b = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    packet = struct.pack("<Q", len(b)) + b
    if deadline is None:
        f.write(packet); f.flush()
        return
    offset = 0
    while offset < len(packet):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [f], [], remaining)[1]:
            raise TimeoutError("render worker request timed out")
        # At most PIPE_BUF bytes after writable readiness; never block on a large request.
        offset += os.write(f.fileno(), packet[offset:offset + 4096])


def _read_exact(f, n, deadline=None):
    chunks = []
    while n:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([f], [], [], remaining)[0]:
                raise TimeoutError("render worker response timed out")
        chunk = os.read(f.fileno(), min(n, 65536))
        if not chunk:
            raise EOFError("render worker closed its response pipe")
        chunks.append(chunk)
        n -= len(chunk)
    return b''.join(chunks)


def _recv(f, deadline=None):
    h = _read_exact(f, 8, deadline)
    n = struct.unpack("<Q", h)[0]
    return pickle.loads(_read_exact(f, n, deadline))


class _Conn:
    def __init__(self, fin, fout):
        self.fin, self.fout = fin, fout

    def send(self, obj, deadline=None):
        _send(self.fout, obj, deadline)

    def recv(self, deadline=None):
        return _recv(self.fin, deadline)


def _loop(conn):
    import bb
    import bbrt
    rd = bb.Renderer()                    # its own MuJoCo model, MjData and OpenGL context
    conn.send("ready")
    while True:
        try:
            snaps = conn.recv()
        except EOFError:
            return
        try:
            conn.send(("ok", bbrt.render_snaps(snaps, rd)))
        except Exception as exc:  # noqa: BLE001
            conn.send(("error", repr(exc)))


class RenderProcess:
    def __init__(self):
        self.timeout_s = float(os.environ.get("RCB_RENDER_TIMEOUT_S", "30"))
        if not np.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("RCB_RENDER_TIMEOUT_S must be positive and finite")
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, cwd=HERE, env=dict(os.environ))
        self.conn = _Conn(self.proc.stdout, self.proc.stdin)
        self.lock = threading.Lock()
        self.cache: dict = {}
        self.ready = False

    def render(self, snaps: list[dict]) -> bytes:
        key = tuple((s["pitch"], s["n"]) for s in snaps)
        deadline = time.monotonic() + self.timeout_s
        if not self.lock.acquire(timeout=self.timeout_s):
            raise TimeoutError("render worker queue timed out")
        try:
            if key in self.cache:
                return self.cache[key]
            if not self.ready:
                if self.conn.recv(deadline) != "ready":
                    raise RuntimeError("invalid render worker handshake")
                self.ready = True
            self.conn.send([dict(s) for s in snaps], deadline)
            st, out = self.conn.recv(deadline)
            if st != "ok":
                raise RuntimeError(out)
            self.cache = {key: out}
            return out
        except Exception:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            raise
        finally:
            self.lock.release()


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    proto_out = os.fdopen(os.dup(1), "wb")      # the protocol keeps the real stdout; anything printed goes to stderr
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    _loop(_Conn(sys.stdin.buffer, proto_out))
