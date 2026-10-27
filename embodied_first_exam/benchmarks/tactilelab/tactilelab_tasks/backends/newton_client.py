"""Client of the Newton sidecar: use Newton (cloth, cables, dough, FEM) from inside the Isaac process (stdlib + numpy only).

Why a separate process: Newton needs ``warp-lang >= 1.17`` and Python 3.12, Isaac Sim 5.1 ships Python 3.11 with warp 1.12,
so Newton cannot be imported into the simulation.  It runs in a sidecar with its own interpreter (``TACTILELAB_NEWTON_PYTHON``,
see the README); this module starts it, talks to it over a unix socket (``sidecar/protocol.py``) and hides the
difference::

    from tactilelab_tasks.backends.newton_client import shared_client, SoftWorldClient

    world = SoftWorldClient(cfg, collider_q0)          # one sidecar per Isaac process, started on first use
    state = world.step(collider_q)                     # (C, 7) xyzw poses in -> {"particle_q": (P, 3), ...} out
    world.close()

* the sidecar is started lazily, restarted if it dies, and stopped with the client (``atexit``);
* a :class:`ServiceHandle` remembers how it was created and re-creates itself after a restart (``recreate=True``);
* the child gets a clean environment - the simulator's ``PYTHONPATH`` / ``LD_LIBRARY_PATH`` / ``VIRTUAL_ENV`` would break a
  different interpreter; its log goes to a file (``client.log_path``);
* ``min_free_mib`` makes :meth:`NewtonClient.start` wait for GPU memory (a shared card);
* arrays above 16 KB travel through shared memory (``/dev/shm``): a call's arrays cost one memcpy each way; results are
  copies unless ``zero_copy=True``, which returns read-only views valid until the next call.

All poses on the wire are ``x y z qx qy qz qw`` (xyzw, Newton's order), env-local metres; convert from the package's
wxyz poses with :func:`tactilelab_tasks.softbody_geom.spec.pose7_wxyz_to_xyzw`.
"""

from __future__ import annotations

import atexit
import importlib.util
import itertools
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import numpy as np

log = logging.getLogger("tactilelab_tasks.newton")

#: environment variable naming the Python interpreter of the Newton environment (Python 3.12, newton >= 1.7, warp >= 1.17)
PYTHON_ENV = "TACTILELAB_NEWTON_PYTHON"
#: environment variable overriding the sidecar directory (default: ``<repository>/sidecar``)
SIDECAR_ENV = "TACTILELAB_NEWTON_SIDECAR"
#: environment variable choosing the directory of the sidecar log files (default: the temp directory)
LOG_DIR_ENV = "TACTILELAB_NEWTON_LOG_DIR"
#: the service module the sidecar preloads; passed on ``create`` so a bare sidecar imports it on demand
SERVICE_MODULE = "sidecar.services"
#: prefix of the socket / shared-memory directories of this package's sidecars
_PREFIX = "tactilelab_newton_"

#: environment variables the sidecar inherits (everything else is dropped)
_KEEP_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "WARP_CACHE_PATH",
    "XDG_CACHE_HOME",
)

Arrays = Dict[str, np.ndarray]
EventCallback = Callable[[str, Dict[str, Any]], None]


