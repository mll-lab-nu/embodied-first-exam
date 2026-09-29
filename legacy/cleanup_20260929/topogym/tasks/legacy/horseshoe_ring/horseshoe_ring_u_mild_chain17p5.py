"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingUMildChain17P5Task(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_u_mild_chain17p5'
    family_id = 'u_mild_chain17p5'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/u_mild_chain17p5.json'
