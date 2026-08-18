"""Task assets and scene construction: what this episode looks like.

Layout -> Scene -> SceneBuilder only. Judging "is it done" lives in
`topogym/verification/`; see `docs/develop/framework/module_boundaries_zh.md`.

Task modules sit in a subpackage named after their capability category
(`deformation` / `routing` / `entangle` / `connectivity`), so the path is the
classification -- there is no separate table to keep in sync. Tasks predating
the taxonomy live in `legacy/` (see its README). The category axis exists only
here; `verification/`, `planning/`, `generation/`, `supervision/` and `envs/`
stay flat. See `docs/develop/framework/task_taxonomy_zh.md`.

This module re-exports every task's public names flat, so importers say
`from topogym.tasks import StackedPlateSceneBuilder` and are unaffected when a
task is reclassified into a different category directory.
"""

from .routing.bar_through_hole import (
    BarThroughHoleLayout,
    BarThroughHoleScene,
    BarThroughHoleSceneBuilder,
)
from .routing.cable_routing import CableRoutingLayout, CableRoutingScene, CableRoutingSceneBuilder, CableRoutingSignature
from .routing.rope_winding import (
    RopeWindingLayout,
    RopeWindingScene,
    RopeWindingSceneBuilder,
)
from .legacy.onestroke import (
    OneStrokeLayout,
    OneStrokeScene,
    OneStrokeSceneBuilder,
)
from .legacy.maze_wall_removal import (
    MazeGraphSolver,
    MazeWallGenerator,
    MazeWallRemovalInstance,
    MazeWallRemovalLayout,
    MazeWallRemovalScene,
    MazeWallRemovalSceneBuilder,
)
from .legacy.peeling import (
    PeelingLayout,
    PeelingScene,
    PeelingSceneBuilder,
    apply_peel_zone_markers,
)
from .legacy.peeling_physical import (
    PeelingKinematicSheetDriver,
    PeelingPhysicalLayout,
    PeelingPhysicalScene,
    PeelingPhysicalSceneBuilder,
    release_all_peeling_groups,
    release_peeling_groups,
)
from .connectivity.diverter_route_ball import (
    DiverterRouteBallLayout,
    DiverterRouteBallScene,
    DiverterRouteBallSceneBuilder,
    other_side,
    side_sign,
)
from .connectivity.gate_cage_ball import (
    GateCageBallLayout,
    GateCageBallScene,
    GateCageBallSceneBuilder,
)
from .connectivity.stacked_plate import (
    StackedPlateLayout,
    StackedPlateScene,
    StackedPlateSceneBuilder,
    apply_stacked_plate_visuals,
    sync_stacked_plate_physics,
)
from .legacy.swap import (
    SwapLayout,
    SwapOraclePlan,
    SwapScene,
    SwapSceneBuilder,
)
from .entangle.untangle import RopeEndpointHandle, UntangleLayout, UntangleScene, UntangleSceneBuilder
from .entangle.untangle_continuous import (
    UntangleContinuousLayout,
    UntangleContinuousScene,
    UntangleContinuousSceneBuilder,
    settle_scene,
)

__all__ = [
    "BarThroughHoleLayout",
    "BarThroughHoleScene",
    "BarThroughHoleSceneBuilder",
    "CableRoutingLayout",
    "CableRoutingScene",
    "CableRoutingSceneBuilder",
    "CableRoutingSignature",
    "RopeWindingLayout",
    "RopeWindingScene",
    "RopeWindingSceneBuilder",
    "OneStrokeLayout",
    "OneStrokeScene",
    "OneStrokeSceneBuilder",
    "MazeGraphSolver",
    "MazeWallGenerator",
    "MazeWallRemovalInstance",
    "MazeWallRemovalLayout",
    "MazeWallRemovalScene",
    "MazeWallRemovalSceneBuilder",
    "PeelingLayout",
    "PeelingScene",
    "PeelingSceneBuilder",
    "apply_peel_zone_markers",
    "PeelingKinematicSheetDriver",
    "PeelingPhysicalLayout",
    "PeelingPhysicalScene",
    "PeelingPhysicalSceneBuilder",
    "release_all_peeling_groups",
    "release_peeling_groups",
    "DiverterRouteBallLayout",
    "DiverterRouteBallScene",
    "DiverterRouteBallSceneBuilder",
    "GateCageBallLayout",
    "GateCageBallScene",
    "GateCageBallSceneBuilder",
    "other_side",
    "side_sign",
    "StackedPlateLayout",
    "StackedPlateScene",
    "StackedPlateSceneBuilder",
    "apply_stacked_plate_visuals",
    "sync_stacked_plate_physics",
    "SwapLayout",
    "SwapOraclePlan",
    "SwapScene",
    "SwapSceneBuilder",
    "RopeEndpointHandle",
    "UntangleLayout",
    "UntangleScene",
    "UntangleSceneBuilder",
    "UntangleContinuousLayout",
    "UntangleContinuousScene",
    "UntangleContinuousSceneBuilder",
    "settle_scene",
]