def sidecar_dir() -> Path:
    """The directory holding ``server.py`` / ``protocol.py`` (``TACTILELAB_NEWTON_SIDECAR`` or ``<repository>/sidecar``)."""
    env = os.environ.get(SIDECAR_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "sidecar"


def _load_protocol():
    """``sidecar/protocol.py`` as a module: the wire format has one source file, shared by both processes."""
    name = "tactilelab_tasks.backends._newton_protocol"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    path = sidecar_dir() / "protocol.py"
    if not path.exists():
        raise ImportError(
            f"the sidecar protocol module {path} does not exist; set {SIDECAR_ENV} to the sidecar directory"
        )
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


protocol = _load_protocol()


class NewtonError(RuntimeError):
    """The sidecar could not be started, died, timed out, or the bridge was misused."""


class SidecarDied(NewtonError):
    pass


class RemoteError(NewtonError):
    """The sidecar ran the request and it raised: ``.type`` / ``.remote_traceback`` are the remote exception's."""

    def __init__(self, err: Dict[str, Any], op: str):
        self.type = err.get("type", "?")
        self.remote_traceback = err.get("traceback", "")
        super().__init__(f"{op}: {self.type}: {err.get('message', '')}\n{self.remote_traceback}")


def find_python(python: Optional[str] = None) -> str:
    """The Newton interpreter: the argument, else ``TACTILELAB_NEWTON_PYTHON``, else ``<sidecar>/.venv/bin/python``."""
    cand = python or os.environ.get(PYTHON_ENV)
    if not cand:
        venv = sidecar_dir() / ".venv" / "bin" / "python"
        if venv.exists():
            cand = str(venv)
    if not cand or not Path(cand).exists():
        raise NewtonError(
            f"the Newton interpreter {cand!r} does not exist: set {PYTHON_ENV} to the python of an environment with Newton "
            "(Python 3.12, newton >= 1.7, warp >= 1.17)"
        )
    return cand


def gpu_free_mib() -> Optional[int]:
    """Free memory of GPU 0 [MiB] (None if ``nvidia-smi`` is not available)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        return int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001 - no GPU tooling: no gate
        return None


def wait_gpu_free(min_free_mib: int, timeout: float, poll: float = 5.0) -> bool:
    """Block until GPU 0 has ``min_free_mib`` free; False if that does not happen within ``timeout`` seconds."""
    t_end = time.monotonic() + timeout
    while True:
        free = gpu_free_mib()
        if free is None or free >= min_free_mib:
            return True
        if time.monotonic() >= t_end:
            return False
        time.sleep(poll)


def _shm_base() -> str:
    return "/dev/shm" if os.access("/dev/shm", os.W_OK) else tempfile.gettempdir()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clean_stale_shm() -> int:
    """Remove the shared-memory directories of clients that are gone (a crash leaves its directory behind)."""
    base, removed = _shm_base(), 0
    for d in Path(base).glob(_PREFIX + "*"):
        try:
            pid = int(d.name[len(_PREFIX) :].split("_")[0])
        except (IndexError, ValueError):
            continue
        if not _pid_alive(pid) and d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def _log_event(name: str, data: Dict[str, Any]) -> None:
    if name == "log":
        log.info("[newton] %s", data.get("msg", data))
    else:
        log.debug("[newton] %s %s", name, data)


class NewtonClient:
    """One sidecar process.  Thread-safe: calls are serialised (the sidecar serves one request at a time)."""

    def __init__(
        self,
        python: Optional[str] = None,
        *,
        paths: Sequence[str] = (),
        modules: Sequence[str] = (),
        startup_timeout: float = 300.0,
        call_timeout: float = 1800.0,
        log_path: Optional[str] = None,
        min_free_mib: int = 0,
        gpu_wait: float = 1800.0,
        extra_env: Optional[Dict[str, str]] = None,
        shm: bool = True,
    ):
        self.python = python
        self.paths = list(paths)
        self.modules = list(modules)
        self.startup_timeout = startup_timeout
        self.call_timeout = call_timeout
        self.log_path = log_path
        self.min_free_mib = int(min_free_mib)
        self.gpu_wait = gpu_wait
        self.extra_env = dict(extra_env or {})
        self.shm = shm
        self._tx = None  # shared-memory arenas: requests / replies
        self._rx = None
        self.info: Dict[str, Any] = {}
        #: incremented on every (re)start: handles created under an older epoch are stale
        self.epoch = 0
        self.restarts = 0
        self._proc: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._conn = None
        self._alive_at = 0.0
        self._dir: Optional[str] = None
        self._shm_dir: Optional[str] = None
        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._pool: Optional[ThreadPoolExecutor] = None
        self._started_before = False
        atexit.register(self.close)

    # -- lifecycle -------------------------------------------------------------------------------------------------------
    @property
    def alive(self) -> bool:
        """The sidecar is up.  ``Popen.poll`` is a syscall: it is asked at most every 50 ms (a death in between surfaces as
        a failed send / recv of the next request, which raises :class:`SidecarDied`; the request after that restarts)."""
        if self._proc is None or self._conn is None:
            return False
        now = time.monotonic()
        if now - self._alive_at > 0.05:
            self._alive_at = now
            if self._proc.poll() is not None:
                self._stop()
                return False
        return True

    def _env(self) -> Dict[str, str]:
        env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env["PYTHONUNBUFFERED"] = "1"
        env.update(self.extra_env)
        return env

    def start(self) -> Dict[str, Any]:
        """Start the sidecar if it is not running (waiting for GPU memory first if ``min_free_mib`` is set); returns its
        ``ping`` info."""
        with self._lock:
            if self.alive:
                return self.info
            self._stop()
            if self.min_free_mib and not wait_gpu_free(self.min_free_mib, self.gpu_wait):
                raise NewtonError(f"less than {self.min_free_mib} MiB of GPU memory free for {self.gpu_wait:.0f} s")
            python = find_python(self.python)
            server = sidecar_dir() / "server.py"
            if not server.exists():
                raise NewtonError(f"sidecar entry point {server} not found; set {SIDECAR_ENV}")
            self._dir = tempfile.mkdtemp(prefix=_PREFIX)
            addr = os.path.join(self._dir, "s")
            cmd_shm: list = []
            if self.shm:
                clean_stale_shm()
                shm_dir = os.path.join(
                    _shm_base(), f"{_PREFIX}{os.getpid()}_{os.path.basename(self._dir)[len(_PREFIX) :]}"
                )
                os.makedirs(shm_dir, mode=0o700)
                self._shm_dir = shm_dir
                self._tx = protocol.Arena(os.path.join(shm_dir, "c2s"), writer=True)
                self._rx = protocol.Arena(os.path.join(shm_dir, "s2c"), writer=False)
                cmd_shm = ["--shm-dir", shm_dir]
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(addr)
            listener.listen(1)
            listener.settimeout(self.startup_timeout)
            if self.log_path is None:
                log_dir = os.environ.get(LOG_DIR_ENV, tempfile.gettempdir())
                self.log_path = os.path.join(log_dir, f"{_PREFIX}{os.getpid()}_{int(time.time())}.log")
            cmd = [python, "-u", str(server), "--address", addr, *cmd_shm]
            for p in self.paths:
                cmd += ["--path", str(p)]
            for m in self.modules:
                cmd += ["--module", m]
            with open(self.log_path, "ab") as logf:
                self._proc = subprocess.Popen(
                    cmd,
                    env=self._env(),
                    stdin=subprocess.DEVNULL,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    cwd=self._dir,
                )
            try:
                self._sock, _ = listener.accept()
                self._conn = protocol.Conn(self._sock, self._tx, self._rx)
            except (socket.timeout, OSError) as exc:
                tail = self.log_tail()
                self._stop()
                raise NewtonError(
                    f"the Newton sidecar ({python}) did not connect within {self.startup_timeout:.0f} s: {exc!r}\n{tail}"
                ) from exc
            finally:
                listener.close()
            self.epoch += 1
            if self._started_before:
                self.restarts += 1
            self._started_before = True
            self.info, _ = self._roundtrip("ping", {}, None, 120.0, None)
            log.info("Newton sidecar up: %s (log %s)", self.info, self.log_path)
            return self.info

    def _stop(self) -> None:
        sock, conn, proc, d, shm_dir = self._sock, self._conn, self._proc, self._dir, self._shm_dir
        self._sock = self._conn = self._proc = self._dir = self._shm_dir = None
        for arena in (self._tx, self._rx):
            if arena is not None:
                arena.close()
        self._tx = self._rx = None
        if sock is not None:
            try:
                if conn is not None:
                    conn.send({"kind": "req", "id": 0, "op": "shutdown"})
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if proc is not None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)  # the sidecar only (it has its own session)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=10)
        for path in (d, shm_dir):
            if path is not None:
                shutil.rmtree(path, ignore_errors=True)

    def close(self) -> None:
        """Stop the sidecar (idempotent).  Its handles die with it."""
        with self._lock:
            self._stop()
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False)

    def restart(self) -> Dict[str, Any]:
        with self._lock:
            self._stop()
            return self.start()

    def __enter__(self) -> "NewtonClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def log_tail(self, n: int = 40) -> str:
        if not self.log_path or not os.path.exists(self.log_path):
            return ""
        with open(self.log_path, "rb") as fh:
            return b"".join(fh.readlines()[-n:]).decode(errors="replace")

    # -- requests --------------------------------------------------------------------------------------------------------
    def _roundtrip(
        self,
        op: str,
        header: Optional[Dict[str, Any]],
        arrays: Optional[Arrays],
        timeout: Optional[float],
        on_event: Optional[EventCallback],
        zero_copy: bool = False,
    ) -> Tuple[Dict[str, Any], Arrays]:
        conn = self._conn
        assert conn is not None
        rid = next(self._ids)
        # `timeout` is the longest silence tolerated: every event frame of a long request restarts it
        conn.settimeout(timeout or self.call_timeout)
        try:
            conn.send({"kind": "req", "id": rid, "op": op, "h": header or {}}, arrays)
            while True:
                env, out = conn.recv(copy=not zero_copy)
                if env.get("kind") == "event":
                    if env.get("id") == rid:
                        (on_event or _log_event)(env.get("event", "?"), env.get("h") or {})
                    continue
                if env.get("id") != rid:
                    raise protocol.ProtocolError(f"reply {env.get('id')} to request {rid}")
                break
        except (EOFError, OSError, socket.timeout, protocol.ProtocolError) as exc:
            tail = self.log_tail()
            died = self._proc is not None and self._proc.poll() is not None
            self._stop()  # the stream is out of step: start over on the next call
            raise SidecarDied(
                f"Newton sidecar {'died' if died else 'failed'} during {op!r} ({exc!r}); log {self.log_path}:\n{tail}"
            ) from exc
        if not env.get("ok"):
            raise RemoteError(env.get("err") or {}, op)
        return env.get("h") or {}, out

    def call(
        self,
        op: str,
        header: Optional[Dict[str, Any]] = None,
        arrays: Optional[Arrays] = None,
        timeout: Optional[float] = None,
        on_event: Optional[EventCallback] = None,
        zero_copy: bool = False,
    ) -> Tuple[Dict[str, Any], Arrays]:
        """One raw request (starting the sidecar if needed).  Raises :class:`RemoteError` if the op failed in the sidecar
        (it stays up) or :class:`SidecarDied` (the next call starts a fresh one; handles re-create themselves).  Result
        arrays are copies; with ``zero_copy=True`` big ones are read-only views of shared memory, valid until the next call."""
        with self._lock:
            if not self.alive:
                self.start()
            return self._roundtrip(op, header, arrays, timeout, on_event, zero_copy)

    def submit(
        self,
        op: str,
        header: Optional[Dict[str, Any]] = None,
        arrays: Optional[Arrays] = None,
        timeout: Optional[float] = None,
        on_event: Optional[EventCallback] = None,
        zero_copy: bool = False,
    ) -> "Future[Tuple[Dict[str, Any], Arrays]]":
        """:meth:`call` on a worker thread: returns a Future, so the simulation can keep stepping while the sidecar works.
        Requests run in submission order."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newton-client")
        return self._pool.submit(self.call, op, header, arrays, timeout, on_event, zero_copy)

    # -- conveniences ----------------------------------------------------------------------------------------------------
    def versions(self) -> Dict[str, Any]:
        """``ping`` with library versions (imports warp / newton in the sidecar: slow the first time)."""
        return self.call("ping", {"versions": True}, timeout=300.0)[0]

    def status(self) -> Dict[str, Any]:
        return self.call("status")[0]

    def load(self, modules: Sequence[str] = (), paths: Sequence[str] = ()) -> Sequence[str]:
        """Import service modules in the sidecar; returns the registered service names."""
        return self.call("load", {"modules": list(modules), "paths": [str(p) for p in paths]})[0]["services"]

    def service(
        self,
        name: str,
        cfg: Optional[Dict[str, Any]] = None,
        arrays: Optional[Arrays] = None,
        module: Optional[str] = SERVICE_MODULE,
        recreate: bool = True,
        timeout: Optional[float] = None,
    ) -> "ServiceHandle":
        """Create service ``name`` (a class registered with ``@register_service``, in ``module`` if given) in the sidecar and
        return its handle."""
        handle = ServiceHandle(self, name, cfg or {}, arrays or {}, module, recreate, timeout)
        handle._ensure()
        return handle


