"""cast_keyhole: legacy_reference. Difficulty is a design target, not a qualification."""

from topogym.tasks.cast_keyhole.common import CastKeyholeTask


class CastKeyholeLegacyReferenceTask(CastKeyholeTask):
    variation_id = 'cast_keyhole_legacy_reference'
    family_id = 'legacy_reference'
    model_revision = 'simulator_v1'
    difficulty = None
