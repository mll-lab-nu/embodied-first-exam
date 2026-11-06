"""Unit tests of skilleval/ on a synthetic sport (skilleval/tests/fixture: one seat commanding two robots). Standard
library only (python >= 3.11):

    python3 skilleval/tests/test_skilleval.py
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.sport import Refused, check_command  # noqa: E402
from skilleval.evaluate import Harness  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture"
CASES = [{"id": "c1", "request": {"arm": "left", "t": 0.5}}, {"id": "c2", "request": {"arm": "both", "t": 1.0}}]


def test_contract_enum_field():
    """An enum field in the core's format validates a request as the core's check_command does, and describe() and
    the act schema made from the contract carry it."""
    c = Harness(FIXTURE, "platform", None).contracts["swing"]
    arm = {"type": "enum", "values": ["left", "right", "both"]}
    assert c.describe()["request"]["arm"] == arm and c.request_schema()["swing"]["arm"] == arm
    for v in ("left", "right", "both", "up", "", ["left"], None, 1):
        why = c.valid_request({"arm": v, "t": 0.5})
        try:
            check_command(c.request_schema(), {"type": "swing", "arm": v, "t": 0.5})
            core_ok = True
        except Refused:
            core_ok = False
        assert (why is None) == core_ok == (v in arm["values"]), (v, why)
        assert why in (None, "arm must be one of ['left', 'right', 'both']"), why


def test_checks_ignore_only_the_core_entity():
    """Stage 6: the act of a seat that commands several robots carries the core's entity beside the skill's fields;
    the contract check leaves out that field and nothing else."""
    h = Harness(FIXTURE, "platform", None)
    same, valid = h.checks(CASES)
    assert same["ok"] and "entity" not in same["detail"]["high"], same
    assert valid["ok"], valid
    c = h.contracts["swing"]
    h.contracts = {"swing": replace(c, args={**c.args, "t": {**c.args["t"], "max": 2.0}})}
    assert not h.checks(CASES)[0]["ok"]


def test_inloop_lowers_with_the_players_skill():
    """skilleval/inloop.py: a skill call is lowered by the player's own skill in its sandbox (a private copy of the
    files: a change during a unit does not reach it, at the next unit it is reloaded), its answer checked by the low
    level's parser (an invalid or missing answer is a no-op); other acts pass only where raw_allowed says so (else
    409); step() runs every step_every steps through tick; every call is logged with the files' sha256."""
    import tempfile
    from skilleval.contract import SkillContract, Tolerance
    from skilleval.inloop import InLoop, InLoopLayer, files_sha

    class Low:
        def schema(self, match, seat):
            return {"go": {"x": {"type": "number", "min": -1, "max": 1}}}

        def parse(self, seat, body, match, ctx):
            return check_command(self.schema(match, seat), body)

        def lower(self, seat, cmd, prepared, match):
            return cmd, {}

        def reply(self, seat, cmd, info, match):
            return {}

    class Match:
        k, u, live = 0, 0, False

        def observe(self, seat, query=None):
            return {"pos": 0.5, "secret": 1}

        def unit(self):
            return self.u

    aim = SkillContract(name="aim", call="aim(x)", args={"x": {"type": "number", "min": -1, "max": 1}},
                        returns="go", measured="-", tolerances=(Tolerance("err", 0.1),))
    d = Path(tempfile.mkdtemp())
    (d / "aim.py").write_text("def aim(x, *, state, spec):\n    return {'type': 'go', 'x': x / 2} if x < 0.9 else {'type': 'go', 'x': 5}\n"
                              "def step(*, state, spec):\n    return {'type': 'go', 'x': state['pos'] + ('secret' in state)}\n")
    loop = InLoop(d, "aim", spec={}, timeouts={"aim": 5, "step": 5})
    m = Match()
    lay = InLoopLayer(Low(), {"aim": aim}, {"A": loop}, {"observation": {"fields": ["pos"]}},
                      raw_allowed=lambda seat, match: not match.live, noop={"type": "noop"}, step_every=2)
    assert lay.parse("A", {"type": "aim", "x": 0.4}, m, {}) == {"type": "aim", "x": 0.4}
    for bad in ({"type": "aim", "x": 3}, {"type": "aim"}):
        try:
            lay.parse("A", bad, m, {})
            raise AssertionError(bad)
        except Refused as e:
            assert e.code == 400
    assert lay.parse("A", {"type": "go", "x": 0.1}, m, {}) == {"type": "go", "x": 0.1}
    m.live = True
    try:
        lay.parse("A", {"type": "go", "x": 0.1}, m, {})
        raise AssertionError("raw command accepted while live")
    except Refused as e:
        assert e.code == 409
    low, info = lay.lower("A", {"type": "aim", "x": 0.4}, None, m)
    assert low == {"type": "go", "x": 0.2} and info["ok"] and info["sha256"] == files_sha(d)
    low, info = lay.lower("A", {"type": "aim", "x": 0.95}, None, m)      # an invalid answer: a no-op, counted
    assert low == {"type": "noop"} and info["skill_failed"] and lay.failures
    assert lay.tick("A", m) == {"type": "go", "x": 0.5}                  # the whitelisted state only (no secret)
    m.k = 1
    assert lay.tick("A", m) is None
    sha0 = files_sha(d)
    (d / "aim.py").write_text("def aim(x, *, state, spec):\n    return {'type': 'go', 'x': -x}\n")
    m.k = 0
    assert lay.lower("A", {"type": "aim", "x": 0.4}, None, m)[0] == {"type": "go", "x": 0.2}   # same unit: old code
    m.u = 1
    assert lay.lower("A", {"type": "aim", "x": 0.4}, None, m)[0] == {"type": "go", "x": -0.4}  # next unit: reloaded
    assert lay.tick("A", m) is None                                     # the new skill has no step
    shas = [c["sha256"] for c in loop.calls]
    assert shas[0] == sha0 and shas[-1] == files_sha(d) != sha0
    sm = loop.summary()
    assert sm["aim"]["n"] == 4 and sm["step"]["n"] == 1 and len(sm["loads"]) == 2
    loop.close()



