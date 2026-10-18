#!/usr/bin/env python3
"""RoboOlympics' low-level matches, option c (owner 2026-10-17, board 0152 decision 28): the agent's skill runs only in
the agent's own container (`game skill serve`, the task's environment/skillkit/skillhost.py) and the simulator calls it
over the loopback. These tests run the task's own files: a real skill server (the agent's kit) and the simulator's
InLoopLayer in timing "sync" on a stub match, and check
  - step() is ONE synchronous call at a due control step, applied at that step, and the world never waits longer than
    step_wait_s (+ a small scheduling allowance) whatever the skill does: slow, hanging, raising, garbage, a dead server;
  - a failure is the skill's (no command at that step, counted in the call log), never an exception in the control step;
  - a step() is skipped (counted) while a skill call is computing or another host operation holds the skill;
  - every version of the skill that played is reported for the episode (drain_loads), a live reload included;
  - RCB_SKILL_REMOTE_ONLY=1 refuses any skill source but the agent's server (no agent code in the sim container);
  - the sim's copy has no upload host, no jail and no upload endpoint left.
Needs numpy (the core's observe module).

    python3 scripts/roboolympics/tests/test_matchlow_sync_step.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASKS = sorted(ROOT.glob("tasks/roboolympics-*-matchlow-i*-standard-realtime"))
WAIT = 0.1
SLACK = 0.05            # scheduling allowance over the bound (well under the bound itself)

SKILL = '''
import json, os, time
MODE = os.path.join(os.path.dirname(__file__), "mode.txt")
def _m():
    try:
        return open(MODE).read().strip()
    except OSError:
        return "fast"
def {fn}(*a, state, spec):
    return {{"type": "hold"}}
def step(*, state, spec):
    m = _m()
    if m == "slow":
        time.sleep(0.4)
        return {{"type": "hold"}}
    if m == "hang":
        time.sleep(30)
    if m == "raise":
        raise RuntimeError("boom")
    if m == "garbage":
        return {{"type": {{"x": [1]}}, "q": "nope"}}
    if m == "huge":
        return {{"type": "hold", "pad": "x" * (8 << 20)}}
    if m == "deep":
        x = []
        for _ in range(900):
            x = [x]
        return {{"type": "hold", "deep": x}}
    if m == "probe":   # tries to read what is not sent: the call carries the sanctioned state only
        return {{"type": "hold", "keys": sorted(state)[:50]}}
    return {{"type": "hold", "v": 2 if m == "v2" else 1}}
'''


class Refused(Exception):
    pass


class Low:
    """The stub low level: hold commands only; anything else is refused, a malformed type raises (as a real parser
    might, e.g. a TypeError on an unhashable type)."""
    def parse(self, seat, body, match, ctx):
        if not isinstance(body, dict):
            raise TypeError("not a dict")
        if body.get("type") == "hold":
            return body
        hash(body.get("type"))                      # TypeError for an unhashable type
        raise Refused("unknown")

    def schema(self, match, seat):
        return {}


class Match:
    def __init__(self):
        self.k = 0

    def unit(self):
        return 1

    def observe(self, seat):
        return {"secret_ball": [1, 2, 3], "robot": {"q": [0] * 9}}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def load(task: Path):
    sim = task / "environment" / "sim"
    for k in [k for k in list(sys.modules) if k.split(".")[0] in ("skilleval", "core")]:
        del sys.modules[k]
    sys.path.insert(0, str(sim))
    import skilleval.inloop as IL
    sys.path.remove(str(sim))
    return IL


def test_sync(task: Path):
    IL = load(task)
    fn = "hit" if "tabletennis" in task.name else "act"
    kit = task / "environment" / "skillkit" / "skillhost.py"
    with tempfile.TemporaryDirectory() as tmp:
        skill = Path(tmp, "skill")
        skill.mkdir()
        (skill / f"{fn}.py").write_text(SKILL.format(fn=fn))
        mode = skill / "mode.txt"
        mode.write_text("fast")
        port = free_port()
        srv = subprocess.Popen([sys.executable, "-I", str(kit), "serve", "--tcp", f"127.0.0.1:{port}", "--skill",
                                str(skill), "--live"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    socket.create_connection(("127.0.0.1", port), 0.2).close()
                    break
                except OSError:
                    time.sleep(0.05)
            loop = IL.InLoop(f"tcp:127.0.0.1:{port}", fn, {"timing": {"mode": "sync"}},
                             timeouts={fn: 5.0, "step": 1.0, "load": 30.0}, load_timeout_s=30.0)
            lay = IL.InLoopLayer(Low(), {}, {"A": loop}, {}, step_every=2, timing="sync", step_wait_s=WAIT,
                                 state_of=lambda seat, m, cmd=None: {"q": [0] * 9})
            m = Match()
            lay._ensure_unit("A", m)                         # the unit's load runs in the worker
            for _ in range(200):
                if loop.loads:
                    break
                time.sleep(0.05)
            assert loop.loads and loop.loads[-1].get("ok"), loop.loads

            def tick(k):
                m.k = k
                t0 = time.monotonic()
                out = lay.tick("A", m)
                return out, time.monotonic() - t0

            out, dt = tick(1)                                 # not due (step_every 2): no call
            assert out is None and dt < 0.05 and not loop.calls, (out, dt)
            out, dt = tick(2)
            assert out == {"type": "hold", "v": 1}, out       # applied at the step it was asked for
            assert loop.calls[-1]["ok"] and loop.calls[-1]["k"] == 2 and loop.calls[-1]["wait_s"] == WAIT
            for bad in ("slow", "hang", "raise", "garbage", "huge", "deep"):
                mode.write_text(bad)
                n = len(loop.calls)
                out, dt = tick(2 * (n + 2))
                assert out is None, (bad, out)
                assert dt < WAIT + SLACK + (0.5 if bad == "huge" else 0.0), (bad, dt)   # the world waited at most the bound
                if bad != "garbage":
                    assert not loop.calls[-1]["ok"], (bad, loop.calls[-1])
                time.sleep(0.5 if bad in ("slow",) else 0.05)
            mode.write_text("probe")
            time.sleep(0.6)                                   # the slow / hanging calls drain on the server side
            for k in range(100, 140, 2):
                out, _ = tick(k)
                if out is not None:
                    break
            assert out is not None and out.get("keys") == ["q", "step"], (out, [(c.get("ok"), c.get("error"), c.get("wall_s")) for c in loop.calls[-6:]])   # the sanctioned state only
            mode.write_text("garbage")                        # an answer the low level cannot parse: the skill's failure
            for k in range(150, 190, 2):
                out, dt = tick(k)
                if loop.calls[-1]["ok"]:
                    break
            assert loop.calls[-1]["ok"] and out is None and dt < WAIT + SLACK, (out, dt, loop.calls[-1])
            assert any("malformed" in f for f in lay.failures), lay.failures
            # a live reload: a new version, reported once for the episode
            drained = lay.drain_loads()
            mode.write_text("v2")
            (skill / "extra.py").write_text("X = 1\n")
            for k in range(200, 260, 2):
                out, _ = tick(k)
                if out == {"type": "hold", "v": 2}:
                    break
            assert out == {"type": "hold", "v": 2}, out
            new = lay.drain_loads()
            assert any(r.get("live") and r.get("sha256") for _, r in new), new
            assert not lay.drain_loads()
            assert drained or new
            # busy: a skill call computing (call_pending) or the host held: the step is skipped, never waited for
            sk = lay.step_skipped.get("A", 0)
            lay._worker("A", m).call_pending = True
            out, dt = tick(300)
            assert out is None and dt < 0.05 and lay.step_skipped["A"] == sk + 1, (out, dt)
            lay._worker("A", m).call_pending = False
            with loop._lock:
                out, dt = tick(302)
            assert out is None and dt < 0.05 and lay.step_skipped["A"] == sk + 2, (out, dt)
            # the server stops: every call the player's failure, bounded
            srv.kill()
            srv.wait()
            out, dt = tick(304)
            assert out is None and dt < WAIT + SLACK and not loop.calls[-1]["ok"], (out, dt, loop.calls[-1])
            out, dt = tick(306)
            assert out is None and dt < WAIT + SLACK, (out, dt)
            lay.close()
        finally:
            srv.kill()


def test_drip(task: Path):
    """A server that drips its answer one byte at a time (each read within a socket timeout): the call still ends at
    its bound."""
    load(task)
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def run():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            def session(c):
                f = c.makefile("rwb")
                try:
                    while f.readline():
                        for ch in b'{"ok": true, "ret": {"type": "hold"}, "pad": "' + b"x" * 200:
                            c.sendall(bytes([ch]))
                            time.sleep(0.02)
                except OSError:
                    pass
            threading.Thread(target=session, args=(conn,), daemon=True).start()
    threading.Thread(target=run, daemon=True).start()
    try:
        h = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
        h.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
        for _ in range(3):
            t0 = time.monotonic()
            try:
                h.call("step", [], {}, wait_s=WAIT)
                raise AssertionError("a dripped answer was accepted")
            except SkillError as e:
                assert e.kind == "timeout", e.kind
            assert time.monotonic() - t0 < WAIT + SLACK, time.monotonic() - t0
        h.close()
    finally:
        srv.close()


def test_hostile_answers(task: Path):
    """Answers no parser should take inside the control step: JSON nested 200 000 deep, two lines, over 1 MiB, not
    UTF-8: each a SkillError (the player's failed call), never another exception."""
    load(task)
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost
    answers = [b"[" * 200000 + b"]" * 200000 + b"\n", b'{"ok": true}\n{"ok": true}\n', b"[" + b"1," * (1 << 20) + b"1]\n",
               b"\xff\xfe{}\n"]
    for ans in answers:
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]

        def run(ans=ans):
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            f = conn.makefile("rwb")
            if f.readline():
                try:
                    conn.sendall(ans)
                except OSError:
                    pass
            time.sleep(1)
            conn.close()
        threading.Thread(target=run, daemon=True).start()
        try:
            h = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
            h.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
            try:
                h.call("step", [], {}, wait_s=0.5)
                raise AssertionError(f"accepted {ans[:20]!r}")
            except SkillError:
                pass
            h.close()
        finally:
            srv.close()


