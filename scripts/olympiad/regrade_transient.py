#!/usr/bin/env python3
"""Re-grade finished Olympiad trials under the model-API validity rule of 2026-10-03 (scripts/olympiad/api_errors.py).

    python3 scripts/olympiad/regrade_transient.py [--write] [--json] <trial_dir or job_dir>...

Before the rule, any failed model call or 429 retry of a seat made the trial a technical failure (proxy_error). Now an
error the harness recovered from (a later model call of the same seat completed) is only counted; the model API fails
the trial only if a seat had an unrecovered error or more than MAX_TRANSIENT_API_ERRORS transient ones.

For each trial the tool
  1. classifies every seat's calls from the trial's own think_calls*.jsonl (and think_usage*.json counters);
  2. patches a COPY of final.json the way the service now writes it: proxy_error := api_failure (per seat in a duel),
     transient_api_errors / unrecovered_api_errors, and the fields the service derives from proxy_error (the duel
     services' valid_trial / technical_failure and the winner they leave out of an invalid match; the single services'
     valid_trial) - only when proxy_error was the only reason the service gave;
  3. runs the task's own grader (tasks/<task>/tests/grade.py, i.e. the current generated grader) on the patched copy and
     prints the reward before (as recorded) and after. Every other validity condition (deterministic replay, the match
     over and finalized, no simulator / metering / replay / grader error, start and clock forfeits) is the grader's, so
     a trial that was invalid for any other reason stays invalid.
A trial is skipped when it has no recorded reward or when the grader on its unpatched final.json does not reproduce the
recorded reward (older task revision): then the difference would not be the API rule's alone.
The original trial files are never modified. With --write, the new reward goes to <trial>/verifier/reward_regraded.json.
Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from api_errors import classify_file, MAX_TRANSIENT_API_ERRORS  # noqa: E402

SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
# Duel services that compute valid_trial (and drop the winner of an invalid match): what "complete" means for each,
# from their write_final (scripts/olympiad/<sport>/duel/environment/sim/server_duel.py).
DUEL_COMPLETE = {
    "archery": lambda d: d.get("reason") in ("match_over", "clock", "abandoned"),
    "basketball": lambda d: d.get("reason") in ("match_over", "clock", "abandoned"),
    "darts": lambda d: d.get("reason") in ("match_over", "clock", "abandoned"),
    "billiards": lambda d: d.get("reason") in ("match_over", "clock_expired") or (
        d.get("reason") == "start_timeout" and d.get("forfeiting") in SIDES),
    "curling": lambda d: d.get("reason") in ("match_over", "clock_expired") or (
        d.get("reason") == "start_timeout" and d.get("forfeiting") in SIDES),
    "tabletennis": lambda d: d.get("reason") == "match_over" or (
        d.get("reason") == "ready_timeout" and d.get("forfeiting") in SIDES),
    "badminton": lambda d: d.get("reason") == "match_over" or (
        d.get("reason") == "ready_timeout" and d.get("forfeiting") in SIDES),
    "tennis": lambda d: d.get("reason") in ("match_over", "match_limit") or (
        d.get("reason") == "ready_timeout" and d.get("forfeiting") in SIDES),
    "baseball": lambda d: d.get("reason") == "game_over" or (
        d.get("reason") == "ready_timeout" and d.get("forfeiting") in SIDES),
}
SINGLE_FLAGS = ("replay_error", "sim_error", "meter_error", "timing_invalid")


def duel_winner(sport: str, d: dict, r: dict):
    """The winner the duel service would have recorded for a valid match (it records None for an invalid one)."""
    if sport in ("archery", "basketball", "darts"):
        return d.get("match_winner")
    if d.get("forfeiting") in SIDES:
        return OTHER[d["forfeiting"]]
    if sport in ("billiards", "curling"):
        return r.get("winner") if d.get("reason") == "match_over" else None
    if sport in ("tabletennis", "badminton"):
        return r.get("winner")
    a, b = d["score"]["A"], d["score"]["B"]
    if a != b:
        return "A" if a > b else "B"
    if sport == "tennis":       # tn.match_winner: the last point that was not a let, else who did not receive first
        won = [p.get("winner") for p in d.get("points") or [] if p.get("winner") in SIDES]
        return won[-1] if won else ("A" if d.get("first_receiver") == "B" else "B")
    if sport == "baseball":     # bbduel.Duel.winner: level -> the winner of the last pitch
        log = d.get("pitch_log") or []
        if not log:
            return None
        last = log[-1]
        return last["batter"] if last.get("plate_appearance_result") in ("walk", "single", "double", "home run") \
            else last["pitcher"]
    return None


def trials(paths):
    for p in map(Path, paths):
        if (p / "artifacts").is_dir():
            yield p
        else:
            subs = sorted(q for q in p.iterdir() if (q / "artifacts").is_dir()) if p.is_dir() else []
            if not subs:
                print(f"{p}: not a trial or job directory", file=sys.stderr)
            yield from subs


def seat_files(data: Path, seat: str | None):
    """A duel seat's think_calls / think_usage files (a single-seat task with per-seat fields uses the plain names)."""
    if seat and ((data / f"think_calls_{seat}.jsonl").exists() or (data / f"think_usage_{seat}.json").exists()):
        return data / f"think_calls_{seat}.jsonl", data / f"think_usage_{seat}.json"
    return data / "think_calls.jsonl", data / "think_usage.json"


