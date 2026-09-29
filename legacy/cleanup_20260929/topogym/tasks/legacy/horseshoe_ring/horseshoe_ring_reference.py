"""horseshoe_ring: reference. Difficulty is a design target, not a qualification."""

from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingReferenceTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_reference'
    family_id = 'reference'
    model_revision = 'simulator_v1'
    difficulty = None
