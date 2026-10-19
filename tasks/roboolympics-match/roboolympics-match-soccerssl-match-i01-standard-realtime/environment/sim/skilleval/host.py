"""The child process that hosts a deliverable skill (skilleval/sandbox.py starts it as `python3 -I -c <this file> DIR
MODULE`, so nothing of the evaluator is on its path). Standard library only.

It imports DIR/MODULE.py (DIR first on sys.path: the skill may import its own files), says which public functions it
has, then answers one JSON line per request on the protocol stream:

    {"ctx": {...}}                                  keyword arguments added to every later call (e.g. spec)
    {"fn": NAME, "args": [...], "kwargs": {...}}    -> {"ok": true, "ret": VALUE} | {"ok": false, "error": "..."}

The protocol stream is a private copy of fd 1; fd 1 and sys.stdout then point at stderr, so nothing the skill prints
(Python or C) can corrupt the protocol. The parent owns the clock (a late answer is a time-out)."""

import importlib.util
import json
import os
import sys
import traceback


def main():
    skill_dir, module = sys.argv[1], sys.argv[2]
    proto = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send(obj):
        proto.write(json.dumps(obj, allow_nan=False) + "\n")
        proto.flush()

    sys.path.insert(0, skill_dir)
    try:
        spec = importlib.util.spec_from_file_location(module, os.path.join(skill_dir, module + ".py"))
        if spec is None:
            raise ImportError(f"no {module}.py in the skill directory")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module] = mod
        spec.loader.exec_module(mod)
    except BaseException:  # noqa: BLE001
        send({"ok": False, "error": "load: " + traceback.format_exc(limit=4)[-900:]})
        return
    funcs = sorted(
        k
        for k, v in vars(mod).items()
        if callable(v) and not k.startswith("_") and getattr(v, "__module__", None) == module
    )
    send({"ok": True, "functions": funcs})
    ctx = {}
    for line in sys.stdin:
        try:
            q = json.loads(line)
            if "ctx" in q:
                ctx = dict(q["ctx"])
                send({"ok": True, "ret": None})
                continue
            fn = getattr(mod, q["fn"], None)
            if not callable(fn) or q["fn"] not in funcs:
                raise AttributeError(f"the skill has no function {q['fn']!r}")
            ret = fn(*q.get("args", []), **{**ctx, **q.get("kwargs", {})})
            out = {"ok": True, "ret": ret}
            json.dumps(out, allow_nan=False)
        except BaseException:  # noqa: BLE001
            out = {"ok": False, "error": traceback.format_exc(limit=4)[-900:]}
        try:
            send(out)
        except (TypeError, ValueError):
            send(
                {
                    "ok": False,
                    "error": "the skill returned something that is not JSON (finite numbers, lists, "
                    "objects, strings, booleans, null)",
                }
            )


if __name__ == "__main__":
    main()
