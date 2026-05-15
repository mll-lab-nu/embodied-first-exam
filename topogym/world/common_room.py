from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import genesis as gs

BackendName = Literal["cpu", "gpu", "cuda"]
RendererName = Literal["rasterizer", "batch"]

_GENESIS_BACKENDS = {
    "cpu": gs.cpu,
    "gpu": gs.gpu,
    "cuda": gs.cuda,
}
_BOOTSTRAPPED_BACKEND: BackendName | None = None


def init_genesis_once(
    backend: BackendName = "cpu",
    *,
    precision: str = "32",
    logging_level: str = "warning",
) -> None:
    """Call ``gs.init`` once per process, matching the official lifecycle."""
    global _BOOTSTRAPPED_BACKEND

    if _BOOTSTRAPPED_BACKEND is None:
        gs.init(
            backend=_GENESIS_BACKENDS[backend],
            precision=precision,
            logging_level=logging_level,
        )
        _BOOTSTRAPPED_BACKEND = backend
        return

    if _BOOTSTRAPPED_BACKEND != backend:
        raise RuntimeError(
            f"Genesis already initialized with backend={_BOOTSTRAPPED_BACKEND!r}; "
            f"cannot switch to backend={backend!r} in the same process."
        )


@dataclass(frozen=True)
class CameraSpec:
    name: str
    res: tuple[int, int]
    pos: tuple[float, float, float]
    lookat: tuple[float, float, float]
    up: tuple[float, float, float] = (0.0, 0.0, 1.0)
    fov: float = 60.0


@dataclass(frozen=True)
class BlockSpec:
    name: str
    pos: tuple[float, float, float]
    size: tuple[float, float, float] = (0.03, 0.03, 0.03)
    color: tuple[float, float, float] = (0.8, 0.1, 0.1)


@dataclass(frozen=True)
class CommonRoomSpec:
    backend: BackendName = "cpu"
    renderer: RendererName = "rasterizer"
    n_envs: int = 1
    show_viewer: bool = False
    dt: float = 0.01
    substeps: int = 1
    gravity: tuple[float, float, float] = (0.0, 0.0, -9.81)
    table_pos: tuple[float, float, float] = (0.55, 0.0, 0.375)
    table_size: tuple[float, float, float] = (0.80, 0.60, 0.75)
    table_color: tuple[float, float, float] = (0.78, 0.80, 0.82)
    stage_pos: tuple[float, float, float] = (0.55, 0.0, 0.751)
    stage_size: tuple[float, float, float] = (0.40, 0.40, 0.002)
    stage_color: tuple[float, float, float] = (0.92, 0.92, 0.94)
    robot_mjcf: str = "xml/franka_emika_panda/panda.xml"
    robot_pos: tuple[float, float, float] = (0.15, 0.0, 0.75)
    robot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0)
    viewer_pos: tuple[float, float, float] = (2.1, -1.3, 1.5)
    viewer_lookat: tuple[float, float, float] = (0.55, 0.0, 0.75)
    viewer_fov: float = 45.0
    cameras: tuple[CameraSpec, ...] = field(default_factory=tuple)
    blocks: tuple[BlockSpec, ...] = field(default_factory=tuple)


@dataclass
class BuiltRoom:
    spec: CommonRoomSpec
    scene: object
    entities: dict[str, object]
    cameras: dict[str, object]

    def read_rgb(self, camera_name: str, envs_idx: list[int] | None = None):
        """Convenience passthrough for ``camera.read(...).rgb``."""
        return self.cameras[camera_name].read(envs_idx=envs_idx).rgb


