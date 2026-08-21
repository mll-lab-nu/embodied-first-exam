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
from .bar_through_hole_verifier import (
    BarThroughHolePuzzleEvaluator,
    BarThroughHolePuzzleState,
    hexagon_contains,
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
from .linkbar_merge_components_verifier import (
    LinkbarMergeEvaluator,
    LinkbarMergeState,
)
from .maze_wall_removal_verifier import (
    MazeWallRemovalPuzzleEvaluator,
    MazeWallRemovalPuzzleState,
)
from .onestroke_verifier import OneStrokePuzzleEvaluator, OneStrokePuzzleState
from .peeling_verifier import PeelingPuzzleEvaluator, PeelingPuzzleState
from .peeling_physical_verifier import PeelingPhysicalEvaluator, PeelingPhysicalState
from .stacked_plate_verifier import (
    StackedPlatePuzzleEvaluator,
    StackedPlatePuzzleState,
)
from .swap_crossing_sign_verifier import (
    SwapCrossingSignPuzzleEvaluator,
    SwapCrossingSignPuzzleState,
    signed_crossings,
)
from .swap_verifier import SwapPuzzleEvaluator, SwapPuzzleState, SwapSuccessChecker
from .untangle_continuous_verifier import (
    GeoCrossing,
    UntangleContinuousPuzzleEvaluator,
    UntangleContinuousPuzzleState,
    count_crossings,
    min_inter_strand_distance,
    strand_polylines,
)

__all__ = [
    "BarThroughHolePuzzleEvaluator",
    "BarThroughHolePuzzleState",
    "LinkbarMergeEvaluator",
    "LinkbarMergeState",
    "DiverterRouteBallEvaluator",
    "DiverterRouteBallState",
    "GeoCrossing",
    "GateCageBallEvaluator",
    "OrientedRect",
    "GateCageBallState",
    "MazeWallRemovalPuzzleEvaluator",
    "MazeWallRemovalPuzzleState",
    "OneStrokePuzzleEvaluator",
    "OneStrokePuzzleState",
    "PeelingPhysicalEvaluator",
    "PeelingPhysicalState",
    "PeelingPuzzleEvaluator",
    "PeelingPuzzleState",
    "StackedPlatePuzzleEvaluator",
    "StackedPlatePuzzleState",
    "SwapPuzzleEvaluator",
    "SwapPuzzleState",
    "SwapSuccessChecker",
    "SwapCrossingSignPuzzleEvaluator",
    "SwapCrossingSignPuzzleState",
    "signed_crossings",
    "UntangleContinuousPuzzleEvaluator",
    "UntangleContinuousPuzzleState",
    "count_crossings",
    "min_inter_strand_distance",
    "strand_polylines",
]
