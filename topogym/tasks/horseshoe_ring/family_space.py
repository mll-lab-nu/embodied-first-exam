"""Audit existing IK families and export a gated 3-by-3 variant-space plan.

This is a planning/evidence exporter, not a claim that new geometry has already
been paired with a reachable, supported robot trajectory.
"""
from copy import deepcopy
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil

import numpy as np
from scipy.spatial.distance import cdist
from scipy.spatial.transform import Rotation

from .geometry import band_centerline
from .independent_motion import IndependentWitness
from .shape_neighborhood import ShapeNeighborhood

ROOT=Path(__file__).resolve().parents[3]
TRACES=ROOT/'runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1'
SHAPES=ROOT/'runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1'
OUTPUT=ROOT/'runs/environment-solvability/horseshoe_ring/family_space_plan_v1'
SPEC=ROOT/'assets/tasks/horseshoe_ring/family_space_v1/plan.json'


def hash_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def normalized_trace(folder):
    trace=json.loads((folder/'ik_trace.json').read_text())
    result=json.loads((folder/'result.json').read_text())
    verification=json.loads((folder/'verification.json').read_text())
    motion=json.loads((folder/'robot_motion.json').read_text())
    if not(result['passed'] and verification['passed']):
        raise ValueError(f'{folder.name}: unqualified seed')
    if not(trace['command_sha256']==result['variant_command_sha256']==verification['command_sha256']):
        raise ValueError('Seed command hashes disagree')
    if hashlib.sha256((folder/'robot_motion.json').read_bytes()).hexdigest()!=trace['source_motion_file_sha256']:
        raise ValueError('Trace and saved motion differ')
    if [f['qpos'] for f in trace['frames']]!=[f['qpos'] for f in motion['frames']]:
        raise ValueError('Trace command samples differ from the saved motion')
    points=np.array([[f['tcp_world'][s]['pos_m'] for s in ('left','right')] for f in trace['frames']])
    mount=trace['world_from_robot_mount']
    local=Rotation.from_quat(mount['quat_xyzw']).inv().apply((points-mount['pos_m']).reshape(-1,3)).reshape(points.shape)
    scene=result['scene']
    canonical=Rotation.from_quat(scene['rotation_xyzw']).inv().apply(
        (local-scene['puzzle_origin_in_robot_mount_m']).reshape(-1,3)).reshape(points.shape)/scene['scale_ratio']
    return trace,result,canonical


def arc_sample(points,count=256):
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    keep=np.r_[True,np.diff(lengths)>1e-10]
    if lengths[-1]<=1e-10:
        return np.repeat(points[:1],count,axis=0)
    return np.column_stack([np.interp(np.linspace(0,lengths[-1],count),lengths[keep],points[keep,k]) for k in range(3)])


def route_distance(a,b,threshold_mm=50.):
    # Equal arc-length sampling removes timing/hold-density effects. These are
    # sampled geometric distances, not continuous curve distance certificates.
    distances=cdist(arc_sample(a),arc_sample(b))
    return dict(sampled_hausdorff_mm=float(max(distances.min(0).max(),distances.min(1).max())*1000),
        directed_p95_max_mm=float(max(np.percentile(distances.min(0),95),np.percentile(distances.min(1),95))*1000),
        maximum_directed_fraction_above_threshold=float(max(np.mean(distances.min(0)*1000>threshold_mm),np.mean(distances.min(1)*1000>threshold_mm))),
        threshold_mm=threshold_mm,
        points_per_curve=256)


