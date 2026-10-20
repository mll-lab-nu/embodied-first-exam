#!/usr/bin/env python3
"""CPU-only self-test of what the eai-standard/2.4 layer adds to 2.2's crash recovery (v2_4/rcb_limited.Episode): the call
watchdog's evidence and the physics-tick ledger, and of the HTTP layer's answer to malformed bodies (400, never a 500).
No simulator, no GPU, no Docker; needs numpy. About 15 seconds.

    python3 embodied_first_exam/standard/v2_4/selftest.py           # every case
    python3 embodied_first_exam/standard/v2_4/selftest.py watchdog  # the cases whose name contains "watchdog"

Each case drives Episode in child processes that end the way a sim service ends (os._exit after a "crash", the watchdog's
own exit, an idle give-up), with the record directory kept between them, as compose's `restart: on-failure` keeps /data.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

CHILD = r"""
import faulthandler, json, os, sys, time
import numpy as np
sys.path[:0] = [{here!r}, {base!r}]
import rcb_limited as L
data, mode = sys.argv[1], sys.argv[2]
ep = L.Episode(data, dim=2, resume="approx")
ep.startup(); ep.scene_built()
E = {{"calls": 0, "step": 0, "success": False, "done": False, "reason": None}}
seen = []
resumed = ep.begin(state=E, step=lambda row: seen.append(None), state_sha=lambda: "s%d" % ep.rows, proprio=lambda: np.zeros(3),
                   spec={{}}, step_ticks=lambda row, ticks: seen.append(int(ticks)))
print(json.dumps({{"resumed": resumed, "rows": ep.rows, "replayed_ticks": seen, "resumes": ep.resumes}}), flush=True)
def call(rows, ticks, finish=True):
    cid = ep.call_begin("/submit", None, deadline=time.time() + float(os.environ.get("CALL_BUDGET_S", "600")))
    for i in range(rows):
        ep.journal([float(i), 1.0], physics_steps=ticks)
    if finish:
        E["calls"] += 1; E["step"] += rows
        ep.checkpoint(E, lambda: "s%d" % ep.rows, lambda: np.zeros(3)); ep.call_end(cid, "/submit")
for step in mode.split(","):
    if step == "ok3": call(3, 7)                       # a completed call of 3 rows, 7 physics ticks each
    elif step == "crash5": call(5, 9, finish=False); ep._jf.flush(); ep._tf.flush(); os._exit(139)   # dies inside a call
    elif step == "hang": call(1, 5, finish=False); time.sleep(60); os._exit(0)                       # a native step that hangs
    elif step == "crash_idle": os._exit(139)           # dies between calls
