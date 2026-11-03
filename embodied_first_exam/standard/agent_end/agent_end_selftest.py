#!/usr/bin/env python3
"""rcb_agent_end.py (agent-ended episodes, PROTOCOL §3) over HTTP, on toy_server.py of the 2.2 layer made an agent-ended
adapter the way an adapter uses the module (numpy only, CPU, about 20 s):

  - feature off: the adapter answers a fixed request script exactly as toy_server.py does with rcb_limited.serve alone
    (RCB_AGENT_END unset or "0"), /finish is a 404 and final.json has none of the feature's fields;
  - feature on: a success changes no answer (done, reason, executed rows, 409s); POST /finish ends the episode and every
    call after it but GET /spec and /status is a 409; the verdict is the end state's (a success undone is 0; a success at
    /finish or at the session's end is 1); final.json records ended_by;
  - RCB_STEP_LIMIT: the episode ends by itself at the limit (reason step_limit, the chunk cut there), graded as it stands;
  - fail closed: an adapter without finish(), and RCB_STEP_LIMIT without RCB_AGENT_END, do not start.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STD = os.path.dirname(HERE)                         # embodied_first_exam/standard: rcb_limited.py, rcb1.py, toy_server.py
sys.path.insert(0, STD)
import rcb1  # noqa: E402

VOLATILE = {"time_s", "time_left_s", "elapsed_s"}
fails: list[str] = []

# toy_server.py -> an agent-ended adapter: (old, new), each found exactly once
PATCH = [
    ("import rcb_limited as L  # noqa: E402\n", "import rcb_limited as L  # noqa: E402\nimport rcb_agent_end as AE  # noqa: E402\n"),
    ('persist=("last_note",))', 'persist=AE.persist(("last_note",)))'),
    ("                **EP.final_fields()})\n    L._write_json", "                **EP.final_fields(), **AE.final_fields(E, ctrl_steps())})\n    L._write_json"),
    ('    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()\n',
     '    E["done"] = True; E["reason"] = reason; E["t_end"] = time.time()\n'
     '    if AE.ENABLED:                                      # the end state is judged (no settle window in this toy)\n'
     '        E["success"] = reason in AE.END_STATE_REASONS and S.success()\n'),
    ('    if S.success() and not E["success"]:\n        E["success"] = True; finish("success")\n',
     '    if AE.ENABLED:\n        AE.hidden_success(E, S.success(), EP.log, ctrl_steps())\n'
     '        if AE.STEP_LIMIT is not None and ctrl_steps() >= AE.STEP_LIMIT:\n            finish("step_limit")\n'
     '    elif S.success() and not E["success"]:\n        E["success"] = True; finish("success")\n'),
    ('            "reason": E["reason"], "proprio"', '            "reason": E["reason"], **AE.steps_left(ctrl_steps()), "proprio"'),
    ("L.serve(L.Service(", "AE.serve(AE.Service("),
    ("proprio=proprio_row), port=", "proprio=proprio_row, **({\"finish\": lambda: finish(\"finished\")} if AE.ENABLED else {})), port="),
]


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def adapter(patched: bool, drop_finish: bool = False) -> str:
    """A directory with the toy service: toy_server.py as it is, or made an agent-ended adapter (PATCH)."""
    d = tempfile.mkdtemp()
    s = open(os.path.join(STD, "toy_server.py")).read()
    if patched:
        for old, new in PATCH:
            assert s.count(old) == 1, f"toy_server.py changed: patch the selftest ({old[:60]!r})"
            s = s.replace(old, new)
        if drop_finish:
            s = s.replace(', **({"finish": lambda: finish("finished")} if AE.ENABLED else {})', "")
    open(os.path.join(d, "toy_server.py"), "w").write(s)
    for f in ("rcb_limited.py", "rcb1.py"):
        shutil.copy(os.path.join(STD, f), d)
    shutil.copy(os.path.join(HERE, "rcb_agent_end.py"), d)
    return d


class Toy:
    def __init__(self, src: str, env_extra: dict | None = None):
        self.src, self.data, self.port = src, tempfile.mkdtemp(), free_port()
        env = {k: v for k, v in os.environ.items() if k not in ("RCB_AGENT_END", "RCB_STEP_LIMIT")}
        env.update({"RCB_DATA": self.data, "RCB_TOY_PORT": str(self.port), **(env_extra or {})})
        self.log = open(self.data + ".log", "w")
        self.p = subprocess.Popen([sys.executable, os.path.join(src, "toy_server.py")], env=env, stdout=self.log,
                                  stderr=subprocess.STDOUT)
        t = time.time()
        while time.time() - t < 30:
            if self.p.poll() is not None:
                return
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.1)

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                code, ctype, raw = r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            code, ctype, raw = e.code, e.headers.get("Content-Type"), e.read()
        if ctype == "application/x-rcb1":
            meta, parts = rcb1.decode(raw)
            return {"code": code, "meta": {k: v for k, v in meta.items() if k not in VOLATILE}, "parts": sorted(parts)}
        obj = json.loads(raw or b"{}")
        return {"code": code, "json": {k: v for k, v in obj.items() if k not in VOLATILE} if isinstance(obj, dict) else obj}

    def end(self) -> dict:
        fin = {}
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGUSR1)
            t = time.time()
            while time.time() - t < 30:
                try:
                    fin = json.load(open(os.path.join(self.data, "final.json")))
                    if fin.get("finalized"):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.1)
            self.p.kill()
        self.p.wait()
        shutil.rmtree(self.data, ignore_errors=True)
        self.log.close(); os.unlink(self.data + ".log")
        return fin


def sub(rows):
    return {"type": "joint_position", "actions": rows, "video": "none"}


TO_BLOCK, PUSH, BACK = [[0.5, 0, 0]] * 12, [[1.0, 0, 0]] * 12, [[0.5, 0, 0]] * 12
SCRIPT = [("GET", "/spec", None), ("GET", "/status", None), ("POST", "/observe", {}), ("POST", "/submit", sub(TO_BLOCK)),
          ("POST", "/finish", {}), ("POST", "/submit", sub(PUSH)), ("GET", "/status", None), ("POST", "/observe", {}),
          ("POST", "/submit", sub(BACK)), ("POST", "/kinematics", {"op": "fk", "q": [0, 0, 0]}), ("POST", "/finish", {}),
          ("POST", "/submit", sub(BACK)), ("POST", "/observe", {}), ("POST", "/kinematics", {"op": "fk", "q": [0, 0, 0]}),
          ("GET", "/status", None)]
KEEP = lambda f: {k: v for k, v in f.items() if k not in VOLATILE | {"resume_s", "t_end"}}  # noqa: E731


def script(src, env=None):
    t = Toy(src, env)
    out = [t.call(*c) for c in SCRIPT]
    return out, t.end()


def main() -> None:
    plain, ae, ae_nofinish = adapter(False), adapter(True), adapter(True, drop_finish=True)
    try:
        ref, fin_ref = script(plain)
        for env in (None, {"RCB_AGENT_END": "0"}):
            off, fin_off = script(ae, env)
            check(off == ref, f"off {env}: answers differ from rcb_limited alone: "
                  + str([(i, a, b) for i, (a, b) in enumerate(zip(ref, off)) if a != b][:2]))
            check(KEEP(fin_off) == KEEP(fin_ref), f"off {env}: final.json differs: {KEEP(fin_off)} {KEEP(fin_ref)}")
        check(ref[4]["code"] == 404 and ref[10]["code"] == 404, "off: /finish is not a 404")
        check(ref[5]["meta"]["reason"] == "success" and ref[5]["meta"]["executed_rows"] < 12 and ref[8]["code"] == 409,
              f"off: a success does not end the episode: {ref[5]} {ref[8]}")

        on, fin = script(ae, {"RCB_AGENT_END": "1"})
        spec, st0, obs0, s1, f1, s2, st1, obs1, s3, k1, f2, s4, obs2, k2, st2 = on
        check("success_signal" in spec["json"], "on: /spec has no success_signal")
        check(f1["code"] == 200 and f1["json"]["done"] and f1["json"]["reason"] == "finished", f"on: the first /finish: {f1}")
        check(s2["code"] == 409 and obs1["code"] == 409 and k1["code"] == 409 and f2["code"] == 409 and st1["code"] == 200,
              f"on: calls after /finish: {s2['code']} {obs1['code']} {k1['code']} {f2['code']} {st1['code']}")
        check(fin.get("success") is False and fin.get("ended_by") == "finish" and fin.get("success_signal") == "hidden"
              and fin.get("hidden_success_seen") is False, f"on: finish before the block moved: {fin}")

        t = Toy(ae, {"RCB_AGENT_END": "1"})       # a success mid-chunk, then undone, then /finish: nothing shown, 0
        a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/submit", sub(PUSH))]
        st = t.call("GET", "/status")
        check(all(x["meta"]["done"] is False and x["meta"]["reason"] is None and x["meta"]["executed_rows"] == 12 for x in a)
              and st["json"]["done"] is False and st["json"]["reason"] is None, f"on: a success shows: {[x['meta'] for x in a]} {st}")
        b = t.call("POST", "/submit", sub(BACK))
        check(b["code"] == 200 and b["meta"]["executed_rows"] == 12, f"on: a call after a hidden success: {b}")
        f = t.call("POST", "/finish", {})
        fin = t.end()
        check(f["code"] == 200 and fin.get("success") is False and fin.get("hidden_success_seen") is True
              and fin.get("ended_by") == "finish", f"on: a success undone was graded: {fin}")

        for how in ("finish", "session_end"):    # a success held to /finish, or to the session's end (SIGUSR1): 1
            t = Toy(ae, {"RCB_AGENT_END": "1"})
            t.call("POST", "/submit", sub(TO_BLOCK)); t.call("POST", "/submit", sub(PUSH))
            if how == "finish":
                t.call("POST", "/finish", {})
            fin = t.end()
            check(fin.get("success") is True and fin.get("ended_by") == how, f"on: a success held to the {how}: {fin}")

        t = Toy(ae, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"})   # the step limit: 12 + 18 of 24 rows, then 409
        a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/submit", sub(PUSH * 2))]
        late = [t.call("POST", "/submit", sub(BACK)), t.call("POST", "/finish", {}), t.call("POST", "/observe", {})]
        fin = t.end()
        check(a[0]["meta"]["steps_left"] == 18 and a[1]["meta"]["executed_rows"] == 18 and a[1]["meta"]["done"]
              and a[1]["meta"]["reason"] == "step_limit" and a[1]["meta"]["steps_left"] == 0,
              f"step limit: the chunk at the limit: {a[1]['meta']}")
        check(late[0]["code"] == 409 and late[1]["code"] == 409 and late[2]["code"] == 200, f"step limit: after it: {late}")
        check(fin.get("ended_by") == "step_limit" and fin.get("step_limit") == 30 and fin.get("steps_used") == 30
              and fin.get("success") is True, f"step limit: final.json: {fin}")

        for src, env, what in ((ae_nofinish, {"RCB_AGENT_END": "1"}, "an adapter without finish()"),
                               (ae, {"RCB_STEP_LIMIT": "30"}, "RCB_STEP_LIMIT without RCB_AGENT_END")):
            t = Toy(src, env)
            time.sleep(1.0)
            check(t.p.poll() is not None and t.p.returncode != 0, f"fail closed: {what} served")
            t.end()
    finally:
        for d in (plain, ae, ae_nofinish):
            shutil.rmtree(d, ignore_errors=True)
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok agent-ended episodes (rcb_agent_end.py on toy_server.py): off = rcb_limited alone, on = no success shown, "
          "/finish, end-state verdict, step limit, fail closed")


if __name__ == "__main__":
    main()
