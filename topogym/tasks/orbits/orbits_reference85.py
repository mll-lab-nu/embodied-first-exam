"""orbits: reference85. Difficulty is a design target, not a qualification."""

from .common import OrbitsTask


class OrbitsReference85Task(OrbitsTask):
    variation_id = 'orbits_reference85'
    family_id = 'reference85'
    model_revision = 'simulator_v1_fem_soft50_fine_v1'
    difficulty = None
