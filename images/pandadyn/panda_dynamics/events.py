"""Simulation-second events and uninterrupted hold predicates."""

from dataclasses import dataclass, field


@dataclass
class EventLedger:
    history: list[dict] = field(default_factory=list)
    holds: dict[str, float] = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    physical_success: bool = False
    valid: bool = True
    failure_reason: str | None = None

    def emit(self, name: str, time: float, **metrics):
        self.history.append(dict(name=name, time=round(time, 6), **metrics))

    def has(self, name: str) -> bool:
        return any(e["name"] == name for e in self.history)

    def first_time(self, name: str) -> float | None:
        return next((e["time"] for e in self.history if e["name"] == name), None)

    def once(self, name: str, time: float, **metrics):
        if not self.has(name):
            self.emit(name, time, **metrics)

    def ordered(self, *names: str) -> bool:
        times = [self.first_time(n) for n in names]
        return all(t is not None for t in times) and all(
            a < b for a, b in zip(times, times[1:])
        )

    def hold(self, name: str, condition: bool, time: float, duration: float) -> bool:
        if not condition:
            self.holds.pop(name, None)
            return False
        self.holds.setdefault(name, time)
        return time - self.holds[name] >= duration - 1e-9

    def fail(self, reason: str, time: float, invalid: bool = False):
        if self.failure_reason is None:
            self.failure_reason = reason
            self.emit("failure", time, reason=reason)
        if invalid:
            self.valid = False