def test_withheld_window(task: Path):
    """A server that accepts but never reads (its receive window full): the send itself is inside the call's bound."""
    load(task)
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]
    held = []
    threading.Thread(target=lambda: held.append(srv.accept()), daemon=True).start()
    try:
        h = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
        h.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
        big = {"pad": "x" * (16 << 20)}            # far beyond what the socket buffers hold
        t0 = time.monotonic()
        try:
            h.call("step", [], big, wait_s=WAIT)
            raise AssertionError("a call to a server that never reads returned")
        except SkillError as e:
            assert e.kind == "timeout", e.kind
        dt = time.monotonic() - t0
        assert dt < WAIT + SLACK, dt
        h.close()
    finally:
        srv.close()


def test_step_answer_cap(task: Path):
    """step()'s answer is parsed on the world's thread: more than 128 KiB is refused unread."""
    load(task)
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost, STEP_LINE_MAX
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        f = conn.makefile("rwb")
        while f.readline():
            try:
                conn.sendall(b'{"ok": true, "ret": {"type": "hold", "pad": "' + b"x" * (STEP_LINE_MAX + 10) + b'"}}\n')
            except OSError:
                return
    threading.Thread(target=run, daemon=True).start()
    try:
        h = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
        h.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
        try:
            h.call("step", [], {}, wait_s=0.5)
            raise AssertionError("an oversized step answer was accepted")
        except SkillError as e:
            assert e.kind == "server", e.kind              # the player's own server, never "host"
        h.close()
    finally:
        srv.close()


