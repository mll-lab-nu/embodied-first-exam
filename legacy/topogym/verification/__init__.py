"""Task-node judgement: is this scene at some task state yet?

This package is the single answer to "did it succeed". It reads a built scene
and returns a discrete task state; it never defines rewards, action spaces, or
control flow. See `docs/develop/framework/module_boundaries_zh.md`.

Split out of `tasks/` per the blueprint
(`docs/develop/data_pipeline/stable_il_generation_system_devlog_zh.md` §3.2:
"verification 暂时放在各 tasks/*.py 旁边，等接口稳定后再迁移").
"""

from .cloth_fold_verifier import (
    ClothFoldEvaluator,
    ClothFoldState,
    ClothFoldThresholds,
    fold_targets,
    particle_error,
)
from .cloth_unpleat_verifier import (
    ClothUnpleatEvaluator,
    ClothUnpleatState,
    ClothUnpleatThresholds,
    band_shift,
    simulated_grid_pairs,
    single_layer_fraction,
    spread_span,
)
from .ring_transfer_verifier import (
    RingTransferEvaluator,
    RingTransferState,
    RingTransferThresholds,
    RingTransferWatch,
)
from .cloth_unroll_verifier import (
    ClothUnrollEvaluator,
    ClothUnrollState,
    ClothUnrollThresholds,
    out_of_plane_thickness,
    wound_particles,
)
from .band_untwist_verifier import (
    BandUntwistPuzzleEvaluator,
    BandUntwistPuzzleState,
    SelfCrossing,
    open_self_crossings,
)
from .bar_through_hole_verifier import (
    BarThroughHolePuzzleEvaluator,
    BarThroughHolePuzzleState,
    polygon_contains,
    prism_axis,
)
from .diverter_route_ball_verifier import (
    DiverterRouteBallEvaluator,
    DiverterRouteBallState,
    OrientedRect,
)
from .gate_cage_ball_verifier import (
    GateCageBallEvaluator,
    GateCageBallState,
)
from .linkbar_rotate_to_zone_verifier import (
    LinkbarRotateEvaluator,
    LinkbarRotateState,
)
from .swap_crossing_sign_verifier import (
    SwapCrossingSignPuzzleEvaluator,
    SwapCrossingSignPuzzleState,
    signed_crossings,
)
from .unlink_c_ring_verifier import (
    UnlinkCRingPuzzleEvaluator,
    UnlinkCRingPuzzleState,
    c_ring_frame,
    opening_to_bar_deg,
)
from .untangle_continuous_verifier import (
    GeoCrossing,
    UntangleContinuousPuzzleEvaluator,
    UntangleContinuousPuzzleState,
    count_crossings,
    min_inter_strand_distance,
    strand_polylines,
)

__all__ = [
    "BandUntwistPuzzleEvaluator",
    "BandUntwistPuzzleState",
    "SelfCrossing",
    "open_self_crossings",
    "BarThroughHolePuzzleEvaluator",
    "BarThroughHolePuzzleState",
    "LinkbarRotateEvaluator",
    "LinkbarRotateState",
    "DiverterRouteBallEvaluator",
    "DiverterRouteBallState",
    "GeoCrossing",
    "GateCageBallEvaluator",
    "OrientedRect",
    "GateCageBallState",
    "SwapCrossingSignPuzzleEvaluator",
    "SwapCrossingSignPuzzleState",
    "signed_crossings",
    "UnlinkCRingPuzzleEvaluator",
    "UnlinkCRingPuzzleState",
    "c_ring_frame",
    "opening_to_bar_deg",
    "UntangleContinuousPuzzleEvaluator",
    "UntangleContinuousPuzzleState",
    "count_crossings",
    "min_inter_strand_distance",
    "strand_polylines",
]
