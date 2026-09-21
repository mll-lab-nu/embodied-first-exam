"""Render recorded physical states, explicitly including failed local probes."""
import os
os.environ.setdefault('MUJOCO_GL', 'egl')
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import mujoco
import numpy as np

from .physics import values


def add_camera(parent, name, position, target, fovy):
    position = np.asarray(position)
    z = position-np.asarray(target); z /= np.linalg.norm(z)
    x = np.cross([0, 0, 1], z); x /= np.linalg.norm(x)
    ET.SubElement(parent, 'camera', name=name, pos=values(position),
                  xyaxes=values(np.r_[x, np.cross(z, x)]), fovy=str(fovy))


def render(run, output=None, cameras=('front_oblique','rear_oblique','topdown'), stride=1, width=960, height=720):
    run = Path(run)
    output = Path(output) if output else run/'recording'
    output.mkdir(parents=True, exist_ok=True)
    model_folder = run/'model'
    root = ET.parse(model_folder/'scene.xml').getroot()
    compiler = root.find('compiler')
    if compiler is not None and not Path(compiler.get('meshdir', '.')).is_absolute():
        compiler.set('meshdir', str((model_folder/compiler.get('meshdir', '.')).resolve()))
    world = root.find('worldbody')
    add_camera(world, 'front_oblique', [.45, -.83, .63], [0, -.07, .13], 43)
    add_camera(world, 'rear_oblique', [.40, .65, .62], [0, -.07, .14], 45)
    add_camera(world, 'topdown', [.01, -.08, 1.1], [0, -.075, .07], 40)
    add_camera(world, 'cam_high', [.7, -1.0, .85], [0, -.05, .14], 46)
    add_camera(world, 'cam_low', [.10, -1.05, .45], [0, -.05, .14], 43)
    for side in ('left', 'right'):
        body = root.find(f".//body[@name='{side}/gripper_link']")
        if body is not None:
            add_camera(body, f'cam_{side}_wrist', [.015, -.105, .105], [.24, 0, -.01], 76)
    root.find('visual/global').set('offwidth', str(width))
    root.find('visual/global').set('offheight', str(height))
    xml = ET.tostring(root, encoding='unicode')
    (output/'render_scene.xml').write_text(xml)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    trace = np.load(run/'states.npz')
    options = mujoco.MjvOption(); options.geomgroup[3] = 0
    if np.any(model.flex_dim == 3):
        options.flags[mujoco.mjtVisFlag.mjVIS_FLEXEDGE] = 0
        options.flags[mujoco.mjtVisFlag.mjVIS_FLEXSKIN] = 1
    renderer = mujoco.Renderer(model, height=height, width=width)
    report = json.loads((run/'report.json').read_text())
    fps = report.get('fps', 20)/stride
    with ExitStack() as stack:
        writers = {n: stack.enter_context(imageio.get_writer(output/f'{n}.mp4', fps=fps,
                    codec='libx264', quality=8, macro_block_size=1,
                    ffmpeg_params=['-movflags','+faststart'])) for n in cameras}
        for i in range(0, len(trace['qpos']), stride):
            data.qpos[:] = trace['qpos'][i]; data.qvel[:] = trace['qvel'][i]
            data.time = trace['time_s'][i]
            if 'eq_active' in trace:
                data.eq_active[:] = trace['eq_active'][i]
            if 'eq_data' in trace:
                model.eq_data[:] = trace['eq_data'][i]
                model.eq_obj2id[:] = trace['eq_obj2id'][i]
            mujoco.mj_forward(model, data)
            for name, writer in writers.items():
                renderer.update_scene(data, camera=name, scene_option=options)
                frame = renderer.render(); writer.append_data(frame)
                if i in (0, (len(trace['qpos'])//2//stride)*stride, ((len(trace['qpos'])-1)//stride)*stride):
                    imageio.imwrite(output/f'{name}_{i:04d}.png', frame)
            if i % 100 == 0:
                print(f'{i}/{len(trace["qpos"])}', flush=True)
    renderer.close()
    (output/'render_report.json').write_text(json.dumps(dict(
        source_scope=report['scope'], source_passed=report['passed'], measured_state_replay=True,
        cameras=list(cameras), fps=fps, frames=len(trace['qpos'][::stride]),
        new_physical_execution=False, renderer='MuJoCo EGL',
        visual_options=dict(geomgroup=options.geomgroup.tolist(),flags=options.flags.tolist())), indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--stride', type=int, default=1)
    parser.add_argument('--cameras', nargs='+', default=['front_oblique','rear_oblique','topdown'])
    args = parser.parse_args()
    render(args.run, args.output, args.cameras, args.stride)