class ServiceHandle:
    """A service instance in the sidecar (one session: a scene, a model).

    Remembers how it was created; if the sidecar was restarted since, the next call re-creates the instance first
    (``recreate=True``) - fine for services that are re-initialised by the caller - or raises :class:`SidecarDied`."""

    def __init__(
        self,
        client: NewtonClient,
        name: str,
        cfg: Dict[str, Any],
        arrays: Arrays,
        module: Optional[str],
        recreate: bool,
        create_timeout: Optional[float],
    ):
        self.client, self.name, self.cfg, self.arrays = client, name, cfg, arrays
        self.module, self.recreate, self.create_timeout = module, recreate, create_timeout
        self.id: Optional[int] = None
        self.epoch = -1
        self.info: Dict[str, Any] = {}

    def _ensure(self) -> None:
        c = self.client
        with c._lock:
            if not c.alive:
                c.start()
            if self.id is not None and self.epoch == c.epoch:
                return
            if self.id is not None and not self.recreate:
                raise SidecarDied(f"the sidecar was restarted; handle {self.name}#{self.id} is gone")
            head, _ = c._roundtrip(
                "create",
                {"service": self.name, "cfg": self.cfg, "module": self.module},
                self.arrays,
                self.create_timeout,
                None,
            )
            self.id, self.epoch, self.info = int(head["handle"]), c.epoch, head

    def call(
        self,
        method: str,
        header: Optional[Dict[str, Any]] = None,
        arrays: Optional[Arrays] = None,
        timeout: Optional[float] = None,
        on_event: Optional[EventCallback] = None,
        zero_copy: bool = False,
    ) -> Tuple[Dict[str, Any], Arrays]:
        """``rpc_<method>`` of the service: ``(header dict, arrays dict)`` back (``zero_copy``: see :meth:`NewtonClient.call`)."""
        with self.client._lock:
            self._ensure()
            return self.client._roundtrip(
                "call",
                {"handle": self.id, "method": method, "args": header or {}},
                arrays,
                timeout,
                on_event,
                zero_copy,
            )

    def submit(self, method: str, header=None, arrays=None, timeout=None, on_event=None, zero_copy=False) -> "Future":
        c = self.client
        if c._pool is None:
            c._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newton-client")
        return c._pool.submit(self.call, method, header, arrays, timeout, on_event, zero_copy)

    def close(self) -> None:
        c = self.client
        with c._lock:
            if self.id is not None and self.epoch == c.epoch and c.alive:
                try:
                    c._roundtrip("destroy", {"handle": self.id}, None, 60.0, None)
                except NewtonError:
                    pass
            self.id = None

    def __enter__(self) -> "ServiceHandle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_SHARED: Dict[str, NewtonClient] = {}
