"""blanket_flatten: fold_spiral. Difficulty is a design target, not a qualification."""

from .common import BlanketFlattenTask
from topogym.tasks.base import merge_parameters


class BlanketFlattenFoldSpiralTask(BlanketFlattenTask):
    variant_parameters = {'fold_count': 3, 'fold_angle_deg': 105.0, 'fold_angle_jitter_deg': 8.0, 'roll_fold_count': 7, 'roll_angle_deg': 55.0, 'roll_angle_jitter_deg': 10.0, 'roll_direction': -1, 'panel_width_jitter': 0.35, 'crease_slant': 0.045, 'drop_clearance_m': 0.02, 'pitch_deg': 15.0, 'tilt_deg': 3.0, 'yaw_deg': 25.0, 'max_attempts': 512, 'particle_size_m': 0.006, 'mesh_spacing_m': 0.009}
    defaults = merge_parameters(BlanketFlattenTask.defaults, variant_parameters)
    variation_id = 'blanket_flatten_fold_spiral'
    family_id = 'fold_spiral'
    model_revision = 'simulator_v1'
    difficulty = None