# ------------------------------------------------------------------ the skill in the loop: hosts, timing, rules
def _aim_contract():
    from skilleval.contract import SkillContract, Tolerance
    return SkillContract(name="push", call="push(v)", args={"v": {"type": "number", "min": -1, "max": 1}},
                         returns="move", measured="-", tolerances=(Tolerance("err", 0.1),))


def test_skillhost_copies_regular_files_only_and_hashes_like_the_evaluator():
    """skilleval/skillhost.py: the private copy holds the skill's regular files only (no symlink followed or taken, no
    FIFO), so a symlink to the simulator's files gives nothing; the identity (files_sha) is the post-match evaluator's
    (evaluate.tree_sha); a missing module, a missing directory and a load error are reported, not raised."""
    import os
    import tempfile
    from skilleval import evaluate
    from skilleval.skillhost import SkillHost, files_sha
    d = Path(tempfile.mkdtemp())
    (d / "push.py").write_text("import os\ndef push(v, *, state, spec):\n    return sorted(os.listdir('.'))\n")
    (d / "data").mkdir()
    (d / "data" / "w.txt").write_text("1")
    secret = Path(tempfile.mkdtemp()) / "secret.txt"
    secret.write_text("sim internals")
    os.symlink(secret, d / "link.txt")
    os.symlink(secret.parent, d / "linkdir")
    os.mkfifo(d / "pipe")
    assert files_sha(d) == evaluate.tree_sha(d)
    h = SkillHost(d)
    h.configure("push", {}, {"push": 5})
    rec = h.refresh(0)
    assert rec["ok"] and rec["sha256"] == files_sha(d), rec
    got = h.call("push", [0.1], {})
    assert got == ["data", "push.py"], got                            # the copy: no link, no FIFO
    assert h.refresh(1) is None                                       # unchanged: kept
    (d / "push.py").write_text("def push(v, *, state, spec):\n    raise RuntimeError('x')\n")
    assert h.refresh(2)["ok"]
    try:
        h.call("push", [0.1], {})
        raise AssertionError("no SkillError")
    except Exception as e:  # noqa: BLE001
        assert type(e).__name__ == "SkillError" and e.kind == "error"
    (d / "push.py").write_text("def push(v *, state, spec):\n")
    r = h.refresh(3)
    assert not r["ok"] and "SyntaxError" in r["error"] and h.status()["load_error"]
    (d / "push.py").unlink()
    assert "no push.py" in h.refresh(4)["error"]
    h.close()
    h2 = SkillHost(d / "nothing")
    h2.configure("push", {}, {})
    assert "no skill directory" in h2.refresh(0)["error"] and not h2.has("push")


