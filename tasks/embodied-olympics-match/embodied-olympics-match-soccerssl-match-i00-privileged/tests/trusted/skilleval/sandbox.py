"""Run a deliverable skill in its own process (the parent side of skilleval/host.py): docs/framework_zh.md §9 robot and
mode rule 10 ("does not depend on the match process's state").

    with SkillProcess("/app/output/skill", "aim", context={"spec": spec}, timeouts={"aim": 2}) as skill:
        cmd = skill.call("aim", 4.8, 0.2, state={})          # raises SkillError (error / timeout / dead)

What the child gets: `python3 -I -B` (no PYTHONPATH, no user site, no script directory on its path, no bytecode
written: it can import the standard library, the image's packages and its own directory only), a scrubbed environment
(PATH, HOME=/tmp, LANG, one thread for the numeric libraries; nothing else, so no credentials), its own directory as
the working directory, resource limits (address space, CPU seconds, open files, file size) and, when the parent runs as
root (the evaluation container, tools/skill_eval.py), the unprivileged user `nobody` with no supplementary groups: it
cannot read the simulator, the evaluator or the hidden requests (those are readable by root only there). The parent
owns the clock: a call that does not answer within its limit is a time-out, the process is ended and the skill gives
nothing more in this run. Every answer is logged (`log`) for the determinism probe.

InProcessSkill gives an in-process implementation (the platform's own skill, the reference rows) the same interface.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

HOST_SRC = (Path(__file__).resolve().parent / "host.py").read_text()
NOBODY = 65534
LIMITS = {"address_space_mb": 4096, "cpu_s": 900, "open_files": 256, "file_size_mb": 64}
ENV_KEEP = ("PATH", "LANG", "LC_ALL", "MUJOCO_GL", "PYOPENGL_PLATFORM")


class SkillError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


def _preexec(limits: dict, drop: bool):
    def run():
        import resource

        mb = 1024 * 1024
        for res, val in (
            (resource.RLIMIT_AS, limits["address_space_mb"] * mb),
            (resource.RLIMIT_CPU, limits["cpu_s"]),
            (resource.RLIMIT_NOFILE, limits["open_files"]),
            (resource.RLIMIT_FSIZE, limits["file_size_mb"] * mb),
        ):
            try:
                resource.setrlimit(res, (val, val))
            except (ValueError, OSError):
                pass
        os.setsid()
        if drop:
            os.setgroups([])
            os.setgid(NOBODY)
            os.setuid(NOBODY)

    return run


class SkillProcess:
    def __init__(
        self,
        skill_dir,
        module: str,
        *,
        context: dict | None = None,
        timeouts: dict | None = None,
        default_timeout_s: float = 5.0,
        load_timeout_s: float = 30.0,
        limits: dict | None = None,
        env: dict | None = None,
        python: str | None = None,
    ):
        self.dir = str(Path(skill_dir).resolve())
        self.module = module
        self.timeouts = dict(timeouts or {})
        self.default_timeout_s = default_timeout_s
        self.calls, self.timeouts_hit, self.errors, self.log = 0, 0, [], []
        self.functions: list[str] = []
        self.dropped = os.geteuid() == 0
        base = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
        base.update(
            HOME="/tmp",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONHASHSEED="0",
        )
        base.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        base.update(env or {})
        self.p = subprocess.Popen(
            [python or sys.executable, "-I", "-B", "-c", HOST_SRC, self.dir, module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=base,
            cwd=self.dir,
            preexec_fn=_preexec({**LIMITS, **(limits or {})}, self.dropped),
        )
        self._buf, self.stderr_tail = b"", b""
        self.alive = True
        try:
            r = self._recv(load_timeout_s)
        except SkillError as e:
            self.errors.append(str(e))
            self.close()
            return
        if not r.get("ok"):
            self.errors.append(r.get("error", "load failed"))
            self.close()
            return
        self.functions = list(r.get("functions", []))
        if context:
            self._send({"ctx": context})
            try:
                self._recv(load_timeout_s)
            except SkillError as e:
                self.errors.append(str(e))
                self.close()

    # ------------------------------------------------------------------ pipes
    def _send(self, obj):
        try:
            self.p.stdin.write((json.dumps(obj, allow_nan=False) + "\n").encode())
            self.p.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as e:
            self.close()
            raise SkillError("dead", f"the skill's process ended ({e}); stderr: {self.stderr()}")

    def _drain_err(self):
        try:
            while select.select([self.p.stderr], [], [], 0)[0]:
                chunk = os.read(self.p.stderr.fileno(), 65536)
                if not chunk:
                    break
                self.stderr_tail = (self.stderr_tail + chunk)[-4000:]
        except (OSError, ValueError):
            pass

    def stderr(self) -> str:
        self._drain_err()
        return self.stderr_tail.decode(errors="replace")[-800:]

    def _recv(self, timeout: float) -> dict:
        end = time.monotonic() + timeout
        fd = self.p.stdout.fileno()
        while b"\n" not in self._buf:
            left = end - time.monotonic()
            if left <= 0:
                self.timeouts_hit += 1
                self.close()
                raise SkillError("timeout", f"no answer within {timeout} s")
            r, _, _ = select.select([fd, self.p.stderr], [], [], left)
            if self.p.stderr in r:
                self._drain_err()
            if fd in r:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    self.close()
                    raise SkillError("dead", f"the skill's process ended; stderr: {self.stderr()}")
                self._buf += chunk
                if len(self._buf) > 64 << 20:
                    self.close()
                    raise SkillError("error", "an answer larger than 64 MB")
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            return json.loads(line)
        except ValueError:
            return {"ok": False, "error": f"not JSON: {line[:200]!r}"}

    # ------------------------------------------------------------------ calls
    def has(self, fn: str) -> bool:
        return fn in self.functions

    def call(self, fn: str, *args, **kwargs):
        if not self.alive:
            raise SkillError("dead", "the skill gives no more answers in this run")
        self.calls += 1
        self._send({"fn": fn, "args": list(args), "kwargs": kwargs})
        r = self._recv(float(self.timeouts.get(fn, self.default_timeout_s)))
        if not r.get("ok"):
            self.errors.append(str(r.get("error", "?"))[-600:])
            self.log.append((fn, None))
            raise SkillError("error", str(r.get("error", "?"))[-600:])
        self.log.append((fn, r.get("ret")))
        return r.get("ret")

    def counters(self) -> dict:
        return {"skill_calls": self.calls, "skill_errors": len(self.errors), "skill_timeouts": self.timeouts_hit}

    def close(self):
        self.alive = False
        try:
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        self._drain_err()
        for f in (self.p.stdin, self.p.stdout, self.p.stderr):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class InProcessSkill:
    """The same interface over an in-process object (the platform's implementation): call(fn, *args, **kw)."""

    def __init__(self, impl, context: dict | None = None):
        self.impl, self.context = impl, dict(context or {})
        self.calls, self.timeouts_hit, self.errors, self.log = 0, 0, [], []
        self.functions = [k for k in dir(impl) if not k.startswith("_") and callable(getattr(impl, k))]
        self.alive = True

    def has(self, fn: str) -> bool:
        return fn in self.functions

    def call(self, fn: str, *args, **kwargs):
        self.calls += 1
        try:
            ret = getattr(self.impl, fn)(*args, **{**self.context, **kwargs})
            json.dumps(ret, allow_nan=False)
        except Exception as e:  # noqa: BLE001
            self.errors.append(repr(e)[-600:])
            self.log.append((fn, None))
            raise SkillError("error", repr(e)[-600:])
        self.log.append((fn, ret))
        return ret

    def counters(self) -> dict:
        return {"skill_calls": self.calls, "skill_errors": len(self.errors), "skill_timeouts": 0}

    def close(self):
        self.alive = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
