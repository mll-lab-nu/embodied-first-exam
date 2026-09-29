"""Shared final settling measurements; TaskDefinition owns time and termination."""
from .settling import SettlingSpec, evaluate_settling, validate_reference

__all__ = ["SettlingSpec", "evaluate_settling", "validate_reference"]
