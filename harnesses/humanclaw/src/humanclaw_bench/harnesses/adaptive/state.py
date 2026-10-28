"""Evidence-linked task memory and feedback policy, separate from chat history."""
from .broker import digest


DEFAULT_POLICY = {"on_prediction_error": "revise_action", "reasoning_on_uncertainty": "high",
                  "completion_requires_evidence": True, "recovery_note": "Compare the last expected outcome with new public evidence; revise an ineffective approach."}


def choose_policy(policy, feedback):
    """Select effort and recovery from the current prediction feedback."""
    return {"effort": "high" if feedback in {"contradicted", "unknown"} else "medium",
            "next": policy["on_prediction_error"] if feedback == "contradicted" else "inspect_evidence" if feedback == "unknown" else "continue"}


class TaskState:
    """Persist evidence-linked interpretations independently of projected chat."""
    def __init__(self, broker, instruction):
        """Bind the task-local runtime dependencies and initial state."""
        self.broker = broker
        self.policy = dict(DEFAULT_POLICY)
        self.policy_version = digest(self.policy)
        self.data = {"instruction": instruction, "claims": [], "subgoals": [], "failures": [],
                     "feedback": "unknown", "completion": "unknown", "expected_outcome": None, "pinned_evidence": []}
        self.known_evidence = {broker.binding.observation_id} if broker.binding.observation_id else set()
        self.memory_version = 0

    def update(self, update):
        """Validate provenance and dependencies before committing task memory."""
        allowed = {"claims", "subgoals", "feedback", "completion", "failure", "pinned_evidence"}
        if set(update) - allowed:
            raise ValueError("Unsupported memory fields")
        claims = update.get("claims", [])
        if "pinned_evidence" in update:
            refs = update["pinned_evidence"]
            if not isinstance(refs, list) or len(refs) > 2 or any(ref not in self.known_evidence for ref in refs):
                raise ValueError("Pin at most two known evidence references")
        for claim in claims:
            if set(claim) != {"text", "evidence", "status"} or claim["status"] not in {"inferred", "unknown", "contradicted"}:
                raise ValueError("Model claims must retain inferred/unknown/contradicted provenance")
            if not claim["evidence"] or any(ref not in self.known_evidence for ref in claim["evidence"]):
                raise ValueError("Claim references unknown evidence")
        for key in ("feedback", "completion"):
            if key in update and update[key] not in {"supported", "contradicted", "unknown"}:
                raise ValueError("Expected supported, contradicted or unknown")
        current = self.broker.binding.observation_id
        needs_observation = "completion" in update or ("feedback" in update and current is not None)
        if needs_observation and not any(current in c["evidence"] for c in claims):
            raise ValueError("Feedback/completion interpretation needs current post-action evidence")
        if "feedback" in update and current is None and not claims:
            raise ValueError("Bootstrap feedback needs public source evidence in a claim")
        if "subgoals" in update:
            goals = update["subgoals"]
            if not isinstance(goals, list) or any(set(g) != {"id", "description", "depends_on", "status"} or g["status"] not in {"pending", "active", "supported", "unknown"} for g in goals):
                raise ValueError("Subgoals require id, description, depends_on and status")
            ids = {g["id"] for g in goals}
            if len(ids) != len(goals) or any(d not in ids or d == g["id"] for g in goals for d in g["depends_on"]):
                raise ValueError("Invalid subgoal dependency")
            def visit(ident, ancestors):
                """Reject cyclic task-subgoal dependencies."""
                if ident in ancestors:
                    raise ValueError("Cyclic subgoal dependency")
                for dep in next(g for g in goals if g["id"] == ident)["depends_on"]:
                    visit(dep, ancestors | {ident})
            for ident in ids:
                visit(ident, set())
            self.data["subgoals"] = goals
        self.data["claims"].extend(claims)
        if "pinned_evidence" in update:
            self.data["pinned_evidence"] = update["pinned_evidence"]
        for key in ("feedback", "completion"):
            if key in update:
                self.data[key] = update[key]
        if update.get("failure"):
            self.data["failures"].append({"description": update["failure"], "evidence": sorted(self.known_evidence)[-1:]})
        self.memory_version += 1
        self.broker.record("memory.updated", {"version": self.memory_version, "update": update})
        return self.snapshot()

    def snapshot(self):
        """Build a compact view while retaining the full append-only evidence log."""
        return {**self.data, "claims": self.data["claims"][-12:], "failures": self.data["failures"][-8:],
                "memory_version": self.memory_version, "policy_version": self.policy_version,
                "policy": self.policy, "recommendation": choose_policy(self.policy, self.data["feedback"]),
                "current_observation": self.broker.binding.observation_id,
                "provenance": "Model interpretations; evaluator success is not exposed"}