def load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def run_grader(grader: Path, data: Path, final: dict | None) -> dict:
    """The task's grader on the trial's data (final.json replaced by `final` when given), in a scratch copy."""
    with tempfile.TemporaryDirectory() as tmp:
        tdata, tlog = Path(tmp) / "data", Path(tmp) / "log"
        tdata.mkdir()
        for f in data.iterdir():
            if f.is_file() and not (final is not None and f.name == "final.json"):
                os.symlink(f.resolve(), tdata / f.name)
        if final is not None:
            (tdata / "final.json").write_text(json.dumps(final))
        env = dict(os.environ, RCB_DATA=str(tdata), RCB_LOG=str(tlog))
        p = subprocess.run([sys.executable, str(grader)], env=env, capture_output=True, text=True, timeout=600)
        out = load(tlog / "reward.json")
        if out is None:
            raise RuntimeError(f"grader wrote no reward.json: {p.stderr[-2000:]}")
        if out.get("grader_error"):
            out["_grader_stderr"] = p.stderr[-1500:]
        return out


def regrade(trial: Path) -> dict:
    cfg = load(trial / "config.json", {})
    task = Path((cfg.get("task") or {}).get("path", "")).name
    grader = ROOT / "tasks" / task / "tests" / "grade.py"
    if not task or not grader.exists():
        raise RuntimeError(f"unknown task {task!r} (no {grader})")
    sport = task.split("-")[0]
    data = trial / "artifacts" / "data"
    d0 = load(data / "final.json")
    if d0 is None:
        raise RuntimeError(f"no final.json in {data}")
    before = load(trial / "verifier" / "reward.json")
    if before is None:
        raise RuntimeError("no recorded verifier/reward.json (the trial was never graded): not re-graded")
    duel_dict = isinstance(d0.get("proxy_error"), dict)
    seats = list(d0["proxy_error"]) if duel_dict else [None]
    api = {}
    for s in seats:
        calls, usage = seat_files(data, s)
        api[s] = classify_file(str(calls), load(usage))
    d = copy.deepcopy(d0)
    old_api = any(d0["proxy_error"].values()) if duel_dict else bool(d0.get("proxy_error"))
    if duel_dict:
        d["proxy_error"] = {s: api[s]["api_failure"] for s in seats}
        d["transient_api_errors"] = {s: api[s]["transient_api_errors"] for s in seats}
        d["unrecovered_api_errors"] = {s: api[s]["unrecovered_api_errors"] for s in seats}
        new_api = any(d["proxy_error"].values())
    else:
        d["proxy_error"] = api[None]["api_failure"]
        d["transient_api_errors"] = api[None]["transient_api_errors"]
        d["unrecovered_api_errors"] = api[None]["unrecovered_api_errors"]
        new_api = d["proxy_error"]
    derived = []
    if old_api and not new_api and not d0.get("valid_trial", True):
        # the fields the service derives from proxy_error (golf and bowling services derive none)
        if duel_dict and "valid_trial" in d0 and sport in DUEL_COMPLETE:
            r = load(data / "replay_check.json", {})
            others = bool(DUEL_COMPLETE[sport](d0) and d0.get("finalized") and d0.get("deterministic")
                          and not d0.get("errors") and not any((d0.get("meter_error") or {}).values()))
            d["valid_trial"], d["technical_failure"] = others, not others
            derived.append(f"valid_trial={others}")
            if others and d0.get("winner") is None:
                d["winner"] = duel_winner(sport, d0, r)
                derived.append(f"winner={d['winner']}")
        elif not duel_dict and "valid_trial" in d0:
            others = not any(d0.get(k) for k in SINGLE_FLAGS)
            d["valid_trial"], d["technical_failure"] = others, not others
            derived.append(f"valid_trial={others}")
    after = run_grader(grader, data, d)
    # the same grader on the unpatched final.json must reproduce the recorded reward (apart from the new count fields):
    # then every difference between before and after comes from the API rule alone
    same = run_grader(grader, data, None)
    drift = sorted(k for k in set(same) | set(before) if not k.startswith("_") and not k.endswith("api_errors")
                   and same.get(k) != before.get(k))
    return {"trial": str(trial), "task": task, "seats": {str(s or "single"): api[s] for s in seats},
            "old_proxy_error": old_api, "new_proxy_error": new_api, "derived": derived,
            "before": before, "after": after, "grader_drift": drift}


