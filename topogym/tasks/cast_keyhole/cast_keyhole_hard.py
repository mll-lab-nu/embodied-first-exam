"""cast_keyhole: turnback. Difficulty is a design target, not a qualification."""

from .common import CastKeyholeTask


class CastKeyholeHardTask(CastKeyholeTask):
    variation_id = 'cast_keyhole_hard'
    family_id = 'turnback'
    model_revision = 'seed_families_v2'
    difficulty = 'hard'
    fixed_parameters = ('scale',)

    geometry_resource = 'variations/cast_keyhole/F3/geometry.json'
