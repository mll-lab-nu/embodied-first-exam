"""Time-sensitive grading; actual completion times remain evaluator-private."""

import math
from ..public.model import DT, HORIZON, SETTLE_TIME, SUCCESS_POINTS, TIME_BONUS_POINTS, ORACLE_TIME_RELAXATION


class SettlingTimer:
    """Credit the final uninterrupted settled interval, sampled at control rate.

    An early stable interval followed by takeoff or instability earns no early
    completion credit. Integer ticks avoid floating-point one-second boundaries.
    """

    def __init__(self):
        self.steps = 0
        self.consecutive_steps = 0
        self.completion_time_s = None

    def update(self, settled):
        self.steps += 1
        self.consecutive_steps = self.consecutive_steps + 1 if settled else 0
        if not settled:
            self.completion_time_s = None
        # N intervals require N+1 settled samples; do not credit the interval
        # before the first settled observation.
        elif self.consecutive_steps == round(SETTLE_TIME / DT) + 1:
            self.completion_time_s = round(self.steps * DT, 4)

    @property
    def duration_s(self):
        return max(0, self.consecutive_steps - 1) * DT


def full_credit_time(reference_time_s):
    if (
        type(reference_time_s) not in (int, float)
        or not math.isfinite(reference_time_s)
        or reference_time_s < SETTLE_TIME
    ):
        raise ValueError("Missing or invalid private oracle reference")
    threshold = reference_time_s * (1.0 + ORACLE_TIME_RELAXATION)
    if threshold >= HORIZON:
        raise ValueError("Oracle reference leaves no scoring interval before the deadline")
    return threshold


def score_metrics(success, completion_time_s, reference_time_s):
    # Validate even failed episodes: missing calibration is an infrastructure
    # error, never silently converted to an agent's zero.
    threshold = full_credit_time(reference_time_s)
    reference = {"oracle_reference_time_s": reference_time_s, "full_credit_time_s": threshold}
    if not success:
        return {**reference, "completion_time_s": None, "success_points": 0.0, "time_bonus_points": 0.0, "score": 0.0}
    if (
        completion_time_s is None
        or not math.isfinite(completion_time_s)
        or not SETTLE_TIME <= completion_time_s <= HORIZON
    ):
        raise ValueError("Successful landing requires a valid completion time")
    fraction = min(1.0, max(0.0, (HORIZON - completion_time_s) / (HORIZON - threshold)))
    bonus = TIME_BONUS_POINTS * fraction
    return {
        **reference,
        "completion_time_s": completion_time_s,
        "success_points": SUCCESS_POINTS,
        "time_bonus_points": bonus,
        "score": SUCCESS_POINTS + bonus,
    }
