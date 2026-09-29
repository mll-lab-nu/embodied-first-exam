"""u_mild: provisional medium by shape/orientation; robot solve is unverified."""
from .common import HorseshoeRingTask


class HorseshoeRingMediumTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_medium'
    family_id = 'u_mild'
    model_revision = 'coupled_shapes_settled_v2'
    difficulty = 'medium'
    template_resource = 'variations/horseshoe_ring/u_mild.json'
    # Rest poses after a 5 s passive settle on the table (release scene fix 2026-09-29).
    layout_resource = 'variations/horseshoe_ring/u_mild_settled_poses.json'
