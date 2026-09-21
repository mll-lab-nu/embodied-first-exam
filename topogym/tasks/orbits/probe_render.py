"""Render measured local probe states; these videos contain no robot execution."""
import argparse
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np


def render(folder):
    folder=Path(folder)
    model=mujoco.MjModel.from_xml_path(str(folder/'model.xml'))
    data=mujoco.MjData(model)
    with np.load(folder/'probe_trajectory.npz') as archive:
        saved={name:archive[name] for name in archive.files}
    fps=round(1./np.median(np.diff(saved['time_s'])))
    camera=mujoco.MjvCamera()
    camera.lookat[:]=[.12,0,.13];camera.distance=.95;camera.azimuth=115;camera.elevation=-26
    model.vis.global_.offwidth=960;model.vis.global_.offheight=720
    options=mujoco.MjvOption();options.sitegroup[:]=0
    with mujoco.Renderer(model,height=720,width=960) as renderer, imageio.get_writer(
            folder/'probe_measured.mp4',fps=fps,codec='libx264',quality=8,macro_block_size=1) as writer:
        for i,q in enumerate(saved['qpos']):
            data.qpos[:]=q;mujoco.mj_forward(model,data)
            renderer.update_scene(data,camera=camera,scene_option=options)
            rgb=renderer.render();writer.append_data(rgb)
            if i in (0,len(saved['qpos'])-1):imageio.imwrite(folder/f'probe_{i}.png',rgb)
    print(folder/'probe_measured.mp4',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    render(parser.parse_args().folder)
