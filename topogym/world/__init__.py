"""Genesis physics lifecycle and shared scene construction."""

from importlib import import_module

from topogym.world.genesis_world import GenesisWorld
from topogym.world.entities import EntityRegistry
from topogym.world.state import WorldState


def __getattr__(name):
    if name in {"RobotFootprintCheck", "StandardTabletopSceneBuilder", "TabletopBaseScene",
                "TabletopFrames", "tabletop_frames_from_config"}:
        value = getattr(import_module(".tabletop", __name__), name)
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value

__all__ = [
    "GenesisWorld",
    "WorldState",
    "EntityRegistry",
    "RobotFootprintCheck",
    "StandardTabletopSceneBuilder",
    "TabletopBaseScene",
    "TabletopFrames",
    "tabletop_frames_from_config",
]
