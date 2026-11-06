#!/usr/bin/env python3
"""The infrastructure-rerun rule (docs/protocol/README.md Appendix H.5), as one pure function
every runner applies and the required CI job `invariants` tests (scripts/tests/test_retry_policy.py):

    An attempt that failed for infrastructure reasons, with positive evidence of it, is void and the task may be rerun
    with the same instance, seed and configuration, clearing all agent and environment state, until an attempt gives a
    result. A graded failure is a result and is never rerun; nor is a success.

An attempt is one run of one task under one run id. Its outcome is "success", "agent_failure" (a result: the agent's
deliverable, its cutoff, its token budget) or "infra_failure" (not a result: scripts/write_task_results.py
not_a_result(), the verifier's `infra_error` / `grader_error`, a trial Harbor or the model account ended). A launch that
never started a trial is no attempt. The runner (a scheduler, scripts/run_agent_batch.sh) asks
decide() after every attempt; check_attempts() audits a recorded sequence (the results pipeline, CI fixtures).
Standard library only.
"""
from __future__ import annotations

MAX_INFRA_RETRIES = None        # no fixed number of reruns after infrastructure failures (H.5); results are never rerun
OUTCOMES = ("success", "agent_failure", "infra_failure")
SAME = ("digest", "seed", "mode", "cutoff_s", "reset_budget", "slowdown", "network", "protocol_version")


def decide(outcome: str, voided_before: int) -> dict:
    """What the runner does after an attempt that ended with `outcome`, given how many earlier attempts of the same task
    x run id were voided for infrastructure. Returns {"retry", "void", "reason"}: `void` = this attempt is not a result
    (it is moved aside, never counted); `retry` = run once more from a fresh environment with the same instance, seed
    and configuration (retry_config)."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome {outcome!r}: one of {OUTCOMES}")
    if voided_before < 0:
        raise ValueError("voided_before < 0")
    if outcome != "infra_failure":
        return {"retry": False, "void": False, "reason": f"{outcome}: a result, never rerun"}
    if MAX_INFRA_RETRIES is not None and voided_before >= MAX_INFRA_RETRIES:
        return {"retry": False, "void": False,
                "reason": "infrastructure failure of the last allowed rerun: the default failure handling"}
    return {"retry": True, "void": True,
            "reason": "infrastructure failure: the attempt is void; rerun with the same instance, seed and "
                      "configuration, all agent and environment state cleared"}


def retry_config(first: dict) -> dict:
    """The configuration of the retry: the first attempt's, unchanged (scripts/task_conventions.py effective_config)."""
    return dict(first)


def check_attempts(attempts: list[dict]) -> list[str]:
    """Errors in a recorded sequence of attempts of one task x run id, oldest first; each {"outcome", "config"}. The rule
    holds when every attempt but the last was voided for infrastructure (decide() said rerun) and every rerun ran with
    the first attempt's instance, seed and configuration."""
    errs: list[str] = []
    if MAX_INFRA_RETRIES is not None and len(attempts) > 1 + MAX_INFRA_RETRIES:
        errs.append(f"{len(attempts)} attempts: at most {1 + MAX_INFRA_RETRIES}")
    voided = 0
    for i, a in enumerate(attempts[:-1]):
        d = decide(a.get("outcome", ""), voided) if a.get("outcome") in OUTCOMES else None
        if d is None:
            errs.append(f"attempt {i + 1}: unknown outcome {a.get('outcome')!r}")
            continue
        if not d["retry"]:
            errs.append(f"attempt {i + 2} follows attempt {i + 1} ({a['outcome']}): {d['reason']}")
        voided += d["void"]
    first = (attempts[0].get("config") or {}) if attempts else {}
    for i, a in enumerate(attempts[1:], 2):
        cfg = a.get("config") or {}
        diff = [k for k in SAME if k in first and cfg.get(k) != first.get(k)]
        if diff:
            errs.append(f"attempt {i}: not the first attempt's instance, seed and configuration ({', '.join(diff)} differ)")
    return errs


def counted(attempts: list[dict]) -> dict | None:
    """The attempt that is the result of a task x run id: the first one that is not voided (None: no result yet, every
    attempt so far failed for infrastructure)."""
    voided = 0
    for a in attempts:
        d = decide(a["outcome"], voided)
        if not d["void"]:
            return a
        voided += 1
    return None
