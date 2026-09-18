"""One-factor appearance variants of the original verified Coil prototype."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np

from .geometry import CoilAssembly, partition_solid
from .verification import (
    CompoundCollision,
    Motion,
    certify_motion,
    geometric_audit,
    prototype_route,
)

PRESETS = {
    "face_small": dict(face_scale=0.95, depth_scale=1.0, corner_cut_ratio=0.0),
    "depth_thick": dict(face_scale=1.0, depth_scale=1.10, corner_cut_ratio=0.0),
    "corner_cut": dict(face_scale=1.0, depth_scale=1.0, corner_cut_ratio=0.25),
}
TITLES = {
    "face_small": "基础版单参数 · 正面缩小 5%",
    "depth_thick": "基础版单参数 · 叠层加厚 10%",
    "corner_cut": "基础版单参数 · 外角切角 5.25 mm",
}


def coordinate_scale(template):
    params = template.get("appearance_design", {}).get("parameters", {})
    s, d = params.get("face_scale", 1.0), params.get("depth_scale", 1.0)
    return np.array([s, d, s], dtype=float)


def appearance_route(assembly):
    if not np.isclose(assembly.scale, 3.0):
        raise ValueError("Appearance routes are authored for the 3x instance")
    scale = coordinate_scale(assembly.template)
    route = []
    if "inverse_design" in assembly.template:
        from .inverse_design import variant_route

        design = assembly.template["inverse_design"]
        source_route = variant_route(design["kind"], design.get("parameters"))
    else:
        source_route = prototype_route(CoilAssembly())
    for motion in source_route:
        fields = {
            name: getattr(motion, name) * scale
            for name in ("start_translation", "end_translation", "pivot", "advance")
            if getattr(motion, name, None) is not None
        }
        route.append(replace(motion, **fields))
    return route


def corner_cuts(length, *, pitch=0.00075):
    """Inward staircase at four x/z outer corners, extruded through y."""
    if length == 0:
        return []
    n = int(round(length / pitch))
    if not np.isclose(n * pitch, length, atol=1e-12, rtol=0):
        raise ValueError("This prototype cuts corners on a 0.75 mm grid")
    cuts = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            for i in range(n):
                bounds = np.array(
                    [
                        [0.051 - length + i * pitch, -0.1, 0.051 - (i + 1) * pitch],
                        [0.052, 0.1, 0.052],
                    ]
                )
                cuts.append(np.sort(bounds * [sx, 1, sz], axis=0))
    return np.round(cuts, 12)


def create_template(kind):
    parameters = PRESETS[kind]
    original = CoilAssembly()
    template = deepcopy(original.template)
    s, d, q = (parameters[k] for k in ("face_scale", "depth_scale", "corner_cut_ratio"))
    scale = np.array([s, d, s])
    cuts = corner_cuts(0.021 * q)
    boxes = {}
    for body in original.bodies:
        _, cells = partition_solid(np.round(body.boxes, 12), cuts)
        boxes[body.name] = (cells * scale / original.unit).tolist()
    for key in (
        "outer_width",
        "band_width",
        "bridge_height",
        "bridge_center_clearance",
        "relief_width",
        "relief_depth",
    ):
        template[key] *= s
    for key in ("layer_thickness", "layer_clearance"):
        template[key] *= d
    template.update(
        template_id=f"cast_coil_appearance_{kind}_v1",
        geometry_status="single_parameter_appearance_of_verified_original_prototype",
        authored_boxes_mm=boxes,
        appearance_design=dict(
            kind=kind,
            parameters=parameters,
            seed_template_id=original.template["template_id"],
            seed_archive="2026-09-17_aloha_full",
            seed_template_sha256=hashlib.sha256(
                json.dumps(
                    original.template, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            changed_parameters=[
                k
                for k, v in parameters.items()
                if v != (0.0 if k == "corner_cut_ratio" else 1.0)
            ],
            corner_cut_length_m=0.021 * s * q,
            corner_method="inward 0.75 mm orthogonal staircase in seed coordinates; not a smooth bevel",
            coordinate_scale=scale.tolist(),
            inherited_route="original slide, quarter-turn, extraction; transformed translations and pivot",
        ),
    )
    return template


def generate(kind, output):
    folder = Path(output)
    if (folder / "template.json").exists():
        raise FileExistsError(folder)
    template = create_template(kind)
    assembly = CoilAssembly(template)
    seed = CoilAssembly()
    audit = geometric_audit(assembly)
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    certificate = [
        certify_motion(collision, m, margin_m=0.0002)
        for m in appearance_route(assembly)
    ]
    negative = audit["straight_extraction_controls"]
    # The certificate stops at first contact. Find an interior overlap witness
    # as well, so a zero-gap tangency alone is never called a blocked path.
    for control in negative:
        if control.get("witness") and control["witness"]["gap_m"] < 0:
            control["overlap_witness"] = control["witness"]
            continue
        motion = Motion(
            **{
                k: np.asarray(v) if isinstance(v, list) else v
                for k, v in control["motion"].items()
            }
        )
        samples = [
            (float(u), collision.gap(*motion.pose(u))) for u in np.linspace(0, 1, 257)
        ]
        u, gap = min(samples, key=lambda item: item[1])
        control["overlap_witness"] = dict(u=u, gap_m=gap)
    mass_ratios = [
        a.visual.volume / b.visual.volume for a, b in zip(assembly.bodies, seed.bodies)
    ]
    geometry = audit["geometry"]
    report = dict(
        kind=kind,
        parameters=template["appearance_design"]["parameters"],
        seed="original 2026-09-17_aloha_full; not one of the three inverse-designed variants",
        changed_parameters=template["appearance_design"]["changed_parameters"],
        geometry=geometry,
        route=certificate,
        route_certified=all(c["passed"] for c in certificate),
        straight_controls=negative,
        all_straight_controls_blocked=all(
            c["overlap_witness"]["gap_m"] < 0 for c in negative
        ),
        mass_ratios=mass_ratios,
        controller_retuning_applied=False,
        physical_execution_verified=False,
        scope="geometry stage only; downstream robot execution reports are separate",
    )
    if (
        not geometry["passed"]
        or not report["route_certified"]
        or not report["all_straight_controls_blocked"]
    ):
        raise ValueError(f"Geometry or solvability rejected: {report}")
    if len(report["changed_parameters"]) != 1 or not all(
        0.9 - 1e-9 <= r <= 1.1 + 1e-9 for r in mass_ratios
    ):
        raise ValueError(
            "Expected one changed appearance parameter and bounded mass variation"
        )
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.json").write_text(json.dumps(template, indent=2) + "\n")
    (folder / "synthesis_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(dict(kind=kind, route_certified=True, mass_ratios=mass_ratios)),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=PRESETS, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.kind, args.output)
