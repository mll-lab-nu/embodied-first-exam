"""Deterministic straight/cross and offset Keyhole outlines, in template mm.

Only authored geometry is exported. Robot routes belong to planning, not the
installed scene resources. The runtime uses the existing compound slab builder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union


LEVELS = ("very_easy", "easier")


def _outline(radius, center_y, bottom, segments=24):
    angle = np.linspace(np.pi, 0., segments + 1)
    arc = np.c_[radius*np.cos(angle), center_y + radius*np.sin(angle)]
    arc[[0, -1], 1] = center_y
    return Polygon(np.vstack((arc, [radius, bottom], [-radius, bottom])))


def _rings(polygon):
    if (polygon.geom_type != "Polygon" or not polygon.is_valid
            or polygon.is_empty or polygon.area <= 0):
        raise ValueError("Keyhole material must be one valid connected polygon")
    return [np.round(np.asarray(r.coords)[:-1], 8).tolist()
            for r in (polygon.exterior, *polygon.interiors)]


def geometry_record(level):
    """Build a frozen resource with the schema of generate_variant_assets()."""
    if level not in LEVELS:
        raise ValueError(f"Unknown simplified Keyhole level: {level}")
    from topogym.assets.variation_resources import read_json
    baseline = read_json("variations/cast_keyhole/F1/geometry.json")
    # Keep the approved lower channel motifs. Only reopen the rounded inlet
    # required by the original F1/F2/F3 perpendicular lower-bore assembly.
    entry_x, offset_x = -3.65, 3.5
    half_width, half_height = 3.5, 3.5
    if level == "very_easy":
        slot = unary_union((box(entry_x-half_width, -40., entry_x+half_width, 8.5),
                            box(entry_x-6.5, -16.5, entry_x+6.5, -9.5)))
    else:
        # Two offsets; overlap at corners admits the finite silver lower bar.
        slot = unary_union((box(entry_x-half_width, -3.-half_height, entry_x+half_width, 8.5),
                            box(entry_x-half_width, -3.-half_height, offset_x+half_width, -3.+half_height),
                            box(offset_x-half_width, -20.-half_height, offset_x+half_width, -3.+half_height),
                            box(entry_x-half_width, -20.-half_height, offset_x+half_width, -20.+half_height),
                            box(entry_x-half_width, -40., entry_x+half_width, -20.+half_height)))
    slot = unary_union((slot, _outline(5.6, 20., 8.5)))
    gold = _outline(13., 21., -35.).difference(slot)
    # Retain F1's exact silver exterior, including its original end notch.
    silver = Polygon(baseline["rings_mm"]["silver"][0]).difference(box(-8.1, -23.3, 8.3, 26.))
    if len(gold.interiors) != 0 or len(silver.interiors) != 1:
        raise ValueError("Expected an open gold fork and one closed silver bore")
    return dict(
        id=f"simplified_{level}", title_zh="十字直通型" if level == "very_easy" else "两处错位型",
        units="mm", scale=3.0, thickness_mm=3.0, density_kg_m3=6600.0,
        gold_offset_z_mm=-47.0,
        initial_relative_pose_id="perpendicular_lower_bore_v1",
        rings_mm=dict(gold=_rings(gold), silver=_rings(silver)),
        design_parameters=dict(nominal_length_mm=69., nominal_width_mm=26.,
                               slot_width_mm=7.0, branch_span_mm=13.0 if level == "very_easy" else 0.,
                               offset_mm=0. if level == "very_easy" else 7.15,
                               silver_lower_bar_height_mm=4.7,
                               inlet_radius_mm=5.6, inlet_center_y_mm=20., inlet_bottom_y_mm=8.5),
        grasp_regions=dict(
            # Outer gold prong: keep both hands away from the central bore.
            # The slanted face grasp spans about 24 mm from this centre.
            gold=dict(center_plate_mm=[28./3., -83./3., 0.], radius_m=.026),
            silver=dict(center_plate_mm=[0., 29., 0.], radius_m=.022)),
        geometry_status="authored_simplification; runtime and robot qualification are separate",
        source="topogym.assets.geometry.cast_keyhole_simplified.geometry_record",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for level in LEVELS:
        path = args.output / level / "geometry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(geometry_record(level), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
