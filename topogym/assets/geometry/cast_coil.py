"""Two open square coils reconstructed from photos, not a certified replica.

Coordinates: x/z span the square face, y orders the four alternating layers.
The solid is an exact union/difference of axis-aligned boxes. Coordinate-plane
partitioning produces disjoint collision boxes and a watertight outer boundary;
neither a whole-piece convex hull nor overlapping mass estimates are used.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from topogym.utils.geometry.rigid_geometry import vector_text

from topogym.assets.library import resource_path


def load_template(path=None):
    return json.loads(Path(path or resource_path("cast_coil/template.json")).read_text())


def box(x, y, z):
    return np.array([x, y, z], dtype=float).T


def occupied(points, boxes):
    p, b = np.asarray(points), np.asarray(boxes)
    return np.any(np.all((p[..., None, :] >= b[:, 0]) &
                         (p[..., None, :] <= b[:, 1]), axis=-1), axis=-1)


def partition_solid(add, subtract):
    """Exact CSG for orthogonal boxes; no rasterization or boolean dependency."""
    all_boxes = np.concatenate((add, subtract)) if len(subtract) else np.asarray(add)
    axes = [np.unique(all_boxes[:, :, i]) for i in range(3)]
    centers = np.stack(np.meshgrid(*[(a[1:]+a[:-1])/2 for a in axes], indexing="ij"), axis=-1)
    solid = occupied(centers, add)
    if len(subtract):
        solid &= ~occupied(centers, subtract)
    cells, vertices, faces = [], [], []
    # Every exposed grid face uses the same global coordinate subdivision,
    # so coplanar neighbours also weld without T-junctions.
    for index in np.argwhere(solid):
        low = np.array([axes[k][index[k]] for k in range(3)])
        high = np.array([axes[k][index[k]+1] for k in range(3)])
        cells.append([low, high])
        for axis in range(3):
            u, v = (axis+1) % 3, (axis+2) % 3
            for sign in (-1, 1):
                neighbour = index.copy()
                neighbour[axis] += sign
                if 0 <= neighbour[axis] < solid.shape[axis] and solid[tuple(neighbour)]:
                    continue
                corners = np.tile(low, (4, 1))
                corners[:, axis] = low[axis] if sign < 0 else high[axis]
                corners[[1, 2], u] = high[u]
                corners[[2, 3], v] = high[v]
                if sign < 0:
                    corners = corners[::-1]
                n = len(vertices)
                vertices.extend(corners)
                faces.extend(((n, n+1, n+2), (n, n+2, n+3)))
    if not cells:
        raise ValueError("Empty coil solid")
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    return mesh, merge_cells(np.asarray(cells))


def merge_cells(cells):
    """Merge only full shared faces, preserving the exact disjoint union."""
    cells = list(cells)
    changed = True
    while changed:
        changed = False
        for axis in range(3):
            groups = {}
            other = [i for i in range(3) if i != axis]
            for cell in cells:
                groups.setdefault(tuple(cell[:, other].ravel()), []).append(cell.copy())
            cells = []
            for group in groups.values():
                group.sort(key=lambda c: c[0, axis])
                current = group[0]
                for following in group[1:]:
                    if current[1, axis] == following[0, axis]:
                        current[1, axis] = following[1, axis]
                        changed = True
                    else:
                        cells.append(current)
                        current = following
                cells.append(current)
    return np.asarray(cells)


@dataclass
class CoilBody:
    name: str
    visual: trimesh.Trimesh
    boxes: np.ndarray
    color: tuple


class CoilAssembly:
    def __init__(self, template=None, scale=3.0):
        self.template = t = load_template() if template is None else template
        self.scale = float(scale)
        keys = ("outer_width", "band_width", "layer_thickness", "layer_clearance",
                "bridge_height", "bridge_center_clearance", "relief_width", "relief_depth", "density_kg_m3")
        dims = [self.scale, *(t[k] for k in keys)]
        if not np.isfinite(dims).all() or min(dims) <= 0 or t["units"] != "mm":
            raise ValueError("Scale, dimensions and density must be finite and positive; units must be mm")
        h, w, d, gap = t["outer_width"]/2, t["band_width"], t["layer_thickness"], t["layer_clearance"]
        inner = h-w
        tip, bridge = t["bridge_center_clearance"]/2, t["bridge_height"]
        rw, rd = t["relief_width"], t["relief_depth"]
        if inner <= 0 or tip+bridge >= inner or rw >= 2*inner or rd >= w:
            raise ValueError("Coil dimensions close the bore, remove a rail, or obstruct the bridge window")
        self.unit = self.scale/1000
        bore = t.get("central_bore_half_width_mm", inner)
        if not np.isfinite(bore) or not 0 < bore < h:
            raise ValueError("The tested bore half-width must be finite, positive and inside the outer boundary")
        ys = (np.arange(4)-1.5)*(d+gap)
        self.layer_centers_m = ys*self.unit
        if "authored_boxes_mm" in t:
            self.bodies = []
            for name in ("coil_gold", "coil_silver"):
                blocks = np.asarray(t["authored_boxes_mm"][name], dtype=float) * self.unit
                if blocks.ndim != 3 or blocks.shape[1:] != (2, 3) or not np.isfinite(blocks).all() or np.any(blocks[:,1] <= blocks[:,0]):
                    raise ValueError("Invalid inverse-designed compound")
                mesh, cells = partition_solid(blocks, [])
                color = tuple(t["colors"][name])
                mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
                    baseColorFactor=color, metallicFactor=.82, roughnessFactor=.34))
                self.bodies.append(CoilBody(name, mesh, cells, color))
            return
        add, cuts = [], []
        for y in ys[[0, 2]]:
            layer = (y-d/2, y+d/2)
            add.extend((box((-h, h), layer, (inner, h)),
                        box((-h, h), layer, (-h, -inner)),
                        box((-h, -inner), layer, (-inner, inner)),
                        box((inner, h), layer, (tip, inner))))
            cuts.append(box((-rw/2, rw/2), layer, (-inner-rd, -inner)))
        add.append(box((inner, h), (ys[0]-d/2, ys[2]+d/2), (tip, tip+bridge)))
        self.bodies = []
        for name in ("coil_gold", "coil_silver"):
            blocks, reliefs = np.asarray(add).copy(), np.asarray(cuts).copy()
            if name == "coil_silver":
                # Half-turn about x: y/z reverse, preserving chirality.
                blocks *= [1, -1, -1]
                reliefs *= [1, -1, -1]
                blocks, reliefs = np.sort(blocks, axis=1), np.sort(reliefs, axis=1)
                # A distinct provisional inner relief: the real silver piece
                # has a different turning window, whose radius is unmeasured.
                extra = box((-inner-rd, -inner), (ys[1]-d/2, ys[1]+d/2), (-rw/2, rw/2))
                reliefs = np.concatenate((reliefs, extra[None]))
            mesh, cells = partition_solid(blocks*self.unit, reliefs*self.unit)
            color = tuple(t["colors"][name])
            mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)), material=PBRMaterial(
                baseColorFactor=color, metallicFactor=.82, roughnessFactor=.34))
            self.bodies.append(CoilBody(name, mesh, cells, color))


def clearance(a, b):
    """Exact signed minimum separation of two axis-aligned box compounds."""
    delta = np.maximum(a[:, None, 0]-b[None, :, 1], b[None, :, 0]-a[:, None, 1])
    distance = np.linalg.norm(np.maximum(delta, 0), axis=-1)
    overlap = np.all(delta < 0, axis=-1)
    if overlap.any():
        return float(np.max(delta, axis=-1)[overlap].min())
    return float(distance.min())


def geometry_report(assembly):
    a, b = assembly.bodies
    gap = clearance(a.boxes, b.boxes)
    bounds = np.array([np.minimum(a.visual.bounds[0], b.visual.bounds[0]),
                       np.maximum(a.visual.bounds[1], b.visual.bounds[1])])
    parts = []
    for body in assembly.bodies:
        mesh = body.visual
        parts.append(dict(name=body.name, watertight=bool(mesh.is_watertight),
            winding_consistent=bool(mesh.is_winding_consistent), components=len(mesh.split()),
            euler_number=int(mesh.euler_number), volume_m3=float(mesh.volume),
            collision_boxes=len(body.boxes)))
    # Probe the actual bore (not just the visual) across the entire depth.
    h = assembly.template.get("central_bore_half_width_mm",
        assembly.template["outer_width"]/2-assembly.template["band_width"])*assembly.unit
    points = np.array([[x, y, z] for x in (-.8*h, 0, .8*h)
                       for z in (-.8*h, 0, .8*h) for y in np.linspace(bounds[0, 1], bounds[1, 1], 31)])
    open_bore = not any(occupied(points, body.boxes).any() for body in assembly.bodies)
    return dict(template_id=assembly.template["template_id"], geometry_status=assembly.template["geometry_status"],
        scale=assembly.scale, body_count=2, bounds_m=bounds.tolist(), extent_m=np.diff(bounds, axis=0)[0].tolist(),
        layer_order=["gold", "silver", "gold", "silver"],
        layer_centers_m=assembly.layer_centers_m.tolist(), minimum_initial_clearance_m=gap,
        no_initial_collision=gap > 0, central_bore_open=open_bore,
        tested_bore_half_width_m=float(h), pieces=parts,
        passed=gap > 0 and open_bore and all(p["watertight"] and p["winding_consistent"] and
            p["components"] == 1 and p["euler_number"] == 2 and p["volume_m3"] > 0 for p in parts),
        measured_replica=False, extraction_route_verified=False, turning_windows_verified=False,
        qualification="initial authored solid only; exact commercial shape and disassembly remain unverified")


def write_body(folder, body, density):
    folder.mkdir(parents=True, exist_ok=True)
    mesh = body.visual.copy()
    mesh.density = density
    props = mesh.mass_properties
    origin = props.center_mass
    mesh.apply_translation(-origin)
    # Flat faces must not interpolate normals across the right-angle edges.
    mesh.unmerge_vertices()
    mesh.export(folder/f"{body.name}.glb", include_normals=True)
    root = ET.Element("robot", name=body.name)
    link = ET.SubElement(root, "link", name=body.name)
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz="0 0 0", rpy="0 0 0")
    ET.SubElement(inertial, "mass", value=str(props.mass))
    ET.SubElement(inertial, "inertia", **{f"i{a}{b}": str(props.inertia[i, j]) for a, b, i, j in
        (("x", "x", 0, 0), ("y", "y", 1, 1), ("z", "z", 2, 2),
         ("x", "y", 0, 1), ("x", "z", 0, 2), ("y", "z", 1, 2))})
    for i, (low, high) in enumerate(body.boxes):
        node = ET.SubElement(link, "collision", name=f"solid_{i:03d}")
        ET.SubElement(node, "origin", xyz=vector_text((low+high)/2-origin), rpy="0 0 0")
        ET.SubElement(ET.SubElement(node, "geometry"), "box", size=vector_text(high-low))
    node = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=f"{body.name}.glb")
    ET.SubElement(ET.SubElement(node, "material", name=body.name), "color", rgba=vector_text(body.color))
    ET.indent(root)
    ET.ElementTree(root).write(folder/f"{body.name}.urdf", encoding="unicode", xml_declaration=True)
    return dict(name=body.name, origin_m=origin.tolist(), mass_kg=float(props.mass),
        inertia_kg_m2=props.inertia.tolist(), collision_boxes=len(body.boxes), physical_links=1,
        fixed=False, mass_model="exact orthogonal solid at uniform declared prototype density")


def generate_assets(output, *, template=None, scale=3.0):
    output = Path(output)
    assembly = CoilAssembly(template, scale)
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError(f"Invalid initial coil assembly: {report}")
    output.mkdir(parents=True, exist_ok=True)
    report["bodies"] = [write_body(output/b.name, b, assembly.template["density_kg_m3"]) for b in assembly.bodies]
    scene = trimesh.Scene()
    separate = trimesh.Scene()
    for sign, body in zip((-1, 1), assembly.bodies):
        mesh = body.visual.copy()
        mesh.unmerge_vertices()
        scene.add_geometry(mesh, node_name=body.name, geom_name=body.name)
        mesh = mesh.copy().apply_translation([sign*assembly.template["outer_width"]*assembly.unit*.75, 0, 0])
        separate.add_geometry(mesh, node_name=body.name, geom_name=body.name)
    scene.export(output/"assembly.glb")
    separate.export(output/"separated_inspection.glb")
    (output/"template.json").write_text(json.dumps(assembly.template, indent=2)+"\n")
    (output/"geometry_report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return assembly, report


def synthesize(kind, output, *, pitch=0.0015, growth=0.006, parameters=None):
    import json
    from pathlib import Path
    from scipy.ndimage import label, binary_opening
    from topogym.planning.motions.cast_coil import variant_route, sample_route, prototype_route
    from topogym.assets.geometry.cast_coil_variants import family_parameter, FAMILY_PARAMETERS
    from topogym.utils.geometry.rigid_motion import RigidMotionSegment
    from topogym.evaluation.motion_certificate import certify_motion
    from topogym.solvers.collision.box_compounds import BoxCompoundCollision, box_corners

    amount = family_parameter(kind, parameters)
    output = Path(output)
    if (output / "template.json").exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    original = CoilAssembly()
    gold, silver = [b.boxes for b in original.bodies]
    # Existing material planes are retained exactly; only the added carving grid
    # is approximate. Cell-wise intersection is conservative, not point occupancy.
    all_boxes = np.concatenate((gold, silver))
    axes = [
        np.unique(
            np.round(
                np.r_[
                    np.arange(
                        all_boxes[:, 0, k].min(), all_boxes[:, 1, k].max(), pitch
                    ),
                    all_boxes[:, :, k].ravel(),
                ],
                10,
            )
        )
        for k in range(3)
    ]
    cx, cy, cz = [(a[:-1] + a[1:]) / 2 for a in axes]
    hx, hy, hz = [np.diff(a) / 2 for a in axes]
    xx, zz = np.meshgrid(cx, cz, indexing="ij")
    hhx, hhz = np.meshgrid(hx, hz, indexing="ij")
    xz = np.c_[xx.ravel(), zz.ravel()]
    half = np.c_[hhx.ravel(), hhz.ravel()]
    points = np.empty((len(cy), len(xz), 3))
    points[:, :, 0] = xz[:, 0]
    points[:, :, 2] = xz[:, 1]
    points[:, :, 1] = cy[:, None]
    base = occupied(points, gold)
    enlarged = gold.copy()
    enlarged[:, 0, [0, 2]] -= growth
    enlarged[:, 1, [0, 2]] += growth
    if kind == "axial_screw_turn":
        # Material here can obstruct a turn without axial advance. Its actual
        # surviving shape is determined by the requested screw trajectory.
        enlarged[:, 1, 1] += amount
    keep = occupied(points, enlarged)
    # Preserve the central through-bore and original external bounding box.
    keep &= ~((np.abs(points[:, :, 0]) < 0.018) & (np.abs(points[:, :, 2]) < 0.018))
    # The original opposing grasp faces must remain unchanged.
    protected = (
        (np.abs(points[:, :, 0] + 0.022) < 0.011)
        & (points[:, :, 1] < -0.024)
        & (points[:, :, 2] > 0.022)
    )
    keep[protected] = base[protected]
    samples = sample_route(variant_route(kind, parameters), silver)
    padding_xz = 0.0012
    padding_y = 0.00060
    for sample_index, (r, t, _) in enumerate(samples):
        rot = r[np.ix_([0, 2], [0, 2])]
        projected_axes = np.concatenate((np.eye(2), rot.T))
        a_radius = half @ np.abs(projected_axes.T)
        for low, high in silver:
            center = (low + high) / 2
            h = (high - low) / 2
            moved = r @ center + t
            yhit = np.abs(cy - moved[1]) <= hy + h[1] + padding_y
            if not yhit.any():
                continue
            gaps = (
                np.abs((xz - moved[[0, 2]]) @ projected_axes.T)
                - a_radius
                - h[[0, 2]] @ np.abs(rot.T @ projected_axes.T)
            )
            hit = np.all(gaps <= padding_xz, axis=1)
            if hit.any():
                keep[np.ix_(yhit, hit)] = False
        if sample_index % 500 == 0:
            print(kind, "sweep", sample_index, "/", len(samples), flush=True)
    lost_grasp = int(np.count_nonzero(base & protected & ~keep))
    if lost_grasp:
        raise RuntimeError(f"Candidate removes {lost_grasp} protected grasp cells")
    solid = keep.reshape(len(cy), len(cx), len(cz)).transpose(1, 0, 2)
    if kind == "axial_screw_turn":
        # Remove grid-scale ridges and diagonal edge contacts; this is a subset
        # operation, so it cannot invalidate the previously carved clearance.
        solid = binary_opening(solid, structure=np.ones((3, 3, 3), dtype=bool))
    labels, _ = label(solid)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    biggest = int(np.argmax(sizes))
    removed_islands = int(sizes.sum() - sizes[biggest])
    solid = labels == biggest
    retained = solid.transpose(1, 0, 2).reshape(keep.shape)
    lost_grasp = int(np.count_nonzero(base & protected & ~retained))
    if lost_grasp:
        raise RuntimeError(f"Mesh cleanup removes {lost_grasp} protected grasp cells")
    indices = np.argwhere(solid)
    cells = np.stack(
        [
            np.stack([axes[k][indices[:, k]] for k in range(3)], axis=1),
            np.stack([axes[k][indices[:, k] + 1] for k in range(3)], axis=1),
        ],
        axis=1,
    )
    boxes = merge_cells(cells)
    mesh, boxes = partition_solid(boxes, [])
    collision = BoxCompoundCollision(boxes, silver)
    certs = [
        certify_motion(collision, m, margin_m=0.00006)
        for m in variant_route(kind, parameters)
    ]
    baseline = [
        certify_motion(collision, m, margin_m=0.00006)
        for m in prototype_route(original)
    ]
    negative = []
    for k in range(3):
        for sign in (-1, 1):
            m = RigidMotionSegment(
                f"straight_{k}_{sign}",
                1.0,
                np.eye(3),
                np.zeros(3),
                np.eye(3)[k] * sign * 0.24,
            )
            negative.append(certify_motion(collision, m, margin_m=0.00006))
    operation_controls = {}
    if kind == "axial_screw_turn":
        slide = variant_route(kind, parameters)[0].end_translation
        advance_first = RigidMotionSegment(
            "advance_before_turn", 1.0, np.eye(3), slide, slide + [0, amount, 0]
        )
        operation_controls["advance_before_turn"] = certify_motion(
            collision, advance_first, margin_m=0.00006
        )
    template = dict(original.template)
    template["central_bore_half_width_mm"] = 6.0
    template.update(
        template_id=f"cast_coil_inverse_{kind}_v1",
        geometry_status="motion_first_inverse_designed_prototype",
        authored_boxes_mm={
            original.bodies[0].name: (boxes / original.unit).tolist(),
            original.bodies[1].name: (silver / original.unit).tolist(),
        },
        inverse_design=dict(
            kind=kind,
            seed="2026-09-17_aloha_full/executed_plan.json",
            pitch_m=pitch,
            growth_m=growth,
            sample_displacement_bound_m=0.00015,
            sweep_padding_xz_m=padding_xz,
            sweep_padding_y_m=padding_y,
        ),
    )
    if parameters is not None:
        key = FAMILY_PARAMETERS[kind][0]
        template["inverse_design"]["parameters"] = {key: amount * 1000}
        template["template_id"] = f"cast_coil_inverse_{kind}_{key}_{amount * 1000:g}mm_v1"
    report = dict(
        kind=kind,
        sweep_samples=len(samples),
        boxes=len(boxes),
        volume_m3=float(mesh.volume),
        volume_ratio_to_seed=float(mesh.volume / original.bodies[0].visual.volume),
        watertight=bool(mesh.is_watertight),
        components=len(mesh.split()),
        euler_number=int(mesh.euler_number),
        removed_disconnected_cells=removed_islands,
        protected_grasp_cells_removed=lost_grasp,
        route=certs,
        route_certified=all(c["passed"] for c in certs),
        seed_route_still_passes=all(c["passed"] for c in baseline),
        seed_route=baseline,
        straight_controls=negative,
        operation_controls=operation_controls,
        all_straight_controls_blocked=not any(c["passed"] for c in negative),
        continuous_robot_path_verified=False,
        physical_execution_verified=False,
    )
    (output / "template.json").write_text(json.dumps(template, indent=2) + "\n")
    (output / "synthesis_report.json").write_text(json.dumps(report, indent=2) + "\n")
    mesh.export(output / "gold_inspection.ply")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("route", "seed_route", "straight_controls")
            }
        ),
        flush=True,
    )
    return template, report