def test_remote_host_over_the_socket_is_the_local_host():
    """The generated tasks reach the seat's skill container over a Unix socket (skillhost.serve / RemoteHost): the
    same loads, answers, errors and time-outs as in process; a closed server is a host error (a technical failure),
    and the client reconnects at the next refresh."""
    import tempfile
    import threading
    from skilleval.sandbox import SkillError
    from skilleval.skillhost import RemoteHost, files_sha, serve
    d = Path(tempfile.mkdtemp())
    (d / "push.py").write_text("import time\ndef push(v, *, state, spec):\n    if v > 0.9: time.sleep(3)\n"
                               "    return {'type': 'move', 'v': v / 2, 'k': state['step'], 'spec': sorted(spec)}\n"
                               "def step(*, state, spec):\n    return None\n")
    sock = str(Path(tempfile.mkdtemp()) / "ipc" / "skill.sock")
    threading.Thread(target=serve, args=(sock, str(d)), daemon=True).start()
    r = RemoteHost(sock, connect_timeout_s=10)
    r.configure("push", {"a": 1}, {"push": 1.0}, 10)
    rec = r.refresh(0)
    assert rec["ok"] and rec["sha256"] == files_sha(d) and r.has("push") and r.has("step"), rec
    assert r.call("push", [0.5], {"step": 7}) == {"type": "move", "v": 0.25, "k": 7, "spec": ["a"]}
    try:
        r.call("push", [0.95], {"step": 7})
        raise AssertionError("no time-out")
    except SkillError as e:
        assert e.kind == "timeout" and not r.has("push")
    try:
        r.call("push", [0.5], {"step": 8})
        raise AssertionError("dead skill answered")
    except SkillError as e:
        assert e.kind == "dead"
    assert r.refresh(1)["ok"] and r.call("push", [0.2], {"step": 9})["v"] == 0.1   # restarted at the next unit
    r.close()
    gone = RemoteHost(str(Path(tempfile.mkdtemp()) / "none.sock"), connect_timeout_s=0.3)
    gone.configure("push", {}, {})
    rec = gone.refresh(0)
    assert not rec["ok"] and rec.get("host_error") and not gone.has("push")


