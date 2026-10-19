"""Unit tests of the core's stage-0 hooks on the synthetic realtime fixture (core/tests/fixture), of the start window
(no-show rule, at the window and at a collect before the start, both protocols; turn fixture core/tests/fixture_turn) and of the outcome and grading rules. Standard library + numpy; run in the sim image:
    docker run --rm -v $PWD:/w -w /w ghcr.io/mll-lab-nu/efe:olympiad-0.1.0 \\
        python3 core/tests/test_core.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.update(READY_TIMEOUT_S="1.5", START_TIMEOUT_S="5", BARRIER_LEAD_S="0.05")

from core.episode import load_plugin  # noqa: E402
from core.grading import grade, line_ok  # noqa: E402
from core.outcome import decide  # noqa: E402
from core.realtime import RealtimeService  # noqa: E402
from core.sport import FINISHED, PLAYING, MatchConfig, Phase, Refused  # noqa: E402
from core.turn import TurnService  # noqa: E402

PLUGIN = str(Path(__file__).resolve().parent / "fixture" / "plugin.py")
SPORT = load_plugin(PLUGIN)
PLUGIN_TURN = str(Path(__file__).resolve().parent / "fixture_turn" / "plugin.py")
SPORT_TURN = load_plugin(PLUGIN_TURN)


def service(seats, sides=None, fmt="team"):
    for s in seats:
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture", format=fmt, seats=tuple(seats), seed=1, slowdown=1.0, sides=sides)
    svc = RealtimeService(SPORT, PLUGIN, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    return svc, svc.routes(True)


def turn_service(seats, sides=None, fmt="duel"):
    for s in seats:
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture_turn", format=fmt, seats=tuple(seats), seed=1, first=seats[0], sides=sides,
                      action_level="low")
    svc = TurnService(SPORT_TURN, PLUGIN_TURN, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    return svc, svc.routes(True)


def play_turn(svc, post, seat, v=0.5):
    """One seat's turn loop: start, then on its turn act (v) and review, until the end."""
    post["start"](seat, {})
    while svc.phase != "over":
        st = post["wait"](seat, {"timeout_s": 1})[1]["state"]
        if st["done"] or not st["your_turn"]:
            continue
        if st["awaiting_review"]:
            post["ready"](seat, {"why": "w", "plan": "p"})
        else:
            post["act"](seat, {"v": v})


def play(svc, post, seat, review=True, act=None):
    """One seat's loop: start, then act (act(seat, post) each round) and review at every unit end until the end."""
    post["start"](seat, {})
    while svc.phase != "over":
        if svc.phase == "review":
            if review and not svc.seats[seat].ready and seat in svc.due():
                post["ready"](seat, {"why": "w", "plan": "p"})
            time.sleep(0.01)
            continue
        if svc.phase == "running" and act:
            act(seat, post)
        time.sleep(0.01)


def finish(svc, timeout=60):
    t = time.time()
    while not svc.finalized and time.time() - t < timeout:
        time.sleep(0.1)
    return json.loads((svc.data / "final.json").read_text())


def run_all(svc, post, seats, **kw):
    th = [threading.Thread(target=play, args=(svc, post, s), kwargs=kw.get(s, {}), daemon=True) for s in seats]
    for t in th:
        t.start()
    return finish(svc)


def test_seats_sides_entities_and_team_channel():
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    svc, post = service(list(sides), sides)
    th = [threading.Thread(target=post["start"], args=(s, {}), daemon=True) for s in sides]
    for t in th:
        t.start()
    while svc.phase != "running":
        time.sleep(0.01)
    lock = svc.seats["A1"].act_lock("e0")
    lock.acquire()                                         # an act of A1's entity e0 is in flight
    try:
        assert post["act"]("A1", {"type": "move", "v": 0.5, "entity": "e0"})[0] == 429
        code, out = post["act"]("A1", {"type": "move", "v": 0.5, "entity": "e1"})   # another entity: accepted
        assert code == 200, out
    finally:
        lock.release()
    try:
        post["act"]("A1", {"type": "move", "v": 0.5, "entity": "e9"})
        raise AssertionError("unknown entity accepted")
    except Refused:
        pass
    assert post["say"]("A1", {"text": "x" * 41})[0] == 400        # longer than max_bytes
    assert post["say"]("A1", {"text": "press high"})[0] == 200
    assert post["say"]("A1", {"text": "again"})[0] == 429          # min_interval_s in game time
    time.sleep(0.05)
    get = svc.routes(False)
    a2 = get["status"]("A2", {})[1]
    b1 = get["status"]("B1", {})[1]
    assert [m["text"] for m in a2["team_messages"]] == ["press high"] and a2["team_messages"][0]["from"] == "A1"
    assert a2["team_messages"][0]["seq"] == 1 and a2["team_seq"] == 1
    assert b1["team_messages"] == [] and b1["team_seq"] == 0       # never shown to the other side
    # core 0.2.20: reading never consumes: a second client of the same seat (the agent's own status, a monitor)
    # sees the same message; a read mark gives only newer ones; the sender never gets its own message back
    again = get["status"]("A2", {})[1]
    assert [m["text"] for m in again["team_messages"]] == ["press high"]
    assert get["status"]("A2", {"team_since": 1})[1]["team_messages"] == []
    assert get["status"]("A1", {})[1]["team_messages"] == [] and get["status"]("A1", {})[1]["team_seq"] == 1
    assert post["team"]("A2", {"since": 0})[1]["messages"][0]["text"] == "press high"
    assert post["team"]("B1", {})[1]["messages"] == []
    for bad in (-1, 1.5, "x", [1], True):
        try:
            get["status"]("A2", {"team_since": bad})
            raise AssertionError(f"read mark {bad!r} accepted")
        except Refused:
            pass
    th = [threading.Thread(target=play, args=(svc, post, s), daemon=True) for s in sides]
    for t in th:
        t.start()
    fin = finish(svc)
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    assert fin["match_winner"] == "home" and fin["sides"]["A2"] == "home" and fin["team_messages"] == 1
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    assert any(r["ev"] == "team" and r["text"] == "press high" for r in rows)
    cmds = [r for r in rows if r["ev"] == "cmd"]
    assert cmds and cmds[0]["cmd"]["entity"] == "e1"


def test_n_sides_ranking_and_retirement():
    svc, post = service(["A", "B", "C"], fmt="multi")

    def mover(v):
        return lambda seat, p: p["act"](seat, {"type": "move", "v": v, "entity": "e0"})
    fin = run_all(svc, post, ["A", "B", "C"], A={"act": mover(0.2)}, B={"act": mover(0.1)},
                  C={"act": mover(0.9), "review": False})      # C never reviews: it retires, A and B play on
    assert fin["retired"] == ["C"] and fin["reason"] == "match_over", fin
    assert fin["ranking"] == ["A", "B", "C"] and fin["match_winner"] == "A"
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    assert any(r["ev"] == "retire" and r["side"] == "C" for r in rows)
    r = {"cfg": fin["cfg"], **fin}
    out = grade(r, json.loads((svc.data / "replay_check.json").read_text()), {}, lambda d: {})
    assert out["A_place"] == 1 and out["C_place"] == 3 and out["A_won"] == 1 and out["success"] == 1


def test_delayed_effect_is_logged_at_its_step():
    os.environ["FIXTURE_DELAY"] = "3"
    try:
        svc, post = service(["A", "B"], fmt="duel")
        got = []

        def act(seat, p):
            if seat == "A" and not got:
                got.append(p["act"](seat, {"type": "move", "v": 0.3, "entity": "e0"}))
        fin = run_all(svc, post, ["A", "B"], A={"act": act})
    finally:
        os.environ.pop("FIXTURE_DELAY")
    code, out = got[0]
    assert code == 200, out
    eff = out["took_effect"]
    assert eff["effect_step"] == eff["step"] + 3
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    cmd = next(r for r in rows if r["ev"] == "cmd" and r["seat"] == "A")
    assert cmd["k"] == eff["effect_step"]
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    rc = fin["reaction"]                                  # core 0.2.23: the layer's delay is part of the report
    assert rc["effect_delay_steps"] == 3 and rc["by_seat"]["A"]["acts"] == 1 and rc["replayed"] is True, rc
    assert rc["by_seat"]["A"]["delay_steps"]["max"] == cmd["k"] - cmd["seen"] >= 3, (rc, cmd)


def fixture_with_reaction_delay(D):
    """A copy of the realtime fixture whose sport.toml declares [timing] reaction_delay_steps = D (core 0.2.18)."""
    import shutil
    d = Path(tempfile.mkdtemp(prefix="core-test-react-")) / "fixture"
    shutil.copytree(Path(PLUGIN).parent, d, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "sport.toml").write_text((d / "sport.toml").read_text() + f"\n[timing]\nreaction_delay_steps = {D}\n")
    return str(d / "plugin.py")


def test_reaction_delay_rule():
    """core 0.2.18: with a declared reaction delay D an act takes effect at max(the next boundary, s + D), s = the
    step of the latest world state the seat was sent (an observation or any reply's `now`); the effect step is
    logged and replayed (deterministic); the same D for every seat; /spec shows it."""
    from core import spec as spec_mod
    assert spec_mod.reaction_delay({}) == 0 and spec_mod.reaction_delay({"timing": {"reaction_delay_steps": 3}}) == 3
    for bad in (-1, 2.0, True, "2"):
        try:
            spec_mod.reaction_delay({"timing": {"reaction_delay_steps": bad}})
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass
    D, plugin = 4, fixture_with_reaction_delay(4)
    for s in ("A", "B"):
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1, slowdown=5.0)   # 50 ms per step
    svc = RealtimeService(load_plugin(plugin), plugin, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    post = svc.routes(True)
    assert svc.spec("A")[1]["timing"]["reaction_delay_steps"] == D
    got = []

    def act(seat, p):
        if len(got) >= 6 or svc.phase != "running":
            return
        code, ob = p["observe"](seat, {})
        if code != 200 or ob["now"]["phase"] != "running":
            return
        code, out = p["act"](seat, {"type": "move", "v": 0.1, "entity": "e0"})
        if code != 200:
            return
        got.append(("observe", ob["now"]["step"], out["took_effect"]))
        code, out2 = p["act"](seat, {"type": "move", "v": 0.2, "entity": "e0"})    # answers the act reply's `now`
        if code == 200:
            got.append(("act", out["now"]["step"], out2["took_effect"]))
    fin = run_all(svc, post, ["A", "B"], A={"act": act})
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    assert len(got) >= 4, got
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    ks = [r["k"] for r in rows if r["ev"] == "cmd" and r["seat"] == "A"]
    for kind, seen, eff in got:
        assert eff["seen_step"] == seen and eff["reaction_delay_steps"] == D, (kind, seen, eff)
        assert eff["step"] >= seen + D, (kind, seen, eff)      # never earlier than s + D
        assert eff["step"] in ks, (eff, ks)                    # the logged (replayed) step is the effect step
    exact = sum(eff["step"] == seen + D for _, seen, eff in got)
    assert exact >= len(got) - 1, got                          # a fast program gets exactly D (50 ms per step)


def test_reaction_delay_undeclared_unchanged():
    """No declaration: D = 0 in /spec, an act takes effect at the next control-step boundary, its reply as before."""
    svc, post = service(["A", "B"], fmt="duel")
    assert svc.react == 0 and svc.spec("A")[1]["timing"]["reaction_delay_steps"] == 0
    got = []

    def act(seat, p):
        if not got and svc.phase == "running":
            code, ob = p["observe"](seat, {})
            code, out = p["act"](seat, {"type": "move", "v": 0.3, "entity": "e0"})
            if code == 200:
                got.append((ob["now"]["step"], out["took_effect"]))
    fin = run_all(svc, post, ["A", "B"], A={"act": act})
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    seen, eff = got[0]
    assert "seen_step" not in eff and "reaction_delay_steps" not in eff and eff["step"] < seen + 4, got


def test_reaction_delay_local_play_deterministic():
    """core/local.py plays by the same rule: an act answers the observation at k and takes effect at k + D; two runs
    give the same state digest, the episode replays to it in a fresh replay, and without the declaration the
    commands are where they were before (at the observation step)."""
    from core import local
    from core.episode import read_rows, replay

    class Mover:
        def __init__(self):
            self.n = 0

        def act(self, view):
            self.n += 1
            return {"type": "move", "entity": "e0", "v": round(0.1 * (self.n % 7) - 0.3, 3)}

    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1, slowdown=1.0)
    out = {}
    for name, plugin in (("D3", fixture_with_reaction_delay(3)), ("D3 again", fixture_with_reaction_delay(3)),
                         ("none", PLUGIN)):
        d = Path(tempfile.mkdtemp(prefix="core-test-"))
        r = local.play(SPORT, cfg, {"A": Mover(), "B": Mover()}, data=d, render=False, plugin=plugin)
        rows = read_rows(d / "episode.jsonl")
        rep = replay(SPORT, rows)
        assert rep["state_sha"] == r["digest"] and rep["scores"] == r["scores"], (name, rep, r)
        out[name] = (r["digest"], [x["k"] for x in rows if x["ev"] == "cmd"])
    assert out["D3"] == out["D3 again"]
    assert out["D3"][1] and all(k % 5 == 3 for k in out["D3"][1]), out["D3"][1][:10]
    assert out["none"][1] and all(k % 5 == 0 for k in out["none"][1]) and out["none"][0] != out["D3"][0]


