#!/usr/bin/env python3
"""INVARIANT test (docs/protocol/README.md Appendix H.5), part of the required CI job `invariants`: infrastructure failures
allow at most one full retry with the same instance, seed and configuration; a failed retry gets the default handling
and no further retry; normal task failures never qualify (scripts/retry_policy.py). Standard library only."""
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

# decide(): one retry after an infrastructure failure, none after a second one, none after a result
d = rp.decide("infra_failure", 0)
expect(d["retry"] and d["void"], f"first infra failure: one full retry, attempt void ({d})")
d = rp.decide("infra_failure", 1)
expect(not d["retry"] and not d["void"], f"infra failure of the retry: default handling, no retry ({d})")
for n in (2, 5):
    expect(not rp.decide("infra_failure", n)["retry"], f"never a retry after {n} voided attempts")
for o in ("agent_failure", "success"):
    for n in (0, 1):
        d = rp.decide(o, n)
        expect(not d["retry"] and not d["void"], f"{o}: a result, never retried, never void ({d})")
try:
    rp.decide("timeout", 0)
    fails.append("an unknown outcome must be refused")
except ValueError:
    pass
expect(rp.MAX_INFRA_RETRIES == 1, "MAX_INFRA_RETRIES is 1 (owner 2026-10-14)")

# retry_config(): the same instance, seed and configuration
r = rp.retry_config(CFG)
expect(r == CFG and r is not CFG, "the retry runs the first attempt's configuration (a copy)")

# check_attempts(): the audit of recorded sequences
ok = [[{"outcome": "success", "config": CFG}],
      [{"outcome": "agent_failure", "config": CFG}],
      [{"outcome": "infra_failure", "config": CFG}, {"outcome": "agent_failure", "config": dict(CFG)}],
      [{"outcome": "infra_failure", "config": CFG}, {"outcome": "infra_failure", "config": dict(CFG)}]]
for seq in ok:
    e = rp.check_attempts(seq)
    expect(not e, f"allowed sequence refused: {[a['outcome'] for a in seq]}: {e}")
bad = {"a third attempt": [{"outcome": "infra_failure", "config": CFG}] * 3,
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
expect(rp.counted([{"outcome": "infra_failure"}, {"outcome": "infra_failure", "id": 2}])["id"] == 2,
       "a failed retry gets the default handling (it is the record), the first attempt stays void")

if fails:
    print("FAIL scripts/tests/test_retry_policy.py:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("ok retry policy: one full retry after an infrastructure failure, none after a result or a second failure")
