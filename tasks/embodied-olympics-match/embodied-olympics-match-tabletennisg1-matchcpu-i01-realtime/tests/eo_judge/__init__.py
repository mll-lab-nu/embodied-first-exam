"""The Judge (fw_pattern_1020.md §3.0 ⑦, §3.1): verifies one Run from its sealed evidence and writes the one verdict
(eo-verdict/1) that reward.json, leaderboard rows and the legacy verdict shape are projected from.

    from framework.judge import judge_dir, verdict_bytes
    v = judge_dir("runs/F-0007/run-1")          # or a legacy Harbor trial directory

Modules: evidence (read the three layouts), verdict (facts, faults, the verdict), rules (the rule texts), gateway (model-call
errors by cause, the interim outage rule), review (review diagnostics), checks (input checks, release digest),
project (reward.json, leaderboard rows, legacy verdict), legacy (the legacy official configuration), verifier (the
verifier sandbox's entry), cli (`eo judge`), compare (old against new verdicts), canon (JCS, digests).
Standard library only; relative imports, so the same files run as `framework.judge` and as the verifier's `eo_judge`.
"""
from __future__ import annotations

from .canon import digest, jcs
from .evidence import load as load_evidence
from .verdict import NAME, SCHEMA, VERSION, judge, verdict_bytes, verdict_digest
from .project import leaderboard_rows, legacy_verdict, reward
from .rules import RULES, RULESET


def judge_dir(path) -> dict:
    """The verdict of the Run evidence at `path` (any layout evidence.load knows)."""
    return judge(load_evidence(path))


def judge_run(run_dir, *, fixture: dict | None = None, run: dict | None = None, evidence: dict | None = None,
              task=None) -> dict:
    """The Runner's entry (framework/run/judging.py): the verdict of a sealed Run directory, a pure function of what
    is sealed there, so `eo judge RUN_DIR` later gives the same bytes. `fixture`, `run`, `evidence` (the
    eo-evidence/1 record) and `task` (the Runner's Task view: path, release, status, lock) are the records the Runner
    holds; anything not given is read from the directory, and a sealed copy (fixture.json, task/) wins over a given
    one. The legacy scoring hook of the Task package (task/sport_grade.py) gives the sport's own numbers
    (diagnostics.sport_fields); it runs without writing bytecode into the Run directory."""
    from . import evidence as _ev, legacy as _legacy
    ev = _ev.load_run_dir(run_dir, run=run, manifest=evidence, fixture=fixture, task=task)
    sport_fields = None
    official = None
    hook_error = None
    if ev.world is not None and ev.world_kind != "eo-world-report/1":
        try:                         # the sport's own numbers are diagnostics: a hook that cannot read the world
            if ev.sport_hook is not None:      # report never decides the verdict (the error is recorded)
                sport_fields = _legacy.run_hook(ev.sport_hook, ev.world)
            official = _legacy.official_reading(ev.world, ev.task.get("contract") or {}, sport_fields)
        except Exception as e:  # noqa: BLE001
            hook_error = f"{type(e).__name__}: {str(e)[:200]}"
    v = judge(ev, sport_fields=sport_fields, legacy_official=official)
    if hook_error:
        v["diagnostics"]["sport_fields_error"] = hook_error
    return v


__all__ = ["NAME", "SCHEMA", "VERSION", "RULES", "RULESET", "digest", "jcs", "judge", "judge_dir", "judge_run",
           "leaderboard_rows",
           "legacy_verdict", "load_evidence", "reward", "verdict_bytes", "verdict_digest"]
