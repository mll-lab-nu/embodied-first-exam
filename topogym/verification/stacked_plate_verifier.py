from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from topogym.tasks.connectivity.stacked_plate import StackedPlateScene, sync_stacked_plate_physics


@dataclass(frozen=True)
class StackedPlatePuzzleState:
    disk_angles: dict[str, float]
    sector_angles: dict[str, float]
    alignment_spread: float
    alignment_tolerance: float

    @property
    def is_terminal(self) -> bool:
        return self.alignment_spread <= self.alignment_tolerance

    def to_info(self) -> dict[str, Any]:
        return {
            "disk_angles": {k: float(v) for k, v in self.disk_angles.items()},
            "sector_angles_deg": {k: float(np.rad2deg(v)) for k, v in self.sector_angles.items()},
            "alignment_spread_deg": float(np.rad2deg(self.alignment_spread)),
            "alignment_tolerance_deg": float(np.rad2deg(self.alignment_tolerance)),
            "terminal": bool(self.is_terminal),
        }


@dataclass(frozen=True)
class StackedPlatePuzzleEvaluator:
    """Success = all disks' missing sectors rotated into angular alignment."""

    def classify(self, plate_scene: StackedPlateScene) -> StackedPlatePuzzleState:
        sync_stacked_plate_physics(plate_scene)
        layout = plate_scene.layout
        angles = dict(plate_scene.plate_yaws)
        return StackedPlatePuzzleState(
            disk_angles=angles,
            sector_angles=layout.sector_angles(angles),
            alignment_spread=layout.alignment_spread(angles),
            alignment_tolerance=layout.alignment_tolerance(),
        )

    def is_success(self, plate_scene: StackedPlateScene) -> bool:
        return self.classify(plate_scene).is_terminal
