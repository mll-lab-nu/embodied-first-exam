"""Design a push-turn-return Keyhole from the previously solved robot IK."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
from shapely.geometry import Point, Polygon, box

from .collision import CompoundCollision
from .geometry import ASSET_ROOT, load_template, outlines
from .inverse_variants import (
    UNIT, certify_variant, check_robot, geometry_from_record, overview, pack,
    polygon_record, save, sha, sweep_polygons,
)
from .long_stroke import SEED, plan, relative
from .robot_motion import ROOT
from .route_probe import PoseSegment

OUTPUT = ROOT / "runs/environment-solvability/cast_keyhole/turnback_v1"


def propose(folder, angle_deg=25., forward_y_mm=-18., return_y_mm=-9.5):
    seed = json.loads(SEED.read_text())
    if not seed["report"]["passed"]:
        raise ValueError("The source robot IK must be solved")
    poses = [relative(seed["frames"][0])]
    stages = []
    for i in range(max(f["motion"] for f in seed["frames"]) + 1):
        frames = [f for f in seed["frames"] if f["motion"] == i]
        poses.append(relative(frames[-1]))
        stages.append(frames[-1]["stage"])
    index = stages.index("pass_right_tooth")
    original_exit = poses[-1]
    poses, stages = poses[:index + 1], stages[:index]
    r0, start = poses[-1]
    turned = Rotation.from_euler("z", angle_deg, degrees=True).as_matrix() @ r0
    x, _, z = start / UNIT
    additions = [
        (r0, [x, forward_y_mm, z], "advance_to_turn_chamber"),
        (turned, [x, forward_y_mm, z], "turn_in_chamber"),
        (turned, [x, return_y_mm, z], "return_to_offset_gate"),
        (turned, [15.8, return_y_mm, z], "shift_through_gate"),
        (r0, [15.8, return_y_mm, z], "restore_after_gate"),
        (original_exit[0], original_exit[1] / UNIT, "withdraw"),
    ]
    for r, xyz, stage in additions:
        poses.append((r, np.array(xyz) * UNIT))
        stages.append(stage)
    motions = [dict(type="pose_segment", name=f"{s}_{i:02d}", stage=s,
                    start=pack(*a), end=pack(*b))
               for i, (a, b, s) in enumerate(zip(poses, poses[1:], stages))]
    data = dict(id="turnback", title_zh="前送—转向—回退型", units="mm", scale=3.,
                moving_piece="silver", fixed_piece="gold", motions=motions,
                source_ik_sha256=sha(SEED), seed_ik_path=str(SEED.relative_to(ROOT)),
                source_template_sha256=sha(ASSET_ROOT / "template.json"),
                turn_angle_deg=angle_deg, forward_y_template_mm=forward_y_mm,
                return_y_template_mm=return_y_mm,
                return_distance_scene_mm=3 * (return_y_mm - forward_y_mm),
                design_order="solved robot FK -> push-turn-return relative motion -> coupled IK -> inverse swept-volume geometry",
                description_zh="先前送到下方转向空间，转动后回退至错位出口，再横移、恢复姿态并分离；由新 IK 的实际 FK 扫掠体反推转向空间和挡肩。")
    save(folder / "proposal.json", data)
    return data, seed


def infer(data, trace, folder):
    template = load_template()
    gold = Polygon(outlines(template, "gold")[0])
    rings = outlines(template, "silver")
    silver = Polygon(rings[0], rings[1:])
    # Keep the old left-side notch connected to the main opening. Extending
    # stock to x=-5.6 would seal that notch into an unwanted extra hole.
    domain = [-3., -25., 8.2, -2.]
    stock = gold.union(box(*domain))
    sweep, sampling = sweep_polygons(trace)
    carved = stock.difference(sweep).simplify(.025, preserve_topology=True)
    if carved.geom_type != "Polygon" or len(carved.interiors) or not carved.is_valid:
        save(folder / "rejected_geometry.json", dict(type=carved.geom_type,
             areas=[p.area for p in getattr(carved, "geoms", [carved])]))
        raise ValueError(f"Disconnected or invalid gold: {carved.geom_type}")
    if not carved.buffer(1e-8).covers(Point(-10.6, -31).buffer(1.0)):
        raise ValueError("Gold grasp anchor was cut away")
    if carved.area < .7 * gold.area:
        raise ValueError("Too much material removed")
    record = dict(id=data["id"], title_zh=data["title_zh"], units="mm", scale=3.,
                  thickness_mm=3., density_kg_m3=6600.,
                  rings_mm=dict(gold=polygon_record(carved), silver=polygon_record(silver)),
                  design_method="Chamber stock minus conservative silver sweep recovered from the varied solved robot IK",
                  input_trace_sha256=sha(folder / "ik_proposal.json"),
                  source_proposal_sha256=sha(folder / "proposal.json"),
                  source_template_sha256=sha(ASSET_ROOT / "template.json"),
                  stock_domain_template_mm=domain, sweep_sampling=sampling,
                  geometry_modified=True, silver_geometry_preserved=True,
                  grasp_anchors_preserved=True, gold_area_before_mm2=gold.area,
                  gold_area_after_mm2=carved.area,
                  removed_area_mm2=gold.difference(carved).area,
                  added_area_mm2=carved.difference(gold).area)
    save(folder / "geometry.json", record)
    meshes, cells = geometry_from_record(record)
    audits = []
    for name, mesh, parts, euler in zip(("gold", "silver"), meshes, cells, (2, 0)):
        item = dict(name=name, watertight=bool(mesh.is_watertight),
                    components=len(mesh.split()), euler=int(mesh.euler_number),
                    collision_prisms=len(parts),
                    volume_error_m3=float(abs(sum(p.volume for p in parts) - mesh.volume)))
        if not item["watertight"] or item["components"] != 1 or item["euler"] != euler or item["volume_error_m3"] > 1e-10:
            raise ValueError(item)
        audits.append(item)
    save(folder / "solid_audit.json", dict(passed=True, pieces=audits))
    return record, meshes, cells


def controls(trace, seed, cells):
    collision = CompoundCollision(*cells)
    groups = {s: [f for f in trace["frames"] if f["stage"] == s]
              for s in ("align_right_tooth", "advance_to_turn_chamber", "turn_in_chamber",
                        "return_to_offset_gate", "shift_through_gate")}
    poses = {s: relative(fs[-1]) for s, fs in groups.items()}
    negative = {}

    def sampled(name, values):
        i = int(np.argmin(values))
        negative[name] = dict(minimum_sample_gap_m=float(values[i]),
                              collision_found=bool(values[i] < 0), witness_sample=i,
                              samples=len(values))

    def shortcut(name, a, b):
        m = PoseSegment(name, a[0], b[0], a[1], b[1])
        sampled(name, [collision.gap(*m.pose(u)) for u in np.linspace(0, 1, 151)])

    sampled("unchanged_solved_robot_ik", [collision.gap(*relative(f)) for f in seed["frames"]])
    shortcut("omit_forward_excursion", poses["align_right_tooth"], poses["return_to_offset_gate"])
    shortcut("omit_return_diagonal_exit", poses["turn_in_chamber"], poses["shift_through_gate"])
    r0 = poses["align_right_tooth"][0]
    selected = groups["return_to_offset_gate"] + groups["shift_through_gate"]
    sampled("omit_chamber_turn", [collision.gap(r0, relative(f)[1]) for f in selected])
    return negative


def generate(folder, angle_deg=25., forward_y_mm=-18., return_y_mm=-9.5, reuse_ik=False, design_only=False):
    folder.mkdir(parents=True, exist_ok=True)
    data, seed = propose(folder, angle_deg, forward_y_mm, return_y_mm)
    trace = json.loads((folder / "ik_proposal.json").read_text()) if reuse_ik else plan(data, seed, folder)
    if trace["report"]["source_proposal_sha256"] != sha(folder / "proposal.json"):
        raise ValueError("Stale IK proposal")
    record, meshes, cells = infer(data, trace, folder)
    overview(data, record, folder)
    negative = controls(trace, seed, cells)
    save(folder / "maneuver_controls.json", negative)
    if not all(n["collision_found"] for n in negative.values()):
        raise ValueError(f"A maneuver shortcut still works: {negative}")
    if design_only:
        return
    proof = certify_variant(data, trace, record, meshes, cells, folder)
    proof["negative_controls"].update(negative)
    if not all(n["collision_found"] for n in proof["negative_controls"].values()):
        raise ValueError("A baseline shortcut still works")
    save(folder / "certificate.json", proof)
    check_robot(trace, record, cells, folder)
    save(folder / "design_result.json", dict(
        passed=True, variant=data["id"], source_ik_sha256=sha(SEED),
        new_ik_sha256=sha(folder / "robot_motion.json"),
        geometry_sha256=sha(folder / "geometry.json"),
        certificate_sha256=sha(folder / "certificate.json"),
        generator_sha256=sha(__file__), negative_controls=proof["negative_controls"],
        turn_angle_deg=angle_deg, return_distance_scene_mm=data["return_distance_scene_mm"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--angle-deg", type=float, default=25.)
    parser.add_argument("--forward-y-mm", type=float, default=-18.)
    parser.add_argument("--return-y-mm", type=float, default=-9.5)
    parser.add_argument("--reuse-ik", action="store_true")
    parser.add_argument("--design-only", action="store_true")
    args = parser.parse_args()
    if not 0 < args.angle_deg <= 45 or not args.forward_y_mm < args.return_y_mm < 0:
        parser.error("Require angle in (0, 45] and forward-y < return-y < 0")
    generate(args.output, args.angle_deg, args.forward_y_mm, args.return_y_mm, args.reuse_ik, args.design_only)


if __name__ == "__main__":
    main()
