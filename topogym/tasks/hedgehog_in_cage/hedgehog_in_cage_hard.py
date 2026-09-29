"""hedgehog_in_cage: gen_keyhole. Difficulty is a design target, not a qualification."""

from .common import HedgehogInCageTask
from topogym.tasks.base import merge_parameters


class HedgehogInCageHardTask(HedgehogInCageTask):
    variant_parameters = {'scale': 3.0, 'finish': 'wood'}
    defaults = merge_parameters(HedgehogInCageTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_hard'
    family_id = 'gen_keyhole'
    model_revision = 'fixed_v2'
    difficulty = 'hard'
    fixed_parameters = ('scale', 'finish')

    asset_resource = 'variations/hedgehog_in_cage/gen_keyhole/assets.zip'
    prototype_resource = 'variations/hedgehog_in_cage/gen_keyhole/prototype.json'
    initial_ball_pose = {'position_m': [0.034, -4.059817334521296e-09, -0.013093779603251927], 'quaternion_wxyz': [-0.08985502802683738, -0.38231459195763656, 0.8996677947434726, 0.19068163471078864]}
