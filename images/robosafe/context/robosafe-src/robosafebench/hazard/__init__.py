"""The hazard state layer: what the physics engine does not model (heat, electricity, liquids, exposure) and the rules
that turn a physical situation into an event. Deterministic; lives in the service process. See docs/CONTRACTS.md 3."""
from .state import Device, State, Vessel, Zone
from . import rules

__all__ = ["State", "Device", "Vessel", "Zone", "rules"]
