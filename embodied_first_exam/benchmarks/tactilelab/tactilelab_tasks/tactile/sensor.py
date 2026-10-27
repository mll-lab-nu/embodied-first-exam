"""GelSight Mini sensor model: taxel raycast + Taxim rendering.

``GelSightMini.observe(gel_pose7, targets)`` turns the world pose of a gel pad
and the meshes it may touch into the published tactile observation:

* ``rgb``: ``(240, 320, 3)`` uint8 Taxim image (markerless, with shadow);
* ``height_mm``: ``(60, 80)`` float32 height map, ``4 - penetration`` in mm;
* ``contact``: ``(60, 80)`` bool contact mask;
* ``press_depth_mm``: 0-d float32, the maximum penetration in mm.

The pipeline is pure geometry plus the Taxim look-up table; no data-driven model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import torch

from .raycast import MeshTarget, TaxelGrid
from .taxim import TaximRenderer

__all__ = ["GelSightMini"]


class GelSightMini:
    """One GelSight Mini gel pad.

    Args:
        name: sensor name (e.g. ``"gsmini_left"``), kept for bookkeeping.
        calib_dir: Taxim calibration folder; ``None`` = the shipped GelSight Mini files.
        device: torch device for the raycast and the renderer.
        grid: taxel grid; the default is the 60 x 80 Taxim field-of-view grid.
        with_shadow: render the Taxim shadow pass.
        out_hw: tactile image size ``(H, W)``.
        render_without_contact: if False, the cached no-contact frame (the render of a
            flat map) is returned when no taxel is in contact, which saves the render and
            gives the same pixels as rendering the flat map.
    """

    def __init__(
        self,
        name: str,
        calib_dir: Optional[str | Path] = None,
        device: str | torch.device = "cuda",
        grid: Optional[TaxelGrid] = None,
        with_shadow: bool = True,
        out_hw: Sequence[int] = (240, 320),
        render_without_contact: bool = True,
    ):
        self.name = str(name)
        self.device = torch.device(device)
        self.grid = grid if grid is not None else TaxelGrid(device=self.device)
        self.renderer = TaximRenderer(calib_dir, with_shadow=with_shadow, out_hw=out_hw, device=self.device)
        self.render_without_contact = bool(render_without_contact)

    @property
    def height_shape(self) -> tuple[int, int]:
        return self.grid.shape

    @property
    def image_shape(self) -> tuple[int, int, int]:
        return (self.renderer.out_hw[0], self.renderer.out_hw[1], 3)

    @torch.no_grad()
    def observe(self, gel_pose7, targets: Sequence[MeshTarget] | MeshTarget | None) -> dict:
        """Tactile observation of the gel at ``gel_pose7`` against ``targets``."""
        height, press, contact = self.grid.penetration(gel_pose7, targets)
        if not self.render_without_contact and not bool(contact.any()):
            rgb = self.renderer.no_contact_image(1)[0]
        else:
            rgb = self.renderer.render(height.unsqueeze(0), press.reshape(1))[0]
        return {"rgb": rgb, "height_mm": height, "contact": contact, "press_depth_mm": press}

    def no_contact_image(self) -> torch.Tensor:
        """Frame rendered when nothing touches the gel, ``(H, W, 3)`` uint8."""
        return self.renderer.no_contact_image(1)[0]
