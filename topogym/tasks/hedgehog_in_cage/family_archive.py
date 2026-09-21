"""Independent archives and a comparison page for three physical cage families."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from html import escape
import json
from pathlib import Path
import re
import shutil
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from .family_motion import OUTPUT,FAMILIES
from .family_runtime import admitted
from .inverse_window import ROOT,SEED,save,sha
from .inverse_archive import verify_recording,Links

META=ROOT/'runs/demo_metadata/hedgehog_in_cage'
VIDEO=ROOT/'runs/demos/hedgehog_in_cage'
DATE='2026-09-17'
NAMES=dict(oblique_gate='A · 单斜窗绕出',staggered_gates='B · 双门槛换层',helical_guide='C · 螺旋导向')
DESCRIPTIONS=dict(oblique_gate='侧移幅度参数 10 mm，配合 −4° 倾斜，沿反推的偏置窗口取出。',staggered_gates='先通过笼体出口，再改变高度和横向位置，越过外侧第二道门槛挡板。',helical_guide='出口朝向逐步转动 36°，转动与推进同步，穿过扭转笼条形成的通道。')
SCOPE='固定笼、单臂、S2 预抓取起点；双指接触后辅助抓持，完整取出、落桌、解除辅助、张爪撤离并自由静置。视频来自同一次连续物理执行的实际状态。'


def read(p):return json.loads(Path(p).read_text())
def require(ok,message):
    if not ok:raise ValueError(message)
def run_id(f):return f'{DATE}_family_{chr(97+FAMILIES.index(f))}_{f}_v1'


def verify_physics(folder):
    trace,cert=admitted(folder)
    robot=read(folder/'robot_audit.json')
    require(robot['passed'] and robot['certificate_sha256']==sha(folder/'certificate.json'),'Stale robot audit')
    runs=[];configs=[]
    for directory,substeps in [('physics',10),('physics_substeps20',20)]:
        p=folder/directory;report,audit,rows=[read(p/n) for n in ('report.json','audit.json','trajectory.json')]
        require(report['passed'] and report['complete'] and report['grasp_released'] and audit['passed'],'Incomplete physical run')
        module=report.get('runner_module','family_runtime.py')
        require(module in ('family_runtime.py','family_guided_runtime.py'),'Unknown physical runtime')
        require(report['runner_sha256']==sha(Path(__file__).with_name(module)),'Physical runtime source changed')
        if module=='family_guided_runtime.py':
            require(report['runtime_dependency_sha256']=={'family_runtime.py':sha(Path(__file__).with_name('family_runtime.py'))},'Guided runtime dependency changed')
        require(report['dt']==.005 and report['substeps']==substeps,'Unexpected physical step')
        require(report['asset_manifest_sha256']==cert['asset_manifest_sha256'] and report['ik_sha256']==cert['ik_sha256'],'Different physical instance')
        require(report['contact_gate']['simultaneous_contact'] and not report['live_object_pose_overwrites'] and not report['live_robot_pose_overwrites'],'Invalid execution contract')
        require(rows[0]['physics_step']==0 and rows[-1]['physics_step']==report['physics_steps'] and rows[-1]['phase']=='final_settle','Incomplete trace')
        for name,digest in audit['source_sha256'].items():require(sha(p/name)==digest,'Stale actual-state check')
        cfg=OmegaConf.to_container(OmegaConf.load(p/'config.yaml'),resolve=True);cfg['env']['sim']['substeps']=0;configs.append(cfg)
        runs.append((report,audit,rows))
    require(configs[0]==configs[1],'Configurations differ beyond physics substeps')
    require(runs[0][0]['runner_sha256']==runs[1][0]['runner_sha256'],'Different physical controllers')
    a,b=[r[2] for r in runs]
    require(np.allclose(a[0]['robot_qpos'],b[0]['robot_qpos'],atol=1e-10),'Different initial robot state')
    require(np.allclose(a[0]['ball_position_m'],b[0]['ball_position_m'],atol=1e-10),'Different initial object state')
    delta=np.linalg.norm(np.array(a[-1]['ball_position_m'])-b[-1]['ball_position_m'])
    rotation=(Rotation.from_quat(a[-1]['ball_quaternion_xyzw'])*Rotation.from_quat(b[-1]['ball_quaternion_xyzw']).inv()).magnitude()
    comparison=dict(passed=True,inner_steps_s=[.0005,.00025],backend=runs[0][0].get('backend','cuda'),final_position_difference_m=float(delta),
        final_orientation_difference_deg=float(np.rad2deg(rotation)),duration_difference_s=abs(a[-1]['time_s']-b[-1]['time_s']),
        report_sha256={d:sha(folder/d/'report.json') for d in ['physics','physics_substeps20']},scope='Two complete executions; not a parameter robustness sweep')
    save(folder/'time_step_comparison.json',comparison)
    return runs[0],comparison


CSS='''body{max-width:1320px;margin:30px auto;padding:0 24px;background:#edf2f1;color:#243b38;font:16px/1.7 system-ui}section{background:white;padding:24px;border-radius:14px;margin:22px 0}video,img{width:100%;border-radius:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}figure{margin:0}button{padding:9px 14px;margin:4px;cursor:pointer;border:0;border-radius:5px;background:#dcece8}a{color:#176d68}.note{padding:14px;background:#fff2d9;border-radius:8px}table{width:100%;border-collapse:collapse}td,th{padding:8px;text-align:left;border-bottom:1px solid #dde5e8}'''
PHASES=dict(pregrasp_contact='预抓取起点',hold_grasp='接触后抓持',align_with_verified_path='对齐路径',initial_adjustment='初始调整',approach_oblique_gate='接近斜窗',lateral_oblique_turn='侧移配合倾斜',approach_first_gate='接近第一收口',first_gate_turn='通过第一收口',change_level_between_gates='两道门之间换层',align_second_gate='对齐第二收口',pass_second_gate='通过第二收口',approach_helical_guide='接近螺旋通道',coupled_turn_and_advance='同步转动与推进',withdraw='完整退出',carry_to_release_location='搬运',orient_for_placement='调整落桌姿态',lower_to_table='降低至桌面',release='松爪并撤离',final_settle='自由静置')


def player(folder,f,record,comparison):
    rid=run_id(f);cert=read(folder/'certificate.json');audit=read(folder/'physics/audit.json')
    url=lambda n:f'../../../demos/hedgehog_in_cage/{rid}_{n}.mp4'
    views=''.join(f'<figure><figcaption>{n}</figcaption><video data-sync controls preload="metadata" poster="recording/pregrasp_contact_{n}.jpg" src="{url(n)}"></video></figure>' for n in ('agentview','front_oblique','wrist'))
    phases=''.join(f'<button onclick="seek({p["time_s"]})">{PHASES.get(p["name"],p["name"])} · {p["time_s"]:.1f}s</button>' for p in record['phases'])
    controls=''.join(f'<tr><td>{escape(name)}</td><td>{"发生结构碰撞" if c["collision_found"] else "未发现碰撞"}</td></tr>' for name,c in cert['finite_controls'].items())
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>刺球出笼 {NAMES[f]}</title><style>{CSS}</style>
<h1>刺球出笼 · {NAMES[f]}</h1><p>{DESCRIPTIONS[f]} {record['duration_s']:.2f} 秒 · 三路同步视角。</p><p class="note">{SCOPE}</p>
<section><h2>完整物理流程</h2><video controls preload="metadata" src="{url('three_views')}"></video><p>下方是三个独立视角；阶段按钮同时定位合成视频和独立视角。</p><button onclick="playAll()">三路同步播放</button><button onclick="pauseAll()">全部暂停</button><button onclick="seek(0)">回到起点</button><div class="grid">{views}</div><p>{phases}</p></section>
<section><h2>验证</h2><p>规划物体路径连续间隙下界 {cert['continuous_clearance_lower_bound_m']*1000:.3f} mm；实际保存状态插值的下界 {audit['continuous_interpolation_clearance_lower_bound_m']*1000:.3f} mm。0.5 ms / 0.25 ms 两种物理子步均完成执行和释放静置，两次末态位置差 {comparison['final_position_difference_m']*1000:.4f} mm。</p><table><tr><th>有限对照路线</th><th>结果</th></tr>{controls}</table><p>这些对照用于辨别本实例的动作约束，尚未证明全局唯一解。视频以真实物理状态离线渲染，未用规划轨迹动画替代物理执行。物理后端：{comparison['backend']}；渲染器：{record.get('renderer_type','Nyx')}。</p>
<p><a href="certificate.json">几何证书与对照</a> · <a href="robot_audit.json">机器人检查</a> · <a href="physics/report.json">物理报告</a> · <a href="physics/audit.json">实际状态检查</a> · <a href="time_step_comparison.json">子步复测</a> · <a href="recording/recording_report.json">逐帧来源</a> · <a href="archive_manifest.json">归档清单</a> · <a href="../{DATE}_family_representatives_v1/index.html">三个 family 对照</a> · <a href="../../index.html">全部 Demo</a></p></section>
<script>const v=[...document.querySelectorAll('[data-sync]')],overview=document.querySelector('video:not([data-sync])');function pauseAll(){{[overview,...v].forEach(x=>x.pause())}}function seek(t){{pauseAll();[overview,...v].forEach(x=>x.currentTime=t)}}function playAll(){{overview.pause();const t=v[0].currentTime;v.forEach(x=>{{x.currentTime=t;x.play()}})}}v[0].addEventListener('timeupdate',()=>{{if(!v[0].paused)v.slice(1).forEach(x=>{{if(Math.abs(x.currentTime-v[0].currentTime)>.15)x.currentTime=v[0].currentTime}})}});</script></html>'''


def archive_one(folder):
    folder=Path(folder);f=read(folder/'ik_before_geometry.json')['family'];rid=run_id(f)
    physical,comparison=verify_physics(folder);record,videos=verify_recording(folder,physical)
    target=META/rid;require(not target.exists(),'Preserve existing archive')
    for v in videos:
        v['file']=f'{rid}_{v["camera"]}.mp4';require(not (VIDEO/v['file']).exists(),'Preserve existing video')
    shutil.copytree(folder,target,ignore=shutil.ignore_patterns('attempts','*.mp4','*.log','sweep.npz','index.html','ik_failure.json'))
    provenance=target/'provenance';provenance.mkdir();seed=provenance/'seed';seed.mkdir()
    for name in ['family_motion.py','family_geometry.py','family_runtime.py','family_guided_runtime.py','family_review.py','family_archive.py','inverse_window.py','inverse_runtime.py','inverse_archive.py','geometry.py','plan_escape.py','stability.py']:
        shutil.copy2(Path(__file__).with_name(name),provenance/name)
    for name in ['escape_upper.json','robot_escape_plan.json','robot_escape_plan.npz','robot_release_plan.json','extraction_config.yaml']:
        shutil.copy2(SEED/name,seed/name)
    shutil.copy2(ROOT/'docs/develop/tasks/hedgehog_in_cage_zh.md',provenance/'family_demos_zh.md')
    for name in ('check_hedgehog_family.py','check_hedgehog_inverse.py'):
        shutil.copy2(ROOT/'tests'/name,provenance/name)
    VIDEO.mkdir(parents=True,exist_ok=True)
    for v in videos:
        source=folder/'recording'/(v['camera']+'.mp4');dest=VIDEO/v['file'];shutil.copy2(source,dest)
        require(dest.stat().st_ino!=source.stat().st_ino and not dest.is_symlink() and sha(dest)==v['sha256'],'Independent video copy failed')
        v['path']='../../../demos/hedgehog_in_cage/'+v['file']
    (target/'index.html').write_text(player(target,f,record,comparison))
    save(target/'delivery_checks.json',dict(passed=True,full_decode=True,synchronized_frames=True,exact_actual_state_source=True,independent_copies=True,
        geometry_and_robot_checks=True,two_complete_physical_executions=True,omitted_regenerable_cache=['sweep.npz']))
    files={str(p.relative_to(target)):sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
    manifest=dict(schema_version=1,task_id='hedgehog_in_cage',family=f,instance_id=rid,title=NAMES[f],
        classification='physical_execution_with_grasp_assistance',counts_as_complete_robotics_demo=True,
        source_directory=str(folder.relative_to(ROOT)),archived_at_utc=datetime.now(timezone.utc).isoformat(),scope=SCOPE,
        duration_s=record['duration_s'],cameras=['agentview','front_oblique','wrist'],videos=videos,metadata_sha256=files,
        pregrasp_start=True,assisted_grasp=True,grasp_released=True,unique_solution_proven=False)
    save(target/'archive_manifest.json',manifest)
    return dict(task_id='hedgehog_in_cage',title='刺球出笼 · '+NAMES[f],variant=f,classification=manifest['classification'],
        counts_as_complete_robotics_demo=True,duration_s=record['duration_s'],cameras=manifest['cameras'],scope=SCOPE,
        source_directory=manifest['source_directory'],directory='hedgehog_in_cage/'+rid,index='hedgehog_in_cage/'+rid+'/index.html',
        archived_at_utc=manifest['archived_at_utc'],video_directory='../demos/hedgehog_in_cage',
        video_files={v['camera']+'.mp4':'../demos/hedgehog_in_cage/'+v['file'] for v in videos})


def comparison_page(output,entries):
    target=META/f'{DATE}_family_representatives_v1';require(not target.exists(),'Preserve comparison archive');target.mkdir(parents=True)
    for name in ['cross_family_checks.json','previous_archive_checks.json','cage_comparison.png','motion_comparison.png']:
        shutil.copy2(output/name,target/name)
    blocks=[]
    for f,e in zip(FAMILIES,entries):
        url='../../../demos/hedgehog_in_cage/'+run_id(f)+'_front_oblique.mp4'
        blocks.append(f'<figure><h2>{NAMES[f]}</h2><video controls preload="metadata" src="{url}" poster="../{run_id(f)}/recording/pregrasp_contact_front_oblique.jpg"></video><p>{DESCRIPTIONS[f]}</p><p>{e["duration_s"]:.2f} 秒 · <a href="../{run_id(f)}/index.html">打开完整三视角</a></p></figure>')
    (target/'index.html').write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>刺球出笼 · 三个 Family 完整 Demo</title><style>{CSS}</style><h1>刺球出笼 · 三个动作 Family</h1><p class="note">{SCOPE}</p><section><button onclick="start()">从起点同时播放</button><button onclick="videos.forEach(v=>v.pause())">全部暂停</button><p>各视频保持原执行速度，流程长度不同；同步起播不代表阶段同时发生。</p><div class="grid">{''.join(blocks)}</div></section><section><h2>同尺度结构与路径对照</h2><img src="cage_comparison.png"><img src="motion_comparison.png"><p>图示为实际导出的几何与球心轨迹，姿态变化见视频与各实例的 IK 文件。</p><p><a href="cross_family_checks.json">三条完整路径在三种结构中的交叉检查</a> · <a href="../../index.html">全部 Demo</a></p><p>已通过有限跨 family 路线对照；未证明全局唯一解。</p></section><script>const videos=[...document.querySelectorAll('video')];function start(){{videos.forEach(v=>{{v.currentTime=0;v.play()}})}}</script></html>''')
    save(target/'archive_manifest.json',dict(task_id='hedgehog_in_cage',classification='physical_family_comparison',counts_as_complete_robotics_demo=False,
        source_archives=[e['directory'] for e in entries],metadata_sha256={p.name:sha(p) for p in target.iterdir() if p.is_file()}))
    return target


def register(entries,comparison):
    base=ROOT/'runs/demo_metadata';catalog=read(base/'catalog.json')
    existing={e.get('directory') for e in catalog['entries']}
    require(not any(e['directory'] in existing for e in entries),'Duplicate catalog entry')
    catalog['entries'].extend(entries);catalog['complete_robotics_demo_count']=sum(bool(e.get('counts_as_complete_robotics_demo')) for e in catalog['entries'])
    catalog['archived_at_utc']=datetime.now(timezone.utc).isoformat()
    comparison_rel=str(comparison.relative_to(base))
    catalog.setdefault('comparisons',[]).append(dict(task_id='hedgehog_in_cage',index=comparison_rel+'/index.html',classification='physical_family_comparison',counts_as_complete_robotics_demo=False,source_archives=[e['directory'] for e in entries]))
    save(base/'catalog.json',catalog)
    page=(base/'index.html').read_text();sections=''
    for e in entries:
        sections+=f'<section><h2><a href="{e["index"]}">{e["title"]}</a></h2><p><strong>完整物理执行 · 辅助抓持并最终释放</strong> · {e["duration_s"]:.2f} 秒 · 三路同步视角</p><p>{SCOPE}</p><a href="{e["index"]}">打开播放页</a> · <a href="{comparison_rel}/index.html">三个 family 对照</a></section>'
    marker='<section><h2>本次暂未收录'
    page=page.replace(marker,sections+marker,1) if marker in page else page.replace('</body>',sections+'</body>',1)
    page=re.sub(r'当前保留 \d+ 份完整物理执行',f'当前保留 {catalog["complete_robotics_demo_count"]} 份完整物理执行',page,count=1);(base/'index.html').write_text(page)
    readme=(base/'README.md').read_text();pos=readme.index('\n\n',readme.index('| 环境 |'))
    rows='\n'.join(f'| {e["title"]} | [打开]({e["index"]}) | 4 | {SCOPE} |' for e in entries)
    (base/'README.md').write_text(readme[:pos]+'\n'+rows+readme[pos:])


def archive_all(output=OUTPUT):
    output=Path(output);cross=read(output/'cross_family_checks.json');require(cross['passed'],'Cross-family check failed')
    for f,hashes in cross['source_sha256'].items():
        require(hashes['ik']==sha(output/f/'ik_before_geometry.json') and hashes['assets']==sha(output/f/'assets/sha256.json'),'Stale cross-family check')
    # Preflight every execution before creating any final archive.
    for f in FAMILIES:verify_physics(output/f)
    witness=read(output/'staggered_gates/second_gate_witness.json')
    require(witness['passed'] and witness['certificate_sha256']==sha(output/'staggered_gates/certificate.json'),'Missing outer-gate collision witness')
    entries=[archive_one(output/f) for f in FAMILIES];comparison=comparison_page(output,entries)
    for folder in [*(META/run_id(f) for f in FAMILIES),comparison]:
        parser=Links();parser.feed((folder/'index.html').read_text())
        require(all((folder/p).exists() for p in parser.paths),'Broken playback link')
        manifest=read(folder/'archive_manifest.json')
        for name,digest in manifest['metadata_sha256'].items():require(sha(folder/name)==digest,'Metadata copy changed')
    register(entries,comparison)
    relative='../../../demo_metadata/hedgehog_in_cage/'+comparison.name+'/index.html'
    (output/'index.html').write_text(f'<!doctype html><meta charset="utf-8"><a href="{relative}">三个 Family 完整物理 Demo</a>')
    print(json.dumps(dict(passed=True,index=str(comparison/'index.html'),entries=entries),ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUTPUT);archive_all(p.parse_args().output)
