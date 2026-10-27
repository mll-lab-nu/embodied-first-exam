"""Sidecar side of the Newton bridge: the service base class, the registry and the request loop.

This module runs in the *Newton interpreter* (see ``server.py``), not in Isaac Sim.  At import time it needs only the
standard library and numpy; a service imports ``warp`` / ``newton`` lazily, in its own methods, so the bridge itself can be
tested with any interpreter.

Writing a service::

    from sidecar.host import NewtonService, register_service

    @register_service("mything.rollout")
    class Rollout(NewtonService):
        def __init__(self, cfg, arrays):             # the client's ``create``: a JSON config and named arrays
            import newton                            # lazy: builds the model, captures CUDA graphs, ...
            ...

        def rpc_run(self, h, a):                     # the client's ``call("run", header, arrays)``
            self.emit("progress", step=3)            # optional events while a long call runs
            return {"cost": 0.1}, {"positions": pos} # header dict [, arrays dict]

        def close(self):                             # the client's ``destroy`` (release GPU memory)
            ...

Arrays reach a service as private, writable copies; a service that only reads them inside the call and handles big
arrays can set ``zero_copy = True`` and gets read-only views of the shared-memory arena (valid until it returns).

Only methods named ``rpc_<name>`` can be called from the client.  One service instance is one *handle* (a session: one
scene, one model); a sidecar hosts any number of them.  Ops of the loop: ``ping``, ``status``, ``load``, ``create``,
``call``, ``destroy``, ``shutdown``.  Service modules are given by dotted name (``load`` / ``create``).
"""

from __future__ import annotations

import gc
import importlib
import os
import socket
import sys
import time
import traceback
from typing import Any, ClassVar, Dict, Optional, Tuple, Type

import numpy as np

from . import protocol

Arrays = Dict[str, np.ndarray]


class NewtonService:
    """Base class of a service hosted by the sidecar; see the module docstring."""

    name: ClassVar[str] = ""
    #: True: ``rpc_*`` get read-only views of the request's shared-memory arrays instead of copies
    zero_copy: ClassVar[bool] = False

    def __init__(self, cfg: Dict[str, Any], arrays: Arrays):
        self.cfg = cfg

    def close(self) -> None:
        """Release what the instance holds (GPU memory, captured graphs); called on ``destroy`` and on shutdown."""

    def describe(self) -> Dict[str, Any]:
        """Small JSON-able description returned by ``create`` and ``status``."""
        return {}

    def emit(self, event: str, **data: Any) -> None:
        """Send an event to the client while the current request runs (progress, log lines)."""
        host = Host.current
        if host is not None:
            host.emit(event, data)


_SERVICES: Dict[str, Type[NewtonService]] = {}


def register_service(name: str):
    """Class decorator: make ``name`` create instances of the class."""

    def deco(cls: Type[NewtonService]) -> Type[NewtonService]:
        old = _SERVICES.get(name)
        if old is not None and (old.__module__, old.__qualname__) != (cls.__module__, cls.__qualname__):
            raise ValueError(f"service {name!r} is already registered by {old}")
        cls.name = name
        _SERVICES[name] = cls
        return cls

    return deco


def registered_services() -> Dict[str, Type[NewtonService]]:
    return dict(_SERVICES)


def load_modules(paths=(), modules=()) -> list:
    """Extend ``sys.path`` and import service modules (which register their services on import); returns the names of
    all registered services."""
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
    for mod in modules:
        importlib.import_module(mod)
    return sorted(_SERVICES)


def _error(exc: BaseException) -> Dict[str, Any]:
    return {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}


def _rss_mb() -> Optional[float]:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return None


def _own(arrays: Arrays) -> Arrays:
    """Private writable copies of arrays that may be read-only views of the shared-memory arena."""
    return {k: (v if v.flags.writeable else v.copy()) for k, v in arrays.items()}


