"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingWaistMildTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_waist_mild'
    family_id = 'waist_mild'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/waist_mild.json'
