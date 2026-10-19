"""Vacuum-specific name for the generic read-only physical approach observer."""
from embodied_safety_exam.hazard.contact_motion import ContactApproachMotion


class VacuumContactMotion(ContactApproachMotion):
    def __init__(self, world):
        super().__init__(world, "vacuum")
