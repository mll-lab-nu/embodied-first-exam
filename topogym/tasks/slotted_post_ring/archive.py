"""Keep independent MP4 copies and self-contained physical evidence, without HTML."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from topogym.utils.demo_paths import demo_video_root

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_render_metadata(run, destination):
    """Keep the actual camera configuration with relocated, reloadable assets."""
    folder=destination/'recording_metadata'
    folder.mkdir(exist_ok=True)
    shutil.copy2(run/'recording/render_report.json',folder/'render_report.json')
    tree=ET.parse(run/'recording/render_scene.xml')
    archived=ET.parse(destination/'main/model/scene.xml').getroot()
    for mesh,relocated in zip(tree.getroot().findall('asset/mesh'),archived.findall('asset/mesh'),strict=True):
        for key in ('file','name'):
            if key in relocated.attrib:mesh.set(key,relocated.get(key))
    tree.getroot().find('compiler').set('meshdir','../main/model')
    path=folder/'render_scene.xml'
    tree.write(path,encoding='unicode')
    model=mujoco.MjModel.from_xml_path(str(path))
    original=mujoco.MjModel.from_binary_path(str(destination/'main/model/scene.mjb'))
    np.testing.assert_array_equal(model.qpos0,original.qpos0)
    np.testing.assert_array_equal(model.eq_data,original.eq_data)


def publication_allowed(report):
    """A failed probe or partial episode cannot enter the current demo folder."""
    return bool(report.get('passed') and not report.get('continuation') and
                (report.get('full_process_demo') or report.get('full_robot_demo')))


def archive(run, name, half_step=None, publish=False, variation=None):
    run = Path(run).resolve()
    report = json.loads((run/'report.json').read_text())
    if publish and not publication_allowed(report):
        raise ValueError('Only a passed complete process may be published to demos; '
                         'archive probes and attempts in environment_bootstrap.')
    destination = ROOT/'runs/demo_metadata/slotted_post_ring'/name
    destination.mkdir(parents=True, exist_ok=False)
    render = json.loads((run/'recording/render_report.json').read_text())
    sources = {'main': run}
    if half_step:
        sources['half_step'] = Path(half_step).resolve()
    for label, source in sources.items():
        folder = destination/label
        shutil.copytree(source, folder, ignore=shutil.ignore_patterns('recording'))
        tree = ET.parse(folder/'model/scene.xml')
        root = tree.getroot()
        meshdir = Path(root.find('compiler').get('meshdir', '.'))
        if not meshdir.is_absolute():
            meshdir = source/'model'/meshdir
        for i, mesh in enumerate(root.findall('asset/mesh')):
            if 'file' not in mesh.attrib:
                continue
            path = Path(mesh.get('file'))
            # MuJoCo uses the original file stem when a mesh has no explicit name.
            # Preserve that identifier before relocating the file.
            if 'name' not in mesh.attrib:
                mesh.set('name', path.stem)
            path = path if path.is_absolute() else meshdir/path
            target = folder/'model'/f'asset_{i:03d}{path.suffix}'
            shutil.copy2(path, target)
            mesh.set('file', target.name)
        root.find('compiler').set('meshdir', '.')
        tree.write(folder/'model/scene.xml', encoding='unicode')
        reloaded = mujoco.MjModel.from_xml_path(str(folder/'model/scene.xml'))
        original = mujoco.MjModel.from_binary_path(str(source/'model/scene.mjb'))
        np.testing.assert_allclose(reloaded.qpos0, original.qpos0, rtol=0, atol=0)
        np.testing.assert_allclose(reloaded.eq_data, original.eq_data, rtol=0, atol=0)
    copy_render_metadata(run,destination)
    code = destination/'source_code'
    code.mkdir()
    runtime_source=next((p for p in (run/'runtime_sources',run/'model/runtime_sources') if p.is_dir()),None)
    for path in (runtime_source or Path(__file__).parent).glob('*.py'):
        shutil.copy2(path, code/path.name)
    videos = []
    for camera in render['cameras']:
        source = run/'recording'/f'{camera}.mp4'
        video_root = (demo_video_root(ROOT, 'slotted_post_ring',
                                     variation or report.get('variant') or name) if publish else
                      ROOT/'runs/environment_bootstrap/slotted_post_ring/archived_demos')
        target = video_root/camera/f'{name}_{camera}.mp4'
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha(source) != sha(target):
            raise RuntimeError('Video copy differs from original')
        subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'], check=True, capture_output=True)
        probe = json.loads(subprocess.check_output([
            'ffprobe','-v','error','-count_frames','-select_streams','v:0',
            '-show_entries','stream=width,height,nb_read_frames,r_frame_rate,duration',
            '-of','json',str(target)]))['streams'][0]
        if int(probe['nb_read_frames']) != render['frames']:
            raise RuntimeError('Recording frame count does not match the trace')
        videos.append(dict(camera=camera, path=str(target.relative_to(ROOT)), sha256=sha(target),
                           full_decode=True, **probe))
    if len({(v['nb_read_frames'], v['duration'], v['r_frame_rate']) for v in videos}) != 1:
        raise RuntimeError('Camera videos are not synchronized')
    (destination/'README.md').write_text(
        f"# {name}\n\n"
        f"Scope: `{report['scope']}`. Passed: **{report['passed']}**. "
        f"Complete robot demo: **{report.get('full_robot_demo', False)}**.\n\n"
        "Videos replay measured physical states with MuJoCo EGL; rendering is not a new dynamics run. "
        "See `main/report.json` for assistance, limitations and failed acceptance gates. "
        "The model, assets, trajectory and source snapshot are retained here.\n\n"
        + '\n'.join(f"- [{v['camera']}](../../../../{v['path']})" for v in videos)
        + '\n\nAll videos passed full decoding, synchronized frame-count/duration and SHA-256 checks.\n')
    manifest = dict(task_id='slotted_post_ring', version=name, scope=report['scope'],
                    published_current_demo=publish,
                    passed=report['passed'], full_robot_demo=report.get('full_robot_demo', False),
                    source_directory=str(run), videos=videos, metadata_directory=str(destination.relative_to(ROOT)),
                    source_snapshot_scope='execution-start snapshot' if runtime_source else 'archive-time workspace snapshot; may include later controller edits',
                    xml_asset_paths_relocated=True,
                    renderer_configuration_retained=True,
                    evidence=[dict(path=str(p.relative_to(destination)), sha256=sha(p))
                              for p in sorted(destination.rglob('*')) if p.is_file()])
    (destination/'archive_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    catalog_path=destination.parent/'catalog.json'
    catalog=json.loads(catalog_path.read_text()) if catalog_path.exists() else dict(task_id='slotted_post_ring',versions=[])
    if any(v['version']==name for v in catalog['versions']):
        raise RuntimeError('Archive version already listed in catalog')
    catalog['versions'].append({key:manifest[key] for key in ('version','scope','passed','full_robot_demo','videos')}
                               | dict(metadata=str(destination.relative_to(ROOT))))
    catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
    if publish:
        # Verification and all independent evidence copies are complete before
        # moving the previous version out of the current-demo directory.
        from .curate_demos import curate
        curate(name)
    print(json.dumps(dict(archive=str(destination), videos=videos), indent=2))
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--half-step')
    parser.add_argument('--variation', help='Stable variant ID for the published camera directory')
    parser.add_argument('--publish', action='store_true',
                        help='Publish a passed complete process and retire earlier videos')
    args = parser.parse_args()
    archive(args.run, args.name, args.half_step, args.publish, args.variation)
