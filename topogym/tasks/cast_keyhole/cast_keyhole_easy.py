"""cast_keyhole: long_stroke. Difficulty is a design target, not a qualification."""

from .common import CastKeyholeTask


class CastKeyholeEasyTask(CastKeyholeTask):
    variation_id = 'cast_keyhole_easy'
    family_id = 'long_stroke'
    model_revision = 'seed_families_v2'
    difficulty = 'easy'
    fixed_parameters = ('scale',)

    geometry_resource = 'variations/cast_keyhole/F1/geometry.json'
