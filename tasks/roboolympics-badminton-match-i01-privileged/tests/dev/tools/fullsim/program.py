"""The submitted program's process: JSON views in, commands out (an API and process boundary; the container boundary
is the verifier's: nobody, no network, no read access to the trusted simulator)."""

from __future__ import annotations

import json
import os
import select
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def child_env():
    keys = ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
    env = {k: os.environ[k] for k in keys if k in os.environ}
    env.update(
        MUJOCO_GL="disable",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


class Program:
    def __init__(self, path, output, initial, *, worker_root=None, identity=None, workdir=None, cpu_s=1800):
        self.stderr = (output / "policy.stderr").open("wb")
        self.p = subprocess.Popen(
            [sys.executable, "-I", str((worker_root or ROOT) / "tools/fullsim/worker.py"), str(path), str(int(cpu_s))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            cwd=workdir or output,
            user=identity,
            group=identity,
            extra_groups=[] if identity is not None else None,
            start_new_session=True,
            env=child_env(),
            bufsize=0,
        )
        self.buf = b""
        try:
            deadline = time.monotonic() + 30
            self.send(initial)
            while time.monotonic() < deadline:
                message = self.poll()
                if message is not None:
                    if message != {"ready": True}:
                        raise RuntimeError("invalid program startup response")
                    return
                time.sleep(0.002)
            raise TimeoutError("program load exceeded 30s")
        except BaseException:
            self.close()
            raise

    def send(self, obj, timeout=5):
        payload = (json.dumps(obj, allow_nan=False) + "\n").encode()
        if len(payload) > 1024 * 1024:
            raise ValueError("policy view exceeds 1 MiB")
        fd = self.p.stdin.fileno()
        os.set_blocking(fd, False)
        deadline = time.monotonic() + timeout
        offset = 0
        while offset < len(payload):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("program did not read its input within the call deadline")
            if self.p.poll() is not None:
                raise BrokenPipeError("program exited before consuming input")
            if not select.select([], [fd], [], min(remaining, 0.05))[1]:
                continue
            try:
                offset += os.write(fd, payload[offset:])
            except BlockingIOError:
                continue

    def poll(self):
        if select.select([self.p.stdout], [], [], 0)[0]:
            data = os.read(self.p.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError(f"program exited ({self.p.poll()}); see policy.stderr")
            self.buf += data
        if len(self.buf) > 1024 * 1024:
            raise ValueError("program response exceeds 1 MiB")
        if b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            return json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if self.p.poll() is not None:
            raise RuntimeError(f"program exited ({self.p.returncode}); see policy.stderr")
        return None

    def close(self):
        # start_new_session gives this exact child PID its own process group.
        # Signal it even if the main policy exited, so forked helpers cannot linger.
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.p.wait()
        try:
            os.killpg(self.p.pid, signal.SIGKILL)  # helpers may ignore TERM after the main process exits
        except ProcessLookupError:
            pass
        self.p.stdin.close()
        self.p.stdout.close()
        self.stderr.close()


def end_uid_processes(uid, rounds=50):
    """Kill every process of the policy's user that is still alive (a double fork or setsid leaves the program's
    process group), until none is left; raises if one survives. Nothing is graded before this returns."""
    for _ in range(rounds):
        alive = []
        for d in Path("/proc").iterdir():
            if not d.name.isdigit():
                continue
            try:
                if d.stat().st_uid == uid:
                    alive.append(int(d.name))
            except OSError:
                continue
        if not alive:
            return
        for pid in alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.05)
    raise RuntimeError(f"processes of uid {uid} survive")


def sanitize(source, destination):
    """Copy bounded regular files only. Never follow an agent-controlled link."""
    if not source.is_dir() or source.is_symlink():
        raise ValueError("submit a real policy/ directory containing program.py")
    total = count = 0
    destination.mkdir(mode=0o755)
    for p in sorted(source.rglob("*")):
        mode = p.lstat().st_mode
        target = destination / p.relative_to(source)
        if stat.S_ISDIR(mode):
            target.mkdir(mode=0o755, exist_ok=True)
            continue
        if not stat.S_ISREG(mode) or p.is_symlink():
            raise ValueError("policy contains a symlink, device, FIFO or socket")
        count += 1
        total += p.stat().st_size
        if count > 512 or total > 32 * 1024**2:
            raise ValueError("policy exceeds 512 files or 32 MiB")
        # Files are copied, not imported/executed by the trusted evaluator.
        with p.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        target.chmod(0o644)
    if not (destination / "program.py").is_file():
        raise ValueError("missing policy/program.py")
