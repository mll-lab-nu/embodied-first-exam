"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingDeepWaistChain17P5Task(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_deep_waist_chain17p5'
    family_id = 'deep_waist_chain17p5'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/deep_waist_chain17p5.json'