_SHARED_LOCK = threading.Lock()


def shared_client(python: Optional[str] = None, **kwargs: Any) -> NewtonClient:
    """The process-wide client for an interpreter: all tasks in one Isaac process share one sidecar (one GPU context, one
    copy of the compiled kernels).  ``kwargs`` (``min_free_mib`` ...) only apply when it is first created."""
    key = find_python(python)
    with _SHARED_LOCK:
        client = _SHARED.get(key)
        if client is None:
            client = _SHARED[key] = NewtonClient(python=key, **kwargs)
        return client


def close_shared_clients() -> None:
    with _SHARED_LOCK:
        clients = list(_SHARED.values())
        _SHARED.clear()
    for c in clients:
        c.close()


# -- typed clients of the three services ------------------------------------------------------------------------------


class SoftWorldClient:
    """One soft world (cloth and / or cable, ``softbody.world``) in the sidecar.

    ``cfg``: soft world config (``softbody_geom.spec.world_cfg`` over-rides, e.g. ``soft_scenes.cloth_edge_feed_nominal_world()``);
    ``collider_q0`` ``(C, 7)`` (x y z qx qy qz qw, env-local) initial poses of the ``cfg["colliders"]``; ``cable_points`` ``(S+1, 3)``
    for a cable world.  ``step(collider_q)`` advances one control tick and returns the state dict; ``state`` keeps the last one."""

    def __init__(
        self,
        cfg: Dict[str, Any],
        collider_q0: Optional[np.ndarray] = None,
        cable_points: Optional[np.ndarray] = None,
        client: Optional[NewtonClient] = None,
    ):
        from ..softbody_geom import spec

        self.cfg = spec.world_cfg(cfg)
        arrays: Arrays = {}
        if collider_q0 is not None and len(self.cfg["colliders"]):
            arrays["collider_q0"] = np.asarray(collider_q0, dtype=np.float32).reshape(-1, 7)
        if cable_points is not None:
            arrays["cable_points"] = np.asarray(cable_points, dtype=np.float32)
        self._client = client or shared_client()
        self._svc = self._client.service("softbody.world", cfg=self.cfg, arrays=arrays)
        self.info: Dict[str, Any] = dict(self._svc.info or {})
        self.state: Dict[str, np.ndarray] = {}
        self.last_step_seconds = 0.0

    def mesh(self) -> Dict[str, np.ndarray]:
        """Cloth topology: ``triangles`` ``(T, 3)``, ``rest`` ``(P, 3)``, ``pinned`` particle ids."""
        return self._svc.call("mesh", {})[1]

    def step(self, collider_q: Optional[np.ndarray] = None, frames: int = 1) -> Dict[str, np.ndarray]:
        arrays = {} if collider_q is None else {"collider_q": np.asarray(collider_q, dtype=np.float32).reshape(-1, 7)}
        h, out = self._svc.call("step", {"frames": int(frames)}, arrays)
        self.state = out
        self.last_step_seconds = float(h.get("seconds", 0.0))
        return out

    def reset(self, particle_q=None, cable_points=None, collider_q=None) -> Dict[str, np.ndarray]:
        arrays: Arrays = {}
        if particle_q is not None:
            arrays["particle_q"] = np.asarray(particle_q, dtype=np.float32)
        if cable_points is not None:
            arrays["cable_points"] = np.asarray(cable_points, dtype=np.float32)
        if collider_q is not None:
            arrays["collider_q"] = np.asarray(collider_q, dtype=np.float32).reshape(-1, 7)
        _, out = self._svc.call("reset", {}, arrays)
        self.state = out
        return out

    def read_state(self) -> Dict[str, np.ndarray]:
        _, self.state = self._svc.call("state", {})
        return self.state

    def anchor_particles(self, ids, slot: int) -> None:
        self._svc.call("anchor_particles", {"slot": int(slot)}, {"ids": np.asarray(ids, dtype=np.int32)})

    def release_particles(self, ids=None) -> None:
        self._svc.call("release_particles", {}, {} if ids is None else {"ids": np.asarray(ids, dtype=np.int32)})

    def anchor_segments(self, ids, slot: int) -> None:
        self._svc.call("anchor_segments", {"slot": int(slot)}, {"ids": np.asarray(ids, dtype=np.int32)})

    def release_segments(self, ids=None) -> None:
        self._svc.call("release_segments", {}, {} if ids is None else {"ids": np.asarray(ids, dtype=np.int32)})

    def close(self) -> None:
        try:
            self._svc.close()
        except Exception:  # noqa: BLE001
            pass


