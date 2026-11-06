"""Camera rendering in its own PROCESS for the wall-clock server.

MuJoCo's render call holds the Python GIL (measured: up to 50 ms stalls of a 10 ms pacing loop when rendering in a
thread), so the observe images are drawn in a separate process: it owns its own model copy, MjData, OpenGL (osmesa)
context and renderer, receives camera-frame snapshots (qpos, time stamp, opponent x) and returns the PNG.
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
    if n > 64 * 1024 * 1024:
        raise ValueError("oversized worker packet")
    return pickle.loads(_read_exact(f, n, deadline))


class _Conn:
    def __init__(self, fin, fout):
        self.fin, self.fout = fin, fout

    def send(self, obj, deadline=None):
        _send(self.fout, obj, deadline)

    def recv(self, deadline=None):
        return _recv(self.fin, deadline)