def reaction_match(plugin, slow_s=0.35, slowdown=5.0, n=8):
    """A duel on the fixture at 50 ms per step: seat A is a fast player (acts right after each observation), seat B a
    slow one (thinks slow_s wall seconds between its observation and its act). Returns final.json, replay_check.json,
    the episode rows and what each act's reply said."""
    for s in ("A", "B"):
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1, slowdown=slowdown)
    svc = RealtimeService(load_plugin(plugin), plugin, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    post = svc.routes(True)
    got = {"A": [], "B": []}

    def player(think):
        def act(seat, p):
            if len(got[seat]) >= n or svc.phase != "running":
                return
            code, ob = p["observe"](seat, {})
            if code != 200 or ob["now"]["phase"] != "running":
                return
            time.sleep(think)
            code, out = p["act"](seat, {"type": "move", "v": 0.1, "entity": "e0"})
            if code == 200:
                got[seat].append((ob["now"]["step"], out["took_effect"]))
        return act
    os.environ["READY_TIMEOUT_S"] = "5"                  # a loaded host: the slow seat still reviews in time
    try:
        fin = run_all(svc, post, ["A", "B"], A={"act": player(0.0)}, B={"act": player(slow_s)})
    finally:
        os.environ["READY_TIMEOUT_S"] = "1.5"
    assert fin["valid_trial"], {k: fin.get(k) for k in ("reason", "phase", "finalized", "deterministic", "errors")}
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    return fin, json.loads((svc.data / "replay_check.json").read_text()), rows, got


def check_reaction_report(fin, rep, rows, D):
    """final.json `reaction` = the rows' numbers = the replay's, and grading never sees it."""
    from core.episode import reaction_report
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    r = fin["reaction"]
    assert r["policy"] == "report_only" and r["reaction_delay_steps"] == D and r["replayed"] is True, r
    assert rep["reaction"]["by_seat"] == r["by_seat"], (rep["reaction"], r)
    head = next(x for x in rows if x["ev"] == "header")
    assert head["timing"] == {"reaction_delay_steps": D, "effect_delay_steps": 0}, head
    assert reaction_report(rows, ("A", "B"), D)["by_seat"] == r["by_seat"]
    for seat in ("A", "B"):
        lags = sorted(x["k"] - x["seen"] for x in rows if x["ev"] == "cmd" and x["seat"] == seat
                      and x.get("seen") is not None)
        b = r["by_seat"][seat]
        assert b["acts"] == len(lags) > 0 and b["within_d"] == sum(d <= D for d in lags), (seat, b, lags)
        assert b["share"] == round(b["within_d"] / b["acts"], 6) and b["delay_steps"]["max"] == lags[-1], b
    out = grade({"cfg": fin["cfg"], **fin}, rep, {}, lambda d: {})
    assert not any("reaction" in k or "within" in k for k in out), sorted(out)
    return r["by_seat"]


def test_reaction_report_declared_delay():
    """core 0.2.23 (report only): with D declared, a fast player's acts all take effect within D (exactly D), a slow
    player's (0.35 s of thinking = 7 steps at 50 ms) none; final.json gives the counts, the share and the delay's
    median / p90 / max per seat, the fresh-process replay recomputes the same numbers, grading ignores them."""
    D = 2
    fin, rep, rows, got = reaction_match(fixture_with_reaction_delay(D))
    by = check_reaction_report(fin, rep, rows, D)
    a, b = by["A"], by["B"]
    assert a["within_d"] >= a["acts"] - 1 and a["delay_steps"]["median"] == D, a       # D exactly when fast
    assert b["within_d"] == 0 and b["share"] == 0 and b["delay_steps"]["median"] >= D + 3, b
    for seen, eff in got["B"]:                                       # the replies agree with the report
        assert eff["seen_step"] == seen and eff["step"] - seen > D, (seen, eff)


def test_reaction_report_without_declared_delay():
    """D = 0 (not declared): within D means the next control-step boundary after the seen state; the slow player is
    never within it; the act replies are unchanged (no seen_step), the report is in final.json and the replay."""
    fin, rep, rows, got = reaction_match(PLUGIN)
    by = check_reaction_report(fin, rep, rows, 0)
    assert by["B"]["within_d"] == 0 and by["B"]["delay_steps"]["median"] >= 4, by["B"]
    assert by["A"]["delay_steps"]["median"] <= 1, by["A"]
    assert all("seen_step" not in eff for _, eff in got["A"] + got["B"])


def test_reaction_report_rule_and_old_episodes():
    """reaction_report on rows: the layer's fixed effect delay counts as part of D; ticks (no `seen`) are not acts; an
    act whose seat had been sent no world state is `unseen`; an episode before 0.2.23 gives empty seats."""
    from core.episode import reaction_report
    rows = [{"ev": "cmd", "k": 10, "seat": "A", "cmd": {}, "seen": 7}, {"ev": "cmd", "k": 11, "seat": "A", "cmd": {}},
            {"ev": "cmd", "k": 20, "seat": "A", "cmd": {}, "seen": 14}, {"ev": "cmd", "k": 21, "seat": "B", "cmd": {},
                                                                          "seen": None}]
    r = reaction_report(rows, ("A", "B"), 2, 1)["by_seat"]
    assert r["A"] == {"acts": 2, "within_d": 1, "share": 0.5, "delay_steps": {"median": 4.5, "p90": 6, "max": 6},
                      "unseen": 0}, r
    assert r["B"] == {"acts": 0, "within_d": 0, "share": None, "delay_steps": None, "unseen": 1}, r
    old = reaction_report([{"ev": "cmd", "k": 3, "seat": "A", "cmd": {}}], ("A",), 0)["by_seat"]
    assert old == {"A": {"acts": 0, "within_d": 0, "share": None, "delay_steps": None, "unseen": 0}}, old


def test_local_play_team_channel_of_builtin_players():
    """core 0.2.21: a built-in player's optional message(view) goes on the team channel in local play as POST /say
    would (the channel's limits; a refused message is dropped), reaches its teammates' views (team_messages) and never
    the other side, is a `team` row of the episode, and changes nothing the replay sees."""
    from core import local
    from core.episode import read_rows, replay

    class Talker:
        def __init__(self, seat):
            self.seat, self.heard, self.n = seat, [], 0

        def act(self, view):
            self.heard += [(m["from"], m["text"]) for m in view["state"].get("team_messages") or []]
            self.n += 1
            return {"type": "move", "entity": "e0", "v": 0.1}

        def message(self, view):
            return f"{self.seat} {self.n}" if self.seat.endswith("1") else None

    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    cfg = MatchConfig(sport="fixture", format="team", seats=tuple(sides), seed=1, slowdown=1.0, sides=sides)
    d = Path(tempfile.mkdtemp(prefix="core-test-"))
    players = {s: Talker(s) for s in sides}
    r = local.play(SPORT, cfg, players, data=d, render=False, plugin=PLUGIN)
    rows = read_rows(d / "episode.jsonl")
    team = [x for x in rows if x["ev"] == "team"]
    assert team and {x["seat"] for x in team} == {"A1", "B1"}, team[:3]
    ks = [x["k"] for x in team if x["seat"] == "A1"]
    assert all(b - a >= 0.2 / SPORT.build(cfg).dt - 1e-9 for a, b in zip(ks, ks[1:])), ks[:5]   # min_interval_s
    assert players["A2"].heard and all(f == "A1" for f, _ in players["A2"].heard)
    assert players["B2"].heard and all(f == "B1" for f, _ in players["B2"].heard)
    assert not players["A1"].heard and not players["B1"].heard                    # never their own, never the others'
    rep = replay(SPORT, rows)
    assert rep["state_sha"] == r["digest"] and rep["scores"] == r["scores"]


def test_preview_format_is_never_official():
    """core 0.2.21: a format declared preview ([formats.<f>] preview = true, in the contract's formats) is never an
    official configuration, whatever its seed, level and first player; the same match in a non-preview format is."""
    from core.grading import official
    d = {"format": "tm", "seed": 202, "first": "A", "slowdown": 10.0, "play": "program",
         "cfg": {"seats": ["A1", "A2"], "level": 2}, "sides": {"A1": "A", "A2": "A"}}
    contract = {"official": {"seeds": [202], "levels": [2, 3], "first_any": True},
                "formats": {"tm": {"seats": ["A1", "A2"], "opponent": True, "preview": True}}}
    assert not official(d, contract)
    contract["formats"]["tm"].pop("preview")
    assert official(d, contract)


def test_observation_query_and_runtime_whitelist():
    svc, post = service(["A", "B"], fmt="duel")
    th = [threading.Thread(target=post["start"], args=(s, {}), daemon=True) for s in "AB"]
    for t in th:
        t.start()
    while svc.phase != "running":
        time.sleep(0.01)
    code, out = post["observe"]("A", {"query": {"view": "near"}})
    assert code == 200 and out["now"]["view"] == "near"
    for bad in ({"query": {"view": "sideways"}}, {"query": "near"}):
        try:
            post["observe"]("A", bad)
            raise AssertionError(f"query {bad} accepted")
        except Refused:
            pass
    code, out = post["observe"]("A", {"query": {"view": "far"}})     # the sport leaks a field: dropped + error
    assert code == 200 and "secret_state" not in out["now"]
    assert any(e["where"] == "observation" for e in svc.errors)
    svc.end("collected")
    fin = finish(svc)
    assert not fin["valid_trial"]


class start_window:
    """START_TIMEOUT_S for one test."""
    def __init__(self, s):
        self.s = s

    def __enter__(self):
        self.old, os.environ["START_TIMEOUT_S"] = os.environ.get("START_TIMEOUT_S"), str(self.s)

    def __exit__(self, *a):
        os.environ["START_TIMEOUT_S"] = self.old


def graded(svc, fin):
    return grade(fin, json.loads((svc.data / "replay_check.json").read_text()), {}, lambda d: {})


def check_no_show(svc, fin, absent="B", winner="A"):
    """The side that never started lost by forfeit, the trial is valid and replays; the grader agrees."""
    assert fin["reason"] == "no_show" and fin["forfeiting"] == absent, fin
    assert fin["match_winner"] == winner and fin["winner"] == winner and fin["decided_by"] == "forfeit:no_show"
    assert fin["valid_trial"] and fin["deterministic"] and not fin["technical_failure"], fin["errors"]
    assert fin["joined"][absent] is False and fin["steps"] == 0
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    assert any(r["ev"] == "forfeit" and r["seat"] == absent and r["why"] == "no_show" for r in rows)
    out = graded(svc, fin)
    assert out["valid_trial"] == 1 and out["success"] == 1 and out["no_show"] == 1, out
    assert out[f"{winner}_won"] == 1 and out[f"{absent}_won"] == 0 and out[f"{absent}_no_show"] == 1
    assert out[f"{winner}_no_show"] == 0


def test_no_show_realtime_duel_present_side_wins():
    with start_window(1):
        svc, post = service(["A", "B"], fmt="duel")
        threading.Thread(target=post["start"], args=("A", {}), daemon=True).start()   # B never starts
        fin = finish(svc)
        assert svc.spec("A")[1]["start"]["window_s"] == 1.0
    check_no_show(svc, fin)


def test_no_show_turn_duel_present_side_wins():
    with start_window(1):
        svc, post = turn_service(["A", "B"])
        assert post["start"]("B", {})[0] == 200                                    # A never starts
        fin = finish(svc)
    check_no_show(svc, fin, absent="A", winner="B")
    assert "start" in svc.spec("B")[1]


def test_no_show_turn_duel_late_start_refused():
    with start_window(1):
        svc, post = turn_service(["A", "B"])
        post["start"]("A", {})
        fin = finish(svc)
        assert post["start"]("B", {})[0] == 409                                    # the window has closed
    check_no_show(svc, fin)


def test_no_show_nobody_started_is_invalid():
    for make, reason in ((lambda: service(["A", "B"], fmt="duel"), "collected"),
                         (lambda: turn_service(["A", "B"]), "incomplete")):
        svc, post = make()
        time.sleep(0.6)
        svc.collect()                                                              # the session ends, nobody started
        fin = finish(svc)
        assert fin["reason"] == reason and fin["winner"] is None and fin["match_winner"] is None, fin
        assert not fin["valid_trial"] and fin["forfeiting"] is None
        out = graded(svc, fin)
        assert out["valid_trial"] == 0 and out["success"] == 0 and out["no_show"] == 0


def test_no_show_every_side_absent_after_the_window_is_invalid():
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    with start_window(1):                       # one home seat started: no side complete when the window closes
        svc, post = service(list(sides), sides)
        threading.Thread(target=post["start"], args=("A1", {}), daemon=True).start()
        fin = finish(svc)
    assert fin["reason"] == "incomplete" and fin["winner"] is None and not fin["valid_trial"], fin
    with start_window(1):
        svc, post = turn_service(list(sides), sides, fmt="team")
        post["start"]("B2", {})
        fin = finish(svc)
    assert fin["reason"] == "incomplete" and fin["winner"] is None and not fin["valid_trial"], fin


def test_no_show_team_side_with_a_missing_seat_loses():
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    with start_window(1):
        svc, post = turn_service(list(sides), sides, fmt="team")
        for s in ("A1", "B1", "B2"):                                               # A2 never starts
            post["start"](s, {})
        fin = finish(svc)
    assert fin["reason"] == "no_show" and fin["forfeiting"] == "A2" and fin["match_winner"] == "away", fin
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]


