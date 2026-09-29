"""Immutable failure decisions and dual-dimension comparisons."""
import time
from uuid import uuid4

DIMENSIONS = ("input_tokens", "output_tokens")
FAILURE_REASONS = frozenset({"budget_exceeded", "budget_exhausted", "reservation_violation",
    "usage_incomplete", "usage_conflict", "usage_unavailable", "gateway_failed", "agent_interrupted"})


def stop(state, reason, dimensions=()):
    if reason not in FAILURE_REASONS:
        raise ValueError("Unknown usage failure reason")
    if state["stop"] is None:
        state["stop"] = dict(stop_id=uuid4().hex, reason=reason, dimensions=list(dimensions),
            decision_at=time.time(), decision_monotonic_ns=time.monotonic_ns(),
            policy_revision=state["policy_revision"], usage=dict(state["usage"]),
            limits=dict(state["limits"]))
    state["closed"] = True


def check(state):
    exceeded = [key for key in DIMENSIONS if state["usage"][key] > state["limits"][key]]
    if exceeded:
        stop(state, "budget_exceeded", exceeded)
