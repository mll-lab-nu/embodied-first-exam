"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingWaistEllipseChain17P0Task(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_waist_ellipse_chain17p0'
    family_id = 'waist_ellipse_chain17p0'
    model_revision = 'coupled_shapes_v1'
    template_resource = 'variations/horseshoe_ring/waist_ellipse_chain17p0.json'
