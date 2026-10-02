"""hedgehog_in_cage: below_easy, very_easy. The ball rests where a translation-only exit exists."""

from topogym.tasks.base import merge_parameters
from .below_easy import HedgehogBelowEasyTask


class HedgehogInCageVeryEasyTask(HedgehogBelowEasyTask):
    # Gravity-settled on CPU (Genesis, 5 s) from a design-search candidate, 2026-10-02.
    variant_parameters = {"ball_pose": {"position_m": [-0.011509, -0.004635, -0.054367],
                                        "quaternion_wxyz": [0.42572, 0.657714, -0.613329, 0.100011]}}
    defaults = merge_parameters(HedgehogBelowEasyTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_very_easy'
    difficulty = 'very_easy'
