"""Tests of the RoboOlympics adapter (shared/sim/rcb_olympics.py) on the rendered tasks; they need the simulator, so they
run in the eai-olympiad image, one task at a time (the task's sim directory mounted at /srv):

    for t in tasks/roboolympics-*; do docker run --rm -v $PWD/$t/environment/sim:/srv:ro \
      -v $PWD/scripts/roboolympics:/gen:ro -e TASK=$(basename $t) ghcr.io/mll-lab-nu/eai-olympiad:0.2.0 \
      python /gen/tests/test_adapter.py; done

  - the interface the instruction documents (sports.toml: the action types, every proprio column) is the service's;
  - /spec is JSON and clip() keeps any finite row inside the limits without raising;
  - a session of random commands through to_sim/step (the realtime service's path) replays bit-exactly from its
    record in a fresh process (verify) and after a simulated crash (a new adapter reading the same commands table);
  - a break: the match stands still, a `ready` row ends it, otherwise it ends by itself after BREAK_S;
  - the realtime service's plan with the sport's action types mixed (rcb_realtime.RealtimeService on this adapter, its
    clock driven by hand): every command is issued once, at its step, and the match never ends on a simulator error.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import tomllib

import numpy as np

sys.path.insert(0, "/srv")
TASK = os.environ["TASK"]
SPORT = TASK.split("-")[1]
os.environ.update(RO_SPORT=SPORT, RO_FORMAT={"badminton": "match-wallclock"}.get(SPORT, "match"),
                  RO_ACTION_LEVEL="low" if SPORT == "airhockey" else "high", RCB_SLOWDOWN="10")
DOCS = tomllib.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sports.toml"), "rb"))[SPORT]


def build(data):
    os.environ["RCB_DATA"] = data
    import server
    return server.build()


def documented_columns(text: str) -> set[str]:
    out = set()
    for stem, a, b in re.findall(r"`([a-z_]+?)(\d+)`\.\.`[a-z_]+?(\d+)`", text):     # `q1`..`q7`
        out.update(f"{stem}{i}" for i in range(int(a), int(b) + 1))
    for tok in re.findall(r"`([a-z0-9_/.]+)`", text):
        if "/" in tok:                                    # paddle_x/y/z, q_striker1/2
            head, *rest = tok.split("/")
            stem = head[:-len(rest[0])] if head.endswith(tuple("xyz0123456789")) else head
            out.update([head] + [stem + r for r in rest])
        else:
            out.add(tok)
    return out


def test_interface(sim):
    spec = json.loads(json.dumps(sim.spec()))
    documented = re.findall(r"^\| `(\w+)` \|", DOCS["actions"], re.M)
    assert sorted(documented) == sorted(spec["action_types"]), (documented, list(spec["action_types"]))
    cols = documented_columns(DOCS["proprio"])
    missing = [c for c in sim.proprio_layout if c not in cols]
    assert not missing, f"proprio columns the instruction does not name: {missing}"
    assert len(sim.proprio()) == len(sim.proprio_layout)
    for typ, t in sim.profile.types.items():
        rows = np.random.default_rng(0).uniform(-50, 50, (20, int(t["dim"])))
        out, clipped = sim.clip(typ, rows)
        assert np.all(np.isfinite(out)) and out.shape == rows.shape, typ
    for typ in sim.profile.types:                         # command() of a type that is no target: no command
        if typ not in sim.profile.interp:
            assert list(sim.to_sim(typ, sim.command(typ))) == [-1.0, 0.0], typ
    assert list(sim.to_sim(*sim.hold())) == [-1.0, 0.0]   # a held step (the plan ran out, or a gap in it): no command
    assert sim.refused == 0 and not sim.commands
    print("interface ok:", list(spec["action_types"]), len(sim.proprio_layout), "proprio columns")


def random_row(sim, typ, rng):
    if typ == "stroke":
        return [rng.uniform(0.2, 1.0), rng.uniform(-0.5, 0.5), rng.uniform(-1.6, -1.0), rng.uniform(0.2, 0.5),
                0.0, 1.0, 0.2, 0.0, rng.uniform(0.5, 2.0), 0.5]
    if typ == "mallet":
        return [rng.uniform(-0.9, -0.1), rng.uniform(-0.4, 0.4)]
    if typ == "toss":
        return [0.3, -3.6, 1.0, 0.0]
    return [0.0]


def session(sim, n, rng, ready_every=None):
    """Drive the adapter the way rcb_realtime's tick does: one row (a command now and then, else hold) per step."""
    rows = []
    types = [t for t in sim.profile.types if t != "ready"]
    for k in range(n):
        if ready_every and sim.in_break and rng.random() < 1.0 / ready_every:
            typ, row = "ready", [1.0]
        elif rng.random() < (0.3 if SPORT == "airhockey" else 0.02):
            typ = rng.choice(types)
            row = random_row(sim, typ, rng)
            row = sim.clip(typ, np.asarray([row], float))[0][0]
        else:
            typ, row = sim.hold()
        r = sim.to_sim(typ, np.asarray(row, float))
        rows.append(r)
        done, _, _ = sim.step(r)
        if done:
            break
    return np.asarray(rows)


