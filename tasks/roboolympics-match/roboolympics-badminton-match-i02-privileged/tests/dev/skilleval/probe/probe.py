"""The isolation probe (tools/skill_eval.py SPORT probe): a "skill" that tries what a deliverable must not be able to
do in the evaluation container and reports each attempt (True = it worked = a leak). skilleval/evaluate.py --probe fails
on any True."""

import os
import socket


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
    out["uid"] = os.getuid()
    return out
