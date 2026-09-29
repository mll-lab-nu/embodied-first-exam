"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingWaistEllipseTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_waist_ellipse'
    family_id = 'waist_ellipse'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/waist_ellipse.json'
