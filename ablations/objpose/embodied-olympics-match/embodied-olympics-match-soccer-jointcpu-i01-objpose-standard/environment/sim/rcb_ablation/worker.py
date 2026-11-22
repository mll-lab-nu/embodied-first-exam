"""python -m rcb_ablation.worker <plugin> <kind> <side> <cfg_json> (RCB_STATE_OPS, a core with platform seats): the
core's worker (core/workers.py main, unchanged), whose platform program is wrapped so the match service can read and
replace its whole state. A job {"rcb_state": ...} is answered by the wrapper; every other job goes to the program.

    {"rcb_state": "get"}            the program pickled: {"blob", "sha" (sha256 of the blob), "state_sha"}. A plan
                                    still being computed in a planner process is waited for first and kept as its
                                    result, so the blob holds every decision the program has made
    {"rcb_state": "set", "blob"}    the program replaced by the blob's: {"sha", "state_sha"}
    {"rcb_state": "fresh"}          a new program, as the worker built it at its start: {"state_sha"}
state_sha is a canonical hash of the program's whole state (every value, recursively; state_sha below): a load is
checked by the restored program's state_sha being the saved one. Each answer also has "parts" (state_sha per
attribute, where two states differ) and the program's own digest (Program.digest, when it has one)."""
import hashlib
import os
import pickle
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # /srv


def _settle(prog):
    """A planned decision still running in a planner process (a concurrent Future in prog.pending): its result, kept
    as the program's own finished-planning object (its module's _Done), so the program can be pickled."""
    mod = sys.modules.get(type(prog).__module__)
    done = getattr(mod, "_Done", None)
    for item in getattr(prog, "pending", None) or []:
        fut = item[-1] if isinstance(item, list) and item else None
        if fut is not None and type(fut).__name__ == "Future" and done is not None:
            item[-1] = done(fut.result())


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _canon(x, h, path=()):
    """A canonical hash of an object's state, independent of how pickling shares equal objects (a restored program
    can pickle to other bytes while holding the same values): types and values, recursively."""
    import numpy as np
    t = type(x)
    if x is None or t in (bool, int, float, complex, str, bytes):
        h.update(f"{t.__name__}:{x!r};".encode())
        return
    if isinstance(x, np.ndarray):
        h.update(f"nd:{x.dtype.str}:{x.shape};".encode())
        if x.dtype.hasobject:
            for v in x.ravel().tolist():
                _canon(v, h, path)
        else:
            h.update(np.ascontiguousarray(x).tobytes())
        return
    if isinstance(x, np.generic):
        h.update(f"np:{x.dtype.str}:{x.item()!r};".encode())
        return
    if id(x) in path:
        h.update(b"<cycle>;")
        return
    path = path + (id(x),)
    if isinstance(x, np.random.Generator):
        h.update(b"gen:")
        _canon(x.bit_generator.state, h, path)
        return
    if isinstance(x, dict):
        h.update(f"{t.__name__}{{{len(x)};".encode())
        for k, v in x.items():
            _canon(k, h, path)
            _canon(v, h, path)
        h.update(b"};")
        return
    if isinstance(x, (list, tuple)) or t.__name__ == "deque":
        h.update(f"{t.__name__}[{len(x)};".encode())
        for v in x:
            _canon(v, h, path)
        h.update(b"];")
        return
    if isinstance(x, (set, frozenset)):
        subs = []
        for v in x:
            g = hashlib.sha256()
            _canon(v, g, path)
            subs.append(g.hexdigest())
        h.update(f"{t.__name__}({','.join(sorted(subs))});".encode())
        return
    if callable(x) and not hasattr(x, "__dict__") or isinstance(x, type):
        h.update(f"fn:{getattr(x, '__qualname__', t.__name__)};".encode())
        return
    d = getattr(x, "__dict__", None)
    slots = [a for c in t.__mro__ for a in (getattr(c, "__slots__", ()) or ())]
    if d is not None or slots:
        h.update(f"obj:{t.__module__}.{t.__qualname__}<".encode())
        if d is not None:
            _canon(d, h, path)
        for a in slots:
            if isinstance(a, str) and hasattr(x, a):
                _canon(a, h, path)
                _canon(getattr(x, a), h, path)
        h.update(b">;")
        return
    try:
        h.update(pickle.dumps(x, protocol=pickle.HIGHEST_PROTOCOL))
    except Exception:  # noqa: BLE001
        h.update(f"{t.__name__}:{x!r};".encode())


def state_sha(x) -> str:
    h = hashlib.sha256()
    _canon(x, h)
    return h.hexdigest()


def _parts(prog) -> dict:
    """state_sha of each attribute of the program (and of its attributes' attributes): where two states differ."""
    out = {}
    for k, v in (getattr(prog, "__dict__", None) or {}).items():
        out[k] = state_sha(v)
        if hasattr(v, "__dict__") and not isinstance(v, (type, types.FunctionType, types.MethodType)):
            for kk, vv in vars(v).items():
                out[f"{k}.{kk}"] = state_sha(vv)
    return out


class Held:
    """The platform program, replaceable (see the module text)."""

    def __init__(self, prog, make):
        self.prog, self.make = prog, make

    def _own(self) -> dict:
        d = getattr(self.prog, "digest", None)
        return {"program_digest": d()} if callable(d) else {}

    def decide(self, job):
        op = job.get("rcb_state") if isinstance(job, dict) else None
        if op is None:
            return self.prog.decide(job)
        if op == "get":
            _settle(self.prog)
            blob = pickle.dumps(self.prog, protocol=pickle.HIGHEST_PROTOCOL)
            return {"blob": blob, "sha": _sha(blob), "state_sha": state_sha(self.prog), "parts": _parts(self.prog),
                    **self._own()}
        if op == "set":
            blob = job["blob"]
            self.prog = pickle.loads(blob)
            return {"sha": _sha(blob), "state_sha": state_sha(self.prog), "parts": _parts(self.prog), **self._own()}
        if op == "fresh":
            self.prog = self.make()
            return {"state_sha": state_sha(self.prog), **self._own()}
        raise ValueError(f"unknown rcb_state {op!r}")

    def __getattr__(self, name):
        return getattr(self.prog, name)


def main():
    from core import platform_seat, workers
    init = platform_seat.worker_main_init

    def worker_main_init(sport, side, cfg):
        prog, cpus = init(sport, side, cfg)
        return Held(prog, lambda: sport.platform_program(side, cfg)), cpus

    platform_seat.worker_main_init = worker_main_init
    workers.main(*sys.argv[1:])


if __name__ == "__main__":
    main()
