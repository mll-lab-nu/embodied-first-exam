"""GelSight-Mini sensors of the dough tasks: raycast against a deformable surface and / or a rigid scene object.

``DoughTactile`` is a ``Task.sensors`` provider: ``tactile_left_rgb`` / ``tactile_right_rgb``
(240, 320, 3) uint8, ``tactile_*_height`` (60, 80) float16 mm, ``tactile_*_contact`` (60, 80) bool, ``tactile_*_press_mm``.

Targets:

* a *soft* surface (``set_soft(points, faces)``): the dough's marching-cubes mesh (new topology every sidecar step ->
  the warp BVH is rebuilt) or the plug's boundary (fixed topology -> the BVH is refitted);
* *rigid* scene objects (``add_rigid(name)``): the held scraper of ``dough_fill_tray``; their mesh is read from the USD once
  and follows the body pose every tick.

torch / warp / Isaac are imported lazily.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


class DoughTactile:
    def __init__(self, scene, pads: Optional[Dict[str, str]] = None, device: str = "cuda"):
        from ..tactile.sensor import GelSightMini

        self.scene = scene
        self.pads = dict(pads or {"tactile_left": "gsmini_left", "tactile_right": "gsmini_right"})
        self.device = device
        self.sensors = {prefix: GelSightMini(prefix, device=device) for prefix in self.pads}
        self.soft = None
        self.rigid: Dict[str, object] = {}
        self.soft_updates = 0

    # ------------------------------------------------------------------ targets
    def set_soft(self, points: np.ndarray, faces: Optional[np.ndarray] = None) -> None:
        """New surface vertices (world frame); ``faces`` = new topology (rebuild), None = same topology (refit)."""
        from ..tactile.raycast import MeshTarget

        pts = np.ascontiguousarray(points, dtype=np.float32).reshape(-1, 3)
        if self.soft is None:
            if faces is None:
                raise ValueError("the first soft surface needs its faces")
            self.soft = MeshTarget(pts, faces, device=self.device)
        elif faces is not None:
            self.soft.rebuild(pts, faces)
        else:
            self.soft.refit(pts)
        self.soft_updates += 1

    def clear_soft(self) -> None:
        self.soft = None

    def add_rigid(self, name: str) -> None:
        """Raycast against scene object ``name`` too (mesh from its USD / cuboid dims, body pose every tick)."""
        from ..tactile.mesh_sources import box_mesh, usd_mesh_in_frame
        from ..tactile.raycast import MeshTarget

        if name in self.rigid:
            return
        ocfg = next(o for o in self.scene.cfg.objects if o.name == name)
        if ocfg.shape == "cuboid" or ocfg.usd_path is None:
            verts, faces = box_mesh(tuple(ocfg.dims))
        else:
            from isaaclab.sim.utils.stage import get_current_stage

            body_path = str(self.scene.objects[name].root_physx_view.prim_paths[0])
            verts, faces = usd_mesh_in_frame(get_current_stage(), body_path, frame_path=body_path)
        self.rigid[name] = MeshTarget(verts, faces, device=self.device, pose7=self.scene.object_pose(name))

    # ------------------------------------------------------------------ read
    def gel_pose(self, body: str) -> np.ndarray:
        return self.scene.robot.body_pose(body)

    def targets(self) -> List[object]:
        out = []
        if self.soft is not None:
            out.append(self.soft)
        for name, tgt in self.rigid.items():
            tgt.set_pose(self.scene.object_pose(name))
            out.append(tgt)
        return out

    def __call__(self) -> Dict[str, np.ndarray]:
        targets = self.targets()
        out: Dict[str, np.ndarray] = {}
        for prefix, body in self.pads.items():
            res = self.sensors[prefix].observe(self.gel_pose(body), targets)
            out[f"{prefix}_rgb"] = np.ascontiguousarray(res["rgb"].detach().cpu().numpy().astype(np.uint8))
            out[f"{prefix}_height"] = res["height_mm"].detach().cpu().numpy().astype(np.float16)
            out[f"{prefix}_contact"] = res["contact"].detach().cpu().numpy().astype(bool)
            out[f"{prefix}_press_mm"] = np.float32(float(res["press_depth_mm"]))
        return out


def surface_normals(points: np.ndarray, faces: np.ndarray, outward: bool = True) -> np.ndarray:
    """Unit vertex normals of a closed surface, flipped so that they point away from the centroid when ``outward``."""
    from ..tactile.raycast import vertex_normals

    n = vertex_normals(points, faces).astype(np.float32)
    if outward and len(points):
        c = np.asarray(points, dtype=np.float64).mean(0)
        if float(np.mean(np.sum(n * (points - c), axis=1))) < 0.0:
            n = -n
    return n


__all__ = ["DoughTactile", "surface_normals"]
