"""Seeded branched cable: one articulated tree, separate colliding strands.

All lengths are metres. MJCF is the dynamic asset; OBJ/GLB are reset previews.
There are no strand actuators, elastic return springs, or runtime pose writes.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import RingGeometry, vector_text, write_ring


# Ordinary insulated conductors: red, blue, green, brown, white, yellow,
# black and grey. These are appearance choices, not electrical assignments.
COLORS = ((.62, .045, .035, 1), (.045, .23, .58, 1), (.08, .34, .12, 1),
          (.25, .10, .045, 1), (.82, .81, .74, 1), (.83, .60, .045, 1),
          (.035, .038, .043, 1), (.36, .39, .42, 1))
JACKET_COLOR = (.026, .029, .032, 1)
FILLER_COLOR = (.36, .35, .30, 1)
COPPER_COLOR = (.68, .32, .14, 1)
COPPER_EXPOSURE_M = .003


@dataclass(frozen=True)
class FiberLayout:
    seed: int = 7
    fiber_count: int = 8
    trunk_radius_m: float = .012
    trunk_length_m: float = .24
    trunk_segments: int = 6
    fiber_radius_m: float = .0012
    fiber_length_m: float = .08
    fiber_segments: int = 10
    # Tip tangent angles; the default first two segments (16 mm) exit axially.
    fan_angle_min_deg: float = 28.
    fan_angle_max_deg: float = 50.
    root_spread_m: float = .008
    ring_inner_radius_m: float = .0135
    ring_tube_radius_m: float = .004
    ring_segments: int = 64
    fiber_damping: float = .00002
    trunk_damping: float = .02
    density_kg_m3: float = 1100.

    def __post_init__(self):
        values = asdict(self)
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("All geometry and material parameters must be finite")
        for name in ("seed", "fiber_count", "trunk_segments", "fiber_segments", "ring_segments"):
            if isinstance(values[name], bool) or not isinstance(values[name], int):
                raise ValueError(f"{name} must be an integer")
        if self.seed < 0 or not 3 <= self.fiber_count <= 16:
            raise ValueError("Use a nonnegative seed and 3–16 fibers")
        if min(self.trunk_segments, self.fiber_segments) < 2 or self.ring_segments < 32:
            raise ValueError("Insufficient cable or ring resolution")
        if any(v <= 0 for k, v in values.items() if k != "seed"):
            raise ValueError("Dimensions, density and damping must be positive")
        if self.fiber_radius_m * 4 >= self.trunk_radius_m:
            raise ValueError("Branches must be substantially thinner than the trunk")
        if self.root_spread_m + self.fiber_radius_m >= self.trunk_radius_m:
            raise ValueError("Root disks must fit inside the trunk end face")
        if 2*self.root_spread_m*np.sin(np.pi/self.fiber_count) <= 2.4*self.fiber_radius_m:
            raise ValueError("Branch roots overlap or have insufficient separation")
        if self.minimum_aperture_radius <= self.trunk_radius_m:
            raise ValueError("The actual polygonal ring aperture cannot pass the trunk")
        if self.ring_inner_radius_m > 1.3*self.trunk_radius_m:
            raise ValueError("This task requires a close-fitting ring")
        if self.fiber_length_m/self.fiber_segments < 3*self.fiber_radius_m:
            raise ValueError("Fiber capsules are too short for the declared radius")
        if not 0 < self.fan_angle_min_deg < self.fan_angle_max_deg < 75:
            raise ValueError("Fan angles must satisfy 0 < min < max < 75 degrees")

    @property
    def ring(self):
        return RingGeometry(self.ring_inner_radius_m+self.ring_tube_radius_m,
                            self.ring_tube_radius_m, self.ring_segments)

    @property
    def minimum_aperture_radius(self):
        return ((self.ring_inner_radius_m+self.ring_tube_radius_m)
                * np.cos(np.pi/self.ring_segments)-self.ring_tube_radius_m)

    def fibers(self):
        """Axial exits followed by gradual outward curves, only at reset.

        Randomness changes direction and curvature, never root attachment offsets.
        Reject the whole sampled layout if independent capsules intersect.
        """
        rng = np.random.default_rng(self.seed)
        paths = []
        for i in range(self.fiber_count):
            azimuth = 2*np.pi*i/self.fiber_count
            root = np.array([self.trunk_length_m,
                             self.root_spread_m*np.cos(azimuth),
                             self.root_spread_m*np.sin(azimuth)])
            theta = np.radians(rng.uniform(self.fan_angle_min_deg, self.fan_angle_max_deg))
            bend = rng.uniform(-.06, .06)
            curl = rng.uniform(-.12, .12)
            points = [root]
            for j in range(self.fiber_segments):
                t = j/(self.fiber_segments-1)
                u = np.clip((t-.16)/.84, 0., 1.)
                # Smoothstep gives a tangent-continuous bend after the sleeve.
                # These angles initialize body frames, never a spring target.
                angle = theta*u*u*(3-2*u)+bend*u*np.sin(np.pi*u)
                phi = azimuth+curl*np.sin(np.pi*u)
                direction = [np.cos(angle), np.sin(angle)*np.cos(phi), np.sin(angle)*np.sin(phi)]
                points.append(points[-1]+self.fiber_length_m/self.fiber_segments*np.array(direction))
            paths.append(np.array(points))
        clearance = minimum_fiber_clearance(paths, self.fiber_radius_m)
        if clearance <= 0:
            raise ValueError(f"Seed {self.seed} produces intersecting fibers ({clearance:g} m)")
        return paths


def segment_distance(a, b, c, d):
    """Exact distance between two finite 3-D segments, including parallel cases."""
    u, v, w = b-a, d-c, a-c
    aa, bb, cc = u@u, u@v, v@v
    dd, ee = u@w, v@w
    denom = aa*cc-bb*bb
    candidates = [(0., np.clip(ee/cc, 0, 1)), (1., np.clip((ee+bb)/cc, 0, 1)),
                  (np.clip(-dd/aa, 0, 1), 0.), (np.clip((bb-dd)/aa, 0, 1), 1.)]
    if denom > 1e-18:
        s, t = (bb*ee-cc*dd)/denom, (aa*ee-bb*dd)/denom
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append((s, t))
    return min(float(np.linalg.norm(w+s*u-t*v)) for s, t in candidates)


def minimum_fiber_clearance(paths, radius):
    return min(segment_distance(a, b, c, d)-2*radius
               for i, p in enumerate(paths) for q in paths[i+1:]
               for a, b in zip(p[:-1], p[1:]) for c, d in zip(q[:-1], q[1:]))


def frame(direction):
    x = direction/np.linalg.norm(direction)
    y = np.cross([0., 0., 1.], x)
    y /= np.linalg.norm(y)
    return Rotation.from_matrix(np.column_stack((x, y, np.cross(x, y))))


def shape_in_root_frame(paths):
    """Remove the trunk's translation/rotation using its fixed root circle.

    This distinguishes actual strand bending from merely bending the trunk.
    """
    paths = np.asarray(paths)
    roots = paths[:, 0]
    center = roots.mean(axis=0)
    angles = np.arange(len(roots))*2*np.pi/len(roots)
    y = ((roots-center)*np.cos(angles)[:, None]).sum(axis=0)
    z = ((roots-center)*np.sin(angles)[:, None]).sum(axis=0)
    y /= np.linalg.norm(y)
    z -= y*(y@z)
    z /= np.linalg.norm(z)
    return (paths-center)@np.column_stack((np.cross(y, z), y, z))


def write_bundle(path, layout, paths, *, fixture=False):
    root = ET.Element("mujoco", model="fiber_bundling")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    defaults = ET.SubElement(root, "default")
    ET.SubElement(defaults, "geom", density=str(layout.density_kg_m3), friction="0.35 0.005 0.0001",
                  solref="0.002 1", solimp="0.95 0.99 0.001")
    assets = ET.SubElement(root, "asset")
    # The cut sheath is visual only; the original solid trunk collision stays.
    ET.SubElement(assets, "mesh", name="jacket_lip", file="jacket_lip.obj")
    for name in ("jacket_segment", "jacket_end_segment"):
        ET.SubElement(assets, "mesh", name=name, file=f"{name}.obj")
    world = ET.SubElement(root, "worldbody")
    parent = world
    step = layout.trunk_length_m/layout.trunk_segments
    for i in range(layout.trunk_segments):
        parent = ET.SubElement(parent, "body", name=f"trunk_{i:02d}",
                               pos=vector_text((0 if i == 0 else step, 0, 0)), gravcomp="1")
        if i == 0:
            if not fixture:
                ET.SubElement(parent, "freejoint", name="trunk_free")
        else:
            ET.SubElement(parent, "joint", name=f"trunk_bend_{i:02d}", type="ball",
                          damping=str(layout.trunk_damping), stiffness="0", armature="0.000001")
        ET.SubElement(parent, "geom", name=f"trunk_shell_{i:02d}", type="cylinder",
                      fromto=vector_text((0, 0, 0, step, 0, 0)), size=str(layout.trunk_radius_m),
                      group="3", rgba=vector_text(JACKET_COLOR))
        ET.SubElement(parent, "geom", name=f"trunk_joint_cover_{i:02d}", type="sphere",
                      size=str(layout.trunk_radius_m), group="3", rgba=vector_text(JACKET_COLOR))
        ET.SubElement(parent, "geom", name=f"jacket_visual_{i:02d}", type="mesh",
                      mesh="jacket_end_segment" if i == layout.trunk_segments-1 else "jacket_segment",
                      contype="0", conaffinity="0", mass="0", rgba=vector_text(JACKET_COLOR))
        if i == layout.trunk_segments-1:
            ET.SubElement(parent, "geom", name="jacket_cut_lip", type="mesh", mesh="jacket_lip",
                          pos=vector_text((step-.001, 0, 0)), contype="0", conaffinity="0", mass="0",
                          rgba=vector_text(JACKET_COLOR))
            ET.SubElement(parent, "geom", name="jacket_inner_filler", type="cylinder",
                          fromto=vector_text((step-.0015, 0, 0, step-.001, 0, 0)),
                          size=str(layout.trunk_radius_m*.855), contype="0", conaffinity="0", mass="0",
                          rgba=vector_text(FILLER_COLOR))
    for i, points in enumerate(paths):
        previous = parent
        previous_rotation = Rotation.identity()
        previous_origin = np.array([layout.trunk_length_m-step, 0., 0.])
        for j, (a, b) in enumerate(zip(points[:-1], points[1:])):
            rotation = frame(b-a)
            local = previous_rotation.inv()*rotation
            body = ET.SubElement(previous, "body", name=f"fiber_{i:02d}_{j:02d}",
                pos=vector_text(previous_rotation.inv().apply(a-previous_origin)),
                quat=vector_text(local.as_quat()[[3, 0, 1, 2]]), gravcomp="1")
            ET.SubElement(body, "joint", name=f"fiber_bend_{i:02d}_{j:02d}", type="ball",
                          damping=str(layout.fiber_damping), stiffness="0", armature="0.00000001")
            # A small root inset prevents the hemispherical cap penetrating the
            # trunk end face. The joint itself remains exactly on that face.
            inset = 2.5*layout.fiber_radius_m if j == 0 else 0.
            ET.SubElement(body, "geom", name=f"fiber_surface_{i:02d}_{j:02d}", type="capsule",
                          fromto=vector_text((inset, 0, 0, np.linalg.norm(b-a), 0, 0)),
                          size=str(layout.fiber_radius_m), group="3", rgba=vector_text(COLORS[i % len(COLORS)]))
            length = float(np.linalg.norm(b-a))
            tip = j == layout.fiber_segments-1
            exposed = min(COPPER_EXPOSURE_M, length*.4)
            ET.SubElement(body, "geom", name=f"insulation_{i:02d}_{j:02d}", type="cylinder" if tip else "capsule",
                          fromto=vector_text((0, 0, 0, length-exposed if tip else length, 0, 0)),
                          size=str(layout.fiber_radius_m), contype="0", conaffinity="0", mass="0",
                          rgba=vector_text(COLORS[i % len(COLORS)]))
            if tip:
                # Seven fine copper filaments stay inside the collision capsule.
                for k in range(7):
                    offset = np.zeros(2) if k == 0 else layout.fiber_radius_m*.36*np.array([
                        np.cos((k-1)*np.pi/3), np.sin((k-1)*np.pi/3)])
                    ET.SubElement(body, "geom", name=f"copper_{i:02d}_{k}", type="cylinder",
                        fromto=vector_text((length-exposed, *offset, length, *offset)),
                        size=str(layout.fiber_radius_m*.20), contype="0", conaffinity="0", mass="0",
                        rgba=vector_text(COPPER_COLOR))
            previous, previous_rotation, previous_origin = body, rotation, a
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)


def generate_assets(folder, layout=None):
    import trimesh
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    def finish(mesh, color, roughness, metallic=0.):
        mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)),
            material=PBRMaterial(baseColorFactor=color, roughnessFactor=roughness, metallicFactor=metallic))
        return mesh

    layout = layout or FiberLayout()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = layout.fibers()
    lip = trimesh.creation.annulus(r_min=layout.trunk_radius_m*.86, r_max=layout.trunk_radius_m,
                                   height=.002, sections=64)
    lip.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], [1, 0, 0]))
    lip.export(folder/"jacket_lip.obj")
    # Open sidewalls avoid smoothed cap normals making every articulated
    # segment look like a separate rounded bead in the continuous jacket.
    for name, inset in (("jacket_segment", 0.), ("jacket_end_segment", .002)):
        length = layout.trunk_length_m/layout.trunk_segments-inset
        tube = trimesh.creation.cylinder(radius=layout.trunk_radius_m,
                                        segment=((0, 0, 0), (length, 0, 0)), sections=64)
        tube.update_faces(np.abs(tube.face_normals[:, 0]) < .5)
        tube.remove_unreferenced_vertices()
        radial = tube.vertices.copy()
        radial[:, 0] = 0
        tube.vertex_normals = radial/np.linalg.norm(radial, axis=1)[:, None]
        tube.export(folder/f"{name}.obj", include_normals=True)
    write_bundle(folder/"bundle.xml", layout, paths)
    ring_report = write_ring(folder/"ring.urdf", layout.ring, color=(.86, .60, .20, 1))
    preview = trimesh.Scene()
    for name, points, radius, color in [("trunk", np.array([[0, 0, 0], [layout.trunk_length_m, 0, 0]]),
                                         layout.trunk_radius_m, JACKET_COLOR)] + [
            (f"fiber_{i:02d}", p, layout.fiber_radius_m, COLORS[i % len(COLORS)]) for i, p in enumerate(paths)]:
        points = points.copy()
        end = points[-1].copy()
        direction = (points[-1]-points[-2])/np.linalg.norm(points[-1]-points[-2])
        exposure = min(COPPER_EXPOSURE_M, layout.fiber_length_m/layout.fiber_segments*.4)
        points[-1] -= direction*(.002 if name == "trunk" else exposure)
        pieces = [trimesh.creation.cylinder(radius=radius, segment=(a, b), sections=32)
                  for a, b in zip(points[:-1], points[1:])]
        pieces += [trimesh.creation.icosphere(subdivisions=1, radius=radius).apply_translation(p)
                   for p in points[1:-1]]
        mesh = trimesh.util.concatenate(pieces)
        finish(mesh, color, .68 if name == "trunk" else .34)
        preview.add_geometry(mesh, node_name=name, geom_name=name)
        if name == "trunk":
            preview.add_geometry(finish(lip.copy().apply_translation(end-[.001, 0, 0]), JACKET_COLOR, .68),
                                 node_name="jacket_cut_lip", geom_name="jacket_cut_lip")
            filler = trimesh.creation.cylinder(radius=radius*.855, sections=48,
                segment=(end-[.0015, 0, 0], end-[.001, 0, 0]))
            preview.add_geometry(finish(filler, FILLER_COLOR, .8), node_name="filler", geom_name="filler")
        else:
            axes = frame(direction).as_matrix()
            strands = []
            for k in range(7):
                offset = np.zeros(3) if k == 0 else radius*.36*(
                    np.cos((k-1)*np.pi/3)*axes[:, 1]+np.sin((k-1)*np.pi/3)*axes[:, 2])
                strands.append(trimesh.creation.cylinder(radius=radius*.20, sections=12,
                    segment=(points[-1]+offset, end+offset)))
            copper = finish(trimesh.util.concatenate(strands), COPPER_COLOR, .27, .85)
            preview.add_geometry(copper, node_name=name+"_copper", geom_name=name+"_copper")
    preview.export(folder/"bundle_initial.glb")
    preview.to_geometry().export(folder/"bundle_initial.obj")
    torus = trimesh.creation.torus(major_radius=layout.ring.radius_m,
                                  minor_radius=layout.ring.tube_radius_m,
                                  major_sections=layout.ring_segments, minor_sections=16)
    torus.export(folder/"ring.obj")
    # Nyx's URDF loader aliases repeated primitive visuals. Use a single
    # embedded-material visual mesh, keeping every compound collision shape.
    torus.visual = TextureVisuals(uv=np.zeros((len(torus.vertices), 2)),
        material=PBRMaterial(baseColorFactor=(.86, .60, .20, 1), metallicFactor=.65, roughnessFactor=.3))
    torus.export(folder/"ring.glb", include_normals=True)
    ring_xml = ET.parse(folder/"ring.urdf")
    link = ring_xml.getroot().find("link")
    for visual in list(link.findall("visual")):
        link.remove(visual)
    visual = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(visual, "geometry"), "mesh", filename="ring.glb")
    ET.indent(ring_xml)
    ring_xml.write(folder/"ring.urdf", encoding="unicode", xml_declaration=True)
    (folder/"centerlines.json").write_text(json.dumps({"frame": "trunk_root; +x toward branches",
        "fibers_m": [p.tolist() for p in paths]}, indent=2)+"\n")
    report = {"schema_version": 1, "layout": asdict(layout), "dynamic_asset": "bundle.xml",
              "appearance": "black cable jacket, cut sheath and filler, PVC insulated cores, 3 mm stranded copper tips",
              "visual_only_details": "sheath lip, filler, copper tips; collision envelopes unchanged in radius",
              "model": "passive articulated capsule strands; gravity compensation 1",
              "gravity_scope": "entire cable, including trunk; world gravity unchanged",
              "root_constraint": "ball joints with fixed positional offsets on trunk end face",
              "initial_curve": "axial sleeve exit, then smooth outward bend; initialization only",
              "shape_retention": "zero spring stiffness; viscous damping; no contact-free gravity sag",
              "fiber_min_initial_surface_clearance_m": minimum_fiber_clearance(paths, layout.fiber_radius_m),
              "ring_min_aperture_radius_m": layout.minimum_aperture_radius,
              "trunk_radial_clearance_m": layout.minimum_aperture_radius-layout.trunk_radius_m,
              "initial_radial_envelope_m": max(float(np.linalg.norm(p[:, 1:], axis=1).max()) for p in paths),
              "graspable_links": [f"trunk_{i:02d}" for i in range(layout.trunk_segments)],
              "fiber_actuators": 0, "ring": ring_report, "full_task_qualified": False}
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())
              if p.is_file() and p.name != "sha256.json"}
    (folder/"sha256.json").write_text(json.dumps(hashes, indent=2)+"\n")
    return layout, report
