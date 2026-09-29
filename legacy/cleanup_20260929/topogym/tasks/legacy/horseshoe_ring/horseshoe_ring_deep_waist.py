"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingDeepWaistTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_deep_waist'
    family_id = 'deep_waist'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/deep_waist.json'