class DoughClient:
    """One dough world (``mpm.dough``) in the sidecar.  ``points`` are the initial particles (n, 3), ``cfg`` the scene description
    (``DoughScene.world_cfg``), ``pvol`` the particle volume, ``poses`` ``(T, 7)`` the initial tool poses."""

    def __init__(
        self,
        cfg: dict,
        points: np.ndarray,
        pvol: float,
        poses: Optional[np.ndarray] = None,
        client: Optional[NewtonClient] = None,
    ):
        self.cfg = dict(cfg, pvol=float(pvol))
        self.n = len(points)
        arrays: Arrays = {"points": np.asarray(points, np.float32)}
        if poses is not None:
            arrays["poses"] = np.asarray(poses, np.float64).reshape(-1, 7)
        self._client = client or shared_client()
        self.svc = self._client.service("mpm.dough", cfg=self.cfg, arrays=arrays)
        self.q: Optional[np.ndarray] = None
        self.last_head: Dict[str, Any] = {}

    def step(self, poses=None, substeps=None, stats=False, return_q=True) -> Optional[np.ndarray]:
        head: Dict[str, Any] = {"stats": bool(stats), "return_q": bool(return_q)}
        if substeps:
            head["substeps"] = int(substeps)
        arrays = {} if poses is None else {"poses": np.asarray(poses, np.float64).reshape(-1, 7)}
        h, a = self.svc.call("step", head, arrays)
        self.last_head = h
        if return_q:
            self.q = a["q"]
        return self.q

    def submit_step(self, poses=None, substeps=None):
        head: Dict[str, Any] = {"stats": False, "return_q": True}
        if substeps:
            head["substeps"] = int(substeps)
        arrays = {} if poses is None else {"poses": np.asarray(poses, np.float64).reshape(-1, 7)}
        return self.svc.submit("step", head, arrays)

    def finish(self, fut) -> np.ndarray:
        """The particles of a step started with :meth:`submit_step`."""
        h, a = fut.result()
        self.last_head = h
        self.q = a["q"]
        return self.q

    @property
    def wrench(self) -> np.ndarray:
        """Force + torque of the dough on tool 0 in the last finished step (zeros before the first)."""
        return np.asarray((self.last_head or {}).get("wrench", [0.0] * 6), np.float64)

    def reset(self, points=None, poses=None) -> np.ndarray:
        arrays: Arrays = {}
        if points is not None:
            arrays["points"] = np.asarray(points, np.float32)
        if poses is not None:
            arrays["poses"] = np.asarray(poses, np.float64).reshape(-1, 7)
        _, a = self.svc.call("reset", {}, arrays)
        self.q = a["q"]
        return self.q

    def read(self) -> np.ndarray:
        _, a = self.svc.call("read", {}, {})
        self.q = a["q"]
        return self.q

    def stats(self) -> dict:
        h, _ = self.svc.call("stats", {}, {})
        return h

    def close(self):
        self.svc.close()


