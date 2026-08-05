from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import genesis as gs
import numpy as np
from omegaconf import OmegaConf

from topogym.core import EntityManifest
from topogym.primitives import PickPlacePrimitive
from topogym.world import StandardTabletopSceneBuilder, TabletopBaseScene, materials


def _list(value):
    if OmegaConf.is_config(value):
        value = OmegaConf.to_container(value, resolve=True)
    return value


@dataclass(frozen=True)
class SwapLayout:
    """Slot and block geometry for the simple Swap task."""

    cfg: Any
    task_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def coordinate_frame(self) -> str:
        return str(getattr(self.cfg, "coordinate_frame", "world"))

    @property
    def block_to_move(self) -> str:
        return self.cfg.oracle.block_to_move

    @property
    def source_slot(self) -> int:
        return int(self.cfg.oracle.source_slot)

    @property
    def target_slot(self) -> int:
        return int(self.cfg.oracle.target_slot)

    def slot(self, index: int):
        return self.cfg.slots[index]

    def slot_xy(self, index: int) -> np.ndarray:
        return self.slot_pos(index)[:2]

    def slot_pos(self, index: int) -> np.ndarray:
        return self.position_to_world(self.slot(index).pos)

    def position_to_world(self, position) -> np.ndarray:
        pos = np.asarray(_list(position), dtype=float)
        if self.coordinate_frame == "world":
            return pos
        if self.coordinate_frame == "task":
            return pos + np.asarray(self.task_origin, dtype=float)
        raise ValueError(
            f"Unsupported Swap coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def world_z(self, z: float) -> float:
        if self.coordinate_frame == "world":
            return float(z)
        if self.coordinate_frame == "task":
            return float(self.task_origin[2]) + float(z)
        raise ValueError(
            f"Unsupported Swap coordinate_frame={self.coordinate_frame!r}; "
            "expected 'world' or 'task'."
        )

    def block_center_for_slot(self, index: int, block_name: str) -> np.ndarray:
        slot_pos = self.slot_pos(index)
        slot_size = np.asarray(_list(self.cfg.slot_size), dtype=float)
        block_size = np.asarray(_list(self.cfg.blocks[block_name].size), dtype=float)
        slot_has_surface = bool(
            getattr(
                self.cfg,
                "slots_collision",
                bool(getattr(self.cfg, "slots_visible", True)),
            )
        )
        slot_surface_z = slot_pos[2] + 0.5 * slot_size[2]
        if not slot_has_surface:
            slot_surface_z = slot_pos[2] - 0.5 * slot_size[2]
        return np.array(
            [
                slot_pos[0],
                slot_pos[1],
                slot_surface_z + 0.5 * block_size[2],
            ]
        )

    def slot_indices(self) -> list[int]:
        return [int(slot.index) for slot in self.cfg.slots]

    def block_names(self) -> list[str]:
        return [str(name) for name in self.cfg.blocks.keys()]

    def target_assignment(self) -> dict[str, int]:
        goal = getattr(self.cfg, "goal", None)
        if goal is not None and hasattr(goal, "blocks"):
            return {str(name): int(slot) for name, slot in goal.blocks.items()}

        assignment = {
            str(block_name): int(block.initial_slot)
            for block_name, block in self.cfg.blocks.items()
        }
        assignment[self.block_to_move] = self.target_slot
        return assignment

    def target_empty_slot(self) -> int | None:
        goal = getattr(self.cfg, "goal", None)
        if goal is not None and hasattr(goal, "empty_slot"):
            return int(goal.empty_slot)

        occupied = set(self.target_assignment().values())
        empty = [slot for slot in self.slot_indices() if slot not in occupied]
        if len(empty) != 1:
            return None
        return empty[0]


@dataclass
class SwapScene:
    scene: Any
    manifest: EntityManifest
    layout: SwapLayout
    cameras: dict = field(default_factory=dict)
    tabletop: TabletopBaseScene | None = None


class SwapSceneBuilder:
    """Build the common table plus Swap slots and blocks."""

    def __init__(self, env_cfg, task_cfg, robot_cfg, *, rigid_options=None) -> None:
        self.env_cfg = env_cfg
        self.task_cfg = task_cfg
        self.robot_cfg = robot_cfg
        self.rigid_options = rigid_options

    def build(self, *, show_viewer: bool = False) -> SwapScene:
        tabletop_builder = StandardTabletopSceneBuilder(
            self.env_cfg,
            self.robot_cfg,
            rigid_options=self.rigid_options,
        )
        tabletop = tabletop_builder.create(show_viewer=show_viewer)
        scene = tabletop.scene
        manifest = tabletop.manifest

        layout = SwapLayout(self.task_cfg, task_origin=tabletop.frames.task_origin)
        self._add_slots(scene, manifest, layout)
        self._add_blocks(scene, manifest, layout)

        tabletop_builder.finalize(tabletop)
        return SwapScene(
            scene=scene,
            manifest=manifest,
            layout=layout,
            cameras=tabletop.cameras,
            tabletop=tabletop,
        )

    def _add_slots(
        self,
        scene,
        manifest: EntityManifest,
        layout: SwapLayout,
    ) -> None:
        slots_visible = bool(getattr(self.task_cfg, "slots_visible", True))
        slots_collision = bool(getattr(self.task_cfg, "slots_collision", slots_visible))
        if not slots_visible and not slots_collision:
            return

        slot_size = tuple(self.task_cfg.slot_size)
        for slot in self.task_cfg.slots:
            manifest.add(
                slot.name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=tuple(layout.slot_pos(int(slot.index))),
                        size=slot_size,
                        fixed=True,
                        visualization=slots_visible,
                        collision=slots_collision,
                    ),
                    surface=materials.plastic("marker", self.task_cfg.slot_color),
                    name=slot.name,
                ),
            )
            self._add_slot_marker(scene, manifest, layout, slot, slot_size)

    def _add_slot_marker(
        self,
        scene,
        manifest: EntityManifest,
        layout: SwapLayout,
        slot,
        slot_size: tuple[float, float, float],
    ) -> None:
        marker_cfg = getattr(self.task_cfg, "slot_marker", None)
        if marker_cfg is None or not bool(getattr(marker_cfg, "enabled", False)):
            return
        # square_ring: concentric squares (decreasing Box footprints) matching
        # the square slots/blocks. (The old round target_ring is retired; its
        # radii/colors are kept commented in config for the record.)
        if str(getattr(marker_cfg, "style", "square_ring")) != "square_ring":
            raise ValueError("swap.slot_marker.style must be 'square_ring'.")

        sides = [float(value) for value in _list(getattr(marker_cfg, "sides", []))]
        colors = [tuple(float(v) for v in _list(color)) for color in _list(getattr(marker_cfg, "colors", []))]
        if not sides or len(sides) != len(colors):
            raise ValueError("swap.slot_marker.sides and colors must be non-empty and have the same length.")

        height = float(getattr(marker_cfg, "height", 0.0004))
        z_gap = float(getattr(marker_cfg, "z_gap", 0.00006))
        collision = bool(getattr(marker_cfg, "collision", False))
        slot_pos = layout.slot_pos(int(slot.index))
        slot_top_z = float(slot_pos[2]) + 0.5 * float(slot_size[2])
        for layer_index, (side, color) in enumerate(zip(sides, colors)):
            name = f"{slot.name}_target_ring_{layer_index}"
            center_z = slot_top_z + z_gap + (layer_index + 0.5) * height
            manifest.add(
                name,
                scene.add_entity(
                    gs.morphs.Box(
                        pos=(float(slot_pos[0]), float(slot_pos[1]), center_z),
                        size=(side, side, height),
                        fixed=True,
                        collision=collision,
                    ),
                    surface=materials.plastic("marker", color),
                    name=name,
                ),
            )

    def _add_blocks(self, scene, manifest: EntityManifest, layout: SwapLayout) -> None:
        for block_name, block in self.task_cfg.blocks.items():
            pos = layout.block_center_for_slot(block.initial_slot, block_name)
            manifest.add(
                block_name,
                scene.add_entity(
                    gs.morphs.Box(pos=tuple(pos), size=tuple(block.size)),
                    surface=materials.plastic("object", block.color),
                    name=block_name,
                ),
            )

@dataclass(frozen=True)
class SwapOraclePlan:
    """Standard answer: move the selected block from source slot to empty slot."""

    primitive: PickPlacePrimitive

    def run(self, swap_scene: SwapScene, controller) -> None:
        layout = swap_scene.layout
        block = swap_scene.manifest.get(layout.block_to_move)
        self.primitive.run(
            controller,
            block=block,
            source_xy=layout.slot_xy(layout.source_slot),
            target_xy=layout.slot_xy(layout.target_slot),
        )
        controller.reset_home(settle_steps=controller.cfg.control_loop.steps_per_action)


