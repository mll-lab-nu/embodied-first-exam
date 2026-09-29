"""cast_coil: baseline_assembly. Difficulty is a design target, not a qualification."""

from .common import CastCoilTask


class CastCoilEasyTask(CastCoilTask):
    variation_id = 'cast_coil_easy'
    family_id = 'baseline_assembly'
    model_revision = 'reference_v1'
    difficulty = 'easy'
    fixed_parameters = ('scale', 'objective')
