"""Shared token settings; no YAML, provider SDK or runner dependencies."""
from dataclasses import dataclass
from .types import BudgetPolicy


def validate_usage(value):
    value = {"mode": "off"} if value is None else value
    if not isinstance(value, dict):
        raise ValueError("usage must be a mapping")
    if value == {"mode": "off"}:
        return dict(mode="off", enforcement="not_enforced", input_tokens=None, output_tokens=None)
    allowed = {"mode", "scope", "limits", "on_usage_unavailable", "watchdog_interval_ms", "stop_grace_ms"}
    if set(value) - allowed or value.get("mode") not in {"observed", "strict"}:
        raise ValueError("Invalid usage configuration; limits with off are not enforced")
    if value.get("scope", "trial") != "trial" or value.get("on_usage_unavailable", "fail") != "fail":
        raise ValueError("Only trial scope and on_usage_unavailable: fail are supported")
    limits = value.get("limits", {})
    if not isinstance(limits, dict) or set(limits) - {"input_tokens", "output_tokens"}:
        raise ValueError("Use separate input_tokens and output_tokens limits")
    policy = BudgetPolicy(**limits, mode=value["mode"])
    result = dict(mode=policy.mode, scope="trial", limits=dict(input_tokens=policy.input_tokens,
        output_tokens=policy.output_tokens), on_usage_unavailable="fail",
        watchdog_interval_ms=value.get("watchdog_interval_ms", 100), stop_grace_ms=value.get("stop_grace_ms", 1000))
    for key, maximum in (("watchdog_interval_ms", 1000), ("stop_grace_ms", 10000)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise ValueError(f"{key} must be an integer in [1, {maximum}]")
    return result


@dataclass(frozen=True)
class BudgetSettings:
    policy: BudgetPolicy
    watchdog_interval_ms: int = 100
    stop_grace_ms: int = 1000

    def __post_init__(self):
        if not isinstance(self.policy, BudgetPolicy):
            raise ValueError("BudgetSettings requires a BudgetPolicy")
        for key, maximum in (("watchdog_interval_ms", 1000), ("stop_grace_ms", 10000)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{key} must be an integer in [1, {maximum}]")

    @classmethod
    def from_mapping(cls, value):
        settings = validate_usage(value)
        if settings["mode"] == "off":
            raise ValueError("An active pipeline requires observed or strict mode")
        return cls(BudgetPolicy(**settings["limits"], mode=settings["mode"]),
                   settings["watchdog_interval_ms"], settings["stop_grace_ms"])
