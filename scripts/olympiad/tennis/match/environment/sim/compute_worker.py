"""Heavy computations of the wall-clock tennis service in their own PROCESSES, off the sim thread and the GIL.

  plan  the stroke plan of an `act` (tn.PlanCtx.plan_act): from the robot snapshot of the step the act was accepted
        (k_s), for its effect step k_e = k_s + lead. The planner's IK, swing search and rehearsals take ~0.15-0.26 s of
        CPU; inside the sim lock they would stall the world for 15-26 control steps at x1 (2-3 at x10).
  opp   the scripted opponent's return search (tn.opp_spec), started when the opponent reacts to our shot and
        cached for its hit step (~0.05-0.11 s of CPU per return; the lock-step engine ran it inside the hit step).

Both are pure functions of their inputs, and the live engine / the replay use the same code (tn.py), so results are
bit-identical whether they come from here or are computed in-process (the replay, a cache miss).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from render_worker import _Conn

HERE = os.path.dirname(os.path.abspath(__file__))


def _loop(conn):
    import tn
    ctx = tn.PlanCtx()
    conn.send("ready")
    while True:
        try:
            req = conn.recv()
        except EOFError:
            return
        t0 = time.perf_counter()
        try:
            if req[0] == "plan":
                _, snap, lead, dec = req
                out = ctx.plan_act(snap, lead, dec["t"], dec["pos"], dec["normal"], dec["vel"], dec.get("base"))
            elif req[0] == "opp":
                out = tn.opp_spec(*req[1:])
            else:
                raise ValueError(f"unknown request {req[0]!r}")
            conn.send(("ok", out, time.perf_counter() - t0))
        except Exception as exc:  # noqa: BLE001
            conn.send(("error", repr(exc), time.perf_counter() - t0))


class ComputeProcess:
    """One worker process; requests are served one at a time (the caller runs call() in its own thread)."""

    def __init__(self, name: str):
        self.name = name
        self.timeout_s = float(os.environ.get("RCB_COMPUTE_TIMEOUT_S", "30"))
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, cwd=HERE, env=dict(os.environ))
        self.conn = _Conn(self.proc.stdout, self.proc.stdin)
        self.lock = threading.Lock()
        self.ready = False

    def warm(self) -> None:
        with self.lock:
            self._handshake(time.monotonic() + 120)

    def _handshake(self, deadline) -> None:
        if not self.ready:
            if self.conn.recv(deadline) != "ready":
                raise RuntimeError(f"invalid {self.name} worker handshake")
            self.ready = True

    def call(self, req):
        """(result, worker CPU seconds); raises on a worker error or timeout."""
        deadline = time.monotonic() + self.timeout_s
        if not self.lock.acquire(timeout=self.timeout_s):
            raise TimeoutError(f"{self.name} worker queue timed out")
        try:
            self._handshake(deadline)
            self.conn.send(req, deadline)
            st, out, cpu = self.conn.recv(deadline)
            if st != "ok":
                raise RuntimeError(f"{self.name} worker: {out}")
            return out, cpu
        except Exception:
            self.proc.terminate()
            raise
        finally:
            self.lock.release()


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    proto_out = os.fdopen(os.dup(1), "wb")      # the protocol keeps the real stdout; anything printed goes to stderr
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    _loop(_Conn(sys.stdin.buffer, proto_out))
