"""A deep copy of a live match (save_state / load_state): the whole object graph, with three exceptions.

- Objects that hold no match state and cannot be copied (process and thread handles, locks, pipes, MuJoCo helpers
  such as Rollout, MjSpec, renderers) are shared by the copy (SHARE_NAMES).
- A function that closes over objects (a method a sport installs on an instance) is rebuilt with its cells copied, so
  the copy's closure refers to the copy.
- A pending Future (a planner process's result) is waited for first, so the copy holds its result.

Everything else (MuJoCo models and data, NumPy arrays and generators, Python containers and objects) is copied by
copy.deepcopy. A copy is checked by the caller with the match's own state digest.

With `models` (a list; save_state, load_state and reset in rcb_ablation/service.py): a MuJoCo model (MjModel, which
holds the meshes and every constant of the world: about 150 MiB for soccer) is shared by the copy instead of copied,
and a MjData is copied with its model shared (copy.copy: the whole data, the arena with the contacts and the solver's
warm start included). MuJoCo's own deepcopy of a MjData copies its model too, ignoring the memo, so without this every
copy held one full model per MjData (soccer: three, about 0.45 GiB a save). The shared models are appended to `models`;
the caller keeps model_key() of each with the copy and checks it before it restores one (a model changed since the
save: the save cannot be restored exactly).
"""
from __future__ import annotations

import collections
import copy
import hashlib
import threading
import types

import numpy as np

SHARE_NAMES = {"Rollout", "Renderer", "GLContext", "Thread", "Process", "Popen", "Condition", "Event", "Semaphore",
               "BoundedSemaphore", "lock", "RLock", "_RLock", "Lock", "TextIOWrapper", "BufferedWriter",
               "BufferedReader", "BufferedRandom", "FileIO", "socket", "ProcessWorker", "CameraWorker", "Connection",
               "Queue", "SimpleQueue", "Pool", "ThreadPoolExecutor", "ProcessPoolExecutor", "InferenceSession",
               "MjrContext", "MjvScene", "MjvOption", "MjvCamera", "MjSpec", "PosixPath"}
LEAF = (int, float, str, bytes, bool, type(None), complex)
_COPY_LOCK = threading.Lock()


def _walk(obj, memo: dict, shared: dict, futures: list):
    seen, stack = set(), [obj]
    while stack:
        x = stack.pop()
        i = id(x)
        if i in seen or isinstance(x, LEAF):
            continue
        seen.add(i)
        tn = type(x).__name__
        if tn == "Future" and hasattr(x, "result") and hasattr(x, "done"):
            futures.append(x)
        if tn in SHARE_NAMES or isinstance(x, (types.ModuleType, types.BuiltinFunctionType, type)) or \
                (isinstance(x, types.FunctionType) and not x.__closure__):
            if not isinstance(x, (types.FunctionType, type, types.BuiltinFunctionType)):
                shared[tn] = shared.get(tn, 0) + 1
            memo[i] = x
            continue
        if isinstance(x, types.FunctionType):
            stack.extend(c.cell_contents for c in x.__closure__ if _filled(c))
            continue
        mod = type(x).__module__ or ""
        if mod.startswith(("numpy", "mujoco", "torch")):
            continue                                  # copied by their own deepcopy
        if isinstance(x, dict):
            stack.extend(x.keys())
            stack.extend(x.values())
        elif isinstance(x, (list, tuple, set, frozenset, collections.deque)):
            stack.extend(x)
        else:
            d = getattr(x, "__dict__", None)
            if isinstance(d, dict):
                stack.append(d)
            for s in getattr(type(x), "__slots__", ()) or ():
                if isinstance(s, str) and hasattr(x, s):
                    stack.append(getattr(x, s))


def _filled(cell) -> bool:
    try:
        cell.cell_contents
        return True
    except ValueError:
        return False


