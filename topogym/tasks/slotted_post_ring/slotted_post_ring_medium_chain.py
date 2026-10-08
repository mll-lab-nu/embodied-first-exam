"""slotted_post_ring medium with the cord as a rigid capsule chain: slotted_post_ring_hard_chain with the medium setting's
ring (major radius 62.5 mm), as the FEM medium setting differs from hard."""
from ..base import merge_parameters
from .slotted_post_ring_hard_chain import SlottedPostRingHardChainTask


class SlottedPostRingMediumChainTask(SlottedPostRingHardChainTask):
    variation_id = "slotted_post_ring_medium_chain"
    family_id = "rigid_chain_middle_ring"
    defaults = merge_parameters(SlottedPostRingHardChainTask.defaults, {"geometry": {"ring_major_radius_m": .0625}})
