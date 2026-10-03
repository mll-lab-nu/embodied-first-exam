#!/usr/bin/env python3
"""One round of a sport's Olympiad experiments (one seed for everything), scheduled over model-account lanes.

    python3 scripts/olympiad/run_round.py <round 1|2|3> [--sport tabletennis] [--results DIR] [--dry] [--missing]
                                          [--lanes opus,fable,astra,luna] [--slowdown S]
                                          [--players opus,fable,astra,luna]

The sport's `EXPERIMENT` (scripts/olympiad/<sport>/spec.py) gives the tasks and official seeds. Round r uses, for every
level, the level's r-th official seed and the r-th duel seed. Matches:
  * single player: every level x players opus, fable, astra, luna;
  * duels: every pair of the four players, both seat orders (the first player/receiver is seat A).
Real-time sports run at --slowdown (default 10, the main experiment); turn-based sports have none.
Lanes (account limits): `astra` two at a time (one Azure key, failover over three deployments; every match with Astra in it), `opus` two (the
second Claude subscription, see run_single.sh: Opus matches and duels with Opus but without Astra), `fable` one (the
first Claude subscription, shared with coding: Fable singles and Fable-luna duels), `luna` two (OpenRouter). Run the
lanes of one round on several hosts by splitting --lanes. A match that ends as a technical failure (or without a
result) is run once more. One line per finished match in <results>/<sport>-round<r>.jsonl (outside the repository:
PROTOCOL D3). --missing runs only the matches without a valid result in that file yet. A match whose model calls were
refused with HTTP 429 (an account limit) waits 30 minutes and is run again without counting the attempt (at most
8 hours). Needs HARBOR (the multi-seat Harbor) in the environment or on PATH.
"""
import argparse
import ast
import importlib.util
import itertools
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAYERS = ["opus", "fable", "astra", "luna"]
LANES = {"astra": 2, "opus": 2, "fable": 1, "luna": 2}


def experiment(sport):
    """The sport's EXPERIMENT dict (its spec.py, imported with the sport directory and scripts/olympiad on the path)."""
    here = ROOT / "scripts/olympiad"
    sys.path[:0] = [str(here / sport), str(here)]
    spec = importlib.util.spec_from_file_location(f"olympiad_{sport}_spec", here / sport / "spec.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.EXPERIMENT


def lane_of(players):
    if "astra" in players:
        return "astra"
    if "opus" in players:
        return "opus"
    if "fable" in players:
        return "fable"
    return "luna"


def matches(r, sport, slowdown, players=PLAYERS):
    ex = experiment(sport)
    single, duel = ex["single"], ex["duel"]
    sd = ["--slowdown", str(slowdown)] if single.get("slowdowns") else []
    dsd = ["--slowdown", str(slowdown)] if duel.get("slowdowns") else []
    out = []
    for level, seeds in sorted(single["seeds"].items()):
        seed = seeds[r - 1]
        for p in players:
            out.append(dict(sport=sport, kind="single", player=p, level=level, seed=seed, lane=lane_of([p]),
                            cmd=["scripts/olympiad/run_single.sh", "--task", single["task"], "--agent", p,
                                 "--level", str(level), *sd, "--seed", str(seed), "--tag", f"r{r}"]))
    dseed = duel["seeds"][r - 1]
    for x, y in itertools.combinations(players, 2):
        for a, b in ((x, y), (y, x)):
            out.append(dict(sport=sport, kind="duel", a=a, b=b, seed=dseed, lane=lane_of([a, b]),
                            cmd=["scripts/olympiad/run_duel.sh", "--task", duel["task"], "--a", a, "--b", b, *dsd,
                                 "--seed", str(dseed), "--first", "A", "--tag", f"r{r}"]))
    return out


def key(m):
    return (m["kind"], m.get("player"), m.get("level"), m.get("a"), m.get("b"), m["seed"])


def rate_limited(job):
    """Whether a model call of this job was refused with HTTP 429 (an account limit, not the player's fault)."""
    for f in (ROOT / "jobs" / job).glob("*/artifacts/data/think_calls*.jsonl"):
        for line in open(f):
            if '"status": 429' in line:
                return True
    return False


def run(m, log):
    attempt, waits = 0, 0
    while attempt < 2:
        attempt += 1
        t0 = time.time()
        p = subprocess.run(m["cmd"], cwd=ROOT, capture_output=True, text=True)
        line = (p.stdout.strip().splitlines() or [""])[-1]
        job, _, res = line.partition(": ")
        try:
            reward = ast.literal_eval(res) if res.startswith("{") else None   # the run script prints a dict literal
        except Exception:  # noqa: BLE001
            reward = None
        rec = {k: v for k, v in m.items() if k != "cmd"} | dict(attempt=attempt, job=job, reward=reward,
                                                                 minutes=round((time.time() - t0) / 60, 1))
        with LOCK:
            with open(log, "a") as f:
                f.write(json.dumps(rec) + "\n")
        if reward and reward.get("valid_trial") == 1:
            return
        if job and rate_limited(job) and waits < 16:      # account limit: wait for the reset, don't count the attempt
            waits += 1
            attempt -= 1
            time.sleep(1800)
        # otherwise a technical failure (or no result): once more


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("round", type=int, choices=(1, 2, 3))
    ap.add_argument("--results", default=str(ROOT.parent / "olympiad_results"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--lanes", default=",".join(LANES), help="run only these lanes")
    ap.add_argument("--sport", default="tabletennis")
    ap.add_argument("--slowdown", type=int, default=10, help="real-time sports only")
    ap.add_argument("--players", default=",".join(PLAYERS), help="the players of this sport (singles and their duels)")
    a = ap.parse_args()
    ms = [m for m in matches(a.round, a.sport, a.slowdown, a.players.split(",")) if m["lane"] in a.lanes.split(",")]
    log = os.path.join(a.results, f"{a.sport}-round{a.round}.jsonl")
    if a.missing and os.path.exists(log):
        done = set()
        for line in open(log):
            r = json.loads(line)
            if (r.get("reward") or {}).get("valid_trial") == 1:
                done.add(key(r))
        ms = [m for m in ms if key(m) not in done]
    if a.dry:
        for m in ms:
            print(m["lane"], " ".join(m["cmd"]))
        print(len(ms), "matches")
        return
    os.makedirs(a.results, exist_ok=True)
    qs = {lane: queue.Queue() for lane in LANES}
    for m in ms:
        qs[m["lane"]].put(m)

    def worker(lane):
        while True:
            try:
                m = qs[lane].get_nowait()
            except queue.Empty:
                return
            run(m, log)
            time.sleep(20)            # stagger starts (image builds, model logins)

    threads = [threading.Thread(target=worker, args=(lane,)) for lane, n in LANES.items() for _ in range(n)]
    for i, t in enumerate(threads):
        t.start()
        time.sleep(15)
    for t in threads:
        t.join()
    print(f"round {a.round} done: {log}")


LOCK = threading.Lock()

if __name__ == "__main__":
    main()
