"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainWiderTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_wider'
    family_id = 'chain_wider'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_wider.json'
