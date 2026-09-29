"""cast_coil: split_turn_offset. Difficulty is a design target, not a qualification."""

from .common import CastCoilTask


class CastCoilHardTask(CastCoilTask):
    variation_id = 'cast_coil_hard'
    family_id = 'split_turn_offset'
    model_revision = 'seed_families_v1_9mm'
    difficulty = 'hard'
    fixed_parameters = ('scale', 'objective')

    template_resource = 'variations/cast_coil/split_turn_offset.json'