def check_single_no_show(svc, fin):
    """A single side that never started: a valid loss by forfeit (no_show), replayed; success 0."""
    assert fin["reason"] == "no_show" and fin["forfeiting"] == "A" and fin["winner"] is None, fin
    assert fin["valid_trial"] and fin["deterministic"] and fin["decided_by"] == "forfeit:no_show", fin["errors"]
    assert fin["joined"]["A"] is False and fin["steps"] == 0, fin
    out = graded(svc, fin)
    assert out["valid_trial"] == 1 and out["success"] == 0 and out["no_show"] == 1 and out["A_no_show"] == 1, out
    assert out["A_won"] == 0 and out["abandoned"] == 0, out


def test_no_show_single_player_valid_loss():
    """One side: the window opens at the service start; not started when it closes = a valid loss (no_show, success
    0). A session that ends before the window closes is the same valid loss, decided at the collect (core 0.2.7)."""
    for make in (lambda: service(["A"], fmt="single"), lambda: turn_service(["A"], fmt="single")):
        with start_window(1):
            svc, post = make()
            fin = finish(svc)
        check_single_no_show(svc, fin)
        assert fin["elapsed_s"] >= 0.9, fin["elapsed_s"]


# ---------------------------------------------- a session that ends before its side started (core 0.2.7, core rule 5)
def collect_rows(svc):
    return [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()
            if json.loads(x)["ev"] == "collect_before_start"]


def test_prestart_single_collected_before_the_window_is_no_show():
    """The single side's session ends inside the start window (5 s here) without a start: no_show at once, a valid
    loss (cores 0.2.2-0.2.6: an unfinished, invalid match, "collected" / "incomplete")."""
    for make in (lambda: service(["A"], fmt="single"), lambda: turn_service(["A"], fmt="single")):
        svc, post = make()
        time.sleep(0.3)
        t = time.time()
        svc.collect()
        fin = finish(svc)
        check_single_no_show(svc, fin)
        assert time.time() - t < 4, "decided at the collect, not when the window closes"
        assert collect_rows(svc) and collect_rows(svc)[0]["absent"] == ["A"]


def test_prestart_duel_collected_before_the_window_absent_side_loses():
    """Two sides, one started, the other never; the sessions end inside the window: the absent side loses (no_show,
    valid), the present side wins, as when the window closes (core rule 5)."""
    svc, post = service(["A", "B"], fmt="duel")
    threading.Thread(target=post["start"], args=("A", {}), daemon=True).start()   # B never starts
    t = time.time()
    while not svc.seats["A"].joined and time.time() - t < 5:
        time.sleep(0.01)
    svc.collect()
    fin = finish(svc)
    check_no_show(svc, fin)
    svc, post = turn_service(["A", "B"])
    assert post["start"]("B", {})[0] == 200                                        # A never starts
    svc.collect()
    fin = finish(svc)
    check_no_show(svc, fin, absent="A", winner="B")
    assert collect_rows(svc)[0]["absent"] == ["A"]


def test_prestart_no_show_check_accepts_a_forfeit_hook_that_ends_the_world():
    """core 0.2.21: the generic check prestart_no_show (core/testkit.py) asks for the forfeit's decision at step 0,
    not for an unfinished world. A sport whose forfeit hook ends its world (the game over, the winner set) is
    decided the same way (the forfeit comes first in core.outcome.decide); cores 0.2.7-0.2.11 failed it."""
    from core import testkit
    cfg = MatchConfig(sport="fixture_turn", format="duel", seats=("A", "B"), seed=1, first="A", action_level="low")
    game = type(SPORT_TURN.build(cfg))
    decl = {"formats": {"single": {"seats": ["A"]}, "duel": {"seats": ["A", "B"], "first": ["A", "B"]}},
            "modes": {"action_levels": ["low"]}}
    plain = testkit.t_prestart_no_show(SPORT_TURN, PLUGIN_TURN, decl)
    phase = game.phase

    def forfeit(self, seat, why):
        self.ended = why
        return True
    game.forfeit = forfeit
    game.phase = lambda self: Phase(FINISHED, reason=self.ended) if getattr(self, "ended", None) else phase(self)
    try:
        ended = testkit.t_prestart_no_show(SPORT_TURN, PLUGIN_TURN, decl)
    finally:
        del game.forfeit
        game.phase = phase
    for rows, finished in ((plain, False), (ended, True)):
        assert [r["name"] for r in rows] == ["prestart_no_show:single", "prestart_no_show:duel"], rows
        assert all(r["ok"] for r in rows), rows
        assert all(json.loads(r["detail"])["finished"] is finished for r in rows), rows


def test_prestart_team_side_with_a_missing_seat_loses_at_the_collect():
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    svc, post = turn_service(list(sides), sides, fmt="team")
    for s in ("A1", "B1", "B2"):                                                   # A2 never starts
        post["start"](s, {})
    svc.collect()
    fin = finish(svc)
    assert fin["reason"] == "no_show" and fin["forfeiting"] == "A2" and fin["match_winner"] == "away", fin
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    out = graded(svc, fin)
    assert out["A2_no_show"] == 1 and out["A1_no_show"] == 0 and out["B1_won"] == 1 and out["A1_won"] == 0, out


def test_prestart_no_side_present_at_the_collect_does_not_count():
    """No side complete (one home seat started): the collect leaves the match unfinished, as before core 0.2.7."""
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    for make, reason in ((lambda: service(list(sides), sides), "collected"),
                         (lambda: turn_service(list(sides), sides, fmt="team"), "incomplete")):
        svc, post = make()
        threading.Thread(target=post["start"], args=("A1", {}), daemon=True).start()
        t = time.time()
        while not svc.seats["A1"].joined and time.time() - t < 5:
            time.sleep(0.01)
        svc.collect()
        fin = finish(svc)
        assert fin["reason"] == reason and fin["forfeiting"] is None and fin["winner"] is None, fin
        assert not fin["valid_trial"] and graded(svc, fin)["no_show"] == 0 and not collect_rows(svc), fin


def test_prestart_n_sides_collect():
    """Three sides: one absent at the collect retires (the sport allows it) and the match, never begun, ends
    unfinished; two absent: the first retires, the second forfeits and the present side wins (as at the window)."""
    svc, post = turn_service(["A", "B", "C"], fmt="multi")
    for s in ("B", "C"):
        post["start"](s, {})
    svc.collect()
    fin = finish(svc)
    assert fin["retired"] == ["A"] and fin["reason"] == "incomplete" and not fin["valid_trial"], fin
    svc, post = turn_service(["A", "B", "C"], fmt="multi")
    post["start"]("C", {})
    svc.collect()
    fin = finish(svc)
    assert fin["reason"] == "no_show" and fin["match_winner"] == "C" and fin["retired"] == ["A"], fin
    assert fin["ranking"] == ["C", "B", "A"] and fin["valid_trial"], fin


def test_no_show_n_sides_absent_side_retires_others_play():
    with start_window(1):
        svc, post = service(["A", "B", "C"], fmt="multi")

        def mover(v):
            return lambda seat, p: p["act"](seat, {"type": "move", "v": v, "entity": "e0"})
        fin = run_all(svc, post, ["A", "B"], A={"act": mover(0.2)}, B={"act": mover(0.1)})   # C never starts
    assert fin["retired"] == ["C"] and fin["reason"] == "match_over", fin
    assert fin["ranking"] == ["A", "B", "C"] and fin["valid_trial"] and fin["deterministic"], \
        {k: fin[k] for k in ("ranking", "valid_trial", "deterministic", "finalized", "scores", "replay_scores", "steps")}
    with start_window(1):
        svc, post = turn_service(["A", "B", "C"], fmt="multi")
        th = [threading.Thread(target=play_turn, args=(svc, post, s, v), daemon=True) for s, v in (("B", .9), ("C", .1))]
        for t in th:
            t.start()
        fin = finish(svc)
    assert fin["retired"] == ["A"] and fin["reason"] == "match_over", fin
    assert fin["ranking"] == ["B", "C", "A"] and fin["match_winner"] == "B", fin
    assert fin["valid_trial"] and fin["deterministic"], {k: fin[k] for k in ("finalized", "scores", "replay_scores")}
    with start_window(1):                       # two of three absent: the first retires, the second forfeits
        svc, post = turn_service(["A", "B", "C"], fmt="multi")
        post["start"]("C", {})
        fin = finish(svc)
    assert fin["reason"] == "no_show" and fin["match_winner"] == "C" and fin["retired"] == ["A"], fin
    assert fin["ranking"] == ["C", "B", "A"] and fin["valid_trial"], fin


def test_turn_duel_plays_to_the_end():
    svc, post = turn_service(["A", "B"])
    th = [threading.Thread(target=play_turn, args=(svc, post, s, v), daemon=True) for s, v in (("A", .3), ("B", .6))]
    for t in th:
        t.start()
    fin = finish(svc)
    assert fin["reason"] == "match_over" and fin["match_winner"] == "B" and fin["valid_trial"], fin
    assert fin["deterministic"], fin["errors"]


class Stub:
    def __init__(self, sc, finished=True, rules=None, rank=None):
        self.sc, self.fin, self.rules, self.rank = sc, finished, rules, rank

    def scores(self):
        return self.sc

    def phase(self):
        return Phase(FINISHED if self.fin else PLAYING)

    def tiebreaks(self):
        return self.rules if self.rules is not None else [("last", lambda m: "B")]

    def ranking(self):
        return self.rank


def test_outcome_rules():
    assert decide(Stub({"A": 30}, rules=[]), sides=["A"]).solo                     # solo: no winner
    assert decide(Stub({"A": 30}, rules=[]), sides=["A"]).winner is None
    assert decide(Stub({"A": 1, "B": 1}), sides=["A", "B"]).winner == "B"         # last tiebreak decides
    assert decide(Stub({"A": 1, "B": 1}), "A", "clock", ["A", "B"]).winner == "B"
    o = decide(Stub({"A": 1, "B": 3, "C": 2}, rank=["B", "C", "A"]), sides=["A", "B", "C"])
    assert o.winner == "B" and o.ranking == ["B", "C", "A"]
    try:
        decide(Stub({"A": 1, "B": 1}, rules=[("x", lambda m: None)]), sides=["A", "B"])
        raise AssertionError("a draw was accepted")
    except RuntimeError:
        pass
    assert decide(Stub({"A": 1, "B": 1}, finished=False), sides=["A", "B"]).winner is None


def test_grading_success_rules():
    assert line_ok(30, {"score_at_least": 30}) and not line_ok(29, {"score_at_least": 30})
    assert line_ok(3, {"score_at_most": 4})
    base = {"cfg": {"seats": ["A"]}, "sides": {"A": "A"}, "deterministic": True, "state_sha": "s", "scores": {"A": 31},
            "match_winner": None, "commands_sha": "c", "source_sha": "x", "steps": 5, "reason": "match_over",
            "valid_trial": True, "finalized": True, "errors": [], "meter_error": {}, "proxy_error": {}, "solo": True,
            "transient_api_errors": {}, "unrecovered_api_errors": {}, "player_modes": {"A": "oracle"},
            "format": "single", "play": "program"}
    rc = {"state_sha": "s", "scores": {"A": 31}, "winner": None, "commands_sha": "c", "source_sha": "x", "k": 5}
    contract = {"formats": {"single": {"success": {"score_at_least": 30}}}}
    assert grade(base, rc, contract, lambda d: {})["success"] == 1
    low = dict(base, scores={"A": 20})
    assert grade(low, dict(rc, scores={"A": 20}), contract, lambda d: {})["success"] == 0
    opp = dict(base, solo=False, match_winner="opponent")                            # single vs a scripted opponent
    assert grade(opp, dict(rc, winner="opponent"), contract, lambda d: {})["success"] == 0
    opp = dict(base, solo=False, match_winner="A")
    assert grade(opp, dict(rc, winner="A"), contract, lambda d: {})["success"] == 1


