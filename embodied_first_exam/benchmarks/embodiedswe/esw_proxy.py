"""The graded `env` of an EmbodiedSWE task: a proxy in an untrusted process, the simulator in a trusted one.

A delivered `solution/solve.py` exposes `solve(env)`. In grading, `solve` never runs next to the simulator:

    trusted sim process (root, verifier)            untrusted solution process (`nobody`, no network)
    rcb_embodiedswe.py rollout                      python -I -B esw_proxy.py <fd_in> <fd_out> <solution dir>
      env (built from the frozen instance)   <--->    solve(RemoteEnv)   (one request per line, over two pipes)
      the task's grader (records every step)

`RemoteEnv` mirrors the env the agent used in development: attribute reads, item reads, `len`, iteration and
read-only method calls are forwarded and answered with copies (a tensor comes back as a new CPU tensor; changing
it changes nothing in the simulator); every other object stays in the trusted process and is reached through a
handle. `env.step(action)` is the only call that advances the simulation; the trusted side records every action
it executes. `reset`, `set_states`, attribute and item assignment, and every call that is not a read are refused
with PermissionError (the same rule as EmbodiedSWE's GradedEnv, made structural).

This module is both sides' codec (`encode` / `decode`) and the untrusted side's entry point (`main`). It imports
only the standard library, numpy and torch, never the simulator.
"""
from __future__ import annotations

import base64
import json
import os
import sys

MAX_LINE = 256 << 20            # one message (a large describe_stage text, a big tensor) at most
MAX_ARRAY_BYTES = 64 << 20      # one tensor or array crossing the boundary
DTYPES = ("float32", "float64", "float16", "int64", "int32", "int16", "int8", "uint8", "bool")
PROTOCOL = "esw-proxy/1"


class ProxyError(RuntimeError):
    """The trusted side refused or failed a request (raised in solve as the original error type when it is one
    of PermissionError, AttributeError, KeyError, IndexError, TypeError, ValueError, RuntimeError)."""


# ------------------------------------------------------------------------------------------------ codec
def _np():
    import numpy as np
    return np


def encode(v, handle_of=None, depth: int = 0):
    """A JSON-able form of `v`. `handle_of(obj) -> dict` turns an object that is not plain data into a handle
    (trusted side); without it such an object is an error (untrusted side: it only sends plain data)."""
    if depth > 64:
        raise ValueError("value nested too deeply")
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else {"__f__": repr(v)}
    if isinstance(v, bytes):
        return {"__b__": base64.b64encode(v).decode()}
    if isinstance(v, (list, tuple)):
        items = [encode(x, handle_of, depth + 1) for x in v]
        return {"__l__": items} if isinstance(v, list) else {"__tu__": items}
    if isinstance(v, dict):
        if all(isinstance(k, str) for k in v):
            return {"__d__": {k: encode(x, handle_of, depth + 1) for k, x in v.items()}}
        return {"__dk__": [[encode(k, handle_of, depth + 1), encode(x, handle_of, depth + 1)] for k, x in v.items()]}
    if isinstance(v, slice):
        return {"__s__": [encode(v.start), encode(v.stop), encode(v.step)]}
    if v is Ellipsis:
        return {"__e__": 1}
    mod = type(v).__module__ or ""
    if mod.startswith("torch") and type(v).__name__ in ("Tensor", "Parameter"):
        import torch
        a = v.detach().to("cpu").contiguous()
        return {"__t__": _arr((a.float() if a.dtype == torch.bfloat16 else a).numpy())}
    if mod.startswith("torch") and type(v).__name__ in ("device", "dtype", "Size"):
        return str(v) if type(v).__name__ != "Size" else {"__tu__": [int(x) for x in v]}
    if mod.startswith("numpy"):
        np = _np()
        if isinstance(v, np.ndarray):
            return {"__n__": _arr(v)}
        if isinstance(v, np.generic):
            return encode(v.item(), handle_of, depth)
    if mod.startswith("pxr.Gf"):                                  # USD vectors / matrices / quaternions by value
        try:
            if hasattr(v, "GetReal") and hasattr(v, "GetImaginary"):
                return {"__tu__": [encode(float(v.GetReal()))] + [encode(float(x)) for x in v.GetImaginary()]}
            return encode(tuple(tuple(r) if hasattr(r, "__len__") else r for r in v), handle_of, depth + 1)
        except TypeError:
            pass
    if handle_of is None:
        raise TypeError(f"cannot send a {type(v).__name__} to the simulator (plain data, tensors and handles only)")
    return handle_of(v)


