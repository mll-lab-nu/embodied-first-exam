from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class StabilityLimits:
    """Generic safety thresholds used before a solver is pushed too hard."""

    max_follow_error: float | None = None
    max_target_error: float | None = None
    min_gap: float | None = None
    max_contact_particles: int | None = None
    max_downward_follow_z: float | None = None


@dataclass(frozen=True)
class StabilitySample:
    """One runtime measurement from a primitive, planner segment, or verifier."""

    phase: str
    follow_error: float | None = None
    target_error: float | None = None
    min_gap: float | None = None
    contact_particles: int | None = None
    downward_follow_z: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def metadata_dict(self) -> dict[str, Any]:
        return dict(self.metadata)


@dataclass(frozen=True)
class StabilityDecision:
    """Result of checking a sample against limits."""

    ok: bool
    reason: str | None = None
    severity: str = "ok"
    sample: StabilitySample | None = None

    @property
    def should_abort(self) -> bool:
        return not self.ok


def evaluate_stability_sample(
    sample: StabilitySample,
    limits: StabilityLimits,
) -> StabilityDecision:
    """Return a soft-abort decision for common physical stability signals."""

    if (
        limits.max_follow_error is not None
        and sample.follow_error is not None
        and sample.follow_error > limits.max_follow_error
    ):
        return StabilityDecision(
            ok=False,
            reason=(
                f"follow_error {sample.follow_error:.4f} exceeds "
                f"{limits.max_follow_error:.4f}"
            ),
            severity="abort",
            sample=sample,
        )
    if (
        limits.max_target_error is not None
        and sample.target_error is not None
        and sample.target_error > limits.max_target_error
    ):
        return StabilityDecision(
            ok=False,
            reason=(
                f"target_error {sample.target_error:.4f} exceeds "
                f"{limits.max_target_error:.4f}"
            ),
            severity="abort",
            sample=sample,
        )
    if (
        limits.min_gap is not None
        and sample.min_gap is not None
        and sample.min_gap < limits.min_gap
    ):
        return StabilityDecision(
            ok=False,
            reason=f"min_gap {sample.min_gap:.4f} below {limits.min_gap:.4f}",
            severity="abort",
            sample=sample,
        )
    if (
        limits.max_contact_particles is not None
        and sample.contact_particles is not None
        and sample.contact_particles > limits.max_contact_particles
    ):
        return StabilityDecision(
            ok=False,
            reason=(
                f"contact_particles {sample.contact_particles} exceeds "
                f"{limits.max_contact_particles}"
            ),
            severity="abort",
            sample=sample,
        )
    if (
        limits.max_downward_follow_z is not None
        and sample.downward_follow_z is not None
        and sample.downward_follow_z > limits.max_downward_follow_z
    ):
        return StabilityDecision(
            ok=False,
            reason=(
                f"downward_follow_z {sample.downward_follow_z:.4f} exceeds "
                f"{limits.max_downward_follow_z:.4f}"
            ),
            severity="abort",
            sample=sample,
        )
    return StabilityDecision(ok=True, sample=sample)


def format_stability_decision(decision: StabilityDecision) -> str:
    if decision.ok:
        return "stable"
    sample_text = ""
    if decision.sample is not None:
        sample_text = f" phase={decision.sample.phase}"
    return f"{decision.severity}:{decision.reason}{sample_text}"
