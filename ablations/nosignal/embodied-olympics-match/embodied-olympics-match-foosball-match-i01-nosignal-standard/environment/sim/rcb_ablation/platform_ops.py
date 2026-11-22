"""Reset, save and load with platform seats (RCB_STATE_OPS; core/platform_seat.py, a core from 0.5.6 on): the
platform opponent's program runs in a process of its own, so its state is read and replaced there
(rcb_ablation/worker.py), in the order of its observations.

install() (before the match service is built):
- a platform seat's process runs `python -m rcb_ablation.worker` (core/workers.py main with the program wrapped);
- PlatformSeats' feeder answers a control request queued among the observations: it reaches the program after every
  observation sent before it;
- PlatformSeats' receiver keeps the replies it has taken in a box until it holds the world's lock, so a caller that
  holds the lock can receive them itself, in order (flush).

With the world's lock held (the world does not step, no observation is sent): save(ps) and restore(ps, blobs)."""
from __future__ import annotations

import collections
import queue as queue_mod
import subprocess
import threading

CONTROL_TIMEOUT_S = 120.0


class _Control:
    def __init__(self, body):
        self.body, self.done, self.res, self.err = body, threading.Event(), None, None


class _Subprocess:
    """core.workers' `subprocess`: a platform seat's worker runs rcb_ablation.worker, every other call unchanged."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def Popen(args, *a, **kw):
        args = list(args)
        if args[1:3] == ["-m", "core.workers"] and len(args) > 4 and args[4] == "platform":
            args[2] = "rcb_ablation.worker"
        return subprocess.Popen(args, *a, **kw)


def install():
    try:
        from core import platform_seat as P
        from core import workers as W
    except ImportError:
        return False
    if getattr(P.PlatformSeats, "abl_patched", False):
        return True
    W.subprocess = _Subprocess()
    P.PlatformSeats.abl_patched = True

    def feed(self, side):
        q = self.queues[side]
        while True:
            job = q.get()
            if job is None:
                return
            if isinstance(job, _Control):
                try:
                    job.res = self.workers[side].call(job.body, wait=True)
                except Exception as exc:  # noqa: BLE001
                    job.err = exc
                job.done.set()
                continue
            res = self._call(side, job)
            if res is None:
                self.replies[side].put(None)
                return
            self.replies[side].put((job, res))

    def recv(self, side):
        rq, box = self.replies[side], _box(self, side)
        while True:
            x = rq.get()
            with self.abl_mu:
                box.append(x)
                _drain(rq, box)
            with self.lock:
                stop = _receive(self, side)
            if stop:
                return

    P.PlatformSeats._loop, P.PlatformSeats._recv_loop = feed, recv
    return True


def _box(ps, side):
    if not hasattr(ps, "abl_mu"):
        ps.abl_mu = threading.Lock()
        ps.abl_box = {}
    return ps.abl_box.setdefault(side, collections.deque())


def _drain(rq, box):
    while True:
        try:
            box.append(rq.get_nowait())
        except queue_mod.Empty:
            return


def _receive(ps, side, drop=False) -> bool:
    """With the world's lock: the replies taken so far, received at the world's step now (dropped: drop). True when
    the feeder has stopped."""
    with ps.abl_mu:
        _drain(ps.replies[side], _box(ps, side))
        got = list(ps.abl_box[side])
        ps.abl_box[side].clear()
    stop = any(x is None for x in got)
    r = int(ps.now())
    for x in got:
        if x is None:
            continue
        job, res = x
        if drop or not ps.accept(job["unit"]):
            ps.stats[side]["dropped_replies"] += 1
            continue
        ps._received(side, job, res, r)
    return stop


def live(ps) -> list:
    return [s for s in (ps.sides if ps else []) if s not in ps.dead and s in ps.queues]


def request(ps, side, body, timeout=CONTROL_TIMEOUT_S):
    c = _Control(body)
    ps.queues[side].put(c)
    if not c.done.wait(timeout):
        raise TimeoutError(f"the platform program of side {side} did not answer {body.get('rcb_state')!r}")
    if c.err is not None:
        raise c.err
    return c.res


def save(ps) -> dict:
    """{side: {"blob", "sha", ...}}: each program's state after every observation sent so far; the replies to those
    observations are received now (at the world's current step), so nothing of the program is in transit."""
    out = {}
    for side in live(ps):
        out[side] = request(ps, side, {"rcb_state": "get"})
        _receive(ps, side)
    return out


def restore(ps, blobs: dict | None) -> dict:
    """Each program replaced: by its saved state (blobs: save()'s), or by a new program (None). The observations of
    the episode that ends here that are not yet sent are dropped, and every reply to them."""
    out = {}
    for side in live(ps):
        q = ps.queues[side]
        stop = False
        while True:
            try:
                job = q.get_nowait()
            except queue_mod.Empty:
                break
            stop = stop or job is None
        if stop:
            q.put(None)
            continue
        if blobs is None:
            out[side] = request(ps, side, {"rcb_state": "fresh"})
        else:
            out[side] = request(ps, side, {"rcb_state": "set", "blob": blobs[side]["blob"]})
        _receive(ps, side, drop=True)
    return out


__all__ = ["install", "save", "restore", "live"]
