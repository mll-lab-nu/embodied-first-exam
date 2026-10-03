"""hedgehog_in_cage: below_easy, easier. At 108 mm the held ball leaves only after one wrist roll about the held spike."""

from topogym.tasks.base import merge_parameters
from .below_easy import HedgehogBelowEasyTask, cage


class HedgehogInCageEasierTask(HedgehogBelowEasyTask):
    variant_parameters = {"cage": cage(108.)}
    defaults = merge_parameters(HedgehogBelowEasyTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_easier'
    difficulty = 'easier'
