"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainNarrowerTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_narrower'
    family_id = 'chain_narrower'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_narrower.json'
