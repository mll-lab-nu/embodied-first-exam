"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainCompactTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_compact'
    family_id = 'chain_compact'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_compact.json'
