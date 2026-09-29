"""waist_ellipse: provisional hard by shape/orientation; robot solve is unverified."""
from .common import HorseshoeRingTask


class HorseshoeRingHardTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_hard'
    family_id = 'waist_ellipse'
    model_revision = 'coupled_shapes_settled_v2'
    difficulty = 'hard'
    template_resource = 'variations/horseshoe_ring/waist_ellipse.json'
    # Rest poses after a 5 s passive settle on the table (release scene fix 2026-09-29).
    layout_resource = 'variations/horseshoe_ring/waist_ellipse_settled_poses.json'
