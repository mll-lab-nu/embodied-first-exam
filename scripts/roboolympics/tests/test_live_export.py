#!/usr/bin/env python3
"""Unit test of the exported matches' live grading (board 0151; scripts/roboolympics/live_grading_export.py), standard
library only, no simulator: for every task of scripts/roboolympics/exported.toml,
  1. the patch is applied (live_grading_export.py --check finds nothing to change) and RO_VERDICT_REPLAY=0 is set;
  2. its tests/grade.py grade() (the core's grader, sport fields stubbed) on synthetic final.json records:
       a valid live match the agent's seat won, no replay_check.json -> success 1, verdict_replay 0, graded_by_live 1, no deterministic,
                                                                         none of the sport's replay_* fields
       the same match lost                                             -> success 0, valid 1 (the agent's result)
       a live technical error (errors[])                               -> success 0, technical_failure 1 (infra)
       the same record without verdict_replay (the upstream rule)      -> needs the replay: technical_failure 1
       a control-step error (where world_step) after the agent's first applied act, finalized
                                                                      -> real-time: success 0, not infra (agent_sim_error 1);
                                                                         turn-based, no applied act, unfinalized, or another
                                                                         `where` (bookkeeping): infra
  3. its core/service.py skips the validity replay and drops the replay term only under RO_VERDICT_REPLAY=0.
    python3 scripts/roboolympics/tests/test_live_export.py"""
import importlib.util, json, os, pathlib, subprocess, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[3]
REG = tomllib.loads((ROOT / "scripts/roboolympics/exported.toml").read_text())
# the privileged twins (kind "fullsim-policy", #282) are graded by the verifier (a formal match and its replay), not live
REG["tasks"] = [e for e in REG["tasks"] if e.get("kind") != "fullsim-policy"]


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"g_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(contract: dict, winner: str, **kw) -> dict:
    fmt = contract["format"]
    seats = list((contract["formats"][fmt]).get("seats") or ["A"])
    sides = {s: s for s in seats} if len(seats) > 1 else {seats[0]: "A"}
    other = "B" if winner == "A" else "A"
    d = {"cfg": {"seats": seats, "level": None, "seed": 1}, "sides": sides, "format": fmt, "play": "program",
         "reason": "match_over", "match_winner": winner, "scores": {winner: 11, other: 3}, "finalized": True,
         "graded_ready": True, "valid_trial": True, "errors": [], "meter_error": {s: False for s in seats},
         "proxy_error": {s: False for s in seats}, "transient_api_errors": {s: 0 for s in seats},
         "unrecovered_api_errors": {s: 0 for s in seats}, "seats": {}, "player_modes": {s: "unmetered" for s in seats},
         "state_sha": "x", "commands_sha": "y", "source_sha": "z", "steps": 100, "solo": False, "seed": 1,
         "graded_by": "live", "replays": 0, "verdict_replay": False, "deterministic": None}
    d.update(kw)
    return d


def main() -> int:
    errs = []
    r = subprocess.run([sys.executable, str(ROOT / "scripts/roboolympics/live_grading_export.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode:
        errs.append("live_grading_export.py --check: " + r.stdout[-300:])
    stub = lambda d: {"replay_error": 1, "replay_points_for": -1, "won": 0}  # noqa: E731  (sport fields)
    for e in REG["tasks"]:
        t = ROOT / "tasks" / e["name"]
        if 'RO_VERDICT_REPLAY: "0"' not in (t / "environment/docker-compose.yaml").read_text():
            errs.append(f"{t.name}: no RO_VERDICT_REPLAY=0"); continue
        svc = (t / "environment/sim/core/service.py").read_text()
        if "if not verdict_replay():" not in svc or "(replay_ok or live)" not in svc or 'graded_by="live"' not in svc:
            errs.append(f"{t.name}: core/service.py is not gated on RO_VERDICT_REPLAY")
        g = load(t / "tests/grade.py")
        contract = json.loads((t / "tests/contract.json").read_text())
        win = g.grade(record(contract, "A"), {}, contract, stub)
        if win.get("success") != 1 or win.get("graded_by_live") != 1 or win.get("verdict_replay") != 0 or "deterministic" in win or \
                any(k.startswith("replay") and k != "replays" for k in win):
            errs.append(f"{t.name}: a won live match: {win}")
        lost = g.grade(record(contract, "B"), {}, contract, stub)
        multi = len(contract["formats"][contract["format"]].get("seats") or []) > 1
        if lost.get("valid_trial") != 1 or (not multi and lost.get("success") != 0) or lost.get("technical_failure"):
            errs.append(f"{t.name}: a lost live match: {lost}")
        if multi and (lost.get("A_won") != 0 or lost.get("B_won") != 1):
            errs.append(f"{t.name}: a lost duel: {lost}")
        bad = g.grade(record(contract, "A", errors=[{"where": "sport", "error": "x"}]), {}, contract, stub)
        if bad.get("success") != 0 or bad.get("technical_failure") != 1:
            errs.append(f"{t.name}: a live technical error: {bad}")
        # a simulator error of the world's step (docs/protocol/standard_mode.md Part 3): after the agent's first act the agent's 0 in a
        # real-time match; before it, or in a turn-based match, a technical failure (infra)
        realtime = "-standard-realtime" in t.name
        world = dict(reason="technical_error", match_winner=None, errors=[{"where": "world_step", "error": "mujoco: bad qacc"}],
                     slowdown=10 if realtime else None)
        after = g.grade(record(contract, "A", seats={"A": {"attempts": 3, "applied": 2}}, **world), {}, contract, stub)
        # acts refused (409 / 429) never reached the world: attempts without an applied act is still infra
        before = g.grade(record(contract, "A", seats={"A": {"attempts": 3, "applied": 0}}, **world), {}, contract, stub)
        unfin = g.grade(record(contract, "A", seats={"A": {"applied": 2}}, finalized=False, **world), {}, contract, stub)
        book = g.grade(record(contract, "A", seats={"A": {"applied": 2}}, **dict(world, errors=[{"where": "world", "error":
                                                                                     "OSError: disk full"}])), {}, contract, stub)
        if unfin.get("technical_failure") != 1 or book.get("technical_failure") != 1:
            errs.append(f"{t.name}: an unfinalized record or a bookkeeping error must stay infra: {unfin} / {book}")
        if after.get("success") != 0 or after.get("technical_failure") != int(not realtime) or \
                after.get("agent_sim_error") != int(realtime):
            errs.append(f"{t.name}: a world error after the first act: {after}")
        if before.get("success") != 0 or before.get("technical_failure") != 1:
            errs.append(f"{t.name}: a world error before the first act: {before}")
        old = record(contract, "A"); [old.pop(k) for k in ("graded_by", "replays", "verdict_replay")]
        up = g.grade(old, {}, contract, stub)
        if up.get("technical_failure") != 1:
            errs.append(f"{t.name}: without graded_by the replay must still be required: {up}")
    for x in errs:
        print("FAIL", x)
    print(f"{'FAIL' if errs else 'ok'} roboolympics exported live grading: {len(REG['tasks'])} task(s), {len(errs)} failed")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
