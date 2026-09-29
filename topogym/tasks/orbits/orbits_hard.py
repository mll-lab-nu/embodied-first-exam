"""orbits: four_rings_compact. Difficulty is a design target, not a qualification."""

from .common import OrbitsTask
from topogym.tasks.base import merge_parameters


class OrbitsHardTask(OrbitsTask):
    variant_parameters = {'linear_scale': 0.85, 'cord_profile': 'compact_external_handle_v1',
                          'geometry': {'bight_radius_m': .028, 'handle_bend_radius_m': .020}}
    defaults = merge_parameters(OrbitsTask.defaults, variant_parameters)
    variation_id = 'orbits_hard'
    family_id = 'four_rings_compact'
    model_revision = 'compact_external_handle_v1_fem_soft50_fine_v1'
    difficulty = 'hard'
    fixed_parameters = ('linear_scale', 'cord_profile', 'geometry')