def build():
    spec=json.loads(SPEC.read_text())
    if len(spec['families'])!=3 or len(spec['appearances'])!=3 or len({f['id'] for f in spec['families']})!=3:
        raise ValueError('This exporter requires three distinct families and three appearances')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(SPEC,OUTPUT/'plan.json')
    shutil.copyfile(ROOT/'docs/develop/tasks/horseshoe_ring_family_space_zh.md',OUTPUT/'README.md')
    seeds={};routes={};pairs=[];rows=[]
    phases=[('right_support_transfer','双臂交接支撑','左臂换抓圆环',1),
            ('left_ring_transfer','左臂换抓圆环','调整圆环并脱出',0)]
    for family in spec['families']:
        name=family['id'];trace,result,points=normalized_trace(TRACES/family['ik_seed'])
        seeds[name]=(trace,result);bounds={p['name']:p['frame'] for p in trace['phases']}
        routes[name]={label:points[bounds[start]:bounds[end],side] for label,start,end,side in phases}
    for i,a in enumerate(spec['families']):
        for b in spec['families'][i+1:]:
            differences={phase[0]:route_distance(routes[a['id']][phase[0]],routes[b['id']][phase[0]],spec['visual_acceptance']['macro_route_p95_mm']) for phase in phases}
            pairs.append(dict(families=[a['id'],b['id']],phases=differences,
                proposed_route_separation_gate_passed=any(v['directed_p95_max_mm']>=spec['visual_acceptance']['macro_route_p95_mm']
                    and v['maximum_directed_fraction_above_threshold']>=spec['visual_acceptance']['macro_minimum_distinct_route_fraction'] for v in differences.values())))
    shape_cache={}
    for family in spec['families']:
        trace,result=seeds[family['id']]
        for appearance in spec['appearances']:
            identifier=family['id']+'_'+appearance['id'];folder=OUTPUT/identifier;folder.mkdir(exist_ok=True)
            baseline=appearance['id']=='R'
            if baseline:
                template=json.loads((TRACES/family['ik_seed']/'template.json').read_text())
                scale=result['scene']['scene_scale']
                source=str((TRACES/family['ik_seed']).relative_to(ROOT))
                source_certificate=TRACES/family['ik_seed']/'geometry_certificate.json'
                if json.loads(source_certificate.read_text())!=result['geometry'] or hash_json(template)!=result['geometry']['template_sha256']:
                    raise ValueError('Seed geometry and certificate disagree')
                certificate=dict(passed=True,scope=result['geometry']['scope'],
                    source_directory=source,source_geometry_certificate_repository_path=str(source_certificate.relative_to(ROOT)),
                    source_geometry_certificate_file_sha256=hashlib.sha256(source_certificate.read_bytes()).hexdigest(),
                    source_robot_trace_file_sha256=hashlib.sha256((TRACES/family['ik_seed']/'ik_trace.json').read_bytes()).hexdigest(),
                    template_sha256=hash_json(template),scale=scale,
                    minimum_clearance_lower_bound_m=result['geometry']['minimum_clearance_lower_bound_m'],
                    goal=result['geometry']['goal'],
                    interpolation=result['geometry']['interpolation'],
                    robot_ik_paired=True,robot_continuous_collision_verified=False,dynamic_execution_verified=False,
                    note='Source-relative paths are resolved in source_directory; retain its dense witness and common transforms')
            else:
                ref=appearance['geometry_reference']
                if ref not in shape_cache:
                    source_dir=SHAPES/'references'/ref
                    path=json.loads((source_dir/'body_poses.json').read_text())
                    cert=json.loads((source_dir/'certificate.json').read_text())
                    ShapeNeighborhood(path,cert)  # hashes, COMs, scale, pair bounds, implementation
                    shape_cache[ref]=(path,cert,IndependentWitness(path['template'],path['scale']))
                path,cert,original=shape_cache[ref]
                template=deepcopy(path['template'])
                factor=result['scene']['scale_ratio']*appearance['relative_scale']
                scale=path['scale']*factor;changed=IndependentWitness(template,scale)
                error=max(float(np.abs(new.vertices-old.vertices*factor).max()) for old,new in zip(original.meshes,changed.meshes))
                if error>1e-10:
                    raise ValueError('New collision covers are not the declared positive similarity')
                source=str((SHAPES/'references'/ref).relative_to(ROOT))
                certificate=dict(passed=True,scope='Independent-body geometric witness under a constant positive uniform scale',
                    template_sha256=hash_json(template),
                    source_template_sha256=cert['template_sha256'],source_frames_sha256=cert['frames_sha256'],
                    source_certificate_sha256=hash_json(cert),source_directory=source,
                    scale=scale,source_scale=path['scale'],scale_ratio=factor,collision_cover_max_error_m=error,
                    minimum_clearance_lower_bound_m=cert['minimum_clearance_lower_bound_m']*factor,
                    source_goal_separation_m=cert['goal']['separation_m'],goal_separation_m=cert['goal']['separation_m']*factor,
                    interpolation='Scale source COM samples and all mesh lengths by the constant ratio; retain source shortest-SLERP rotations',
                    initial_topology_preserved=True,robot_ik_paired=False,robot_execution_verified=False,
                    dynamic_execution_verified=False,
                    note='Geometry is solved; no pairing to the chosen macro-family IK is implied')
            template_file=folder/'template.json';template_file.write_text(json.dumps(template,indent=2)+'\n')
            (folder/'scene_seed.json').write_text(json.dumps(dict(template='template.json',scene_scale=scale,
                desired_puzzle_origin_in_robot_mount_m=result['scene']['puzzle_origin_in_robot_mount_m'],
                desired_initial_rotation_xyzw=result['scene']['rotation_xyzw'],
                nominal_layout_only=not baseline,robot_pairing_verified=baseline,
                note='For new shapes this is an initial placement target; fit/check the final scene against newly solved grasp anchors'),indent=2)+'\n')
            (folder/'geometry_evidence.json').write_text(json.dumps(certificate,indent=2)+'\n')
            ring=template['target_ring'];radii=ring.get('centerline_radii',[ring['centerline_radius']]*2)
            row=dict(id=identifier,family=family['id'],appearance=appearance['id'],name_zh=appearance['name_zh'],
                geometry_reference=source,scene_scale=scale,ellipse_aspect=max(radii)/min(radii),
                relative_scale=appearance['relative_scale'],chain_semimajor_template_mm=template['chain']['link_radii'][0],
                geometric_solvability_verified=True,minimum_clearance_mm=certificate['minimum_clearance_lower_bound_m']*1000,
                corresponding_ik_seed=str((TRACES/family['ik_seed']/'ik_trace.json').relative_to(ROOT)),
                target_ik_id=identifier+'_ik_v2',target_ik_trace=None,
                existing_seed_ik_and_scene_paired=baseline,new_pairing_status='existing_seed_only' if baseline else 'requires_grasp_and_ik_replanning',
                family_visual_gate_passed=all(p['proposed_route_separation_gate_passed'] for p in pairs if family['id'] in p['families']),
                physical_execution_verified=False)
            (folder/'representative.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');rows.append(row)
    audit=dict(normalization='Remove each seed initial scene translation, yaw and scale; preserve robot hand identity',
        sampling='256 points per stage, uniformly spaced by TCP arc length; comparison removes hold-time/retiming effects',
        pairs=pairs,appearance_checks=appearance_checks(rows))
    report=dict(schema_version=1,scope='3x3 plan with geometry evidence; 6 new robot/shape pairings pending',
        references=rows,audit=audit,existing_paired_robot_seeds=3,new_geometry_paired_robot_traces=0,
        nine_pair_sampler_enabled=False,reason='B/C macro separation and six new shape-to-IK pairings are not yet qualified')
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    draw_routes(routes,spec);draw_appearances(rows)
    write_page(spec,report)
    return report


