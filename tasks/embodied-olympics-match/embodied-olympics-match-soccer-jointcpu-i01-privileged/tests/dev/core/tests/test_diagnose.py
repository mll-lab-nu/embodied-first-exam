"""Tests of the diagnostic records (core/diaglog.py, core 0.2.25) and the post-match diagnosis (core/diagnose.py):
in-process matches (core/local.py) of the realtime fixture and the live realtime service (a turn-protocol
example: the example sport's tests/test_diagnose.py). Run in the sim image:
    docker run --rm -v $PWD:/w -w /w -e MUJOCO_GL=osmesa ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0 \\
        python3 core/tests/test_diagnose.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import test_core as tc  # noqa: E402  (service helpers; sets the short timeouts)
from core import diagnose, local  # noqa: E402
from core.episode import load_plugin, read_rows, replay  # noqa: E402
from core.sport import MatchConfig  # noqa: E402



class Mover:
    """A fixture player: every observation, move entity e0 (and e1 every other time)."""

    def __init__(self, v=0.3):
        self.v, self.n = v, 0

    def act(self, view):
        self.n += 1
        return {"type": "move", "v": self.v if self.n % 2 else -self.v, "entity": "e0" if self.n % 3 else "e1"}


def fixture_local(delay=0):
    os.environ["FIXTURE_DELAY"] = str(delay)
    try:
        cfg = MatchConfig(sport="fixture", format="duel", seats=("A", "B"), seed=1)
        d = Path(tempfile.mkdtemp(prefix="diag-fx-"))
        res = local.play(tc.SPORT, cfg, {"A": Mover(0.3), "B": Mover(-0.2)}, data=d, render=False,
                         plugin=tc.PLUGIN, every=4)
        return d, res
    finally:
        os.environ.pop("FIXTURE_DELAY", None)


def test_local_rows_link_every_act():
    d, res = fixture_local()
    rep = diagnose.load(d, tc.PLUGIN)
    assert rep["interface"] == diagnose.INTERFACE and all(rep["has"][n] for n in ("observe", "act_received",
                                                                                   "effect", "event"))
    link = diagnose.linkage(rep)
    for seat in ("A", "B"):
        L = link[seat]
        assert L["acts"] > 10 and L["act_ids_contiguous"], L
        assert L["with_observation"] == L["acts"] and L["effect"] == L["acts"] == L["effect_with_cmd"], L
        assert L["unresolved"] == 0 and L["both"] == 0, L
        for a in rep["acts"][seat]:
            assert a["k_obs"] == a["k_recv"] == a["k_effect"] and a["view_steps"] == [], a
    # events: one per unit end, with the step at which the unit ended
    assert [e["k"] for e in rep["events"]] == [30, 60, 90], rep["events"]
    # the replay rows are unchanged by the diagnostic rows: the fresh replay gives the local result
    sport = load_plugin(tc.PLUGIN)
    assert replay(sport, read_rows(d / "episode.jsonl"))["state_sha"] == res["digest"]


def test_local_delayed_effects_and_drops():
    d, _ = fixture_local(delay=3)
    rep = diagnose.load(d, tc.PLUGIN)
    link = diagnose.linkage(rep)
    for seat in ("A", "B"):
        L = link[seat]
        assert L["unresolved"] == 0 and L["both"] == 0 and L["dropped"] > 0, L
        assert set(L["dropped_by"]) <= {"unit_over", "match_over"}, L
        for a in rep["acts"][seat]:
            if a["k_effect"] is not None:
                assert a["k_effect"] == a["k_recv"] + 3, a


def test_world_at_matches_the_replay():
    d, res = fixture_local(delay=2)
    rep = diagnose.load(d, tc.PLUGIN)
    w = rep["world"]()
    m = w.at(45)
    assert m.k == 45
    pos45 = dict(m.pos)
    w.at(90)
    assert w.k == 90
    assert w.at(45).pos == pos45                      # backwards: rebuilt, same state
    w2 = rep["world"]()
    assert w2.run().state_digest() == res["digest"]
    assert sorted(w2.events) == [30, 60, 90]
    # before / after the rows of a step: an effect at step k changes the velocity, not yet the position
    a = next(a for a in rep["acts"]["A"] if a["k_effect"] is not None and a["k_effect"] > 5)
    pre = rep["world"]().at(a["k_effect"])
    post = rep["world"]().at(a["k_effect"], after=True)
    key = f"A.{a['decision']['entity']}"
    assert post.vel[key] == a["cmd"]["v"] and pre.pos == post.pos


def test_turn_service_rows():
    svc, post = tc.turn_service(["A", "B"])

    def loop(seat):
        post["start"](seat, {})
        while svc.phase != "over":
            st = post["wait"](seat, {"timeout_s": 1})[1]["state"]
            if st["done"] or not st["your_turn"]:
                continue
            if st["awaiting_review"]:
                post["ready"](seat, {"why": "w", "plan": "p"})
            else:
                post["observe"](seat, {})
                post["act"](seat, {"v": 0.5})
    th = [threading.Thread(target=loop, args=(s,), daemon=True) for s in ("A", "B")]
    for t in th:
        t.start()
    final = tc.finish(svc)
    assert final["valid_trial"], final
    rep = diagnose.load(svc.data, tc.PLUGIN_TURN)
    link = diagnose.linkage(rep)
    for seat in ("A", "B"):
        L = link[seat]
        assert L["acts"] > 0 and L["with_observation"] == L["acts"] == L["effect"] == L["effect_with_cmd"], L
        for a in rep["acts"][seat]:
            assert a["k_obs"] == a["k_recv"] == a["k_effect"], a
    w = rep["world"]()
    assert w.run().state_digest() == final["state_sha"]


def test_service_rows_link_acts_effects_and_team_delivery():
    sides = {"A1": "home", "A2": "home", "B1": "away", "B2": "away"}
    os.environ["FIXTURE_DELAY"] = "2"
    try:
        svc, post = tc.service(list(sides), sides)
    finally:
        os.environ.pop("FIXTURE_DELAY", None)
    said = []

    def act(seat, post):
        post["observe"](seat, {})
        post["act"](seat, {"type": "move", "v": 0.2, "entity": "e0"})
        if seat == "A1" and not said and svc.phase == "running":
            said.append(post["say"](seat, {"text": "go"})[0])
    final = tc.run_all(svc, post, list(sides), **{s: {"act": act} for s in sides})
    assert final["valid_trial"], final
    rep = diagnose.load(svc.data, tc.PLUGIN)
    link = diagnose.linkage(rep)
    for seat in sides:
        L = link[seat]
        assert L["acts"] > 0 and L["act_ids_contiguous"] and L["unresolved"] == 0 and L["both"] == 0, (seat, L)
        assert L["with_observation"] == L["acts"], (seat, L)
        assert L["effect"] == L["effect_with_cmd"], (seat, L)
        for a in rep["acts"][seat]:
            if a["k_effect"] is not None:
                assert a["k_effect"] - a["k_recv"] >= 2 and a["k_obs"] <= a["k_recv"], a
    # the reaction report (core 0.2.23) agrees with the act rows: acts with an effect = the report's acts
    rr = final["reaction"]["by_seat"]
    for seat in sides:
        assert rr[seat]["acts"] == link[seat]["effect"], (rr[seat], link[seat])
    assert [e["k"] for e in rep["events"]] == [30, 60, 90]
    if said == [200]:
        got = [r for r in rep["team_delivered"] if r["from"] == "A1"]
        assert [r["seat"] for r in got] == ["A2"], got          # the teammate, once; never the other side
        assert got[0]["k"] >= got[0]["sent_k"]
    # the diagnostic rows are not replayed: the fresh replay of the service's episode passed
    assert final["deterministic"]


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    bad = 0
    for name, f in tests:
        t = time.time()
        try:
            f()
            print(f"ok   {name} ({time.time() - t:.1f} s)")
        except Exception:  # noqa: BLE001
            import traceback
            bad += 1
            print(f"FAIL {name}\n{traceback.format_exc()}")
    print(f"{len(tests) - bad}/{len(tests)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
