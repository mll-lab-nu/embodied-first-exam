"""Build a fixed-three-tooth 3-by-3 geometry/IK library and audit range corners.

No physical run, robot collision qualification, or dataset sampler is implied.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from html import escape
from itertools import product
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from ._staged_lock_geometry import LockGeometry
from .certificate import certificate
from .inverse_variants import (
    ROOT, SOURCE, ArmIK, analytic_route_check, dump, export_assets,
    infer_geometry, motion_variant,
)

PLAN = ROOT / "assets/tasks/lock_picking/family_space_v1/plan.yaml"
OUTPUT = ROOT / "runs/environment-solvability/lock_picking/family_space_v2"


def candidate(seed, cfg, arm, family, resets, pitch_mm, radius_mm):
    if not np.all(np.isfinite([pitch_mm, radius_mm, *resets])):
        raise ValueError('Non-finite variant parameters')
    if not 65 <= radius_mm <= 95 or pitch_mm > 180:
        raise ValueError('Parameters outside the declared family proposal domain')
    minimum_pitch = 150. * max(1., radius_mm / 80.)
    if pitch_mm < minimum_pitch - 1e-9:
        raise ValueError(f"Visibility spacing requires at least {minimum_pitch:g} mm")
    if len(resets) != family.required_retreats:
        raise ValueError("Retreat count changed family")
    if any(not low <= angle <= high for angle, (low, high) in zip(resets, family.reset_angle_candidate_bounds_deg)):
        raise ValueError('Reset angle outside the declared family proposal domain')
    if family.id == "F2" and resets[1] - resets[0] < family.minimum_reset_difference_deg:
        raise ValueError("F2 requires unequal resets separated by at least 2 degrees")
    states = motion_variant(resets, max(resets) / 2)
    prototype = replace(seed, pitch=pitch_mm / 1000.,
                        grip_offset=(3 * pitch_mm + 45) / 1000.,
                        disc_radius=radius_mm / 1000.)
    g, stops = infer_geometry(prototype, states, cfg.task.rotor_stops)
    proof = certificate(g, stops)
    if proof["minimum_required_decoupling_retreats"] != family.required_retreats:
        raise ValueError("Necessary retreat count changed")
    if not proof["unique_shortest_branch_sequence"]:
        raise ValueError("Shortest branch order changed")
    geom = analytic_route_check(g, stops, states)
    # The fixed frame's innermost radial band stays beyond the entire slot.
    ring_inner = .083 * g.disc_radius / .08
    if ring_inner <= g.slot_radius:
        raise ValueError("Shrinking the outside frame entered the aperture region")
    frames, ik = arm.route(g, states)
    return dict(geometry=asdict(g), rotor_stops=OmegaConf.to_container(stops),
                keyframes=states, certificate=proof, geometry_check=geom, ik=ik,
                frame_aperture_radial_gap_m=ring_inner-g.slot_radius), frames, g, stops


def sector_path(cx, cy, radius, a0, a1):
    p = [(cx + radius * np.sin(np.radians(a)), cy - radius * np.cos(np.radians(a)))
         for a in np.linspace(a0, a1, 20)]
    return f'M {cx:.2f} {cy:.2f} ' + ' '.join(f'L {x:.2f} {y:.2f}' for x, y in p) + ' Z'


def gallery(results):
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1260" height="1120" viewBox="0 0 1260 1120">',
           '<rect width="1260" height="1120" fill="#edf2f5"/>',
           '<style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;fill:#243541}.small{font-size:14px}.label{font-size:18px;font-weight:600}</style>',
           '<text x="24" y="32" class="label">三个动作 family × 三种几何外观代表</text>',
           '<text x="24" y="58" class="small">同一视图保持同一毫米比例、相同材质；左：D1 正视，右：三锁片 + END 侧视。工程示意，非物理录像。</text>']
    for i, r in enumerate(results):
        row, col = divmod(i, 3)
        x, y = 20 + col * 415, 80 + row * 340
        g = r["geometry"]; rad = g["disc_radius"] * 1000; pitch = g["pitch"] * 1000
        svg += [f'<rect x="{x}" y="{y}" width="400" height="322" rx="12" fill="white"/>',
                f'<text x="{x+16}" y="{y+28}" class="label">{escape(r["title"])}</text>',
                f'<text x="{x+16}" y="{y+52}" class="small">D1 {len(g["slots"][0])} 槽 · 必要回退 {r["necessary_retreats"]} 次</text>']
        cx, cy, k = x + 96, y + 153, .60
        outer = rad * 1.4 * k
        svg += [f'<circle cx="{cx}" cy="{cy}" r="{outer}" fill="#98a4aa"/>',
                f'<circle cx="{cx}" cy="{cy}" r="{rad*1.0375*k}" fill="#edf2f5"/>',
                f'<circle cx="{cx}" cy="{cy}" r="{rad*k}" fill="#7547a8"/>',
                f'<circle cx="{cx}" cy="{cy}" r="{g["bore_radius"]*1000*k}" fill="white"/>']
        for s in g["slots"][0]:
            svg.append(f'<path d="{sector_path(cx, cy, 45*k, s-8, s+8)}" fill="white"/>')
        # Show real stop stroke at its ear phase, independent of decorative color.
        lo, hi = r["rotor_stops"][0]["bounds_deg"]
        points = [(cx + .097/.08*rad*k*np.sin(np.radians(a-35)),
                   cy - .097/.08*rad*k*np.cos(np.radians(a-35))) for a in np.linspace(lo, hi, 24)]
        svg.append('<polyline points="'+' '.join(f'{a:.2f},{b:.2f}' for a,b in points)+'" fill="none" stroke="white" stroke-width="5"/>')
        sx, sy, ks = x + 215, y + 162, .27
        svg.append(f'<line x1="{sx-20}" y1="{sy}" x2="{sx+3*pitch*ks+16}" y2="{sy}" stroke="#697c89" stroke-width="3"/>')
        for j, color in enumerate(('#7547a8', '#467997', '#b46547', '#397665')):
            px = sx + j * pitch * ks
            svg.append(f'<rect x="{px-2.4}" y="{sy-rad*ks}" width="4.8" height="{2*rad*ks}" fill="{color}"/>')
            svg.append(f'<text x="{px-7}" y="{sy+rad*ks+18}" font-size="11">{("D"+str(j+1)) if j<3 else "E"}</text>')
        svg.append(f'<text x="{x+16}" y="{y+249}" class="small">盘径 {2*rad:g} mm · 盘距 {pitch:g} mm · 行程 {4*pitch:g} mm</text>')
        svg.append(f'<text x="{x+16}" y="{y+274}" class="small">复位角：'+ '° / '.join(f'{d:g}' for d in r['reset_angles_deg'])+'°</text>')
        svg.append(f'<text x="{x+16}" y="{y+300}" class="small">3 齿 · 几何 / IK 通过；碰撞与物理待验收</text>')
    svg.append('</svg>')
    return '\n'.join(svg)


def review(summary, out):
    rows = []
    for r in summary["representatives"]:
        g = r['geometry']; name = r['id']
        rows.append(f'<tr><td>{r["title"]}</td><td>{2*g["disc_radius"]*1000:g}</td><td>{g["pitch"]*1000:g}</td>'
                    f'<td>{4*g["pitch"]*1000:g}</td><td>{r["ik"]["samples"]}</td>'
                    f'<td><a href="{name}/result.json">证据</a> · <a href="{name}/ik_trace.json">IK</a> · '
                    f'<a href="{name}/inspection_config.yaml">场景</a></td></tr>')
    scan = summary['candidate_range_audit']
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lock-picking · 保持可视间距的 S/M/L</title><style>body{max-width:1260px;margin:32px auto;padding:0 22px;background:#edf2f5;color:#243541;font:16px/1.7 system-ui}section{background:white;border-radius:12px;padding:22px;margin:22px 0}img{width:100%}table{width:100%;border-collapse:collapse}td,th{padding:9px;text-align:left;border-bottom:1px solid #dce3e7}a{color:#076f91}.notice{background:#fff0ca;padding:16px;border-radius:8px}.scroll{overflow:auto}</style>
<h1>Lock-picking：保持可视间距的 S/M/L · v2</h1>
<p><strong>盘距下限 150 mm</strong>，取自当前 spaced_initial 可视性初态。所有 family 共用 S/M/L 间距规则；旧版小于 150 mm 的代表不再属于当前规划。</p>
<p>先改成功种子的回退 / 复位动作，反推槽位和限位；再在 family 内改变盘径、盘距，并为每个实例重新求 IK。</p>
<p class="notice">九个代表均有同轴几何路径、必要回退下界和机械臂 IK 采样证据。新结构的机器人场景碰撞、完整抓取和接触动力学仍未验收。图中为统一比例的结构示意，尚未进行场景遮挡或人工识别率验收。</p>
<section><img src="representatives.svg" alt="九个代表点，按 family 分行、按小标准大分列"></section>
<section><h2>Family 身份与 S/M/L</h2><p>F1：双槽，一次回退。F2：三槽，两次不等角复位。F3：四槽，三次回退。Family 由动作与槽位定义，三个 family 不再靠盘距大小区分。</p>
<p>S / M / L 为 130 / 160 / 190 mm 盘径，盘距分别为 150 / 150 / 180 mm，均保留三齿。S 只缩小外盘；L 随盘径增大而加宽间距。固定外环同步缩放，钥匙凸片与有效槽口尺寸保持不变。</p>
<p>约束 p ≥ 150 mm，且 p/R ≥ 150/80。它保留基准的间距比例，不构成真实相机无遮挡的保证；仍需检查三片锁孔的原始视图。</p></section>
<section><h2>九个代表的精确配对</h2><div class="scroll"><table><tr><th>代表</th><th>盘径 mm</th><th>盘距 mm</th><th>插入行程 mm</th><th>IK 采样</th><th>数据</th></tr>__ROWS__</table></div></section>
<section><h2>随机空间</h2><p>离散 family → 条件采样动作角与几何参数 → 反推孔槽 / 限位 → 重建场景与 IK → 检查 family 身份、几何与机器人 → 独立采样材质 → 输出可复现配对。</p>
<p>三个 family 统一候选盘距 150–180 mm，按盘半径条件筛选；盘径 130–190 mm。F1 复位 28–34°；F2 分别 26–30° / 30–34°，且第二次至少多 2°；F3 每次 23–25°。范围是提案域，每个实例都需要通过筛选。</p>
<p>__SCAN__</p><p>改变颜色、纹理、metallic、roughness 可以保留既有几何与 IK 证据；改变质量、摩擦、盘径、间距、孔槽等不能继承完整物理执行结论。材质风格跨 family 共用，避免颜色与回退次数绑定。</p>
<p><a href="summary.json">全部验证结果</a> · <a href="plan.yaml">机器可读规划</a> · <a href="../../../../docs/develop/tasks/lock_picking_family_space_zh.md">详细空间规划</a></p></section></html>'''
    html = html.replace('__ROWS__', ''.join(rows)).replace('__SCAN__',
        f'动作角与盘距的 {scan["checked"]} 个有效边界组合：{scan["passed"]} 个通过同轴几何、回退下界和 IK，{len(scan["failures"])} 个拒绝。边界检查不构成整个连续域的 IK 或碰撞证书。')
    (out / 'index.html').write_text(html)


def build(output=OUTPUT, audit_corners=True):
    output = Path(output)
    if (output / 'summary.json').exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = OmegaConf.load(PLAN)
    cfg = OmegaConf.load(SOURCE / 'config.yaml')
    seed = LockGeometry.from_config(json.loads((SOURCE / 'layout.json').read_text()))
    arm = ArmIK(cfg, json.loads((SOURCE / 'frames.json').read_text()))
    representatives = []
    for family in plan.families:
        for i, appearance in enumerate(plan.appearance_anchors):
            result, frames, g, stops = candidate(seed, cfg, arm, family,
                list(family.reset_angles_deg), float(family.pitch_anchors_mm[i]),
                float(appearance.disc_radius_mm))
            name = f'{family.id}_{appearance.id}'
            folder = output / name
            folder.mkdir(exist_ok=True)
            result.update(id=name, family_id=family.id, appearance_id=appearance.id,
                title=f'{name} · {appearance.name}', family_name=family.name,
                necessary_retreats=family.required_retreats,
                reset_angles_deg=list(family.reset_angles_deg),
                source_variant=family.source_variant,
                visual_validation='Equal-scale engineering diagram only; rendered scene occlusion and human recognition not yet checked')
            export_assets(g, stops, cfg, folder / 'assets')
            dump(folder / 'result.json', result)
            dump(folder / 'ik_trace.json', dict(scope=result['ik']['scope'], frames=frames))
            dump(folder / 'keyframes.json', result['keyframes'])
            dump(folder / 'layout.json', result['geometry'])
            instance = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
            instance.task.variant = 'aligned_entry'
            instance.task.geometry = result['geometry']
            instance.task.rotor_stops = result['rotor_stops']
            instance.run.inspect_only = True
            instance.run.build_only = False
            instance.run.output = str(folder / 'inspection')
            # Keep the widened initial scene's table, and put each diagnostic
            # aperture camera in its own gap rather than borrowing old positions.
            instance.env.world.table.size = [1.8, 1.4, float(cfg.env.world.table.size[2])]
            for disc in range(3):
                instance.env.cameras[f'disc{disc+1}_face'] = dict(res=[900, 900],
                    pos=[g.disc_x(disc)-.070, g.center_y, g.axis_z],
                    lookat=[g.disc_x(disc), g.center_y, g.axis_z], up=[0, 0, 1],
                    fov=120, near=.001, far=12)
            OmegaConf.save(instance, folder / 'inspection_config.yaml')
            representatives.append(result)
            print(name, 'passed', result['ik']['samples'], 'IK samples', flush=True)
    audit = dict(checked=0, passed=0, failures=[], accepted=[])
    if audit_corners:
        for family in plan.families:
            for resets in product(*family.reset_angle_candidate_bounds_deg):
                if family.id == 'F2' and resets[1]-resets[0] < family.minimum_reset_difference_deg:
                    continue
                for pitch in family.pitch_candidate_bounds_mm:
                    params = dict(family_id=family.id, reset_angles_deg=list(resets), pitch_mm=pitch,
                                  disc_radius_mm=80, scope='Coaxial geometry and sampled arm IK; no robot collisions')
                    audit['checked'] += 1
                    try:
                        result, _, _, _ = candidate(seed, cfg, arm, family, resets, pitch, 80.)
                        audit['passed'] += 1
                        audit['accepted'].append(dict(**params, ik=result['ik']))
                    except (ValueError, RuntimeError, AssertionError) as exc:
                        audit['failures'].append(dict(**params, reason=str(exc)))
                    print('corner', params['family_id'], resets, pitch,
                          audit['passed'], '/', audit['checked'], flush=True)
    summary = dict(task_id='lock_picking', source=str(SOURCE),
        schema_version=2, visibility_baseline_pitch_mm=150,
        representatives=representatives, candidate_range_audit=audit,
        physical_execution_verified=False, robot_scene_collision_verified=False,
        random_physical_dataset_generator_implemented=False)
    dump(output / 'summary.json', summary)
    OmegaConf.save(plan, output / 'plan.yaml')
    (output / 'representatives.svg').write_text(gallery(representatives))
    review(summary, output)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--skip-corner-audit', action='store_true')
    args = parser.parse_args()
    build(args.output, not args.skip_corner_audit)
