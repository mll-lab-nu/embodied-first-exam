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

Isolation (the Embodied Olympics screening notes §3): the skill runs from a private copy made of
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
import sys
import tempfile
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
        sha = files_sha(self.src)
        if self.proc is not None and self.proc.alive and sha == self.sha:
            return None
        self._stop()
        self.sha, t0 = sha, time.monotonic()
        rec = {"unit": unit, "sha256": sha}

        def failed(why):
            self.load_error = why
            return {**rec, "ok": False, "error": why, "wall_s": round(time.monotonic() - t0, 4)}

        if not self.src.is_dir():
            return failed(f"no skill directory (write {self.module}.py into it)")
        if sha is None:
            return failed(f"the skill directory is unreadable or larger than {MAX_FILES} files / {MAX_BYTES >> 20} MB")
        if self.copy_to is not None:
            self.copy = self.copy_to
        else:
            self._tmp = self._tmp or Path(tempfile.mkdtemp(prefix="inloop-"))
            self.copy = self._tmp / "skill"
        try:
            copy_skill(self.src, self.copy)
        except (OSError, ValueError) as e:
            return failed(f"copy: {e}")
        if not (self.copy / f"{self.module}.py").is_file():
            return failed(f"no {self.module}.py in the skill directory (a regular file, not a symlink)")
        self.proc = SkillProcess(self.copy, self.module, context={"spec": self.spec}, timeouts=self.timeouts,
                                 load_timeout_s=self.load_timeout_s, limits=self.limits)
        if not self.proc.alive:
            return failed(str((self.proc.errors or ["load failed"])[-1])[-600:])
        self.load_error = None
        return {**rec, "ok": True, "error": None, "wall_s": round(time.monotonic() - t0, 4),
                "functions": list(self.proc.functions)}

    def has(self, fn: str) -> bool:
        return self.proc is not None and self.proc.alive and self.proc.has(fn)

    def call(self, fn: str, args: list, state: dict):
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


def handle(host: SkillHost, q: dict) -> dict:
    op = q.get("op")
    try:
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


def serve(sock_path: str, src: str, copy_to: str | None = None, once: bool = False):
    """Serve one connection at a time (the simulator; a reconnect replaces the previous one) until killed."""
    p = Path(sock_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    host = SkillHost(src, copy_to=copy_to)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(p))
    os.chmod(p, 0o600)  # the simulator connects as root; the skill (nobody) cannot
    srv.listen(1)
    print(f"skillhost: serving {src} on {p}", file=sys.stderr, flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            with conn, conn.makefile("rwb") as f:
                while True:
                    try:
                        q = _recv(f)
                    except (ValueError, OSError):
                        break
                    if q is None:
                        break
                    try:
                        _send(f, handle(host, q))
                    except (TypeError, ValueError):
                        _send(f, {"ok": False, "kind": "error", "error": "the skill returned something that is not JSON"})
                    except OSError:
                        break
            if once:
                break
    finally:
        host.close()
        srv.close()
        p.unlink(missing_ok=True)


class RemoteHost:
    """The simulator's side of `serve`: the same interface over the seat's socket (unix:PATH). A broken connection is
    reopened at the next refresh; meanwhile calls raise SkillError("host", ...): a technical failure, not the
    player's."""

    def __init__(self, sock_path: str, connect_timeout_s: float = 60.0):
        self.path, self.connect_timeout_s = sock_path, float(connect_timeout_s)
        self.sock = self.f = None
        self.conf: dict | None = None
        self.timeouts, self.load_timeout_s = {}, 30.0
        self._status = {"sha256": None, "loaded": False, "functions": [], "load_error": "not connected yet"}
        self.host_errors = 0

    def _connect(self, wait_s: float):
        end = time.monotonic() + wait_s
        while True:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.path)
                self.sock, self.f = s, s.makefile("rwb")
                if self.conf is not None:
                    self._req(self.conf, 10.0)
                return
            except OSError:
                self._drop()
                if time.monotonic() >= end:
                    raise SkillError("host", f"the skill container does not answer at {self.path}")
                time.sleep(0.2)

    def _drop(self):
        for x in (self.f, self.sock):
            try:
                x and x.close()
            except OSError:
                pass
        self.sock = self.f = None

    def _req(self, q: dict, timeout: float) -> dict:
        if self.sock is None:
            raise SkillError("host", "not connected to the skill container")
        try:
            self.sock.settimeout(timeout)
            _send(self.f, q)
            r = _recv(self.f)
        except (OSError, ValueError) as e:
            self._drop()
            self.host_errors += 1
            raise SkillError("host", f"the skill container's connection failed: {type(e).__name__}") from e
        if r is None:
            self._drop()
            self.host_errors += 1
            raise SkillError("host", "the skill container closed the connection")
        return r

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
        self._status = r.get("status") or self._status
        return r.get("load")

    def has(self, fn: str) -> bool:
        return bool(self._status.get("loaded")) and fn in (self._status.get("functions") or [])

    def call(self, fn: str, args: list, state: dict):
        r = self._req({"op": "call", "fn": fn, "args": list(args), "state": state},
                      float(self.timeouts.get(fn, 5.0)) + 10.0)
        if r.get("ok"):
            return r.get("ret")
        if r.get("kind") in ("timeout", "dead"):
            self._status = {**self._status, "loaded": False}
        raise SkillError(r.get("kind", "error"), r.get("error", "?"))

    def status(self) -> dict:
        return dict(self._status)

    def close(self):
        self._drop()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="skillhost.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="serve the skill directory on a Unix socket (the seat's skill container)")
    s.add_argument("--socket", required=True)
    s.add_argument("--skill", required=True, help="the player's skill directory (read-only)")
    s.add_argument("--copy-to", default=None, help="where the private copy runs from (default: a temporary directory)")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        serve(a.socket, a.skill, a.copy_to)


if __name__ == "__main__":
    main()
