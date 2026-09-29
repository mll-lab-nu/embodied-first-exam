"""waist_mild: provisional easy by shape/orientation; robot solve is unverified."""
from .common import HorseshoeRingTask


class HorseshoeRingEasyTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_easy'
    family_id = 'waist_mild'
    model_revision = 'coupled_shapes_settled_v2'
    difficulty = 'easy'
    template_resource = 'variations/horseshoe_ring/waist_mild.json'
    # Rest poses after a 5 s passive settle on the table (release scene fix 2026-09-29).
    layout_resource = 'variations/horseshoe_ring/waist_mild_settled_poses.json'
