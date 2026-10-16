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

Nothing the skill starts outlives it (robot coding bench, board 0111: a detached child of the skill could otherwise
rewrite the report after the evaluation): the parent is the subreaper of its process tree (PR_SET_CHILD_SUBREAPER), so a
process the skill detaches (double fork, setsid) is re-parented to it, and close() ends the skill's session and then every
process below the parent that runs as the sandbox user, until none is left (`end_sandbox_processes`). RLIMIT_NPROC
bounds how many the skill can start.

InProcessSkill gives an in-process implementation (the platform's own skill, the reference rows) the same interface.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

HOST_SRC = (Path(__file__).resolve().parent / "host.py").read_text()
NOBODY = 65534
# processes: RLIMIT_NPROC counts every process (and thread) of the user on the host, not only this sandbox's: generous,
# so that a few unrelated `nobody` processes elsewhere never stop the skill from starting
LIMITS = {"address_space_mb": 4096, "cpu_s": 900, "open_files": 256, "file_size_mb": 64, "processes": 128}
ENV_KEEP = ("PATH", "LANG", "LC_ALL", "MUJOCO_GL", "PYOPENGL_PLATFORM")


class SkillError(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


# The jail of a skill that runs inside the simulator's own container (skilleval/skillhost.py UploadHost: the skill the
# player uploads to the match service, core 0.2.32), where no container boundary cuts the network or the CPU off:
# no_network  a seccomp filter (set after the drop, with no_new_privs): socket() of any family but AF_UNIX and
#             io_uring_setup fail with EPERM, an x32 or foreign-ABI system call ends the process; the filter is
#             inherited by everything the skill starts. Fails closed: on an architecture without a table the skill does
#             not start.
# one_cpu     the skill's process tree is pinned to one CPU of the container's set, the least busy one when it starts
#             (the skill container had cpus: 1)
_SECCOMP_ARCH = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198)}   # AUDIT_ARCH_*, __NR_socket
_NR_IO_URING_SETUP = 425


def _seccomp_program():
    """(prctl, the filter's sock_fprog) prepared in the parent (no dlopen after fork)."""
    import ctypes
    import platform
    import struct

    machine = platform.machine()
    if machine not in _SECCOMP_ARCH:
        raise OSError(f"no seccomp table for {machine}: the skill cannot run without the network jail")
    audit, nr_socket = _SECCOMP_ARCH[machine]
    LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06            # BPF_LD|W|ABS, BPF_JMP|JEQ|K, BPF_JMP|JGE|K, BPF_RET|K
    ALLOW, EPERM, KILL = 0x7FFF0000, 0x00050000 | 1, 0x80000000
    prog = [(LD, 0, 0, 4),                                 # 0 arch
            (JEQ, 1, 0, audit),                            # 1 -> 3
            (RET, 0, 0, KILL),                             # 2 a foreign ABI
            (LD, 0, 0, 0),                                 # 3 nr
            (JGE, 5, 0, 0x40000000),                       # 4 x32 -> 10
            (JEQ, 4, 0, _NR_IO_URING_SETUP),               # 5 -> 10
            (JEQ, 0, 2, nr_socket),                        # 6 -> 7, else 9
            (LD, 0, 0, 16),                                # 7 args[0] (the family, low 32 bits)
            (JEQ, 0, 1, 1),                                # 8 AF_UNIX -> 9, else 10
            (RET, 0, 0, ALLOW),                            # 9
            (RET, 0, 0, EPERM)]                            # 10
    buf = ctypes.create_string_buffer(b"".join(struct.pack("=HBBI", *ins) for ins in prog))

    class Fprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

    fprog = Fprog(len(prog), ctypes.cast(buf, ctypes.c_void_p))
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
    return libc.prctl, fprog, buf


def _idlest_cpu(sample_s: float = 0.05):
    """The least busy CPU of this process's set over a short sample (/proc/stat), so that the skills of trials sharing
    a host do not all land on one core; the first CPU of the set without /proc/stat."""
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus:
        return None

    def busy():
        out = {}
        try:
            with open("/proc/stat") as f:
                for line in f:
                    if line.startswith("cpu") and line[3:4].isdigit():
                        x = line.split()
                        v = [int(n) for n in x[1:]]
                        out[int(x[0][3:])] = (sum(v) - v[3] - (v[4] if len(v) > 4 else 0), sum(v))
        except (OSError, ValueError):
            pass
        return out

    a = busy()
    time.sleep(sample_s)
    b = busy()
    load = {c: (b[c][0] - a[c][0]) / max(1, b[c][1] - a[c][1]) for c in cpus if c in a and c in b}
    return min(load, key=lambda c: (load[c], c)) if load else cpus[0]