def test_launch_seat_env_second_account_and_route():
    from core.launch import PROXY, seat_env
    env = {"KEY_ACCOUNT": "t1", "KEY_ACCOUNT_2": "t2", "THINK_OPENAI_ROUTE": "openrouter",
           "RO_SEAT_SELECT_A": "KEY_ACCOUNT=KEY_ACCOUNT_2", "RO_SEAT_SELECT_B": "",
           "RO_SEAT_ENV_THINK_OPENAI_ROUTE_B": "azure", "RO_SEAT_ENV_THINK_OPENAI_ROUTE_A": ""}
    a, b = seat_env("A", env, ["A", "B"]), seat_env("B", env, ["A", "B"])
    assert a["KEY_ACCOUNT"] == "t2" and b["KEY_ACCOUNT"] == "t1"
    assert a["THINK_OPENAI_ROUTE"] == "openrouter" and b["THINK_OPENAI_ROUTE"] == "azure"
    assert a["THINK_USAGE_FILE"].endswith("think_usage_A.json") and a["THINK_CLIENT_HOST"] == "seat_a"
    assert PROXY.parts[-2:] == ("metering", "think_proxy.py")     # where tools/sportlib.py puts the proxy


def test_launch_seat_env_holds_no_other_seats_variables():
    """After the mapping a proxy has no RO_SEAT_* and no other seat's per-seat variable; a seat on route chatgpt keeps
    only the credentials given to it alone (no task-wide key)."""
    from core.launch import seat_env
    env = {"SUB_TOKEN": "", "TASK_KEY": "task-key", "THINK_OPENAI_ROUTE": "azure", "SUB_TOKEN_A": "raw-a",
           "PLAYER_MODE_A": "model", "PLAYER_MODE_B": "model", "RO_SEAT_SELECT_A": "", "RO_SEAT_SELECT_B": ""}
    for s, tok, route in (("A", "secret-a", "chatgpt"), ("B", "secret-b", "chatgpt"), ("C", "", "azure")):
        env.update({f"RO_SEAT_ENV_SUB_TOKEN_{s}": tok, f"RO_SEAT_ENV_TASK_KEY_{s}": "",
                    f"RO_SEAT_ENV_THINK_OPENAI_ROUTE_{s}": route, f"RO_SEAT_ENV_THINK_MODEL_{s}": f"model-{s}"})
    a, b, c = (seat_env(s, env, ["A", "B", "C"]) for s in "ABC")
    for e, own, others in ((a, "secret-a", ("secret-b",)), (b, "secret-b", ("secret-a", "raw-a")),
                           (c, None, ("secret-a", "secret-b", "raw-a"))):
        assert not [k for k in e if k.startswith(("RO_SEAT_ENV_", "RO_SEAT_SELECT_"))], sorted(e)
        assert not [k for k, v in e.items() for x in others if x in v], sorted(e.items())
        assert e.get("SUB_TOKEN") == (own if own else "")
    assert "TASK_KEY" not in a and "TASK_KEY" not in b and c["TASK_KEY"] == "task-key"   # route chatgpt: no task key
    assert (a["THINK_MODEL"], b["THINK_MODEL"], c["THINK_MODEL"]) == ("model-A", "model-B", "model-C")
    assert "PLAYER_MODE_B" not in a and "PLAYER_MODE_A" not in b and "SUB_TOKEN_A" in a


# ------------------------------------------------------------------ the spectator scene (core 0.2.4, renderer rule 6)
_ARM = ('<mujoco><worldbody><light pos="0 0 3" dir="0 0 -1"/><body name="arm" pos="0 0 .2"><joint axis="0 0 1"/>'
        '<geom name="arm_c" type="box" size=".05 .05 .2" rgba=".8 .2 .2 1"/></body></worldbody></mujoco>')
_MODEL = ('<mujoco><asset><mesh name="m" file="tetra.obj"/></asset><worldbody>'
          '<body name="arm"><geom type="mesh" mesh="m" rgba=".1 .3 .9 1" contype="0" conaffinity="0" group="2"/>'
          '</body></worldbody></mujoco>')


def test_spectator_scene_is_the_presentation_scene_and_players_keep_the_match_scene():
    from core.observe import CameraWorker
    from core.spectator import spectator_scene
    from renderers.base import Scene

    class Sport:
        def scene(self, cfg):
            return Scene(xml=_ARM)

    cfg = MatchConfig(sport="x", format="single", seats=("A",), seed=1)
    with tempfile.TemporaryDirectory() as tmp:
        plugin = Path(tmp) / "plugin.py"
        sc, what = spectator_scene(Sport(), str(plugin), cfg)          # no presentation/: the match scene
        assert what == "match" and not sc.is_presentation
        d = Path(tmp) / "presentation"
        d.mkdir()
        (d / "arm.xml").write_text(_MODEL)
        (d / "tetra.obj").write_text("v -.1 -.1 0\nv .1 -.1 0\nv 0 .1 0\nv 0 0 .4\nf 1 3 2\nf 1 2 4\nf 2 3 4\nf 3 1 4\n")
        (d / "presentation.toml").write_text('[presentation]\nversion = 1\n[[presentation.robot]]\n'
                                             'model = "./arm.xml"\nbodies = "arm"\nbody = "arm"\n')
        sc, what = spectator_scene(Sport(), str(plugin), cfg)
        assert what == "presentation" and sc.is_presentation and "_vis:arm:0" in sc.xml
        os.environ["RO_VIDEO_SCENE"] = "match"
        try:
            sc2, what2 = spectator_scene(Sport(), str(plugin), cfg)
        finally:
            del os.environ["RO_VIDEO_SCENE"]
        assert what2 == "match" and not sc2.is_presentation
        (d / "presentation.toml").write_text('[presentation]\nversion = 1\n[[presentation.robot]]\n'
                                             'model = "not_in_the_manifest"\nbodies = "arm"\nbody = "arm"\n')
        sc3, what3 = spectator_scene(Sport(), str(plugin), cfg)         # a broken presentation: the match scene
        assert what3.startswith("match (presentation unavailable") and not sc3.is_presentation
    try:
        CameraWorker(sc, None)
        raise AssertionError("players' images must refuse a presentation scene")
    except ValueError:
        pass



def test_players_scene_is_the_presentation_scene_only_when_declared():
    """core 0.2.9, renderer rule 6: a presentation.toml with `players` = the players' images use it (CameraWorker
    accepts it, the same kinematics checked); without, the match scene."""
    from core.observe import CameraWorker, players_scene
    from core.spectator import spectator_scene
    from renderers.base import CameraDef, Scene
    from renderers.label import frame_label

    class Sport:
        def scene(self, cfg):
            return Scene(xml=_ARM)

    cfg = MatchConfig(sport="x", format="single", seats=("A",), seed=1)
    cam = CameraDef("c", pos=(1.2, -1.2, 0.8), lookat=(0, 0, 0.2), width=64, height=48).to_dict()
    with tempfile.TemporaryDirectory() as tmp:
        plugin = Path(tmp) / "plugin.py"
        assert not players_scene(Sport(), str(plugin), cfg).is_presentation        # no presentation/
        d = Path(tmp) / "presentation"
        d.mkdir()
        (d / "arm.xml").write_text(_MODEL)
        (d / "tetra.obj").write_text("v -.1 -.1 0\nv .1 -.1 0\nv 0 .1 0\nv 0 0 .4\nf 1 3 2\nf 1 2 4\nf 2 3 4\nf 3 1 4\n")
        decl = '[presentation]\nversion = 2\n[[presentation.robot]]\nmodel = "./arm.xml"\nbodies = "arm"\nbody = "arm"\n'
        (d / "presentation.toml").write_text(decl)
        sc = players_scene(Sport(), str(plugin), cfg)
        assert not sc.is_presentation                                             # spectators only
        (d / "presentation.toml").write_text(decl.replace("version = 2\n", 'version = 2\nplayers = "full"\n'))
        sc = players_scene(Sport(), str(plugin), cfg)
        assert sc.is_presentation and sc.players and "_vis:arm:0" in sc.xml
        w = CameraWorker(sc, None)
        fine = w.draw({"qpos": [0.3]}, [cam])
        plain = CameraWorker(Scene(xml=_ARM), None).draw({"qpos": [0.3]}, [cam])
        assert fine["png"] != plain["png"] and fine["renderer"] == "mujoco"
        assert frame_label(w.renderer, sc) is None                                # the competition picture: no tag
        sp, what = spectator_scene(Sport(), str(plugin), cfg)
        assert what == "presentation" and sp.is_presentation
        (d / "presentation.toml").write_text(decl.replace("version = 2\n", 'version = 2\nplayers = "fine"\n'))
        try:
            players_scene(Sport(), str(plugin), cfg)
            raise AssertionError("players must be full or a level of detail")
        except ValueError as e:
            assert "players" in str(e)


# ---- core 0.2.14: hidden official seeds (core/seeds.py) and the continuous score (core/score.py) ---------------
def test_hidden_seed_commitments():
    from core import seeds
    priv = seeds.new("fixture_turn", {"duel": 3, "single/L1": 2, "single/L2": 2}, avoid=[1, 2, 3])
    pub = seeds.public(priv)
    flat = [e["seed"] for v in priv["cells"].values() for e in v]
    assert pub["counts"] == {"duel": 3, "single/L1": 2, "single/L2": 2} and len(set(flat)) == 7   # no shared seeds
    assert all(seeds.SEED_RANGE[0] <= x <= seeds.SEED_RANGE[1] for x in flat)
    assert not any(str(x) in json.dumps(pub) for x in flat)                         # the public part names no seed
    for cell, entries in priv["cells"].items():
        fmt, _, lv = cell.partition("/L")
        for i, e in enumerate(entries):
            c = seeds.commitment("fixture_turn", e["seed"], e["salt"])
            assert seeds.index("fixture_turn", fmt, int(lv) if lv else None, c, pub) == i
            assert seeds.resolve(priv, cell, i, pub) == (e["seed"], e["salt"])
    e = priv["cells"]["single/L1"][0]
    c = seeds.commitment("fixture_turn", e["seed"], e["salt"])
    assert seeds.index("fixture_turn", "single", 2, c, pub) is None                 # another cell (level)
    assert seeds.index("fixture_turn", "duel", None, c, pub) is None                # another cell (format)
    assert seeds.index("fixture_turn", "single", 1, seeds.commitment("fixture_turn", e["seed"], "0" * 32), pub) is None
    assert seeds.index("fixture_turn", "single", 1, None, pub) is None              # no proof
    assert seeds.cell_of("duel", 2, pub["cells"]) == "duel"                          # a fixed level the sim reports
    forged = dict(pub, cells=dict(pub["cells"], duel=pub["cells"]["duel"][:-1] + ["ab" * 32]))
    assert seeds.index("fixture_turn", "duel", None, "ab" * 32, forged) is None      # not the registered list
    try:
        seeds.resolve(seeds.new("fixture_turn", {"duel": 3, "single/L1": 2, "single/L2": 2}), "duel", 0, pub)
        raise AssertionError("a different private set resolved against the registration")
    except ValueError:
        pass
    s = seeds.scrub({"seed": 5, "x": {"rng_seed": 7, "v": [123456, "123456", 2.5]}, "step": 123456,
                     "salt": "ab" * 16}, 123456, "ab" * 16)
    assert s == {"seed": -1, "x": {"rng_seed": -1, "v": [-1, "-1", 2.5]}, "step": 123456, "salt": "-1"}, s