def _arr(a) -> dict:
    np = _np()
    a = np.ascontiguousarray(a)
    if a.dtype.name not in DTYPES:
        raise TypeError(f"array dtype {a.dtype} is not supported")
    if a.nbytes > MAX_ARRAY_BYTES:
        raise ValueError(f"array of {a.nbytes} bytes is larger than {MAX_ARRAY_BYTES}")
    return {"dtype": a.dtype.name, "shape": list(a.shape), "b64": base64.b64encode(a.tobytes()).decode()}


def _unarr(d: dict):
    """Rebuild an array from untrusted input: whitelisted dtype, exact byte count, bounded size."""
    np = _np()
    if not isinstance(d, dict) or d.get("dtype") not in DTYPES or not isinstance(d.get("shape"), list):
        raise ValueError("malformed array")
    shape = [int(x) for x in d["shape"]]
    if any(x < 0 for x in shape) or len(shape) > 8:
        raise ValueError("malformed array shape")
    raw = base64.b64decode(d.get("b64", ""), validate=True)
    if len(raw) > MAX_ARRAY_BYTES:
        raise ValueError("array too large")
    a = np.frombuffer(raw, dtype=np.dtype(d["dtype"]))
    if a.size != int(np.prod(shape, dtype=np.int64)):
        raise ValueError("array size does not match its shape")
    return a.reshape(shape).copy()


def decode(v, resolve=None, depth: int = 0):
    """Inverse of `encode`. `resolve(dict) -> object` turns a handle back into what it names (each side its own)."""
    if depth > 64:
        raise ValueError("value nested too deeply")
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, list):
        raise ValueError("bare list on the wire")
    if not isinstance(v, dict) or len(v) == 0:
        raise ValueError("malformed value")
    if "__h__" in v:
        if resolve is None:
            raise ValueError("unexpected handle")
        return resolve(v)
    (k, x), = list(v.items())[:1]
    if k == "__f__":
        return float(x) if x in ("nan", "inf", "-inf") else float("nan")
    if k == "__b__":
        return base64.b64decode(x, validate=True)
    if k == "__l__":
        return [decode(i, resolve, depth + 1) for i in x]
    if k == "__tu__":
        return tuple(decode(i, resolve, depth + 1) for i in x)
    if k == "__d__":
        return {str(kk): decode(i, resolve, depth + 1) for kk, i in x.items()}
    if k == "__dk__":
        return {decode(a, resolve, depth + 1): decode(b, resolve, depth + 1) for a, b in x}
    if k == "__s__":
        return slice(*(decode(i, resolve, depth + 1) for i in x))
    if k == "__e__":
        return Ellipsis
    if k == "__n__":
        return _unarr(x)
    if k == "__t__":
        import torch
        return torch.from_numpy(_unarr(x))
    raise ValueError(f"unknown tag {k!r}")


# ------------------------------------------------------------------------------------------------ wire
class Wire:
    """Line-delimited JSON over two file descriptors."""

    def __init__(self, fd_in: int, fd_out: int):
        self.r = os.fdopen(fd_in, "rb", buffering=1 << 16)
        self.w = os.fdopen(fd_out, "wb", buffering=0)

    def send(self, obj) -> None:
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        if len(data) > MAX_LINE:
            raise ValueError("message too large")
        self.w.write(data)

    def recv(self):
        line = self.r.readline(MAX_LINE + 1)
        if not line:
            raise EOFError("the other side closed the connection")
        if len(line) > MAX_LINE:
            raise ValueError("message too large")
        return json.loads(line)


