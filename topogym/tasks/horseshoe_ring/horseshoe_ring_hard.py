"""waist_ellipse: hard seed 0 has an audited assisted-robot solution."""
from .common import HorseshoeRingTask


class HorseshoeRingHardTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_hard'
    family_id = 'waist_ellipse'
    model_revision = 'ring_release_clearance_candidate_v8'
    difficulty = 'hard'
    template_resource = 'variations/horseshoe_ring/waist_ellipse.json'
    # Naturally settled ring-clearance candidate; see the task proof for execution qualification.
    layout_resource = 'variations/horseshoe_ring/waist_ellipse_settled_poses.json'
