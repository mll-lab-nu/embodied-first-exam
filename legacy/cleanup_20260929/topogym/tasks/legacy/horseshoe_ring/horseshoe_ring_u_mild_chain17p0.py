"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingUMildChain17P0Task(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_u_mild_chain17p0'
    family_id = 'u_mild_chain17p0'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/u_mild_chain17p0.json'