# ------------------------------------------------------------------------------------------------ client
_ERRORS = {"PermissionError": PermissionError, "AttributeError": AttributeError, "KeyError": KeyError,
           "IndexError": IndexError, "TypeError": TypeError, "ValueError": ValueError,
           "RuntimeError": RuntimeError, "StopIteration": StopIteration, "TimeoutError": TimeoutError}


class _Conn:
    def __init__(self, wire: Wire):
        self.wire = wire
        self.calls = 0

    def ask(self, req: dict):
        self.calls += 1
        self.wire.send(req)
        rep = self.wire.recv()
        if "error" in rep:
            if rep.get("stop"):                      # the trusted side ended the rollout (time limit, step cap)
                raise SystemExit(f"[esw] rollout stopped by the evaluator: {rep['error']}")
            raise _ERRORS.get(rep.get("kind"), ProxyError)(rep["error"])
        return decode(rep.get("value"), self.handle)

    def handle(self, d: dict):
        return RemoteObject(self, int(d["__h__"]), str(d.get("type", "object")), bool(d.get("callable")))


class RemoteObject:
    """A read-only view of an object that lives in the trusted simulator process."""

    __slots__ = ("_c", "_h", "_t", "_callable")

    def __init__(self, conn: _Conn, h: int, type_name: str, is_callable: bool = False):
        object.__setattr__(self, "_c", conn)
        object.__setattr__(self, "_h", h)
        object.__setattr__(self, "_t", type_name)
        object.__setattr__(self, "_callable", is_callable)

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return self._c.ask({"op": "getattr", "h": self._h, "name": name})

    def __setattr__(self, name, value):
        raise PermissionError(f"blocked during grading: cannot set {self._t}.{name} (read-only view of the simulator)")

    def __delattr__(self, name):
        raise PermissionError(f"blocked during grading: cannot delete {self._t}.{name}")

    def __getitem__(self, key):
        return self._c.ask({"op": "getitem", "h": self._h, "key": encode(key, _send_handle)})

    def __setitem__(self, key, value):
        raise PermissionError(f"blocked during grading: cannot assign items of {self._t}")

    def __delitem__(self, key):
        raise PermissionError(f"blocked during grading: cannot delete items of {self._t}")

    def __len__(self):
        return int(self._c.ask({"op": "len", "h": self._h}))

    def __iter__(self):
        return iter(self._c.ask({"op": "iter", "h": self._h}))

    def __contains__(self, item):
        return bool(self._c.ask({"op": "contains", "h": self._h, "item": encode(item, _send_handle)}))

    def __bool__(self):
        return bool(self._c.ask({"op": "bool", "h": self._h}))

    def __call__(self, *args, **kwargs):
        return self._c.ask({"op": "call", "h": self._h, "args": encode(list(args), _send_handle),
                            "kwargs": encode(dict(kwargs), _send_handle)})

    def __repr__(self):
        try:
            return self._c.ask({"op": "repr", "h": self._h})
        except Exception:  # noqa: BLE001
            return f"<remote {self._t}>"

    def __dir__(self):
        return list(self._c.ask({"op": "dir", "h": self._h}))


def _send_handle(obj):
    """Untrusted side: a RemoteObject may be passed back as an argument (by handle); nothing else that is not data."""
    if isinstance(obj, RemoteObject):
        return {"__h__": object.__getattribute__(obj, "_h")}
    raise TypeError(f"cannot send a {type(obj).__name__} to the simulator (plain data, tensors and handles only)")


class RemoteEnv(RemoteObject):
    """The env handed to `solve` in grading. `step` is the one call that advances the simulation."""

    __slots__ = ()

    def step(self, action, render: bool = False):
        return self._c.ask({"op": "step", "action": encode(action, _send_handle)})

    def reset(self, *args, **kwargs):
        raise PermissionError("blocked during grading — the graded env was reset by the grader; solve may only step forward")

    def set_states(self, *args, **kwargs):
        raise PermissionError("blocked during grading — solve may only step forward")