def default_common_room_spec(
    *,
    backend: BackendName = "cpu",
    renderer: RendererName = "rasterizer",
    n_envs: int = 1,
    show_viewer: bool = False,
) -> CommonRoomSpec:
    table_top = 0.75
    block_z = table_top + 0.015
    return CommonRoomSpec(
        backend=backend,
        renderer=renderer,
        n_envs=n_envs,
        show_viewer=show_viewer,
        cameras=(
            CameraSpec(
                name="oblique",
                res=(512, 512),
                pos=(1.35, -0.95, 1.35),
                lookat=(0.55, 0.0, 0.78),
                fov=50.0,
            ),
            CameraSpec(
                name="topdown",
                res=(512, 512),
                pos=(0.55, 0.0, 1.65),
                lookat=(0.55, 0.0, 0.75),
                fov=45.0,
            ),
        ),
        blocks=(
            BlockSpec("cube_red", (0.45, -0.09, block_z), color=(0.86, 0.20, 0.20)),
            BlockSpec("cube_blue", (0.53, -0.03, block_z), color=(0.21, 0.36, 0.84)),
            BlockSpec("cube_green", (0.61, 0.03, block_z), color=(0.15, 0.62, 0.32)),
            BlockSpec("cube_yellow", (0.69, 0.09, block_z), color=(0.91, 0.73, 0.18)),
        ),
    )


def build_common_room(spec: CommonRoomSpec | None = None) -> BuiltRoom:
    """Build a reusable common stage for Swap / OneStroke / Untangle prototypes."""
    spec = spec or default_common_room_spec()
    init_genesis_once(spec.backend)

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=spec.dt,
            substeps=spec.substeps,
            gravity=spec.gravity,
        ),
        show_viewer=spec.show_viewer,
        viewer_options=gs.options.ViewerOptions(
            camera_pos=spec.viewer_pos,
            camera_lookat=spec.viewer_lookat,
            camera_fov=spec.viewer_fov,
        ),
        renderer=_make_renderer(spec.renderer),
    )

    entities: dict[str, object] = {}
    cameras: dict[str, object] = {}

    entities["ground"] = scene.add_entity(gs.morphs.Plane(), name="ground")
    entities["table"] = scene.add_entity(
        gs.morphs.Box(pos=spec.table_pos, size=spec.table_size, fixed=True),
        surface=gs.surfaces.Plastic(color=spec.table_color, roughness=0.9),
        name="table",
    )
    entities["stage"] = scene.add_entity(
        gs.morphs.Box(pos=spec.stage_pos, size=spec.stage_size, fixed=True),
        surface=gs.surfaces.Plastic(color=spec.stage_color, roughness=0.95),
        name="stage",
    )
    entities["robot"] = scene.add_entity(
        gs.morphs.MJCF(
            file=spec.robot_mjcf,
            pos=spec.robot_pos,
            euler=spec.robot_euler,
        ),
        name="robot",
    )

    for block in spec.blocks:
        entities[block.name] = scene.add_entity(
            gs.morphs.Box(pos=block.pos, size=block.size),
            surface=gs.surfaces.Plastic(color=block.color, roughness=0.75),
            name=block.name,
        )

    for camera_spec in spec.cameras:
        cameras[camera_spec.name] = scene.add_sensor(_make_camera_options(spec.renderer, camera_spec))

    scene.build(n_envs=spec.n_envs)
    return BuiltRoom(spec=spec, scene=scene, entities=entities, cameras=cameras)


def _make_renderer(renderer: RendererName):
    if renderer == "rasterizer":
        return None
    if renderer == "batch":
        return gs.renderers.BatchRenderer()
    raise ValueError(f"Unsupported renderer: {renderer!r}")


def _make_camera_options(renderer: RendererName, spec: CameraSpec):
    kwargs = dict(
        res=spec.res,
        pos=spec.pos,
        lookat=spec.lookat,
        up=spec.up,
        fov=spec.fov,
    )
    if renderer == "rasterizer":
        return gs.sensors.RasterizerCameraOptions(**kwargs)
    if renderer == "batch":
        return gs.sensors.BatchRendererCameraOptions(**kwargs)
    raise ValueError(f"Unsupported renderer: {renderer!r}")

