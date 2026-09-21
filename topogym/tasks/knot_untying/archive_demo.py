"""Archive a completed physical knot execution as independent per-view MP4s."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from .recording import validate_recording


ROOT = Path(__file__).resolve().parents[3]
REQUIRED_CAMERAS = {'cam_high', 'cam_low', 'cam_left_wrist', 'cam_right_wrist'}


def digest(path):
    with path.open('rb') as source:
        result = hashlib.file_digest(source, 'sha256').hexdigest()
    return result


def refresh_catalog():
    folder = ROOT/'runs/demo_metadata/knot_untying'
    entries = []
    for path in sorted(folder.glob('*/archive_manifest.json')):
        manifest = json.loads(path.read_text())
        if not manifest.get('video_files'):
            continue
        entries.append(dict(run_id=path.parent.name, variant=manifest['variant'],
            scope=manifest['scope'], simulated_seconds=manifest['simulated_seconds'],
            manifest=str(path.relative_to(ROOT)), video_files=manifest['video_files']))
    (folder/'catalog.json').write_text(json.dumps(dict(task_id='knot_untying', entries=entries), indent=2)+'\n')
    lines = ['# 解绳结完整物理执行归档', '',
             '视频按视角保存。每次执行的辅助抓持、初始准备位与物理验收范围分别见清单。', '',
             '| 运行 | 实例 | 范围 |', '| --- | --- | --- |']
    lines += [f"| [{entry['run_id']}]({entry['run_id']}/README.md) | {entry['variant']} | {entry['scope']} |"
              for entry in entries]
    (folder/'README.md').write_text('\n'.join(lines)+'\n')


def archive(source, run_id):
    source = Path(source).resolve()
    if not source.is_relative_to(ROOT/'runs'):
        raise ValueError('The original run must be inside this repository runs directory')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}_[a-zA-Z0-9_-]+', run_id):
        raise ValueError('Use a dated run ID, for example 2026-09-19_figure_eight_v1')
    report = json.loads((source/'report.json').read_text())
    rig = json.loads((source/'camera_rig.json').read_text())
    if not (report.get('passed') and report.get('untying_verified')
            and report['actuation']['final_active_constraints'] == 0):
        raise ValueError('Only a verified continuous execution with complete release can be archived as a full demo')
    if not REQUIRED_CAMERAS <= set(rig['cameras']):
        raise ValueError('ALOHA full execution requires its four synchronized views')
    validation_path = source/'video_validation.json'
    validation = json.loads(validation_path.read_text()) if validation_path.exists() else {}
    unchanged = (set(validation.get('metadata_sha256', {})) == {'camera_rig.json', 'frames.json'}
        and set(validation.get('streams', {})) == set(rig['cameras'])
        and all(digest(source/name) == expected for name, expected in validation['metadata_sha256'].items())
        and all(digest(source/f'{name}.mp4') == stream.get('sha256')
                for name, stream in validation['streams'].items()))
    if not unchanged:
        validation = validate_recording(source)
    if not validation['passed']:
        raise ValueError('Original videos failed complete decoding or physical clock validation')
    metadata = ROOT/'runs/demo_metadata/knot_untying'/run_id
    videos = {name: ROOT/'demos/knot_untying'/name/f'{run_id}_{name}.mp4' for name in rig['cameras']}
    if metadata.exists() or any(path.exists() for path in videos.values()):
        raise FileExistsError('An archive already uses this run ID; existing evidence will not be overwritten')
    # Preserve evidence independently. Live checkpoints and videos have their
    # own locations; historical HTML is not republished.
    shutil.copytree(source, metadata, ignore=shutil.ignore_patterns(
        '*.mp4', '*.html', 'partial_*', 'progress.json', 'STOP', '__pycache__'))
    if not (metadata/'scene_assets/aloha').exists():
        raise ValueError('Original run lacks its robot asset snapshot')
    for name, destination in videos.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/f'{name}.mp4', destination)
        if digest(destination) != validation['streams'][name]['sha256']:
            raise RuntimeError(f'Independent video copy hash mismatch: {name}')
    scope = ('同一次连续物理执行：开爪准备位、实体接触后辅助抓持、解结、完全释放并静置；'
             '本轨迹局部检查通过。完整物理套件、持续精细操作和难度分档另行验收。')
    links = {name: str(path.relative_to(ROOT)) for name, path in videos.items()}
    lines = [f'# {run_id}', '', scope, '', f"实例：`{report['variant']}`；物理时长 {report['simulated_seconds']:.3f} s。",
             '', '[物理报告](report.json) · [解析配置](config.yaml) · [录制验证](video_validation.json)', '',
             '| 视角 | 完整 MP4 |', '| --- | --- |']
    lines += [f'| {name} | [视频](../../../../{path}) |' for name, path in links.items()]
    (metadata/'README.md').write_text('\n'.join(lines)+'\n')
    validation.update(archive_video_hashes_match=True,
                      archive_decode_evidence='Original streams fully decoded; independent copies have identical SHA-256')
    (metadata/'archive_validation.json').write_text(json.dumps(validation, indent=2)+'\n')
    files = [p for p in metadata.rglob('*') if p.is_file()]+list(videos.values())
    manifest = dict(task_id='knot_untying', family=report['family'], variant=report['variant'],
        source_directory=str(source.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat(),
        classification='physical_execution_with_grasp_assistance', scope=scope,
        simulated_seconds=report['simulated_seconds'], cameras=rig['cameras'],
        video_layout='one directory per camera', video_files=links,
        untying_verified=True, complete_physics_suite_passed=report['complete_physics_suite_passed'],
        files_sha256={str(p.relative_to(ROOT)): digest(p) for p in sorted(files)})
    (metadata/'archive_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    refresh_catalog()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    result = archive(args.source, args.run_id)
    print(json.dumps(result['video_files'], indent=2))


if __name__ == '__main__':
    main()
