"""Archive three clean, complete lock videos under demos/lock_picking/<camera>."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from .render_physical_trace import ROOT, CAMERAS, physics_signature, save, sha


def probe(path):
    data = json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames',
        '-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate,nb_read_frames,duration',
        '-of','json',str(path)]))['streams'][0]
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)
    return data


def archive(source, run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Use a simple run id')
    source=Path(source).resolve()
    report=json.loads((source/'report.json').read_text())
    if not report['complete'] or report['preview_only'] or not report['source_success']:
        raise ValueError('Only a complete rendering of a successful source may be archived')
    if report['rendered_frame_count']!=report['source_frame_count'] or report['cameras']!=list(CAMERAS):
        raise ValueError('Incomplete camera or frame coverage')
    camera_records = [json.loads(line) for line in (source/'camera_poses.jsonl').read_text().splitlines()]
    if len(camera_records) != report['source_frame_count'] or any(
            r['frame'] != i or abs(r['time_s']-i/report['fps']) > 1e-10 or
            set(r['cameras']) != set(CAMERAS) for i, r in enumerate(camera_records)):
        raise ValueError('Camera records do not cover the full synchronized timeline')
    for name,digest in report['source_sha256'].items():
        if sha(source/'source_evidence'/name)!=digest:
            raise ValueError('Source evidence changed: '+name)
    if not json.loads((source/'physics_equivalence.json').read_text())['passed']:
        raise ValueError('Physical geometry was not preserved')
    for name in CAMERAS:
        if sha(source/f'{name}.mp4')!=report['video_sha256'][name]:
            raise ValueError('Rendered video changed: '+name)
    checks={n:probe(source/f'{n}.mp4') for n in CAMERAS}
    for n,data in checks.items():
        numerator,denominator=map(int,data['avg_frame_rate'].split('/'))
        if int(data['nb_read_frames'])!=report['source_frame_count'] or numerator/denominator!=report['fps']:
            raise ValueError('Decoded frame timeline mismatch: '+n)
        if abs(float(data['duration'])-report['duration_s'])>1e-4:
            raise ValueError('Video duration mismatch: '+n)
    metadata=ROOT/'runs/demo_metadata/lock_picking'/run_id
    if metadata.exists():
        raise FileExistsError(metadata)
    video_paths={n:ROOT/'demos/lock_picking'/n/f'{run_id}_{n}.mp4' for n in CAMERAS}
    if any(p.exists() for p in video_paths.values()):
        raise FileExistsError('An output video already exists')
    metadata.mkdir(parents=True)
    for folder in ('source_evidence','assets'):
        shutil.copytree(source/folder,metadata/folder)
    if (source/'render_attempts').is_dir():
        shutil.copytree(source/'render_attempts', metadata/'render_attempts')
    physical_assets = Path(report['source_directory'])/'assets'
    shutil.copytree(physical_assets, metadata/'source_evidence/assets')
    for name in ('report.json','physics_equivalence.json','render_config.yaml','render_source.py','camera_poses.jsonl'):
        shutil.copy2(source/name,metadata/name)
    shutil.copy2(__file__,metadata/'archive_source.py')
    impl=metadata/'implementation';impl.mkdir()
    for name in ('scene.py','_staged_lock_geometry.py','_staged_lock_limits.py','_staged_lock_ring.py','_aperture_outline.py'):
        shutil.copy2(Path(__file__).with_name(name),impl/name)
    for name in ('gripper.py', 'franka.py'):
        shutil.copy2(ROOT/'topogym/robot'/name, impl/('robot_'+name))
    # Standalone copied assets must not retain absolute links into a scratch run.
    for asset_root, original_root in ((metadata/'assets', source/'assets'),
            (metadata/'source_evidence/assets', physical_assets)):
        for p in asset_root.rglob('*.urdf'):
            tree=ET.parse(p)
            for mesh in tree.findall('.//mesh'):
                prior=Path(mesh.get('filename'))
                if prior.is_absolute():
                    target=asset_root/prior.relative_to(original_root)
                    if not target.is_file():raise FileNotFoundError(target)
                    mesh.set('filename',os.path.relpath(target,p.parent))
            tree.write(p,encoding='unicode')
        for p in asset_root.rglob('aperture_outline.json'):
            doc=json.loads(p.read_text())
            for key in ('source_visual','outlined_visual'):
                original=Path(doc[key]);new=asset_root/original.relative_to(original_root)
                doc[key]=os.path.relpath(new,p.parent)
            save(p,doc)
    for p in (metadata/'source_evidence/assets').rglob('*.urdf'):
        equivalent = metadata/'assets'/p.relative_to(metadata/'source_evidence/assets')
        if physics_signature(p) != physics_signature(equivalent):
            raise ValueError('Archived collision geometry differs from the physical source: '+p.name)
    videos={}
    for n,destination in video_paths.items():
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/f'{n}.mp4',destination)
        digest=sha(destination)
        if digest!=sha(source/f'{n}.mp4'):raise ValueError('Copy mismatch: '+n)
        videos[n]=dict(path=os.path.relpath(destination,metadata),sha256=digest,**checks[n])
        shutil.copy2(source/f'frame_00000_{n}.jpg',metadata/f'initial_{n}.jpg')
        shutil.copy2(source/f'frame_{report["source_frame_count"]-1:05d}_{n}.jpg',metadata/f'final_{n}.jpg')
    phase_starts = {}
    for frame in (metadata/'source_evidence/states.jsonl').read_text().splitlines():
        state = json.loads(frame)
        phase_starts.setdefault(state['stage'], state['step'] * report['source_simulation_dt'])
    save(metadata/'phase_starts.json', phase_starts)
    landmarks = [('抓取', 'Close fingers on handle'),
        ('第一次回退', 'Retreat one - disengage second disc'),
        ('第二次回退', 'Retreat two - disengage second disc'),
        ('换抓', 'Open fingers for regrasp'),
        ('终点插入', 'Insert final lock hole'), ('松爪', 'Release key at goal')]
    navigation = ''.join(f'<button onclick="seekAll({phase_starts[phase]})">{label} · {phase_starts[phase]:.2f}s</button>'
                         for label, phase in landmarks)
    scope=('150 mm 盘距、三齿、两次必要回退的标准变体；第一片紫色，四个锁孔黄色描边。'
           '三路同时间轴、原速完整过程，无文字、状态栏或画中画。来自 attempt06 成功物理执行的实测状态重渲染；'
           '含接触触发的辅助抓持，最终松爪并静置。机械臂、钥匙、锁片使用实测姿态；'
           '夹爪被动连杆按记录开合量重建，未重跑动力学，不作为新的完整物理执行验收。')
    readme=f'''# 开锁 · 新外观标准变体 · 三视角完整过程

{scope}

每路 {report['duration_s']:.2f} 秒、{report['fps']:g} fps、{report['source_frame_count']} 帧，覆盖抓取、两次回退换槽、中途换抓、最终插入和松爪。

'''+ '\n'.join(f'- [{n}]({v["path"]})' for n,v in videos.items())+f'''

机械臂、钥匙和锁片姿态直接取自已成功的物理执行，原记录见 [source_evidence/](source_evidence/)。旧日志没有保存全部 Robotiq 被动关节角，因此连杆采用标定重建，并非逐关节精确回放；误差见 [report.json](report.json) 的 `max_reconstruction_errors`。原执行 `success=true`、零几何错误步数、最终解除辅助抓持；这不等于本次重新执行了动力学。

视频由 Genesis CPU Rasterizer 渲染。原执行与当前模型的碰撞网格、质量、惯量、关节和任务配置一致，见 [physics_equivalence.json](physics_equivalence.json)。三路完整解码及帧数检查见 [archive_validation.json](archive_validation.json)。

复现入口：`python -m topogym.tasks.lock_picking.render_physical_trace --output <新目录>`；归档入口：`python -m topogym.tasks.lock_picking.demo_archive --source <渲染目录> --run-id <新名称>`。CPU 无显示渲染使用 `PYOPENGL_PLATFORM=egl EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1`。
'''
    (metadata/'README.md').write_text(readme)
    cards=''.join(f'<section><h2>{n}</h2><video controls preload="metadata" poster="initial_{n}.jpg" src="{html.escape(v["path"])}"></video><p><a href="{html.escape(v["path"])}">下载 {n}</a></p></section>' for n,v in videos.items())
    (metadata/'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>开锁 · 标准变体完整过程</title><style>body{max-width:1250px;margin:28px auto;padding:0 20px;background:#edf2f5;color:#253541;font:16px/1.7 system-ui}section{background:white;padding:18px;margin:18px 0;border-radius:12px}video{width:100%;max-height:720px}a{color:#126d93}button{padding:9px 18px;margin:5px}</style><h1>开锁 · 新外观标准变体 · 三视角完整过程</h1><p>'''+html.escape(scope)+f'''</p><p>每路 {report['duration_s']:.2f} 秒 · {report['fps']:g} fps · {report['source_frame_count']} 帧</p><button onclick="syncPlay()">三路同步播放</button><button onclick="document.querySelectorAll('video').forEach(v=>v.pause())">全部暂停</button><p><a href="README.md">来源与说明</a> · <a href="archive_manifest.json">归档清单</a> · <a href="archive_validation.json">视频检查</a></p>'''+cards+'''<script>function syncPlay(){const vs=[...document.querySelectorAll('video')];const t=vs[0].currentTime;vs.forEach(v=>{v.currentTime=t;v.play()})}</script></html>''')
    page = metadata/'index.html'
    page.write_text(page.read_text().replace(cards, navigation+cards).replace(
        '<script>function syncPlay()',
        "<script>function seekAll(t){document.querySelectorAll('video').forEach(v=>{v.currentTime=t})}function syncPlay()"))
    now=datetime.now(timezone.utc).isoformat()
    manifest=dict(task_id='lock_picking',run_id=run_id,variant=report['variant'],classification=report['classification'],
        counts_as_complete_robotics_demo=False,counts_as_complete_process_demo=True,
        source_physics_success=True,new_physics_execution=False,scope=scope,
        duration_s=report['duration_s'],recording_range_s=report['recording_range_s'],cameras=list(CAMERAS),
        source_directory=str(source.relative_to(ROOT)),physical_source_directory=report['source_directory'],
        videos=videos,ui_overlays=False,archived_at_utc=now)
    save(metadata/'archive_validation.json',dict(passed=True,full_decode=True,frame_count=report['source_frame_count'],
        duration_s=report['duration_s'],synchronized=True,checks=checks,physics_equivalent=True,
        limitation='Visual reconstruction of passive gripper joints; not a new physical execution qualification'))
    manifest['metadata_sha256']={str(p.relative_to(metadata)):sha(p) for p in sorted(metadata.rglob('*')) if p.is_file()}
    save(metadata/'archive_manifest.json',manifest)
    catalog_path=ROOT/'runs/demo_metadata/catalog.json'
    catalog=json.loads(catalog_path.read_text())
    entry={k:manifest[k] for k in ('task_id','variant','classification','counts_as_complete_robotics_demo',
        'counts_as_complete_process_demo','source_physics_success','new_physics_execution','scope','duration_s','cameras','archived_at_utc')}
    entry.update(title='开锁 · 新外观标准变体 · 三视角完整过程',directory=f'lock_picking/{run_id}',
        index=f'lock_picking/{run_id}/index.html',video_directory='../../demos/lock_picking',
        video_files={n:os.path.relpath(p,catalog_path.parent) for n,p in video_paths.items()},ui_overlays=False)
    catalog['entries'].append(entry)
    catalog['excluded']=[e for e in catalog['excluded'] if e['task_id']!='lock_picking']
    catalog.setdefault('task_video_layout',{})['lock_picking']=dict(organization='one MP4 per camera; standard variant',
        video_directory='../../demos/lock_picking',metadata_directory='lock_picking',cameras=list(CAMERAS))
    catalog['updated_at_utc']=now
    save(catalog_path,catalog)
    index_path=catalog_path.parent/'index.html';text=index_path.read_text()
    text=re.sub(r'<tr><td>lock_picking</td><td>.*?</td></tr>','',text)
    section=f'<section><h2><a href="lock_picking/{run_id}/index.html">{entry["title"]}</a></h2><p>{html.escape(scope)}</p><p>{report["duration_s"]:.2f} 秒 · 三路同步 · <a href="../../demos/lock_picking/">按视角视频目录</a></p></section>'
    text=text.replace('</body>',section+'</body>') if '</body>' in text else text+section
    index_path.write_text(text)
    readme_path=catalog_path.parent/'README.md'
    text=readme_path.read_text()
    text='\n'.join(line for line in text.splitlines() if not ('lock_picking' in line and 'agentview' in line and ('一路' in line or '三视角' in line)))+'\n'
    text+=f'\n开锁新外观标准变体的[三路完整过程](lock_picking/{run_id}/index.html)已放入 `demos/lock_picking/<camera>/`，每路 {report["duration_s"]:.2f} 秒。源物理执行成功；本次按实测状态重渲染，夹爪被动连杆根据开合量重建，未计为新的完整物理执行验收。\n'
    readme_path.write_text(text)
    print(metadata,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    a=p.parse_args();archive(a.source,a.run_id)


if __name__=='__main__':main()