def test_inloop_rules_free_types_entity_and_state():
    """InLoopLayer: low-level command types in `free` pass at any time, the others through raw_allowed(seat, match,
    cmd) (the 3-argument form sees the command: gating by type, e.g. walking allowed, arm plans not); a skill call
    keeps its `entity` (checked against the seat's robots), the skill's state carries it, the skill's command gets it
    when it names none; state_of replaces the default state (e.g. one robot's entry)."""
    import tempfile
    from skilleval.inloop import InLoop, InLoopLayer

    class Low:
        def schema(self, match, seat):
            return {"move": {"v": {"type": "number", "min": -1, "max": 1}}, "walk": {"x": {"type": "number"}},
                    "toss": {}}

        def parse(self, seat, body, match, ctx):
            return check_command(self.schema(match, seat), body)

        def lower(self, seat, cmd, prepared, match):
            return cmd, {}

        def reply(self, seat, cmd, info, match):
            return {}

    class Match:
        k, u = 4, 0

        def observe(self, seat, query=None):
            return {"pos": 1.0}

        def unit(self):
            return self.u

        def entities(self, seat):
            return ("e0", "e1")

    d = Path(tempfile.mkdtemp())
    (d / "push.py").write_text("def push(v, *, state, spec):\n"
                               "    return {'type': 'move', 'v': v, 'entity': 'e0'} if state['entity'] == 'e0' and"
                               " state['mine'] == 'e0' else {'type': 'move', 'v': -v}\n")
    loop = InLoop(d, "push", spec={}, timeouts={"push": 5})
    seen = []
    lay = InLoopLayer(Low(), {"push": _aim_contract()}, {"A": loop}, {"observation": {"fields": ["pos"]}},
                      raw_allowed=lambda seat, match, cmd: seen.append(cmd["type"]) or cmd["type"] == "walk",
                      noop={"type": "noop"}, free=("toss",),
                      state_of=lambda seat, match, cmd: {"mine": (cmd or {}).get("entity")})
    m = Match()
    assert lay.parse("A", {"type": "walk", "x": 1}, m, {})["type"] == "walk"
    assert lay.parse("A", {"type": "toss"}, m, {})["type"] == "toss" and "toss" not in seen
    try:
        lay.parse("A", {"type": "move", "v": 0.1}, m, {})
        raise AssertionError("move accepted")
    except Refused as e:
        assert e.code == 409 and "push" in str(e)
    try:
        lay.parse("A", {"type": "push", "v": 0.1, "entity": "e7"}, m, {})
        raise AssertionError("unknown entity accepted")
    except Refused as e:
        assert e.code == 400
    for ent, v in (("e0", 0.3), ("e1", -0.3)):
        cmd = lay.parse("A", {"type": "push", "v": 0.3, "entity": ent}, m, {})
        assert cmd["entity"] == ent
        low, info = lay.lower("A", cmd, None, m)
        assert low == {"type": "move", "v": v, "entity": ent} and info["ok"], (low, info)
    loop.close()


