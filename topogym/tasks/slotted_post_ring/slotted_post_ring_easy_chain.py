"""slotted_post_ring easy with the cord as a rigid capsule chain: slotted_post_ring_hard_chain with the easy setting's
ring (major radius 64 mm), as the FEM easy setting differs from hard."""
from ..base import merge_parameters
from .slotted_post_ring_hard_chain import SlottedPostRingHardChainTask


class SlottedPostRingEasyChainTask(SlottedPostRingHardChainTask):
    variation_id = "slotted_post_ring_easy_chain"
    family_id = "rigid_chain_large_ring"
    defaults = merge_parameters(SlottedPostRingHardChainTask.defaults, {"geometry": {"ring_major_radius_m": .064}})
