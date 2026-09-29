"""Historical geometry candidate; no new clearance tier or runtime qualification."""
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask


class HorseshoeRingChainLongControlTask(HorseshoeRingTask):
    variation_id = 'horseshoe_ring_chain_long_control'
    family_id = 'chain_long_control'
    model_revision = 'fixed_trace_v1'
    template_resource = 'variations/horseshoe_ring/chain_long_control.json'
