"""Six full-height elliptical apertures, with closed ends and a real wood finish."""
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from .hedgehog_in_cage import write_body
from topogym.assets.variation_resources import unpack_assets


BALL_QUAT_XYZW = (.7341127330265252, -.3109226781652186,
                 -.09424941943357217, -.5962571847343461)


def build_ellipse_cage(folder, ball_resource):
    folder = Path(folder)
    unpack_assets(ball_resource, folder)
    height, inner, outer = .240, .082, .090
    window_height, window_width = .224, .058
    shell = trimesh.boolean.difference([
        trimesh.creation.cylinder(radius=outer, height=height, sections=192),
        trimesh.creation.cylinder(radius=inner, height=window_height, sections=192),
    ], engine="manifold")
    cutters = []
    for angle in np.deg2rad(np.arange(-90, 270, 60)):
        radial = np.array([np.cos(angle), np.sin(angle), 0.])
        tangent = np.array([-np.sin(angle), np.cos(angle), 0.])
        cutter = trimesh.creation.cylinder(radius=1, height=1, sections=192)
        cutter.apply_scale([window_width/2, window_height/2, .05])
        transform = np.eye(4)
        transform[:3, :3] = np.column_stack([tangent, [0, 0, 1], radial])
        transform[:3, 3] = radial*(inner+outer)/2
        cutter.apply_transform(transform)
        cutters.append(cutter)
    cage = trimesh.boolean.difference([shell, *cutters], engine="manifold")
    if not cage.is_watertight or len(cage.split()) != 1:
        raise ValueError("Elliptical cage must be one closed connected solid")
    # Keep the concave collision surface: a global convex hull seals the windows.
    write_body(folder, "cage", cage, [cage], (1., 1., 1., 1.), 650., finish="wood")
    ball = trimesh.load(folder/"hedgehog.obj", force="mesh", process=False)
    z = -.112 - Rotation.from_quat(BALL_QUAT_XYZW).apply(ball.vertices)[:, 2].min() + .0002
    q = np.asarray(BALL_QUAT_XYZW)[[3, 0, 1, 2]].tolist()
    report = dict(family="elliptical_windows", window_count=6, window_pitch_deg=60,
        cage_height_m=height, cage_outer_radius_m=outer, cage_inner_radius_m=inner,
        window_height_m=window_height, window_max_width_m=window_width,
        closed_end_thickness_m=.008, finish="dark_wood_texture",
        initial_pose=dict(position_m=[0., 0., float(z)], quaternion_wxyz=q),
        core_diameter_m=.054, spike_count=10, ball_source=ball_resource,
        core_only_exit_band_halfheight_m=(window_height/2)*np.sqrt(1-(.054/window_width)**2),
        geometry_connected=True, historical_certificate_transferred=False,
        full_exit_path_verified=False, robot_solution_verified=False)
    (folder/"asset_report.json").write_text(json.dumps(report, indent=2)+"\n")
    return cage, ball, -height/2, report