KEYS = ("valid_trial", "technical_failure", "success", "won", "A_won", "B_won", "proxy_error", "deterministic",
        "match_over", "grader_error")


def show(res: dict) -> None:
    b, a = res["before"], res["after"]
    print(f"== {res['trial']}\n   task {res['task']}")
    for s, v in res["seats"].items():
        print(f"   seat {s}: transient {v['transient_api_errors']}, unrecovered {v['unrecovered_api_errors']} "
              f"(limit {MAX_TRANSIENT_API_ERRORS}) -> api_failure {v['api_failure']}")
    print(f"   proxy_error {int(res['old_proxy_error'])} -> {int(res['new_proxy_error'])}"
          + (f"; service fields: {', '.join(res['derived'])}" if res["derived"] else ""))
    for k in KEYS:
        if k in a or k in b:
            print(f"   {k:18s} {str(b.get(k, '-')):>4s} -> {str(a.get(k, '-')):>4s}")
    changed = sorted(k for k in set(a) | set(b) if k not in KEYS and not k.startswith("_") and a.get(k) != b.get(k))
    if changed:
        print("   other changes: " + ", ".join(f"{k} {b.get(k, '-')} -> {a.get(k, '-')}" for k in changed))
    print("   current grader on the original final.json reproduces the recorded reward: "
          + ("yes" if not res["grader_drift"] else "NO, differs in " + ", ".join(res["grader_drift"])))
    if a.get("_grader_stderr"):
        print("   grader error:\n" + a["_grader_stderr"])
    verdict = ("NOT RE-GRADED: the current grader does not reproduce the recorded reward" if res["grader_drift"] else
               "now VALID" if a.get("valid_trial") and not b.get("valid_trial") else
               "was valid, unchanged" if a.get("valid_trial") else "stays INVALID")
    print(f"   verdict: {verdict}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", help="trial directories (or job directories holding them)")
    ap.add_argument("--write", action="store_true", help="write <trial>/verifier/reward_regraded.json")
    ap.add_argument("--json", action="store_true", help="print one JSON object per trial instead of the summary")
    args = ap.parse_args(argv)
    bad = 0
    for t in trials(args.paths):
        try:
            res = regrade(t)
        except Exception as exc:  # noqa: BLE001
            print(f"== {t}\n   ERROR: {exc}")
            bad = 1
            continue
        print(json.dumps(res)) if args.json else show(res)
        if res["grader_drift"]:
            bad = 1
        elif args.write:
            out = {k: v for k, v in res["after"].items() if not k.startswith("_")}
            out["regraded_transient"] = 1
            (t / "verifier").mkdir(exist_ok=True)
            (t / "verifier" / "reward_regraded.json").write_text(json.dumps(out, allow_nan=False))
            print(f"   wrote {t / 'verifier' / 'reward_regraded.json'}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
