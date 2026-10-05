"""Keep an oracle's recorded joint targets inside the standard service's per-step joint limit.

The standard HTTP service moves an arm joint target at most ``rcb_topogym.JOINT_STEP_LIMIT_RAD`` per control step and
spreads a faster row over extra control steps (rules 2026-10-03); the standard oracle bridge refuses such a slowed row,
because the standard reference is the privileged oracle trajectory itself, replayed row by row. A privileged oracle
whose rows respect the limit is therefore standard-executable as recorded.

``RateLimiter.step(row)`` reaches ``row`` from the Session's current (guarded) targets along the straight joint-space
segment the row asked for, in as many control steps as the limit needs (each arm joint moves at most ``limit`` per
step; gripper targets switch on the first step, as in the service). A row within the limit is one ordinary step, so
an oracle that never exceeds the limit is unchanged. Every step goes through the caller's ``session.step``: rules,
table guard and recording stay with the Session. Only the timing of fast rows changes; no target is altered.

``mode="clamp"`` (oraclefix2) keeps one control step per row instead: an arm joint that asks for more than the limit
moves by the limit toward its target, and the remainder carries into the following rows, which a feedback policy
computes from the reached state again. The timing of every row is kept, and with it the rest of a closed-loop run,
which an inserted step would shift (Horseshoe hard: lab oraclefix2/exp/X11).
"""
from __future__ import annotations

import sys

import numpy as np

DEFAULT_LIMIT_RAD = .04   # rcb_topogym.JOINT_STEP_LIMIT_RAD (tooling 15) when the tooling module is not importable
MARGIN = .975             # stay clear of the service threshold after float32 rounding of the recorded rows


def joint_step_limit():
    tooling = sys.modules.get("rcb_topogym")
    return float(getattr(tooling, "JOINT_STEP_LIMIT_RAD", DEFAULT_LIMIT_RAD))


class RateLimiter:
    def __init__(self, session, limit_rad=None, *, mode="spread"):
        if mode not in ("spread", "clamp"):
            raise ValueError("Rate limiter mode must be spread or clamp")
        self.mode = mode
        self.session = session
        self.limit = (joint_step_limit() if limit_rad is None else float(limit_rad)) * MARGIN
        grips = sorted(set(session.robot.grip_index.values()))
        self.grips = np.asarray(grips, dtype=int)
        self.arm = np.asarray([i for i in range(len(session.action_layout)) if i not in grips], dtype=int)
        self.requested = self.slowed = self.inserted = self.clamped = 0
        self.max_request_rad = self.max_carried_rad = 0.

    def step(self, row):
        """Step toward ``row``; returns the last ``session.step`` result (True ends the caller's loop)."""
        s = self.session
        target = np.asarray(row, dtype=np.float32).reshape(-1).astype(np.float64)
        current = s.hold_action().astype(np.float64)
        reach = float(np.abs(target[self.arm] - current[self.arm]).max(initial=0.))
        self.requested += 1
        self.max_request_rad = max(self.max_request_rad, reach)
        if self.mode == "clamp":
            if reach > self.limit:
                delta = target[self.arm] - current[self.arm]
                target[self.arm] = current[self.arm] + np.clip(delta, -self.limit, self.limit)
                self.clamped += 1
                self.max_carried_rad = max(self.max_carried_rad, reach - self.limit)
            return s.step(target.astype(np.float32))
        n = max(1, int(np.ceil(reach / self.limit - 1e-9)))
        if n > 1:
            self.slowed += 1
        for k in range(1, n):
            # Re-anchor on the accepted (guarded) targets each step, so a guarded step never forces a jump later.
            current = s.hold_action().astype(np.float64)
            sub = current + (target - current) / (n - k + 1)
            sub[self.grips] = target[self.grips]
            self.inserted += 1
            if s.step(sub.astype(np.float32)):
                return True
        return s.step(target.astype(np.float32))

    def report(self):
        return dict(limit_rad=self.limit, mode=self.mode, requested_rows=self.requested, slowed_rows=self.slowed,
                    inserted_steps=self.inserted, clamped_rows=self.clamped, max_carried_rad=self.max_carried_rad,
                    max_requested_step_rad=self.max_request_rad,
                    scope="oracle-side timing only; the standard service limit and the bridge are unchanged")


def rate_limited_runner(session, *, control_mode="JOINT_ABS", limit_rad=None, mode="spread"):
    """A SessionPolicyRunner whose every committed row respects the standard joint-speed limit."""
    from topogym.planning.harbor_bridge.actions import SessionExecutor, SessionPolicyRunner, public_action, public_row

    limiter = RateLimiter(session, limit_rad, mode=mode)

    class RateLimitedExecutor(SessionExecutor):
        def step(self, action, *, mode="JOINT_ABS"):
            from topogym.robot.control import compile_action
            native = compile_action(self.session.env._robot, action, mode)
            return limiter.step(public_row(self.session, native))

        def step_public(self, row):
            return limiter.step(public_action(self.session, row))

    runner = SessionPolicyRunner(session, control_mode=control_mode)
    runner.executor = RateLimitedExecutor(session)
    runner.rate_limiter = limiter
    return runner
