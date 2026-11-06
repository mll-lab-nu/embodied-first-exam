"""The program's process in the formal match (run as `nobody`): python3 worker.py POLICY_DIR. It reads the config, then
one view per message, and answers each with {"seq", "action"} (or {"seq", "error"}); stdout carries only the
protocol (the program's own prints go to stderr)."""
import json
import os
import struct
import sys
import traceback


def read_msg(f):
    h = f.read(4)
    if len(h) < 4:
        return None
    n = struct.unpack(">I", h)[0]
    return json.loads(f.read(n))


def main():
    pdir = os.path.abspath(sys.argv[1])
    inp, out = sys.stdin.buffer, os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)                                   # print() of the program -> stderr

    def send(obj):
        b = json.dumps(obj, separators=(",", ":"), default=float).encode()
        out.write(struct.pack(">I", len(b)) + b)
        out.flush()
    cfg = read_msg(inp)["config"]
    try:
        sys.path.insert(0, pdir)
        import importlib.util
        spec = importlib.util.spec_from_file_location("program", os.path.join(pdir, "program.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pol = mod.make_policy(cfg)
        send({"ready": True})
    except BaseException as exc:  # noqa: BLE001
        send({"ready": False, "error": "".join(traceback.format_exception_only(type(exc), exc))[:1000]})
        return
    while True:
        m = read_msg(inp)
        if m is None:
            return
        try:
            send({"seq": m["seq"], "action": pol.act(m["view"])})
        except Exception as exc:  # noqa: BLE001
            send({"seq": m["seq"], "error": "".join(traceback.format_exception_only(type(exc), exc))[:1000]})


if __name__ == "__main__":
    main()