def hidden_turn_duel(seed, salt, index=None):
    """A turn duel of the fixture played to the end at `seed`, with the runner's salt (and the seed itself, for the
    fresh-process replay) in the sim's environment."""
    env = {"RO_SEED_SALT": salt or "", "RO_SEED": str(seed), "RO_SEED_INDEX": "" if index is None else str(index)}
    os.environ.update(env)
    try:
        for s in ("A", "B"):
            os.environ[f"PLAYER_MODE_{s}"] = "oracle"
        cfg = MatchConfig(sport="fixture_turn", format="duel", seats=("A", "B"), seed=seed, first="A",
                          action_level="low")
        svc = TurnService(SPORT_TURN, PLUGIN_TURN, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
        threading.Thread(target=svc.loop, daemon=True).start()
        post = svc.routes(True)
        th = [threading.Thread(target=play_turn, args=(svc, post, s, v), daemon=True) for s, v in (("A", .3), ("B", .6))]
        for t in th:
            t.start()
        return svc, finish(svc)
    finally:
        for k in env:
            os.environ.pop(k, None)


def test_hidden_seed_official_only_when_registered():
    """The verifier counts a match as official only when its commitment is in the registered cell (core 0.2.14)."""
    from core import seeds
    priv = seeds.new("fixture_turn", {"duel": 3, "single": 2})
    reg = seeds.public(priv)
    e = priv["cells"]["duel"][1]
    svc, fin = hidden_turn_duel(e["seed"], e["salt"], 1)
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    assert fin["seed_proof"] == {"commitment": seeds.commitment("fixture_turn", e["seed"], e["salt"]), "index": 1}
    rc = json.loads((svc.data / "replay_check.json").read_text())
    assert rc["seed_commitment"] == fin["seed_proof"]["commitment"]
    contract = {"sport": "fixture_turn", "official": {"hidden_seeds": reg, "seeds": [e["seed"]], "first_any": True}}
    out = grade(fin, rc, contract, lambda d: {})
    assert out["official_config"] == 1 and out["hidden_seed"] == 1 and out["hidden_seed_index"] == 1, out
    assert out["seed"] == -1
    bad = dict(fin, seed_proof={"commitment": seeds.commitment("fixture_turn", e["seed"], "0" * 32)})
    out = grade(bad, dict(rc, seed_commitment=bad["seed_proof"]["commitment"]), contract, lambda d: {})
    assert out["official_config"] == 0 and out["hidden_seed"] == 0 and out["hidden_seed_index"] == -1
    out = grade(dict(fin, format="single"), rc, contract, lambda d: {})               # another cell
    assert out["hidden_seed"] == 0
    out = grade(dict(fin, seed_proof=None), rc, contract, lambda d: {})               # a public seed is not enough
    assert out["official_config"] == 0 and out["hidden_seed"] == 0
    other = seeds.public(seeds.new("fixture_turn", {"duel": 3, "single": 2}))         # an unregistered set
    out = grade(fin, rc, dict(contract, official=dict(contract["official"], hidden_seeds=other)), lambda d: {})
    assert out["official_config"] == 0
    out = grade(fin, dict(rc, seed_commitment="ab" * 32), contract, lambda d: {})      # the replay must agree
    assert out["deterministic"] == 0 and out["official_config"] == 1 and out["valid_trial"] == 0
    svc2, fin2 = hidden_turn_duel(7, None)                                             # no salt: an ordinary seed
    assert fin2["seed_proof"] is None and fin2["seed"] == 7
    assert grade(fin2, json.loads((svc2.data / "replay_check.json").read_text()), contract,
                 lambda d: {})["official_config"] == 0


def test_hidden_seeds_override_the_sports_official_rule():
    """Core 0.2.19: with a registered hidden seed set the sport's own official_config (a legacy public-seed rule in
    tests/sport_grade.py) cannot make a match official: only a registered hidden seed of the match's cell counts, and
    the sport's rule can only lower it."""
    from core import seeds
    priv = seeds.new("fixture_turn", {"duel": 3, "single": 2})
    reg = seeds.public(priv)
    e = priv["cells"]["duel"][0]
    svc, fin = hidden_turn_duel(e["seed"], e["salt"], 0)
    rc = json.loads((svc.data / "replay_check.json").read_text())
    contract = {"sport": "fixture_turn", "official": {"hidden_seeds": reg, "first_any": True}}
    legacy = lambda d: {"official_config": 1}                         # noqa: E731  a sport that always says 1
    defer = lambda d: {}                                               # noqa: E731  a sport that keeps the core's
    lower = lambda d: {"official_config": 0}                           # noqa: E731  e.g. its slowdown rule fails
    assert grade(fin, rc, contract, legacy)["official_config"] == 1    # hidden seed of the cell: official
    assert grade(fin, rc, contract, defer)["official_config"] == 1
    assert grade(fin, rc, contract, lower)["official_config"] == 0     # the sport can lower it
    svc2, pub = hidden_turn_duel(7, None)                              # a public seed: never official once frozen
    rc2 = json.loads((svc2.data / "replay_check.json").read_text())
    assert pub["seed_proof"] is None
    assert grade(pub, rc2, contract, legacy)["official_config"] == 0
    out = grade(dict(fin, format="single"), rc, contract, legacy)     # a commitment of another cell
    assert out["official_config"] == 0 and out["hidden_seed"] == 0
    assert grade(pub, rc2, {"sport": "fixture_turn", "official": {}}, legacy)["official_config"] == 1   # not frozen


def test_hidden_seed_is_never_written():
    """A hidden seed and its salt appear in no record of the match (episode, final.json, replay check, broadcast log,
    reward) nor in a reply to a player; the fresh-process replay still reproduces the match (core 0.2.14)."""
    from core import seeds
    priv = seeds.new("fixture_turn", {"duel": 2})
    e = priv["cells"]["duel"][0]
    svc, fin = hidden_turn_duel(e["seed"], e["salt"], 0)
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    assert fin["sport_fields"]["seed"] == -1 and fin["sport_fields"]["draws"] == [-1, 1]
    assert fin["cfg"]["seed"] == -1 and fin["seed"] == -1
    out = grade(fin, json.loads((svc.data / "replay_check.json").read_text()),
                {"sport": "fixture_turn", "official": {"hidden_seeds": seeds.public(priv)}}, lambda d: {})
    assert out["hidden_seed"] == 1 and out["seed"] == -1
    texts = {f.name: f.read_text() for f in svc.data.iterdir() if f.is_file() and f.suffix in (".json", ".jsonl")}
    texts["reward"] = json.dumps(out)
    os.environ.update(RO_SEED_SALT=e["salt"])
    try:
        texts["spec"] = json.dumps(svc.public(svc.spec("A")[1]))
        texts["observe"] = json.dumps(svc.public(svc.routes(True)["observe"]("A", {})[1]))
    finally:
        os.environ.pop("RO_SEED_SALT", None)
    assert "episode.jsonl" in texts and "replay_check.json" in texts and "final.json" in texts
    for name, text in texts.items():
        assert str(e["seed"]) not in text and e["salt"] not in text, name
    head = json.loads((svc.data / "episode.jsonl").read_text().splitlines()[0])
    assert head["cfg"]["seed"] == -1 and head["seed_hidden"]["commitment"] == fin["seed_proof"]["commitment"]
    from core.episode import header_cfg
    try:
        header_cfg(head)                                       # an offline replay needs the seed from the host
        raise AssertionError("a hidden-seed episode replayed without its seed")
    except ValueError:
        pass
    os.environ.update(RO_SEED=str(e["seed"] + 1), RO_SEED_SALT=e["salt"])
    try:
        header_cfg(head)
        raise AssertionError("a wrong seed was accepted for a hidden-seed episode")
    except ValueError:
        pass
    finally:
        os.environ.pop("RO_SEED", None), os.environ.pop("RO_SEED_SALT", None)


def test_continuous_score_in_final_reward_and_replay():
    svc, fin = hidden_turn_duel(5, None)
    c = fin["continuous"]
    assert c["name"] == "score_share" and c["higher_is_better"] is True and c["forfeited"] == []
    assert abs(c["by_side"]["A"] - .3 / .9) < 1e-6 and abs(c["by_side"]["B"] - .6 / .9) < 1e-6, c
    rc = json.loads((svc.data / "replay_check.json").read_text())
    assert rc["continuous"] == c["by_side"]
    out = grade(fin, rc, {"sport": "fixture_turn", "score": {"forfeit": 0.0}}, lambda d: {})
    assert out["A_continuous_score"] == c["by_side"]["A"] and out["B_continuous_score"] == c["by_side"]["B"]
    assert "continuous_score" not in out                                               # two sides: per seat only
    out = grade(dict(fin, continuous=dict(c, by_side={"A": 0.9, "B": 0.1})), rc, {}, lambda d: {})
    assert out["deterministic"] == 0 and out["valid_trial"] == 0                       # the replay must agree


def test_continuous_score_forfeit_value_on_no_show():
    with start_window(1):
        svc, post = turn_service(["A", "B"])
        assert post["start"]("A", {})[0] == 200                                    # B never starts
        fin = finish(svc)
    check_no_show(svc, fin)
    assert fin["continuous"]["by_side"] == {"A": 0.5, "B": 0.0} and fin["continuous"]["forfeited"] == ["B"]
    out = graded(svc, fin)
    assert out["A_continuous_score"] == 0.5 and out["B_continuous_score"] == 0.0


def test_continuous_score_rules():
    from core import score
    decl = {"score": {"name": "x", "text": "t", "from": "share", "forfeit": 0.0}, "formats": {"d": {"seats": ["A", "B"]}}}
    m = Stub({"A": 3, "opponent": 1})
    assert score.compute(m, decl, ["A"])["by_side"] == {"A": 0.75}                     # against a scripted opponent
    assert score.compute(Stub({"A": 0, "B": 0}), decl, ["A", "B"])["by_side"] == {"A": 0.5, "B": 0.5}
    assert score.compute(m, decl, ["A"], forfeited=["A"])["by_side"] == {"A": 0.0}
    d = {"score": dict(decl["score"], **{"from": "margin", "forfeit": -10})}
    assert score.compute(Stub({"A": 1, "B": 4, "C": 2}), d, ["A", "B"])["by_side"] == {"A": -3.0, "B": 2.0}
    d = {"score": dict(decl["score"], **{"from": "own"})}
    assert score.compute(Stub({"A": 31}), d, ["A"])["by_side"] == {"A": 31.0}
    assert score.compute(m, {}, ["A"]) is None                                         # not declared: nothing
    h = Stub({"A": 0})
    h.continuous_score = lambda: {"A": float("nan")}
    try:
        score.compute(h, {"score": dict(decl["score"], **{"from": "hook"})}, ["A"])
        raise AssertionError("a non-finite continuous score was accepted")
    except RuntimeError:
        pass
    assert score.problems(decl, False) == []
    assert score.problems({"score": {"name": "Bad name", "from": "hook", "forfeit": "x"}}, False)
    solo = {"score": dict(decl["score"]), "formats": {"s": {"seats": ["A"]}}}
    assert any("opponent" in p for p in score.problems(solo, False))


# ------------------------------------------------------------------ core 0.2.15: a layer's tick
def test_layer_tick_is_applied_logged_and_replayed():
    """An action layer's tick(seat, match) (the skill in the loop's step(), skilleval/inloop.py) runs every control
    step before the actions: its command is applied, logged as a command row and the episode replays without the
    layer (core/local.py and core/realtime.py share the rule)."""
    from core import local
    from core.episode import read_rows, replay

    class Tick(SPORT.action_layer("low").__class__):
        def tick(self, seat, match):
            return {"type": "move", "entity": "e0", "v": 0.25 if (match.k // 10) % 2 else -0.5} \
                if match.k % 10 == 0 else None

    class WithTick:
        def __getattr__(self, k):
            return getattr(SPORT, k)

        def action_layer(self, level):
            return Tick(0)

    class Idle:
        def act(self, view):
            return None

    cfg = MatchConfig(sport="fixture", format="solo", seats=("A",), seed=1, slowdown=1.0)
    d = Path(tempfile.mkdtemp(prefix="core-test-"))
    r = local.play(WithTick(), cfg, {"A": Idle()}, data=d, render=False)
    rows = read_rows(d / "episode.jsonl")
    cmds = [x for x in rows if x["ev"] == "cmd"]
    assert len(cmds) == 9 and all(c["cmd"]["entity"] == "e0" for c in cmds), cmds[:3]
    assert r["scores"]["A"] != 0
    rep = replay(SPORT, rows)
    assert rep["state_sha"] == r["digest"] and rep["scores"] == r["scores"], (rep, r)


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    bad = 0
    for name, f in tests:
        t = time.time()
        try:
            f()
            print(f"ok   {name} ({time.time() - t:.1f} s)")
        except Exception:  # noqa: BLE001
            bad += 1
            print(f"FAIL {name}\n{traceback.format_exc()}")
    print(f"{len(tests) - bad}/{len(tests)} passed")
    return 1 if bad else 0



def test_local_play_refused_action_is_a_refusal():
    """core 0.2.3: a built-in player's invalid action is refused (as HTTP 400 in a real match), not a crash."""
    from core import local
    cfg = MatchConfig(sport="fixture_turn", format="duel", seats=("A", "B"), seed=1, first="A", action_level="low")

    class Flaky:
        def __init__(self):
            self.n = 0

        def act(self, view):
            self.n += 1
            return {"type": "add", "v": 5.0} if self.n == 1 else {"type": "add", "v": 0.5}   # first: out of range

    r = local.play(SPORT_TURN, cfg, {"A": Flaky(), "B": Flaky()}, render=False, plugin=PLUGIN_TURN)
    assert r["winner"] in ("A", "B"), r     # the match was played out despite the refused first actions



def test_team_channel_switch_off():
    """core 0.2.5: RO_TEAM_CHANNEL=off switches a declared team channel off (403), on by default."""
    from core.channel import TeamChannel
    cfg = MatchConfig(sport="fixture", format="team", seats=("A1", "A2", "B1", "B2"), seed=1,
                      sides={"A1": "A", "A2": "A", "B1": "B", "B2": "B"})
    conf = {"max_bytes": 64, "min_interval_s": 0.0, "max_messages": 5}
    os.environ.pop("RO_TEAM_CHANNEL", None)
    assert TeamChannel(cfg, conf).say("A1", "go left", 0, 0.01)[0] == 200
    os.environ["RO_TEAM_CHANNEL"] = "off"
    try:
        code, body = TeamChannel(cfg, conf).say("A1", "go left", 0, 0.01)
        assert code == 403 and "off" in body["error"], (code, body)
    finally:
        os.environ.pop("RO_TEAM_CHANNEL", None)
    assert TeamChannel(cfg, None).say("A1", "x", 0, 0.01)[0] == 404      # not declared: no channel at all



# ------------------------------------------------------------ a session that ends mid-match (core 0.2.6, core rule 6)
def check_abandoned(svc, fin):
    """A single side whose session ended after the start: a valid loss by forfeit (abandoned), replayed; success 0."""
    assert fin["reason"] == "abandoned" and fin["forfeiting"] == "A" and fin["winner"] is None, fin
    assert fin["decided_by"] == "forfeit:abandoned" and fin["match_winner"] is None, fin
    assert fin["valid_trial"] and fin["deterministic"] and not fin["technical_failure"], fin["errors"]
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    assert any(r["ev"] == "forfeit" and r["seat"] == "A" and r["why"] == "abandoned" for r in rows)
    out = graded(svc, fin)
    assert out["valid_trial"] == 1 and out["technical_failure"] == 0 and out["success"] == 0, out
    assert out["abandoned"] == 1 and out["no_show"] == 0 and out["A_won"] == 0 and out["A_no_show"] == 0, out


def test_solo_quit_realtime_single_mid_match_is_a_valid_loss():
    for when in ("running", "review"):
        svc, post = service(["A"], fmt="single")
        threading.Thread(target=post["start"], args=("A", {}), daemon=True).start()   # never reviews
        t = time.time()
        while svc.phase != when and time.time() - t < 10:
            time.sleep(0.005)
        assert svc.phase == when, svc.phase
        svc.collect()                                                              # the session ends mid-match
        fin = finish(svc)
        check_abandoned(svc, fin)
        assert fin["steps"] < 90 and (when == "running" or fin["steps"] == 30), fin["steps"]


def test_solo_quit_turn_single_on_and_off_turn_is_a_valid_loss():
    for case in ("on_turn", "awaiting_review", "off_turn"):
        svc, post = turn_service(["A"], fmt="single")
        post["start"]("A", {})
        if case != "on_turn":
            assert post["act"]("A", {"v": 0.5})[0] == 200                         # one move, review pending
        if case == "off_turn":
            post["ready"]("A", {"why": "w", "plan": "p"})
            with svc.cond:              # a sport whose to_move() names nobody for a while (e.g. a pending action)
                svc.set_turn(None)
        svc.collect()
        fin = finish(svc)
        check_abandoned(svc, fin)
        assert fin["steps"] == (0 if case == "on_turn" else 1), fin["steps"]


def test_solo_quit_realtime_duel_unchanged():
    """Two sides: the collect before the end still leaves the match unfinished ("collected", invalid). A side that
    stops playing while the other plays on loses at the next review it owes (ready_timeout, valid)."""
    svc, post = service(["A", "B"], fmt="duel")
    for s in ("A", "B"):
        threading.Thread(target=post["start"], args=(s, {}), daemon=True).start()
    t = time.time()
    while svc.phase != "running" and time.time() - t < 10:
        time.sleep(0.005)
    svc.collect()
    fin = finish(svc)
    assert fin["reason"] == "collected" and fin["forfeiting"] is None and fin["winner"] is None, fin
    assert not fin["valid_trial"] and graded(svc, fin)["abandoned"] == 0
    svc, post = service(["A", "B"], fmt="duel")
    threading.Thread(target=play, args=(svc, post, "A"), daemon=True).start()
    threading.Thread(target=post["start"], args=("B", {}), daemon=True).start()   # B starts, then never reviews
    fin = finish(svc)
    assert fin["reason"] == "ready_timeout" and fin["forfeiting"] == "B" and fin["winner"] == "A", fin
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]


PLUGIN_IMG = str(Path(__file__).resolve().parent / "fixture_images" / "plugin.py")
_TINY = ('<mujoco><visual><headlight ambient=".5 .5 .5"/></visual><worldbody><geom type="plane" size="5 5 .1" '
         'rgba=".3 .5 .3 1"/><body mocap="true" pos="0 0 .2"><geom type="box" size=".1 .1 .1" rgba="1 0 0 1"/>'
         '</body></worldbody></mujoco>')
_CAM = {"name": "top", "pos": [0, 0, 3], "lookat": [0, 0, 0], "up": [1, 0, 0], "fovy_deg": 60, "width": 64,
        "height": 48}


def _img_service():
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    for s in ("A", "B"):
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    sport = load_plugin(PLUGIN_IMG)
    cfg = MatchConfig(sport="fixture_images", format="duel", seats=("A", "B"), seed=1, first="A", action_level="low")
    svc = TurnService(sport, PLUGIN_IMG, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    post = svc.routes(True)
    post["start"]("A", {})
    post["start"]("B", {})
    return svc, post


def test_reply_images_turn_attached_replayable_and_review_state():
    """core 0.2.8: Match.reply_views -> the act reply carries the result's images (observe's format, frames with
    labels), drawn off the lock by the task renderer; a replay draws the same PNG; the sport sees whose review is due
    (the other seat gets no images while the actor reviews, although the sport's to_move() already names it)."""
    import base64
    import struct
    from core.episode import read_rows, reply_image
    svc, post = _img_service()
    assert post["observe"]("A", {})[1]["observation"].get("image_png_b64")      # on turn: the camera image
    code, out = post["act"]("A", {"v": 0.7})
    assert code == 200, out
    ob = out["observation"]
    raw = base64.b64decode(ob["image_png_b64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", raw[16:24]) == (160, 60)
    assert [(t["camera"], t["frame"], t["label"]) for t in ob["tiles"]] == [("top", 0, "before"), ("top", 1, "after")]
    assert ob["of"] and ob["note"] and "render_wall_s" in ob
    assert svc.m.awaiting_review == "A" and out["state"]["awaiting_review"] and svc.m.to_move() == "B"
    assert "image_png_b64" not in post["observe"]("B", {})[1]["observation"]     # the review-window leak is closed
    rows = read_rows(svc.data / "episode.jsonl")
    assert [(r["seat"], r["tiles"]) for r in rows if r["ev"] == "reply_images"] == [("A", 2)]   # information row
    img = reply_image(PLUGIN_IMG, rows, 1)
    assert img["png"] == raw and img["tiles"] == ob["tiles"]          # a pure function of the recorded match
    post["ready"]("A", {"why": "w", "plan": "p"})
    assert svc.m.awaiting_review is None
    assert post["observe"]("B", {})[1]["observation"].get("image_png_b64")      # B's turn now
    assert svc.camera is not None and not svc.camera.renderer.scene.is_presentation   # the match scene only
    svc.collect()
    finish(svc)


def test_reply_images_off_the_lock_and_off_the_clock():
    """Drawing the reply image neither blocks the other seat nor runs the actor's chess clock."""
    svc, post = _img_service()
    orig = svc.draw

    def slow(seat, job):
        time.sleep(1.5)
        return orig(seat, job)
    svc.draw = slow
    res = {}
    th = threading.Thread(target=lambda: res.update(r=post["act"]("A", {"v": 0.5})), daemon=True)
    t0 = time.time()
    th.start()
    time.sleep(0.5)
    t = time.time()
    code, st = svc.routes(False)["status"]("B", {})
    assert code == 200 and time.time() - t < 0.3, "the other seat was blocked by the drawing"
    assert svc.seats["A"].frozen == 1
    th.join()
    assert time.time() - t0 >= 1.5 and res["r"][0] == 200 and res["r"][1]["observation"].get("image_png_b64")
    used = svc.seats["A"].clock_used()
    assert used < 0.5, f"the drawing ran the actor's clock: {used:.2f} s"
    svc.collect()
    finish(svc)


def test_reply_images_realtime():
    """Realtime: an act that takes effect at once carries its result's images (frames, camera order, labels), drawn
    after the act's timing was taken; the match stays deterministic."""
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    from renderers.base import Scene
    World = type(SPORT.build(MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1)))

    class ImgWorld(World):
        def cameras(self, seat, query=None):
            return [_CAM]

        def render_state(self):
            return {"qpos": [], "mocap_pos": [[self.pos["A.e0"] * 0.01, 0.0, 0.2]], "mocap_quat": [[1, 0, 0, 0]]}

        def reply_views(self, seat, cmd, info):
            later = {"qpos": [], "mocap_pos": [[0.5, 0.0, 0.2]], "mocap_quat": [[1, 0, 0, 0]]}
            return {"frames": [{"cameras": [_CAM, dict(_CAM, name="top2")], "label": "now"},
                               {"cameras": [_CAM, dict(_CAM, name="top2")], "state": later, "label": "later"}],
                    "order": "camera", "columns": 2, "note": "two frames"}

    class ImgSport(type(SPORT)):
        def build(self, cfg):
            return ImgWorld(cfg)

        def scene(self, cfg):
            return Scene(xml=_TINY)

    for s in ("A", "B"):
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1, slowdown=1.0)
    svc = RealtimeService(ImgSport(), PLUGIN, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    post = svc.routes(True)
    for s in ("A", "B"):
        threading.Thread(target=post["start"], args=(s, {}), daemon=True).start()
    while svc.phase != "running":
        time.sleep(0.01)
    code, out = post["act"]("A", {"type": "move", "v": 0.5, "entity": "e0"})
    assert code == 200, out
    ob = out["observation"]
    assert [(t["camera"], t["frame"], t["label"]) for t in ob["tiles"]] == [
        ("top", 0, "now"), ("top", 1, "later"), ("top2", 0, "now"), ("top2", 1, "later")], ob["tiles"]
    assert ob["note"] == "two frames" and ob["image_png_b64"] and "wall_s_after_request" in out["took_effect"]
    fin = run_all(svc, post, ["A", "B"])
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]


# ------------------------------------------------------------------ core 0.2.11: malformed requests never void a match
HOSTILE_RAW = [b'{"type": "add", "v": 1' + b"0" * 400 + b"}", b'{"type": "add", "v": NaN}',
               b'{"type": "add", "v": Infinity}', b'{"type": "add", "v": 1e400}', b'{"type": []}', b'{"type": {}}',
               b'{"type": null}', b'{"type": "add", "v": [1, [2, [3]]]}', b'{"type": "add", "v": {"a": 1}}',
               b"[" * 5000 + b"]" * 5000, b'{"type": "' + b"x" * 20000 + b'"}', b"not json", b"\xff\xfe",
               b'{"type": "add", "v": "0.5"}', b"[1, 2]", b'"x"', b'{"type": "add", "v": 0.5, "x": ' +
               b"[" * 50 + b"]" * 50 + b"}"]


def _http(svc, seats):
    from core.http import make_server
    srv = make_server(svc, seats, {}, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _post(port, path, raw, timeout=10):
    time.sleep(0.06)                          # under the 20 requests per second and seat (core/http.py)
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=raw, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_turn_malformed_actions_are_refusals_over_http():
    """core 0.2.11 (anti-cheat G3): a hostile act body (huge integer, NaN / inf, an unhashable type, nested junk,
    oversize strings, broken JSON) is the player's own 400; the match goes on and stays a valid trial."""
    svc, post = turn_service(["A", "B"])
    srv, port = _http(svc, ("A", "B"))
    try:
        for s in ("A", "B"):
            assert post["start"](s, {})[0] == 200
        assert svc.on_turn == "A"
        for raw in HOSTILE_RAW:
            code, out = _post(port, "/A/act", raw)
            assert 400 <= code < 500, (raw[:40], code, out)
            assert "detail" not in out and "Error" not in json.dumps(out), out
        for raw in (b'{"timeout_s": 1' + b"0" * 400 + b"}", b'{"timeout_s": [1]}', b'{"query": {"a": 1e999}}'):
            code, out = _post(port, "/A/wait", raw)
            assert 400 <= code < 500, (raw[:40], code, out)
        code, out = _post(port, "/A/observe", b'{"query": {"a": [1' + b"0" * 400 + b"]}}")
        assert code == 400, (code, out)
        assert svc.phase == "play" and not svc.errors, (svc.phase, svc.errors)
        assert svc.seats["A"].stats["refused_invalid"] >= 6, svc.seats["A"].stats
    finally:
        srv.shutdown()
        srv.server_close()
    th = [threading.Thread(target=play_turn, args=(svc, post, s, v), daemon=True) for s, v in (("A", .3), ("B", .6))]
    for t in th:
        t.start()
    fin = finish(svc)
    assert fin["reason"] == "match_over" and fin["valid_trial"] and fin["deterministic"], fin
    rows = [json.loads(x) for x in (svc.data / "episode.jsonl").read_text().splitlines()]
    assert any(r["ev"] == "refused_invalid" for r in rows)


def test_parse_exceptions_are_refusals_and_world_errors_stay_failures():
    """Any exception of the action layer's parse is a refusal (no exception text to the player); an exception of
    the world after the action was accepted is still a technical failure, and the 500 reply carries no detail."""
    from core.sport import parse_action
    svc, post = turn_service(["A", "B"])
    inner = svc.layer

    class Crashy:
        level, worker, delay_steps = "low", None, 0

        def schema(self, m, seat):
            return inner.schema(m, seat)

        def parse(self, seat, body, m, ctx):
            if body.get("v") == 0.25:
                raise ZeroDivisionError("secret internal detail")
            return inner.parse(seat, body, m, ctx)

        def __getattr__(self, k):
            return getattr(inner, k)

    svc.layer = Crashy()
    try:
        parse_action(svc.layer, "A", {"type": "add", "v": 0.25}, svc.m, {})
        raise AssertionError("not refused")
    except Refused as exc:
        assert "secret" not in str(exc) and "ZeroDivisionError" in exc.cause
    srv, port = _http(svc, ("A", "B"))
    try:
        for s in ("A", "B"):
            post["start"](s, {})
        code, out = _post(port, "/A/act", b'{"type": "add", "v": 0.25}')
        assert code == 400 and "secret" not in json.dumps(out), (code, out)
        assert svc.phase == "play" and not svc.errors
        world_apply = svc.m.apply

        def boom(seat, cmd):
            raise RuntimeError("secret world detail")
        svc.m.apply = boom
        code, out = _post(port, "/A/act", b'{"type": "add", "v": 0.5}')
        assert code == 500 and out.get("error") == "technical failure" and "detail" not in out, (code, out)
        assert "secret" not in json.dumps(out)
        svc.m.apply = world_apply
        assert svc.reason == "technical_error" and svc.errors
    finally:
        srv.shutdown()
        srv.server_close()


def test_realtime_malformed_actions_are_refusals_over_http():
    """The realtime protocol: hostile act / wait / observe / ready / say bodies are 400s, the world runs on."""
    svc, post = service(["A", "B"], fmt="duel")
    srv, port = _http(svc, ("A", "B"))
    try:
        for s in ("A", "B"):                  # both seats start and review as usual; A also sends hostile bodies
            threading.Thread(target=play, args=(svc, post, s), daemon=True).start()
        t = time.time()
        while svc.phase != "running" and time.time() - t < 10:
            time.sleep(0.01)
        assert svc.phase == "running"
        for raw in [*HOSTILE_RAW, b'{"type": "move", "v": 0.5, "entity": "' + b"e" * 9000 + b'"}']:
            code, out = _post(port, "/A/act", raw)
            assert 400 <= code < 500, (raw[:40], code, out)
            assert "detail" not in out, out
        for ep, raw in (("wait", b'{"dt": 1' + b"0" * 400 + b"}"), ("wait", b'{"dt": [1]}'),
                        ("observe", b'{"query": {"q": 1e999}}'), ("observe", b'{"query": [1]}'),
                        ("say", b'{"text": ["x"]}'), ("ready", b'{"why": 1' + b"0" * 400 + b"}")):
            code, out = _post(port, f"/A/{ep}", raw)
            assert 400 <= code < 500, (ep, raw[:40], code, out)
        assert svc.reason != "technical_error" and not svc.errors, (svc.reason, svc.errors)
        assert svc.seats["A"].stats["refused_invalid"] >= 6 and svc.seats["A"].stats["refused"] >= 6
    finally:
        srv.shutdown()
        srv.server_close()
    fin = finish(svc)
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]


def test_check_body_and_check_action_limits():
    from core.sport import check_action, check_body
    for bad in (10 ** 400, 2 ** 70, float("nan"), float("inf"), 1e300, "x" * 9000, [0] * 5000,
                json.loads("[" * 20 + "]" * 20), {"k" * 9000: 1}):
        try:
            check_body({"v": bad})
            raise AssertionError(f"accepted {str(bad)[:20]}")
        except Refused:
            pass
    check_body({"type": "x", "q": [[0.1] * 8] * 600, "s": "ok", "n": None, "b": True, "i": -3})
    schema = {"go": {"v": {"type": "vector", "len": 3}, "r": {"type": "vector", "len": "1 or 2"},
                     "rows": {"type": "rows", "len": 2, "max_rows": 3}, "o": {"type": "object", "keys": ["a"]},
                     "e": {"type": "enum", "values": ["x"]}, "b": {"type": "boolean"}, "n": {"type": "number"}}}
    check_action(schema, {"type": "go", "v": [1, 2, 3], "r": [1], "rows": [[1, 2]], "o": {"a": 1}, "e": "x",
                          "b": False, "n": 2})
    check_action(schema, {"rods": {}})                    # an implicit type stays with the layer
    for body in ({"type": []}, {"type": 3}, {"type": "x" * 65}, {"type": "go", "v": [1, 2]},
                 {"type": "go", "v": [1, 2, "3"]}, {"type": "go", "r": [1, 2, 3]}, {"type": "go", "rows": [[1]]},
                 {"type": "go", "rows": [[1, 2]] * 4}, {"type": "go", "o": {"z": 1}}, {"type": "go", "e": ["x"]},
                 {"type": "go", "b": 1}, {"type": "go", "n": "1"}, {"type": "go", "n": True}, [1]):
        try:
            check_action(schema, body)
            raise AssertionError(f"accepted {body}")
        except Refused:
            pass
# ------------------------------------------------------------------ unmetered seats (core 0.2.27)
def test_unmetered_seat_needs_no_meter_and_no_proxy():
    from core.launch import seat_mode
    from core.seats import Seat, validity_fields
    data = Path(tempfile.mkdtemp(prefix="core-test-"))
    os.environ["PLAYER_MODE_A"] = "unmetered"
    try:
        st = Seat("A", data)
        st.joined = True
        assert st.mode == "unmetered" and st.meter.decided_by_model()       # acts pass without a metering proxy
        st.meter.check_ready()
        v = validity_fields({"A": st}, lambda s: s.mode == "model" and s.joined)
        assert v["meter_error"] == {"A": False} and v["proxy_error"] == {"A": False}
        assert v["player_modes"] == {"A": "unmetered"}
        assert seat_mode("A") == "unmetered" and seat_mode("B", {"RCB_PLAYER_MODE": "oracle"}) == "oracle"
        os.environ["PLAYER_MODE_A"] = "model"
        st = Seat("A", data)
        st.joined = True
        assert validity_fields({"A": st}, lambda s: s.mode == "model" and s.joined)["meter_error"] == {"A": True}
        os.environ["PLAYER_MODE_A"] = "metered-elsewhere"
        try:
            Seat("A", data)
            raise AssertionError("an unknown player mode must be refused")
        except ValueError:
            pass
    finally:
        os.environ.pop("PLAYER_MODE_A", None)


# ------------------------------------------------------------------ core 0.2.13
def test_game_shortcuts_send_entity_and_enum_values_as_text():
    """The `game` shortcuts send `entity` as written and a value that is not a number (an enum value, true / false) as
    such; the core checks the body. Cores <= 0.2.12 sent robot 1 as entity "1.0" (refused) and exited with the usage
    text on an enum value."""
    from core.sport import MatchBase, SchemaLayer, parse_action
    cli = {"kick": ["kick", "entity", "power", "foot", "chip"]}
    game = {"__name__": "game"}
    exec(compile((ROOT / "core" / "game.py").read_text().replace("@@COMMANDS@@", json.dumps(cli)), "game", "exec"), game)
    sent = []
    game.update(call=lambda ep, body=None: sent.append(body) or {}, show=lambda out: None)
    game["main"](["kick", "1", "0.5", "left", "true"])
    assert sent == [{"type": "kick", "entity": "1", "power": 0.5, "foot": "left", "chip": True}], sent

    class Robots(MatchBase):
        def schema(self, seat):
            return {"kick": {"power": {"type": "number", "min": 0, "max": 1},
                             "foot": {"type": "enum", "values": ["left", "right"]}, "chip": {"type": "boolean"}}}

        def entities(self, seat):
            return ("1", "2")
    assert parse_action(SchemaLayer(), "A", sent[0], Robots(), {}) == sent[0]


def test_fairness_plays_and_counts_the_sides_of_a_team_format():
    """The fairness check plays a team format with its sides and judges it against one over the number of sides. The
    turn fixture's built-in player always adds 0.5, so the first side wins every match by the last tiebreak: +50 pp
    for the first side, 0 for seat A1 (whose side starts half the matches). Cores <= 0.2.12 played one side per seat
    (A1 won every match) and judged against 1/4: -25 pp and +75 pp."""
    from core import testkit
    rows = testkit.fairness(PLUGIN_TURN, matches=2)
    assert [r["name"] for r in rows] == ["fairness:team"], rows
    got = json.loads(rows[0]["detail"])
    assert got["N"] == 4 and got["first_side"]["advantage_pp"] == 50 and got["seat_A1"]["advantage_pp"] == 0, got
    assert not rows[0]["ok"]


def test_replay_video_appears_only_when_complete():
    """The replay video is written to replay.part.mp4 and renamed once its writer has closed: a render that stops early
    (killed at RCB_VIDEO_TIMEOUT_S) leaves no replay.mp4 for the grader to count as rendered. Cores <= 0.2.12 wrote
    replay.mp4 in place."""
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    from core import episode, local, spectator
    sport = load_plugin(PLUGIN_IMG)
    cfg = MatchConfig(sport="fixture_images", format="duel", seats=("A", "B"), seed=1, first="A", action_level="low")

    class Mover:
        def act(self, view):
            return {"type": "add", "v": 0.5}
    data = Path(tempfile.mkdtemp(prefix="core-test-"))
    local.play(sport, cfg, {"A": Mover(), "B": Mover()}, data=data, render=False, plugin=PLUGIN_IMG)
    replay = episode.replay

    def stopped(sport, rows, observer):                  # the render stops after its first frame
        def first(match):
            observer(match)
            raise TimeoutError
        return replay(sport, rows, observer=first)
    episode.replay = stopped
    try:
        spectator.render_video(PLUGIN_IMG, data)
        raise AssertionError("the render went on")
    except TimeoutError:
        pass
    finally:
        episode.replay = replay
    assert (data / "replay.part.mp4").exists() and not (data / "replay.mp4").exists()
    info = spectator.render_video(PLUGIN_IMG, data)
    assert info["video"] and (data / "replay.mp4").stat().st_size and not (data / "replay.part.mp4").exists(), info


def test_realtime_resume_time_is_not_game_time():
    """The world's clock restarts when Match.resume() has returned: a resume that takes 0.5 s (a sport setting up the
    next unit) no longer makes the loop run the missed control steps back to back. Cores <= 0.2.12 anchored the clock
    before resume(): the unit's first steps ran at once to catch up, the first one 0.5 s late."""
    World = type(SPORT.build(MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1)))

    class SlowResume(World):
        def resume(self):
            time.sleep(0.5)
            super().resume()

    class SlowSport(type(SPORT)):
        def build(self, cfg):
            return SlowResume(cfg)

    for s in ("A", "B"):
        os.environ[f"PLAYER_MODE_{s}"] = "oracle"
    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1, slowdown=1.0)
    svc = RealtimeService(SlowSport(), PLUGIN, cfg, Path(tempfile.mkdtemp(prefix="core-test-")))
    threading.Thread(target=svc.loop, daemon=True).start()
    fin = run_all(svc, svc.routes(True), ["A", "B"])
    assert fin["valid_trial"] and fin["deterministic"], fin["errors"]
    assert fin["sim_lag"]["late_max_s"] < 0.25, fin["sim_lag"]


