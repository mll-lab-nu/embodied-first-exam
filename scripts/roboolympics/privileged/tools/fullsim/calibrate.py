"""Calibrate a full-state program against the scripted opponent's levels, in process (the world waits for the program).

    python -m tools.fullsim.calibrate --sport badminton --program tools/fullsim/oracles/badminton.py \
        --levels 1-4 --seeds 1-40 --jobs 8 [--delay D] --out /tmp/bm-priv-calib.json

Each match: a fresh Session(sport, level, seed); the program gets the formal runner's view every EVERY control steps
(the adapter's; and at every point review) and its commands take effect at once (or `--delay` steps later). This is the step timing, not the formal S = 10 wall clock;
use it to compare players on paired seeds (e.g. the full-state reference with the camera-only reference player of
the screening, docs/construction_zh.md step 4), not as a formal result. No replay, no subprocess per match.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def ints(text):
    out = []
    for part in str(text).split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def load(path):
    spec = importlib.util.spec_from_file_location(f"calib_program_{os.getpid()}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).resolve().parent))
    spec.loader.exec_module(mod)
    return mod


def one(job):
    sport, program, level, seed, max_steps, delay = job
    from core.outcome import decide
    from core.sport import FINISHED, UNIT_OVER, Refused
    from tools.fullsim.formal import commands_of
    from tools.fullsim.session import Session, plugin

    t0 = time.monotonic()
    s = Session(sport, level=level, seed=seed)
    sys.path.insert(0, str(Path(plugin(s.ad.SPORT).__file__).parent))  # the oracle's builtin_players
    every = s.ad.EVERY
    policy = load(program).make_policy(
        {"spec": s.spec(), "setting": "calibrate-step", "max_commands": s.ad.MAX_COMMANDS}
    )
    refused = calls = 0
    no_ready = False
    while s.match.phase().state != FINISHED and s.match.k < max_steps:
        phase = s.match.phase().state
        st = s.state()
        view = {
            "state": st["state"],
            "truth": st["truth"],
            "scores": st["scores"],
            "observation": {},
        }
        cmds = commands_of(policy.act(view), s.ad.MAX_COMMANDS)
        calls += 1
        if delay and cmds and cmds[0].get("type") != "ready":  # they take effect `delay` steps after the state
            s.step(delay)
            if s.match.phase().state != "playing":
                continue
        for cmd in cmds:
            try:
                if cmd.get("type") == "ready":
                    if phase == UNIT_OVER:
                        s.ready()
                else:
                    s.act(cmd)
            except (Refused, ValueError, TypeError, KeyError):
                refused += 1
        if s.match.phase().state == UNIT_OVER:
            if phase == UNIT_OVER and not cmds:
                # the formal match would forfeit this side after READY_TIMEOUT_S; here it ends as unfinished
                no_ready = True
                break
            continue
        s.step(every)
    sc = s.match.scores()
    finished = s.match.phase().state == FINISHED
    # the referee's winner (its tiebreaks: a soccer shoot-out ends level on goals), as the grader decides it
    winner = decide(s.match, None, None, s.cfg.side_list(), s.cfg.side_of).winner if finished else None
    return {
        "level": level,
        "seed": seed,
        "delay": delay,
        "A": sc.get("A"),
        "opp": sc.get("opponent"),
        "win": bool(finished and winner == "A"),
        "winner": winner,
        "finished": finished,
        "steps": s.match.k,
        "state_sha": s.match.state_digest(),
        "calls": calls,
        "refused": refused,
        "no_ready": no_ready,
        "wall_s": round(time.monotonic() - t0, 2),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", required=True)
    p.add_argument("--program", required=True)
    p.add_argument("--levels", default="1-4")
    p.add_argument("--seeds", default="1-40")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--max-steps", type=int, default=20000)
    p.add_argument("--delay", type=int, default=0, help="effect delay D in control steps (the screening used 5)")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    program = str(Path(a.program).resolve())
    jobs = [(a.sport, program, lv, sd, a.max_steps, a.delay) for sd in ints(a.seeds) for lv in ints(a.levels)]
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one, jobs))
    table = {}
    for lv in ints(a.levels):
        rs = [r for r in rows if r["level"] == lv]
        pts = sum(r["A"] for r in rs), sum(r["opp"] for r in rs)
        table[lv] = {
            "wins": sum(r["win"] for r in rs),
            "n": len(rs),
            "point_share": round(pts[0] / max(1, sum(pts)), 3),
        }
    Path(a.out).write_text(
        json.dumps(
            {"program": a.program, "sport": a.sport, "timing": "step", "delay": a.delay, "table": table, "rows": rows},
            indent=1,
        )
    )
    print(json.dumps(table))


if __name__ == "__main__":
    main()
