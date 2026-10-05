"""Approved single-post and single-ring Orbits variants.

Both retain the shared FEM cord, permanent handle connections and whole-target
placement goal. Difficulty names describe design intent, not solver qualification.
"""
from topogym.tasks.base import merge_parameters
from .common import OrbitsTask


class OrbitsBelowEasyTask(OrbitsTask):
    variant_parameters = {
        'linear_scale': .85,
        'cord_profile': 'below_easy_external_handle_v1',
        'geometry': {
            'ring_count': 1,
            'ring_radius_m': .090,
            'post_spacing_m': .112,
            'lowest_ring_z_m': .100,
            'base_length_m': .360,
            'base_width_m': .230,
            'bight_radius_m': .028,
            'handle_bend_radius_m': .020,
        },
    }
    defaults = merge_parameters(OrbitsTask.defaults, variant_parameters)
    fixed_parameters = ('linear_scale', 'cord_profile', 'geometry')
    model_revision = 'below_easy_v1_fem_soft50_fine_v1'
