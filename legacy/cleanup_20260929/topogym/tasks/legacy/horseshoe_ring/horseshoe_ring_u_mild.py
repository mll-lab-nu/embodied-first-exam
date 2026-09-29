"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingUMildTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_u_mild'
    family_id = 'u_mild'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/u_mild.json'
