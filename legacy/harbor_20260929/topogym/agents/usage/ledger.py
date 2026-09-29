"""Atomic per-trial admission, cumulative/delta accounting and immutable failure."""
import json
import time

from .budget import DIMENSIONS, check, stop
from .store import Store
from .types import BudgetPolicy, BudgetStopped, CapacityUnavailable, UsageEvent, token_count


class UsageLedger:
    def __init__(self, path, *, scope_id=None, policy=None):
        self.store = Store(path)
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            if state is None:
                if not scope_id or not isinstance(policy, BudgetPolicy):
                    raise ValueError("New ledger requires scope_id and BudgetPolicy")
                state = dict(schema_version=1, scope_id=scope_id, mode=policy.mode,
                    limits={key: getattr(policy, key) for key in DIMENSIONS},
                    usage={key: 0 for key in DIMENSIONS}, policy_revision=1,
                    closed=False, stop=None, created_at=time.time())
                self.store.write_scope(db, state)
            elif scope_id is not None and state["scope_id"] != scope_id:
                raise ValueError("Ledger scope mismatch")

    @staticmethod
    def _requests(db):
        return [json.loads(row[0]) for row in db.execute("SELECT data FROM requests")]

    @staticmethod
    def _request(db, identifier):
        row = db.execute("SELECT data FROM requests WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Unknown request")
        return json.loads(row[0])

    @staticmethod
    def _write_request(db, request):
        db.execute("INSERT OR REPLACE INTO requests VALUES (?, ?)",
                   (request["id"], json.dumps(request, allow_nan=False)))

    @staticmethod
    def _audit(db, kind, **values):
        row = dict(kind=kind, received_at=time.time(), received_monotonic_ns=time.monotonic_ns())
        row.update(values)
        db.execute("INSERT INTO audit(data) VALUES (?)", (json.dumps(row, allow_nan=False),))

    def _snapshot(self, db, state):
        requests = self._requests(db)
        pending = {key: sum(max(0, r["reservation"][key] - r["usage"][key])
            for r in requests if r["status"] != "complete") for key in DIMENSIONS}
        complete = all(r["status"] == "complete" for r in requests)
        by_model, by_route = {}, {}
        for request in requests:
            model = request["model"] or "unknown"
            row = by_model.setdefault(model, {k: 0 for k in DIMENSIONS})
            route = by_route.setdefault(request.get("route_id", "legacy_unspecified"), {k: 0 for k in DIMENSIONS})
            for key in DIMENSIONS:
                row[key] += request["usage"][key]
                route[key] += request["usage"][key]
        visible = {key: (state["usage"][key] if not requests or any(r["known"][key] for r in requests) else None)
                   for key in DIMENSIONS}
        return dict(**state, by_model=by_model, by_route=by_route, **visible, pending_reservation=pending,
            remaining={k: state["limits"][k] - state["usage"][k] - pending[k] for k in DIMENSIONS},
            overshoot={k: max(0, state["usage"][k] - state["limits"][k]) for k in DIMENSIONS},
            usage_complete=complete, request_count=len(requests),
            in_flight_requests=sum(r["status"] != "complete" for r in requests),
            budget_qualified=(state["closed"] and state["stop"] is None and complete),
            enforcement=state["mode"], failure_reason=state["stop"]["reason"] if state["stop"] else None)

    def snapshot(self):
        with self.store.transaction() as db:
            return self._snapshot(db, self.store.read_scope(db))

    def admit(self, request_id, *, source, input_bound=None, output_bound=0, model=None, parent_request_id=None, route_id="legacy_unspecified"):
        token_count(input_bound, "input_bound", optional=True)
        token_count(output_bound, "output_bound")
        if not request_id or not source or not isinstance(route_id, str) or not route_id:
            raise ValueError("Request, route and source identity required")
        blocked = False
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            if state["closed"]:
                if state["stop"]:
                    raise BudgetStopped(self._snapshot(db, state))
                raise RuntimeError("Trial has been finalized")
            if state["mode"] == "strict" and input_bound is None:
                raise ValueError("Strict admission requires a verified input upper bound")
            if db.execute("SELECT 1 FROM requests WHERE id=?", (request_id,)).fetchone():
                raise ValueError("Request already admitted; retries need a new upstream attempt ID")
            bounds = dict(input_tokens=input_bound or 0, output_tokens=output_bound)
            snapshot = self._snapshot(db, state)
            shortage = [k for k in DIMENSIONS if bounds[k] > snapshot["remaining"][k]
                or snapshot["remaining"][k] <= 0]
            if shortage:
                impossible = [k for k in shortage if bounds[k] > state["limits"][k] - state["usage"][k]
                              or state["limits"][k] - state["usage"][k] <= 0]
                if not impossible:
                    raise CapacityUnavailable("Budget reserved by in-flight requests")
                stop(state, "budget_exhausted", shortage)
                self._audit(db, "stop", stop=state["stop"], request_id=request_id, route_id=route_id)
                blocked = True
            else:
                self._write_request(db, dict(id=request_id, source=source, model=model, route_id=route_id,
                    parent_request_id=parent_request_id, reservation=bounds,
                    usage={k: 0 for k in DIMENSIONS}, known={k: False for k in DIMENSIONS},
                    sequence=-1, status="reserved", details={}))
                self._audit(db, "admit", request_id=request_id, bounds=bounds, model=model,
                            source=source, parent_request_id=parent_request_id, route_id=route_id)
            self.store.write_scope(db, state)
            result = self._snapshot(db, state)
        if blocked:
            raise BudgetStopped(result)
        return result

    def mark_sent(self, request_id):
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            if state["closed"]:
                raise BudgetStopped(self._snapshot(db, state)) if state["stop"] else RuntimeError("Trial closed")
            request = self._request(db, request_id)
            if request["status"] != "reserved":
                raise ValueError("Request already sent")
            request["status"] = "sent"
            self._write_request(db, request)

    def release_unsent(self, request_id):
        with self.store.transaction() as db:
            request = self._request(db, request_id)
            if request["status"] != "reserved":
                raise ValueError("Cannot release a sent request without a receipt")
            db.execute("DELETE FROM requests WHERE id=?", (request_id,))
            self._audit(db, "unsent_released", request_id=request_id)

    def record(self, event: UsageEvent):
        received_at, received_ns = time.time(), time.monotonic_ns()
        encoded = json.dumps(event.asdict(), sort_keys=True, allow_nan=False)
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            previous_stop = state["stop"]
            request = self._request(db, event.request_id)
            seen = db.execute("SELECT data FROM events WHERE request_id=? AND event_id=?",
                              (event.request_id, event.event_id)).fetchone()
            if seen:
                if seen[0] != encoded:
                    stop(state, "usage_conflict")
                    request["status"] = "unknown"
                    self._write_request(db, request)
            elif event.source != request["source"] or request["status"] == "reserved":
                stop(state, "usage_conflict")
                request["status"] = "unknown"
                self._write_request(db, request)
            else:
                db.execute("INSERT INTO events VALUES (?, ?, ?)", (event.request_id, event.event_id, encoded))
                self._audit(db, "usage", event=event.asdict(), received_at=received_at,
                            received_monotonic_ns=received_ns)
                state["last_usage_received_at"] = received_at
                state["last_usage_received_monotonic_ns"] = received_ns
                stale = event.sequence <= request["sequence"]
                if stale and event.semantics == "delta":
                    # A missing delta cannot safely be inferred from a sequence gap/reorder.
                    stop(state, "usage_conflict")
                    request["status"] = "unknown"
                    self._write_request(db, request)
                elif not stale:
                    invalid = request["status"] == "complete" or (
                        event.semantics == "delta" and event.sequence != request["sequence"] + 1)
                    for key in DIMENSIONS:
                        value = getattr(event, key)
                        if value is None:
                            continue
                        total = request["usage"][key] + value if event.semantics == "delta" else value
                        if total < request["usage"][key]:
                            invalid = True
                        else:
                            state["usage"][key] += total - request["usage"][key]
                            request["usage"][key] = total
                            request["known"][key] = True
                    request["sequence"] = event.sequence
                    request["details"].update(event.details)
                    if invalid:
                        stop(state, "usage_conflict")
                    if event.final:
                        if not all(request["known"].values()):
                            stop(state, "usage_incomplete")
                            request["status"] = "unknown"
                        else:
                            request["status"] = "complete"
                    if invalid:
                        request["status"] = "unknown"
                    check(state)
                    if state["mode"] == "strict":
                        violation = [k for k in DIMENSIONS if request["usage"][k] > request["reservation"][k]]
                        if violation:
                            stop(state, "reservation_violation", violation)
                    self._write_request(db, request)
            if previous_stop is None and state["stop"] is not None:
                self._audit(db, "stop", stop=state["stop"], request_id=event.request_id)
            self.store.write_scope(db, state)
            return self._snapshot(db, state)

    def fail(self, reason="usage_incomplete", *, request_id=None):
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            if request_id:
                request = self._request(db, request_id)
                if request["status"] != "complete":
                    request["status"] = "unknown"
                    self._write_request(db, request)
            stop(state, reason)
            self._audit(db, "failure", reason=reason, request_id=request_id)
            self.store.write_scope(db, state)
            return self._snapshot(db, state)

    def update_limits(self, *, input_tokens, output_tokens, expected_revision, actor, reason):
        policy = BudgetPolicy(input_tokens, output_tokens)
        if not actor or not reason:
            raise ValueError("Policy updates require actor and reason")
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            if state["policy_revision"] != expected_revision:
                raise ValueError("Stale policy revision")
            if state["closed"] and state["stop"] is None:
                raise ValueError("Successful trial has already been finalized")
            old = dict(state["limits"])
            state["limits"] = {k: getattr(policy, k) for k in DIMENSIONS}
            state["policy_revision"] += 1
            check(state)
            snapshot = self._snapshot(db, state)
            if state["mode"] == "strict" and any(snapshot["remaining"][k] < 0 for k in DIMENSIONS):
                stop(state, "budget_exhausted", [k for k in DIMENSIONS if snapshot["remaining"][k] < 0])
            self._audit(db, "policy_update", old=old, new=state["limits"], actor=actor,
                        reason=reason, policy_revision=state["policy_revision"])
            self.store.write_scope(db, state)
            return self._snapshot(db, state)

    def finalize(self, *, require_requests=False):
        with self.store.transaction() as db:
            state = self.store.read_scope(db)
            previous_stop, was_closed = state["stop"], state["closed"]
            snapshot = self._snapshot(db, state)
            if not snapshot["usage_complete"]:
                stop(state, "usage_incomplete")
            elif require_requests and not snapshot["request_count"]:
                stop(state, "usage_unavailable")
            state["closed"] = True
            if previous_stop is None and state["stop"] is not None:
                self._audit(db, "stop", stop=state["stop"])
            if not was_closed:
                self._audit(db, "finalize", scope_id=state["scope_id"])
            self.store.write_scope(db, state)
            return self._snapshot(db, state)
