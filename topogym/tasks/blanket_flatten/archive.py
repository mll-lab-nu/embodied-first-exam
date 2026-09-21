"""Independently retain a verified three-view blanket robot demonstration."""
from topogym.utils.demo_paths import demo_video_root

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from omegaconf import OmegaConf

from .render_execution import CAMERAS

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(report, render, stability):
    restoration = report.get('initial_state_restoration')
    if restoration:
        stable_restoration = stability.get('initial_state_restoration') or {}
        if any(restoration.get(key) != stable_restoration.get(key)
               for key in ('source_sha256', 'source_frame', 'initial_velocity')):
            raise ValueError('Independent stability used a different selected initial shape or velocity')
    if report.get('motion_robot_clearance_checks', 0) and report.get('minimum_motion_robot_clearance_m', 0) < .008:
        raise ValueError('Released arm recenter motion violates blanket clearance')
    if not (report['full_robot_task_verified'] and report['success'] and report['initialization_accepted']
            and not report['active_grasp_particles'] and report['releases'] > 0
            and report['physics_steps'] > 0 and not report['live_particle_position_writes']
            and report.get('initial_robot_clearance_checks', 0) > 0
            and report.get('minimum_initial_robot_clearance_m', 0) >= .008
            and not report['live_robot_position_writes_after_home']
            and report['final_evidence']['window_seconds'] >= .5-1e-8
            and bool(report['final_evidence']['gates'])
            and all(report['final_evidence']['gates'].values())):
        raise ValueError('Physical run is incomplete, unreleased, or failed final acceptance')
    start_frame = int(render.get('source_start_frame', 0))
    actions = [e for e in report.get('events', []) if e['phase'].startswith('pull_')]
    complete_range = start_frame == 0 or bool(actions and
        render.get('recording_start_s', float('inf')) <= actions[0]['seconds'] and
        abs(render.get('recording_end_s', -1)-report['simulated_seconds']) < 1e-8)
    stride = 1
    if 'source_fps' in render:
        if render['fps'] <= 0 or render['source_fps'] != report['fps'] or render['source_fps'] % render['fps']:
            raise ValueError('Invalid source/video frame rates')
        stride = render['source_fps']//render['fps']
    expected = sorted(set([*range(start_frame, render['source_frames'], stride), render['source_frames']-1]))
    complete_samples = render.get('source_frame_indices', expected) == expected
    if not (render['source_success'] and not render['preview_only'] and complete_range
            and render.get('arm_clearance_review_passed', False)
            and start_frame >= 0 and complete_samples and render['frames'] == len(expected)
            and render['source_frames'] == report['frame_count']
            and set(render['cameras']) == set(CAMERAS)
            and render['maximum_particle_reconstruction_error_m'] <= 1e-6
            and render['maximum_joint_reconstruction_error'] <= 1e-6):
        raise ValueError('Three-view rendering does not match the complete physical trace')
    if not (stability['success'] and stability['mode'] == 'stability'
            and stability['worst']['nonfinite_steps'] == 0
            and stability.get('initial_robot_clearance_checks', 0) > 0
            and stability.get('minimum_initial_robot_clearance_m', 0) >= .008
            and stability['final_evidence'].get('passive_seconds', 0) >= 10
            and stability['final_evidence'].get('window_seconds', 0) >= .4-1e-8
            and bool(stability['final_evidence']['gates'])
            and all(stability['final_evidence']['gates'].values())):
        raise ValueError('Independent passive stability check missing or failed')