# ------------------------------------------------------------------------------------------------ untrusted entry
def _limits() -> None:
    import resource
    gb = 1 << 30
    for res, val in ((resource.RLIMIT_AS, 24 * gb), (resource.RLIMIT_NOFILE, 512), (resource.RLIMIT_FSIZE, 1 * gb),
                     (resource.RLIMIT_NPROC, 512), (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(res, (val, val))
        except (ValueError, OSError):
            pass


# Landlock (Linux >= 5.13, unprivileged, allowed by Docker's default seccomp profile): the solution process may read
# the system's software trees, its own solution copy and /proc entries of its own; it may write only its scratch
# directory, and it can open no TCP connection. Everything else (other processes' /proc entries, /tests, /logs, the
# trusted work files, /tmp, /cache, /app) is out of reach whatever the file modes say. A PID namespace would need
# CAP_SYS_ADMIN, which a verifier container does not get (docs/protocol/invariants.md H.1: no service widens its container).
LANDLOCK_ABI_MIN = 4
_FS_EXECUTE, _FS_WRITE_FILE, _FS_READ_FILE, _FS_READ_DIR = 1, 2, 4, 8
_FS_ALL_V1 = (1 << 13) - 1                   # execute .. make_sym
_FS_REFER, _FS_TRUNCATE = 1 << 13, 1 << 14
_NET_BIND_TCP, _NET_CONNECT_TCP = 1, 2
READ_TREES = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc", "/opt", "/root", "/sys")
PROC_FILES = ("/proc/cpuinfo", "/proc/meminfo", "/proc/stat", "/proc/loadavg", "/proc/version", "/proc/filesystems",
              "/proc/sys")
DEV_FILES = ("/dev/null", "/dev/zero", "/dev/urandom", "/dev/random", "/dev/full")


def landlock_abi() -> int:
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    return int(libc.syscall(444, None, 0, 1))          # landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)


def sandbox(solution: str, scratch: str) -> int:
    """Restrict this process (and everything it starts) with Landlock. Returns the ABI; raises when unavailable."""
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    abi = landlock_abi()
    if abi < LANDLOCK_ABI_MIN:
        raise OSError(f"Landlock ABI {abi} < {LANDLOCK_ABI_MIN}")
    fs_all = _FS_ALL_V1 | _FS_REFER | _FS_TRUNCATE

    class Ruleset(ctypes.Structure):
        _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64)]

    class PathBeneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed", ctypes.c_uint64), ("fd", ctypes.c_int32)]

    rs = Ruleset(fs_all, _NET_BIND_TCP | _NET_CONNECT_TCP)
    fd = libc.syscall(444, ctypes.byref(rs), ctypes.sizeof(rs), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    read = _FS_EXECUTE | _FS_READ_FILE | _FS_READ_DIR
    rules = [(p, read) for p in READ_TREES] + [(p, _FS_READ_FILE | _FS_READ_DIR) for p in PROC_FILES]
    rules += [(f"/proc/{os.getpid()}", _FS_READ_FILE | _FS_READ_DIR), (solution, _FS_READ_FILE | _FS_READ_DIR)]
    rules += [(p, _FS_READ_FILE | _FS_WRITE_FILE) for p in DEV_FILES]
    rules += [(scratch, fs_all & ~_FS_REFER if abi < 2 else fs_all)]
    for path, acc in rules:
        try:
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        except OSError:
            continue
        try:
            if os.path.isfile(path) or not os.path.isdir(path):
                acc &= _FS_EXECUTE | _FS_READ_FILE | _FS_WRITE_FILE | _FS_TRUNCATE
            attr = PathBeneath(acc, pfd)
            if libc.syscall(445, fd, 1, ctypes.byref(attr), 0) != 0:
                raise OSError(ctypes.get_errno(), f"landlock_add_rule {path}")
        finally:
            os.close(pfd)
    if libc.prctl(38, 1, 0, 0, 0) != 0:                # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_NO_NEW_PRIVS)")
    if libc.syscall(446, fd, 0) != 0:                  # landlock_restrict_self
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    os.close(fd)
    return abi


def _verify_sandbox(scratch: str) -> None:
    """Fail closed: after sandbox() returns, confirm the restrictions are actually in force. A silently
    mis-applied Landlock ruleset (a rule fd that failed to open, an ABI quirk) would otherwise leave a hole
    that only shows up as a leak. Each check must be DENIED; if any is allowed we raise, and main() reports
    an infrastructure failure instead of running the solution. Cheap (a few syscalls)."""
    import socket
    holes = []
    try:                                              # another process's /proc must be unreadable
        with open("/proc/1/cmdline", "rb") as f:
            f.read(1)
        holes.append("/proc/1/cmdline readable")
    except (PermissionError, FileNotFoundError, OSError):
        pass
    probe = os.path.join("/", "esw_sandbox_probe")     # a write outside scratch must be refused
    try:
        with open(probe, "w") as f:
            f.write("x")
        os.unlink(probe)
        holes.append("write outside scratch allowed")
    except (PermissionError, FileNotFoundError, OSError):
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # an outbound TCP connect must be refused
    s.settimeout(0.2)
    try:
        s.connect(("10.255.255.1", 9))
        holes.append("outbound TCP connect allowed")
    except PermissionError:
        pass
    except OSError:
        pass                                           # unreachable / refused / timeout: no egress, acceptable
    finally:
        s.close()
    if holes:
        raise OSError("sandbox verification failed: " + "; ".join(holes))


def main(argv: list[str]) -> int:
    """`python -I -B esw_proxy.py FD_IN FD_OUT SOLUTION_DIR [EXTRA_PATH ...]` (started by the trusted side)."""
    fd_in, fd_out, sol = int(argv[1]), int(argv[2]), argv[3]
    _limits()
    wire = Wire(fd_in, fd_out)
    conn = _Conn(wire)
    for p in reversed(argv[4:]):                 # read-only package roots (robobench), after the standard library
        if p not in sys.path:
            sys.path.append(p)
    import importlib.util
    import traceback

    hello = wire.recv()                          # {"op": "hello", "root": {...handle...}, "scratch": dir}
    env = RemoteEnv(conn, int(hello["root"]["__h__"]), "BaseEnv")
    status = {"op": "done"}
    try:
        scratch = hello.get("scratch") or os.getcwd()
        status["sandbox"] = f"landlock/{sandbox(sol, scratch)}"
        _verify_sandbox(scratch)                     # fail closed: a sandbox that did not take effect = no run
    except Exception as exc:  # noqa: BLE001 — no sandbox, no run: the trusted side reports an infrastructure failure
        wire.send({"op": "done", "sandbox_failed": f"{type(exc).__name__}: {exc}"})
        os._exit(0)
    try:
        sys.path.insert(0, sol)                  # the native grader's rule: solve.py's directory is importable
        spec = importlib.util.spec_from_file_location("solve", os.path.join(sol, "solve.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["solve"] = mod
        spec.loader.exec_module(mod)
        if not callable(getattr(mod, "solve", None)):
            raise AttributeError("solve.py does not expose solve(env)")
        wire.send({"op": "loaded"})
        wire.recv()
        mod.solve(env)
    except SystemExit as e:
        status["error"] = f"SystemExit: {e}"
    except BaseException:  # noqa: BLE001 — the solution's own exception: its progress so far is still graded
        status["error"] = traceback.format_exc()[-8000:]
    status["calls"] = conn.calls
    for f in (sys.stdout, sys.stderr):           # before "done": the trusted side ends this process right after it
        try:
            f.flush()
        except Exception:  # noqa: BLE001
            pass
    try:
        wire.send(status)
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
