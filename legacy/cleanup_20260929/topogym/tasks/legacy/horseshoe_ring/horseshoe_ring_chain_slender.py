"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainSlenderTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_slender'
    family_id = 'chain_slender'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_slender.json'
