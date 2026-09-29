"""cast_keyhole: eccentric_window. Difficulty is a design target, not a qualification."""

from .common import CastKeyholeTask


class CastKeyholeMediumTask(CastKeyholeTask):
    variation_id = 'cast_keyhole_medium'
    family_id = 'eccentric_window'
    model_revision = 'seed_families_v2'
    difficulty = 'medium'
    fixed_parameters = ('scale',)

    geometry_resource = 'variations/cast_keyhole/F2/geometry.json'
