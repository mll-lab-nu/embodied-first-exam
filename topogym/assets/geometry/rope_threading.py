"""Offline, metric task assets with explicit source-to-table transformation."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.assets.library import resource_path
REFERENCE = resource_path("rope_threading/reference.json")


@dataclass(frozen=True)
class ThreadingLayout:
    translation_m: tuple = (0., 0., .0009)
    yaw_deg: float = 0.
    rope_subdivisions: int = 4
    radial_segments: int = 12
    ring_radial_segments: int = 24
    rope_height_offset_m: float = 0.
    centerline_interpolation: str = 'linear'
    ring_ids: tuple[str, ...] | None = None
    ring_inner_radius_m: float | None = None

    def __post_init__(self):
        if not np.isfinite(self.yaw_deg):
            raise ValueError("yaw_deg must be finite")
        if np.asarray(self.translation_m).shape != (3,) or not np.isfinite(self.translation_m).all():
            raise ValueError("translation_m must be a finite 3-vector")
        if not np.isfinite(self.rope_height_offset_m) or self.rope_height_offset_m < 0:
            raise ValueError("rope_height_offset_m must be finite and nonnegative")
        if self.centerline_interpolation not in ('linear', 'circular_arc'):
            raise ValueError('Unknown centerline interpolation')
        for key, lower in (("rope_subdivisions", 1), ("radial_segments", 8), ("ring_radial_segments", 12)):
            value = getattr(self, key)
            if isinstance(value, bool) or int(value) != value or value < lower:
                raise ValueError(f"{key} must be an integer >= {lower}")
        source_ids = tuple(ring["name"] for ring in self.reference["rings"])
        if self.ring_ids is not None:
            selected = tuple(self.ring_ids)
            if (not selected or len(set(selected)) != len(selected)
                    or any(name not in source_ids for name in selected)
                    or selected != tuple(name for name in source_ids if name in selected)):
                raise ValueError("ring_ids must be a nonempty ordered subset of source ring IDs")
            object.__setattr__(self, "ring_ids", selected)
        if (self.ring_inner_radius_m is not None
                and (isinstance(self.ring_inner_radius_m, bool)
                     or not np.isfinite(self.ring_inner_radius_m)
                     or self.ring_inner_radius_m <= self.radius)):
            raise ValueError("Ring inner radius must be finite and larger than the rope radius")

    @property
    def reference(self):
        return json.loads(REFERENCE.read_text())

    @property
    def radius(self):
        return self.reference["rope_radius_m"]

    @property
    def rope_radius_m(self):
        """Shared FEM diagnostic protocol."""
        return self.radius

    def transform(self, points):
        return Rotation.from_euler('z',self.yaw_deg,degrees=True).apply(
            np.asarray(points, dtype=float))+np.asarray(self.translation_m)

    def centerline(self):
        source = np.asarray(self.reference["rope_nodes_m"])
        if self.centerline_interpolation == 'circular_arc':
            # The public initialization is a planar semicircle. Subdividing
            # its chords concentrates the same 2.25-degree corners into
            # shorter FEM elements; instead sample the common smooth arc.
            xy = source[:, :2]
            fit = np.linalg.lstsq(np.c_[2*xy, np.ones(len(xy))],
                                  np.sum(xy*xy, axis=1), rcond=None)[0]
            center = fit[:2]
            radius = np.sqrt(fit[2]+center@center)
            if (np.max(abs(np.linalg.norm(xy-center, axis=1)-radius)) > 1.e-8
                    or np.ptp(source[:, 2]) > 1.e-10):
                raise ValueError('Circular interpolation requires a planar circular reference')
            angles = np.unwrap(np.arctan2(xy[:, 1]-center[1], xy[:, 0]-center[0]))
            changes = np.diff(angles)
            if not (np.all(changes > 0) or np.all(changes < 0)):
                raise ValueError('Circular material coordinates must be monotonic')
            parameter = np.arange((len(source)-1)*self.rope_subdivisions+1)/self.rope_subdivisions
            angle = np.interp(parameter, np.arange(len(source)), angles)
            points = np.c_[center+radius*np.c_[np.cos(angle), np.sin(angle)],
                           np.full(len(angle), source[0, 2])]
            points[::self.rope_subdivisions] = source
        else:
            t = np.arange(self.rope_subdivisions)/self.rope_subdivisions
            points = source[:-1, None, :]+t[None, :, None]*np.diff(source, axis=0)[:, None, :]
            points = np.vstack((points.reshape(-1, 3), source[-1]))
        result = self.transform(points)
        result[:, 2] += self.rope_height_offset_m
        return result

    def rings(self):
        rotation = Rotation.from_euler('z',self.yaw_deg,degrees=True)
        sources = self.reference["rings"]
        if self.ring_ids is not None:
            sources = [ring for ring in sources if ring["name"] in self.ring_ids]
        if self.ring_inner_radius_m is not None:
            for ring in sources:
                new_radius = float(self.ring_inner_radius_m)+ring["tube_radius_m"]
                # Authored stands meet the rim along horizontal basis_u. Keep
                # the ring centre/plane fixed; move its stand and foot together.
                direction = np.asarray(ring["basis_u"], dtype=float)
                if abs(direction[2]) > 1e-8:
                    raise ValueError("Aperture resizing requires a horizontal rim mount")
                shift = (new_radius-ring["radius_m"])*direction
                for kind in ("stand", "base"):
                    ring[kind]["position"] = (np.asarray(ring[kind]["position"])+shift).tolist()
                ring["radius_m"] = new_radius
        return [dict(ring, center_m=self.transform(ring["center_m"]).tolist(),
                     **{key: rotation.apply(ring[key]).tolist()
                        for key in ('normal','basis_u','basis_v')})
                for ring in sources]

    def required_crossings(self):
        """Signed material order for this candidate; no runtime success claim.

        Task terminal integration must consume this instead of assuming R1/R2/R3
        before a reduced-ring layout can be published as a difficulty tier.
        """
        selected = {ring["name"] for ring in self.rings()}
        return [(entry[:-1], 1 if entry[-1] == "+" else -1)
                for entry in self.reference["target_material_order"] if entry[:-1] in selected]


def route_crossings(points, rings, rope_radius=0.):
    """Signed plane crossings ordered along the source material coordinate.

    This is a geometry observation, not a continuous contact/success certificate.
    Disk radius includes nominal rope clearance; tangencies are excluded.
    """
    p = np.asarray(points, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2 or not np.isfinite(p).all():
        raise ValueError("Expected a finite Nx3 centerline")
    hits = []
    for ring in rings:
        center, normal = np.asarray(ring["center_m"]), np.asarray(ring["normal"])
        d = (p-center)@normal
        away = np.flatnonzero(abs(d) > 1e-10)
        for left, right in zip(away[:-1], away[1:]):
            # An isolated on-plane vertex counts once only if its neighbours
            # are on opposite sides. Coplanar runs and touches are ambiguous.
            if d[left]*d[right] >= 0 or right-left > 2:
                continue
            i = left
            t = -d[i]/(d[i+1]-d[i])
            point = p[i]+t*(p[i+1]-p[i])
            if np.linalg.norm(point-center) < ring["radius_m"]-ring["tube_radius_m"]-rope_radius:
                hits.append(dict(ring=ring["name"], sign=1 if d[right] > d[left] else -1,
                                 material_coordinate=float(i+t), point_m=point.tolist()))
    return sorted(hits, key=lambda hit: hit["material_coordinate"])


def surface_intersects_ring_disk(vertices, faces, ring):
    """Detect triangle/finite-aperture intersections, including coplanar faces."""
    points = np.asarray(vertices, dtype=float)-ring["center_m"]
    normal = np.asarray(ring["normal"])
    distances = points@normal
    if distances.min() > 1e-9 or distances.max() < -1e-9:
        return False
    radius = ring["radius_m"]-ring["tube_radius_m"]
    triangles = np.asarray(faces)
    signed = distances[triangles]
    candidates = triangles[(signed.min(1) <= 1e-9) & (signed.max(1) >= -1e-9)]

    def segment_distance(a, b):
        edge = b-a
        parameter = np.clip(-a@edge/max(float(edge@edge), 1e-30), 0, 1)
        return np.linalg.norm(a+parameter*edge)

    for face in candidates:
        tri, d = points[face], distances[face]
        intersections = [p for p, value in zip(tri, d) if abs(value) <= 1e-9]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if d[a]*d[b] < 0:
                intersections.append(tri[a]-d[a]/(d[b]-d[a])*(tri[b]-tri[a]))
        if any(np.linalg.norm(p) < radius for p in intersections):
            return True
        if any(segment_distance(a, b) < radius for i, a in enumerate(intersections) for b in intersections[i+1:]):
            return True
        if np.all(abs(d) <= 1e-9):
            # A coplanar triangle may enclose the disk without an edge inside.
            signs = [np.dot(np.cross(tri[b]-tri[a], -tri[a]), normal) for a, b in ((0, 1), (1, 2), (2, 0))]
            if min(signs) >= 0 or max(signs) <= 0:
                return True
    return False


def ring_mesh(ring, radial_segments=24):
    mesh = trimesh.creation.torus(major_radius=ring["radius_m"], minor_radius=ring["tube_radius_m"],
                                 major_sections=ring["segments"], minor_sections=radial_segments)
    basis = np.column_stack((ring["basis_u"], ring["basis_v"], ring["normal"]))
    mesh.vertices = mesh.vertices@basis.T+ring["center_m"]
    return mesh


def _material(mesh, color):
    from trimesh.visual.material import PBRMaterial
    mesh.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(
        name="threading_"+"_".join(str(int(round(float(v)*255))) for v in color),
        baseColorFactor=np.asarray(color), metallicFactor=.15, roughnessFactor=.4))
    return mesh


def inspect_geometry(layout):
    p, rings = layout.centerline(), layout.rings()
    ref = layout.reference
    table_z = ref["source_table_surface_z_m"]+layout.translation_m[2]
    floor_gap = float(p[:, 2].min()-layout.radius-table_z)
    # Conservative bound: every segment lies within half its length of a node.
    half_step = float(np.linalg.norm(np.diff(p, axis=0), axis=1).max()/2)
    gaps = []
    for ring in rings:
        delta = p-np.asarray(ring["center_m"])
        axial = delta@ring["normal"]
        radial = np.sqrt(np.maximum(0, np.sum(delta*delta, axis=1)-axial*axial))
        gaps.append(float(np.sqrt(axial**2+(radial-ring["radius_m"])**2).min()
                          -ring["tube_radius_m"]-layout.radius-half_step))
        for kind in ("stand", "base"):
            geom = ring[kind]
            center = layout.transform(geom["position"])
            if kind == "stand":
                delta = p-center
                delta[:, 2] -= np.clip(delta[:, 2], -geom["size"][1], geom["size"][1])
                gap = np.linalg.norm(delta, axis=1).min()-geom["size"][0]-layout.radius-half_step
            else:
                local = Rotation.from_euler('z', layout.yaw_deg, degrees=True).inv().apply(p-center)
                delta = np.maximum(abs(local)-geom["size"], 0.)
                gap = np.linalg.norm(delta, axis=1).min()-layout.radius-half_step
            gaps.append(float(gap))
    # Source is a simple planar U. Nonlocal clearance excludes 4 diameters of material.
    from topogym.assets.geometry.knot_untying import minimum_nonlocal_distance
    self_distance, _ = minimum_nonlocal_distance(p, 8*layout.radius)
    crossings = route_crossings(p, rings, layout.radius)
    if floor_gap < -1e-9 or min(gaps) <= 0 or self_distance <= 2*layout.radius or crossings:
        raise ValueError("Initial rope intersects the table, fixtures, itself or a ring aperture")
    return dict(rope_length_m=float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()),
        rope_diameter_m=2*layout.radius, source_nodes=81, fem_centerline_points=len(p),
        centerline_interpolation=layout.centerline_interpolation,
        table_surface_gap_m=floor_gap, minimum_fixture_gap_lower_bound_m=min(gaps),
        minimum_nonlocal_rope_surface_gap_m=self_distance-2*layout.radius,
        endpoints_m=p[[0, -1]].tolist(), initial_crossings=crossings,
        ring_aperture_diameter_m=2*(rings[0]["radius_m"]-rings[0]["tube_radius_m"]),
        ring_aperture_diameters_m={r["name"]: 2*(r["radius_m"]-r["tube_radius_m"]) for r in rings},
        selected_ring_ids=[r["name"] for r in rings],
        source_to_world_translation_m=list(layout.translation_m),
        target_material_order=[name+("+" if sign > 0 else "-") for name, sign in layout.required_crossings()],
        geometry_verified=True)


def generate_assets(folder, layout=None):
    from topogym.utils.geometry.rope import make_elastic_tube_mesh, write_obj
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    layout = layout or ThreadingLayout()
    selected = {r["name"] for r in layout.rings()}
    removed = {r["name"] for r in layout.reference["rings"]}-selected
    if any(p.stem == name or p.stem.startswith(name+"_")
           for p in folder.iterdir() for name in removed):
        raise ValueError("Use a fresh asset directory when removing source rings")
    report = inspect_geometry(layout)
    vertices, faces = make_elastic_tube_mesh(layout.centerline(), radius=layout.radius,
                                           radial_segments=layout.radial_segments)
    rope = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if not rope.is_watertight or not rope.is_volume:
        raise ValueError("Rope surface must enclose a positive volume")
    write_obj(folder/"rope.obj", vertices, faces)
    _material(rope, [.95, .48, .15, 1]).export(folder/"rope.glb")
    assembly = trimesh.Scene()
    assembly.add_geometry(rope, node_name="rope")
    for ring in layout.rings():
        mesh = _material(ring_mesh(ring, layout.ring_radial_segments), ring["rgba"])
        if not mesh.is_watertight or mesh.euler_number != 0:
            raise ValueError("Ring must be a closed genus-one mesh with an open aperture")
        mesh.export(folder/f'{ring["name"]}.obj', mtl_name=f'{ring["name"]}.mtl')
        mesh.export(folder/f'{ring["name"]}.glb')
        assembly.add_geometry(mesh, node_name=ring["name"])
        for kind in ("stand", "base"):
            geom = ring[kind]
            if kind == "stand":
                support = trimesh.creation.capsule(height=2*geom["size"][1], radius=geom["size"][0], count=[16, 16])
                support.apply_translation(-support.bounds.mean(axis=0))
            else:
                support = trimesh.creation.box(extents=2*np.asarray(geom["size"]))
            matrix = np.eye(4)
            matrix[:3,:3] = Rotation.from_euler('z',layout.yaw_deg,degrees=True).as_matrix()
            support.apply_transform(matrix)
            support.apply_translation(layout.transform(geom["position"]))
            _material(support, geom["rgba"]).export(folder/f'{ring["name"]}_{kind}.obj',
                                                   mtl_name=f'{ring["name"]}_{kind}.mtl')
            support.export(folder/f'{ring["name"]}_{kind}.glb')
            assembly.add_geometry(support, node_name=f'{ring["name"]}_{kind}')
    assembly.export(folder/"assembly.glb")
    np.save(folder/"centerline.npy", layout.centerline())
    (folder/"layout.json").write_text(json.dumps(dict(rings=layout.rings(), **report), indent=2)+"\n")
    report["reference_sha256"] = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    report["ring_collision_model"] = "nonconvex watertight torus mesh; 64 x 24 by default; aperture preserved"
    report["source_ring_discretization_deviation_bound_m"] = (
        max(r["radius_m"]*(1-np.cos(np.pi/64))
            +r["tube_radius_m"]*(1-np.cos(np.pi/layout.ring_radial_segments)) for r in layout.rings()))
    report["files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())
                       if p.suffix in (".obj", ".glb", ".mtl", ".npy")}
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    return report
