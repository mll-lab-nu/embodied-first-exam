"""The host of a player's skill during a match (the skill in the loop, skilleval/inloop.py): the skill's files, their
identity, the private copy the skill runs from and its sandboxed process (skilleval/sandbox.py), behind one small
interface that the simulator uses either in process (SkillHost: tests, core.local.play, the local pilot) or over a
Unix socket to the seat's skill container (RemoteHost <-> `serve`, the generated tasks). Standard library only: the
skill container runs this file as a script, without the simulator or the core.

    python3 skillhost.py serve --socket /ipc/skill.sock --skill /player_output/skill [--copy-to /app/output/skill]

The interface (both hosts):
    configure(module, spec, timeouts, load_timeout_s)   the deliverable's module, the public spec, the time limits
    refresh(unit) -> load record or None                 at a unit's start: hash the skill directory, and only if the
                                                         files changed (or nothing runs) copy them and restart the
                                                         process; None when nothing changed
    has(fn) -> bool, call(fn, args, state) -> answer     raises SkillError("error" | "timeout" | "dead" | "host", ...)
    status() -> {sha256, loaded, functions, load_error}
    close()

Isolation (docs: olympiad_review screening/skill_in_loop_design_zh.md §3): the skill runs from a private copy made of
regular files only (no symlink is followed, FIFOs and devices are skipped, at most MAX_BYTES / MAX_FILES), in its own
process (python -I, a scrubbed environment, resource limits, `nobody` when the host runs as root); in a generated
task the host itself runs in the seat's skill container (no network, read-only root, no simulator directory).

Wire protocol (RemoteHost <-> serve): one JSON object per line each way, one request at a time:
    {"op": "configure", ...} | {"op": "refresh", "unit": U} | {"op": "call", "fn", "args", "state"} | {"op": "status"}
    -> {"ok": true, ...} | {"ok": false, "kind": ..., "error": ...}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import threading
import tempfile
import threading
import time
from pathlib import Path

try:
    from .sandbox import SkillError, SkillProcess
except ImportError:  # run as a script in the skill container (no package)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sandbox import SkillError, SkillProcess  # type: ignore  # noqa: E402

MAX_BYTES = 256 << 20  # the skill directory's total size (as tools/skill_eval.py copy_skill)
MAX_FILES = 2000
LINE_MAX = 64 << 20  # one protocol line


def _regular_files(root: Path):
    """(relative path, absolute path) of the regular files under root: no symlink followed or taken, no FIFO, device
    or socket, no __pycache__; sorted; stops with ValueError beyond MAX_FILES / MAX_BYTES."""
    out, total = [], 0
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not os.path.islink(os.path.join(dirpath, d)))
        for f in sorted(files):
            p = Path(dirpath) / f
            try:
                st = p.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            total += st.st_size
            out.append((p.relative_to(root).as_posix(), p))
            if len(out) > MAX_FILES or total > MAX_BYTES:
                raise ValueError(f"the skill directory is larger than {MAX_FILES} files or {MAX_BYTES >> 20} MB")
    return sorted(out)


def _stat_sig(root) -> tuple | None:
    """(relative path, size, mtime_ns) of every regular file under root, sorted; None when unreadable."""
    out = []
    try:
        for dirpath, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in files:
                full = os.path.join(dirpath, name)
                st = os.lstat(full)
                if stat.S_ISREG(st.st_mode):
                    out.append((os.path.relpath(full, root), st.st_size, st.st_mtime_ns))
                if len(out) > MAX_FILES:
                    return None
    except OSError:
        return None
    return tuple(sorted(out))


def files_sha(path) -> str | None:
    """sha256 over the sorted "relative/path\\0<file sha256>" of the skill directory's regular files (no symlinks, no
    __pycache__): the identity of the code a call ran, and of the code the post-match evaluation tests
    (skilleval/evaluate.py). None without the directory or beyond the size limits."""
    p = Path(path)
    if not p.is_dir():
        return None
    try:
        files = _regular_files(p)
    except ValueError:
        return None
    h = hashlib.sha256()
    for rel, f in files:
        try:
            h.update(f"{rel}\0".encode() + hashlib.sha256(f.read_bytes()).digest())
        except OSError:
            return None
    return h.hexdigest()


def copy_skill(src: Path, dst: Path) -> int:
    """Copy the regular files of src to dst (replaced): directories 755, files 644 (readable by `nobody`); bytes."""
    files = _regular_files(Path(src))
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    total = 0
    for rel, f in files:
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, out)
        total += out.stat().st_size
    for p in [dst, *dst.rglob("*")]:
        p.chmod(0o755 if p.is_dir() else 0o644)
    return total


class SkillHost:
    """In-process host: the skill directory `src` (the player's /app/output/skill or a test directory)."""

    no_dir = "no skill directory (write {module}.py into it)"

    def __init__(self, src, copy_to=None, limits: dict | None = None):
        self.src = Path(src)
        self.copy_to = Path(copy_to) if copy_to else None
        self.limits = limits
        self.module, self.spec, self.timeouts, self.load_timeout_s = None, {}, {}, 30.0
        self.proc, self.sha, self.copy, self.load_error = None, None, None, None
        self._tmp = None

    def configure(self, module: str, spec: dict, timeouts: dict | None = None, load_timeout_s: float = 30.0):
        self.module, self.spec = module, spec
        self.timeouts, self.load_timeout_s = dict(timeouts or {}), float(load_timeout_s)

    def refresh(self, unit) -> dict | None:
        # robot_coding_bench (option c): the live server checks at every call; the files are hashed only when a file's
        # path, size or mtime changed (a stat walk of the skill directory per call, about a millisecond for a few files)
        sig = _stat_sig(self.src)
        if self.proc is not None and self.proc.alive and sig is not None and sig == getattr(self, "_sig", None):
            return None
        sha = files_sha(self.src)
        self._sig = sig
        if self.proc is not None and self.proc.alive and sha == self.sha:
            return None
        self._stop()
        self.sha, t0 = sha, time.monotonic()
        rec = {"unit": unit, "sha256": sha}

        def failed(why):
            self.load_error = why
            return {**rec, "ok": False, "error": why, "wall_s": round(time.monotonic() - t0, 4)}

        if not self.src.is_dir():
            return failed(self.no_dir.format(module=self.module))
        if sha is None:
            return failed(f"the skill directory is unreadable or larger than {MAX_FILES} files / {MAX_BYTES >> 20} MB")
        if self.copy_to is not None:
            self.copy = self.copy_to
        else:
            if self._tmp is None:
                self._tmp = Path(tempfile.mkdtemp(prefix="inloop-"))
                self._tmp.chmod(0o755)         # the skill runs as nobody when the host is root: it must reach its copy
            self.copy = self._tmp / "skill"
        try:
            copy_skill(self.src, self.copy)
        except (OSError, ValueError) as e:
            return failed(f"copy: {e}")
        if not (self.copy / f"{self.module}.py").is_file():
            return failed(f"no {self.module}.py in the skill directory (a regular file, not a symlink)")
        try:
            self.proc = SkillProcess(self.copy, self.module, context={"spec": self.spec}, timeouts=self.timeouts,
                                     load_timeout_s=self.load_timeout_s, limits=self.limits)
        except (OSError, subprocess.SubprocessError) as e:                  # the sandbox did not start
            self.proc = None
            return failed(f"sandbox: {type(e).__name__}: {e}"[:600])
        if not self.proc.alive:
            return failed(str((self.proc.errors or ["load failed"])[-1])[-600:])
        self.load_error = None
        return {**rec, "ok": True, "error": None, "wall_s": round(time.monotonic() - t0, 4),
                "functions": list(self.proc.functions)}

    def has(self, fn: str) -> bool:
        return self.proc is not None and self.proc.alive and self.proc.has(fn)

    def call(self, fn: str, args: list, state: dict, wait_s: float | None = None):
        if self.proc is None or not self.proc.alive:
            raise SkillError("dead", self.load_error or "the skill is not running (stopped after a time-out: it is "
                                                        "restarted at the next unit)")
        return self.proc.call(fn, *args, state=state)

    def status(self) -> dict:
        alive = self.proc is not None and self.proc.alive
        return {"sha256": self.sha, "loaded": alive, "functions": list(self.proc.functions) if alive else [],
                "load_error": self.load_error}

    def _stop(self):
        if self.proc is not None:
            self.proc.close()
        self.proc = None

    def close(self):
        self._stop()
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None


# ---------------------------------------------------------------------------------------------- the wire
def _send(f, obj):
    f.write((json.dumps(obj, allow_nan=False) + "\n").encode())
    f.flush()


def _recv(f) -> dict | None:
    line = f.readline(LINE_MAX + 1)
    if not line:
        return None
    if len(line) > LINE_MAX:
        raise ValueError("protocol line too long")
    return json.loads(line)


def handle(host: SkillHost, q: dict, live: bool = False) -> dict:
    """One request. live (the agent's own skill server, core 0.2.34): every call first reloads the skill if its files
    changed (the agent may change it at any time; the new version plays from that call on), and every answer carries
    the version (sha256) it ran with."""
    op = q.get("op")
    try:
        if live and op == "call":
            load = host.refresh("live")
            try:
                ret = host.call(q["fn"], list(q.get("args") or []), q.get("state") or {})
            except SkillError as e:
                return {"ok": False, "kind": e.kind, "error": str(e)[-600:], "load": load, "status": host.status()}
            return {"ok": True, "ret": ret, "load": load, "status": host.status()}
        if op == "configure":
            host.configure(q["module"], q.get("spec") or {}, q.get("timeouts"), q.get("load_timeout_s", 30.0))
            return {"ok": True}
        if op == "refresh":
            return {"ok": True, "load": host.refresh(q.get("unit")), "status": host.status()}
        if op == "status":
            return {"ok": True, "status": host.status()}
        if op == "call":
            return {"ok": True, "ret": host.call(q["fn"], list(q.get("args") or []), q.get("state") or {})}
        return {"ok": False, "kind": "host", "error": f"unknown op {op!r}"}
    except SkillError as e:
        return {"ok": False, "kind": e.kind, "error": str(e)[-600:]}
    except Exception as e:  # noqa: BLE001  (the host never dies of a request)
        return {"ok": False, "kind": "host", "error": f"{type(e).__name__}: {e}"[-600:]}


def tcp_addr(addr: str):
    """(host, port) of "tcp:HOST:PORT", else None (a Unix socket path, optionally "unix:PATH")."""
    if not str(addr).startswith("tcp:"):
        return None
    host, _, port = str(addr)[4:].rpartition(":")
    return host or "127.0.0.1", int(port)


def serve(sock_path: str, src: str, copy_to: str | None = None, once: bool = False, live: bool = False):
    """Serve one connection at a time (the simulator; a reconnect replaces the previous one) until killed. sock_path:
    a Unix socket (the seat's skill container) or "tcp:127.0.0.1:PORT" (core 0.2.34: the agent's own container, which
    shares its network namespace with the simulator: the simulator connects to it over the loopback)."""
    host = SkillHost(src, copy_to=copy_to)
    tcp = tcp_addr(sock_path)
    if tcp is not None:
        p = None
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(tcp)                      # the loopback only: nothing outside the trial's network namespace
    else:
        p = Path(sock_path[5:] if sock_path.startswith("unix:") else sock_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(p))
        os.chmod(p, 0o600)  # the simulator connects as root; the skill (nobody) cannot
    srv.listen(8)
    print(f"skillhost: serving {src} on {sock_path}{' (live reload)' if live else ''}", file=sys.stderr, flush=True)
    lock = threading.Lock()                # one request at a time on the host (the skill answers one call)

    def session(conn):
        with conn, conn.makefile("rwb") as f:
            while True:
                try:
                    q = _recv(f)
                except (ValueError, OSError):
                    break
                if q is None:
                    break
                with lock:
                    r = handle(host, q, live)
                try:
                    _send(f, r)
                except (TypeError, ValueError):
                    _send(f, {"ok": False, "kind": "error", "error": "the skill returned something that is not JSON"})
                except OSError:
                    break

    try:
        while True:
            conn, _ = srv.accept()
            if once:
                session(conn)
                break
            # live (the agent's server): the simulator's connection and the agent's own `game skill status` at once
            threading.Thread(target=session, args=(conn,), daemon=True).start() if live else session(conn)
    finally:
        host.close()
        srv.close()
        if p is not None:
            p.unlink(missing_ok=True)


# robot_coding_bench (board 0146, #300 review): the agent serves its own skill (core 0.2.34): the simulator reads only the fields it needs from
# its answers, each of its own type, so no answer of the agent's server can raise inside the control step (a world_step
# technical error) or put an unhashable value in the call log (tests/fexam_reward.py); anything else is no status.
_LOAD_KEYS = ("unit", "sha256", "ok", "error", "wall_s", "host_error", "live", "k")
LIVE_MARGIN_S = 1.0          # live: the transport's allowance over a function's own time limit (same machine, loopback)
LIVE_LINE_MAX = 1 << 20      # live: one answer (a command and a status) at most 1 MiB, so its parse stays short
LIVE_RETRY_S = 1.0           # live: a server that is not up / not loaded is tried again at most this often by step()
STEP_LINE_MAX = 128 << 10    # live, step() (a bounded synchronous call, parsed on the world's thread): at most 128 KiB
                             # (a full answer, a 50-row plan of 9 targets and the status, is well under 64 KiB)


def _sha(v):
    return v if isinstance(v, str) and 0 < len(v) <= 128 else None


def _clean_status(st, old: dict) -> dict:
    if not isinstance(st, dict):
        return old
    fns, err = st.get("functions"), st.get("load_error")
    return {"sha256": _sha(st.get("sha256")), "loaded": st.get("loaded") is True,
            "functions": [f for f in fns if isinstance(f, str)][:64] if isinstance(fns, list) else [],
            "load_error": None if err is None else str(err)[:2000]}


def _clean_load(rec, unit):
    if not isinstance(rec, dict):
        return None
    out = {k: rec[k] for k in _LOAD_KEYS if k in rec and isinstance(rec[k], (str, int, float, bool, type(None)))}
    out["unit"], out["sha256"], out["ok"] = unit, _sha(rec.get("sha256")), rec.get("ok") is True
    return out


class RemoteHost:
    """The simulator's side of `serve`: the same interface over the seat's socket (unix:PATH). A broken connection is
    reopened at the next refresh; meanwhile calls raise SkillError("host", ...). live ("tcp:127.0.0.1:PORT", the
    agent's own skill server in the agent's container; robot_coding_bench (board 0152 decision 28, option c)): the server is the player's, so
    every failure of it (not started, refused, closed, slow, malformed) is the player's: the call lowers to the no-op,
    never a technical failure; each call waits at most `wait_s` (the caller's bound: one control period for step()) or
    the function's time limit + LIVE_MARGIN_S, after which the connection is dropped (its late answer can never be
    read as the next call's) and the call is a time-out."""

    def __init__(self, sock_path: str, connect_timeout_s: float = 60.0, live: bool = False):
        # live (core 0.2.34, "tcp:127.0.0.1:PORT"): the agent's own skill server in its container; it may be down
        # (not started, restarted): a call reconnects quickly, and a missing server is the player's error ("noserver")
        self.path, self.connect_timeout_s = sock_path, float(2.0 if live else connect_timeout_s)
        self.live, self.tcp = live, tcp_addr(sock_path)
        self.sock = self.f = None
        self.conf: dict | None = None
        self.timeouts, self.load_timeout_s = {}, 30.0
        self._status = {"sha256": None, "loaded": False, "functions": [], "load_error": "not connected yet"}
        self.host_errors = 0
        self._retry_at = 0.0

    def _connect(self, wait_s: float, conf_timeout: float = 10.0, end_by: float | None = None):
        """end_by (live): the caller's deadline; the connection and its configure both end by it (the configure gets
        the time left when it is sent, a timeout when none is left)."""
        end = time.monotonic() + wait_s
        if end_by is not None:
            end = min(end, end_by)
        while True:
            try:
                if self.tcp is not None:      # live: never past the caller's bound (the world may be waiting)
                    s = socket.create_connection(self.tcp, timeout=(max(0.001, min(2.0, end - time.monotonic()))
                                                                    if self.live else max(0.2, min(2.0, wait_s))))
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.path[5:] if self.path.startswith("unix:") else self.path)
                self.sock, self.f = s, s.makefile("rwb")
                if self.conf is not None:
                    if end_by is not None:
                        left = end_by - time.monotonic()
                        if left <= 0:
                            self._drop()
                            raise SkillError("timeout", "no time left for the skill server's configure")
                        conf_timeout = left
                    self._req(self.conf, conf_timeout)
                return
            except OSError:
                self._drop()
                if time.monotonic() >= end:
                    if self.live:
                        raise SkillError("noserver", f"no skill server answers at {self.path} (start it: game skill "
                                                     "serve /app/output/skill)")
                    raise SkillError("host", f"the skill container does not answer at {self.path}")
                time.sleep(min(0.2, max(0.0, end - time.monotonic())) if self.live else 0.2)

    def _drop(self):
        for x in (self.f, self.sock):
            try:
                x and x.close()
            except OSError:
                pass
        self.sock = self.f = None

    def _req(self, q: dict, timeout: float, max_bytes: int | None = None) -> dict:
        if self.sock is None:
            raise SkillError("host", "not connected to the skill container")
        bad = "server" if self.live else "host"        # live: the agent's own server, every failure the player's
        end = time.monotonic() + timeout              # live: ONE deadline for the request, its send included
        try:
            if self.live:
                line = (json.dumps(q, allow_nan=False) + "\n").encode()
                self.sock.settimeout(max(0.001, end - time.monotonic()))
                self.sock.sendall(line)               # a server that withholds its receive window times out here
                r = self._recv_by(end, LIVE_LINE_MAX if max_bytes is None else max_bytes)
            else:
                self.sock.settimeout(timeout)
                _send(self.f, q)
                r = _recv(self.f)
        except (OSError, ValueError, RecursionError, MemoryError) as e:   # option c: e.g. JSON nested too deep
            self._drop()
            self.host_errors += 1
            if self.live and isinstance(e, TimeoutError):     # option c: the agent's server did not answer in time
                raise SkillError("timeout", f"your skill server gave no answer within {timeout:.3f} s") from e
            raise SkillError(bad, f"the skill server's connection failed: {type(e).__name__}: {str(e)[:200]}") from e
        if r is None:
            self._drop()
            self.host_errors += 1
            raise SkillError(bad, "the skill server closed the connection")
        if not isinstance(r, dict):                    # robot_coding_bench (board 0146, #300 review)
            self._drop()
            self.host_errors += 1
            raise SkillError(bad, "the skill server's answer is not a JSON object")
        return r

    def _recv_by(self, end: float, max_bytes: int = LIVE_LINE_MAX):
        """live (option c): one answer line read by a deadline for the whole line (a socket timeout bounds each read
        only: a server that drips its answer would hold the caller, and the world, past any bound)."""
        buf = bytearray()
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError("the answer did not arrive in time")
            self.sock.settimeout(left)
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                return None
            i = chunk.find(b"\n")
            if i >= 0:
                buf += chunk[:i + 1]
                if len(buf) > max_bytes + 1:
                    raise ValueError(f"answer longer than {max_bytes} bytes")
                if len(chunk) > i + 1:          # the protocol is one answer per request: anything after it is not ours
                    raise ValueError("more than one answer line")
                return json.loads(bytes(buf))
            buf += chunk
            if len(buf) > max_bytes:
                raise ValueError(f"answer longer than {max_bytes} bytes")

    def configure(self, module: str, spec: dict, timeouts: dict | None = None, load_timeout_s: float = 30.0):
        self.conf = {"op": "configure", "module": module, "spec": spec, "timeouts": dict(timeouts or {}),
                     "load_timeout_s": float(load_timeout_s)}
        self.timeouts, self.load_timeout_s = dict(timeouts or {}), float(load_timeout_s)

    def refresh(self, unit) -> dict | None:
        try:
            if self.sock is None:
                self._connect(self.connect_timeout_s)
            r = self._req({"op": "refresh", "unit": unit}, self.load_timeout_s + 30.0)
        except SkillError as e:
            self._status = {"sha256": None, "loaded": False, "functions": [], "load_error": str(e)}
            return {"unit": unit, "sha256": None, "ok": False, "error": str(e), "wall_s": 0.0, "host_error": True}
        self._status = _clean_status(r.get("status"), self._status)     # robot_coding_bench (board 0146, #300 review)
        return _clean_load(r.get("load"), unit)

    def has(self, fn: str) -> bool:
        if bool(self._status.get("loaded")) and fn in (self._status.get("functions") or []):
            return True
        # live (option c): a server that was down, or not loaded, is retried at most once a second (one bounded call;
        # a refused connection costs nothing), so step() comes back without waiting for the next unit
        return bool(self.live and not self._status.get("loaded") and time.monotonic() >= self._retry_at)

    def _stale(self) -> bool:
        """live: data waiting on the connection before a request is sent (an answer nobody asked for, or the server
        closed it): the connection is not trusted for the next answer."""
        try:
            self.sock.settimeout(0.0)         # non-blocking: a socket with a timeout would wait for data first
            return self.sock.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) is not None
        except (BlockingIOError, InterruptedError):
            return False
        except OSError:
            return True

    def call(self, fn: str, args: list, state: dict, wait_s: float | None = None):
        if self.live:            # option c: one bound for the whole call (connecting included)
            bound = float(wait_s) if wait_s is not None else float(self.timeouts.get(fn, 5.0)) + LIVE_MARGIN_S
            end = time.monotonic() + bound
            if not self._status.get("loaded"):          # a try of a server that was down: the next one in a second
                self._retry_at = time.monotonic() + LIVE_RETRY_S
            if self.sock is not None and self._stale():
                self._drop()
        if self.live and self.sock is None:
            try:      # the connection and its configure inside the same deadline
                self._connect(max(0.005, min(0.5, bound)), end_by=end)
            except SkillError as e:
                if e.kind != "timeout":      # a server that is there but slow keeps its status (the next call retries)
                    self._status = {"sha256": None, "loaded": False, "functions": [], "load_error": str(e)}
                raise
        r = self._req({"op": "call", "fn": fn, "args": list(args), "state": state},
                      max(0.001, end - time.monotonic()) if self.live else
                      float(self.timeouts.get(fn, 5.0)) + 10.0,
                      STEP_LINE_MAX if (self.live and wait_s is not None) else None)
        if isinstance(r.get("status"), dict):          # live: the version this call ran with
            self._status = _clean_status(r["status"], self._status)     # robot_coding_bench (board 0146, #300 review)
        if r.get("ok"):
            return r.get("ret")
        if r.get("kind") in ("timeout", "dead"):
            self._status = {**self._status, "loaded": False}
        kind = r.get("kind") if r.get("kind") in ("timeout", "dead", "error", "load", "noserver") else "error"
        raise SkillError(kind, str(r.get("error", "?"))[:2000])

    def status(self) -> dict:
        return dict(self._status)

    def close(self):
        self._drop()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="skillhost.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="serve the skill directory on a Unix socket (the seat's skill container)")
    s.add_argument("--socket", default=None)
    s.add_argument("--tcp", default=None, help="HOST:PORT (core 0.2.34: the agent's own container, the loopback)")
    s.add_argument("--live", action="store_true", help="reload the skill whenever its files change (at each call)")
    s.add_argument("--skill", required=True, help="the player's skill directory (read-only)")
    s.add_argument("--copy-to", default=None, help="where the private copy runs from (default: a temporary directory)")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        if not a.socket and not a.tcp:
            ap.error("serve needs --socket or --tcp")
        serve(f"tcp:{a.tcp}" if a.tcp else a.socket, a.skill, a.copy_to, live=a.live)


if __name__ == "__main__":
    main()