def qualify_mesh_review(review, frame_count):
    if not (review.get('frames') == frame_count
            and len(review.get('counts', [])) == frame_count
            and review.get('maximum_intersecting_faces') == 0
            and review.get('intersecting_frames') == []
            and all(count == 0 for count in review['counts'])):
        raise ValueError('Cloth self-intersection review is missing, partial, or failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--stability', type=Path, required=True)
    parser.add_argument('--run-id', default='single_arm_v1')
    args = parser.parse_args()
    source, stability_dir = args.source.resolve(), args.stability.resolve()
    if not (source/'review.json').exists() or not json.loads((source/'review.json').read_text()).get('approved_for_archive', False):
        raise ValueError('Visual review is missing or rejected this execution')
    report = json.loads((source/'report.json').read_text())
    render = json.loads((source/'render/render_report.json').read_text())
    stability = json.loads((stability_dir/'report.json').read_text())
    qualify(report, render, stability)
    for directory, physical in ((source, report), (stability_dir, stability)):
        qualify_mesh_review(json.loads((directory/'self_intersection_review.json').read_text()), physical['frame_count'])
    cfg, stable_cfg = OmegaConf.load(source/'config.yaml'), OmegaConf.load(stability_dir/'config.yaml')
    for path in ('task.variant', 'task.origin_xy_m', 'task.preparation', 'task.initial_state_recording', 'task.initialization', 'task.success', 'task.geometry', 'task.material', 'task.stretch_iterations', 'task.table_friction',
                 'task.robot_gravity_compensation', 'robot_control.home', 'env.sim', 'env.genesis.precision'):
        if OmegaConf.select(cfg, path) != OmegaConf.select(stable_cfg, path):
            raise ValueError(f'Stability used different physics: {path}')
    for name, digest in render['source_sha256'].items():
        if sha(source/name) != digest:
            raise ValueError(f'Render source was altered: {name}')
    if sha(source/'render/render_config.yaml') != render['render_config_sha256']:
        raise ValueError('Recorded camera configuration was altered')
    if render.get('render_source_sha256') and sha(source/'render/render_execution_source.py') != render['render_source_sha256']:
        raise ValueError('Recorded rendering source was altered')
    now = datetime.now(timezone.utc)
    prefix = f'{now:%Y-%m-%d}_{args.run_id}'
    metadata = ROOT/'runs/demo_metadata/blanket_flatten'/prefix
    videos = demo_video_root(ROOT, "blanket_flatten", cfg.task.variant)
    if metadata.exists():
        raise FileExistsError(metadata)
    videos.mkdir(parents=True, exist_ok=True)
    checks = {}
    for name in CAMERAS:
        path = source/'render'/f'{name}.mp4'
        detail = json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','stream=nb_frames,duration,width,height','-of','json',str(path)],
            capture_output=True, text=True, check=True).stdout)['streams'][0]
        if int(detail['nb_frames']) != render['frames']:
            raise ValueError(f'Wrong frame count: {name}')
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True)
        checks[name] = detail
    if len({(v['nb_frames'],v['duration']) for v in checks.values()}) != 1:
        raise ValueError('Videos are not synchronized')
    metadata.mkdir(parents=True)
    for name in ('config.yaml','report.json','physical_trace.npz'):
        shutil.copy2(source/name, metadata/name)
    if (source/'selected_initial_state.npz').exists():
        shutil.copy2(source/'selected_initial_state.npz', metadata/'selected_initial_state.npz')
        reproduction = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
        reproduction.task.initial_state_recording.path = str((metadata/'selected_initial_state.npz').relative_to(ROOT))
        reproduction.task.initial_state_recording.frame = 0
        reproduction.run.output = f'runs/environment_bootstrap/blanket_flatten/reproduce_{prefix}'
        OmegaConf.save(reproduction, metadata/'reproduction_config.yaml', resolve=True)
    if (source/'review.json').exists():
        shutil.copy2(source/'review.json', metadata/'review.json')
    for name in ('assets', 'source_snapshot'):
        if (source/name).exists():
            shutil.copytree(source/name, metadata/name)
    for path in source.glob('prepared_*.npz'):
        shutil.copy2(path, metadata/path.name)
    for name in ('self_intersection_review.json', 'twist_review.json', 'robot_motion_review.json'):
        if (source/name).exists():
            shutil.copy2(source/name, metadata/name)
    shutil.copytree(stability_dir, metadata/'stability', ignore=shutil.ignore_patterns('*.html'))
    shutil.copy2(source/'render/render_report.json', metadata/'render_report.json')
    shutil.copy2(source/'render/render_config.yaml', metadata/'render_config.yaml')
    for name in ('robot_motion_review.json', 'video_verification.json', 'render_execution_source.py'):
        if (source/'render'/name).exists():
            shutil.copy2(source/'render'/name, metadata/name)
    stills = metadata/'stills'; stills.mkdir()
    for path in (source/'render').glob('*.jpg'):
        shutil.copy2(path, stills/path.name)
    video_records = {}
    for name in CAMERAS:
        dest = videos/name/f'{prefix}_{name}.mp4'
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise FileExistsError(dest)
        shutil.copy2(source/'render'/f'{name}.mp4', dest)
        if sha(dest) != sha(source/'render'/f'{name}.mp4'):
            raise ValueError('Video copy hash mismatch')
        video_records[name] = dict(path=os.path.relpath(dest, metadata), sha256=sha(dest), **checks[name])
    links = '\n'.join(f'- [{name}]({record["path"]})' for name, record in video_records.items())
    (metadata/'README.md').write_text('被子展平：单臂完整流程\n\n'+links+'\n\n'+
        '视频从稳定初态开始，连续呈现抓角、展开、释放、撤手和自由静置；源轨迹保留本次运行的全部初始化与动作。\n'+
        '布料与机器人不启用 PBD 碰撞耦合；双指几何接近检查后使用局部辅助抓持。三视角来自实测粒子和全部关节状态。\n\n'+
        '[执行报告](report.json) · [独立稳定性](stability/report.json) · [渲染核验](render_report.json)\n')
    if report.get('initial_state_restoration'):
        with (metadata/'README.md').open('a') as stream:
            stream.write('\n初态取自用户选定视频保存的落桌形状，验证材料索引和视觉绑定后，在步进前一次性设置位置并将速度归零；随后重新静置验证。这是新的连续物理运行，不是原轨迹的动力学续接。动作过程中不直接写入布料位置。\n'
                         '独立的初态快照位于 selected_initial_state.npz；reproduction_config.yaml 使用归档内快照，可从仓库根目录复现，另设新的 run.output。\n')
    manifest = dict(task_id='blanket_flatten', instance=prefix, source_directory=str(source),
        archived_at_utc=now.isoformat(), classification='physical_execution_with_grasp_assistance',
        counts_as_complete_robotics_demo=True, recording_range_s=[render.get('recording_start_s', 0), report['simulated_seconds']],
        cameras=list(CAMERAS), videos=video_records,
        metadata_sha256={str(p.relative_to(metadata)):sha(p) for p in metadata.rglob('*') if p.is_file()})
    (metadata/'archive_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    hub = ROOT/'runs/demo_metadata'
    catalog = json.loads((hub/'catalog.json').read_text())
    entry = dict(task_id='blanket_flatten',
        title='被子展平 · 麻花初态单臂完整流程' if report.get('initial_state_restoration') else '被子展平 · 单臂完整物理流程',
        variant=str(cfg.task.variant),
        classification=manifest['classification'], counts_as_complete_robotics_demo=True,
        duration_s=float(next(iter(checks.values()))['duration']), cameras=list(CAMERAS),
        scope=f'从已验收的落桌形状开始，双指接近后局部辅助抓持，经历 {report["releases"]} 次抓持和释放，最终撤手后自由静置验收；真实物理状态同步回放。',
        source_directory=str(source), directory=str(metadata.relative_to(hub)),
        readme=str((metadata/'README.md').relative_to(hub)), archived_at_utc=now.isoformat(),
        video_files={name:os.path.relpath(metadata/record['path'],hub) for name,record in video_records.items()})
    catalog['entries'].append(entry)
    catalog['complete_robotics_demo_count'] = sum(bool(e.get('counts_as_complete_robotics_demo')) for e in catalog['entries'])
    catalog['archived_at_utc'] = now.isoformat()
    (hub/'catalog.json').write_text(json.dumps(catalog,indent=2,ensure_ascii=False)+'\n')
    with (hub/'README.md').open('a') as stream:
        stream.write('\n被子展平完整动作：'+ ' · '.join(
            f'[{name}]({entry["video_files"][name]})' for name in CAMERAS)+
            f'。{prefix}；局部辅助抓持，释放撤手后通过展平验收。\n')
    print(metadata/'README.md')


if __name__ == '__main__':
    main()
