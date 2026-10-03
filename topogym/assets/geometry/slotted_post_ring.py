"""Deterministic, hole-preserving geometry for the video-derived initial state.

Dimensions are authored estimates in metres, not measurements of the video.
No solution path, physics qualification, or hidden rope constraints are implied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicHermiteSpline
from shapely.geometry import LineString, Point, box
import trimesh

from topogym.assets.library import resource_path
SOURCE_URL = "https://www.youtube.com/shorts/yZv8eUWIF-8"


@dataclass(frozen=True)
class SlottedPostLayout:
    base_width_m: float = .26
    base_depth_m: float = .19
    base_height_m: float = .022
    post_width_m: float = .072
    post_depth_m: float = .028
    post_height_m: float = .29
    slot_width_m: float = .028
    slot_bottom_m: float = .072
    slot_top_m: float = .276
    ring_major_radius_m: float = .061
    ring_tube_radius_m: float = .010
    rope_radius_m: float = .0035
    bead_radius_m: float = .0195
    bead_hole_radius_m: float = .0045
    disc_radius_m: float = .055
    disc_thickness_m: float = .011
    floor_clearance_m: float = .001

    @property
    def ring_inner_radius(self):
        return self.ring_major_radius_m - self.ring_tube_radius_m

    @property
    def ring_z(self):
        return self.base_height_m + self.ring_tube_radius_m + self.floor_clearance_m

    def validate(self):
        values = np.array(list(asdict(self).values()))
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("All geometry dimensions must be positive and finite")
        if not (self.base_height_m < self.slot_bottom_m < self.slot_top_m
                < self.base_height_m + self.post_height_m):
            raise ValueError("Slot must remain enclosed by the post")
        if not (2*self.rope_radius_m < self.slot_width_m < self.post_width_m):
            raise ValueError("Slot must admit cord and retain two solid side rails")
        if self.slot_top_m-self.slot_bottom_m <= self.slot_width_m:
            raise ValueError("The rounded slot must be taller than it is wide")
        if self.ring_inner_radius <= np.hypot(self.post_width_m, self.post_depth_m)/2:
            raise ValueError("Ring must fit around the post cross-section")
        if not (2*self.ring_tube_radius_m < self.slot_width_m
                and 2*(self.ring_major_radius_m+self.ring_tube_radius_m)
                < self.slot_top_m-self.slot_bottom_m):
            raise ValueError("The ring itself must fit edgewise through the post slot")
        if not self.rope_radius_m < self.bead_hole_radius_m < self.bead_radius_m:
            raise ValueError("Bead bore must admit the cord and retain a shell")
        if not self.slot_width_m < 2*self.bead_radius_m < 2*self.ring_inner_radius:
            raise ValueError("Beads must block the slot but fit through the ring")
        if 2*self.disc_radius_m <= 2*self.ring_inner_radius:
            raise ValueError("End discs must block direct extraction through the ring")
        if not (self.disc_thickness_m + 2*self.rope_radius_m < self.slot_width_m
                and 2*self.disc_radius_m < self.slot_top_m-self.slot_bottom_m-self.slot_width_m):
            raise ValueError("Disc and adjacent cord need an edge-on slot envelope")
        if 2*(self.ring_major_radius_m+self.ring_tube_radius_m) >= min(
                self.base_width_m, self.base_depth_m):
            raise ValueError("Base must support the initial ring")
        return self

    def post_polygon(self):
        """Cross-section in x/z, including the actual rounded through-slot."""
        radius = self.slot_width_m/2
        opening = LineString([(0, self.slot_bottom_m+radius),
                              (0, self.slot_top_m-radius)]).buffer(radius, quad_segs=20)
        outer = box(-self.post_width_m/2, self.base_height_m,
                    self.post_width_m/2, self.base_height_m+self.post_height_m)
        return outer.difference(opening)

    def cord_controls(self):
        """One open cord: left stop -> slot once -> back/right -> right stop.

        Both tails lie above/outside the ring in the initial state. The return
        tail must go around the right rail, not through a second invented slot.
        Layout v1 fixes the tail arrangement; these are not randomization axes.
        """
        c = self.floor_clearance_m
        bz = self.bead_radius_m+c
        end_z = self.disc_thickness_m+c+self.rope_radius_m+.002
        slot_z = self.slot_bottom_m+self.slot_width_m*.8
        return np.array([
            [-.092, -.281, end_z], [-.082, -.261, bz], [-.070, -.237, bz],
            [-.058, -.213, bz], [-.052, -.157, .040], [-.035, -.100, .063],
            [-.012, -.055, slot_z], [0, -.025, slot_z], [0, .025, slot_z],
            [.023, .052, slot_z], [.065, .043, .086], [.090, .004, .076],
            [.104, -.058, .060], [.108, -.125, .038], [.066, -.199, bz],
            [.078, -.223, bz], [.090, -.247, bz], [.104, -.277, end_z],
        ])

    def bead_controls(self):
        """Indices of the cord controls at the two bead centres; each bore spans index -1 .. +1."""
        return 2, len(self.cord_controls())-3

    def route_checks(self, slot_crossings, exterior_crossings, cord):
        """Checks of the cord route (layout v1: once through the slot, back round the right rail)."""
        return dict(cord_passes_slot_once=len(slot_crossings) == 1,
                    return_cord_outside_right_rail=len(exterior_crossings) == 1
                    and exterior_crossings[0][0] > self.post_width_m/2+self.rope_radius_m)


def _extrude_xz(polygon, depth):
    mesh = trimesh.creation.extrude_polygon(polygon, depth, engine="earcut")
    # (x, z, extrusion) -> (x, -extrusion, z), a proper rotation.
    mesh.apply_transform(np.array([[1, 0, 0, 0], [0, 0, -1, depth/2],
                                   [0, 1, 0, 0], [0, 0, 0, 1]]))
    return mesh


def centerline(layout, spacing=.0015):
    controls = layout.cord_controls()
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(controls, axis=0), axis=1))]
    derivatives = np.gradient(controls, s, axis=0)
    # Preserve straight, bore-aligned spans through each bead. A generic
    # interpolating spline can bow into the bead's small cylindrical bore.
    for a, b in ((k-1, k+1) for k in layout.bead_controls()):
        direction = controls[b]-controls[a]
        derivatives[a:b+1] = direction/np.linalg.norm(direction)
    dense = CubicHermiteSpline(s, controls, derivatives)(np.linspace(0, s[-1], 4000))
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))]
    target = np.linspace(0, arc[-1], int(np.ceil(arc[-1]/spacing))+1)
    return np.column_stack([np.interp(target, arc, dense[:, i]) for i in range(3)])


def tube_mesh(points, radius, sides=16):
    """Closed surface around one continuous open centerline, with end caps."""
    tangent = np.gradient(points, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.empty_like(tangent)
    seed = np.eye(3)[np.argmin(np.abs(tangent[0]))]
    normal[0] = np.cross(tangent[0], seed)
    normal[0] /= np.linalg.norm(normal[0])
    for i in range(1, len(points)):
        normal[i] = normal[i-1]-tangent[i]*np.dot(normal[i-1], tangent[i])
        normal[i] /= np.linalg.norm(normal[i])
    binormal = np.cross(tangent, normal)
    theta = np.arange(sides)*2*np.pi/sides
    vertices = (points[:, None] + radius*(np.cos(theta)[None, :, None]*normal[:, None]
                + np.sin(theta)[None, :, None]*binormal[:, None])).reshape(-1, 3)
    faces = []
    for i in range(len(points)-1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.extend([[a, b, b+sides], [a, b+sides, a+sides]])
    vertices = np.vstack([vertices, points[0], points[-1]])
    for j in range(sides):
        faces.append([len(vertices)-2, (j+1)%sides, j])
        a = (len(points)-1)*sides
        faces.append([len(vertices)-1, a+j, a+(j+1)%sides])
    return trimesh.Trimesh(vertices, faces, process=False)


def _bead(layout, position, direction):
    # Revolve the spherical shell with a real axial cylindrical bore.
    radius, hole = layout.bead_radius_m, layout.bead_hole_radius_m
    end = np.sqrt(radius**2-hole**2)
    z = np.linspace(-end, end, 65)
    profile = np.column_stack([np.sqrt(radius**2-z*z), z])
    mesh = trimesh.creation.revolve(np.vstack([profile, profile[0]]), sections=64)
    axis = np.asarray(direction)/np.linalg.norm(direction)
    transform = trimesh.geometry.align_vectors([0, 0, 1], axis)
    transform[:3, 3] = position
    mesh.apply_transform(transform)
    return mesh


def make_meshes(layout):
    layout.validate()
    base = trimesh.creation.box(extents=[layout.base_width_m, layout.base_depth_m, layout.base_height_m])
    base.apply_translation([0, 0, layout.base_height_m/2])
    post = _extrude_xz(layout.post_polygon(), layout.post_depth_m)
    ring = trimesh.creation.torus(major_radius=layout.ring_major_radius_m,
                                 minor_radius=layout.ring_tube_radius_m,
                                 major_sections=128, minor_sections=24)
    ring.apply_translation([0, 0, layout.ring_z])
    cord = centerline(layout)
    parts = {"base": base, "post": post, "target_ring": ring,
             "cord": tube_mesh(cord, layout.rope_radius_m)}
    # Bore orientation follows the cord tangent at each bead's location.
    for name, index in zip(("left", "right"), layout.bead_controls()):
        point = layout.cord_controls()[index]
        k = np.argmin(np.linalg.norm(cord-point, axis=1))
        parts[f"bead_{name}"] = _bead(layout, cord[k], cord[k+1]-cord[k-1])
    for name, x, y, endpoint in (("left", -.092, -.324, 0), ("right", .104, -.320, -1)):
        # An off-centre eye near the inner rim anchors each end of the cord.
        profile = Point(x, y).buffer(layout.disc_radius_m, quad_segs=32).difference(
            Point(*cord[endpoint, :2]).buffer(layout.bead_hole_radius_m, quad_segs=16))
        disc = trimesh.creation.extrude_polygon(profile, layout.disc_thickness_m, engine="earcut")
        disc.apply_translation([0, 0, layout.floor_clearance_m])
        parts[f"disc_{name}"] = disc
        knot = trimesh.creation.icosphere(subdivisions=2, radius=layout.rope_radius_m*1.6)
        knot.apply_translation(cord[endpoint])
        parts[f"stop_knot_{name}"] = knot
    return parts, cord


def geometry_report(layout, parts, cord):
    """Necessary geometry checks; these do NOT prove the puzzle solvable."""
    crossing = np.flatnonzero(cord[:-1, 1]*cord[1:, 1] < 0)
    slot_crossings, exterior_crossings = [], []
    for i in crossing:
        alpha = -cord[i, 1]/(cord[i+1, 1]-cord[i, 1])
        p = cord[i]+alpha*(cord[i+1]-cord[i])
        (slot_crossings if abs(p[0]) < layout.slot_width_m/2 else exterior_crossings).append(p.tolist())
    # Euclidean point-to-triangle distances: conservative by half a segment
    # and rope radius; no FCL/GPU or containment shortcut required.
    clearance = {}
    half_step = np.linalg.norm(np.diff(cord, axis=0), axis=1).max()/2
    for name in ("post", "target_ring", "base", "bead_left", "bead_right", "disc_left", "disc_right"):
        distances = []
        for chunk in np.array_split(cord, 32):
            _, distance, _ = trimesh.proximity.closest_point_naive(parts[name], chunk)
            distances.extend(distance)
        clearance[name] = float(min(distances)-layout.rope_radius_m-half_step)
    # Check non-neighbor segments via densely sampled centerline distances.
    delta = cord[:, None]-cord[None]
    distances = np.linalg.norm(delta, axis=2)
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(cord, axis=0), axis=1))]
    distances[np.abs(arc[:, None]-arc[None]) < 4*layout.rope_radius_m] = np.inf
    self_clearance = float(distances.min()-2*layout.rope_radius_m-2*half_step)
    mesh_status = {name: dict(watertight=bool(m.is_watertight),
                             volume_positive=bool(m.volume > 0),
                             euler_number=int(m.euler_number), vertices=len(m.vertices), faces=len(m.faces))
                   for name, m in parts.items()}
    aperture = dict(
        ring_post_radial_margin_m=float(layout.ring_inner_radius-np.hypot(layout.post_width_m, layout.post_depth_m)/2),
        bead_slot_blocking_margin_m=2*layout.bead_radius_m-layout.slot_width_m,
        bead_ring_diameter_margin_m=2*layout.ring_inner_radius-2*layout.bead_radius_m,
        disc_ring_blocking_margin_m=2*layout.disc_radius_m-2*layout.ring_inner_radius,
        disc_and_rope_slot_width_margin_m=layout.slot_width_m-layout.disc_thickness_m-2*layout.rope_radius_m,
        disc_slot_height_margin_m=layout.slot_top_m-layout.slot_bottom_m-layout.slot_width_m-2*layout.disc_radius_m)
    checks = dict(meshes_closed_and_positive=all(v["watertight"] and v["volume_positive"] for v in mesh_status.values()),
                  post_and_ring_have_real_holes=all(parts[n].euler_number == 0 for n in ("post", "target_ring")),
                  **layout.route_checks(slot_crossings, exterior_crossings, cord),
                  cord_clear_of_solid_parts=min(clearance.values()) > 0,
                  cord_clear_of_table=float(cord[:, 2].min()) > layout.rope_radius_m,
                  no_nonlocal_cord_overlap=self_clearance > 0,
                  aperture_relations_valid=min(aperture.values()) > 0)
    return dict(scope="static_authored_geometry_only", passed=all(checks.values()), checks=checks,
                dimensions=asdict(layout), meshes=mesh_status, aperture_margins=aperture,
                cord_length_m=float(arc[-1]), cord_segments=len(cord)-1,
                cord_clearance_lower_bounds_m=clearance, cord_self_clearance_bound_m=self_clearance,
                slot_crossings=slot_crossings, exterior_crossings=exterior_crossings,
                endpoint_model="geometry preview only; TaskSpec declares permanent endpoints and the runtime FEM volume includes end stops",
                physics_qualified=False, solution_verified=False, robot_reachability_verified=False)


def _finish(mesh, name):
    from PIL import Image
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    result = mesh.copy()
    if name == "cord" or name.startswith("stop_knot"):
        result.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
            name=f"slotted_{name}", baseColorFactor=[.91, .89, .81, 1], roughnessFactor=.88, metallicFactor=0))
        return result
    texture_file = resource_path("hedgehog_in_cage/materials/" + (
        "light_wood.png" if name == "base" or name.startswith("bead") else "dark_wood.png"))
    vertices = mesh.vertices[mesh.faces].reshape(-1, 3)
    normals = mesh.vertex_normals[mesh.faces].reshape(-1, 3)
    dominant = np.repeat(np.argmax(np.abs(mesh.face_normals), axis=1), 3)
    u, v = np.where(dominant == 0, 1, 0), np.where(dominant == 2, 1, 2)
    rows = np.arange(len(vertices))
    uv = np.column_stack([vertices[rows, u], vertices[rows, v]])/.16+.5
    with Image.open(texture_file) as source:
        texture = source.convert("RGB")
    result = trimesh.Trimesh(vertices, np.arange(len(vertices)).reshape(-1, 3),
                             vertex_normals=normals, process=False)
    result.visual = TextureVisuals(uv=uv, material=PBRMaterial(
        name=f"slotted_{name}", baseColorFactor=[1., 1., 1., 1.], baseColorTexture=texture,
        roughnessFactor=.48, metallicFactor=0))
    return result


def generate_assets(output, layout=None):
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    layout = (layout or SlottedPostLayout()).validate()
    parts, cord = make_meshes(layout)
    report = geometry_report(layout, parts, cord)
    if not report["passed"]:
        raise ValueError(f"Invalid reconstruction: {report['checks']}; clearance={report['cord_clearance_lower_bounds_m']}")
    scene = trimesh.Scene()
    for name, mesh in parts.items():
        mesh.export(folder/f"{name}.obj")
        visual = _finish(mesh, name)
        visual.export(folder/f"{name}.glb")
        scene.add_geometry(visual, node_name=name)
    scene.export(folder/"scene.glb")
    np.save(folder/"cord_centerline.npy", cord)
    (folder/"layout.json").write_text(json.dumps(asdict(layout), indent=2)+"\n")
    (folder/"geometry_report.json").write_text(json.dumps(report, indent=2)+"\n")
    files = [p for p in folder.iterdir() if p.suffix in (".obj", ".glb", ".npy", ".json") and p.name != "sha256.json"]
    (folder/"sha256.json").write_text(json.dumps(
        {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}, indent=2)+"\n")
    return layout, report
