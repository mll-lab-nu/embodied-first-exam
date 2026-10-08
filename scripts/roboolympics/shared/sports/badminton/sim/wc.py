"""Wall-clock helpers for the badminton match service: exact match snapshots, the stroke-planner process and the
reference advisor (oracle mode only).

Why a planner process. An `act` is planned by the stroke controller (`bm.Match.plan_racket`: deterministic multi-start
IK, up to three candidate solutions, five robot-only twin rehearsals each), 0.15-0.26 s of CPU. Done inside the sim
thread it would stall the world by up to 26 control steps at x1 and 2.6 at x10, beyond the 100 ms completion-lag
bound. So the service plans OUTSIDE the sim thread and its process, without changing what the plan is:

  * an act queued while the match is at step k_q takes effect at the fixed step k_e = k_q + LEAD_STEPS
    (LEAD_STEPS = ceil(PLAN_LEAD_S / wall seconds per step), a constant of the task);
  * at queue time the service pickles the whole match (an exact copy, MjData included; the MjModel is shared by
    reference) and sends it to the planner process; the planner advances the copy to k_e with the command in force
    (installing any earlier act that takes effect before k_e, from its own earlier result) and plans the stroke there,
    exactly as `Match.rt_act` at k_e would;
  * at k_e the sim thread compares the live state with the planner's state key at k_e and installs the plan (the
    same attribute changes as `rt_act`). The result is bit-identical to calling `rt_act` at k_e, which is what the
    fresh-process replay does. A key mismatch (never seen) falls back to `rt_act` in the sim thread and is counted
    (`plan_mismatch`). If the plan is not back by k_e the sim thread waits for it; the lateness is recorded.

Wire format: length-prefixed pickles over the worker's stdin/stdout (`_send` / `_recv`).
"""
from __future__ import annotations

import hashlib
import io
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "wallclock-4"                 # 4: the players serve (bm.Match.toss)
SOURCE_FILES = ("bm.py", "wc.py")


def source_sha() -> str:
    """Fingerprint of everything that decides the match (engine, planning/installation, scene)."""
    root = Path(HERE)
    h = hashlib.sha256()
    names = list(SOURCE_FILES) + [str(p.relative_to(root)) for p in sorted((root / "scene").rglob("*")) if p.is_file()]
    for name in names:
        h.update(name.encode()); h.update((root / name).read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------- pipes
def _send(f, obj, deadline=None) -> None:
    b = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    packet = struct.pack("<Q", len(b)) + b
    if deadline is None:
        view = memoryview(packet)
        while len(view):
            n = os.write(f.fileno(), view[:1 << 20])
            view = view[n:]
        return
    offset = 0
    while offset < len(packet):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [f], [], remaining)[1]:
            raise TimeoutError("worker request timed out")
        offset += os.write(f.fileno(), packet[offset:offset + 65536])


def _read_exact(f, n, deadline=None):
    chunks = []
    while n:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([f], [], [], remaining)[0]:
                raise TimeoutError("worker response timed out")
        chunk = os.read(f.fileno(), min(n, 1 << 20))
        if not chunk:
            raise EOFError("worker closed its pipe")
        chunks.append(chunk)
        n -= len(chunk)
    return b"".join(chunks)


def _recv(f, deadline=None):
    n = struct.unpack("<Q", _read_exact(f, 8, deadline))[0]
    return pickle.loads(_read_exact(f, n, deadline))


# ---------------------------------------------------------------------------------------------- snapshots
class _Pickler(pickle.Pickler):
    def persistent_id(self, obj):
        import mujoco as mj
        return "MODEL" if isinstance(obj, mj.MjModel) else None


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, model):
        super().__init__(f)
        self.model = model

    def persistent_load(self, pid):
        if pid != "MODEL":
            raise pickle.UnpicklingError(pid)
        return self.model


