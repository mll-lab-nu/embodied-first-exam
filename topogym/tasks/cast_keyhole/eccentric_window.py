"""Infer an eccentric turning window from a variation of the solved robot IK."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon, box

from .collision import CompoundCollision
from .geometry import ASSET_ROOT, load_template, outlines
from .inverse_variants import (
    UNIT, certify_variant, check_robot, geometry_from_record, overview, pack,
    polygon_record, save, sha, sweep_polygons,
)
from .long_stroke import SEED, plan, relative
from .robot_motion import ROOT

OUTPUT = ROOT / "runs/environment-solvability/cast_keyhole/eccentric_window_v1"


def propose(folder, offset_mm):
    seed = json.loads(SEED.read_text())
    if not seed["report"]["passed"]:
        raise ValueError("Seed IK did not pass")
    poses = [relative(seed["frames"][0])]
    stages = []
    for i in range(max(f["motion"] for f in seed["frames"]) + 1):
        frames = [f for f in seed["frames"] if f["motion"] == i]
        poses.append(relative(frames[-1]))
        stages.append(frames[-1]["stage"])
    turning = [i for i, s in enumerate(stages) if s == "follow_cap_to_right"]
    first, last = turning[0], turning[-1] + 1
    for i in range(first + 1, last):
        weight = np.sin(np.pi * (i - first) / (last - first))
        r, t = poses[i]
        poses[i] = (r, t + UNIT * weight * np.array([offset_mm, offset_mm / 2, 0]))
    motions = [dict(type="pose_segment", name=f"{s}_{i:02d}", stage=s,
                    start=pack(*a), end=pack(*b))
               for i, (a, b, s) in enumerate(zip(poses, poses[1:], stages))]
    data = dict(id="eccentric_window", title_zh="偏心转向窗型", units="mm", scale=3.,
                moving_piece="silver", fixed_piece="gold", motions=motions,
                source_ik_sha256=sha(SEED), seed_ik_path=str(SEED.relative_to(ROOT)),
                source_template_sha256=sha(ASSET_ROOT / "template.json"),
                maximum_excursion_template_mm=[offset_mm, offset_mm / 2, 0],
                maximum_excursion_scene_mm=[3 * offset_mm, 1.5 * offset_mm, 0],
                design_order="solved robot FK -> lateral turning excursion -> seeded coupled IK -> inverse swept-volume window",
                description_zh="顶部绕行向右、向上偏心；保留绕行两端和原有穿齿行程，先求新的双臂 IK，再由实际 FK 扫掠体反推带内侧挡肩的转向窗口。")
    save(folder / "proposal.json", data)
    return data, seed


def infer(data, trace, folder):
    template = load_template()
    gold = Polygon(outlines(template, "gold")[0])
    rings = outlines(template, "silver")
    silver = Polygon(rings[0], rings[1:])
    # This is the allowed added-material domain, not a prescribed opening.
    # Filling the old upper chamber first lets the new FK sweep determine an
    # inner shoulder as well as the required outer relief. The earlier stock
    # domain on the outer rim alone left the unmodified solution usable.
    stock_bounds = [-6., 15., 8., 28.]
    stock = gold.union(box(*stock_bounds))
    sweep, sampling = sweep_polygons(trace)
    carved = stock.difference(sweep).simplify(.025, preserve_topology=True)
    # A larger, explicitly versioned excursion can machine off tiny chips.
    # They are discarded stock, not extra movable puzzle pieces. Keep only the
    # grasp-connected component, with a strict bound on discarded material.
    discarded = 0.
    if carved.geom_type == "MultiPolygon" and data.get("discard_small_sweep_offcuts", False):
        anchor = Point(-10.6, -31).buffer(1.0)
        connected = [p for p in carved.geoms if p.buffer(1e-8).covers(anchor)]
        if len(connected) != 1:
            raise ValueError("No unique grasp-connected solid")
        discarded = carved.area - connected[0].area
        if discarded > .01 * stock.area:
            raise ValueError("Sweep disconnected more than 1% of stock")
        carved = connected[0]
    if carved.geom_type != "Polygon" or len(carved.interiors) or not carved.is_valid:
        raise ValueError(f"Disconnected or invalid gold: {carved.geom_type}")
    if not carved.buffer(1e-8).covers(Point(-10.6, -31).buffer(1.0)):
        raise ValueError("Gold grasp anchor was cut away")
    if carved.area < .7 * gold.area:
        raise ValueError("Too much material removed")
    record = dict(id=data["id"], title_zh=data["title_zh"], units="mm", scale=3.,
                  thickness_mm=3., density_kg_m3=6600.,
                  rings_mm=dict(gold=polygon_record(carved), silver=polygon_record(silver)),
                  design_method="Upper-chamber stock minus conservative silver sweep recovered from the varied solved robot IK",
                  input_trace_sha256=sha(folder / "ik_proposal.json"),
                  source_proposal_sha256=sha(folder / "proposal.json"),
                  source_template_sha256=sha(ASSET_ROOT / "template.json"),
                  stock_domain_template_mm=stock_bounds, sweep_sampling=sampling,
                  geometry_modified=True, silver_geometry_preserved=True,
                  grasp_anchors_preserved=True, gold_area_before_mm2=gold.area,
                  gold_area_after_mm2=carved.area,
                  removed_area_mm2=gold.difference(carved).area,
                  added_area_mm2=carved.difference(gold).area)
    if data.get("discard_small_sweep_offcuts", False):
        record["discarded_sweep_offcuts_mm2"] = discarded
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


def generate(folder, offset_mm=2., reuse_ik=False):
    folder.mkdir(parents=True, exist_ok=True)
    data, seed = propose(folder, offset_mm)
    trace = json.loads((folder / "ik_proposal.json").read_text()) if reuse_ik else plan(data, seed, folder)
    if trace["report"]["source_proposal_sha256"] != sha(folder / "proposal.json"):
        raise ValueError("Stale IK proposal")
    record, meshes, cells = infer(data, trace, folder)
    proof = certify_variant(data, trace, record, meshes, cells, folder)
    collision = CompoundCollision(*cells)
    gaps = [collision.gap(*relative(f)) for f in seed["frames"]]
    i = int(np.argmin(gaps))
    proof["negative_controls"]["unchanged_solved_robot_ik"] = dict(
        minimum_sample_gap_m=float(gaps[i]), collision_found=gaps[i] < 0,
        witness=dict(frame=i, motion=seed["frames"][i]["motion"], stage=seed["frames"][i]["stage"]),
        source_ik_sha256=sha(SEED))
    if not all(n["collision_found"] for n in proof["negative_controls"].values()):
        raise ValueError("The original IK, baseline path or direct pull still works")
    save(folder / "certificate.json", proof)
    check_robot(trace, record, cells, folder)
    overview(data, record, folder)
    save(folder / "design_result.json", dict(
        passed=True, variant=data["id"], source_ik_sha256=sha(SEED),
        new_ik_sha256=sha(folder / "robot_motion.json"),
        geometry_sha256=sha(folder / "geometry.json"),
        certificate_sha256=sha(folder / "certificate.json"),
        generator_sha256=sha(__file__), negative_controls=proof["negative_controls"],
        maximum_excursion_scene_mm=data["maximum_excursion_scene_mm"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--offset-mm", type=float, default=2.)
    parser.add_argument("--reuse-ik", action="store_true")
    args = parser.parse_args()
    if not 0 < args.offset_mm <= 4:
        parser.error("--offset-mm must be in (0, 4] template mm")
    generate(args.output, args.offset_mm, args.reuse_ik)


if __name__ == "__main__":
    main()
