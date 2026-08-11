"""Task-node judgement: is this scene at some task state yet?

This package is the single answer to "did it succeed". It reads a built scene
and returns a discrete task state; it never defines rewards, action spaces, or
control flow. See `docs/develop/framework/module_boundaries_zh.md`.

Split out of `tasks/` per the blueprint
(`docs/develop/data_pipeline/stable_il_generation_system_devlog_zh.md` §3.2:
"verification 暂时放在各 tasks/*.py 旁边，等接口稳定后再迁移").
"""

from .bar_through_hole_verifier import (
    BarThroughHolePuzzleEvaluator,
    BarThroughHolePuzzleState,
    hexagon_contains,
    prism_axis,
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
    "GeoCrossing",
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
    "UntangleContinuousPuzzleEvaluator",
    "UntangleContinuousPuzzleState",
    "count_crossings",
    "min_inter_strand_distance",
    "strand_polylines",
]
