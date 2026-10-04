"""Shared oracle parameter validation without CLI/snapshot dependencies."""
import math


def validate_parameters(values):
    for key in ("end_offset", "speed", "max_pull", "max_decisions", "tight_curl_m", "max_attempts"):
        if key in values and (isinstance(values[key], bool) or not isinstance(values[key], (int, float))
                              or not math.isfinite(values[key]) or values[key] <= 0):
            raise ValueError(f"{key} must be finite and positive")
    for key in ("close", "settle", "wait_hours"):
        if key in values and (isinstance(values[key], bool) or not isinstance(values[key], (int, float))
                              or not math.isfinite(values[key]) or values[key] < 0):
            raise ValueError(f"{key} must be finite and nonnegative")
    if values.get("max_nonprogress_decisions") is not None:
        value = values["max_nonprogress_decisions"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("max_nonprogress_decisions must be a nonnegative integer")
    if "full_pull" in values and not isinstance(values["full_pull"], bool):
        raise ValueError("full_pull must be boolean")


