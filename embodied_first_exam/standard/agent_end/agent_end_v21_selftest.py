#!/usr/bin/env python3
"""Agent-ended episodes (PROTOCOL §3) in the 2.1 sidecar (every distinct rcb_service.py: embodied_first_exam/benchmarks/
and the abc-sim realtime copy) and in the 2.3 realtime layer on top of it (rcb_realtime.py), in process on a toy
simulator (numpy only, CPU, a few seconds):

  - feature off: POST /finish is a 404 and a success ends the episode as before;
  - the oracle and /finish: 1; nothing done and /finish: 0; a success undone before /finish: 0; a success then the
    task's failure rule: 0; a success never changes an answer (no done, no reason, no success key in meta);
  - after /finish: /submit, /observe, /reset are 409, /spec and /status answer;
  - the step cap (the adapter's max_control_steps, or RCB_STEP_LIMIT) ends the episode judged as it stands
    (reason step_limit), /observe still answers there; the end of the session (SIGUSR1) judges the state too;
  - end_judgement "events": a moment reached and gone counts; a moment reached and then the task's failure rule (a fall
    after the pass mark) still counts (decision 1), and the failure rule with no moment reached is 0;
    end_window_steps: the settle window decides;
  - hidden_keys: step() info keys of progress never reach a meta;
  - a crash: the restart resumes the hidden success with the episode;
  - realtime: /finish stops the clock and ends the episode; the verdict is the state's; a /finish body over 64 MiB
    is a 413 (as every POST); a hold chunk answers executed_rows 0; /spec.timing.recorder is declared also by a service
    without a recorder (record_frames False).
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
STD = ROOT / "embodied_first_exam/standard"
sys.path.insert(0, str(STD))                     # rcb1.py
import rcb1  # noqa: E402

fails: list[str] = []


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what)


class Toy:
    """x moves by row[0]; x >= 1 is the success (state); row[1] > 0 is the task's failure rule (done, no success);
    info carries a progress key ("stage") the service must hide and a plain one ("tick")."""
    raw_dim = 2
    control_dt = 0.02
    max_control_steps = 40
    proprio_layout = ["x"]
    cameras = ["a"]
    depth_cameras: list = []
    end_judgement = "state"
    end_window_steps = 0
    hidden_keys = ("stage",)
    drift = 0.0                                      # what a held step does to x (the settle window's physics)

    def __init__(self):
        self.x = 0.0

    def spec(self):
        return {"cameras": {}, "action_types": {"joints": {"dim": 2}}}

    def interpolable(self, t):
        return False

    def images(self, cams, depth):
        return {c: np.zeros((4, 4, 3), np.uint8) for c in cams}, {}

    def proprio(self):
        return np.array([self.x], np.float32)

    def clip(self, t, rows):
        return rows, []

    def to_sim(self, t, row):
        return np.asarray(row, float)

    def command(self, t):
        return np.zeros(2)

    def hold(self):
        return "joints", np.array([self.drift, 0.0])

    def step(self, row):
        self.x = round(self.x + float(row[0]), 6)
        fail = float(row[1]) > 0
        ok = self.x >= 1.0 and not fail
        return bool(ok or fail), bool(ok), {"stage": int(self.x), "tick": 1}

    def reset(self):
        self.x = 0.0

    def state_sha(self):
        return hashlib.sha256(np.array([self.x]).tobytes()).hexdigest()[:12]

    def save_trajectory(self, rows, path, meta):
        np.savez(path, actions=rows)

    def render_video(self, rows, path):
        open(path, "wb").write(b"mp4")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def call(svc, path, body=None, method="POST"):
    code, ctype, out = svc.handle(method, path, json.dumps(body if body is not None else {}).encode())
    out = bytes(out)
    if ctype == "application/json":
        return code, json.loads(out)
    meta, _ = rcb1.decode(out)
    return code, meta


def submit(svc, *rows):
    return call(svc, "/submit", {"type": "joints", "actions": [list(map(float, r)) for r in rows], "cameras": ["a"],
                                 "video": "none"})


def final(d):
    return json.load(open(os.path.join(d, "final.json")))


def end_session(svc):
    svc.on_sigusr1()
    svc.poll()


def scenario(S, tag, name, *, sim=None, agent_end=True, step_limit=None, budget=0, run=None):
    d = tempfile.mkdtemp()
    try:
        svc = S.Service(sim or Toy(), data=d, reset_budget=budget, agent_end=agent_end, step_limit=step_limit)
        svc.start()
        res = run(svc, d)
        return res
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(False, f"{tag} {name}: raised {exc!r}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def suite_21(S, tag):
    # feature off: /finish 404, a success ends the episode
    def off(svc, d):
        check(call(svc, "/finish")[0] == 404, f"{tag} off: /finish is not 404")
        c, m = submit(svc, [1, 0])
        check(m["done"] and m["reason"] == "success", f"{tag} off: a success did not end the episode ({m['reason']})")
        check("success_signal" not in svc.spec, f"{tag} off: spec states a success signal")
    scenario(S, tag, "off", agent_end=False, run=off)

    def oracle(svc, d):
        check("success_signal" in svc.spec and svc.spec["success_signal"].startswith("hidden"), f"{tag}: spec has no success_signal")
        c, m = submit(svc, [0.5, 0], [0.5, 0], [0, 0])
        check(c == 200 and not m["done"] and m["reason"] is None and "success" not in m and "stage" not in m
              and m.get("tick") == 1, f"{tag} oracle: a success showed in the answer {m}")
        c, st = call(svc, "/status", method="GET")
        check(c == 200 and not st["done"], f"{tag} oracle: status {st}")
        c, out = call(svc, "/finish")
        check(c == 200 and out.get("ok") and out["done"] and out["reason"] == "finished", f"{tag} oracle: /finish {c} {out}")
        for p in ("/submit", "/observe", "/finish"):
            check(call(svc, p, {"type": "joints", "actions": [[0, 0]]})[0] == 409, f"{tag} oracle: {p} after /finish is not 409")
        check(call(svc, "/spec", method="GET")[0] == 200 and call(svc, "/status", method="GET")[0] == 200,
              f"{tag} oracle: /spec or /status refused after /finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["ended_by"] == "finish" and f["hidden_success_seen"] and f["finalized"],
              f"{tag} oracle + /finish: {f.get('success')} {f.get('ended_by')}")
    scenario(S, tag, "oracle", run=oracle)

    def nop(svc, d):
        submit(svc, [0, 0], [0.2, 0])
        call(svc, "/finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["ended_by"] == "finish" and not f["hidden_success_seen"], f"{tag} nop + /finish: {f}")
    scenario(S, tag, "nop", run=nop)

    def undo(svc, d):
        submit(svc, [1, 0])
        submit(svc, [-0.5, 0])
        call(svc, "/finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["hidden_success_seen"] and f["hidden_success_first_step"] == 1,
              f"{tag} success then undo: {f.get('success')} seen {f.get('hidden_success_seen')}")
    scenario(S, tag, "undo", run=undo)

    def fail_after(svc, d):
        submit(svc, [1, 0])
        c, m = submit(svc, [0, 1])
        check(m["done"] and m["reason"] == "failed", f"{tag} failure rule after a success: {m['reason']}")
        check(call(svc, "/finish")[0] == 409, f"{tag} /finish after a failure end is not 409")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["ended_by"] == "failed", f"{tag} failure after success: {f.get('success')} {f.get('ended_by')}")
    scenario(S, tag, "fail_after", run=fail_after)

    def cap(svc, d):
        submit(svc, *([[0.05, 0]] * 40))
        c, m = submit(svc, [0, 0])
        check(c == 409, f"{tag} step cap: submit after the cap is {c}")
        c, m = call(svc, "/observe", {"cameras": ["a"]})
        check(c == 200 and m["done"] and m["reason"] == "step_limit", f"{tag} step cap: observe {c} {m.get('reason')}")
        check(call(svc, "/finish")[0] == 409, f"{tag} step cap: /finish after it is not 409")
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["ended_by"] == "step_limit", f"{tag} step cap (x = 2 at the end): {f.get('success')} {f.get('ended_by')}")
    scenario(S, tag, "cap", run=cap)

    def cap_reset(svc, d):           # an episode the step cap ended in success shows nothing and keeps its resets
        submit(svc, *([[0.05, 0]] * 40))
        c, st = call(svc, "/status", method="GET")
        check(st["done"] and st["reason"] == "step_limit" and st["resets_left"] == 1, f"{tag} cap + reset: status {st}")
        c, m = call(svc, "/reset", {"cameras": ["a"]})
        check(c == 200 and m["episode"] == 2, f"{tag} cap + reset: the reset after a step-cap end is {c}")
    scenario(S, tag, "cap_reset", budget=1, run=cap_reset)

    def limit(svc, d):
        check(svc.spec["max_control_steps"] == 5 and svc.spec["budget"].get("steps") == 5, f"{tag} step limit: spec {svc.spec['budget']}")
        c, m = submit(svc, [0.5, 0], [0.5, 0])
        check(m.get("steps_left") == 3 and m.get("step_limit") == 5, f"{tag} step limit: steps_left {m.get('steps_left')}")
        c, m = submit(svc, [0.1, 0], [-0.5, 0], [0, 0], [0, 0])
        check(m["done"] and m["reason"] == "step_limit" and m["executed_rows"] == 3, f"{tag} step limit: {m['reason']} {m['executed_rows']}")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["steps_used"] == 5 and f["step_limit"] == 5, f"{tag} step limit (undone at the end): {f}")
    scenario(S, tag, "limit", step_limit=5, run=limit)

    def timeout(svc, d):
        submit(svc, [1.5, 0])
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["ended_by"] == "session_end" and f["reason"] == "timeout", f"{tag} session end: {f}")
    scenario(S, tag, "timeout", run=timeout)

    class Events(Toy):
        end_judgement = "events"
    def events(svc, d):
        submit(svc, [1, 0], [-1, 0])
        call(svc, "/finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["end_judgement"] == "events", f"{tag} events: a moment reached did not count {f}")
    scenario(S, tag, "events", sim=Events(), run=events)

    def events_failed(svc, d):       # a moment reached, then the failure rule ends the episode: the event stands
        submit(svc, [1, 0], [-1, 0])
        c, m = submit(svc, [0, 1])
        check(m["done"] and m["reason"] == "failed", f"{tag} events + failure: {m['reason']}")
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["ended_by"] == "failed",
              f"{tag} events + failure: an event that happened was taken back {f.get('success')} {f.get('ended_by')}")
    scenario(S, tag, "events_failed", sim=Events(), run=events_failed)

    def events_failed_none(svc, d):  # the failure rule with no moment reached: 0
        submit(svc, [0.5, 0], [0, 1])
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["ended_by"] == "failed", f"{tag} events, failure, no event: {f.get('success')}")
    scenario(S, tag, "events_failed_none", sim=Events(), run=events_failed_none)

    class Settle(Toy):
        end_window_steps = 5
        drift = -0.1
    def settle_bad(svc, d):
        submit(svc, [1.2, 0])
        call(svc, "/finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["end_window_success"] is False and f["end_window_steps"] == 5,
              f"{tag} settle window (falls back under 1): {f.get('success')} {f.get('end_window_success')}")
    scenario(S, tag, "settle_bad", sim=Settle(), run=settle_bad)
    def settle_ok(svc, d):
        submit(svc, [2.0, 0])
        call(svc, "/finish")
        end_session(svc)
        f = final(d)
        check(f["success"] is True and f["end_window_success"] is True, f"{tag} settle window (stays): {f.get('success')}")
    scenario(S, tag, "settle_ok", sim=Settle(), run=settle_ok)

    def resets(svc, d):
        submit(svc, [1, 0])
        c, m = call(svc, "/reset", {"cameras": ["a"]})
        check(c == 200 and m["episode"] == 2, f"{tag} reset after a hidden success: {c}")
        submit(svc, [0.3, 0])
        call(svc, "/finish")
        check(call(svc, "/reset", {"cameras": ["a"]})[0] == 409, f"{tag} reset after /finish is not 409")
        end_session(svc)
        f = final(d)
        check(f["success"] is False and f["trial_hidden_success_seen"] and not f["hidden_success_seen"],
              f"{tag} resets: only the last episode is graded {f}")
    scenario(S, tag, "resets", budget=2, run=resets)

    # a crash mid-episode: the restart resumes the hidden success with the episode
    d = tempfile.mkdtemp()
    try:
        svc = S.Service(Toy(), data=d, agent_end=True)
        svc.start()
        submit(svc, [1, 0])
        with open(os.path.join(d, "startups.jsonl"), "a") as fh:
            fh.write(json.dumps({"ts": 0, "process": 1}) + "\n" + json.dumps({"ts": 0, "process": 2}) + "\n")
        svc2 = S.Service(Toy(), data=d, agent_end=True)
        svc2.start()
        check(svc2.now_success and svc2.seen_step == 1 and not svc2.done, f"{tag} resume: hidden state {svc2.now_success} {svc2.seen_step}")
        call(svc2, "/finish")
        end_session(svc2)
        check(final(d)["success"] is True, f"{tag} resume: verdict {final(d).get('success')}")
    except Exception as exc:  # noqa: BLE001
        check(False, f"{tag} resume: raised {exc!r}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


copies: dict[str, Path] = {}
for p in sorted([*(ROOT / "embodied_first_exam/benchmarks").glob("*/rcb_service.py"),
                 *(ROOT / "embodied_first_exam/benchmarks").glob("*/*/rcb_service.py"),
                 ROOT / "images/abc-sim/tools/realtime/rcb_service.py"]):
    copies.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
for h, path in copies.items():
    suite_21(load(path, f"rcb_service_{h[:8]}"), str(path.relative_to(ROOT)))

# 2.3: the realtime layer on each distinct copy that realtime tasks use (the layer imports `rcb_service`)
for h, path in copies.items():
    sys.modules["rcb_service"] = load(path, "rcb_service")
    R = load(STD / "realtime/rcb_realtime.py", "rcb_realtime")
    rcb1_max = R.MAX_BODY
    tag = f"2.3 on {path.relative_to(ROOT)}"
    for want, rows in ((True, [[0.5, 0], [0.5, 0]]), (False, [[1.0, 0], [-0.5, 0]])):
        d = tempfile.mkdtemp()
        try:
            svc = R.RealtimeService(Toy(), data=d, slowdown=1.0, agent_end=True)
            svc.start()
            job = R._Job("POST", "/submit")
            svc._rt_submit({"type": "joints", "actions": np.array(rows), "dt": 0.02, "k": 1, "interpolate": "hold",
                            "at": None, "view": ([], 10, "none", False), "note": ""}, job)
            check(svc.running, f"{tag}: the clock did not start")
            for _ in range(len(rows) + 2):
                svc.tick()
            check(not svc.done, f"{tag}: a success ended the realtime episode")
            fin = R._Job("POST", "/finish", b"{}")
            svc.dispatch(fin)
            code, _, body = fin.reply[1:]
            out = json.loads(body)
            check(code == 200 and out["reason"] == "finished" and not svc.running and svc.due_in(0.0) is None,
                  f"{tag}: /finish {code} {out} running={svc.running}")
            again = R._Job("POST", "/finish", b"{}")
            svc.dispatch(again)
            check(again.reply[1] == 409, f"{tag}: a second /finish is {again.reply[1]}")
            obs = R._Job("POST", "/observe", b'{"seconds": 0, "cameras": []}')
            svc.dispatch(obs)
            check(obs.reply[1] == 409 if obs.reply[0] == "raw" else False, f"{tag}: /observe after /finish not refused")
            svc.on_sigusr1()
            svc.poll()
            f = final(d)
            check(f["success"] is want and f["ended_by"] == "finish", f"{tag}: verdict {f.get('success')} (want {want})")
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(False, f"{tag}: raised {exc!r}")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    d = tempfile.mkdtemp()                      # eai-standard/3.0 review: the wire of the realtime layer
    try:
        svc = R.RealtimeService(Toy(), data=d, slowdown=1.0, agent_end=True)
        svc.start()
        big = R._Job("POST", "/finish", b"", content_length=rcb1_max + 1)
        svc.dispatch(big)
        check(big.reply[1] == 413 and not svc.done, f"{tag}: /finish over 64 MiB is {big.reply[1]}")
        hold = R._Job("POST", "/submit", json.dumps({"type": "joints", "interpolate": "hold", "seconds": 0.1,
                                                        "cameras": []}).encode())
        svc.dispatch(hold)
        m = rcb1.decode(bytes(svc._reply_rcb1(*hold.reply[1:])[2]))[0] if hold.reply[0] == "rcb1" else {}
        check(m.get("hold") is True and m.get("executed_rows") == 0 and m.get("duration_s") == 0.1,
              f"{tag}: realtime hold chunk answer {hold.reply[0]} {m}")
        for bad in (b'{"type": "joints", "interpolate": "hold", "seconds": true}',
                    b'{"type": "joints", "interpolate": "hold", "seconds": "0.1"}', b'{"last_s": "1"}'):
            j = R._Job("POST", "/observe" if b"last_s" in bad else "/submit", bad)
            svc.dispatch(j)
            check(j.reply[1] == 400, f"{tag}: {bad!r} is {j.reply[1]}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    d = tempfile.mkdtemp()
    try:
        class NoRec(Toy):
            record_frames = False
        svc = R.RealtimeService(NoRec(), data=d, slowdown=1.0, agent_end=True)
        rec = svc.spec["timing"].get("recorder", {})
        check(rec.get("cameras") == [] and rec.get("depth") == [] and "nothing" in rec.get("records", ""),
              f"{tag}: no recorder: /spec.timing.recorder {rec}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # off: /finish is a 404 in realtime too
    d = tempfile.mkdtemp()
    try:
        svc = R.RealtimeService(Toy(), data=d, slowdown=1.0, agent_end=False)
        svc.start()
        j = R._Job("POST", "/finish", b"{}")
        svc.dispatch(j)
        check(j.reply[1] == 404, f"{tag} off: /finish is {j.reply[1]}")
    finally:
        shutil.rmtree(d, ignore_errors=True)

if fails:
    print(f"{len(fails)} failure(s)")
    sys.exit(1)
print(f"ok agent-ended episodes in {len(copies)} distinct rcb_service.py (2.1) and the 2.3 realtime layer on each: "
      "oracle + /finish 1, nop 0, undone 0, failure after success 0, step cap / limit, session end, events, events + "
      "failure (the event stands), settle "
      "window, resets, resume, realtime /finish stops the clock")
