"""Complementary cubic Coil pieces, authored in the final assembly frame.

This module builds geometry only. It does not register a Task, certify a robot
grasp, or provide an operational solution to the installed scene resources.
Orthogonal CSG and URDF export reuse the existing Cast Coil implementation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .cast_coil import CoilBody, box, clearance, occupied, partition_solid, write_body


LEVELS = ("very_easy", "easier")
REVISION = "cubic_frames_v1"
COMB_REVISION = "cubic_comb_v2"
BAFFLE_REVISION = "cubic_baffle_v2"


def geometry_record(level):
    """Return the current modeling candidate; all authored lengths are mm."""
    if level not in LEVELS:
        raise ValueError(f"Unknown simplified Coil level: {level}")
    record = dict(
        schema_version=1, id=f"cast_coil_{level}_{REVISION}", level=level,
        model_revision=REVISION, units="mm", density_kg_m3=6700.,
        parameters=dict(edge_mm=102., bore_mm=60., seam_mm=.6, clearance_mm=.6,
                        tongue_depth_mm=12., head_depth_mm=6.,
                        head_width_mm=12., head_height_mm=14.,
                        neck_width_mm=6., neck_height_mm=6.,
                        straight_tongue_height_mm=9.,
                        slide_mm=18. if level == "easier" else 0.,
                        joint_y_centers_mm=[0., 6.]),
        colors=dict(coil_gold=[.53, .39, .12, 1.], coil_silver=[.39, .43, .47, 1.]),
        coordinate_frame="final assembly center; X left/right, Y bore/depth, Z up",
        geometry_status="authored mesh candidate; robot and runtime not validated",
        source="topogym.assets.geometry.cast_coil_simplified.geometry_record",
    )
    if level == "very_easy":
        record.update(id=f"cast_coil_{level}_{COMB_REVISION}", model_revision=COMB_REVISION,
                      coordinate_frame="final assembly center; X insertion, Y depth, Z up")
        record["parameters"] = dict(edge_mm=102., seam_mm=.6, tooth_reach_mm=20.4,
                                    band_count=5, slide_mm=0.)
    else:
        record.update(id=f"cast_coil_{level}_{BAFFLE_REVISION}", model_revision=BAFFLE_REVISION,
                      coordinate_frame="final assembly center; X insertion, Y lateral (positive at entry), Z up")
        record["parameters"] = dict(edge_mm=102., wall_mm=18., seam_mm=.6,
                                    baffle_width_mm=15., baffle_depth_mm=15., slide_mm=18.)
    return record


def scaled_record(record, scale=1.):
    """Uniformly scale the reviewed CAD candidate for the robot embodiment."""
    if isinstance(scale, bool) or not np.isfinite(scale) or scale <= 0:
        raise ValueError("Geometry scale must be finite and positive")
    result = deepcopy(record)
    for key, value in result["parameters"].items():
        if key.endswith("_mm"):
            result["parameters"][key] = (np.asarray(value)*scale).tolist()
    if scale != 1.:
        result["authored_scale"] = float(scale)
    return result


def comb_solids(p):
    """Five alternating full-depth bands: three gold fingers and two silver.

    Continuous outer spines connect each set of fingers. Half the nominal
    clearance is removed from each mating face; outer cube faces stay flush.
    """
    if (not np.isfinite(list(p.values())).all() or p["band_count"] != 5 or
            p["slide_mm"] != 0):
        raise ValueError("Comb requires five bands, finite dimensions and no lateral slide")
    h, d, c = p["edge_mm"]/2, p["tooth_reach_mm"], p["seam_mm"]/2
    if not (0 < c < d < h-c and 2*c < 2*h/5):
        raise ValueError("Comb clearance must preserve both fingers and outer spines")
    gold = [box((-h, -d-c), (-h, h), (-h, h))]
    silver = [box((d+c, h), (-h, h), (-h, h))]
    bounds = np.linspace(-h, h, 6)
    for i, (z0, z1) in enumerate(zip(bounds, bounds[1:])):
        z = (z0+c if i else z0, z1-c if i < 4 else z1)
        if i % 2 == 0:
            gold.append(box((-h, d-c), (-h, h), z))
        else:
            silver.append(box((-d+c, h), (-h, h), z))
    return gold, silver


def comb_seams(p):
    """Intended voids: five vertical tip gaps plus four horizontal fit gaps."""
    h, d, c = p["edge_mm"]/2, p["tooth_reach_mm"], p["seam_mm"]/2
    bounds = np.linspace(-h, h, 6)
    seams = [box(((d if i % 2 == 0 else -d)-c,
                  (d if i % 2 == 0 else -d)+c), (-h, h), (z0, z1))
             for i, (z0, z1) in enumerate(zip(bounds, bounds[1:]))]
    seams.extend(box((-d-c, d+c), (-h, h), (z-c, z+c)) for z in bounds[1:-1])
    return np.asarray(seams)*.001


def baffle_solids(p):
    """Gold C with a front bar; silver T with an open root pocket.

    Both pieces span the full Y edge length. The bar bridges the gold top and
    bottom rails. The pocket opens at silver's front edge and stops before its
    back, leaving the central tongue connected to the outer wall.
    """
    if not np.isfinite(list(p.values())).all() or min(p.values()) <= 0:
        raise ValueError("Baffle dimensions must be finite and positive")
    h, a = p["edge_mm"]/2, p["edge_mm"]/2-p["wall_mm"]
    g, w, d, s = (p[k] for k in ("seam_mm", "baffle_width_mm", "baffle_depth_mm", "slide_mm"))
    c = g/2
    if not (g < p["wall_mm"] < h and g < w < 2*a-2*g and
            g < d and d+g < s < 2*h-d-g):
        raise ValueError("Baffle must retain rails, an entry offset and the silver rear bridge")
    gold = [box((-h, -a-c), (-h, h), (-h, h)),
            box((-h, a-c), (-h, h), (-h, -a-c)),
            box((-h, a-c), (-h, h), (a+c, h)),
            box((a-c-w, a-c), (-h, -h+d), (-h, h))]
    silver = [box((a+c, h), (-h, h), (-h, h)),
              box((-a+c, a+c), (-h, h), (-a+c, a-c))]
    pocket = box((a-c-w-g, a+c), (-h-1, -h+d+g), (-a-c, a+c))
    return gold, silver, [pocket]


def baffle_voids(p):
    """Independent cube-complement specification of mating gaps and pocket.

    The gold bar occupies part of the otherwise empty rail seams and pocket,
    so it is subtracted from this void union.
    """
    h, a = p["edge_mm"]/2, p["edge_mm"]/2-p["wall_mm"]
    g, w, d = (p[k] for k in ("seam_mm", "baffle_width_mm", "baffle_depth_mm"))
    c = g/2
    gaps = [box((-a-c, -a+c), (-h, h), (-a-c, a+c)),
            box((-a-c, a+c), (-h, h), (-a-c, -a+c)),
            box((-a-c, a+c), (-h, h), (a-c, a+c)),
            box((a-c, a+c), (-h, h), (-h, -a+c)),
            box((a-c, a+c), (-h, h), (a-c, h)),
            box((a-c-w-g, a+c), (-h, -h+d+g), (-a-c, a+c))]
    bar = box((a-c-w, a-c), (-h, -h+d), (-h, h))
    return np.asarray(gaps)*.001, np.asarray([bar])*.001


class SimplifiedCoilAssembly:
    def __init__(self, level="very_easy", *, record=None):
        self.record = deepcopy(geometry_record(level) if record is None else record)
        t = self.record
        if t["level"] not in LEVELS or t["units"] != "mm" or t["schema_version"] != 1:
            raise ValueError("Invalid simplified Coil resource identity or units")
        self.level = t["level"]
        p = t["parameters"]
        if not np.isfinite(t["density_kg_m3"]) or t["density_kg_m3"] <= 0:
            raise ValueError("Density must be finite and positive")
        if t["model_revision"] == BAFFLE_REVISION:
            if self.level != "easier":
                raise ValueError("Baffle revision is only authored for easier")
            gold_add, silver_add, silver_cuts = baffle_solids(p)
            self.joint_centers_mm = []
            self._build_bodies(gold_add, [], silver_add, silver_cuts)
            return
        if t["model_revision"] == COMB_REVISION:
            if self.level != "very_easy":
                raise ValueError("Comb revision is only authored for very_easy")
            gold_add, silver_add = comb_solids(p)
            self.joint_centers_mm = []
            self._build_bodies(gold_add, [], silver_add, [])
            return
        if t["model_revision"] != REVISION:
            raise ValueError("Unknown simplified Coil geometry revision")
        numeric = [v for k, v in p.items() if k != "joint_y_centers_mm"]
        if not np.isfinite(numeric).all() or any(v <= 0 for k, v in p.items()
                if k not in ("slide_mm", "joint_y_centers_mm")):
            raise ValueError("Geometry dimensions must be finite and positive")
        ys = np.asarray(p["joint_y_centers_mm"], dtype=float)
        if ys.shape != (2,) or not np.isfinite(ys).all():
            raise ValueError("Expected two finite joint Y coordinates")
        half, hole = p["edge_mm"]/2, p["bore_mm"]/2
        seam, c, s = p["seam_mm"]/2, p["clearance_mm"], p["slide_mm"]
        depth, head_d = p["tongue_depth_mm"], p["head_depth_mm"]
        hw, hh = p["head_width_mm"]/2, p["head_height_mm"]/2
        nw, nh = p["neck_width_mm"]/2, p["neck_height_mm"]/2
        zc = (half+hole)/2
        if not (0 < seam < hole < half and depth+c < hole and
                c < head_d < depth-c and hh+c < (half-hole)/2 and
                0 < nw < hw and 0 < nh < hh and depth-head_d > seam+c):
            raise ValueError("Joints must fit inside solid rails and retain their shoulder")
        if p["straight_tongue_height_mm"]/2+c >= (half-hole)/2:
            raise ValueError("Straight tongue breaks through the rail")
        if ((self.level == "very_easy" and s != 0) or
                (self.level == "easier" and s <= 2*hw+c) or
                np.any(ys-s-hw-c <= -half) or np.any(ys+hw+c >= half)):
            raise ValueError("Sliding gate or joint endpoints do not fit the frame")

        bore = box((-hole, hole), (-half-1, half+1), (-hole, hole))
        gold_add = [box((-half, -seam), (-half, half), (-half, half))]
        silver_add = [box((seam, half), (-half, half), (-half, half))]
        gold_cuts, silver_cuts = [bore], [bore]
        self.joint_centers_mm = []
        for y, z in zip(ys, (zc, -zc)):
            self.joint_centers_mm.append([0., float(y), float(z)])
            if self.level == "very_easy":
                height = p["straight_tongue_height_mm"]/2
                silver_add.append(box((-depth, seam+1), (y-hw, y+hw), (z-height, z+height)))
                gold_cuts.append(box((-depth-c, seam+1), (y-hw-c, y+hw+c),
                                     (z-height-c, z+height+c)))
            else:
                # Wider head is behind the front lip; neck alone traverses it.
                head_end = -depth+head_d
                silver_add.extend((
                    box((-depth, head_end), (y-hw, y+hw), (z-hh, z+hh)),
                    box((head_end, seam+1), (y-nw, y+nw), (z-nh, z+nh))))
                gold_cuts.extend((
                    # Internal chamber contains the full head translation.
                    box((-depth-c, head_end+c), (y-s-hw-c, y+hw+c), (z-hh-c, z+hh+c)),
                    # Large gate at the Y-offset insertion position only.
                    box((-depth-c, seam+1), (y-s-hw-c, y-s+hw+c), (z-hh-c, z+hh+c)),
                    # Narrow neck opening retains material above/below it.
                    box((head_end-c, seam+1), (y-s-nw-c, y+nw+c), (z-nh-c, z+nh+c))))

        self._build_bodies(gold_add, gold_cuts, silver_add, silver_cuts)

    def _build_bodies(self, gold_add, gold_cuts, silver_add, silver_cuts):
        self.bodies = []
        for name, additions, cuts in (("coil_gold", gold_add, gold_cuts),
                                      ("coil_silver", silver_add, silver_cuts)):
            mesh, cells = partition_solid(np.asarray(additions)*.001, np.asarray(cuts)*.001)
            color = tuple(self.record["colors"][name])
            if len(color) != 4 or not np.isfinite(color).all():
                raise ValueError("Expected finite RGBA colors")
            mesh.visual = TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)),
                material=PBRMaterial(baseColorFactor=color, metallicFactor=.82, roughnessFactor=.34))
            self.bodies.append(CoilBody(name, mesh, cells, color))


def geometry_report(assembly):
    """Check actual solids, including every exterior rectangle partition cell."""
    p = assembly.record["parameters"]
    edge, hole, seam = (p.get(k, 0.)*.001 for k in ("edge_mm", "bore_mm", "seam_mm"))
    is_comb = assembly.record["model_revision"] == COMB_REVISION
    is_baffle = assembly.record["model_revision"] == BAFFLE_REVISION
    seams = comb_seams(p) if is_comb else None
    void_add, void_cut = baffle_voids(p) if is_baffle else (None, None)
    all_boxes = np.concatenate([b.boxes for b in assembly.bodies])
    low, high = all_boxes[:, 0].min(0), all_boxes[:, 1].max(0)
    extent = high-low
    cube_error = float(np.max(np.abs(np.r_[low+edge/2, high-edge/2])))
    face_checks = {}
    # Material boundaries are rectilinear. Midpoints of the full partition
    # check whole open rectangles, not an arbitrary low-resolution point grid.
    boundaries = np.concatenate((all_boxes, seams)) if is_comb else all_boxes
    if is_baffle:
        boundaries = np.concatenate((all_boxes, void_add, void_cut))
    axes = [np.unique(np.r_[boundaries[:, :, i].ravel(), -hole/2, hole/2,
                           -seam/2, seam/2, -edge/2, edge/2]) for i in range(3)]
    for axis in range(3):
        other = [i for i in range(3) if i != axis]
        mids = [(axes[i][1:]+axes[i][:-1])/2 for i in other]
        uv = np.stack(np.meshgrid(*mids, indexing="ij"), -1).reshape(-1, 2)
        for side in (-1, 1):
            points = np.zeros((len(uv), 3))
            points[:, other] = uv
            points[:, axis] = side*(edge/2-1e-10)
            expected = (~occupied(points, seams) if is_comb else
                        ((np.abs(points[:, 0]) >= hole/2) |
                         (np.abs(points[:, 2]) >= hole/2)) & (np.abs(points[:, 0]) >= seam/2))
            if is_baffle:
                expected = ~(occupied(points, void_add) & ~occupied(points, void_cut))
            actual = occupied(points, all_boxes)
            face_checks[f"{'xyz'[axis]}{'+' if side > 0 else '-'}"] = dict(
                rectangles=len(points), mismatches=int(np.count_nonzero(actual != expected)))
    bore = box((-hole/2, hole/2), (-edge/2, edge/2), (-hole/2, hole/2))
    bore_overlap = np.minimum(all_boxes[:, 1], bore[1])-np.maximum(all_boxes[:, 0], bore[0])
    bore_open = hole > 0 and not bool(np.any(np.all(bore_overlap > 1e-12, axis=1)))
    # Extruded comb fills the cube except the specified seam network. Compare
    # every 3-D partition cell as well as its analytic total material volume.
    interior_check = None
    if is_comb:
        centers = np.stack(np.meshgrid(*[(a[1:]+a[:-1])/2 for a in axes], indexing="ij"), -1)
        expected_volume = edge**3 - seam*edge*(edge+8*p["tooth_reach_mm"]*.001)
        volume = float(np.prod(all_boxes[:, 1]-all_boxes[:, 0], axis=1).sum())
        interior_check = dict(cells=int(np.prod(centers.shape[:-1])),
            mismatches=int(np.count_nonzero(occupied(centers, all_boxes) != ~occupied(centers, seams))),
            expected_volume_m3=expected_volume, actual_volume_m3=volume,
            volume_match=bool(np.isclose(volume, expected_volume, rtol=1e-9, atol=1e-14)))
    elif is_baffle:
        centers = np.stack(np.meshgrid(*[(a[1:]+a[:-1])/2 for a in axes], indexing="ij"), -1)
        _, void_cells = partition_solid(void_add, void_cut)
        expected_volume = edge**3-float(np.prod(void_cells[:, 1]-void_cells[:, 0], axis=1).sum())
        volume = float(np.prod(all_boxes[:, 1]-all_boxes[:, 0], axis=1).sum())
        interior_check = dict(cells=int(np.prod(centers.shape[:-1])),
            mismatches=int(np.count_nonzero(occupied(centers, all_boxes) !=
                ~(occupied(centers, void_add) & ~occupied(centers, void_cut)))),
            expected_volume_m3=expected_volume, actual_volume_m3=volume,
            volume_match=bool(np.isclose(volume, expected_volume, rtol=1e-9, atol=1e-14)))
    parts = []
    for body in assembly.bodies:
        mesh = body.visual
        box_volume = float(np.prod(body.boxes[:, 1]-body.boxes[:, 0], axis=1).sum())
        parts.append(dict(name=body.name, watertight=bool(mesh.is_watertight),
            winding_consistent=bool(mesh.is_winding_consistent), components=len(mesh.split()),
            volume_m3=float(mesh.volume), collision_volume_m3=box_volume,
            volume_match=bool(np.isclose(mesh.volume, box_volume, rtol=1e-9, atol=1e-14)),
            collision_boxes=len(body.boxes), triangles=len(mesh.faces)))
    gap = clearance(*(b.boxes for b in assembly.bodies))
    fill_valid = (interior_check["mismatches"] == 0 and interior_check["volume_match"]
                  if is_comb or is_baffle else bore_open)
    passed = (cube_error <= 1e-8 and fill_valid and gap > 0 and
              all(f["mismatches"] == 0 for f in face_checks.values()) and
              all(q["watertight"] and q["winding_consistent"] and q["components"] == 1
                  and q["volume_m3"] > 0 and q["volume_match"] for q in parts))
    report = dict(id=assembly.record["id"], model_revision=assembly.record["model_revision"],
        assembled_extent_m=extent.tolist(), cube_extent_error_m=cube_error,
        square_bore_width_m=hole, central_bore_open=bore_open,
        final_pair_clearance_m=gap, exterior_face_checks=face_checks,
        pieces=parts, passed=bool(passed),
        qualification="static authored solids only; no robot or physics qualification")
    if is_comb or is_baffle:
        report.update(fill_kind="solid cube except fitting seams", interior_check=interior_check)
    if is_baffle:
        report.update(mechanism="positive Y offset bypasses front bar; negative Y seats bar in open root pocket",
                      piece_depths_m=[float(b.visual.extents[1]) for b in assembly.bodies])
    return report


def generate_assets(output, *, level="very_easy", record=None, allow_existing_empty=False):
    """Export an inspectable candidate to a new directory, without Task changes."""
    assembly = SimplifiedCoilAssembly(level, record=record)
    report = geometry_report(assembly)
    if not report["passed"]:
        raise ValueError(f"Invalid simplified Coil solid: {report}")
    output = Path(output)
    if allow_existing_empty and output.is_dir() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing assets: {output}")
    output.mkdir(parents=True, exist_ok=allow_existing_empty)
    report["bodies"] = [write_body(output/b.name, b, assembly.record["density_kg_m3"])
                        for b in assembly.bodies]
    scene = trimesh.Scene()
    mesh_record = {}
    for body in assembly.bodies:
        scene.add_geometry(body.visual.copy(), node_name=body.name, geom_name=body.name)
        body.visual.export(output/f"{body.name}_assembly_frame.stl")
        mesh_record[body.name] = dict(vertices_m=body.visual.vertices.tolist(),
            faces=body.visual.faces.tolist(), boxes_m=body.boxes.tolist(), color=list(body.color))
    scene.export(output/"assembly.glb")
    for filename, data in (("geometry.json", assembly.record), ("geometry_report.json", report),
                           ("assembly_meshes.json", mesh_record)):
        (output/filename).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")
    return assembly, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=LEVELS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, report = generate_assets(args.output, level=args.level)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
