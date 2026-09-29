"""Physical material declarations and validation, without importing Genesis."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping


@dataclass(frozen=True)
class MaterialSpec:
    model: str = "rigid"
    parameters: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if self.model not in {"rigid", "pbd_cloth", "pbd_elastic", "fem_elastic"}:
            raise ValueError(f"Unknown physical material: {self.model}")
        for key, value in self.parameters.items():
            if isinstance(value, (int, float)) and not math.isfinite(value):
                raise ValueError(f"Material parameter {key} must be finite")
        for key in ("rho", "E"):
            if key in self.parameters and self.parameters[key] <= 0:
                raise ValueError(f"Material {key} must be positive")
        if "nu" in self.parameters and not -1 < self.parameters["nu"] < 0.5:
            raise ValueError("Poisson ratio must lie strictly between -1 and 0.5")
        for key in (
            "friction",
            "friction_mu",
            "stretch_compliance",
            "bending_compliance",
        ):
            if key in self.parameters and self.parameters[key] < 0:
                raise ValueError(f"Material {key} cannot be negative")


def rope_fem_parameters():
    """Soft v13 material; task qualification and extra damping are separate."""
    return dict(
        model="stable_neohookean", E=5.0e4, nu=0.30, rho=650.0, friction_mu=0.3
    )


def rope_ipc_parameters():
    """Contact distance used with the fine FEM rope skin, in metres."""
    return dict(contact_d_hat=0.0002)
