"""Cast Keyhole plate geometry for the YAMLab port (pure numpy + trimesh).

Source: ported from the old RoboTangle generator
``yamlab_port/ref/topogym_2dafa5f/topogym/assets/geometry/cast_keyhole.py``
(``polygon_slabs``, ``extrude_slabs``, ``plate_assembly_transforms``,
``generate_variant_assets``) and the scene placement in
``topogym/tasks/cast_keyhole/common.py`` (``CastKeyholeTask.declare``) plus the
goal region rule ``topogym/tasks/placement.py::choose_region``.
The geometry records in ``records/<tier>.json`` are verbatim copies of
``topogym/assets/resources/variations/cast_keyhole/{very_easy,easier,F1}/geometry.json``.

Frames
- plate frame: the authored 2-D outline (mm, x across, y along the plate, z = normal), scaled by ``scale``.
- assembly frame: ``plate_assembly_transforms`` (gold: Rz90*Rx90, shifted by gold_offset_z; silver: Rx90).
- part frame (= the STL frame of the package): assembly axes, origin at the axis-aligned bbox centre of the
  part's visual mesh.  This is the frame of the rigid bodies in the YAMLab task.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
RECORDS = HERE / "records"
NAMES = ("gold", "silver")


def load_record(tier):
    return json.loads((RECORDS / f"{tier}.json").read_text())


def polygon_slabs(rings):
    """Even/odd polygon fill, including holes, cut into convex trapezoids (verbatim port)."""
    rings = [np.round(np.asarray(ring, float), 8) for ring in rings]
    edges = [(a, b) for ring in rings for a, b in zip(ring, np.roll(ring, -1, axis=0))]
    ys = np.unique(np.concatenate(rings)[:, 1])
    cells = []
    for lo, hi in zip(ys[:-1], ys[1:]):
        mid = (lo + hi) / 2
        hits = []
        for a, b in edges:
            if min(a[1], b[1]) < mid < max(a[1], b[1]):
                x = lambda y: a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                hits.append((x(mid), x(lo), x(hi)))
        hits.sort()
        if len(hits) % 2:
            raise ValueError("Invalid outline scanline")
        for left, right in zip(hits[::2], hits[1::2]):
            cell = np.round([[left[1], lo], [right[1], lo], [right[2], hi], [left[2], hi]], 8)
            if right[0] - left[0] <= 1e-9:
                raise ValueError("Degenerate or crossed outline")
            cells.append(cell)
    return cells


def extrude_slabs(cells, thickness):
    """Watertight visual + exact non-overlapping convex prisms (verbatim port)."""
    row_points = {}
    for cell in cells:
        for x, y in cell:
            row_points.setdefault(y, set()).add(x)
    vertices, faces = [], []
    perimeter_edges = {}
    collision = []
    for cell in cells:
        outline = []
        for a, b in zip(cell, np.roll(cell, -1, axis=0)):
            if np.linalg.norm(b - a) < 1e-9:
                continue
            outline.append(a)
            if a[1] == b[1]:
                xs = sorted(x for x in row_points[a[1]] if min(a[0], b[0]) + 1e-9 < x < max(a[0], b[0]) - 1e-9)
                if b[0] < a[0]:
                    xs.reverse()
                outline.extend(np.array([x, a[1]]) for x in xs)
        outline = np.asarray(outline)
        center = outline.mean(axis=0)
        for side in (-1, 1):
            for a, b in zip(outline, np.roll(outline, -1, axis=0)):
                tri = np.c_[np.vstack((center, a, b)), np.full(3, side * thickness / 2)]
                if side < 0:
                    tri = tri[::-1]
                index = len(vertices)
                vertices.extend(tri)
                faces.append([index, index + 1, index + 2])
        for a, b in zip(outline, np.roll(outline, -1, axis=0)):
            key = tuple(sorted((tuple(a), tuple(b))))
            if key in perimeter_edges:
                del perimeter_edges[key]
            else:
                perimeter_edges[key] = (a, b)
        collision.append(trimesh.convex.convex_hull(np.vstack((
            np.c_[cell, np.full(4, -thickness / 2)], np.c_[cell, np.full(4, thickness / 2)]))))
    for a, b in perimeter_edges.values():
        index = len(vertices)
        vertices.extend([[*a, -thickness / 2], [*b, -thickness / 2], [*b, thickness / 2], [*a, thickness / 2]])
        faces.extend([[index, index + 1, index + 2], [index, index + 2, index + 3]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True), collision


def plate_assembly_transforms(record):
    """Plate-local (scaled metres) -> assembly transforms (verbatim port)."""
    rx = Rotation.from_euler("x", 90, degrees=True).as_matrix()
    rz = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    result = {name: np.eye(4) for name in NAMES}
    result["gold"][:3, :3] = rz @ rx
    result["gold"][2, 3] = record.get("gold_offset_z_mm", -47.0) * (record["scale"] / 1000.)
    result["silver"][:3, :3] = rx
    if "silver_pose" in record:
        pose = record["silver_pose"]
        result["silver"][:3, :3] = Rotation.from_euler("xyz", pose["rotation_xyz_deg"], degrees=True).as_matrix()
        result["silver"][:3, 3] = np.asarray(pose["position_mm"]) * record["scale"] / 1000.
    return result


class Plate:
    """One plate: visual mesh and convex cells in the assembly frame (m), plus plate-frame data."""

    def __init__(self, name, visual, cells, plate_to_asm, rings):
        self.name, self.visual, self.cells, self.plate_to_asm, self.rings = name, visual, cells, plate_to_asm, rings
        lo, hi = visual.bounds
        self.bbox_center_asm = (lo + hi) / 2           # part-frame origin in the assembly frame
        self.extent = hi - lo

    def cells_part(self):
        return [c.copy().apply_translation(-self.bbox_center_asm) for c in self.cells]

    def visual_part(self):
        return self.visual.copy().apply_translation(-self.bbox_center_asm)


def build_plates(record):
    """generate_variant_assets without file output: dict name -> Plate (assembly frame, metres)."""
    unit = record["scale"] / 1000.
    transforms = plate_assembly_transforms(record)
    plates = {}
    for name in NAMES:
        layers = record.get("layers", {}).get(name, [dict(
            z_min_mm=-record["thickness_mm"] / 2, z_max_mm=record["thickness_mm"] / 2,
            rings_mm=record["rings_mm"][name])])
        meshes, cells = [], []
        for layer in layers:
            lo, hi = layer["z_min_mm"], layer["z_max_mm"]
            mesh, parts = extrude_slabs(polygon_slabs([np.asarray(r) for r in layer["rings_mm"]]), hi - lo)
            for part in [mesh, *parts]:
                part.apply_translation([0, 0, (hi + lo) / 2])
                part.apply_scale(unit)
            meshes.append(mesh)
            cells.extend(parts)
        if len(meshes) != 1:
            raise NotImplementedError("multi-layer plates need a boolean union (manifold3d)")
        mesh = meshes[0]
        for part in [mesh, *cells]:
            part.apply_transform(transforms[name])
        plates[name] = Plate(name, mesh, cells, transforms[name], record["rings_mm"][name])
    return plates


def scene_rotation(yaw_deg=0., assembly_roll_deg=45.):
    """Old CastKeyholeTask.declare: assembly frame -> old world/table axes."""
    return (Rotation.from_euler("z", yaw_deg, degrees=True) * Rotation.from_euler("y", 90, degrees=True)
            * Rotation.from_euler("z", assembly_roll_deg, degrees=True))


def old_start_poses(plates, center_xy_table_m=(0.0, 0.05), clearance=.0005):
    """Start poses of the part frames in the OLD TABLE frame (m), as in declare() (table top z = 0).

    The old centre_xy is (-0.1356786, 0.05) in the old world; the table frame origin is at world x -0.135679,
    so the table-frame centre is (0, 0.05).
    """
    rot = scene_rotation()
    verts = np.concatenate([rot.apply(p.visual.vertices) for p in plates.values()])
    mid = (verts.min(0) + verts.max(0)) / 2
    origin = np.r_[np.asarray(center_xy_table_m) - mid[:2], -verts[:, 2].min() + clearance]
    return {n: (origin + rot.apply(p.bbox_center_asm), rot) for n, p in plates.items()}


def choose_goal_region(gold_points_xy, silver_points, margin=.03):
    """placement.choose_region for side (+y) only, in the frame of the given points (m).

    Returns dict(center_xy, half, height, normal, offset). Table bounds / mount exclusions of the old
    scene did not bind for the nominal +y candidate (verified against the package numbers)."""
    rigid_size = float(np.linalg.norm(np.ptp(silver_points, axis=0)))
    half = max(.10, rigid_size / 2 + .015)
    height = max(.15, rigid_size + .02)
    edge = float(np.max(gold_points_xy[:, 1])) + .005
    return dict(center_xy=None, center_y=edge + margin + half, half=half, height=height,
                normal=(0., 1.), offset=edge, rigid_size=rigid_size)
