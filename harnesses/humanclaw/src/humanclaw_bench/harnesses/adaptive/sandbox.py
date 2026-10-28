"""OS-isolated task programs with pipe-only, broker-mediated environment access.

Scientific workspaces add explicitly copied packages and task files.
No evaluator, credentials, source repository, or validation oracles are mounted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


WORKER = '''import json, sys, resource, os
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
resource.setrlimit(resource.RLIMIT_FSIZE, (33554432, 33554432))
if sys.platform == "linux": resource.setrlimit(resource.RLIMIT_AS, (2147483648, 2147483648))
payload = json.loads(sys.stdin.readline())
sys.path[:0] = payload.get("import_paths", [])
if payload.get("workspace"): os.chdir(payload["workspace"] + "/outputs")
def tools(request):
    print(json.dumps({"call": request}), flush=True)
    response = json.loads(sys.stdin.readline())
    if "error" in response: raise RuntimeError(response["error"])
    return response["value"]
namespace = {}
exec(compile(payload["source"], "candidate.py", "exec"), namespace)
result = namespace["run"](payload["input"], tools)
print(json.dumps({"result": result}, allow_nan=False), flush=True)
'''


def command(directory: Path, workspace=None, sources=None):
    """Build a fail-closed OS sandbox with a minimal read-only runtime."""
    python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    base = Path(sys.base_prefix).resolve()
    if sys.platform == "darwin":
        executable = shutil.which("sandbox-exec")
        if not executable:
            raise RuntimeError("sandbox-exec is required; refusing unsandboxed candidate")
        paths = [str(base), str(directory), "/System", "/usr/lib", "/usr/share/locale", "/dev/null", "/dev/urandom", "/private/var/db/timezone"]
        paths += [str(p) for p in (workspace, sources) if p is not None]
        # Homebrew interpreter dependency dylibs live in opt symlinks / Cellar.
        for root in ("/opt/homebrew/Cellar", "/opt/homebrew/opt"):
            if Path(root).is_dir():
                paths.append(root)
        policy = '(version 1)(deny default)(allow sysctl-read)(allow mach-lookup)'
        policy += '(allow process-exec (literal ' + json.dumps(str(python)) + '))'
        policy += '(allow file-read* ' + ' '.join('(subpath ' + json.dumps(p) + ')' for p in paths) + ')'
        policy += '(allow file-read-metadata)(allow file-read* (literal "/"))(allow file-write* (literal "/dev/null"))'
        if workspace:
            policy += '(allow file-write* ' + ' '.join('(subpath ' + json.dumps(str(workspace / name)) + ')' for name in ("outputs", "tmp")) + ')'
        return [executable, "-p", policy, str(python), "-I", "-S", str(directory / "worker.py")]
    if sys.platform == "linux":
        executable = shutil.which("bwrap") or os.environ.get("HUMANCLAW_BWRAP")
        if not executable or not Path(executable).is_file():
            raise RuntimeError("bubblewrap is required; refusing unsandboxed candidate")
        cmd = [executable, "--unshare-all", "--die-with-parent", "--new-session"]
        for name in ("/usr", "/bin", "/lib", "/lib64"):
            path = Path(name)
            if path.is_symlink():
                cmd += ["--symlink", os.readlink(path), name]
            elif path.exists():
                cmd += ["--ro-bind", name, name]
        if not str(base).startswith("/usr/"):
            cmd += ["--ro-bind", str(base), str(base)]
        cmd += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--ro-bind", str(directory), "/candidate", "--chdir", "/candidate"]
        for root in (workspace, sources):
            if root:
                cmd += ["--ro-bind", str(root), str(root)]
        if workspace:
            for name in ("outputs", "tmp"):
                cmd += ["--bind", str(workspace / name), str(workspace / name)]
        cmd += ["--", str(python), "-I", "-S", "/candidate/worker.py"]
        return cmd
    raise RuntimeError("No supported OS sandbox; refusing candidate execution")


def run_program(source: str, value, *, invoke=None, timeout=30.0, workspace=None, sources=None, import_paths=None):
    """Bound wall time and output; arbitrary child calls still require admission."""
    with tempfile.TemporaryDirectory(prefix="hc-program-") as name:
        directory = Path(name).resolve()
        (directory / "worker.py").write_text(WORKER)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": str(directory),
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        if workspace:
            env["TMPDIR"] = str(workspace / "tmp")
        if os.environ.get("HUMANCLAW_BWRAP_LD_LIBRARY_PATH"):
            env["LD_LIBRARY_PATH"] = os.environ["HUMANCLAW_BWRAP_LD_LIBRARY_PATH"]
        process = subprocess.Popen(command(directory, workspace, sources), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env, start_new_session=True, cwd=directory)
        lines = queue.Queue(maxsize=64)
        errors = []
        def read_output():
            """Read bounded candidate messages without blocking the owner thread."""
            while True:
                line = process.stdout.readline(262145)
                if not line:
                    break
                try:
                    lines.put_nowait(line)
                except queue.Full:
                    process.kill()
                    break
            try:
                lines.put_nowait(None)
            except queue.Full:
                pass
        def read_errors():
            """Drain diagnostics while retaining only a bounded tail."""
            while chunk := process.stderr.read(4096):
                if sum(map(len, errors)) < 16384:
                    errors.append(chunk)
        readers = [threading.Thread(target=read_output, daemon=True), threading.Thread(target=read_errors, daemon=True)]
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + timeout
        try:
            process.stdin.write(json.dumps({"source": source, "input": value, "import_paths": import_paths or [],
                                           "workspace": str(workspace) if workspace else None}) + "\n")
            process.stdin.flush()
            output = None
            has_output = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Candidate program deadline")
                try:
                    line = lines.get(timeout=min(remaining, 0.1))
                except queue.Empty:
                    continue
                if line is None:
                    break
                if len(line) > 262144:
                    raise ValueError("Candidate output exceeds limit")
                item = json.loads(line)
                if set(item) == {"call"}:
                    if invoke is None:
                        raise ValueError("Environment effects forbidden by this validation protocol")
                    # The callback serializes all effectful children through Broker.execute.
                    result = invoke(item["call"])
                    process.stdin.write(json.dumps({"value": result}) + "\n")
                    process.stdin.flush()
                elif set(item) == {"result"} and not has_output:
                    output, has_output = item["result"], True
                else:
                    raise ValueError("Invalid candidate pipe protocol")
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            if process.returncode or not has_output:
                raise RuntimeError("Candidate failed: " + "".join(errors)[-3000:])
            return output
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            for reader in readers:
                reader.join(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
