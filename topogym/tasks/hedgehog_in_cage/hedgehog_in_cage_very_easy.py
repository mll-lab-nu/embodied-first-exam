"""hedgehog_in_cage: below_easy, very_easy. 118 mm windows let the held ball leave by translation alone."""

from topogym.tasks.base import merge_parameters
from .below_easy import HedgehogBelowEasyTask, cage


class HedgehogInCageVeryEasyTask(HedgehogBelowEasyTask):
    variant_parameters = {"cage": cage(118.)}
    defaults = merge_parameters(HedgehogBelowEasyTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_very_easy'
    difficulty = 'very_easy'
