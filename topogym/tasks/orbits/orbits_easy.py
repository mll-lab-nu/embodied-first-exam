"""orbits: 2_rings. Difficulty is a design target, not a qualification."""

from .common import OrbitsTask
from topogym.tasks.base import merge_parameters


class OrbitsEasyTask(OrbitsTask):
    variant_parameters = {'linear_scale': 0.85, 'cord_profile': 'compact_external_handle_v1',
                          'geometry': {'ring_count': 2, 'bight_radius_m': .028,
                                       'handle_bend_radius_m': .020}}
    defaults = merge_parameters(OrbitsTask.defaults, variant_parameters)
    variation_id = 'orbits_easy'
    family_id = '2_rings'
    model_revision = 'compact_external_handle_v1_fem_soft50_fine_v1'
    difficulty = 'easy'
    fixed_parameters = ('linear_scale', 'cord_profile', 'geometry')