def appearance_checks(rows):
    checks=[]
    for family in {r['family'] for r in rows}:
        group=[r for r in rows if r['family']==family]
        for i,a in enumerate(group):
            for b in group[i+1:]:
                scale_difference=max(a['relative_scale'],b['relative_scale'])/min(a['relative_scale'],b['relative_scale'])-1
                aspect_difference=abs(a['ellipse_aspect']-b['ellipse_aspect'])
                checks.append(dict(pair=[a['id'],b['id']],uniform_scale_difference=scale_difference,
                    ellipse_aspect_difference=aspect_difference,design_gate_passed=scale_difference>=.15 or aspect_difference>=.12,
                    scope='Design dimensions; fixed-camera human visibility remains to be reviewed'))
    return checks


def draw_routes(routes,spec):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(13,8),layout='constrained')
    for family in spec['families']:
        for row,key in enumerate(['right_support_transfer','left_ring_transfer']):
            points=routes[family['id']][key]*1000
            for ax,(a,b) in zip(axes[row],[(0,1),(0,2),(1,2)]):
                ax.plot(points[:,a],points[:,b],label=family['id'],lw=1.5)
                ax.set(xlabel='XYZ'[a]+' / mm',ylabel='XYZ'[b]+' / mm',title=key.replace('_',' '))
                ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend()
    fig.savefig(OUTPUT/'ik_routes.svg');fig.savefig(OUTPUT/'ik_routes.png',dpi=150);plt.close(fig)


def draw_appearances(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,3,figsize=(13,10),layout='constrained')
    for ax,row in zip(axes.flat,rows):
        t=json.loads((OUTPUT/row['id']/'template.json').read_text());scale=row['scene_scale'];h=t['horseshoe']
        alpha=np.radians(h['mouth_half_angle_deg']);points=band_centerline(h,scale,np.linspace(alpha,2*np.pi-alpha,401))
        ax.plot(points[:,0]-95,points[:,1],color='#627f98',lw=5)
        ring=t['target_ring'];radii=np.asarray(ring.get('centerline_radii',[ring['centerline_radius']]*2))*scale
        theta=np.linspace(0,2*np.pi,256)
        ax.plot(95+radii[0]*np.cos(theta),radii[1]*np.sin(theta),color='#cb921d',lw=2.5)
        chain=np.asarray(t['chain']['link_radii'])*scale
        ax.plot(chain[0]*np.cos(theta),chain[1]*np.sin(theta)-102,color='#62727c',lw=2)
        ax.set(xlim=(-185,185),ylim=(-125,95),title=f'{row["id"]} | e={row["ellipse_aspect"]:.2f} | size x{row["relative_scale"]:.2f}',xlabel='Scene mm; same scale in every panel')
        ax.set_aspect('equal');ax.grid(alpha=.13)
    fig.suptitle('Component centerlines, not assembly poses | blue: shoe, gold: target, grey: chain',fontsize=12)
    fig.savefig(OUTPUT/'representatives.svg');fig.savefig(OUTPUT/'representatives.png',dpi=160);plt.close(fig)