class PlugPadClient:
    """Client of ``fem.plugpad``: the driver arrays are the two gel-pad poses ``(2, 7)`` (anchored frame, xyzw)."""

    def __init__(self, cfg: dict, pads: np.ndarray, client: Optional[NewtonClient] = None):
        self.cfg = dict(cfg)
        self._client = client or shared_client()
        self.svc = self._client.service(
            "fem.plugpad", cfg=self.cfg, arrays={"pads": np.asarray(pads, np.float32).reshape(2, 7)}
        )
        _, a = self.svc.call("mesh", {}, {})
        self.tris = np.asarray(a["tris"], np.int32)
        self.q: Optional[np.ndarray] = None

    def step(self, pads, frames: int = 1) -> np.ndarray:
        _, a = self.svc.call("step", {"frames": int(frames)}, {"pads": np.asarray(pads, np.float32).reshape(2, 7)})
        self.q = a["q"]
        return self.q

    def submit_step(self, pads, frames: int = 1):
        return self.svc.submit("step", {"frames": int(frames)}, {"pads": np.asarray(pads, np.float32).reshape(2, 7)})

    def finish(self, fut) -> np.ndarray:
        _, a = fut.result()
        self.q = a["q"]
        return self.q

    def reset(self, pads=None) -> np.ndarray:
        _, a = self.svc.call("reset", {}, {} if pads is None else {"pads": np.asarray(pads, np.float32).reshape(2, 7)})
        self.q = a["q"]
        return self.q

    def stats(self) -> dict:
        h, _ = self.svc.call("stats", {}, {})
        return h

    def close(self):
        self.svc.close()


