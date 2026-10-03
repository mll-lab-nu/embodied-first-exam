"""waist_mild: enlarged ring; easy seed 0 has an audited assisted-robot solution."""
from .common import HorseshoeRingTask


class HorseshoeRingEasyTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_easy'
    family_id = 'waist_mild'
    model_revision = 'ring_clearance_candidate_v3'
    difficulty = 'easy'
    template_resource = 'variations/horseshoe_ring/waist_mild.json'
    # Naturally resettled enlarged ring; exact layout retained from the accepted run.
    layout_resource = 'variations/horseshoe_ring/waist_mild_settled_poses.json'