def write_page(spec,report):
    rows=[]
    for r in report['references']:
        seed=ROOT/r['corresponding_ik_seed']
        url=os.path.relpath(seed,OUTPUT)
        status='已有配对 IK 种子' if r['existing_seed_ik_and_scene_paired'] else '几何有解；新 IK 配对待验证'
        rows.append(f'<tr><td>{r["id"]}</td><td>{escape(r["name_zh"])}</td><td>{status}</td><td><a href="{url}">IK 种子</a> · <a href="{r["id"]}/geometry_evidence.json">几何证据</a></td></tr>')
    families=''.join(f'<li><b>{f["id"]} · {escape(f["name_zh"])}</b>：{escape(f["signature_zh"])}</li>' for f in spec['families'])
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe · 3 × 3 变体空间规划</title>
<style>body{max-width:1180px;margin:30px auto;padding:0 20px;background:#f2f5f7;color:#253d50;font:16px/1.7 system-ui}section{padding:22px;background:white;border-radius:12px;margin:20px 0}img{width:100%}a{color:#096992}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:9px;text-align:left}.notice{border-left:4px solid #d9a446;padding-left:14px}.scroll{overflow:auto}</style>
<h1>一个 IK family 轴 × 三类外观代表</h1>
<p>每个 family 保留自己的操作路线特征；每个外观实例拥有与几何匹配的 IK trace。类内允许调整抓点、姿态和换抓路径。</p>
<p class="notice">本页是规划与证据分层。三个原始机器人种子已有完整运动学预演；六个新外观配对的几何有解，但尚无已验证的对应 IK。F2/F3 还需增强路线区分度。不能把本页当成已经完成九个机器人 demo。</p>
<section><h2>宏观 family</h2><ul>'''+families+'''</ul><a href="ik_routes.svg"><img src="ik_routes.png" alt="去掉整体位姿和尺度差异后的双臂换抓轨迹"></a>
<p>同一尺度和坐标下比较换抓路线，并用等弧长重采样消除播放速度影响。F1 与其他两族的区别明显；F2/F3 尚未达到拟定的 50 mm 路线区分门槛。机器人基座和相机变化不计为 family 差异。</p></section>
<section><h2>九个代表槽位</h2><p>每行一个 IK family：R 为现有经典圆环基准，U 为放大 18% 的宽体 U 形原型，E 为 1.15 椭圆比的相位调整型。下图是零件中心线对照，不是装配姿态；所有格子采用同一毫米比例。</p>
<a href="representatives.svg"><img src="representatives.png" alt="三个 family 各三种外观代表的零件轮廓对照"></a><div class="scroll"><table><tr><th>代表</th><th>外观特征</th><th>当前证据</th><th>文件</th></tr>'''+''.join(rows)+'''</table></div></section>
<section><h2>生成机制与放行条件</h2><p>先选 family，再选该 family 内已经通过 IK 配对的外观锚点，联合采样形状、椭圆比、链长和抓点，调整 IK 并检查连续几何、手物约束、机器人碰撞与外观区分度。最后采样颜色、粗糙度和光照。每一个层级都保留来源与状态。</p>
<p>当前 3 × 3 生成器处于规划状态；不能自动把已有 42 个几何样本分到三个 IK family，就声称完成机器人变体。</p>
<p><a href="README.md">详细规划与验收顺序</a> · <a href="plan.json">机器可读规划</a> · <a href="report.json">本次审计与九个代表的状态</a> · <a href="../coupled_shape_variants_v1/index.html">已验证的完整几何回放</a> · <a href="../trace_scene_variants_v1/index.html">三个原有 IK demo</a></p></section></html>'''
    (OUTPUT/'index.html').write_text(page)


if __name__=='__main__':
    result=build()
    print(json.dumps(dict(representatives=len(result['references']),audit=result['audit']),ensure_ascii=False,indent=2))