class PlugClient:
    """Client of ``fem.plug`` (carrier variant): the driver array is the carrier pose ``(7,)`` (xyzw)."""

    def __init__(self, cfg: dict, pose: Optional[np.ndarray] = None, client: Optional[NewtonClient] = None):
        self.cfg = dict(cfg)
        arrays = {} if pose is None else {"pose": np.asarray(pose, np.float64).reshape(7)}
        self._client = client or shared_client()
        self.svc = self._client.service("fem.plug", cfg=self.cfg, arrays=arrays)
        _, a = self.svc.call("mesh", {}, {})
        self.tris = np.asarray(a["tris"], np.int32)
        self.q: Optional[np.ndarray] = None

    def step(self, pose, frames: int = 1) -> np.ndarray:
        _, a = self.svc.call("step", {"frames": int(frames)}, {"pose": np.asarray(pose, np.float64).reshape(7)})
        self.q = a["q"]
        return self.q

    def submit_step(self, pose, frames: int = 1):
        return self.svc.submit("step", {"frames": int(frames)}, {"pose": np.asarray(pose, np.float64).reshape(7)})

    def finish(self, fut) -> np.ndarray:
        _, a = fut.result()
        self.q = a["q"]
        return self.q

    def reset(self, pose=None) -> np.ndarray:
        _, a = self.svc.call("reset", {}, {} if pose is None else {"pose": np.asarray(pose, np.float64).reshape(7)})
        self.q = a["q"]
        return self.q

    def anchor(self) -> int:
        h, _ = self.svc.call("anchor", {}, {})
        return int(h["anchored"])

    def release(self) -> None:
        self.svc.call("release", {}, {})

    def stats(self) -> dict:
        h, _ = self.svc.call("stats", {}, {})
        return h

    def close(self):
        self.svc.close()
