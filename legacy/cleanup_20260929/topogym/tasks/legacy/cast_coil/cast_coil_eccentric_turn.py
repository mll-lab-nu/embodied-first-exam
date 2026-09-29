"""cast_coil: eccentric_turn. Difficulty is a design target, not a qualification."""

from topogym.tasks.cast_coil.common import CastCoilTask


class CastCoilEccentricTurnTask(CastCoilTask):
    variation_id = 'cast_coil_eccentric_turn'
    family_id = 'eccentric_turn'
    model_revision = 'simulator_v1'
    difficulty = None

    template_resource = 'variations/cast_coil/eccentric_turn.json'
