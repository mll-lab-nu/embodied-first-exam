"""hedgehog_in_cage: below_easy, very_easy. The ball rests where a translation-only exit exists."""

from topogym.tasks.base import merge_parameters
from .below_easy import HedgehogBelowEasyTask


class HedgehogInCageVeryEasyTask(HedgehogBelowEasyTask):
    # Gravity-settled on CPU (Genesis, 5 s) from a design-search candidate, 2026-10-02.
    # A 60 mm spike points at the robot and reaches 19 mm outside the cage wall.
    variant_parameters = {"ball_pose": {"position_m": [0., 0., -0.056233],
                                        "quaternion_wxyz": [0.034671, -0.754386, -0.526716, -0.390218]}}
    defaults = merge_parameters(HedgehogBelowEasyTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_very_easy'
    difficulty = 'very_easy'
