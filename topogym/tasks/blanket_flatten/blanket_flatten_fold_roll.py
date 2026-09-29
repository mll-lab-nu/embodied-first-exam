"""Retained simulator_v1 fold/roll setting, outside the gathered difficulty tiers."""
from .common import BlanketFlattenTask
from topogym.tasks.base import merge_parameters


class BlanketFlattenFoldRollTask(BlanketFlattenTask):
    variant_parameters = {'fold_count': 3, 'fold_angle_deg': 105.0, 'fold_angle_jitter_deg': 8.0, 'roll_fold_count': 5, 'roll_angle_deg': 54.0, 'roll_angle_jitter_deg': 12.0, 'roll_direction': -1, 'panel_width_jitter': 0.35, 'crease_slant': 0.045, 'drop_clearance_m': 0.025, 'pitch_deg': 155.0, 'tilt_deg': 5.0, 'yaw_deg': 25.0, 'max_attempts': 256}
    defaults = merge_parameters(BlanketFlattenTask.defaults, variant_parameters)
    variation_id = "blanket_flatten_fold_roll"
    family_id = "fold_roll"
    model_revision = "simulator_v1"
    fixed_parameters = ("fold_count", "roll_fold_count", "roll_angle_deg")
