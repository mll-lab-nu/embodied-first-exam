"""Trusted proxy and separate, restricted policy interpreter.

Production requires Linux, root worker and a distinct policy UID. Unprivileged
unit tests explicitly disable OS isolation; that option is not a worker CLI flag.
"""
import argparse
import ctypes
import ctypes.util
import errno
import os
from pathlib import Path
import pwd
import resource
import signal
import subprocess
import sys
import threading

from .protocol import decode, encode, loads, receive, send


class PolicyCancelled(BaseException):
    pass


def restrict_process(user, directory):
    """Drop privilege before loading source. Filter applies to descendants too."""
    if os.geteuid() != 0:
        raise PermissionError("Production policy isolation requires a root worker")
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise PermissionError("Policy user cannot be root")
    seccomp = ctypes.CDLL(ctypes.util.find_library("seccomp") or "libseccomp.so.2")
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "no_new_privs")
    os.chown(directory, account.pw_uid, account.pw_gid)
    os.chmod(directory, 0o700)
    os.chdir(directory)
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    ctx = seccomp.seccomp_init(0x7FFF0000)  # default allow; explicit denied capabilities
    if not ctx:
        raise RuntimeError("seccomp_init failed")
    try:
        # No sockets (including worker/admin/GPU services), process inspection,
        # new programs, namespace changes, or escaping killpg cancellation.
        for name in ("socket", "socketpair", "connect", "ptrace", "process_vm_readv",
                     "process_vm_writev", "mount", "umount2", "unshare", "setns",
                     "setsid", "setpgid", "execve", "execveat", "bpf", "io_uring_setup", "ioctl"):
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and seccomp.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError("seccomp_rule_add failed")
        if seccomp.seccomp_load(ctx) != 0:
            raise RuntimeError("seccomp_load failed")
    finally:
        seccomp.seccomp_release(ctx)


class RemotePolicyProxy:
    def __init__(self, submission, directory, *, isolated=True, user="policy"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o711)
        # Parent is root-owned; child cwd is exclusively owned by the policy UID.
        work = self.directory / "cwd"
        work.mkdir(mode=0o700)
        self.cancelled = threading.Event()
        self._close_lock = threading.Lock()
        self._closed = False
        self.log = (self.directory / "stderr.log").open("wb")
        args = [sys.executable, "-I", "-m", __name__, "--directory", str(work)]
        if isolated:
            args += ["--user", user]
        else:
            args += ["--unit-test-no-isolation"]
        # Source checkout only for tests: -I deliberately ignores PYTHONPATH.
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, start_new_session=True, cwd="/", env={
                "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
        self.submission = submission
        self.started = False

    def _call(self, method, *values):
        if self.cancelled.is_set():
            raise PolicyCancelled()
        try:
            if not self.started:
                send(self.process.stdin, self.submission)
                self.started = True
            send(self.process.stdin, {"method": method, "args": encode(values)})
            reply = receive(self.process.stdout)
        except (EOFError, BrokenPipeError, OSError, ValueError):
            if self.cancelled.is_set():
                raise PolicyCancelled() from None
            raise RuntimeError("policy_process_exited") from None
        if not isinstance(reply, dict) or set(reply) != {"ok", "value"} or reply["ok"] is not True:
            raise RuntimeError("policy_process_error")
        return decode(reply["value"])

    def initialize(self, context):
        return self._call("initialize", context)

    def act(self, observation):
        return self._call("act", observation)

    def on_segment_end(self, observation, result):
        # Core catches Exception for this callback; don't re-raise cancellation.
        if self.cancelled.is_set():
            return None
        return self._call("on_segment_end", observation, result)

    def cancel(self):
        self.cancelled.set()
        self.close()

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=5)
            for stream in (self.process.stdin, self.process.stdout, self.log):
                try:
                    stream.close()
                except BrokenPipeError:
                    pass  # child exit may leave a buffered request on stdin
            self._closed = True


def child_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--user", default="policy")
    parser.add_argument("--unit-test-no-isolation", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    source_stream, sink = sys.stdin.buffer, sys.stdout.buffer
    # Keep stdout exclusively for framed transport, including native extension prints.
    transport = os.fdopen(os.dup(sink.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    if not args.unit_test_no_isolation:
        restrict_process(args.user, args.directory)
    else:
        os.chdir(args.directory)
    submission = receive(source_stream)
    try:
        namespace = {"__name__": "submitted_policy"}
        exec(compile(submission["source_utf8"], "submitted_policy.py", "exec"), namespace)
        policy = namespace["create_policy"](**submission["parameters"])
        if not callable(getattr(policy, "act", None)):
            raise TypeError("Policy requires act")
        while True:
            message = receive(source_stream)
            if message["method"] not in {"initialize", "act", "on_segment_end"}:
                raise ValueError("Unknown policy call")
            method = getattr(policy, message["method"], None)
            result = None if method is None else method(*decode(message["args"]))
            send(transport, {"ok": True, "value": encode(result)})
    except EOFError:
        return
    except BaseException:
        import traceback
        traceback.print_exc(file=sys.stderr)
        send(transport, {"ok": False, "value": None})


if __name__ == "__main__":
    child_main()
