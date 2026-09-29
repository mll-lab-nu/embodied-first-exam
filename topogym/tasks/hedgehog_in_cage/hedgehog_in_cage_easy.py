"""hedgehog_in_cage: classic_3star. Difficulty is a design target, not a qualification."""

from .common import HedgehogInCageTask


class HedgehogInCageEasyTask(HedgehogInCageTask):
    variation_id = 'hedgehog_in_cage_easy'
    family_id = 'classic_3star'
    model_revision = 'simulator_v1'
    difficulty = 'easy'
    fixed_parameters = ('scale',)