os._exit(0)
"""


def child(data: str, mode: str, timeout: float = 30, **env) -> tuple[int | None, dict]:
    """Run one service process; returns (exit code, or None if it had to be stopped: a give-up idles for good), its line."""
    code = CHILD.format(here=HERE, base=os.path.dirname(HERE))
    p = subprocess.Popen([sys.executable, "-c", code, data, mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         env={**os.environ, **{k: str(v) for k, v in env.items()}})
    try:
        out, _ = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill(); out, _ = p.communicate(); rc = None
    line = next((x for x in out.splitlines() if x.startswith("{")), "{}")
    return rc, json.loads(line)


def final(data: str) -> dict:
    try:
        return json.load(open(os.path.join(data, "final.json")))
    except (OSError, ValueError):
        return {}


def files(data: str) -> set:
    return {n for n in os.listdir(data) if n.startswith("call-watchdog")}


def case_crash_in_call_is_not_the_watchdog():
    """A crash inside a call whose restart comes back after the call's deadline (the old rule's false positive)."""
    d = tempfile.mkdtemp(prefix="v24_")
    rc, _ = child(d, "ok3,crash5")
    assert rc == 139, rc
    assert files(d) == {"call-watchdog.json", "call-watchdog.trace"}, files(d)
    wd = json.load(open(os.path.join(d, "call-watchdog.json"))); wd["deadline"] = time.time() - 3600   # the restart was slow
    json.dump(wd, open(os.path.join(d, "call-watchdog.json"), "w"))
    rc, out = child(d, "ok3")
    assert rc == 0 and out["resumed"] and out["rows"] == 3, (rc, out)
    assert final(d).get("reason") is None, final(d)
    assert "call-watchdog.json" not in files(d), "the marker outlived the resume and the call after it"
    assert open(os.path.join(d, "call-watchdog.trace")).read() == ""
    rows = np.fromfile(os.path.join(d, "journal.f64")).size // 2
    assert rows == 6, rows                                # 3 replayed + 3 new; the crashed call's 5 rows are gone


def case_crash_between_calls_after_a_resume():
    """A stale marker must not turn a later crash outside any call into call_watchdog."""
    d = tempfile.mkdtemp(prefix="v24_")
    assert child(d, "ok3,crash5")[0] == 139
    assert child(d, "crash_idle", RCB_MAX_RESUMES=5)[0] == 139      # resumed, then died between calls
    assert files(d) == set(), f"the marker outlived the resume: {files(d)}"
    stale = os.path.join(d, "call-watchdog.json")                   # (the 2.4 layer before this test kept it: as if its
    if os.path.exists(stale):                                       # deadline had passed by the time of the next start)
        json.dump({**json.load(open(stale)), "deadline": time.time() - 3600}, open(stale, "w"))
    rc, out = child(d, "ok3", RCB_MAX_RESUMES=5)
    assert rc == 0 and out["resumed"] and out["resumes"] == 2, (rc, out)
    assert final(d).get("reason") is None, final(d)


def case_watchdog_fired_ends_the_episode():
    """The watchdog really ends a process whose call hangs: its banner is the evidence, and the restart gives up."""
    d = tempfile.mkdtemp(prefix="v24_")
    t = time.time()
    rc, _ = child(d, "ok3,hang", RCB_CALL_WATCHDOG_GRACE_S=1, CALL_BUDGET_S=1)
    assert rc == 1 and time.time() - t < 20, (rc, time.time() - t)        # faulthandler's exit, not the 60 s sleep
    trace = open(os.path.join(d, "call-watchdog.trace")).read()
    assert "Timeout (" in trace and "Thread" in trace, trace[:200]
    rc, _ = child(d, "ok3", timeout=6)
    assert rc is None, "a give-up idles with its PID file; this process went on instead"
    f = final(d)
    assert f.get("gave_up") and f.get("infra_error") == 1 and str(f.get("reason")).startswith("call_watchdog"), f


def case_watchdog_trace_is_per_call():
    """A call that finished leaves no banner behind for a later crash to inherit."""
    d = tempfile.mkdtemp(prefix="v24_")
    assert child(d, "ok3,ok3,crash5")[0] == 139
    assert open(os.path.join(d, "call-watchdog.trace")).read() == ""
    rc, out = child(d, "ok3")
    assert rc == 0 and out["resumed"] and out["rows"] == 6, (rc, out)


def case_tick_ledger_cut_with_the_journal():
    """A crash in the first call (no checkpoint with rows yet) cuts the tick ledger to 0 rows with the journal, so the
    rows journaled afterwards keep their own tick counts on the next resume."""
    d = tempfile.mkdtemp(prefix="v24_")
    assert child(d, "crash5")[0] == 139
    assert np.fromfile(os.path.join(d, "journal.ticks.i64"), dtype=np.int64).size == 5
    assert child(d, "ok3,crash5", RCB_MAX_RESUMES=5)[0] == 139
    rc, out = child(d, "", RCB_MAX_RESUMES=5)
    assert rc == 0 and out["resumed"] and out["rows"] == 3, (rc, out)
    assert out["replayed_ticks"] == [7, 7, 7], out["replayed_ticks"]       # not the lost call's 9s
    assert np.fromfile(os.path.join(d, "journal.ticks.i64"), dtype=np.int64).tolist() == [7, 7, 7]
    assert np.fromfile(os.path.join(d, "journal.f64")).size == 6


def case_malformed_bodies_are_400():
    """The HTTP layer: a body that is malformed (wrong-typed actions, a meta that is no object, wrong-typed kinematics
    fields) is answered 400 before the service's submit runs; it must never be a 500, which ends the episode."""
    import threading, urllib.request, urllib.error
    from http.server import HTTPServer
    sys.path[:0] = [HERE, os.path.dirname(HERE)]
    import rcb1, rcb_limited as L
    ran, ended = [], []
    kin = {"joint_names": ["a", "b"], "links": ["tcp"], "ik_targets": ["tcp"], "frame": "world"}
    svc = L.Service(spec={"kinematics": kin}, lock=threading.Lock(), state={"done": False}, submit=lambda meta, A: (ran.append(A.shape), ({"ok": True}, []))[1],
                    observe=lambda meta: ({"ok": True}, []), kinematics=lambda req: {"ok": True}, status=lambda: {},
                    on_submit_error=lambda exc: ended.append(repr(exc)), log=lambda ev: None)
    srv = HTTPServer(("127.0.0.1", 0), L.make_handler(svc)); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(path, body: bytes, ctype="application/json") -> int:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers={"Content-Type": ctype})
        try:
            return urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as exc:
            return exc.code
    try:
        bad = {"actions is an object": b'{"type": "joint_position", "actions": {"a": 1}}',
               "actions holds an object": b'{"type": "joint_position", "actions": [[1, {"a": 1}]]}',
               "actions holds a string": b'{"type": "joint_position", "actions": [["x", 1]]}',
               "an integer too large for a float": b'{"type": "joint_position", "actions": [[' + b"9" * 400 + b', 1]]}',
               "the body is a list": b'[1, 2]', "the body is not JSON": b'{"type": ',
               "a bad operation id": b'{"operation_id": 7, "actions": [[1, 2]]}',
               "a bad deadline": b'{"request_deadline_unix_s": "soon", "actions": [[1, 2]]}',
               "a deadline beyond the float range": (b'{"type": "joint_position", "request_deadline_unix_s": 1' + b"0" * 400
                                                     + b', "actions": [[1, 2]]}')}
        for what, body in bad.items():
            assert post("/submit", body) == 400, f"/submit where {what}: {post('/submit', body)}"
        frame = rcb1.encode({"type": "joint_position"}, [rcb1.array_part("actions", np.zeros((2, 2), np.float32))])
        listed = rcb1.encode([1], [rcb1.array_part("actions", np.zeros((2, 2), np.float32))])     # the frame's meta is a list
        code = post("/submit", listed, "application/x-rcb1")
        assert code == 400, f"/submit with an RCB1 frame whose meta is a list: {code}"
        for what, body in {"q is a string": b'{"op": "fk", "q": "abc"}', "q holds an object": b'{"op": "fk", "q": [{}, 1]}',
                           "max_iters is a list": b'{"op": "ik", "targets": {"tcp": [0,0,0,1,0,0,0]}, "max_iters": [3]}',
                           "tol_pos_m is null": b'{"op": "ik", "targets": {"tcp": [0,0,0,1,0,0,0]}, "tol_pos_m": null}'}.items():
            assert post("/kinematics", body) == 400, f"/kinematics where {what}: {post('/kinematics', body)}"
        assert not ran and not ended, f"executed {ran}, episode ended by {ended}"   # nothing ran, the episode goes on
        assert post("/submit", b'{"type": "joint_position", "actions": [[1, 2]]}') == 200 and ran == [(1, 2)], ran
        assert post("/submit", frame, "application/x-rcb1") == 200 and ran[-1] == (2, 2), ran
    finally:
        srv.shutdown()