def _preexec(limits: dict, drop: bool, jail: dict | None = None):
    jail = dict(jail or {})
    seccomp = _seccomp_program() if jail.get("no_network") else None
    cpu = _idlest_cpu() if jail.get("one_cpu") else None

    def run():
        import ctypes
        import resource

        mb = 1024 * 1024
        for res, val in (
            (resource.RLIMIT_AS, limits["address_space_mb"] * mb),
            (resource.RLIMIT_CPU, limits["cpu_s"]),
            (resource.RLIMIT_NOFILE, limits["open_files"]),
            (resource.RLIMIT_FSIZE, limits["file_size_mb"] * mb),
            # as nobody only: for another user the count includes all of that user's own processes
            *([(resource.RLIMIT_NPROC, limits["processes"])] if drop else []),
        ):
            try:
                resource.setrlimit(res, (val, val))
            except (ValueError, OSError):
                pass
        os.setsid()
        if cpu is not None:
            os.sched_setaffinity(0, {cpu})
        if drop:
            os.setgroups([])
            os.setgid(NOBODY)
            os.setuid(NOBODY)
        if seccomp is not None:
            prctl, fprog, _buf = seccomp
            if prctl(38, 1, None, 0, 0) != 0:                              # PR_SET_NO_NEW_PRIVS
                raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
            if prctl(22, 2, ctypes.addressof(fprog), 0, 0) != 0:          # PR_SET_SECCOMP, SECCOMP_MODE_FILTER
                raise OSError(ctypes.get_errno(), "PR_SET_SECCOMP failed")

    return run


def _subreaper() -> bool:
    """This process adopts every orphan below it (prctl PR_SET_CHILD_SUBREAPER = 36), so that a process the skill
    detaches stays in its tree, where end_sandbox_processes finds it. Linux only; False where it is not available."""
    try:
        import ctypes

        return ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    except Exception:  # noqa: BLE001
        return False


def _proc_table() -> dict:
    """{pid: (ppid, real uid)} of every process this one can see."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{d}/status") as f:
                uid = next(int(line.split()[1]) for line in f if line.startswith("Uid:"))
        except (OSError, ValueError, IndexError, StopIteration):
            continue
        out[int(d)] = (ppid, uid)
    return out


def _reap(pids):
    """Collect the exit of those of `pids` that are this process's children (an adopted orphan included); never a
    wait on any child, which would take another subprocess's status from its owner."""
    for p in pids:
        try:
            os.waitpid(p, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


def end_sandbox_processes(uid: int = NOBODY, within_s: float = 10.0) -> int:
    """SIGKILL every process below this one that runs as `uid` (the sandbox user), round after round until none is
    left, and reap them. Returns how many were sent the signal. With the subreaper set, a skill's detached processes
    are below this one too. Raises if one is still there after `within_s`."""
    me, sent, end = os.getpid(), 0, time.monotonic() + within_s
    while time.monotonic() < end:
        table = _proc_table()
        kids: dict = {}
        for pid, (ppid, _) in table.items():
            kids.setdefault(ppid, []).append(pid)
        below, todo = [], [me]
        while todo:
            for c in kids.get(todo.pop(), []):
                below.append(c)
                todo.append(c)
        victims = [p for p in below if table[p][1] == uid]
        if not victims:
            return sent
        for p in victims:
            try:
                os.kill(p, signal.SIGKILL)
                sent += 1
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(0.005)
        _reap(victims)
    raise RuntimeError(f"processes of uid {uid} still alive {within_s} s after SIGKILL")


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
        sweep_uid: int | None = None,
        jail: dict | None = None,
    ):
        self.dir = str(Path(skill_dir).resolve())
        self.module = module
        self.timeouts = dict(timeouts or {})
        self.default_timeout_s = default_timeout_s
        self.calls, self.timeouts_hit, self.errors, self.log = 0, 0, [], []
        self.functions: list[str] = []
        self.dropped = os.geteuid() == 0
        self.reaper = _subreaper()
        # whose processes below this one close() ends: the sandbox user's when the skill runs as it (the official
        # evaluation), else only a caller's explicit choice (a test); without it, close() ends the skill's session only
        self.sweep_uid = NOBODY if self.dropped else sweep_uid
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
            preexec_fn=_preexec({**LIMITS, **(limits or {})}, self.dropped, jail),
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
            os.killpg(self.p.pid, signal.SIGKILL)   # the skill's session (it is its own group leader: setsid)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        if self.sweep_uid is not None:              # and whatever it started, detached or not (raises if one survives)
            end_sandbox_processes(self.sweep_uid)
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