def test_tick_counts_for_the_seat(task: Path):
    """A world_step error after a step() command of the seat's own skill, before any act: the agent's 0, not a retry."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("grade_under_test", task / "tests" / "grade.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    d = {"cfg": {"seats": ["A"]}, "sides": {"A": "A"}, "verdict_replay": False, "finalized": True, "slowdown": 10,
         "reason": "technical_error", "errors": [{"where": "world_step", "error": "x"}], "valid_trial": False,
         "meter_error": {"A": False}, "proxy_error": {"A": False}, "match_winner": None, "scores": {"A": 0},
         "state_sha": "s", "commands_sha": "c", "source_sha": "x", "steps": 10, "play": "program",
         "player_modes": {"A": "unmetered"}, "transient_api_errors": {}, "unrecovered_api_errors": {},
         "seats": {"A": {"applied": 0, "applied_tick": 3}}}
    out = g.grade(d, {}, {}, lambda d: {})
    assert out["technical_failure"] == 0 and out["success"] == 0 and out["agent_sim_error"] == 1, out
    d["seats"]["A"].update(applied_tick=0, tick_submitted=1)      # its first step() command made the step raise
    out = g.grade(d, {}, {}, lambda d: {})
    assert out["technical_failure"] == 0 and out["agent_sim_error"] == 1, out
    d["seats"]["A"].update(applied_tick=0, tick_submitted=0)
    out = g.grade(d, {}, {}, lambda d: {})
    assert out["technical_failure"] == 1 and out["agent_sim_error"] == 0, out


def fake(handler):
    """A loopback server: handler(conn, file) per connection, each in its own thread."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def run():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=handler, args=(conn, conn.makefile("rwb")), daemon=True).start()
    threading.Thread(target=run, daemon=True).start()
    return srv, srv.getsockname()[1]


def test_late_configure(task: Path):
    """A server that accepts at once but answers the reconnect's configure late: the step still ends by its bound."""
    load(task)
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost

    def h(conn, f):
        try:
            while True:
                line = f.readline()
                if not line:
                    return
                if b'"configure"' in line:
                    time.sleep(0.5)
                conn.sendall(b'{"ok": true, "ret": {"type": "hold"}}\n')
        except OSError:
            pass
    srv, port = fake(h)
    try:
        rh = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
        rh.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
        for _ in range(3):
            t0 = time.monotonic()
            try:
                rh.call("step", [], {}, wait_s=WAIT)
                raise AssertionError("a late configure was waited for")
            except SkillError as e:
                assert e.kind == "timeout", e.kind
            assert time.monotonic() - t0 < WAIT + SLACK, time.monotonic() - t0
        rh.close()
    finally:
        srv.close()