def case_give_up_is_answered_and_a_repeated_camera_is_one():
    """What the 2.4 layer shares with 2.2 (embodied_first_exam/standard/selftest.py has the full cases): a service that gave up
    answers 409 to every request and the client raises EpisodeOver at once (before: nothing listened, and Robot() waited
    out its timeout, an hour by default); the recorder renders and returns a camera named N times once, not N * N times."""
    import socket
    sys.path[:0] = [HERE, os.path.dirname(HERE)]
    import rcb_client, rcb_limited as L
    grabs = []

    def grab(cams, want):
        grabs.append(list(cams)); return {c: np.zeros((2, 2, 3), np.uint8) for c in cams}, {}
    rec = L.Recorder(["top"] * 40, 1, grab, lambda: np.zeros(1), lambda cams: {}, lambda: 0)
    rec.tick(force=True)
    shapes = [p[3]["shape"] for p in rec.parts("frames", 10) if p[0] == "frames/top"]
    assert grabs == [["top"]] and shapes == [[1, 2, 2, 3]], (grabs, shapes)
    with socket.socket() as k:
        k.bind(("127.0.0.1", 0)); port = k.getsockname()[1]
    code = (f"import sys; sys.path[:0] = [{HERE!r}, {os.path.dirname(HERE)!r}]; import rcb_limited as L; "
            "ep = L.Episode(sys.argv[1], dim=2); ep.startup(); ep.give_up('too_few_cpus', infra=True)")
    with tempfile.TemporaryDirectory() as data:
        p = subprocess.Popen([sys.executable, "-c", code, data], env={**os.environ, "RCB_PORT": str(port)},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            t = time.time()
            try:
                rcb_client.Robot(base=f"http://127.0.0.1:{port}", timeout=120)
                raise AssertionError("Robot() connected to a service that gave up")
            except rcb_client.EpisodeOver as exc:
                assert "too_few_cpus" in str(exc) and "infrastructure" in str(exc), exc
            assert time.time() - t < 30, f"at once, not after its timeout ({time.time() - t:.0f} s)"
            fin = final(data)
            assert fin.get("reason") == "too_few_cpus" and fin.get("infra_error") == 1 and fin.get("gave_up"), fin
            assert p.poll() is None, "the service stays up for the collect hook"
        finally:
            p.kill(); p.wait()


def main(argv: list[str]) -> int:
    cases = [(n[5:], f) for n, f in sorted(globals().items()) if n.startswith("case_") and (not argv or any(a in n for a in argv))]
    bad = 0
    for name, fn in cases:
        t = time.time()
        try:
            fn(); print(f"ok   {name} ({time.time() - t:.1f} s)")
        except Exception as exc:  # noqa: BLE001
            bad += 1; print(f"FAIL {name}: {exc!r}")
    print(f"{len(cases) - bad}/{len(cases)} cases passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
