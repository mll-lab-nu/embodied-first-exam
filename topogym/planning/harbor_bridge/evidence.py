"""Observe the actual evaluation Session without changing its rules or targets."""
from copy import deepcopy
import hashlib

import numpy as np

from .contracts import BridgeError, SmokeComplete


def evaluation_state(session):
    """Missing instrumentation is unknown, never evidence that a rule passed."""
    return dict(rules=deepcopy(getattr(session, "rules", None)),
                pbd_depenetration_margin_m_s=getattr(session, "pbd_depenetration_margin_m_s", None),
                particle_speed_guard=getattr(session, "particle_speed_guard", None),
                safety=deepcopy(session.safety(episode=True)) if callable(getattr(session, "safety", None)) else None,
                instability=deepcopy(getattr(session, "instability", None)))


class SessionEvidence:
    """Count committed steps and compare requested versus recorded float32 targets.

    The installed Session.step remains the only executor. In particular, a table
    guard adjustment is recorded as an adjustment, not disabled or called lossless.
    This is diagnostic agent evidence; independent verifier evidence is still required.
    """

    def __init__(self, session, *, smoke_steps=None):
        self.session = session
        self.original = session.step
        self.had_step_attribute = "step" in vars(session)
        self.start_step = session.n_steps
        self.calls = self.rows = self.changed = 0
        self.requested_hash, self.executed_hash = hashlib.sha256(), hashlib.sha256()
        self.max_delta = np.zeros(len(session.action_layout), dtype=float)
        self.examples = []
        self.initial = evaluation_state(session)
        self.before_rules = deepcopy(getattr(session, "rules", None))
        self.rule_objects = {name: getattr(session, name, None) for name in ("table_guard", "monitor")}

        def observed_step(action, **kwargs):
            if smoke_steps is not None and session.n_steps - self.start_step >= smoke_steps:
                raise SmokeComplete()
            requested = np.asarray(action, dtype=np.float32).reshape(-1).copy()
            before = session.n_steps
            self.calls += 1
            result = self.original(action, **kwargs)
            advanced = session.n_steps - before
            if advanced:
                if advanced != 1 or session._recording is None or not session._recording:
                    raise BridgeError("Session step did not commit one recorded action")
                actual = np.asarray(session._recording[-1], dtype=np.float32).reshape(-1)
                if requested.shape != actual.shape:
                    raise BridgeError("Recorded action layout differs from requested action")
                self.rows += 1
                self.requested_hash.update(requested.astype('<f4').tobytes())
                self.executed_hash.update(actual.astype('<f4').tobytes())
                delta = np.abs(actual.astype(float) - requested.astype(float))
                self.max_delta = np.maximum(self.max_delta, delta)
                if np.any(delta):
                    self.changed += 1
                    if len(self.examples) < 8:
                        self.examples.append(dict(control_step=session.n_steps,
                            requested=requested.tolist(), executed=actual.tolist(),
                            table_guard=deepcopy(getattr(session, "last_guard", None))))
            return result

        self.observed_step = observed_step
        session.step = observed_step

    def check(self):
        if self.session.step is not self.observed_step:
            raise BridgeError("Reference replaced the observed Session step")
        if self.rows != self.session.n_steps - self.start_step:
            raise BridgeError("Reference bypassed the observed Session step")
        if getattr(self.session, "rules", None) != self.before_rules or any(
                getattr(self.session, name, None) is not value for name, value in self.rule_objects.items()):
            raise BridgeError("Reference changed the installed evaluation rules")

    def report(self):
        return dict(initial=self.initial, final=evaluation_state(self.session),
                    action_transfer=dict(step_calls=self.calls, committed_rows=self.rows,
                        adjusted_rows=self.changed, requested_float32_sha256=self.requested_hash.hexdigest(),
                        executed_float32_sha256=self.executed_hash.hexdigest(),
                        max_abs_delta_by_action=dict(zip(self.session.action_layout, self.max_delta.tolist())),
                        first_adjustments=self.examples),
                    scope="evaluation Session observations; does not prove original-Env equivalence or verifier success")

    def close(self):
        if self.had_step_attribute:
            self.session.step = self.original
        elif "step" in vars(self.session):
            del self.session.step
