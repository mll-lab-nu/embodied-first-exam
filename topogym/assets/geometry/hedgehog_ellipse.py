"""Hedgehog medium cage: waisted windows, narrow slots with one wide band.

Replaced the six 58 mm elliptical windows on 2026-09-29: the ball's narrowest
projection is 97 mm, so no straight exit existed. The band sits above the ball's
rest height, so the ball must be lifted into it and turned to a fitting pose.
"""
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from .hedgehog_in_cage import write_body
from topogym.assets.variation_resources import unpack_assets


BALL_QUAT_XYZW = (.7341127330265252, -.3109226781652186,
                 -.09424941943357217, -.5962571847343461)


def window_parts(wide_width, narrow_width, band_center, band_half_height, ramp, slot_half_height):
    """Convex (tangent, z) outlines: lower slot, wide band with ramps, upper slot."""
    n, w = narrow_width/2, wide_width/2
    low, high = band_center-band_half_height, band_center+band_half_height
    overlap = .001  # Slots enter the band so the union has no coplanar seams.
    return [[(-n, -slot_half_height), (n, -slot_half_height), (n, low-ramp+overlap), (-n, low-ramp+overlap)],
            [(-n, low-ramp), (n, low-ramp), (w, low), (w, high), (n, high+ramp), (-n, high+ramp), (-w, high), (-w, low)],
            [(-n, high+ramp-overlap), (n, high+ramp-overlap), (n, slot_half_height), (-n, slot_half_height)]]


def build_waisted_cage(folder, ball_resource, window_count=4, wide_width=.105, narrow_width=.048,
                       band_center=.020, band_half_height=.055, ramp=.015):
    folder = Path(folder)
    unpack_assets(ball_resource, folder)
    height, inner, outer = .240, .082, .090
    slot_half_height = .104
    shell = trimesh.boolean.difference([
        trimesh.creation.cylinder(radius=outer, height=height, sections=192),
        trimesh.creation.cylinder(radius=inner, height=.224, sections=192),
    ], engine="manifold")
    parts = window_parts(wide_width, narrow_width, band_center, band_half_height, ramp, slot_half_height)
    centers = -90+np.arange(window_count)*360/window_count
    cutters = []
    for angle in np.deg2rad(centers):
        radial = np.array([np.cos(angle), np.sin(angle), 0.])
        tangent = np.array([-np.sin(angle), np.cos(angle), 0.])
        for outline in parts:
            points = [t*tangent+z*np.array([0., 0., 1.])+r*radial
                      for t, z in outline for r in (inner-.02, outer+.02)]
            cutters.append(trimesh.convex.convex_hull(np.array(points)))
    cage = trimesh.boolean.difference([shell, *cutters], engine="manifold")
    if not cage.is_watertight or len(cage.split()) != 1:
        raise ValueError("Waisted cage must be one closed connected solid")
    # Keep the concave collision surface: a global convex hull seals the windows.
    write_body(folder, "cage", cage, [cage], (1., 1., 1., 1.), 650., finish="wood")
    ball = trimesh.load(folder/"hedgehog.obj", force="mesh", process=False)
    z = -.112 - Rotation.from_quat(BALL_QUAT_XYZW).apply(ball.vertices)[:, 2].min() + .0002
    q = np.asarray(BALL_QUAT_XYZW)[[3, 0, 1, 2]].tolist()
    post = 2*inner*np.sin(np.pi/window_count)-wide_width  # chord left between wide bands at the inner wall
    report = dict(family="waisted_windows", window_count=window_count, window_pitch_deg=360/window_count,
        window_centers_deg=centers.tolist(), cage_height_m=height, cage_outer_radius_m=outer,
        cage_inner_radius_m=inner, window_slot_half_height_m=slot_half_height,
        window_wide_width_m=wide_width, window_narrow_width_m=narrow_width,
        window_band_center_m=band_center, window_band_half_height_m=band_half_height, window_ramp_m=ramp,
        minimum_post_chord_at_inner_wall_m=float(post), closed_end_thickness_m=.008, finish="dark_wood_texture",
        initial_pose=dict(position_m=[0., 0., float(z)], quaternion_wxyz=q),
        core_diameter_m=.054, spike_count=10, ball_source=ball_resource,
        ball_minimum_projected_width_m=.097, geometry_connected=True,
        historical_certificate_transferred=False, full_exit_path_verified=False, robot_solution_verified=False)
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    return cage, ball, -height/2, report
