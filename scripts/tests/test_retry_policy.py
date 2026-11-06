#!/usr/bin/env python3
"""INVARIANT test (docs/protocol/README.md Appendix H.5), part of the required CI job `invariants`: an infrastructure
failure is void and may be rerun with the same instance, seed and configuration, also after a rerun that failed for
infrastructure; a result (an agent failure or a success) is never rerun (scripts/retry_policy.py). Standard library only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retry_policy as rp  # noqa: E402

fails = []


def expect(cond: bool, what: str) -> None:
    if not cond:
        fails.append(what)


CFG = {"digest": "sha256:a", "seed": 7, "mode": "standard", "cutoff_s": 3600, "reset_budget": 0, "slowdown": None,
       "network": "allowlist", "protocol_version": "2.0"}

# decide(): a rerun after every infrastructure failure, none after a result
for n in (0, 1, 2, 5):
    d = rp.decide("infra_failure", n)
    expect(d["retry"] and d["void"], f"infra failure after {n} voided attempts: void, rerun ({d})")
for o in ("agent_failure", "success"):
    for n in (0, 1, 3):
        d = rp.decide(o, n)
        expect(not d["retry"] and not d["void"], f"{o}: a result, never retried, never void ({d})")
try:
    rp.decide("timeout", 0)
    fails.append("an unknown outcome must be refused")
except ValueError:
    pass
expect(rp.MAX_INFRA_RETRIES is None, "MAX_INFRA_RETRIES is None: no fixed number of infrastructure reruns (PROTOCOL H.5)")

# retry_config(): the same instance, seed and configuration
r = rp.retry_config(CFG)
expect(r == CFG and r is not CFG, "the retry runs the first attempt's configuration (a copy)")

# check_attempts(): the audit of recorded sequences
ok = [[{"outcome": "success", "config": CFG}],
      [{"outcome": "agent_failure", "config": CFG}],
      [{"outcome": "infra_failure", "config": CFG}, {"outcome": "agent_failure", "config": dict(CFG)}],
      [{"outcome": "infra_failure", "config": CFG}, {"outcome": "infra_failure", "config": dict(CFG)}],
      [{"outcome": "infra_failure", "config": CFG}] * 3 + [{"outcome": "success", "config": dict(CFG)}]]
for seq in ok:
    e = rp.check_attempts(seq)
    expect(not e, f"allowed sequence refused: {[a['outcome'] for a in seq]}: {e}")
bad = {"a rerun after a result": [{"outcome": "infra_failure", "config": CFG}, {"outcome": "agent_failure", "config": CFG},
                                   {"outcome": "success", "config": CFG}],
       "a retry after an agent failure": [{"outcome": "agent_failure", "config": CFG}, {"outcome": "success", "config": CFG}],
       "a retry after a success": [{"outcome": "success", "config": CFG}, {"outcome": "success", "config": CFG}],
       "a retry on another seed": [{"outcome": "infra_failure", "config": CFG}, {"outcome": "success", "config": dict(CFG, seed=8)}],
       "a retry of another task version": [{"outcome": "infra_failure", "config": CFG},
                                           {"outcome": "success", "config": dict(CFG, digest="sha256:b")}],
       "a retry with another reset budget": [{"outcome": "infra_failure", "config": CFG},
                                             {"outcome": "success", "config": dict(CFG, reset_budget=3)}]}
for what, seq in bad.items():
    expect(bool(rp.check_attempts(seq)), f"{what} must be refused")

# counted(): the voided attempt never counts
expect(rp.counted([{"outcome": "infra_failure"}, {"outcome": "agent_failure", "id": 2}]) == {"outcome": "agent_failure", "id": 2},
       "the retry's result counts, the voided attempt does not")
expect(rp.counted([{"outcome": "infra_failure"}]) is None, "a voided attempt alone is no result")
expect(rp.counted([{"outcome": "infra_failure"}, {"outcome": "infra_failure", "id": 2}]) is None,
       "two infrastructure failures: still no result, both void")
expect(rp.counted([{"outcome": "infra_failure"}] * 2 + [{"outcome": "agent_failure", "id": 3}])["id"] == 3,
       "the first attempt that is a result counts")

if fails:
    print("FAIL scripts/tests/test_retry_policy.py:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("ok retry policy: reruns only after infrastructure failures, never after a result")