def test_inloop_wall_timing_in_the_realtime_service():
    """Timing "wall" in the core's realtime service (core/tests/fixture, slowdown 1: 10 ms per control step): a skill
    call computes off the world's lock while the world runs on, its command takes effect at the first step after it
    returns (here >= 5 steps after the call for a 60 ms skill) and the reply says so; step() runs in the background
    and its commands are logged where they took effect; joint commands are refused while raw_allowed says no; the
    episode replays without the skill, bit for bit; every call is in inloop_A.jsonl with its sha256."""
    import json
    import os
    import tempfile
    import threading
    import time
    from core.episode import load_plugin, read_rows, replay
    from core.realtime import RealtimeService
    from core.sport import MatchConfig
    from skilleval.inloop import layer_from_env
    from skilleval.skillhost import files_sha

    os.environ.update(READY_TIMEOUT_S="5", START_TIMEOUT_S="5", BARRIER_LEAD_S="0.05", PLAYER_MODE_A="oracle")
    plugin = str(ROOT / "core" / "tests" / "fixture" / "plugin.py")
    sport = load_plugin(plugin)
    d = Path(tempfile.mkdtemp())
    (d / "push.py").write_text("import time\ndef push(v, *, state, spec):\n    time.sleep(0.06)\n"
                               "    return {'type': 'move', 'entity': 'e0', 'v': v}\n"
                               "def step(*, state, spec):\n    time.sleep(0.03)\n"
                               "    return {'type': 'move', 'entity': 'e1', 'v': 0.001 * (state['step'] % 7)}\n")
    logd = Path(tempfile.mkdtemp())
    decl = {"observation": {"fields": ["unit", "pos"]},
            "modes": {"low": {"implements": ["push"], "deliverable": {"path": "/app/output/skill/push.py",
                                                                     "time_limits_s": {"load": 30, "push": 2, "step": 1}},
                              "inloop": {"step_every": 4}}}}
    env = {"RCB_SKILL_INLOOP_A": str(d), "RCB_SKILL_INLOOP_LOG": str(logd), "RO_SLOWDOWN": "1"}
    lay = layer_from_env(type(sport.action_layer("low"))(0), {"push": _aim_contract()}, decl, spec={"x": 1},
                         control_dt=0.01, raw_allowed=lambda seat, match, cmd: cmd["v"] >= 0, environ=env)
    assert lay is not None and lay.timing == "wall" and layer_from_env(None, {}, decl, spec={}, control_dt=0.01,
                                                                        environ={}) is None
    assert lay.loops["A"].host.spec["timing"]["compute_counts"] and lay.loops["A"].host.spec["timing"]["period_s"] == 0.01

    class InLoopSport(type(sport)):
        def action_layer(self, level):
            return lay

    cfg = MatchConfig(sport="fixture", format="solo", seats=("A",), seed=1, slowdown=1.0)
    svc = RealtimeService(InLoopSport(), plugin, cfg, Path(tempfile.mkdtemp(prefix="inloop-rt-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    post = svc.routes(True)
    replies = []

    def player():
        post["start"]("A", {})
        while svc.phase != "over":
            if svc.phase == "review":
                if not svc.seats["A"].ready:
                    post["ready"]("A", {"why": "w", "plan": "p"})
            elif svc.phase == "running" and len(replies) < 6:
                replies.append(post["act"]("A", {"type": "push", "v": 0.5, "entity": "e0"}))
                try:
                    replies.append(post["act"]("A", {"type": "move", "v": -0.5, "entity": "e1"}))
                except Refused as e:
                    replies.append((e.code, str(e)))
            time.sleep(0.005)

    th = threading.Thread(target=player, daemon=True)
    th.start()
    t0 = time.time()
    while not svc.finalized and time.time() - t0 < 60:
        time.sleep(0.05)
    fin = json.loads((svc.data / "final.json").read_text())
    assert fin["valid_trial"] and fin["deterministic"], fin.get("errors")
    hits = [r[1] for r in replies if r[0] == 200]
    assert hits, replies
    for h in hits:
        sk = h["took_effect"]["skill"]
        assert sk["ok"] and sk["sha256"] == files_sha(d) and h["took_effect"]["step"] - sk["k_call"] >= 5, h
    assert all(r[0] == 409 for r in replies if r[0] != 200), replies
    rows = read_rows(svc.data / "episode.jsonl")
    steps = [x for x in rows if x["ev"] == "cmd" and x["cmd"]["entity"] == "e1"]
    assert steps, rows[:20]                                             # step(): applied when it returned
    rep = replay(sport, rows)                                           # without the skill (also: deterministic)
    assert rep["scores"] == svc.m.scores() and rep["state_sha"] == svc.m.state_digest(), rep
    log = [json.loads(x) for x in (logd / "inloop_A.jsonl").read_text().splitlines()]
    assert log[0]["op"] == "load" and log[0]["ok"] and {x.get("fn") for x in log[1:]} == {"push", "step"}
    assert all(x["sha256"] == files_sha(d) for x in log)
    assert all(x["k_done"] >= x["k"] for x in log[1:])
    sm = lay.summary()["A"]
    assert sm["push"]["steps_p50"] >= 5 and sm["push"]["errors"] == 0, sm
    assert sm["step"]["steps_p50"] >= 2 and sm["step"]["n"] >= len(steps), sm      # 30 ms of compute: >= 2 steps late
    pushes = [x["k"] for x in log if x.get("fn") == "push"]
    for kc, h in zip(pushes, hits):                                     # no step() starts while a push is in flight
        k_eff = h["took_effect"]["step"]
        assert not [x for x in log if x.get("fn") == "step" and kc < x["k"] < k_eff], (kc, k_eff)
    lay.close()


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in tests:
        try:
            f()
            print("ok  ", n)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL", n)
            traceback.print_exc()
    print(f"{len(tests) - bad}/{len(tests)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
