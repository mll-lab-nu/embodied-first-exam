"""The formal match's seat A: the program in a process of its own, run as another user (`nobody`), one JSON message per
view and per answer over two pipes (4-byte length + JSON). An answer later than the call limit is no command at that
step and is dropped when it comes; a program that dies, or breaks the protocol, sends no command for the rest of the
match (its own 0, never a retry)."""
from __future__ import annotations

import json
import os
import select
import struct
import subprocess
import time

MAX_MSG = 1 << 20                 # one answer: at most 1 MiB


def send(f, obj) -> None:
    b = json.dumps(obj, separators=(",", ":"), default=float).encode()
    f.write(struct.pack(">I", len(b)) + b)
    f.flush()


def read_exact(fd: int, n: int, deadline: float | None) -> bytes | None:
    out = b""
    while len(out) < n:
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                return None
        chunk = os.read(fd, n - len(out))
        if not chunk:
            raise EOFError("the program's process closed its pipe")
        out += chunk
    return out


class Isolated:
    def __init__(self, argv: list[str], config: dict, start_limit_s: float = 300.0, env: dict | None = None,
                 cwd: str | None = None):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(os.devnull, "wb"),
                                  env=env, cwd=cwd, start_new_session=True)
        self.out, self.fd = self.p.stdin, self.p.stdout.fileno()
        self.seq, self.failed, self.why, self.buf = 0, False, None, b""
        self.stale = 0
        try:
            send(self.out, {"config": config})
            r = self._recv(time.monotonic() + start_limit_s)
            if r is None or not r.get("ready"):
                self._fail("make_policy: " + ("no answer in time" if r is None else str(r.get("error"))[:300]))
        except Exception as exc:  # noqa: BLE001
            self._fail(f"start: {type(exc).__name__}: {exc}"[:300])
        self.limit = None

    def _fail(self, why: str) -> None:
        self.failed, self.why = True, self.why or why

    def _recv(self, deadline: float | None):
        h = read_exact(self.fd, 4, deadline)
        if h is None:
            return None
        n = struct.unpack(">I", h)[0]
        if n > MAX_MSG:
            raise ValueError(f"an answer of {n} bytes")
        b = read_exact(self.fd, n, None if deadline is None else max(deadline, time.monotonic() + 1.0))
        if b is None:
            raise ValueError("a truncated answer")
        return json.loads(b)

    def act(self, view):
        if self.failed:
            return None
        self.seq += 1
        deadline = time.monotonic() + (self.limit or 0.5)
        try:
            send(self.out, {"seq": self.seq, "view": view})
            while True:
                r = self._recv(deadline)
                if r is None:
                    return None                       # late: no command at this step (its answer is dropped later)
                if r.get("seq") != self.seq:
                    self.stale += 1
                    continue
                if r.get("error"):
                    raise RuntimeError(str(r["error"])[:300])
                return r.get("action")
        except (OSError, EOFError, ValueError, TypeError) as exc:
            self._fail(f"{type(exc).__name__}: {exc}"[:300])
            return None
        except RuntimeError:
            raise                                     # the program's own exception: this step's error

    def close(self, grace_s: float = 2.0) -> None:
        try:
            self.out.close()
        except OSError:
            pass
        try:
            self.p.wait(grace_s)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(self.p.pid, 9)
        except OSError:
            pass
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            pass
