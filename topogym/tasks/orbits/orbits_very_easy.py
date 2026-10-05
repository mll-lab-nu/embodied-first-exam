"""Single ball-topped post: lift the cord loop clear and place the whole target."""
from topogym.tasks.base import merge_parameters
from .below_easy import OrbitsBelowEasyTask


class OrbitsVeryEasyTask(OrbitsBelowEasyTask):
    variation_id = 'orbits_very_easy'
    family_id = 'single_stopper_post'
    difficulty = 'very_easy'
    placement_remainder_description = 'the fixed post, stopper ball and base'
    variant_parameters = merge_parameters(OrbitsBelowEasyTask.variant_parameters,
                                          {'geometry': {'ring_count': 0}})
    defaults = merge_parameters(OrbitsBelowEasyTask.defaults, variant_parameters)
