"""u_mild: medium seed 0 has an audited assisted-robot solution."""
from .common import HorseshoeRingTask


class HorseshoeRingMediumTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_medium'
    family_id = 'u_mild'
    model_revision = 'ring_clearance_grasp_candidate_v5'
    difficulty = 'medium'
    template_resource = 'variations/horseshoe_ring/u_mild.json'
    # Naturally settled ring-clearance candidate; see the task proof for execution qualification.
    layout_resource = 'variations/horseshoe_ring/u_mild_settled_poses.json'
