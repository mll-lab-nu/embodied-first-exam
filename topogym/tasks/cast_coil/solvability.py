"""Constructive solvability report for the current prototype, not a robot demo.

Recheck the known route against the authored solids and exported collision
boxes, independently sample triangle meshes, and bound table clearance over
the entire motion. The HTML viewer only illustrates these geometric poses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from omegaconf import OmegaConf

from .geometry import generate_assets
from .verification import box_corners, geometric_audit, prototype_route

ROOT = Path(__file__).resolve().parents[3]
OFFICIAL_URL = "https://www.huzzle.eu/wp-content/uploads/2018/01/515056-Huzzle-Cast-Coil-Oct-2017.pdf"


def minimum_height(motion, corners):
    """Exact vertex z minimum: endpoints plus all sinusoid stationary points.

    For an orthogonal compound a linear projection attains its minimum at a
    corner. Under fixed-axis rotation each corner's z is c + a cos(t) + b sin(t).
    Endpoint-only or finite-pose checks can miss a corner dipping below a table.
    """
    corners = np.asarray(corners)
    if motion.axis is None or abs(motion.angle_rad) < 1e-15:
        options = []
        for u in (0., 1.):
            R, t = motion.pose(u)
            zs = (corners@R.T+t)[:, 2]
            index = int(np.argmin(zs))
            options.append(dict(minimum_z_m=float(zs[index]), u=u, corner_index=index))
        return min(options, key=lambda row: row['minimum_z_m'])
    axis = np.asarray(motion.axis)
    if not np.isclose(np.linalg.norm(axis), 1., atol=1e-12):
        raise ValueError('A unit rotation axis is required')
    points = corners@motion.start_rotation.T+motion.start_translation-motion.pivot
    parallel = (points@axis)[:, None]*axis
    perpendicular = points-parallel
    cross = np.cross(axis, points)
    lo, hi = sorted((0., motion.angle_rad))
    best = dict(minimum_z_m=float('inf'))
    for i in range(len(points)):
        a, b = perpendicular[i, 2], cross[i, 2]
        phase = math.atan2(b, a)
        angles = [lo, hi]
        for k in range(math.ceil((lo-phase)/math.pi), math.floor((hi-phase)/math.pi)+1):
            angles.append(phase+k*math.pi)
        for angle in angles:
            z = motion.pivot[2]+parallel[i, 2]+a*math.cos(angle)+b*math.sin(angle)
            if z < best['minimum_z_m']:
                best = dict(minimum_z_m=float(z), u=float(angle/motion.angle_rad), corner_index=i)
    return best


def table_audit(assembly, motions, initial_clearance_m):
    initial_bottom = min(b.visual.bounds[0, 2] for b in assembly.bodies)
    origin_above_table = -initial_bottom+initial_clearance_m
    rows = [dict(name=m.name, **minimum_height(m, box_corners(assembly.bodies[1].boxes))) for m in motions]
    lowest = min(row['minimum_z_m'] for row in rows)
    clearance = origin_above_table+lowest
    required = max(0., -clearance)
    # Choose a reproducible geometric margin, not a robot reachability claim.
    lift = math.ceil((required+.005)/.010)*.010
    return dict(method='analytic sinusoid extrema at all compound corners', segments=rows,
        initial_floor_clearance_m=initial_clearance_m, assembly_origin_above_table_m=float(origin_above_table),
        minimum_table_clearance_without_lift_m=float(clearance),
        minimum_lift_for_nonpenetration_m=float(required), proposed_common_lift_m=float(lift),
        minimum_table_clearance_after_lift_m=float(clearance+lift),
        lift_requires_grasp_or_support=True, robot_and_fixture_collisions_checked=False,
        scope='horizontal table only; yaw about world z preserves this bound')


def exported_boxes_match(folder, assembly):
    """Check the actual URDF compounds after restoring their COM origins."""
    folder = Path(folder)
    try:
        if json.loads((folder/'template.json').read_text()) != assembly.template:
            return False
        report = json.loads((folder/'geometry_report.json').read_text())
        if len(report['bodies']) != len(assembly.bodies):
            return False
        for body, item in zip(assembly.bodies, report['bodies']):
            if item['name'] != body.name:
                return False
            root = ET.parse(folder/body.name/f'{body.name}.urdf')
            boxes = []
            for node in root.findall('.//collision'):
                center = np.fromstring(node.find('origin').get('xyz'), sep=' ')+item['origin_m']
                half = np.fromstring(node.find('geometry/box').get('size'), sep=' ')/2
                boxes.append([center-half, center+half])
            def canonical(values):
                return sorted(tuple(np.round(b, 11).ravel()) for b in values)
            if canonical(boxes) != canonical(body.boxes):
                return False
        return True
    except (FileNotFoundError, KeyError, ValueError, ET.ParseError):
        return False


def mesh_crosscheck(assembly, motions, samples_per_segment=1001):
    import fcl

    objects = []
    for body in assembly.bodies:
        mesh = body.visual
        model = fcl.BVHModel()
        model.beginModel(len(mesh.faces), len(mesh.vertices))
        model.addSubModel(np.asarray(mesh.vertices), np.asarray(mesh.faces, dtype=np.int32))
        model.endModel()
        objects.append(fcl.CollisionObject(model, fcl.Transform()))
    rows = []
    for motion in motions:
        distances, collisions = [], []
        for u in np.linspace(0, 1, samples_per_segment):
            objects[1].setTransform(fcl.Transform(*motion.pose(u)))
            result = fcl.CollisionResult()
            fcl.collide(*objects, fcl.CollisionRequest(), result)
            if result.is_collision:
                collisions.append(float(u))
            distance = fcl.distance(*objects, fcl.DistanceRequest(), fcl.DistanceResult())
            distances.append(float(distance))
        rows.append(dict(name=motion.name, samples=samples_per_segment,
            collision_sample_count=len(collisions), collision_u=collisions,
            minimum_sampled_mesh_distance_m=min(distances)))
    return dict(method='FCL triangle meshes; discrete independent cross-check, not the continuous proof',
        passed=all(r['collision_sample_count'] == 0 and r['minimum_sampled_mesh_distance_m'] > 0 for r in rows),
        total_samples=samples_per_segment*len(motions), segments=rows)


def cached_physics(assembly):
    base = ROOT/'runs/environment-solvability/cast_coil/photo_reference_v1'
    rows = []
    for profile in ('nominal', 'half_dt'):
        file = base/profile/'report.json'
        if not file.is_file():
            rows.append(dict(profile=profile, available=False, passed=False))
            continue
        data = json.loads(file.read_text())
        case = next((c for c in data['cases'] if c['name'] == 'baseline_3x_route'), None)
        matches = exported_boxes_match(base/profile/'assets/baseline_3x', assembly)
        rows.append(dict(profile=profile, available=True, geometry_matches=matches,
            passed=bool(matches and case and case['passed']), dt_s=data['config']['dt'],
            source=str(file.relative_to(ROOT)), source_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
            suite_passed=data['passed'], case=case))
    return dict(reused_existing_evidence=True, physics_rerun_in_this_report=False, cases=rows,
        both_baseline_route_checks_passed=all(r['passed'] for r in rows),
        scope='Gold fixed in air; silver driven by bounded forces/torques with gravity compensation; no robot')


def write_view(output, assembly, motions, report):
    # Geometry is embedded so file:// works without a server or network imports.
    payload = dict(meshes=[dict(vertices=(b.visual.vertices*1000).round(8).tolist(),
        faces=b.visual.faces.tolist(), name=b.name) for b in assembly.bodies],
        motions=[m.to_dict() for m in motions], table=report['table'], scale=assembly.scale,
        total_seconds=sum(m.duration_s for m in motions), official_url=OFFICIAL_URL)
    template = Path(__file__).with_name('solvability_view.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__', json.dumps(payload, ensure_ascii=False)))


def plot_steps(output, assembly, motions, table):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    views = [('Initial (lifted together)', np.eye(3), np.zeros(3)),
             ('1. Slide silver -x: 21.75 mm', *motions[0].pose(1)),
             ('2. Rotate silver -90 deg about y', *motions[1].pose(1)),
             ('3. Extract silver +x: 207 mm', *motions[2].pose(1))]
    ztable = -(table['assembly_origin_above_table_m']+table['proposed_common_lift_m'])*1000
    fig = plt.figure(figsize=(13, 10), layout='constrained')
    fig.set_constrained_layout_pads(w_pad=.08, h_pad=.08, hspace=.12, wspace=.05)
    for i, (label, R, t) in enumerate(views):
        ax = fig.add_subplot(2, 2, i+1, projection='3d', proj_type='ortho')
        parts = []
        for moving, body in enumerate(assembly.bodies):
            mesh = body.visual
            vertices = (mesh.vertices@R.T+t if moving else mesh.vertices)*1000
            parts.append(vertices)
            ax.add_collection3d(Poly3DCollection(vertices[mesh.faces],
                facecolors='#8798aa' if moving else '#b39843', edgecolors='#455363', linewidths=.12))
        points = np.concatenate(parts)
        lo, hi = points.min(axis=0)-10, points.max(axis=0)+10
        lo[2] = ztable
        plane = np.array([[lo[0], lo[1], ztable], [hi[0], lo[1], ztable],
                          [hi[0], hi[1], ztable], [lo[0], hi[1], ztable]])
        ax.add_collection3d(Poly3DCollection([plane], facecolors='#e0e7ee', alpha=.5))
        ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), zlim=(lo[2], hi[2]),
               title=label, xlabel='x (mm)', ylabel='y (mm)', zlabel='z (mm)')
        ax.set_box_aspect(hi-lo, zoom=.82)
        ax.view_init(elev=24, azim=-65)
    fig.suptitle('Current prototype: continuous geometric solution, gold held fixed\n'
                 'Common lift 70 mm; no robot execution or dynamics in this visualization')
    fig.savefig(output/'solution_steps.png', dpi=135)
    plt.close(fig)


def run(output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Use a new output directory to preserve earlier evidence')
    output.mkdir(parents=True, exist_ok=True)
    cfg = OmegaConf.load(ROOT/'configs/cast_coil_preview.yaml')
    if float(cfg.task.scale) != 3.:
        raise ValueError('This explanation targets the baseline 3x preview; update its instructions for a different scale')
    assembly, _ = generate_assets(output/'assets', scale=float(cfg.task.scale))
    if cfg.task.variant != assembly.template['template_id']:
        raise ValueError('Preview task and current geometry do not match')
    motions = prototype_route(assembly)
    audit = geometric_audit(assembly)
    mesh_check = mesh_crosscheck(assembly, motions)
    table = table_audit(assembly, motions, float(cfg.task.initial_floor_clearance_m))
    matches = exported_boxes_match(ROOT/'runs/environment_bootstrap/cast_coil/assembly_initial/assets', assembly)
    continuity = all(np.allclose(a.pose(1)[0], b.pose(0)[0], atol=1e-12, rtol=0)
        and np.allclose(a.pose(1)[1], b.pose(0)[1], atol=1e-12, rtol=0) for a, b in zip(motions, motions[1:]))
    report = dict(task_id='cast_coil', scope='constructive prototype solvability and table-clearance explanation',
        current_prototype_solvable=bool(audit['prototype_route_certified'] and mesh_check['passed'] and continuity),
        geometry_modified=False, current_preview_assets_match=matches, continuous_junctions=continuity,
        geometry_audit=audit, independent_mesh_check=mesh_check, table=table,
        existing_physics=cached_physics(assembly), official_source_url=OFFICIAL_URL,
        official_route_verified=False, robot_execution_verified=False, formal_demo_generated=False,
        simulation_steps_this_run=0,
        conclusion_zh='当前原型有完整三段解；官方八步的度量映射仍未验证。贴桌执行此路径会碰桌，须先整体抬高。',
        limitations=['Manufacturer drawings do not supply metric CAD or pivots.',
            'Illustrated screen directions cannot simply be equated with world axes.',
            'The shorter prototype route does not establish an error or shortcut in the commercial puzzle.',
            'Table clearance does not certify gripper reachability, grasp stability, or fixture clearance.'])
    (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (output/'route.json').write_text(json.dumps(dict(coordinates='assembly frame, metres, right-handed rotations; not COM translations',
        fixed='coil_gold', moving='coil_silver', motions=[m.to_dict() for m in motions]), indent=2)+'\n')
    if not (report['current_prototype_solvable'] and matches and report['existing_physics']['both_baseline_route_checks_passed']):
        raise RuntimeError('Evidence changed or is missing; inspect result.json before publishing the explanation')
    write_view(output, assembly, motions, report)
    plot_steps(output, assembly, motions, table)
    manifest = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'artifact_manifest.json').write_text(json.dumps(dict(sha256=manifest), indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='runs/environment-solvability/cast_coil/solvability_explanation_v1')
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({k: result[k] for k in ('current_prototype_solvable', 'current_preview_assets_match', 'table')}, indent=2))
