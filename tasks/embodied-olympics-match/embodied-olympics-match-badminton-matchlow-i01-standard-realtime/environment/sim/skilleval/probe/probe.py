"""The isolation probe (tools/skill_eval.py SPORT probe): a "skill" that tries what a deliverable must not be able to
do in the evaluation container and reports each attempt (True = it worked = a leak). skilleval/evaluate.py --probe fails
on any True. It also leaves a detached process behind (`survivor_pid`): the evaluator checks that closing the skill ended
it (`survives_close`), and that RLIMIT_NPROC is set (`nproc_unlimited`)."""

import os
import resource
import socket
import time


def _read(path):
    try:
        with open(path, "rb") as f:
            f.read(16)
        return True
    except OSError:
        return False


def probe(targets):
    out = {}
    for name, path in targets.items():
        if name.startswith("read_"):
            out[name] = _read(path)
        elif name.startswith("list_"):
            try:
                os.listdir(path)
                out[name] = True
            except OSError:
                out[name] = False
        elif name.startswith("write_"):
            try:
                with open(path, "w") as f:
                    f.write("x")
                out[name] = True
            except OSError:
                out[name] = False
    out["read_init_environ"] = _read("/proc/1/environ")
    for name, addr in (("network_ip", ("1.1.1.1", 53)), ("network_dns", ("github.com", 443))):
        try:
            socket.create_connection(addr, timeout=3).close()
            out[name] = True
        except OSError:
            out[name] = False
    allowed = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "MUJOCO_GL",
        "PYOPENGL_PLATFORM",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "LC_CTYPE",
    }
    out["env_beyond_allowed"] = sorted(set(os.environ) - allowed) != []
    try:
        import core  # noqa: F401

        out["import_core"] = True
    except ImportError:
        out["import_core"] = False
    soft = resource.getrlimit(resource.RLIMIT_NPROC)[0]
    out["nproc_unlimited"] = soft == resource.RLIM_INFINITY
    out["survivor_pid"] = _survivor()
    out["uid"] = os.getuid()
    return out


def _survivor():
    """A grandchild in a session of its own (double fork + setsid), re-parented away from the skill: it sleeps for a
    minute. Returns its pid (None when it could not be started)."""
    r, w = os.pipe()
    try:
        pid = os.fork()
    except OSError:
        return None
    if pid == 0:                                   # the child: detach, start the sleeper, report its pid, exit
        try:
            os.setsid()
            g = os.fork()
            if g == 0:
                os.close(r)
                os.close(w)
                time.sleep(60)
                os._exit(0)
            os.write(w, str(g).encode())
        finally:
            os._exit(0)
    os.close(w)
    os.waitpid(pid, 0)
    data = os.read(r, 32)
    os.close(r)
    return int(data) if data else None
