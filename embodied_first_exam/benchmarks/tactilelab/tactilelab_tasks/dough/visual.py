"""USD mesh of a deformable surface, updated from the sidecar every step (visual only, no physics).

``SoftMeshVisual`` writes a ``UsdGeom.Mesh`` with a preview-surface material under ``prim_path`` so the wrist cameras see
the dough / the plug.  PhysX never sees it (no collision API).  ``pxr`` is imported lazily.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np


class SoftMeshVisual:
    """One mesh prim; ``update(points, faces=None)`` writes new vertices (and a new topology when ``faces`` is given)."""

    def __init__(self, prim_path: str, color: Sequence[float] = (0.74, 0.52, 0.26), roughness: float = 0.75):
        self.path = str(prim_path)
        self.color = tuple(float(c) for c in color)
        self.roughness = float(roughness)
        self._geom = None
        self._faces: Optional[np.ndarray] = None
        self.n_updates = 0

    def _define(self):
        from isaaclab.sim.utils.stage import get_current_stage
        from pxr import Gf, Sdf, UsdGeom, UsdShade

        stage = get_current_stage()
        geom = UsdGeom.Mesh.Define(stage, self.path)
        geom.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        geom.CreateDoubleSidedAttr().Set(True)
        geom.CreateDisplayColorPrimvar("constant").Set([Gf.Vec3f(*self.color)])
        mat_path = self.path + "_mat"
        mat = UsdShade.Material.Define(stage, mat_path)
        sh = UsdShade.Shader.Define(stage, mat_path + "/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*self.color))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(self.roughness)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(geom.GetPrim()).Bind(mat)
        self._geom = geom
        return geom

    def update(
        self, points: np.ndarray, faces: Optional[np.ndarray] = None, normals: Optional[np.ndarray] = None
    ) -> None:
        """Write the vertices (world frame); ``faces`` replaces the topology (required on the first call)."""
        from pxr import Gf, Vt

        geom = self._geom or self._define()
        v = np.ascontiguousarray(points, dtype=np.float32).reshape(-1, 3)
        geom.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(v))
        if faces is not None:
            f = np.ascontiguousarray(faces, dtype=np.int32).reshape(-1, 3)
            geom.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(np.full(len(f), 3, dtype=np.int32)))
            geom.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(f.reshape(-1)))
            self._faces = f
        if normals is not None and len(normals) == len(v):
            geom.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(normals, dtype=np.float32)))
            geom.SetNormalsInterpolation("vertex")
        if len(v):
            lo, hi = v.min(0) - 1e-3, v.max(0) + 1e-3
            geom.GetExtentAttr().Set(
                Vt.Vec3fArray([Gf.Vec3f(*[float(x) for x in lo]), Gf.Vec3f(*[float(x) for x in hi])])
            )
        self.n_updates += 1

    def hide(self) -> None:
        """Collapse the mesh to nothing (no dough drawn)."""
        if self._geom is not None:
            from pxr import Vt

            self._geom.GetPointsAttr().Set(Vt.Vec3fArray())
            self._geom.GetFaceVertexCountsAttr().Set(Vt.IntArray())
            self._geom.GetFaceVertexIndicesAttr().Set(Vt.IntArray())
            self._faces = None


__all__ = ["SoftMeshVisual"]