def test_entity_refused_from_a_seat_without_entities():
    """An act may name an entity only if the seat has entities (Match.entities); otherwise the core refuses it (400),
    in both protocols and in local play (parse_action). Cores <= 0.2.12 passed it on, and in real time every new
    entity string was a new act slot: one act in flight per (seat, entity), one pending act per (seat, entity)."""
    from core.sport import SchemaLayer, parse_action
    cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1)
    world = SPORT.build(cfg)

    class OneBody(type(world)):                           # the realtime fixture's world without entities
        def entities(self, seat):
            return ()
    game = SPORT_TURN.build(MatchConfig(sport="fixture_turn", format="duel", seats=("A", "B"), seed=1, first="A"))
    assert parse_action(SchemaLayer(), "A", {"type": "move", "v": 0.5, "entity": "e1"}, world, {})["entity"] == "e1"
    for layer, m, body in ((SchemaLayer(), OneBody(cfg), {"type": "move", "v": 0.5}),
                           (SPORT_TURN.action_layer("low"), game, {"v": 0.5})):
        for entity in ("x1", "x2", 7):
            try:
                parse_action(layer, "A", {**body, "entity": entity}, m, {})
                raise AssertionError(f"{type(m).__name__} accepted entity {entity!r}")
            except Refused as e:
                assert e.code == 400 and "entit" in str(e), e
        assert "entity" not in parse_action(layer, "A", body, m, {})


