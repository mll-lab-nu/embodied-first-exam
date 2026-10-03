"""hedgehog_in_cage: gen_keyhole. Difficulty is a design target, not a qualification."""

from .common import HedgehogInCageTask
from topogym.tasks.base import merge_parameters


class HedgehogInCageHardTask(HedgehogInCageTask):
    variant_parameters = {'scale': 3.0, 'finish': 'wood'}
    defaults = merge_parameters(HedgehogInCageTask.defaults, variant_parameters)
    variation_id = 'hedgehog_in_cage_hard'
    family_id = 'gen_keyhole'
    model_revision = 'fixed_v3_s5_post'
    difficulty = 'hard'
    fixed_parameters = ('scale', 'finish')

    asset_resource = 'variations/hedgehog_in_cage/gen_keyhole_s5_post/assets.zip'
    prototype_resource = 'variations/hedgehog_in_cage/gen_keyhole_s5_post/prototype.json'
    # S5 stands on the fixed internal post after a 0.5 mm gravity settle.
    # This elevated default was approved on 2026-10-03; the robot still starts at home.
    initial_ball_pose = {
        'position_m': [-0.01583115692613754, -0.019335115098656826, 0.072],
        'quaternion_wxyz': [-3.5527802710877415e-07, -0.3072272672081592,
                           0.9516361732740086, 2.852426941313269e-07],
    }
