"""The verifier sandbox's entry (a generated task's tests/grade.py runs main()): the Judge on the match service's
artifacts. No network, no simulator; the task's tests/ directory carries this package (eo_judge/), the sport's scoring
hook (sport_grade.py: evaluate(final) -> numbers), contract.json, taskspec.json and the legacy helpers (seeds.py,
nocode_audit.py).

    DATA (RCB_DATA, default /data)                    final.json, episode.jsonl, replay_check.json,
                                                      think_calls_<seat>.jsonl, think_usage_<seat>.json
    LOG  (RCB_LOG, default /logs/verifier)            verdict.json      the verdict (eo-verdict/1), canonical JSON
                                                      verdict_v0.json   the core 0.3.0 verdict shape (projection)
                                                      reward.json       numbers only (projection; Harbor reads it)
                                                      reward.txt        success (0 / 1)
                                                      versions.json     what the match ran on
                                                      copies of final.json, replay_check.json, episode.jsonl, replay.mp4
A crash of the judge itself is written as a void verdict (platform, judge_error) so a trial never passes silently.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import canon, evidence, legacy, project, verdict as judge_mod


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod                                   # main() writes no bytecode (sys.dont_write_bytecode)


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(canon.jcs(obj) + b"\n")
    tmp.replace(path)


def crash_verdict(error: str, data: Path) -> dict:
    """The verdict when the judge itself failed: void, platform / judge_error (rerun)."""
    fid = "LEGACY-" + canon.digest({"judge_error": str(data)})[7:19].upper()
    return {"schema": judge_mod.SCHEMA, "fixture_id": fid, "run_id": fid + "/run-1",
            "task_release": canon.digest({"task": "unknown"}), "valid": False,
            "official": {"eligible": False, "blockers": ["adhoc_fixture", "dev_seed", "candidate_release",
                                                         "uncertified_backend", "invalid"]},
            "termination": "platform_fault", "sides": {"A": {"kind": "entrant", "status": "void", "exit": None,
                                                              "score": None, "rank": None, "metrics": {},
                                                              "valid": False}},
            "winner": None, "ranking": [],
            "faults": [{"class": "platform", "code": "judge_error", "scope": "match",
                        "effect": "void_match", "evidence": [], "note": "R-JUDGE: " + error[:300]}],
            "checks": {**{c: "n/a" for c in judge_mod.checks_mod.CHECKS}, "platform_services": "n/a"},
            "diagnostics": {"fault_rules": ["R-JUDGE"]},
            "rerun": {"recommended": True, "reason": "platform/judge_error"},
            "evidence_digest": canon.digest({"items": [], "missing": []}),
            "judge": {"name": judge_mod.NAME, "version": judge_mod.VERSION, "rules": canon.digest({}),
                      "digest": canon.digest({}), "offline": True},
            "meta": {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "layout": "verifier"}}


def grade(d: dict, r: dict, contract: dict, evaluate, audits: dict | None = None) -> dict:
    """For callers of the core 0.3.0 grader's grade() (tools/olympiad/plan.py reads official_config): reward.json of
    the match described by a final.json `d` and replay_check.json `r`, judged by the Judge (no episode, no gateway
    logs: only what the two records say)."""
    ev = evidence.Evidence(root=Path("."), layout="verifier")
    ev.world, ev.world_kind, ev.replay = d, d.get("schema") or "ro-final/1", r
    sport_fields = evaluate(d) if evaluate is not None else None
    official = legacy.official_reading(d, contract, sport_fields)
    v = judge_mod.judge(ev, sport_fields=sport_fields, audits=audits, legacy_official=official, now=0.0)
    fmt = d.get("format") or contract.get("format") or ""
    line = ((contract.get("formats") or {}).get(fmt) or {}).get("success") or {}
    return project.reward(v, d, line, d.get("sides"))


def main(tests: Path | None = None) -> int:
    """Judge the match in the verifier sandbox; no bytecode is written while it runs (the task's tests/ directory and
    the hooks it loads stay as they were)."""
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        return _main(tests)
    finally:
        sys.dont_write_bytecode = old


def _main(tests: Path | None = None) -> int:
    tests = Path(tests) if tests else Path(sys.argv[0]).resolve().parent
    data = Path(os.environ.get("RCB_DATA", "/data"))
    log = Path(os.environ.get("RCB_LOG", "/logs/verifier"))
    log.mkdir(parents=True, exist_ok=True)
    final = None
    try:
        contract = json.loads((tests / "contract.json").read_text()) if (tests / "contract.json").exists() else {}
        ev = evidence.load_verifier(data, tests)
        final = ev.world
        sport_fields = None
        hook_error = None
        if final is not None and ev.sport_hook is not None:
            try:                                 # the sport's numbers are diagnostics: never the verdict's cause
                sport_fields = legacy.run_hook(ev.sport_hook, final)
            except Exception as e:  # noqa: BLE001
                hook_error = f"{type(e).__name__}: {str(e)[:200]}"
        audits = None
        if final is not None and final.get("play") == "direct" and (tests / "nocode_audit.py").exists():
            nmod = _load(tests / "nocode_audit.py", "nocode_audit")
            audits = {s: nmod.nocode_audit(data / f"think_calls_{s}.jsonl",
                                           skip_ids=nmod.gate_blocked_ids(data / f"direct_gate_{s}.jsonl"))
                      for s in (final.get("cfg") or {}).get("seats", [])}
            (log / "nocode_audit.json").write_text(json.dumps({s: dict(tool_calls=a[0], violations=a[1][:50])
                                                               for s, a in audits.items()}, indent=1))
        official = legacy.official_reading(final, contract, sport_fields) if final is not None else None
        v = judge_mod.judge(ev, sport_fields=sport_fields, audits=audits, legacy_official=official)
        if hook_error:
            v["diagnostics"]["sport_fields_error"] = hook_error
        fmt = (final or {}).get("format") or contract.get("format") or ""
        line = ((contract.get("formats") or {}).get(fmt) or {}).get("success") or {}
        out = project.reward(v, final, line, (final or {}).get("sides"))
        ts = (final or {}).get("taskspec") or {}
        v0 = project.legacy_verdict(v, ev.task.get("taskspec_bytes") and canon.sha256_hex(ev.task["taskspec_bytes"])
                                    or ts.get("sha256"), ts.get("overrides"))
        hs = (contract.get("official") or {}).get("hidden_seeds") or {}
        (log / "versions.json").write_text(json.dumps({
            "versions": (final or {}).get("versions"), "renderer": (final or {}).get("renderer"),
            "judge": v["judge"],
            "seed_set": {"sha256": hs.get("sha256"), "counts": hs.get("counts"),
                         "index": (official or {}).get("hidden_seed_index")} if hs else None,
            "continuous_score": {k: ((final or {}).get("continuous") or {}).get(k)
                                 for k in ("name", "from", "higher_is_better")}
            if (final or {}).get("continuous") else None}))
        for f in ("final.json", "replay_check.json", "episode.jsonl", "replay.mp4"):
            if (data / f).exists():
                shutil.copy(data / f, log / f)
    except Exception as e:  # noqa: BLE001
        print(type(e).__name__, str(e))
        v = crash_verdict(f"{type(e).__name__}: {e}", data)
        v0 = project.legacy_verdict(v)
        out = {"success": 0, "valid_trial": 0, "technical_failure": 1, "grader_error": 1,
               "missing_log": int(not (data / "final.json").exists()), "failure_agent": 0,
               "failure_infrastructure": 1, "failure_external": 0, "void": 1, "t0_barrier": 0,
               "failure_platform": 1, "failure_plugin": 0, "failure_undetermined": 0, "official_eligible": 0}
    write_json(log / "verdict.json", v)
    (log / "verdict_v0.json").write_text(json.dumps(v0))
    (log / "reward.json").write_text(json.dumps(out))
    (log / "reward.txt").write_text(str(out["success"]) + "\n")
    print(json.dumps({"valid": v["valid"], "termination": v["termination"], "winner": v["winner"],
                      "faults": [f"{f['class']}/{f['code']}" for f in v["faults"]]}))
    return 0
