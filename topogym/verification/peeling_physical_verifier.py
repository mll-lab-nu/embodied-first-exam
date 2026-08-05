from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from topogym.tasks.legacy.peeling_physical import PeelingPhysicalScene


@dataclass(frozen=True)
class PeelingPhysicalState:
    released_fraction: float
    lifted_fraction: float
    centroid: tuple[float, float, float]
    centroid_displacement_xy: float
    target_xy_error: float
    settled_fraction: float
    peeled: bool
    placed: bool
    terminal: bool


class PeelingPhysicalEvaluator:
    def classify(self, peeling_scene: PeelingPhysicalScene) -> PeelingPhysicalState:
        positions = peeling_scene.particle_positions()
        centroid = positions.mean(axis=0)
        success_cfg = peeling_scene.layout.cfg.success
        lift_threshold = (
            peeling_scene.layout.substrate_top_z
            + float(success_cfg.lift_clearance)
        )
        lifted_fraction = float(np.mean(positions[:, 2] >= lift_threshold))
        released_fraction = float(
            peeling_scene.released_groups
            / max(1, len(peeling_scene.adhesion_groups))
        )
        displacement = float(
            np.linalg.norm(
                centroid[:2] - peeling_scene.initial_centroid[:2]
            )
        )
        target_xy_error = float(
            np.linalg.norm(
                centroid[:2] - peeling_scene.layout.placement_center[:2]
            )
        )
        settled_threshold = (
            peeling_scene.layout.placement_surface_z
            + float(success_cfg.settle_height)
        )
        settled_fraction = float(
            np.mean(positions[:, 2] <= settled_threshold)
        )
        peeled = bool(
            released_fraction >= float(success_cfg.min_released_fraction)
            and lifted_fraction >= float(success_cfg.min_lifted_fraction)
            and displacement >= float(success_cfg.min_centroid_displacement_xy)
        )
        placed = bool(
            released_fraction >= float(success_cfg.min_released_fraction)
            and target_xy_error <= float(success_cfg.max_target_xy_error)
            and settled_fraction >= float(success_cfg.min_settled_fraction)
        )
        return PeelingPhysicalState(
            released_fraction=released_fraction,
            lifted_fraction=lifted_fraction,
            centroid=tuple(float(value) for value in centroid),
            centroid_displacement_xy=displacement,
            target_xy_error=target_xy_error,
            settled_fraction=settled_fraction,
            peeled=peeled,
            placed=placed,
            terminal=placed,
        )
