"""Genesis-grounded scene presets for TopoGym module A."""

from .common_room import (
    BlockSpec,
    BuiltRoom,
    CameraSpec,
    CommonRoomSpec,
    build_common_room,
    default_common_room_spec,
    init_genesis_once,
)

__all__ = [
    "BlockSpec",
    "BuiltRoom",
    "CameraSpec",
    "CommonRoomSpec",
    "build_common_room",
    "default_common_room_spec",
    "init_genesis_once",
]

