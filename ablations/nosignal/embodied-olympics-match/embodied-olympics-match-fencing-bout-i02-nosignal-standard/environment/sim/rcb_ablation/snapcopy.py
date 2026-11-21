"""A deep copy of a live match (save_state / load_state): the whole object graph, with three exceptions.

- Objects that hold no match state and cannot be copied (process and thread handles, locks, pipes, MuJoCo helpers
  such as Rollout, MjSpec, renderers) are shared by the copy (SHARE_NAMES).
- A function that closes over objects (a method a sport installs on an instance) is rebuilt with its cells copied, so
  the copy's closure refers to the copy.
- A pending Future (a planner process's result) is waited for first, so the copy holds its result.

Everything else (MuJoCo models and data, NumPy arrays and generators, Python containers and objects) is copied by
copy.deepcopy. A copy is checked by the caller with the match's own state digest.
"""
from __future__ import annotations

import collections
import copy
import threading
import types

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


def snap(obj, extra_shared=()):
    """(a deep copy of obj, {type name: count} of the shared objects)."""
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
    with _COPY_LOCK:
        old = copy._deepcopy_dispatch.get(types.FunctionType)
        copy._deepcopy_dispatch[types.FunctionType] = _copy_function
        try:
            out = copy.deepcopy(obj, memo)
        finally:
            copy._deepcopy_dispatch[types.FunctionType] = old
    return out, shared
