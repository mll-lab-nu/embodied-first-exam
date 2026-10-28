"""Immutable task-local candidates and host-owned validation/release decisions."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

from .broker import digest, encoded
from .sandbox import run_program


PROTOCOLS = {
    "angle-delta-v1": {"kind": "python", "effect": "compute",
        "contract": "run({current: degrees, target: degrees}, tools) returns shortest signed delta in [-180,180)."},
    "turn-adapter-v1": {"kind": "python", "effect": "compute",
        "contract": "run({angle: signed degrees}, tools) returns {direction: left if angle>=0 else right, degrees: abs(angle) clamped to [10,120]}."},
    "feedback-policy-v1": {"kind": "policy", "effect": "policy",
        "contract": "Rules: on_prediction_error = reobserve|revise_action|repair_tool; reasoning_on_uncertainty = high; completion_requires_evidence = true; recovery_note = nonempty string. Cannot change kernel, oracles or termination semantics."},
}
PROTOCOL_VERSION = digest(PROTOCOLS)


class Lifecycle:
    """A local eligibility decision never authorizes cross-task publication."""

    def __init__(self, directory: Path, broker):
        """Bind the task-local runtime dependencies and initial state."""
        self.directory, self.broker = directory, broker
        directory.mkdir(exist_ok=True)
        self.candidates, self.reports, self.health = {}, {}, {}
        self.active = {}
        self.pending = None
        self.discarded = set()
        self.proposals = {}
        self.closed_observations = {}
        self.review = None

    def status(self, ident):
        """Describe a candidate without resetting its validation or activation state."""
        if ident in self.discarded:
            return "discarded"
        if self.health.get(ident) == "quarantined":
            return "quarantined"
        if self.active.get(self.candidates[ident]["protocol"]) == ident:
            return "active"
        return self.reports.get(ident, {}).get("report", {}).get("status", "unvalidated")

    def snapshot(self):
        """Keep the outstanding repair and legal next steps in projected memory."""
        observation = self.broker.binding.observation_id
        protocols = [p for p in PROTOCOLS if self.closed_observations.get(p) != observation]
        tools = ["execute", "receipt", "evidence", "memory"]
        if any(self.candidates[ident]["protocol"] != "feedback-policy-v1" for ident in self.active.values()):
            tools.append("compute")
        pending = None
        if self.pending:
            ident = self.pending
            status = self.status(ident)
            action = "validate" if status == "unvalidated" else "activate" if status == "pass" else "candidate"
            protocols = [self.candidates[ident]["protocol"]] if action == "candidate" else []
            tools.extend([action, "discard"])
            pending = {"candidate_id": ident, "status": status, "candidate": self.candidates[ident],
                       "validation": self.reports.get(ident), "next_action": action}
            next_step = f"{action} candidate {ident}, or discard it and resume the task. A repair must name this candidate as parent."
        else:
            tools.append("discover")
            if protocols:
                tools.append("candidate")
            next_step = "Use the active tools/policy in the task. A closed protocol needs new environment evidence before another proposal."
        return {"pending": pending, "active": dict(self.active), "available_protocols": protocols,
                "available_tools": tools, "next_step": next_step}

    def propose(self, value):
        """Freeze a task-local candidate, its parent, diagnosis and evidence."""
        required = {"protocol", "implementation", "parent", "diagnosis", "evidence"}
        if set(value) != required or value["protocol"] not in PROTOCOLS:
            raise ValueError("Candidate requires protocol, implementation, parent, diagnosis and evidence")
        if not isinstance(value["diagnosis"], str) or not value["diagnosis"].strip() or not value["evidence"]:
            raise ValueError("Candidate needs an evidence-linked diagnosis")
        if value["parent"] is not None and value["parent"] not in self.candidates:
            raise ValueError("Unknown parent candidate")
        if value["parent"] is not None and self.candidates[value["parent"]]["protocol"] != value["protocol"]:
            raise ValueError("Parent candidate belongs to a different validation scope")
        if not isinstance(value["evidence"], list) or any(not isinstance(ref, str) for ref in value["evidence"]):
            raise ValueError("Candidate evidence must be observation references")
        value = json.loads(encoded(value))  # The caller cannot mutate an immutable candidate.
        value["evidence"] = sorted(set(value["evidence"]))
        # Rewording a diagnosis or changing ancestry does not create a new implementation.
        fingerprint = digest({key: value[key] for key in ("protocol", "implementation", "evidence")})
        if fingerprint in self.proposals:
            ident = self.proposals[fingerprint]
            self.broker.record("candidate.reused", {"candidate_id": ident, "status": self.status(ident)})
            return {"candidate_id": ident, "status": self.status(ident), "publish_eligible": False, "reused": True}
        if not self.broker.settled:
            raise ValueError("Candidate construction requires a settled execution boundary")
        observation = self.broker.binding.observation_id
        if observation not in value["evidence"]:
            raise ValueError("A new candidate needs the current observation in its evidence")
        if self.pending:
            status = self.status(self.pending)
            if status not in {"fail", "inconclusive", "quarantined"}:
                raise ValueError(f"Candidate {self.pending} is {status}; validate/activate or discard it before another proposal")
            if value["parent"] != self.pending:
                raise ValueError(f"Repair must name the failed candidate {self.pending} as parent, or discard it")
            parent = self.candidates[self.pending]
            if value["implementation"] == parent["implementation"] and observation in parent["evidence"]:
                raise ValueError("Repair must change the implementation or provide a new environment observation")
        elif self.closed_observations.get(value["protocol"]) == observation:
            raise ValueError("Use the current tools/policy and obtain new environment evidence before another proposal for this protocol")
        candidate = {**value, "scope": "this_task_only", "dependencies": ["python-stdlib"],
                     "protocol_version": PROTOCOL_VERSION}
        ident = digest(candidate)
        self.candidates[ident] = candidate
        self.proposals[fingerprint] = ident
        self.pending = ident
        (self.directory / f"{ident}.json").write_text(encoded(candidate))
        self.broker.record("candidate.created", {"candidate_id": ident, **candidate})
        return {"candidate_id": ident, "status": "unvalidated", "publish_eligible": False}

    def validate(self, ident):
        """Run the immutable protocol and separate local eligibility from publication."""
        if not self.broker.settled:
            raise ValueError("Cannot validate or switch versions while execution is unresolved")
        candidate = self.candidates[ident]
        if ident in self.reports:
            self.broker.record("validation.reused", {"candidate_id": ident})
            return self.reports[ident]
        if ident != self.pending or ident in self.discarded:
            raise ValueError("Only the pending candidate can receive a new validation")
        protocol = candidate["protocol"]
        job = {"candidate_id": ident, "protocol": protocol, "protocol_version": PROTOCOL_VERSION,
               "checker": "host-fixed-oracles-v1", "scope": "this_task_only", "started": time.time()}
        self.broker.record("validation.job", job)
        checks = []
        def check(label, function):
            """Retain every fresh check result, including execution errors."""
            try:
                passed, evidence = function()
                checks.append({"check": label, "status": "pass" if passed else "fail", "evidence": evidence})
            except Exception as exc:
                checks.append({"check": label, "status": "fail", "error": str(exc)})
        implementation = candidate["implementation"]
        if protocol == "feedback-policy-v1":
            def contract():
                """Check structured policy rules against the immutable kernel constraints."""
                p = implementation
                valid = (isinstance(p, dict) and set(p) == {"on_prediction_error", "reasoning_on_uncertainty", "completion_requires_evidence", "recovery_note"}
                    and p["on_prediction_error"] in {"reobserve", "revise_action", "repair_tool"}
                    and p["reasoning_on_uncertainty"] == "high" and p["completion_requires_evidence"] is True
                    and isinstance(p["recovery_note"], str) and 0 < len(p["recovery_note"]) <= 1500)
                return valid, {"oracle": "immutable-policy-contract", "kernel_unchanged": valid}
            check("policy_contract", contract)
            # Fresh policy interpreter probes, distinct from model-authored explanations.
            if all(c["status"] == "pass" for c in checks):
                from .state import choose_policy
                check("fresh_feedback", lambda: (choose_policy(implementation, "contradicted")["next"] == implementation["on_prediction_error"], {"feedback": "contradicted"}))
                check("fresh_success", lambda: (choose_policy(implementation, "supported")["next"] == "continue", {"feedback": "supported"}))
        else:
            if protocol == "angle-delta-v1":
                samples = [{"current": a, "target": b} for a, b in [(0, 90), (350, 10), (10, 350), (0, 180), (720, -90), (27.5, -371.25)]]
                oracle = lambda v: (v["target"] - v["current"] + 180) % 360 - 180
            else:
                samples = [{"angle": n} for n in [-360, -32.5, -2, 0, 22, 179]]
                oracle = lambda v: {"direction": "left" if v["angle"] >= 0 else "right", "degrees": max(10, min(120, abs(v["angle"])))}
            for index, value in enumerate(samples):
                def numerical(value=value):
                    """Execute a fresh isolated sample and compare it with the host oracle."""
                    if not isinstance(implementation, str):
                        raise ValueError("Python implementation must define run(input, tools)")
                    remaining = min(20, self.broker.deadline - time.monotonic())
                    if remaining <= 0:
                        raise TimeoutError("Episode deadline during validation")
                    got = run_program(implementation, value, timeout=remaining)
                    expected = oracle(value)
                    ok = (type(got) in (int, float) and math.isclose(got, expected, abs_tol=1e-9)) if isinstance(expected, (int, float)) else got == expected
                    self.broker.counts["compute"] += 1
                    return ok, {"input": value, "actual": got, "expected": expected, "oracle": "host-fixed-numerical-v1"}
                check(f"fresh_case_{index}", numerical)
        passed = bool(checks) and all(c["status"] == "pass" for c in checks)
        review = {"status": "not_required"}
        if protocol == "feedback-policy-v1" and passed:
            review = self.review(candidate, checks) if self.review else {"status": "inconclusive", "reason": "Independent review unavailable"}
            passed = review.get("status") == "pass"
        status = "pass" if passed else "inconclusive" if review.get("status") == "inconclusive" else "fail"
        report = {**job, "checks": checks, "review": review, "finished": time.time(), "status": status}
        release = {"candidate_id": ident, "report_id": digest(report), "local_eligible": passed,
                   "publish_eligible": False, "scope": "this_task_only", "reason": "Local validation " + status,
                   "publish_reason": "Pilot never publishes cross-task"}
        self.reports[ident] = {"report": report, "release": release}
        self.broker.record("validation.report", report)
        self.broker.record("release.decision", release)
        if not passed and any(c["status"] == "fail" for c in checks):
            self.health[ident] = "quarantined"
            self.broker.record("candidate.quarantined", {"candidate_id": ident, "reason": "Confirmed contract/numerical defect"})
        return self.reports[ident]

    def activate(self, ident, *, rollback=False):
        """Switch a passing candidate only at a settled execution boundary."""
        if not self.broker.settled:
            raise ValueError("Version activation requires a settled execution boundary")
        if self.health.get(ident) == "quarantined" or not self.reports.get(ident, {}).get("release", {}).get("local_eligible"):
            raise ValueError("Candidate is not locally eligible")
        candidate = self.candidates[ident]
        if digest(candidate) != ident:
            raise ValueError("Candidate hash mismatch")
        protocol = candidate["protocol"]
        previous = self.active.get(protocol)
        if ident in self.discarded:
            raise ValueError("Discarded candidate cannot be activated")
        if previous == ident:
            return {"active": dict(self.active), "policy": candidate["implementation"] if protocol == "feedback-policy-v1" else None}
        if ident != self.pending and not rollback:
            raise ValueError("Only the pending validated candidate can be activated")
        self.active[protocol] = ident
        self.closed_observations[protocol] = self.broker.binding.observation_id
        if self.pending == ident:
            self.pending = None
        self.broker.record("candidate.activated", {"candidate_id": ident, "previous": previous, "scope": "this_task_only"})
        return {"active": dict(self.active), "policy": candidate["implementation"] if protocol == "feedback-policy-v1" else None}

    def discard(self, ident, reason):
        """Abandon unfinished adaptation explicitly while preserving its audit trail."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Discard requires a reason")
        candidate = self.candidates[ident]
        if ident in self.discarded:
            return {"candidate_id": ident, "status": "discarded"}
        if not self.broker.settled or ident != self.pending:
            raise ValueError("Discard requires the pending candidate and settled execution")
        self.discarded.add(ident)
        self.pending = None
        self.closed_observations[candidate["protocol"]] = self.broker.binding.observation_id
        self.broker.record("candidate.discarded", {"candidate_id": ident, "reason": reason})
        return {"candidate_id": ident, "status": "discarded"}

    def compute(self, ident, value):
        """Invoke an active isolated tool and quarantine confirmed runtime defects."""
        candidate = self.candidates[ident]
        if self.active.get(candidate["protocol"]) != ident or candidate["protocol"] == "feedback-policy-v1":
            raise ValueError("Only an active validated computational tool can run")
        if not self.broker.settled or time.monotonic() >= self.broker.deadline:
            raise ValueError("Execution unsettled or deadline expired")
        self.broker.counts["compute"] += 1
        try:
            output = run_program(candidate["implementation"], value, timeout=min(30, self.broker.deadline-time.monotonic()))
        except Exception:
            self.health[ident] = "quarantined"
            if self.pending is None:
                self.pending = ident
            parent = candidate["parent"]
            self.active.pop(candidate["protocol"], None)
            self.broker.record("candidate.quarantined", {"candidate_id": ident, "reason": "Runtime defect", "parent": parent})
            if parent and parent not in self.discarded and self.health.get(parent) != "quarantined" and self.reports.get(parent, {}).get("release", {}).get("local_eligible"):
                self.activate(parent, rollback=True)
            raise
        self.broker.record("compute.result", {"candidate_id": ident, "input": value, "output": output})
        return {"candidate_id": ident, "output": output}