class Host:
    """The request loop: one connection, one request at a time."""

    #: the running host (services reach it through :meth:`NewtonService.emit`)
    current: ClassVar[Optional["Host"]] = None

    #: requests slower than this (seconds) are logged; the log is for trouble, not a per-request line
    slow_log_s: ClassVar[float] = 1.0

    def __init__(self, sock: socket.socket, shm_dir: Optional[str] = None):
        tx = rx = None  # shared-memory arenas: replies / requests
        if shm_dir:
            tx = protocol.Arena(os.path.join(shm_dir, "s2c"), writer=True)
            rx = protocol.Arena(os.path.join(shm_dir, "c2s"), writer=False)
        self.conn = protocol.Conn(sock, tx, rx)
        self._ops = {n[3:]: getattr(self, n) for n in dir(self) if n.startswith("op_")}
        self.handles: Dict[int, NewtonService] = {}
        self._next = 1
        self._req_id = 0
        self.started = time.time()
        Host.current = self

    # -- plumbing ------------------------------------------------------------------------------------------------------
    def emit(self, event: str, data: Dict[str, Any]) -> None:
        self.conn.send({"kind": "event", "id": self._req_id, "event": event, "h": data})

    def serve(self) -> None:
        conn, ops = self.conn, self._ops
        while True:
            try:
                env, arrays = conn.recv(copy=False)
            except EOFError:
                break
            rid = self._req_id = env["id"]
            op = env["op"]
            if op == "shutdown":
                conn.send({"kind": "resp", "id": rid, "ok": True, "h": {}})
                break
            t0 = time.perf_counter()
            try:
                fn = ops.get(op)
                if fn is None:
                    raise ValueError(f"unknown op {op!r}")
                head, out = self._normalise(fn(env.get("h") or {}, arrays))
                conn.send({"kind": "resp", "id": rid, "ok": True, "h": head}, out)
            except Exception as exc:  # noqa: BLE001 - reported to the caller, the host stays up
                print(f"[newton-host] {op} failed:\n{traceback.format_exc()}", flush=True)
                conn.send({"kind": "resp", "id": rid, "ok": False, "err": _error(exc)})
            dt = time.perf_counter() - t0
            if dt > self.slow_log_s:
                print(f"[newton-host] {op}: {dt:.2f} s", flush=True)
        self.close_all()

    @staticmethod
    def _normalise(ret: Any) -> Tuple[Dict[str, Any], Arrays]:
        if ret is None:
            return {}, {}
        if isinstance(ret, tuple):
            head, out = ret
            return dict(head or {}), dict(out or {})
        return dict(ret), {}

    def close_all(self) -> None:
        for hid in list(self.handles):
            self._destroy(hid)
        Host.current = None

    def _destroy(self, hid: int) -> None:
        svc = self.handles.pop(hid, None)
        if svc is not None:
            try:
                svc.close()
            except Exception:  # noqa: BLE001
                print(f"[newton-host] closing {svc.name}#{hid} failed:\n{traceback.format_exc()}", flush=True)
            del svc
            gc.collect()

    # -- ops -----------------------------------------------------------------------------------------------------------
    def op_ping(self, h: Dict[str, Any], a: Arrays):
        info: Dict[str, Any] = {"pid": os.getpid(), "python": sys.version.split()[0], "protocol": protocol.VERSION}
        if h.get("versions"):  # imports warp / newton: seconds, so only on request
            for mod in ("warp", "newton"):
                try:
                    m = importlib.import_module(mod)
                    info[mod] = getattr(m, "__version__", "?")
                except Exception:  # noqa: BLE001
                    info[mod] = None
            try:
                import warp as wp

                info["cuda"] = bool(wp.is_cuda_available())
            except Exception:  # noqa: BLE001
                info["cuda"] = False
        return info

    def op_status(self, h: Dict[str, Any], a: Arrays):
        info: Dict[str, Any] = {
            "pid": os.getpid(),
            "uptime_s": time.time() - self.started,
            "rss_mb": _rss_mb(),
            "services": sorted(_SERVICES),
            "handles": {str(i): {"service": s.name, **s.describe()} for i, s in self.handles.items()},
        }
        wp = sys.modules.get("warp")
        if wp is not None:
            try:
                info["warp_mempool_mb"] = wp.get_mempool_used_mem_current("cuda:0") / 2**20
            except Exception:  # noqa: BLE001
                pass
        return info

    def op_load(self, h: Dict[str, Any], a: Arrays):
        return {"services": load_modules(h.get("paths", []), h.get("modules", []))}

    def op_create(self, h: Dict[str, Any], a: Arrays):
        if h.get("module"):
            importlib.import_module(h["module"])
        name = h["service"]
        cls = _SERVICES.get(name)
        if cls is None:
            raise KeyError(f"no service {name!r}; registered: {sorted(_SERVICES)} (module given: {h.get('module')!r})")
        t0 = time.perf_counter()
        svc = cls(h.get("cfg") or {}, _own(a))
        hid = self._next
        self._next += 1
        self.handles[hid] = svc
        return {"handle": hid, "seconds": time.perf_counter() - t0, **svc.describe()}

    def op_call(self, h: Dict[str, Any], a: Arrays):
        svc = self.handles.get(int(h["handle"]))
        if svc is None:
            raise KeyError(f"no handle {h['handle']!r}")
        fn = getattr(svc, f"rpc_{h['method']}", None)
        if fn is None:
            raise AttributeError(f"{svc.name} has no rpc_{h['method']}")
        return fn(h.get("args") or {}, a if svc.zero_copy else _own(a))

    def op_destroy(self, h: Dict[str, Any], a: Arrays):
        self._destroy(int(h["handle"]))
        return {}


def serve_socket(address: str, shm_dir: Optional[str] = None) -> None:
    """Connect to the client's listening unix socket and serve until it closes."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(address)
    Host(sock, shm_dir).serve()
