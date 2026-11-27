#!/usr/bin/env python3
"""rcb_agent_end.py (agent-ended episodes, PROTOCOL §3) over HTTP, on toy_server.py of the shared layer, an agent-ended
adapter that uses the module the way every adapter does (numpy only, CPU, about 20 s):

  - feature off: the adapter answers a fixed request script exactly as the toy does with rcb_limited.serve alone
    (PLAIN; RCB_AGENT_END unset or "0"), /finish is a 404 and final.json has none of the feature's fields;
  - feature on: a success changes no answer (done, reason, executed rows, 409s); POST /finish ends the episode and every
    call after it but GET /spec and /status is a 409; the verdict is the end state's (a success undone is 0; a success at
    /finish or at the session's end is 1); /spec's success_signal is SUCCESS_SIGNAL_NOTE, which says so; final.json records
    ended_by;
  - RCB_STEP_LIMIT, enforced by the layer (the toy has no cap of its own): the episode ends by itself at the limit
    (reason step_limit, the chunk or hold chunk cut there), graded as it stands; /finish after it is a 409;
  - a finish() that raises: a 500 with a JSON error, the episode ends "error" (on_submit_error), checkpointed;
  - fail closed: an adapter without finish(), RCB_STEP_LIMIT without RCB_AGENT_END, and RCB_STEP_LIMIT with an adapter
    that passes no end_step_limit, do not start.
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
sys.path.insert(0, HERE)
import rcb_agent_end as AE  # noqa: E402   (only its SUCCESS_SIGNAL_NOTE: the adapters run in their own processes)

VOLATILE = {"time_s", "time_left_s", "elapsed_s"}
fails: list[str] = []

# toy_server.py is an agent-ended adapter; PLAIN undoes that, (agent-ended text, rcb_limited-alone text), each found
# exactly once: the toy as it would be with rcb_limited.serve alone, the reference the feature-off answers must equal
PLAIN = [
    ('HERE = os.path.dirname(os.path.abspath(__file__))\nsys.path[:0] = [HERE, os.path.join(HERE, "agent_end")]'
     '   # rcb_agent_end.py: next to it in a task, in agent_end/ here\n'
     "import rcb_limited as L  # noqa: E402\nimport rcb_agent_end as AE  # noqa: E402\n",
     "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nimport rcb_limited as L  # noqa: E402\n"),
    ('persist=AE.persist(("last_note",)))', 'persist=("last_note",))'),
    ("                **EP.final_fields(), **AE.final_fields(E, ctrl_steps())})\n    L._write_json",
     "                **EP.final_fields()})\n    L._write_json"),
    ('    if AE.ENABLED:                                      # the end state is judged (no settle window in this toy)\n'
     '        E["success"] = reason in AE.END_STATE_REASONS and S.success()\n', ""),
    ('    if AE.ENABLED:                                      # agent-ended: the success is only recorded\n'
     '        AE.hidden_success(E, S.success(), EP.log, ctrl_steps())\n'
     '    elif S.success() and not E["success"]:\n        E["success"] = True; finish("success")\n',
     '    if S.success() and not E["success"]:\n        E["success"] = True; finish("success")\n'),
    ('            "reason": E["reason"], **AE.steps_left(ctrl_steps()), "proprio"', '            "reason": E["reason"], "proprio"'),
    ('"done": E["done"], "reason": E["reason"], **AE.steps_left(ctrl_steps()),\n            "proprio"',
     '"done": E["done"], "reason": E["reason"],\n            "proprio"'),
    ('"last_note": E.get("last_note"), **AE.steps_left(ctrl_steps())}', '"last_note": E.get("last_note")}'),
    ("AE.serve(AE.Service(", "L.serve(L.Service("),
    ('proprio=proprio_row, **({"finish": lambda: finish("finished"),\n'
     '                                           "end_step_limit": lambda: finish("step_limit")} if AE.ENABLED else {})), port=',
     "proprio=proprio_row), port="),
]
DROP_FINISH = (', **({"finish": lambda: finish("finished"),\n'
               '                                           "end_step_limit": lambda: finish("step_limit")} if AE.ENABLED else {})')
# variants (each a list of (old, new) replacements): a finish() that raises before it ends anything; an adapter without
# end_step_limit (it must not start with RCB_STEP_LIMIT); an adapter whose status() states no control_steps (neither:
# the step limit counts them); an adapter with a step cap of its own (it ends the episode itself at RCB_STEP_LIMIT, as
# RoboPaint or DexJoCo do: the layer must not end it again; its end_step_limit logs "layer_end_step_limit" when called)
VARIANT = {"raise_finish": [('{"finish": lambda: finish("finished"),', '{"finish": lambda: 1 / 0,')],
           "no_end_step_limit": [(',\n                                           "end_step_limit": lambda: finish("step_limit")}', '}')],
           "no_control_steps": [('def status() -> dict:\n    return {"step": E["step"], "calls": E["calls"], "control_steps": ctrl_steps(), ',
                                 'def status() -> dict:\n    return {"step": E["step"], "calls": E["calls"], ')],
           "own_cap": [('        AE.hidden_success(E, S.success(), EP.log, ctrl_steps())\n',
                        '        AE.hidden_success(E, S.success(), EP.log, ctrl_steps())\n'
                        '        if AE.STEP_LIMIT is not None and ctrl_steps() >= AE.STEP_LIMIT:\n'
                        '            finish("step_limit")\n'),
                       ('"end_step_limit": lambda: finish("step_limit")}',
                        '"end_step_limit": lambda: (EP.log({"ev": "layer_end_step_limit"}), finish("step_limit"))}')]}


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def adapter(patched: bool, drop_finish: bool = False, variant: str | None = None) -> str:
    """A directory with the toy service: toy_server.py as it is (an agent-ended adapter), or as it would be with
    rcb_limited alone (PLAIN); drop_finish: the agent-ended toy without its finish() (it must not start)."""
    d = tempfile.mkdtemp()
    s = open(os.path.join(STD, "toy_server.py")).read()
    if not patched:
        for ae, plain in PLAIN:
            assert s.count(ae) == 1, f"toy_server.py changed: update the selftest's PLAIN ({ae[:60]!r})"
            s = s.replace(ae, plain)
    elif drop_finish:
        assert s.count(DROP_FINISH) == 1, "toy_server.py changed: update the selftest's DROP_FINISH"
        s = s.replace(DROP_FINISH, "")
    for old, new in VARIANT.get(variant, []) if variant else []:
        assert s.count(old) == 1, f"toy_server.py changed: update the selftest's VARIANT {variant}"
        s = s.replace(old, new)
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

    def call(self, method: str, path: str, body: dict | None = None, raw: bytes | None = None) -> dict:
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, data=data,
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


def events(t) -> list:
    """The toy's episode.jsonl so far (read before Toy.end removes its data)."""
    try:
        return [json.loads(x) for x in open(os.path.join(t.data, "episode.jsonl")) if x.strip()]
    except OSError:
        return []


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
    ae_raise, ae_own = adapter(True, variant="raise_finish"), adapter(True, variant="own_cap")
    ae_noend, ae_nocs = adapter(True, variant="no_end_step_limit"), adapter(True, variant="no_control_steps")
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
        check(spec["json"].get("success_signal") == AE.SUCCESS_SIGNAL_NOTE, f"on: /spec's success_signal: {spec['json']}")
        check(all(w in AE.SUCCESS_SIGNAL_NOTE for w in ("how things stand at that moment", "count as they happen", "409")),
              "the success_signal note no longer says what is judged at the end (the end state, steps that count as they "
              "happen) or that every call after /finish is refused")
        check(f1["code"] == 200 and f1["json"]["done"] and f1["json"]["reason"] == "finished", f"on: the first /finish: {f1}")
        check(s2["code"] == 409 and obs1["code"] == 409 and k1["code"] == 409 and f2["code"] == 409 and st1["code"] == 200,
              f"on: calls after /finish: {s2['code']} {obs1['code']} {k1['code']} {f2['code']} {st1['code']}")
        check(fin.get("success") is False and fin.get("ended_by") == "finish" and fin.get("success_signal") == "hidden"
              and fin.get("hidden_success_seen") is False, f"on: finish before the block moved: {fin}")

        t = Toy(ae, {"RCB_AGENT_END": "1"})       # eai-standard/3.0: /finish's body is optional and ignored
        f = t.call("POST", "/finish", raw=b"not json {")
        t.end()
        check(f["code"] == 200 and f["json"]["reason"] == "finished", f"on: /finish with a malformed body: {f}")

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

        for src, who in ((ae, "the layer"), (ae_own, "the adapter's own cap")):   # 12 + 18 of 24 rows, then 409
            t = Toy(src, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"})
            a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/submit", sub(PUSH * 2))]
            late = [t.call("POST", "/submit", sub(BACK)), t.call("POST", "/finish", {}), t.call("POST", "/observe", {}),
                    t.call("GET", "/status")]
            ev = events(t)
            ends = [e for e in ev if e.get("ev") == "end"]
            layer_ends = sum(1 for e in ev if e.get("ev") == "layer_end_step_limit")
            fin = t.end()
            if src is ae_own:
                check(layer_ends == 0, f"step limit (the adapter's own cap): the layer's end_step_limit ran {layer_ends}x")
            check(a[0]["meta"]["steps_left"] == 18 and a[1]["meta"]["executed_rows"] == 18 and a[1]["meta"]["done"]
                  and a[1]["meta"]["reason"] == "step_limit" and a[1]["meta"]["steps_left"] == 0
                  and a[1]["meta"]["control_steps"] == 30 and a[1]["meta"].get("duration_s") == 0.9,
                  f"step limit ({who}): the chunk at the limit: {a[1]['meta']}")
            check(late[0]["code"] == 409 and late[1]["code"] == 409 and late[2]["code"] == 200
                  and late[2]["meta"]["reason"] == "step_limit" and late[3]["json"]["reason"] == "step_limit"
                  and late[3]["json"]["steps_left"] == 0, f"step limit ({who}): after it: {late}")
            check([e.get("reason") for e in ends] == ["step_limit"] and ends[0].get("control_steps") == 30,
                  f"step limit ({who}): one end, at step 30: {ends}")
            check(fin.get("ended_by") == "step_limit" and fin.get("step_limit") == 30 and fin.get("steps_used") == 30
                  and fin.get("success") is True, f"step limit ({who}): final.json: {fin}")

        t = Toy(ae, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "12"})   # the limit reached exactly at a chunk's end
        a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/submit", sub(BACK)), t.call("POST", "/finish", {})]
        fin = t.end()
        check(a[0]["code"] == 200 and a[0]["meta"]["executed_rows"] == 12 and a[0]["meta"]["reason"] == "step_limit"
              and a[1]["code"] == 409 and a[2]["code"] == 409 and fin.get("steps_used") == 12,
              f"step limit at a chunk's last row: {[x.get('meta', x.get('json')) for x in a]} {fin}")

        t = Toy(ae_raise, {"RCB_AGENT_END": "1"})   # finish() raises: a 500 with a JSON error, the episode ends "error"
        a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/finish", {}), t.call("GET", "/status"),
             t.call("POST", "/submit", sub(BACK))]
        ev = events(t)
        fin = t.end()
        cps = [e for e in ev if e.get("ev") == "checkpoint"]
        check(a[1]["code"] == 500 and "error" in a[1]["json"] and a[2]["json"]["done"] and a[2]["json"]["reason"] == "error"
              and a[3]["code"] == 409, f"finish() raising: {[(x['code'], x.get('json')) for x in a]}")
        check(cps and cps[-1].get("done") is True and cps[-1].get("reason") == "error"
              and any(e.get("ev") == "call_end" and e.get("path") == "/finish" for e in ev),
              f"finish() raising: no checkpoint of the end: {cps[-1:]}")
        check(fin.get("ended_by") == "error" and fin.get("success") is False, f"finish() raising: final.json {fin}")

        t = Toy(ae, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"})   # eai-standard/3.0: a hold chunk is a chunk
        hold = {"type": "joint_position", "interpolate": "hold", "seconds": 1.0, "video": "none"}
        a = [t.call("POST", "/submit", sub(TO_BLOCK)), t.call("POST", "/observe", {"seconds": 1.0}),
             t.call("POST", "/observe", {"last_s": 0.5}), t.call("POST", "/submit", hold)]
        late = [t.call("POST", "/submit", hold), t.call("POST", "/observe", {"last_s": 0.5})]
        fin = t.end()
        check(a[1]["code"] == 400 and a[2]["code"] == 200 and a[2]["meta"].get("last_s") == 0.5
              and a[3]["code"] == 200 and a[3]["meta"].get("hold") is True and a[3]["meta"]["reason"] == "step_limit"
              and a[3]["meta"].get("duration_s") == 0.9,
              f"3.0: observe seconds 400, last_s read, a hold chunk cut at the step limit: {a}")
        check(late[0]["code"] == 409 and late[1]["code"] == 200 and fin.get("ended_by") == "step_limit",
              f"3.0: after the step limit a hold chunk is a 409, a last_s read still answers: {late} {fin}")
        t = Toy(ae, {"RCB_AGENT_END": "1"})
        a = [t.call("POST", "/submit", hold), t.call("POST", "/finish", {}), t.call("POST", "/observe", {"last_s": 0.5}),
             t.call("POST", "/submit", hold)]
        t.end()
        check(a[0]["code"] == 200 and a[1]["code"] == 200 and a[2]["code"] == 409 and a[3]["code"] == 409,
              f"3.0: after /finish a last_s read and a hold chunk are 409s: {[x['code'] for x in a]}")

        t = Toy(ae, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"})   # /spec states the limit in force
        sp = t.call("GET", "/spec")["json"]
        t.end()
        check(sp.get("max_control_steps") == 30 and sp.get("budget", {}).get("steps") == 30,
              f"step limit: /spec max_control_steps {sp.get('max_control_steps')}, budget {sp.get('budget')}")

        for src, env, what in ((ae_nofinish, {"RCB_AGENT_END": "1"}, "an adapter without finish()"),
                               (ae, {"RCB_STEP_LIMIT": "30"}, "RCB_STEP_LIMIT without RCB_AGENT_END"),
                               (ae_noend, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"},
                                "RCB_STEP_LIMIT and an adapter without end_step_limit"),
                               (ae_nocs, {"RCB_AGENT_END": "1", "RCB_STEP_LIMIT": "30"},
                                "RCB_STEP_LIMIT and an adapter whose status() states no control_steps")):
            t = Toy(src, env)
            time.sleep(1.0)
            check(t.p.poll() is not None and t.p.returncode != 0, f"fail closed: {what} served")
            t.end()
    finally:
        for d in (plain, ae, ae_nofinish, ae_raise, ae_own, ae_noend, ae_nocs):
            shutil.rmtree(d, ignore_errors=True)
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok agent-ended episodes (rcb_agent_end.py on toy_server.py): off = rcb_limited alone, on = no success shown, "
          "/finish, end-state verdict, step limit (the layer's, or the adapter's own: one end), a finish() error, fail closed, "
          "3.0 observe / hold chunks")


if __name__ == "__main__":
    main()
