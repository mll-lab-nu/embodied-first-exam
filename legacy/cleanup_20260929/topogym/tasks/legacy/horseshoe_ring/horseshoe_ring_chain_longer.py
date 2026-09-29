"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainLongerTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_longer'
    family_id = 'chain_longer'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_longer.json'