# ------------------------------------------------------------------ core 0.2.16: the budget of the authenticated seat
class _Held:
    """A service whose `hold` stays open until the gate opens (open requests); `ping` answers at once."""

    def __init__(self):
        self.gate, self.entered = threading.Event(), threading.Semaphore(0)

    def routes(self, post):
        return {"hold": self.hold, "ping": lambda seat, body: (200, {"seat": seat})}

    def hold(self, seat, body):
        self.entered.release()
        self.gate.wait(30)
        return 200, {"seat": seat}

    def failure(self, ep, exc):
        pass


def _call(port, path, timeout=30):
    """One POST without retries: (status, raw body); a connection refused before its request was read (closed while
    the client still wrote it, which core/client.py retries like a bare 429) is (429, b"")."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, (BrokenPipeError, ConnectionResetError)):
            return 429, b""
        raise


def _hold(port, svc, seats, n=4):
    """n held requests per seat, each in its own thread; returns (threads, results) once all reached the service."""
    results, threads = [], []
    for s in seats:
        for _ in range(n):
            t = threading.Thread(target=lambda s=s: results.append((s, _call(port, f"/{s}/hold"))), daemon=True)
            t.start()
            threads.append(t)
    for _ in range(n * len(seats)):
        assert svc.entered.acquire(timeout=15), f"held requests refused: {results}"
    return threads, results


def test_http_budget_belongs_to_the_authenticated_seat():
    """core 0.2.16: without SEAT_HOSTS every local seat may be any seat; each seat has its own 4 open requests and
    20 per second (cores <= 0.2.15 charged every local connection to the first seat: a team format's 8 local seats
    shared 4 slots and got 429s). The 429 of a full seat is bare (core/client.py retries it), other seats go on."""
    from core.http import make_server
    seats = ("A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4")
    svc = _Held()
    srv = make_server(svc, seats, {}, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        threads, results = _hold(port, svc, ["A1"])
        assert _call(port, "/A1/ping") == (429, b""), "a seat over its own 4 open requests"
        code, raw = _call(port, "/B1/ping")
        assert code == 200 and json.loads(raw) == {"seat": "B1"}, (code, raw)
        more, results2 = _hold(port, svc, seats[1:])          # every other seat: 4 open requests each, 32 in all
        svc.gate.set()
        for t in threads + more:
            t.join(15)
        got = results + results2
        assert len(got) == 32 and all(c == 200 and json.loads(raw)["seat"] == s for s, (c, raw) in got), got
        time.sleep(1.1)                                       # a new second for every seat
        codes = [_call(port, "/A2/ping")[0] for _ in range(30)]
        assert codes[:20] == [200] * 20 and 429 in codes, codes   # A2's 20 per second ...
        code, raw = _call(port, "/A3/ping")
        assert code == 200 and json.loads(raw) == {"seat": "A3"}, (code, raw)   # ... are not A3's
    finally:
        svc.gate.set()
        srv.shutdown()
        srv.server_close()


def test_http_seat_never_spends_another_seats_budget():
    """core 0.2.16: a request for a seat its address may not be (SEAT_HOSTS) is refused (403) before it spends any
    seat's budget, and before a request is read an address holds only the budget of the seats it may be."""
    from core.http import make_server
    svc = _Held()
    srv = make_server(svc, ("A", "B"), {"B": "192.0.2.1"}, port=0)   # B's container: never this host (TEST-NET-1)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        for _ in range(8):
            time.sleep(0.06)
            assert _call(port, "/B/ping")[0] == 403, "impersonating B"
        assert srv.arrivals["B"] == [] and srv.slots["B"].acquire(False), "B's budget spent by another address"
        srv.slots["B"].release()
        code, raw = _call(port, "/A/ping")
        assert code == 200 and json.loads(raw) == {"seat": "A"}, (code, raw)
        time.sleep(1.1)
        threads, results = _hold(port, svc, ["A"])
        assert _call(port, "/A/ping") == (429, b"")           # this address may be A only: A's 4 open requests
        assert _call(port, "/B/ping") == (429, b"")           # and no more, whatever seat the path names
        svc.gate.set()
        for t in threads:
            t.join(15)
        assert [c for _, (c, _) in results] == [200] * 4, results
    finally:
        svc.gate.set()
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------------ core 0.2.17: the testkit's replay limit
def test_testkit_replay_timeout_from_sport_toml():
    """core 0.2.17: the fresh-process replays of the generic tests (determinism, solo_quit) take sport.toml [timing]
    replay_timeout_s when it is above 1800 s (a 600 s match replays in more than 1800 s), never less than 1800 s;
    a replay over the limit is a failed row that names the limit, not a crash of the suite."""
    import subprocess
    from core import testkit
    assert testkit.replay_timeout({}) == 1800
    assert testkit.replay_timeout({"timing": {"slowdown": 20}}) == 1800
    assert testkit.replay_timeout({"timing": {"replay_timeout_s": 600}}) == 1800      # the task's default: no tighter
    assert testkit.replay_timeout({"timing": {"replay_timeout_s": 3600}}) == 3600
    decl = {"formats": {"duel": {"seats": ["A", "B"], "first": ["A"]}}, "modes": {"action_levels": ["low"]},
            "timing": {"replay_timeout_s": 4321}}
    seen, run = [], subprocess.run

    def spy(cmd, **kw):
        seen.append(kw.get("timeout"))
        return run(cmd, **kw)
    testkit.subprocess.run = spy
    try:
        rows = testkit.t_determinism(SPORT_TURN, PLUGIN_TURN, decl)
        assert seen == [4321] and all(r["ok"] for r in rows), (seen, rows)

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        testkit.subprocess.run = slow
        rows = testkit.t_determinism(SPORT_TURN, PLUGIN_TURN, decl)
    finally:
        testkit.subprocess.run = run
    bad = {r["name"]: r for r in rows}["determinism:fresh_process_replay"]
    assert not bad["ok"] and "4321 s" in bad["detail"] and "replay_timeout_s" in bad["detail"], rows



