"""Three Keyhole mechanisms, nine silhouettes, and seeded continuous variations.

An unchanged family solution is a witness, never a certificate for new solids.
Every instance must pass independent geometry, robot, and physical validation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

import numpy as np
from shapely import affinity, wkb, set_precision
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from .geometry import ASSET_ROOT
from .inverse_variants import (certify_variant, check_robot, geometry_from_record,
                               polygon_record, save, sha, sweep_polygons)
from .long_stroke import SEED
from .robot_motion import ROOT
from .turnback import controls as turnback_controls
from .variant_assets import require_variant

OUTPUT = ROOT / "runs/environment-solvability/cast_keyhole/families_v1"
FAMILIES = {"F1": "long_stroke_v1", "F2": "eccentric_window_v1", "F3": "turnback_v1"}
TITLES = {"F1_A": "圆冠长梯", "F1_B": "方冠宽肩", "F1_C": "渐缩楔架",
          "F2_A": "豆形偏头", "F2_B": "斜肩偏头", "F2_C": "梨形偏头",
          "F3_A": "圆腹回钩", "F3_B": "方腹折返", "F3_C": "双腹葫芦"}
PALETTES = [
    {"gold": [.61, .43, .12, 1.], "silver": [.56, .61, .66, 1.], "metallic": .8, "roughness": .3},
    {"gold": [.15, .30, .42, 1.], "silver": [.72, .40, .23, 1.], "metallic": .65, "roughness": .4},
    {"gold": [.35, .38, .40, 1.], "silver": [.72, .70, .62, 1.], "metallic": .5, "roughness": .5},
]


def ellipse(x, y, rx, ry):
    return affinity.scale(Point(x, y).buffer(1, quad_segs=12), rx, ry, origin=(x, y))


def envelope(style, parameters):
    """Outer stock only; protected functional material is never scaled."""
    shapes = {
        "F1_A": unary_union([box(-14, -23, 14, 21), ellipse(0, 21, 14, 13)]),
        "F1_B": unary_union([box(-14, -23, 14, 6), box(-16, 6, 16, 31)]),
        "F1_C": Polygon([(-13, -23), (13, -23), (17, 16), (13, 27), (0, 34), (-13, 27), (-17, 16)]),
        "F2_A": ellipse(-6, 21, 21, 13),
        "F2_B": Polygon([(-13, 2), (-26, 8), (-30, 25), (-17, 34), (-5, 34), (13, 21), (13, 4)]),
        "F2_C": unary_union([ellipse(-15, 30, 13, 17), Polygon([(-13, 2), (10, 4), (-2, 30), (-28, 30)])]),
        "F3_A": ellipse(1, -11, 22, 15),
        "F3_B": box(-20, -21, 22, 3).buffer(1, quad_segs=2),
        "F3_C": unary_union([ellipse(0, 21, 18, 13), ellipse(0, -13, 20, 12)]),
    }
    shape = affinity.scale(shapes[style], parameters["width_scale"], parameters["height_scale"], origin=(0, 0))
    return affinity.translate(shape, xoff=parameters["lateral_shift_mm"])


def parameters(seed=None):
    if seed is None:
        return dict(width_scale=1., height_scale=1., lateral_shift_mm=0., palette=0)
    rng = np.random.default_rng(seed)
    return dict(width_scale=float(rng.uniform(.96, 1.04)),
                height_scale=float(rng.uniform(.96, 1.04)),
                lateral_shift_mm=float(rng.uniform(-.5, .5)), palette=int(rng.integers(len(PALETTES))))


def normalize_outer_stock(shape):
    """Remove floating-point slits, while bounding actual material changes."""
    if shape.minimum_clearance >= 1e-8:
        return shape
    normalized = set_precision(shape, 1e-9)
    if shape.symmetric_difference(normalized).area > 1e-6:
        raise ValueError("Numerical cleanup changed too much material")
    return normalized


def family_seed(root, family, source_override=None):
    source = Path(source_override) if source_override else ROOT / "runs/environment-solvability/cast_keyhole" / FAMILIES[family]
    geometry, _ = require_variant(source / "geometry.json")
    trace = json.loads((source / "ik_proposal.json").read_text())
    cache = root / "family_cache" / (family+"_"+sha(source / "ik_proposal.json")[:12])
    cache.mkdir(parents=True, exist_ok=True)
    fingerprint = dict(trace_sha256=sha(source / "ik_proposal.json"),
                       geometry_sha256=sha(source / "geometry.json"),
                       sweep_code_sha256=sha(Path(__file__).with_name("inverse_variants.py")),
                       template_sha256=sha(ASSET_ROOT / "template.json"))
    cache_file = cache / "sweep.json"
    if cache_file.exists():
        meta = json.loads(cache_file.read_text())
        if meta["fingerprint"] == fingerprint and meta["wkb_sha256"] == sha(cache / "sweep.wkb"):
            return source, geometry, trace, wkb.loads((cache / "sweep.wkb").read_bytes()), meta["sampling"]
    sweep, sampling = sweep_polygons(trace)
    (cache / "sweep.wkb").write_bytes(sweep.wkb)
    save(cache_file, dict(fingerprint=fingerprint, sampling=sampling, wkb_sha256=sha(cache / "sweep.wkb")))
    return source, geometry, trace, sweep, sampling


def build(style, root=OUTPUT, instance_id=None, seed=None, source_override=None, parameters_override=None):
    root = Path(root); family = style[:2]; instance_id = instance_id or style
    folder = root / instance_id
    if (folder / "qualification.json").exists():
        raise ValueError("Refusing to overwrite a qualified instance")
    folder.mkdir(parents=True, exist_ok=True)
    source, original, trace, sweep, sampling = family_seed(root, family, source_override)
    params = parameters(seed) if parameters_override is None else dict(parameters_override)
    if set(params) != {"width_scale", "height_scale", "lateral_shift_mm", "palette"}:
        raise ValueError("Exactly four appearance parameters are required")
    for key, lo, hi in (("width_scale", .96, 1.04), ("height_scale", .96, 1.04),
                        ("lateral_shift_mm", -.5, .5)):
        if not np.isfinite(params[key]) or not lo <= params[key] <= hi:
            raise ValueError(f"Invalid {key}")
    if isinstance(params["palette"], bool) or not isinstance(params["palette"], (int, np.integer)) or not 0 <= params["palette"] < len(PALETTES):
        raise ValueError("Invalid palette")
    gold = Polygon(original["rings_mm"]["gold"][0])
    # Added stock lives outside the original envelope; the moving plate's
    # expanded sweep is removed. Only nonfunctional crown stock may be trimmed.
    protected_core = gold.intersection(box(-100, -100, 100, 27))
    base = gold
    if style == "F1_B":
        base = gold.intersection(box(-100, -100, 100, 31))
    elif style == "F1_C":
        crown = Polygon([(-100, -100), (100, -100), (100, 27), (13, 27), (0, 34), (-13, 27), (-100, 27)])
        base = gold.intersection(crown)
    additions = envelope(style, params).difference(gold.convex_hull)
    protected_grasp = box(-22, -45, -2, -20)
    additions = additions.difference(protected_grasp).difference(sweep)
    combined = base.union(additions).buffer(0)
    if combined.geom_type == "MultiPolygon":
        candidates = [p for p in combined.geoms if p.buffer(1e-8).covers(base)]
        if len(candidates) != 1:
            raise ValueError("No unique solid containing the protected seed")
        combined = candidates[0]
    combined = combined.simplify(.015, preserve_topology=True).union(base)
    if parameters_override is not None and combined.minimum_clearance < 1e-8:
        # Explicit v2 inputs: eliminate sub-nanometre Boolean slits before the
        # slab mesher rounds coordinates. This is numerical normalization, not
        # a relaxed topology check. All protection and collision tests still run.
        combined = normalize_outer_stock(combined)
    if combined.geom_type != "Polygon" or not combined.is_valid or combined.interiors:
        raise ValueError("Appearance introduced a disconnected solid or extra hole")
    if protected_core.difference(combined).area > 1e-7:
        raise ValueError("Functional material changed")
    added_area = combined.difference(gold).area
    if added_area < .04 * gold.area or combined.difference(gold).intersection(protected_grasp).area > 1e-7:
        raise ValueError("Appearance is too subtle or intrudes into the grasp region")
    proposal = json.loads((source / "proposal.json").read_text())
    proposal.update(id=instance_id, title_zh=f"{style} · {TITLES[style]}", family=family,
                    source_family=original["id"], appearance_style=style, appearance_parameters=params,
                    random_seed=seed, family_ik_frozen=True,
                    family_proposal_sha256=sha(source / "proposal.json"))
    save(folder / "proposal.json", proposal)
    trace = deepcopy(trace)
    trace["report"].update(source_proposal_sha256=sha(folder / "proposal.json"),
                           family_ik_reused=True, family_ik_sha256=sha(source / "ik_proposal.json"))
    save(folder / "ik_proposal.json", trace)
    record = deepcopy(original)
    record.update(id=instance_id, title_zh=proposal["title_zh"], family=family, appearance_style=style,
                  source_family=original["id"], family_geometry_sha256=sha(source / "geometry.json"),
                  family_ik_sha256=sha(source / "ik_proposal.json"),
                  source_proposal_sha256=sha(folder / "proposal.json"),
                  input_trace_sha256=sha(folder / "ik_proposal.json"),
                  design_method="Frozen solved family IK; protected functional solid plus exterior stock outside its silver sweep",
                  rings_mm=dict(gold=polygon_record(combined), silver=original["rings_mm"]["silver"]),
                  appearance_parameters=params, visual_material=PALETTES[params["palette"]],
                  protected_functional_core_preserved=True, removed_crown_stock_mm2=gold.difference(combined).area,
                  added_exterior_area_mm2=added_area,
                  outer_shape_bounds_mm=list(combined.bounds), sweep_sampling=sampling)
    save(folder / "geometry.json", record)
    for name in ("proposal.json", "geometry.json", "ik_proposal.json", "certificate.json"):
        shutil.copy2(source / name, folder / ("family_" + name))
    meshes, cells = geometry_from_record(record)
    solid = []
    for name, mesh, parts, euler in zip(("gold", "silver"), meshes, cells, (2, 0)):
        item = dict(name=name, watertight=bool(mesh.is_watertight), components=len(mesh.split()),
                    euler=int(mesh.euler_number), collision_prisms=len(parts),
                    volume_error_m3=float(abs(sum(p.volume for p in parts) - mesh.volume)))
        if not item["watertight"] or item["components"] != 1 or item["euler"] != euler or item["volume_error_m3"] > 1e-10:
            raise ValueError(item)
        solid.append(item)
    save(folder / "solid_audit.json", dict(passed=True, pieces=solid))
    save(folder / "candidate.json", dict(status="awaiting_geometry_and_physics_validation", family=family,
         style=style, random_seed=seed, parameters=params, geometry_sha256=sha(folder / "geometry.json")))
    print(f"Built {instance_id}: added exterior area {added_area:.1f} mm^2", flush=True)
    return folder


def qualify_geometry(folder, baseline_seed_path=None):
    folder = Path(folder)
    data = json.loads((folder / "proposal.json").read_text())
    trace = json.loads((folder / "ik_proposal.json").read_text())
    record = json.loads((folder / "geometry.json").read_text())
    meshes, cells = geometry_from_record(record)
    proof = certify_variant(data, trace, record, meshes, cells, folder)
    if record["family"] == "F3":
        baseline = Path(baseline_seed_path) if baseline_seed_path is not None else SEED
        if sha(baseline) != data["source_ik_sha256"]:
            raise ValueError("Baseline IK for mechanism controls changed")
        proof["negative_controls"].update(turnback_controls(trace, json.loads(baseline.read_text()), cells))
    if not all(n["collision_found"] for n in proof["negative_controls"].values()):
        raise ValueError("Appearance erased a required mechanism")
    proof["protected_functional_core_preserved"] = True
    save(folder / "certificate.json", proof)
    check_robot(trace, record, cells, folder)
    save(folder / "design_result.json", dict(passed=True, variant=record["id"], family=record["family"],
         geometry_sha256=sha(folder / "geometry.json"), certificate_sha256=sha(folder / "certificate.json"),
         generator_sha256=sha(__file__), negative_controls=proof["negative_controls"],
         status="geometry_verified_physics_pending"))


def overview(root=OUTPUT):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch
    root = Path(root)
    fig, axes = plt.subplots(3, 3, figsize=(12, 12), sharex=True, sharey=True)
    polygons = {}
    for ax, style in zip(axes.flat, TITLES):
        path = root / style / "geometry.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text()); p = Polygon(record["rings_mm"]["gold"][0]); polygons[style] = p
        ax.add_patch(Patch(np.asarray(p.exterior.coords), color="#73777c"))
        ax.set_title(f"{style}  {record['source_family']}", fontsize=10)
        ax.set_aspect("equal"); ax.set_xlim(-30, 32); ax.set_ylim(-38, 56); ax.axis("off")
    fig.suptitle("Same scale, same gray material, protected mechanism / grasp / solution", fontsize=12)
    fig.tight_layout(); fig.savefig(root / "nine_silhouettes.png", dpi=160); plt.close(fig)
    distances = {a: {b: 1 - p.intersection(q).area / p.union(q).area
                    for b, q in polygons.items() if a != b} for a, p in polygons.items()}
    save(root / "silhouette_distances.json", dict(metric="1 minus planar silhouette IoU; same scale and alignment",
         pairs=distances, human_review_required=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("build", "qualify", "overview"))
    p.add_argument("--style", choices=tuple(TITLES)); p.add_argument("--root", type=Path, default=OUTPUT)
    p.add_argument("--instance-id"); p.add_argument("--seed", type=int)
    args = p.parse_args()
    if args.command == "overview":
        overview(args.root)
    elif not args.style:
        p.error("--style is required")
    elif args.command == "build":
        build(args.style, args.root, args.instance_id, args.seed)
    else:
        qualify_geometry(args.root / (args.instance_id or args.style))


if __name__ == "__main__":
    main()