def test_replay_and_resume():
    data = tempfile.mkdtemp()
    sim = build(data)
    rng = np.random.default_rng(1)
    rows = session(sim, 2500, rng, ready_every=30)
    live = sim.state_sha()
    rep = sim.verify(rows)
    assert rep["state_sha"] == live, "fresh-process replay differs from the live run"
    again = build(data)                                  # a crash: a new process reads the same commands table
    for r in rows:
        again.step(r)
    assert again.state_sha() == live, "resume replay differs from the live run"
    m = json.load(open(os.path.join(data, "match.json")))
    print(f"replay ok: {len(rows)} steps, {sim.applied} commands applied, {sim.refused} refused, "
          f"{len(sim.breaks)} breaks, score {m['scores']}")


def test_break():
    sim = build(tempfile.mkdtemp())
    for _ in range(200000):                               # hold until the first unit ends
        sim.step(sim.to_sim(*sim.hold()))
        if sim.in_break or sim.finished:
            break
    assert sim.in_break, "no unit ended"
    k = sim.m.k
    for _ in range(10):
        sim.step(sim.to_sim(*sim.hold()))
    assert sim.in_break and sim.m.k == k, "the match moved during the break"
    sim.step(sim.to_sim("ready", np.array([1.0])))
    assert not sim.in_break and sim.breaks[-1]["by"] == "ready"
    for _ in range(200000):
        sim.step(sim.to_sim(*sim.hold()))
        if sim.in_break or sim.finished:
            break
    if sim.in_break:
        n = 0
        while sim.in_break:
            sim.step(sim.to_sim(*sim.hold()))
            n += 1
        assert n == sim.break_steps and sim.breaks[-1]["by"] == "time", (n, sim.break_steps)
    print(f"break ok: {sim.break_steps} steps ({sim.break_steps * sim.control_dt:g} s of game time)")


def test_mixed_plan(rounds: int = 60):
    """The agent's ordinary play through the realtime service: commands of every action type of the sport, sent back to
    back with `at` a few steps ahead while the others are still planned (badminton: a toss, then the stroke; air
    hockey: a stop, then a mallet target), and commands sent for a step before what is planned. Until 2026-10-10 the
    plan combined rows of different types (a chunk interpolated from, and filled the gap before `at` with, whatever row
    was planned there): numpy could not broadcast a 4-value toss against a 10-value stroke (a 500), a one-value `stop`
    row went to the simulator as a `mallet` target (IndexError at its step), and a command was issued again at every
    step of a gap. The first two ended the match "error": infra_error = 1 on a legal sequence of commands."""
    import rcb_realtime
    data = tempfile.mkdtemp()
    sim = build(data)
    svc = rcb_realtime.RealtimeService(sim, data=data, slowdown=1000.0)   # the clock is driven by hand: tick()
    svc.start()
    rng = np.random.default_rng(2)
    types = [t for t in sim.profile.types if t != "ready"]
    sent = 0

    def submit(typ, ahead):
        nonlocal sent
        body = {"type": typ, "actions": [random_row(sim, typ, rng)], "at": len(svc.episode) + ahead, "cameras": []}
        job = rcb_realtime._Job("POST", "/submit", json.dumps(body).encode())
        svc.dispatch(job)
        assert job.reply[0] == "rec", (typ, ahead, job.reply)             # 200: an RCB1 answer, not a 4xx / 5xx
        sent += 1

    for _ in range(rounds):
        if svc.done:
            break
        order = [str(t) for t in rng.permutation(types)]
        for i, typ in enumerate(order):                   # every pair of types meets in the plan, a gap between them
            submit(typ, 3 * i + (0 if i == 0 else int(rng.integers(1, 3))))
        if rng.random() < 0.5:
            submit(order[0], 1)                           # earlier than what is planned: replaces the plan from there
        for _ in range(3 * len(types) + 4):
            if not svc.done:
                svc.tick()
        assert svc.reason != "error", "the match ended on a simulator error"
    with open(os.path.join(data, "commands.jsonl")) as f:
        issued = [json.loads(line) for line in f]
    assert len(issued) <= sent, f"{len(issued)} commands issued for {sent} rows sent: a row was issued more than once"
    assert len({(c["step"], c["type"]) for c in issued}) == len(issued), "two commands of one type at one step"
    svc.on_sigusr1()
    svc.poll()
    with open(os.path.join(data, "final.json")) as f:
        fin = json.load(f)
    assert fin["finalized"] and fin["deterministic"] and "infra_error" not in fin and fin["reason"] != "error", fin
    assert fin["video_pending"] is False, fin
    print(f"mixed plan ok: {sent} rows of {types} sent, {len(issued)} commands issued ({sim.applied} applied, "
          f"{sim.refused} refused), {len(svc.episode)} control steps, reason {fin['reason']}, video {fin['video']}")


if __name__ == "__main__":
    test_interface(build(tempfile.mkdtemp()))
    test_break()
    test_replay_and_resume()
    test_mixed_plan()
    print(TASK, "all tests passed")