def test_team_channel_reads_after_a_seq_never_consume():
    """core 0.2.20: every message has a per-side seq; reads with a read mark return each message after it once per
    read mark, any number of clients; without a read mark the recent window (recent_s game seconds, at most recent_max);
    POST /team pages through the log; the limits of say are unchanged."""
    from core.channel import TeamChannel
    cfg = MatchConfig(sport="fixture", format="team", seats=("A1", "A2", "B1", "B2"), seed=1,
                      sides={"A1": "A", "A2": "A", "B1": "B", "B2": "B"})
    ch = TeamChannel(cfg, {"max_bytes": 64, "min_interval_s": 0.2, "max_messages": 4, "recent_s": 1.0,
                           "recent_max": 2})
    dt = 0.02
    assert ch.say("A1", "a", 0, dt)[1]["sent"]["seq"] == 1
    assert ch.say("A1", "b", 5, dt)[0] == 429                       # 0.2 s between two messages of one seat
    assert ch.say("A2", "c", 5, dt)[1]["sent"]["seq"] == 2          # one seq per side
    assert ch.say("B1", "z", 5, dt)[1]["sent"]["seq"] == 1          # the other side counts its own
    assert ch.say("A1", "d", 10, dt)[1]["sent"]["seq"] == 3
    assert ch.say("A1", "e", 100, dt)[1]["sent"]["seq"] == 4
    for _ in range(3):                                              # never consumed
        msgs, top = ch.messages("A2", 100, dt, since=0)
        assert [m["text"] for m in msgs] == ["a", "d", "e"] and top == 4, (msgs, top)
    assert [m["seq"] for m in ch.messages("A2", 100, dt, since=3)[0]] == [4]
    assert ch.messages("A2", 100, dt, since=4)[0] == []
    assert [m["text"] for m in ch.messages("A2", 100, dt)[0]] == ["e"]         # recent: the last 1.0 s only
    assert [m["text"] for m in ch.messages("A2", 10, dt)[0]] == ["a", "d"]     # at step 10: both within 1 s, max 2
    assert [m["text"] for m in ch.messages("B2", 100, dt, since=0)[0]] == ["z"]
    assert ch.messages("A1", 100, dt, since=0)[0][0]["text"] == "c"            # A1 sees A2's only
    code, page = ch.page("A2", 100, 1)
    assert code == 200 and [m["seq"] for m in page["messages"]] == [3, 4] and page["team_seq"] == 4
    assert not page["more"]
    ch.page_max = 1
    assert ch.page("A2", 100, 0)[1]["more"] and len(ch.page("A2", 100, 0)[1]["messages"]) == 1
    assert ch.say("A1", "f", 200, dt)[0] == 200                     # A1's 4th message
    assert ch.say("A1", "g", 300, dt)[0] == 429                     # max_messages (4 per seat) unchanged
    off = TeamChannel(cfg, None)
    assert off.messages("A1", 0, dt) == ([], 0) and off.page("A1", 0, 0)[0] == 404


def test_team_channel_turn_protocol_and_http_since():
    """core 0.2.20: the turn protocol reads the channel the same way (status / wait / observe with team_since, POST
    /team), and an HTTP GET carries the read mark as ?team_since=N (anything but a small integer is a 400)."""
    from core.http import make_server
    sides = {"A1": "A", "A2": "A", "B1": "B", "B2": "B"}
    svc, post = turn_service(list(sides), sides, fmt="team")
    if not svc.channel.enabled:                                     # the turn fixture declares no channel
        svc.channel.declared = svc.channel.enabled = True
    assert post["say"]("A1", {"text": "hi"})[0] == 200
    get = svc.routes(False)
    st = get["status"]("A2", {})[1]["state"]
    assert [m["text"] for m in st["team_messages"]] == ["hi"] and st["team_seq"] == 1
    assert get["status"]("A2", {"team_since": 1})[1]["state"]["team_messages"] == []
    assert get["team"]("A2", {"since": 0})[1]["messages"][0]["from"] == "A1"
    srv = make_server(svc, tuple(sides), {}, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    import urllib.error
    import urllib.request

    def fetch(path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)
    try:
        code, out = fetch("/A2/status?team_since=0")
        assert code == 200 and out["state"]["team_messages"][0]["text"] == "hi", out
        code, out = fetch("/A2/status?team_since=1")
        assert code == 200 and out["state"]["team_messages"] == [], out
        assert fetch("/A2/status?team_since=-3")[0] == 400
        assert fetch("/A2/status?team_since=abc")[0] == 400
        code, out = fetch("/A2/team?since=0")
        assert code == 200 and out["messages"][0]["text"] == "hi", out
    finally:
        srv.shutdown()
        srv.server_close()


def test_requests_after_the_end_never_void_a_finished_match():
    """core 0.2.26: once a match is over, observe / act answer 409 with the final state and draw nothing (realtime and
    turn); after finalization the render workers are closed, so a late draw returns no images and a late request's
    failure is only logged: a player that keeps observing after the end (713 broken pipes in a four-seat match)
    never voids the finished, replayed match."""
    svc, post = service(["A", "B"], fmt="duel")
    fin = run_all(svc, post, ["A", "B"])
    assert fin["valid_trial"] and svc.finalized, fin["errors"]

    class Closed:                                  # a render worker after finalize(): every call is a broken pipe
        lock = threading.Lock()

        def call(self, job, wait=True):
            raise BrokenPipeError(32, "Broken pipe")

        def close(self):
            pass
    svc.workers["render", "A"] = Closed()
    code, out = post["observe"]("A", {})
    assert code == 409 and out["error"] == "the match is over" and out["now"]["done"], (code, out)
    assert "observation" not in out
    code, out = post["act"]("A", {"type": "move", "v": 0.5})
    assert code == 409 and out["now"]["done"], (code, out)
    assert svc.draw("A", {"state": {}, "cams": []}) is None                  # finalized: nothing drawn
    svc.failure("observe", BrokenPipeError(32, "Broken pipe"))               # what core/http.py reports
    with svc.cond:
        svc.write_final()
    fin2 = json.loads((svc.data / "final.json").read_text())
    assert fin2["valid_trial"] and not fin2["technical_failure"] and fin2["errors"] == fin["errors"], fin2
    assert fin2["winner"] == fin["winner"] and svc.phase == "over"

    tsvc, tpost = turn_service(["A", "B"])
    th = [threading.Thread(target=play_turn, args=(tsvc, tpost, s), daemon=True) for s in ("A", "B")]
    for t in th:
        t.start()
    tfin = finish(tsvc)
    assert tfin["valid_trial"], tfin["errors"]
    for ep in ("observe", "act"):
        code, out = tpost[ep]("A", {"v": 0.5} if ep == "act" else {})[:2]
        assert code == 409 and out["error"] == "the match is over" and out["state"]["done"], (ep, code, out)

if __name__ == "__main__":
    sys.exit(main())
