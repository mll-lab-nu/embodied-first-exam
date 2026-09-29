"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainElongatedWideTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_elongated_wide'
    family_id = 'chain_elongated_wide'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_elongated_wide.json'
