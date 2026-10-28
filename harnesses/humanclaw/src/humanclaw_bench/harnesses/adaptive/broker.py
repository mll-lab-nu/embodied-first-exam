"""Durable admission and receipts, independent of simulator/tool vocabulary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any


def encoded(value: Any) -> str:
    """Serialize finite JSON deterministically for durable identities."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(value: Any) -> str:
    """Hash the canonical serialization of a versioned record."""
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class Broker:
    """Only the owner thread dispatches. Unknown execution is never replayed.

    Binding contract: catalog(), observation_id, execute(tool, arguments), and
    optional reconcile(request). A receipt must be committed before being sent.
    The journal does not restore a simulator; reopening requires reconciliation.
    """

    def __init__(self, path: Path, binding, deadline: float):
        """Bind the task-local runtime dependencies and initial state."""
        self.binding, self.deadline = binding, deadline
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            state TEXT NOT NULL, request TEXT NOT NULL, receipt TEXT);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, kind TEXT, payload TEXT);
          CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        self.db.execute("UPDATE requests SET state='indeterminate' WHERE state IN ('accepted','running')")
        self.db.commit()
        self.counts = dict(compute=0, observations=0, physical_operations=0, control_steps=0)

    def record(self, kind: str, data: Any):
        """Append and commit a causally ordered audit event."""
        self.db.execute("INSERT INTO events(kind,payload) VALUES (?,?)", (kind, encoded(data)))
        self.db.commit()

    def remember_observation(self, observation, execution_id=None):
        """Persist public evidence independently of the request projection."""
        value = {**observation, "execution_id": execution_id, "captured_at": time.time(), "provenance": "observed"}
        previous = self.db.execute("SELECT payload FROM observations WHERE id=?", (observation["id"],)).fetchone()
        if previous:
            return json.loads(previous[0])
        self.db.execute("INSERT INTO observations VALUES (?,?)", (observation["id"], encoded(value)))
        self.db.commit()
        return value

    def evidence(self, references):
        """Load bounded original evidence by public observation identity."""
        if not isinstance(references, list) or not 1 <= len(references) <= 3:
            raise ValueError("Retrieve one to three evidence references per call")
        values = []
        for reference in references:
            row = self.db.execute("SELECT payload FROM observations WHERE id=?", (reference,)).fetchone()
            if not row:
                raise ValueError("Unknown evidence reference")
            values.append(json.loads(row[0]))
        return values

    @property
    def settled(self):
        """Return whether all admitted execution has a determinate outcome."""
        return self.db.execute("SELECT 1 FROM requests WHERE state IN ('accepted','running','indeterminate') LIMIT 1").fetchone() is None

    def receipt(self, request_id: str):
        """Recover a committed receipt without replaying the operation."""
        row = self.db.execute("SELECT state,receipt FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            return {"status": "unknown", "request_id": request_id}
        return json.loads(row[1]) if row[1] else {"status": row[0], "request_id": request_id,
            "reconciliation_required": True, "retry_allowed": False}

    def execute(self, request: dict):
        """Persist intent, check admission, dispatch once and commit its receipt."""
        ident = request.get("request_id")
        if not isinstance(ident, str) or not ident.strip():
            raise ValueError("A nonempty request_id is required")
        fingerprint = digest(request)
        old = self.db.execute("SELECT fingerprint FROM requests WHERE id=?", (ident,)).fetchone()
        if old:
            if old[0] != fingerprint:
                raise ValueError("request_id conflict: immutable request differs")
            self.record("execution.reused", {"request_id": ident})
            return self.receipt(ident)
        self.db.execute("INSERT INTO requests VALUES (?,?,?,?,NULL)", (ident, fingerprint, "accepted", encoded(request)))
        self.db.commit()  # Write-ahead intent, before any effect.
        try:
            if time.monotonic() >= self.deadline:
                raise ValueError("Episode deadline: new admission closed")
            unresolved = self.db.execute("SELECT id FROM requests WHERE state='indeterminate'").fetchall()
            if unresolved:
                raise ValueError("Unreconciled execution: no further dispatch")
            catalog = {t["id"]: t for t in self.binding.catalog()}
            tool = catalog.get(request.get("tool"))
            if not tool or tool["readiness"] != "ready":
                raise ValueError("Tool is unavailable or its effects are unknown")
            if tool["version"] != request.get("tool_version"):
                raise ValueError("Tool schema/version changed: rediscover before executing")
            import jsonschema
            jsonschema.validate(request.get("arguments"), tool["input_schema"])
            decision = request.get("decision")
            if not isinstance(decision, dict) or any(not decision.get(k) for k in ("intent", "expected_outcome", "evidence", "policy_version")):
                raise ValueError("DecisionRecord requires intent, expected_outcome, evidence and policy_version")
            if tool["requires_current_observation"] and self.binding.observation_id not in decision["evidence"]:
                raise ValueError("Operation requires the current observation")
            if tool["effect"] not in {"compute", "observe", "physical", "terminate", "program"}:
                raise ValueError("Unknown effect must be resolved before execution")
            if hasattr(self.binding, "validate_request"):
                self.binding.validate_request(request)
        except Exception as exc:
            return self._commit(ident, "rejected", {"error": str(exc), "executed": False})
        self.db.execute("UPDATE requests SET state='running' WHERE id=?", (ident,))
        self.db.commit()
        self.record("execution.started", request)
        try:
            if hasattr(self.binding, "execute_request"):
                result = self.binding.execute_request(tool["id"], request["arguments"], request)
            else:
                result = self.binding.execute(tool["id"], request["arguments"])
        except BaseException as exc:
            # Dispatch may already have changed the world. No guessed cancellation.
            self._commit(ident, "indeterminate", {"error_type": type(exc).__name__, "retry_allowed": False})
            raise
        status = "rejected" if result.get("isError") else "completed"
        if status == "completed":
            for observation in result.get("observations", []):
                self.remember_observation(observation, ident)
            self.counts["physical_operations"] += int(tool["effect"] in {"physical", "terminate"})
            self.counts["compute"] += int(tool["effect"] in {"compute", "program"})
            self.counts["observations"] += int(bool(result.get("observations")))
            self.counts["control_steps"] += result.get("control_steps", 0)
        return self._commit(ident, status, {"tool": tool["id"], "tool_version": tool["version"],
            "parent_id": request.get("parent_id"), "decision": request["decision"], "result": result,
            "counts": dict(self.counts), "completed_after_deadline": time.monotonic() >= self.deadline})

    def _commit(self, ident, state, data):
        """Durably record a terminal or indeterminate execution outcome."""
        receipt = {"schema": "execution-receipt-v1", "request_id": ident, "status": state, **data}
        self.db.execute("UPDATE requests SET state=?,receipt=? WHERE id=?", (state, encoded(receipt), ident))
        self.db.commit()
        self.record("execution.receipt", receipt)
        return receipt

    def close(self):
        """Close this task boundary and preserve committed audit records."""
        self.db.close()
