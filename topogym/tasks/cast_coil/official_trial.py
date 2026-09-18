"""Search a metric interpretation of the official Coil solution's first four moves.

The reference is an illustrated sequence, not CAD or a metric trajectory. This
experiment keeps the existing solids and gold fixed, searches silver motions,
and rejects early full separation masquerading as an eight-move solution.
Failure is a bounded search result, not a proof that all official paths fail.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import time

import numpy as np
from numba import njit
from scipy.optimize import differential_evolution
from scipy.spatial.transform import Rotation

from .geometry import CoilAssembly, generate_assets
from .verification import CompoundCollision, Motion, REFERENCE_STEPS, REFERENCE_URL, box_corners, certify_motion


@njit(cache=True)
def _path_gaps(deltas, radii, axes, translations):
    values = np.empty(len(translations))
    for n in range(len(translations)):
        projections = axes[n]@translations[n]
        minimum = 1e6
        for i in range(deltas.shape[1]):
            for j in range(deltas.shape[2]):
                gap = -1e6
                for k in range(axes.shape[1]):
                    gap = max(gap, abs(deltas[n, i, j, k]+projections[k])-radii[n, i, j, k])
                minimum = min(minimum, gap)
        values[n] = minimum
    return values


class PoseFamily:
    """Precompute OBB projection data for an orientation sequence, in mm."""
    def __init__(self, boxes, rotations):
        self.rotations = np.asarray(rotations)
        ac, bc = [b.mean(axis=1) for b in boxes]
        ah, bh = [np.diff(b, axis=1)[:, 0]/2 for b in boxes]
        axes, deltas, radii = [], [], []
        for R in self.rotations:
            ax = np.concatenate((np.eye(3), R.T, np.cross(np.eye(3)[:, None], R.T[None]).reshape(-1, 3)))
            norms = np.linalg.norm(ax, axis=1)
            ax /= np.maximum(norms, 1e-10)[:, None]
            delta = ((bc@R.T)[None]-ac[:, None])@ax.T
            radius = (ah@abs(ax.T))[:, None]+(bh@abs(R.T@ax.T))[None]
            # A degenerate cross product is not a separating axis.
            radius[:, :, norms < 1e-10] = 1e6
            axes.append(ax)
            deltas.append(delta)
            radii.append(radius)
        self.data = [np.asarray(v) for v in (deltas, radii, axes)]
        corners = box_corners(boxes[1])
        self.moving_bounds = np.array([(corners@R.T).min(axis=0) for R in rotations]), np.array([
            (corners@R.T).max(axis=0) for R in rotations])
        self.fixed_low, self.fixed_high = boxes[0][:, 0].min(axis=0), boxes[0][:, 1].max(axis=0)

    def gaps(self, translations):
        return _path_gaps(*self.data, np.ascontiguousarray(translations, dtype=float))

    def separating_plane_gaps(self, translations):
        """Positive proves whole-body separation along a world coordinate axis.

        A nonpositive value alone does NOT prove mechanical interlocking.
        """
        lo, hi = self.moving_bounds
        return np.maximum(self.fixed_low-(hi+translations), (lo+translations)-self.fixed_high).max(axis=1)


class PrefixFamily:
    def __init__(self, assembly, first_sign, slide_sign, fold_axis, fold_sign, samples=49):
        self.assembly = assembly
        self.first_sign, self.slide_sign = first_sign, slide_sign
        self.fold_axis, self.fold_sign = fold_axis, fold_sign
        self.us = np.linspace(0, 1, samples)
        self.turns = [Rotation.from_rotvec(np.eye(3)[axis][None]*self.us[:, None]*sign*np.pi/2).as_matrix()
                      for axis, sign in ((1, first_sign), (fold_axis, fold_sign))]
        R2 = self.turns[0][-1]
        boxes = [b.boxes/assembly.unit for b in assembly.bodies]
        self.evaluators = [PoseFamily(boxes, self.turns[0]),
                          PoseFamily(boxes, np.repeat(R2[None], samples, axis=0)),
                          PoseFamily(boxes, self.turns[1]@R2)]

    def decode(self, values):
        s, px, pz, down, pa, pb = values
        t1, p2 = np.array([s*self.slide_sign, 0., 0.]), np.array([px, 0., pz])
        t2 = p2+self.turns[0][-1]@(t1-p2)
        t3 = t2-np.array([0., 0., down])
        p4 = np.zeros(3)
        p4[[k for k in range(3) if k != self.fold_axis]] = [pa, pb]
        return t1, p2, t2, t3, p4

    def translations(self, values):
        t1, p2, t2, t3, p4 = self.decode(values)
        return [p2+np.einsum('nij,j->ni', self.turns[0], t1-p2),
                t2+self.us[:, None]*(t3-t2),
                p4+np.einsum('nij,j->ni', self.turns[1], t3-p4)]

    def sampled_metrics(self, values):
        translations = self.translations(values)
        gaps = [e.gaps(t).min() for e, t in zip(self.evaluators, translations)]
        planes = [e.separating_plane_gaps(t).max() for e, t in zip(self.evaluators, translations)]
        return np.array(gaps), np.array(planes)

    def motions(self, values):
        u = self.assembly.unit
        t1, p2, t2, t3, p4 = [v*u for v in self.decode(values)]
        R2 = self.turns[0][-1]
        return [Motion('step_1_relative_slide', 2., np.eye(3), np.zeros(3), t1),
                Motion('step_2_right_quarter_turn_candidate', 3., np.eye(3), t1,
                    axis=np.eye(3)[1], angle_rad=self.first_sign*np.pi/2, pivot=p2),
                Motion('step_3_down_slide_candidate', 2., R2, t2, t3),
                Motion('step_4_up_fold_candidate', 3., R2, t3,
                    axis=np.eye(3)[self.fold_axis], angle_rad=self.fold_sign*np.pi/2, pivot=p4)]


def audit_candidate(assembly, family, values, *, margin_mm=.02):
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    motions = family.motions(values)
    certificates = [certify_motion(collision, m, margin_m=margin_mm*assembly.unit) for m in motions]
    # Independent, denser evaluation of the early-separation exclusion.
    dense = PrefixFamily(assembly, family.first_sign, family.slide_sign, family.fold_axis, family.fold_sign, 361)
    gaps, planes = dense.sampled_metrics(values)
    premature = bool(max(planes) > 1e-8)
    return dict(continuous_certificates=certificates, dense_min_gaps_mm=gaps.tolist(),
        maximum_early_separating_plane_gap_mm=float(max(planes)), premature_full_separation=premature,
        prefix_passed=all(c['passed'] for c in certificates) and not premature,
        full_eight_step_route_verified=False, robot_execution_verified=False)


def boundary_trials(assembly, config, candidates):
    """Keep the closest feasible first three moves and probe an engaged fold.

    This additional search uses a 1 mm nominal AABB overlap buffer to avoid
    optimizing directly on the early-exit boundary. The buffer is a diagnostic
    constraint, not an official puzzle measurement or an interlocking proof.
    """
    for axis in (0, 2):
        for sign in (-1, 1):
            family = PrefixFamily(assembly, -1, 1, axis, sign)
            def objective(values):
                gaps, planes = family.sampled_metrics(values)
                return float(np.sum(np.minimum(gaps-.02, 0.)**2)+np.sum(np.maximum(planes+1., 0.)**2))
            solution = differential_evolution(objective, config['parameter_bounds_nominal_mm'],
                seed=config['seeds'][0], popsize=config['popsize'], maxiter=config['maxiter'], tol=1e-5, polish=True)
            audit = audit_candidate(assembly, family, solution.x)
            row = dict(id=len(candidates), search_phase='one_mm_overlap_buffer_diagnostic',
                first_turn_sign=-1, initial_slide_sign=1, fold_axis='xyz'[axis], fold_sign=sign,
                seed=config['seeds'][0], parameters_nominal_mm=solution.x.tolist(),
                optimizer_objective=float(solution.fun), optimizer_nfev=solution.nfev, **audit)
            candidates.append(row)
            print(f"Boundary probe {'xyz'[axis]}{sign:+d}: prefix={audit['prefix_passed']}, "
                  f"gaps_mm={np.round(audit['dense_min_gaps_mm'], 4)}", flush=True)
    return candidates


def independent_witness(assembly, best):
    """Check the earliest actual overlap in the selected candidate with FCL."""
    collision = CompoundCollision(*(b.boxes for b in assembly.bodies))
    family = PrefixFamily(assembly, best['first_turn_sign'], best['initial_slide_sign'],
                          'xyz'.index(best['fold_axis']), best['fold_sign'])
    for number, motion in enumerate(family.motions(best['parameters_nominal_mm']), 1):
        us = np.linspace(0, 1, 721)
        gaps = np.array([collision.gap(*motion.pose(u)) for u in us])
        bad = np.flatnonzero(gaps < -1e-8)
        if not len(bad):
            continue
        # Use the largest overlap for an independently inspectable witness.
        index = int(np.argmin(gaps))
        R, t = motion.pose(us[index])
        result = dict(step=number, earliest_sampled_overlap_u=float(us[bad[0]]),
            earliest_sampled_overlap_angle_deg=float(us[bad[0]]*90) if motion.axis is not None else None,
            deepest_sample_u=float(us[index]), sat_gap_m=float(gaps[index]),
            witness_rotation=R.tolist(), witness_translation_m=t.tolist(),
            curve_u=us.tolist(), curve_gap_m=gaps.tolist())
        try:
            import fcl
            objects = []
            for body, moving in zip(assembly.bodies, (False, True)):
                model = fcl.BVHModel()
                model.beginModel(len(body.visual.faces), len(body.visual.vertices))
                model.addSubModel(np.asarray(body.visual.vertices), np.asarray(body.visual.faces, dtype=np.int32))
                model.endModel()
                objects.append(fcl.CollisionObject(model, fcl.Transform(R, t) if moving else fcl.Transform()))
            contact = fcl.CollisionResult()
            fcl.collide(*objects, fcl.CollisionRequest(num_max_contacts=100, enable_contact=True), contact)
            result.update(fcl_available=True, triangle_mesh_collision_confirmed=bool(contact.is_collision),
                          fcl_reported_contacts=len(contact.contacts))
        except ImportError:
            result.update(fcl_available=False, triangle_mesh_collision_confirmed=None)
        return result
    return None


def search(output, *, seeds=(97, 131, 173), iterations=350):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output/'result.json').exists():
        raise FileExistsError('Use a new output directory to preserve this trial and its evidence')
    assembly, asset_report = generate_assets(output/'assets', scale=3.)
    # These generous bounds are a declared interpretation of the drawing, not
    # dimensions or pivots asserted to have been supplied by the manufacturer.
    bounds = [(.1, 19.9), (-40., 40.), (-40., 40.), (.1, 40.), (-40., 40.), (-40., 40.)]
    config = dict(scale=3., seeds=list(seeds), optimizer='scipy differential_evolution',
        maxiter=iterations, popsize=18, polish=True, search_samples_per_motion=49,
        dense_review_samples_per_motion=361, nominal_margin_mm=.02,
        parameter_names=['initial_slide_magnitude', 'turn_pivot_x', 'turn_pivot_z',
                         'down_slide', 'fold_pivot_first_orthogonal_coordinate', 'fold_pivot_second_orthogonal_coordinate'],
        parameter_bounds_nominal_mm=bounds, first_turn_axis='assembly y',
        first_turn_signs=[-1, 1], initial_slide_signs=[1, -1], fold_axes=['x', 'z'], fold_signs=[-1, 1],
        interpretation='Prefix uses one translation, fixed-pivot quarter-turn, downward translation, fixed-pivot fold; axes/signs are candidate mappings.',
        source_url=REFERENCE_URL, official_steps_zh=REFERENCE_STEPS,
        geometry_modified=False, no_global_unsolvability_claim=True,
        bounds_are_not_manufacturer_dimensions=True,
        early_separation_guard='Reject any sampled coordinate separating plane before final official step; this is necessary but not sufficient for engagement.')
    (output/'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n')
    candidates = []
    started = time.monotonic()
    for first_sign in (-1, 1):
        for slide_sign in (1, -1):
            for axis in (0, 2):
                for sign in (-1, 1):
                    family = PrefixFamily(assembly, first_sign, slide_sign, axis, sign)
                    for seed in seeds:
                        def objective(values):
                            gaps, planes = family.sampled_metrics(values)
                            return float(np.sum(np.minimum(gaps-.02, 0.)**2)+np.sum(np.maximum(planes, 0.)**2))
                        solution = differential_evolution(objective, bounds, seed=seed, popsize=18,
                            maxiter=iterations, tol=1e-5, polish=True)
                        audit = audit_candidate(assembly, family, solution.x)
                        row = dict(id=len(candidates), first_turn_sign=first_sign, initial_slide_sign=slide_sign,
                            fold_axis='xyz'[axis], fold_sign=sign, seed=seed,
                            parameters_nominal_mm=solution.x.tolist(), optimizer_objective=float(solution.fun),
                            optimizer_nfev=solution.nfev, **audit)
                        candidates.append(row)
                        (output/'candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
                        print(f"Candidate {len(candidates)}/{16*len(seeds)}: y{first_sign:+d}, slide{slide_sign:+d}, "
                              f"{'xyz'[axis]}{sign:+d}, prefix={audit['prefix_passed']}, "
                              f"gaps_mm={np.round(audit['dense_min_gaps_mm'], 4)}, early_exit={audit['premature_full_separation']}", flush=True)
    candidates = boundary_trials(assembly, config, candidates)
    config['additional_boundary_trials'] = dict(count=4, overlap_buffer_nominal_mm=1., first_turn_sign=-1,
        initial_slide_sign=1, seed=seeds[0], purpose='Find a diagnostic fold without optimizing on complete separation')
    (output/'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n')
    (output/'candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    valid = [c for c in candidates if c['prefix_passed']]
    # Select a witness with an actually certified first three moves, so an
    # earlier collision cannot be hidden by displaying only a later failure.
    prefix3 = [c for c in candidates if all(s['passed'] for s in c['continuous_certificates'][:3])
               and not c['premature_full_separation']]
    pool = valid or prefix3 or candidates
    best = min(pool, key=lambda c: c['optimizer_objective'])
    report = dict(task_id='cast_coil', scope='official_guided_prefix_geometry_experiment', config=config,
        tested_candidates=len(candidates), valid_four_move_prefixes=len(valid), best_candidate=best,
        status='prefix_found_remaining_steps_pending' if valid else 'no_valid_prefix_found_in_tested_families',
        official_route_verified=False, full_eight_step_route_verified=False, robot_execution_verified=False,
        formal_demo_generated=False, geometry_modified=False, simulation_steps=0,
        remaining_official_steps=[5, 6, 7, 8], no_global_unsolvability_claim=True,
        independent_collision_witness=independent_witness(assembly, best),
        asset_report=asset_report, wall_seconds=time.monotonic()-started,
        limitations=['No proof of global impossibility; variable-pivot and unsearched paths remain possible.',
                    'No exact manufacturer CAD or metric poses; the coordinate mapping is an explicit hypothesis.',
                    'A prefix alone cannot qualify the official full solution or robot recording.'])
    (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    write_review(output, assembly, report)
    return report


def write_review(output, assembly, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    best = report['best_candidate']
    family = PrefixFamily(assembly, best['first_turn_sign'], best['initial_slide_sign'],
                          'xyz'.index(best['fold_axis']), best['fold_sign'])
    motions = family.motions(best['parameters_nominal_mm'])
    certificates = best['continuous_certificates']
    failed = next((i for i, c in enumerate(certificates) if not c['passed']), None)
    views = [('Initial', np.eye(3), np.zeros(3))]
    for i, motion in enumerate(motions):
        u = certificates[i]['witness']['u'] if i == failed else 1.
        views.append((f"Step {i+1}"+(' collision witness' if i == failed else ''), *motion.pose(u)))
        if i == failed:
            break
    fig = plt.figure(figsize=(4*len(views), 4.8), layout='constrained')
    for i, (label, R, t) in enumerate(views):
        ax = fig.add_subplot(1, len(views), i+1, projection='3d')
        vertices = []
        for body, moving in zip(assembly.bodies, (False, True)):
            mesh = body.visual
            points = ((mesh.vertices@R.T+t) if moving else mesh.vertices)*1000
            vertices.append(points)
            ax.add_collection3d(Poly3DCollection(points[mesh.faces], facecolors='#a88b35' if not moving else '#8794a1',
                edgecolors='#34404a', linewidths=.15, alpha=.8))
        points = np.concatenate(vertices)
        lo, hi = points.min(axis=0), points.max(axis=0)
        center, radius = (lo+hi)/2, max(hi-lo)*.55
        ax.set(xlim=(center[0]-radius, center[0]+radius), ylim=(center[1]-radius, center[1]+radius),
               zlim=(center[2]-radius, center[2]+radius), title=label, xlabel='x (mm)', ylabel='y (mm)', zlabel='z (mm)')
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=24, azim=-65)
    fig.suptitle('Official-guided geometry trial: authored solids, no robot or physical playback')
    fig.savefig(output/'prefix_diagnostic.png', dpi=130)
    plt.close(fig)
    rows = ''.join(f'<tr><td>{i+1}</td><td>{escape(REFERENCE_STEPS[i])}</td><td>{"通过" if c["passed"] else "未通过"}</td>'
                   f'<td>{c["minimum_sample_sat_gap_m"]*1000:.4f}</td></tr>' for i, c in enumerate(certificates))
    witness = report.get('independent_collision_witness')
    witness_html = ''
    if witness:
        fig, ax = plt.subplots(figsize=(9, 4), layout='constrained')
        rotating = witness['earliest_sampled_overlap_angle_deg'] is not None
        ax.plot(np.array(witness['curve_u'])*(90 if rotating else 1), np.array(witness['curve_gap_m'])*1000)
        ax.axhline(0, color='red', linewidth=.8)
        ax.set(xlabel='Candidate fold angle (degrees)' if rotating else 'Normalized motion progress', ylabel='Signed SAT gap (mm)',
               title=f"Step {witness['step']} geometry witness; negative means overlap")
        ax.grid(alpha=.25)
        fig.savefig(output/'collision_curve.png', dpi=140)
        plt.close(fig)
        fcl_status = '确认三角网格相交' if witness.get('triangle_mesh_collision_confirmed') else '没有独立网格碰撞确认'
        location = (f"转过约 {witness['earliest_sampled_overlap_angle_deg']:.3f}°" if rotating else
                    f"移动至 {witness['earliest_sampled_overlap_u']*100:.3f}%")
        witness_html = f'''<section><h2>独立碰撞复核</h2><p>选定候选在第 {witness['step']} 步、{location}
时首次采样到重叠；最深采样 SAT 间隙为 {witness['sat_gap_m']*1000:.3f} mm。
FCL 复核：{fcl_status}。这里是几何重叠量，不是物理解算器的接触穿透测量。</p>
<img src="collision_curve.png" alt="候选翻转的连续角度与采样间隙"></section>'''
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cast Coil · 官方指导解法试验</title><style>body{{max-width:1200px;margin:32px auto;padding:0 20px;font:16px/1.7 system-ui;background:#f4f6f8;color:#263544}}section{{padding:22px;margin:20px 0;background:white;border:1px solid #dbe2e8;border-radius:10px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}img{{width:100%}}a{{color:#12699b}}</style>
<h1>Cast Coil：按官方指导进行几何解法试验</h1>
<section><p>使用现有 3 倍原型、金件固定、银件移动；几何和物理参数未修改。</p>
<p>搜索了 {report['tested_candidates']} 组方向/轴向/随机种子，得到 {report['valid_four_move_prefixes']} 条通过检查的四步前缀。
完整八步及机器人执行均未验收，本次没有生成正式 demo。</p>
<p><a href="result.json">结果</a> · <a href="candidates.json">全部候选及连续碰撞证书</a> · <a href="config.json">边界与搜索参数</a> · <a href="{REFERENCE_URL}">官方八步示意</a></p></section>
<section><h2>当前选定候选</h2><p>下面是几何位姿诊断，失败位姿用于定位碰撞，不能当作已经执行的物理动作。</p>
<img src="prefix_diagnostic.png" alt="官方指导前缀的几何检查"><table><tr><th>步骤</th><th>图示动作</th><th>连续证书</th><th>最小采样 SAT 间隙 mm</th></tr>{rows}</table>
<p>负间隙表示盒体重叠。只展示关键帧不能认证路径，表中连续证书另使用材料点位移上界检查整段运动。</p></section>{witness_html}
<section><h2>适用范围</h2><p>图示没有尺寸和转轴坐标；本次检查的是明确记录的动作解释：平移、固定轴转动、下移、固定轴翻转。
初始滑动方向、面内转动方向及两种出平面轴向都纳入对照。未找到路径不等于证明实物或当前原型完全无解。</p>
<p>另拒绝在第 3 步提前完全退出后再空中转动的候选：它不能充当官方八步复现。
该提前分离检查只是必要条件，通过它也不单独证明仍然互锁。当前尚未执行步骤 5–8 或机器人录制。</p></section></html>'''
    (output/'index.html').write_text(page)
    manifest = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact_manifest.json'}
    (output/'artifact_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('runs/environment-solvability/cast_coil/official_guided_v1'))
    parser.add_argument('--seeds', nargs='+', type=int, default=[97, 131, 173])
    parser.add_argument('--iterations', type=int, default=350)
    args = parser.parse_args()
    report = search(args.output, seeds=args.seeds, iterations=args.iterations)
    print(report['status'], args.output/'index.html')


if __name__ == '__main__':
    main()
