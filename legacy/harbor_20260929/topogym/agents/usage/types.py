"""Shared counting contract. Totals include cache/reasoning exactly once."""
from dataclasses import asdict, dataclass, field


def token_count(value, name, *, optional=False):
    if optional and value is None:
        return value
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class BudgetPolicy:
    input_tokens: int = 50_000_000
    output_tokens: int = 20_000_000
    mode: str = "observed"

    def __post_init__(self):
        token_count(self.input_tokens, "input_tokens")
        token_count(self.output_tokens, "output_tokens")
        if self.mode not in {"observed", "strict"}:
            raise ValueError("Budget policy requires observed or strict mode")


@dataclass(frozen=True)
class UsageEvent:
    request_id: str
    event_id: str
    sequence: int
    source: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    semantics: str = "cumulative"
    final: bool = False
    details: dict = field(default_factory=dict)
    provider_event_at: str | None = None

    def __post_init__(self):
        if any(not isinstance(v, str) or not v for v in (self.request_id, self.event_id, self.source)):
            raise ValueError("Event identities must be nonempty strings")
        token_count(self.sequence, "sequence")
        token_count(self.input_tokens, "input_tokens", optional=True)
        token_count(self.output_tokens, "output_tokens", optional=True)
        if self.semantics not in {"cumulative", "delta"} or type(self.final) is not bool:
            raise ValueError("Invalid event semantics")

    def asdict(self):
        return asdict(self)


class BudgetStopped(RuntimeError):
    def __init__(self, snapshot):
        self.snapshot = snapshot
        super().__init__(snapshot["stop"]["reason"])


class CapacityUnavailable(RuntimeError):
    """In-flight reservations, not actual consumption, temporarily fill the budget."""