def _copy_function(f, memo):
    if not f.__closure__:
        return f
    cells = tuple(types.CellType(copy.deepcopy(c.cell_contents, memo)) if _filled(c) else c for c in f.__closure__)
    g = types.FunctionType(f.__code__, f.__globals__, f.__name__, f.__defaults__, cells)
    g.__kwdefaults__ = f.__kwdefaults__
    g.__dict__.update(f.__dict__)
    return g


# a model's fields that only draw it (cameras, lights, colours, textures, names): a renderer may set them while the
# match runs; they change no physics and are left out of model_key
PRESENTATION = ("cam_", "light_", "mat_", "tex_", "skin_", "geom_rgba", "site_rgba", "tendon_rgba", "flex_rgba",
                "name_", "names", "paths", "vis", "stat")


def model_key(model) -> str:
    """A hash of everything in a MuJoCo model that the physics reads (its arrays, sizes and options)."""
    h = hashlib.blake2b(digest_size=20)
    for name in sorted(dir(model)):
        if name.startswith("_") or name.startswith(PRESENTATION):
            continue
        try:
            v = getattr(model, name)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(v, np.ndarray):
            h.update(f"{name}:{v.dtype}:{v.shape}".encode())
            h.update(np.ascontiguousarray(v).data)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            h.update(f"{name}={v!r}".encode())
    opt = getattr(model, "opt", None)
    for name in sorted(dir(opt)) if opt is not None else ():
        if name.startswith("_"):
            continue
        v = getattr(opt, name, None)
        if isinstance(v, np.ndarray):
            h.update(f"opt.{name}".encode() + np.ascontiguousarray(v).tobytes())
        elif isinstance(v, (int, float)):
            h.update(f"opt.{name}={v!r}".encode())
    return h.hexdigest()


def _copiers(mj, models):
    """deepcopy's copiers for MjModel (shared) and MjData (copied, its model shared), for this thread's copy only: a
    deepcopy another thread makes meanwhile gets MuJoCo's own."""
    plain_model, plain_data = mj.MjModel.__deepcopy__, mj.MjData.__deepcopy__
    me = threading.get_ident()

    def note(m):
        if not any(x is m for x in models):
            models.append(m)

    def model(x, memo):
        if threading.get_ident() != me:
            return plain_model(x, memo)
        note(x)
        return x

    def data(x, memo):
        if threading.get_ident() != me:
            return plain_data(x, memo)
        note(x.model)
        return copy.copy(x)
    return model, data


def snap(obj, extra_shared=(), models=None):
    """(a deep copy of obj, {type name: count} of the shared objects). models: a list: MuJoCo models shared (appended
    to it), see above; None: everything copied."""
    memo, shared, futures = {}, {}, []
    _walk(obj, memo, shared, futures)
    for f in futures:
        try:
            f.result(timeout=30)
        except Exception:  # noqa: BLE001
            pass
    if futures:
        shared["Future (waited for)"] = len(futures)
    for e in extra_shared:
        memo[id(e)] = e
    mj = None
    if models is not None:
        try:
            import mujoco as mj
        except ImportError:
            mj = None
    with _COPY_LOCK:
        old = copy._deepcopy_dispatch.get(types.FunctionType)
        copy._deepcopy_dispatch[types.FunctionType] = _copy_function
        if mj is not None:
            old_mj = {t: copy._deepcopy_dispatch.get(t) for t in (mj.MjModel, mj.MjData)}
            copy._deepcopy_dispatch[mj.MjModel], copy._deepcopy_dispatch[mj.MjData] = _copiers(mj, models)
        try:
            out = copy.deepcopy(obj, memo)
        finally:
            copy._deepcopy_dispatch[types.FunctionType] = old
            if mj is not None:
                for t, f in old_mj.items():
                    if f is None:
                        copy._deepcopy_dispatch.pop(t, None)
                    else:
                        copy._deepcopy_dispatch[t] = f
    if models:
        shared["MjModel (shared)"] = len(models)
    return out, shared