def test_stale_answer(task: Path):
    """An answer nobody asked for waiting on the connection: the next call drops it, reconnects and gets its own."""
    load(task)
    from skilleval.skillhost import RemoteHost
    n = {"conn": 0}

    def h(conn, f):
        n["conn"] += 1
        first = n["conn"] == 1
        try:
            while True:
                line = f.readline()
                if not line:
                    return
                if b'"configure"' in line:
                    conn.sendall(b'{"ok": true}\n')
                    continue
                conn.sendall(b'{"ok": true, "ret": {"type": "hold", "v": %d}}\n' % n["conn"])
                if first:
                    time.sleep(0.02)
                    conn.sendall(b'{"ok": true, "ret": {"type": "hold", "v": 99}}\n')     # unsolicited
        except OSError:
            pass
    srv, port = fake(h)
    try:
        rh = RemoteHost(f"tcp:127.0.0.1:{port}", live=True)
        rh.configure("hit", {}, {"hit": 5.0, "step": 1.0}, 30.0)
        assert rh.call("step", [], {}, wait_s=0.5) == {"type": "hold", "v": 1}
        time.sleep(0.1)
        out = rh.call("step", [], {}, wait_s=0.5)
        assert out == {"type": "hold", "v": 2}, out          # a new connection, never the stale v 99
        rh.close()
    finally:
        srv.close()


def test_remote_only(task: Path):
    IL = load(task)
    os.environ["RCB_SKILL_REMOTE_ONLY"] = "1"
    try:
        for src in ("/app/output/skill", "unix:/x/skill.sock", "upload:A"):
            try:
                IL.InLoop(src, "hit", {})
            except ValueError:
                continue
            raise AssertionError(f"RCB_SKILL_REMOTE_ONLY accepted {src}")
    finally:
        del os.environ["RCB_SKILL_REMOTE_ONLY"]
    loop = IL.InLoop("tcp:127.0.0.1:9", "hit", {})
    for timing in ("wall", "free"):
        try:
            IL.InLoopLayer(Low(), {}, {"A": loop}, {}, timing=timing)
        except ValueError:
            continue
        raise AssertionError(f"timing {timing} accepted for the agent's own server")
    env = {"RCB_SKILL_INLOOP_A": "tcp:127.0.0.1:9", "RO_SLOWDOWN": "10"}
    decl = {"modes": {"low": {"deliverable": {"path": "/app/output/skill/hit.py", "time_limits_s": {"hit": 5, "step": 1}},
                              "inloop": {"skills": []}}}}
    lay = IL.layer_from_env(Low(), {}, decl, spec={}, control_dt=0.01, seats=("A",), environ=env)
    assert lay.timing == "sync" and abs(lay.step_wait_s - 0.1) < 1e-9, (lay.timing, lay.step_wait_s)
    lay.close()


def test_nothing_runs_in_the_sim(task: Path):
    sim = task / "environment" / "sim"
    for f in ("skilleval/skillhost.py", "skilleval/sandbox.py", "skilleval/inloop.py", "core/service.py",
              "core/http.py", "core/game.py"):
        s = (sim / f).read_text()
        for w in ("class UploadHost", "UPLOAD_HOSTS", "_seccomp_program", "def skill_upload", "SKILL_BODY_MAX",
                  '"upload:"'):
            assert w not in s, (f, w)
    comp = (task / "environment" / "docker-compose.yaml").read_text()
    assert 'RCB_SKILL_REMOTE_ONLY: "1"' in comp and 'RCB_SKILL_INLOOP_TIMING: "sync"' in comp
    assert 'RCB_SKILL_INLOOP_A: "tcp:127.0.0.1:8765"' in comp


def main() -> int:
    if not TASKS:
        print("ok roboolympics matchlow sync step: no matchlow task")
        return 0
    failed = 0
    for t in TASKS:
        for fn in (test_nothing_runs_in_the_sim, test_remote_only, test_drip, test_hostile_answers, test_withheld_window,
                   test_step_answer_cap, test_tick_counts_for_the_seat, test_late_configure, test_stale_answer, test_sync):
            try:
                fn(t)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {fn.__name__} {t.name}: {type(exc).__name__}: {exc}")
    print(f"{'ok' if not failed else 'FAIL'} roboolympics matchlow sync step: {len(TASKS)} task(s), {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main())
