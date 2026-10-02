"""hedgehog_in_cage: below_easy, easier. The ball rests where one in-grasp roll is needed before it exits."""

from topogym.tasks.base import merge_parameters
from .below_easy import HedgehogBelowEasyTask


class HedgehogInCageEasierTask(HedgehogBelowEasyTask):
    # Gravity-settled on CPU (Genesis, 5 s) from a design-search candidate, 2026-10-02.
    # A 60 mm spike points at the robot and reaches 19 mm outside the cage wall.
    variant_parameters = {"ball_pose": {"position_m": [0., 0., -0.058757],
                                        "quaternion_wxyz": [0.419726, 0.426712, 0.800963, -0.014313]}}
    defaults = merge_parameters(HedgehogBelowEasyTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_easier'
    difficulty = 'easier'
