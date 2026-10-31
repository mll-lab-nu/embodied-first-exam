"""Taxel-grid raycaster (warp): gel pose + target meshes -> penetration height map.

A GelSight Mini gel pad is modelled as a flat grid of taxels on its contact
face. For every taxel a ray is cast from the undeformed gel surface *into* the
gel (along gel-local -Z) against the target mesh(es); the distance to the first
hit is how deep the object has pushed into the gel at that taxel. A second
"back-cast" from just inside the object along the opposite direction confirms
that the taxel really is inside the object (an object touched from behind the
sensor surface, or a stray back face, gives a first hit but no back hit and is
rejected). Depth is kept only where both rays hit and is clamped to ``>= 0``.

Gel frame convention: gel-local +Z is the contact face normal, the face sits at
``z = normal_offset`` (4 mm, the pad thickness). The image is seen by a camera
behind the gel: image right = gel +X (columns), image down = gel +Y (rows).

Works with warp >= 1.12 (the Isaac Sim 5.1 / Isaac Lab 2.3 stack).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import torch
import warp as wp

__all__ = ["TaxelGrid", "MeshTarget", "shell_faces", "vertex_normals", "PenetrationResult"]

wp.config.quiet = True
wp.init()


# --------------------------------------------------------------------------- small helpers


def _to_numpy(a, dtype) -> np.ndarray:
    if isinstance(a, torch.Tensor):
        a = a.detach().cpu().numpy()
    return np.ascontiguousarray(np.asarray(a, dtype=dtype))


def _wp_device(device: str | torch.device) -> str:
    d = torch.device(device)
    if d.type == "cuda":
        idx = d.index if d.index is not None else torch.cuda.current_device()
        return f"cuda:{idx}"
    return "cpu"


def _pose7_to_transform(pose7) -> wp.transform:
    """``[x y z qw qx qy qz]`` -> ``wp.transform`` (warp quaternions are xyzw)."""
    p = _to_numpy(pose7, np.float64).reshape(7)
    return wp.transform(
        wp.vec3(float(p[0]), float(p[1]), float(p[2])),
        wp.quat(float(p[4]), float(p[5]), float(p[6]), float(p[3])),
    )


def _pose7_to_transform_row(pose7) -> np.ndarray:
    p = _to_numpy(pose7, np.float32).reshape(7)
    return np.array([p[0], p[1], p[2], p[4], p[5], p[6], p[3]], dtype=np.float32)


# --------------------------------------------------------------------------- thick shell (cloth)


def vertex_normals(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals of a triangle mesh (unit length)."""
    v = np.asarray(points, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def shell_faces(faces: np.ndarray, n_points: int) -> np.ndarray:
    """Faces of the closed thick shell of an open sheet.

    Top = the sheet's own faces (vertices ``0..P-1``), bottom = the same faces
    reversed on vertices ``P..2P-1``, plus a wall along every boundary edge.
    """
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    top = f
    bottom = f[:, ::-1] + n_points
    edges: dict = {}
    for tri in f:
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            edges.setdefault((min(a, b), max(a, b)), []).append((a, b))
    walls = []
    for lst in edges.values():
        if len(lst) == 1:  # boundary edge
            a, b = lst[0]
            walls.append((a, a + n_points, b + n_points))
            walls.append((a, b + n_points, b))
    wall = np.asarray(walls, dtype=np.int64).reshape(-1, 3)
    return np.concatenate([top, bottom, wall], axis=0).astype(np.int32)


# --------------------------------------------------------------------------- targets


class MeshTarget:
    """A triangle mesh the gel can touch, wrapped in a ``warp.Mesh`` (BVH).

    Args:
        vertices: ``(N, 3)`` vertex positions in the mesh frame (metres).
        faces: ``(M, 3)`` triangle vertex indices.
        device: torch/warp device.
        thickness: ``> 0`` turns an open sheet (cloth through the particle centres)
            into the closed shell ``centre +- thickness * normal``, the surface a
            gel actually touches. The sheet itself stays in :attr:`mid_points`.
        pose7: optional ``[x y z qw qx qy qz]`` pose of the mesh frame in the world;
            identity by default (vertices already in the world frame). Rigid objects
            keep their vertices in the body frame and call :meth:`set_pose` every tick.

    ``refit(points)`` follows a deformed surface with the same topology (cheap BVH
    refit); ``rebuild(points, faces)`` or ``update(points, faces=...)`` replaces the
    topology (new BVH).
    """

    def __init__(
        self,
        vertices,
        faces,
        device: str | torch.device = "cuda",
        thickness: float = 0.0,
        pose7=None,
    ):
        self.device = _wp_device(device)
        self.thickness = float(thickness)
        self.mid_faces = _to_numpy(faces, np.int32).reshape(-1, 3)
        self.mid_points = _to_numpy(vertices, np.float32).reshape(-1, 3)
        self.faces = shell_faces(self.mid_faces, len(self.mid_points)) if self.thickness > 0.0 else self.mid_faces
        self.points = self._shell(self.mid_points)
        self.version = 0
        self.topology = 0
        self._mesh: Optional[wp.Mesh] = None
        self._build()
        self._xform = np.array([0, 0, 0, 0, 0, 0, 1], dtype=np.float32)
        if pose7 is not None:
            self.set_pose(pose7)

    # ----------------------------------------------------------------- geometry

    def _shell(self, mid: np.ndarray) -> np.ndarray:
        if self.thickness <= 0.0:
            return mid
        h = self.thickness * vertex_normals(mid, self.mid_faces)
        return np.concatenate([mid + h, mid - h], axis=0).astype(np.float32)

    def _build(self) -> None:
        self._mesh = wp.Mesh(
            points=wp.array(self.points, dtype=wp.vec3, device=self.device),
            indices=wp.array(self.faces.reshape(-1), dtype=wp.int32, device=self.device),
        )

    @property
    def mesh(self) -> wp.Mesh:
        return self._mesh

    @property
    def mesh_id(self) -> int:
        return int(self._mesh.id)

    def set_pose(self, pose7) -> None:
        """World pose ``[x y z qw qx qy qz]`` of the mesh frame."""
        self._xform = _pose7_to_transform_row(pose7)

    @property
    def transform_row(self) -> np.ndarray:
        """Pose as a warp transform row ``[x y z qx qy qz qw]``."""
        return self._xform

    def refit(self, points) -> None:
        """New vertex positions, same topology: refit the BVH in place."""
        pts = _to_numpy(points, np.float32).reshape(-1, 3)
        if len(pts) != len(self.mid_points):
            raise ValueError(
                f"refit: {len(pts)} points for a mesh with {len(self.mid_points)} vertices; use rebuild() when the topology changes"
            )
        self.mid_points = pts
        self.points = self._shell(pts)
        self._mesh.points.assign(wp.array(self.points, dtype=wp.vec3, device=self.device))
        self._mesh.refit()
        self.version += 1

    def rebuild(self, points, faces) -> None:
        """New surface with a new topology (e.g. a marching-cubes mesh): rebuild the BVH."""
        self.mid_faces = _to_numpy(faces, np.int32).reshape(-1, 3)
        self.mid_points = _to_numpy(points, np.float32).reshape(-1, 3)
        self.faces = shell_faces(self.mid_faces, len(self.mid_points)) if self.thickness > 0.0 else self.mid_faces
        self.points = self._shell(self.mid_points)
        self._build()
        self.topology += 1
        self.version += 1

    def update(self, points, faces=None) -> None:
        """Refit when ``faces`` is None, rebuild otherwise."""
        if faces is None:
            self.refit(points)
        else:
            self.rebuild(points, faces)

    def world_points(self) -> np.ndarray:
        """Current shell vertices transformed by the mesh pose, ``(N, 3)``."""
        x, y, z, qx, qy, qz, qw = (float(v) for v in self._xform)
        q = np.array([qx, qy, qz])
        v = self.points.astype(np.float64)
        t = 2.0 * np.cross(q, v)
        return (v + qw * t + np.cross(q, t) + np.array([x, y, z])).astype(np.float32)


# --------------------------------------------------------------------------- kernel


@wp.kernel(enable_backward=False)
def _penetration_kernel(
    gel_xform: wp.transform,
    taxels_local: wp.array(dtype=wp.vec3),
    mesh_ids: wp.array(dtype=wp.uint64),
    mesh_xforms: wp.array(dtype=wp.transform),
    max_dist: float,
    cpd_max_dist: float,
    cpd_eps: float,
    depth_out: wp.array(dtype=float),
    hit_out: wp.array(dtype=wp.int32),
):
    tid = wp.tid()
    start_w = wp.transform_point(gel_xform, taxels_local[tid])
    dir_w = wp.transform_vector(gel_xform, wp.vec3(0.0, 0.0, -1.0))  # into the gel

    n_mesh = mesh_ids.shape[0]
    t_best = float(1.0e30)
    hit1 = int(0)
    for m in range(n_mesh):
        inv = wp.transform_inverse(mesh_xforms[m])
        s = wp.transform_point(inv, start_w)
        d = wp.transform_vector(inv, dir_w)
        q = wp.mesh_query_ray(mesh_ids[m], s, d, max_dist)
        if q.result:
            if q.t < t_best:
                t_best = q.t
                hit1 = 1

    depth = float(0.0)
    hit = int(0)
    if hit1 == 1:
        depth = wp.max(t_best, 0.0)
        if cpd_max_dist > 0.0:
            # Back-cast: start just inside the object (cpd_eps < 0 before the first hit) and cast out again.
            adv_w = start_w + dir_w * (depth + cpd_eps)
            back_w = -dir_w
            for m in range(n_mesh):
                inv2 = wp.transform_inverse(mesh_xforms[m])
                s2 = wp.transform_point(inv2, adv_w)
                d2 = wp.transform_vector(inv2, back_w)
                q2 = wp.mesh_query_ray(mesh_ids[m], s2, d2, cpd_max_dist)
                if q2.result:
                    hit = 1
        else:
            hit = 1
    if hit == 0:
        depth = 0.0
    depth_out[tid] = depth
    hit_out[tid] = hit


# --------------------------------------------------------------------------- grid


class PenetrationResult(tuple):
    """``(height_map_mm, press_depth_mm, contact_mask)`` with named access."""

    __slots__ = ()

    @property
    def height_map_mm(self) -> torch.Tensor:
        return self[0]

    @property
    def press_depth_mm(self) -> torch.Tensor:
        return self[1]

    @property
    def contact_mask(self) -> torch.Tensor:
        return self[2]


class TaxelGrid:
    """Flat taxel grid on the gel contact face and its penetration raycast.

    Args:
        num_rows: rows of the height map (image height, along gel +Y). 60 for the
            GelSight Mini Taxim field of view.
        num_cols: columns of the height map (image width, along gel +X). 80.
        pitch: taxel spacing in metres (0.236 mm -> 18.88 x 14.16 mm field of view,
            the 640 x 480 px calibration at 0.0295 mm/px).
        normal_offset: z of the contact face in the gel frame (pad thickness, 4 mm).
        base_height_mm: height-map value where nothing touches (``height = base - depth``).
        max_dist: maximum penetration ray length in metres.
        cpd_max_dist: back-cast length in metres (``<= 0`` disables the back-cast).
        cpd_eps: back-cast start offset relative to the first hit (negative = just inside).
        device: torch/warp device.

    Taxel ``(i, j)`` sits at ``x = pitch * (j - (num_cols - 1) / 2)``,
    ``y = pitch * (i - (num_rows - 1) / 2)``, ``z = normal_offset`` in the gel frame,
    so image right is gel +X and image down is gel +Y.
    """

    def __init__(
        self,
        num_rows: int = 60,
        num_cols: int = 80,
        pitch: float = 0.000236,
        normal_offset: float = 0.004,
        base_height_mm: float = 4.0,
        max_dist: float = 0.02,
        cpd_max_dist: float = 0.5,
        cpd_eps: float = -1.0e-4,
        device: str | torch.device = "cuda",
    ):
        self.num_rows = int(num_rows)
        self.num_cols = int(num_cols)
        self.pitch = float(pitch)
        self.normal_offset = float(normal_offset)
        self.base_height_mm = float(base_height_mm)
        self.max_dist = float(max_dist)
        self.cpd_max_dist = float(cpd_max_dist)
        self.cpd_eps = float(cpd_eps)
        self.torch_device = torch.device(device)
        self.device = _wp_device(device)

        i = np.arange(self.num_rows, dtype=np.float64)
        j = np.arange(self.num_cols, dtype=np.float64)
        x = self.pitch * (j - (self.num_cols - 1) / 2.0)
        y = self.pitch * (i - (self.num_rows - 1) / 2.0)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        pts = np.stack([xx.reshape(-1), yy.reshape(-1), np.full(xx.size, self.normal_offset)], axis=1)
        self.points_local = pts.astype(np.float32)  # (P, 3), P = rows * cols, row-major
        self._taxels_wp = wp.array(self.points_local, dtype=wp.vec3, device=self.device)
        self._depth = torch.zeros(self.num_rows * self.num_cols, dtype=torch.float32, device=self.torch_device)
        self._hit = torch.zeros(self.num_rows * self.num_cols, dtype=torch.int32, device=self.torch_device)
        self._depth_wp = wp.from_torch(self._depth, dtype=wp.float32)
        self._hit_wp = wp.from_torch(self._hit, dtype=wp.int32)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.num_rows, self.num_cols)

    @property
    def fov_mm(self) -> tuple[float, float]:
        """Field of view ``(width_x, height_y)`` in mm."""
        return (self.pitch * self.num_cols * 1000.0, self.pitch * self.num_rows * 1000.0)

    def points_world(self, gel_pose7) -> torch.Tensor:
        """Taxel positions in the world frame, ``(rows, cols, 3)``."""
        p = _to_numpy(gel_pose7, np.float64).reshape(7)
        q = p[4:7]
        v = self.points_local.astype(np.float64)
        t = 2.0 * np.cross(q, v)
        w = v + p[3] * t + np.cross(q, t) + p[0:3]
        return torch.as_tensor(
            w.reshape(self.num_rows, self.num_cols, 3), dtype=torch.float32, device=self.torch_device
        )

    def penetration(self, gel_pose7, targets: Sequence[MeshTarget] | MeshTarget | None) -> PenetrationResult:
        """Raycast the grid against ``targets``.

        Args:
            gel_pose7: ``[x y z qw qx qy qz]`` world pose of the gel frame.
            targets: one or several :class:`MeshTarget`; may be empty.

        Returns:
            ``(height_map_mm, press_depth_mm, contact_mask)``: ``(rows, cols)`` float32
            map ``base_height_mm - depth_mm``, the maximum depth in mm (0-d tensor) and a
            ``(rows, cols)`` bool mask of taxels with depth > 0. All on :attr:`torch_device`.
        """
        if targets is None:
            targets = []
        elif isinstance(targets, MeshTarget):
            targets = [targets]
        targets = [t for t in targets if t is not None]
        if len(targets) == 0:
            self._depth.zero_()
            self._hit.zero_()
        else:
            ids = np.array([t.mesh_id for t in targets], dtype=np.uint64)
            xf = np.stack([t.transform_row for t in targets], axis=0).astype(np.float32)
            wp.launch(
                _penetration_kernel,
                dim=self.num_rows * self.num_cols,
                inputs=[
                    _pose7_to_transform(gel_pose7),
                    self._taxels_wp,
                    wp.array(ids, dtype=wp.uint64, device=self.device),
                    wp.array(xf, dtype=wp.transform, device=self.device),
                    self.max_dist,
                    self.cpd_max_dist,
                    self.cpd_eps,
                ],
                outputs=[self._depth_wp, self._hit_wp],
                device=self.device,
            )
            wp.synchronize_device(self.device)
        depth_mm = self._depth.view(self.num_rows, self.num_cols) * 1000.0
        height = self.base_height_mm - depth_mm
        press = depth_mm.amax()
        contact = (self._hit.view(self.num_rows, self.num_cols) != 0) & (depth_mm > 0.0)
        return PenetrationResult((height.clone(), press, contact))
