"""hedgehog_in_cage: fixed_side_window. Difficulty is a design target, not a qualification."""

from topogym.tasks.hedgehog_in_cage.common import HedgehogInCageTask
from topogym.tasks.base import merge_parameters


class HedgehogInCageFixedSideWindowTask(HedgehogInCageTask):
    variant_parameters = {'scale': 3.0, 'finish': 'wood'}
    defaults = merge_parameters(HedgehogInCageTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_fixed_side_window'
    family_id = 'fixed_side_window'
    model_revision = 'fixed_v2'
    difficulty = None
    fixed_parameters = ('scale', 'finish')

    asset_resource = 'variations/hedgehog_in_cage/fixed_side_window/assets.zip'
    prototype_resource = 'variations/hedgehog_in_cage/fixed_side_window/prototype.json'
    initial_ball_pose = {'position_m': [0.034, -4.059817334521296e-09, -0.013093779603251927], 'quaternion_wxyz': [-0.08985502802683738, -0.38231459195763656, 0.8996677947434726, 0.19068163471078864]}