def snapshot(m) -> bytes:
    """Exact copy of the match state for planning. Not copied: the MjModel (shared by reference), the scratch twin, and
    the joint-target history except its last two entries (the planner reads only those, for the target velocity)."""
    tw = m.__dict__.pop("_twin", None)
    acts = m.s._actions
    m.s._actions = acts[-2:]
    try:
        f = io.BytesIO()
        _Pickler(f, protocol=pickle.HIGHEST_PROTOCOL).dump(m)
        return f.getvalue()
    finally:
        m._twin = tw
        m.s._actions = acts


def restore(b: bytes, model):
    m = _Unpickler(io.BytesIO(b), model).load()
    m._twin = None
    return m


def state_key(m) -> str:
    """Everything the stroke planner reads, hashed: physics state, command, leg and shot counters."""
    h = hashlib.sha256()
    h.update(m.s.state_sha().encode())
    h.update(repr((m.k, m.plan_j, len(m.plan), m.n_our_legs, len(m.points), len(m.legs), m.leg.get("launch"),
                   m.leg.get("state"), m.done)).encode())
    h.update(np.ascontiguousarray(m.s.target, dtype=np.float64).tobytes())
    if len(m.s._actions) >= 2:
        h.update(np.ascontiguousarray(m.s._actions[-2], dtype=np.float64).tobytes())
    qa = getattr(m, "_q_hit_active", None)
    if qa is not None:
        h.update(np.ascontiguousarray(qa, dtype=np.float64).tobytes())
    if m.plan_j < len(m.plan):
        h.update(np.ascontiguousarray(np.asarray(m.plan[m.plan_j:]), dtype=np.float64).tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------- plan / install
def plan_on(m, dec: dict) -> dict:
    """What `Match.rt_act` / `rt_clear` would do at the current step of m (a copy), as an installable result."""
    if dec["type"] == "none":
        return {"type": "none"}
    import bm
    T = float(dec["t"])
    t_hit = (m.k - m.leg["launch"]) * bm.CONTROL_DT + T
    ik_seed = getattr(m, "_q_hit_active", None) if m.plan_j < len(m.plan) else None
    m._ik_seed = ik_seed
    plan, info = m.plan_racket(t_hit, dec["pos"], dec["normal"], dec["vel"])
    q_hit = info.pop("_q_hit", None)
    info["T_from_now"] = round(T, 4)
    return {"type": "act", "plan": plan, "q_hit": q_hit, "info": info, "ik_seed": ik_seed,
            "swing_last": getattr(m, "_swing_last", None)}


def install(m, res: dict) -> dict | None:
    """Apply a planned result to m with exactly the attribute changes of `Match.rt_act` (or `rt_clear`)."""
    if res["type"] == "none":
        m.rt_clear()
        return None
    m._ik_seed = res["ik_seed"]
    if res["swing_last"] is not None:
        m._swing_last = res["swing_last"]
    info = res["info"]
    if res["plan"]:
        m.plan, m.plan_j = res["plan"], 0
        m._q_hit_active = res["q_hit"]
    m.shots.append({"k": m.k, "leg": m.n_our_legs, **info})
    m._last_act = info
    return info


def apply_inline(m, dec: dict) -> dict | None:
    """The reference semantics (also the replay's): plan and apply at the current step."""
    if dec["type"] == "none":
        m.rt_clear()
        return None
    return m.rt_act(dec["t"], dec["pos"], dec["normal"], dec["vel"])


# ---------------------------------------------------------------------------------------------- worker process
def _worker(conn_in, conn_out) -> None:
    import bm
    model = bm.Phys().m
    cache: dict = {}            # act_id -> (k_e, result), the planner's earlier results (for later forks)
    _send(conn_out, "ready")
    while True:
        try:
            job = _recv(conn_in)
        except EOFError:
            return
        t0 = time.monotonic()
        try:
            m = restore(job["snap"], model)
            t1 = time.monotonic()
            if job["op"] == "plan":
                k_e = int(job["k_e"])
                pend = [(cache[i][0], i) for i in job.get("pending", []) if i in cache]
                applied = set()
                status = "ok"
                while True:
                    for ke, i in pend:
                        if ke == m.k and i not in applied and cache[i][1] is not None:
                            install(m, cache[i][1]); applied.add(i)
                    if m.k >= k_e:
                        break
                    n0 = len(m.points)
                    m.rt_advance(1)
                    if len(m.points) > n0 or m.done:
                        status = "dropped"
                        break
                t2 = time.monotonic()
                out = {"act_id": job["act_id"], "status": status, "fork_steps": int(m.k - job["k_q"]),
                       "unpickle_ms": round((t1 - t0) * 1e3, 2), "fork_ms": round((t2 - t1) * 1e3, 2)}
                if status == "ok":
                    out["key"] = state_key(m)
                    res = plan_on(m, job["dec"])
                    out["res"] = res
                    cache[job["act_id"]] = (k_e, res)
                else:
                    cache[job["act_id"]] = (k_e, None)
                out["plan_ms"] = round((time.monotonic() - t2) * 1e3, 2)
                for i in sorted(cache)[:-64]:
                    cache.pop(i)
            elif job["op"] == "advise":
                import oracle_ref
                out = oracle_ref.advise(m)
                out["unpickle_ms"] = round((t1 - t0) * 1e3, 2)
                out["advice_ms"] = round((time.monotonic() - t1) * 1e3, 2)
            else:
                raise ValueError(f"unknown job {job.get('op')}")
            out["worker_ms"] = round((time.monotonic() - t0) * 1e3, 2)
            _send(conn_out, ("ok", out))
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            _send(conn_out, ("error", {"act_id": job.get("act_id"), "error": repr(exc)[:300]}))


class Worker:
    """A planner / advisor child process. `submit` is asynchronous (results arrive through `on_result` from a reader
    thread); `call` is synchronous (one request at a time)."""

    def __init__(self, name: str, on_result=None):
        self.name = name
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "worker"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, cwd=HERE, env=dict(os.environ))
        self.fin, self.fout = self.proc.stdout, self.proc.stdin
        if _recv(self.fin, time.monotonic() + 120) != "ready":
            raise RuntimeError(f"{name} worker handshake failed")
        self.on_result = on_result
        self.lock = threading.Lock()
        self.jobs: "list" = []
        self.cv = threading.Condition()
        if on_result is not None:
            threading.Thread(target=self._sender, daemon=True).start()
            threading.Thread(target=self._reader, daemon=True).start()

    def submit(self, job: dict) -> None:
        with self.cv:
            self.jobs.append(job)
            self.cv.notify()

    def _sender(self):
        while True:
            with self.cv:
                while not self.jobs:
                    self.cv.wait()
                job = self.jobs.pop(0)
            try:
                _send(self.fout, job)
            except Exception as exc:  # noqa: BLE001
                self.on_result(("error", {"act_id": job.get("act_id"), "error": repr(exc)[:300]}))

    def _reader(self):
        while True:
            try:
                msg = _recv(self.fin)
            except Exception as exc:  # noqa: BLE001
                self.on_result(("dead", {"error": repr(exc)[:300]}))
                return
            self.on_result(msg)

    def call(self, job: dict, timeout_s: float):
        deadline = time.monotonic() + timeout_s
        if not self.lock.acquire(timeout=timeout_s):
            raise TimeoutError(f"{self.name} worker busy")
        try:
            _send(self.fout, job, deadline)
            st, out = _recv(self.fin, deadline)
            if st != "ok":
                raise RuntimeError(out.get("error"))
            return out
        finally:
            self.lock.release()


if __name__ == "__main__" and sys.argv[1:] == ["worker"]:
    sys.path.insert(0, HERE)
    proto_out = os.fdopen(os.dup(1), "wb")      # the protocol keeps the real stdout; anything printed goes to stderr
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    _worker(sys.stdin.buffer, proto_out)
