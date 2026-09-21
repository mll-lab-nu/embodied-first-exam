"""Aligned-solving IK preview of a saved instance; zero dynamics steps.

The camera and sampling cadence are fixed across families. This does not depict
pickup/release and must not be classified as a complete physical robot demo.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation

from . import variants as v


def render(instance_path, output, *, stills_only=False):
    import genesis as gs
    from topogym.robot.franka import FrankaPositionIKController
    from .scene import LockPickingSceneBuilder, numpy

    output = v.metadata_path(output)
    cfg, _, instance = v.load_instance(instance_path)
    output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(__file__, output/'render_source.py')
    cfg.env.genesis.backend='cpu'
    cfg.env.renderer.type='rasterizer'
    cfg.env.cameras=OmegaConf.create(dict(front_oblique=dict(
        pos=[1.05,-.8,1.68],lookat=[.05,.15,1.12],up=[0,0,1],fov=55,res=[1280,720],GUI=False)))
    OmegaConf.save(cfg, output/'render_config.yaml',resolve=True)
    gs.init(backend=gs.cpu, precision='32', logging_level='warning', seed=int(cfg.task.seed))
    task=LockPickingSceneBuilder(cfg.env,cfg.task,cfg.robot_control).build(asset_dir=output/'assets')
    robot=task.manifest.get('robot')
    control=FrankaPositionIKController(task.scene,robot,cfg.robot_control)
    camera=task.cameras['front_oblique']
    frames=instance['ik_frames']
    selected=sorted({0,len(frames)-1,*range(0,len(frames),2)})
    if stills_only:
        selected=sorted({0,len(frames)//2,len(frames)-1})
    images=output/'frames'
    images.mkdir()
    peaks=dict(hand_position_m=0.,hand_rotation_rad=0.,robot_qpos_rad=0.,key_position_m=0.,disc_angle_deg=0.)
    records=[]
    start=time.monotonic()
    for number,index in enumerate(selected):
        f=frames[index]
        q=np.asarray(f['robot_qpos'])
        if q.shape != numpy(robot.get_qpos()).shape:
            raise ValueError('Robot qpos layout differs from IK model')
        robot.set_qpos(q,zero_velocity=True)
        tip=[task.layout.tip_x(f['depth']),task.layout.center_y,task.layout.axis_z]
        quat=Rotation.from_euler('x',-f['key_deg'],degrees=True).as_quat()[[3,0,1,2]]
        task.key.set_qpos([*tip,*quat],zero_velocity=True)
        for disc, angle in zip(task.discs,f['disc_deg']):
            disc.set_qpos([np.radians(angle)],zero_velocity=True)
        state=task.state()
        actual_r=Rotation.from_quat(control.hand_quat()[[1,2,3,0]])
        target_r=Rotation.from_quat(np.asarray(f['hand_quat_wxyz'])[[1,2,3,0]])
        errors=dict(hand_position_m=float(np.linalg.norm(control.hand_pos()-f['hand_pos_m'])),
            hand_rotation_rad=float((actual_r.inv()*target_r).magnitude()),
            robot_qpos_rad=float(np.max(np.abs(numpy(robot.get_qpos())-q))),
            key_position_m=float(np.linalg.norm(np.asarray(state['key_tip_pos'])-tip)),
            disc_angle_deg=float(np.max(np.abs(np.asarray(state['disc_deg'])-f['disc_deg']))))
        for name,value in errors.items(): peaks[name]=max(peaks[name],value)
        if errors['hand_position_m']>1e-5 or errors['hand_rotation_rad']>1e-4 or errors['key_position_m']>1e-6 or errors['disc_angle_deg']>1e-4:
            raise ValueError(f'Rendered state differs from IK witness: {errors}')
        task.scene.visualizer.update_visual_states(force_render=True)
        rgb=camera.render(force_render=True)[0]
        Image.fromarray(rgb).save(images/f'{number:05d}.jpg',quality=95)
        records.append(dict(video_frame=number,ik_frame=index,depth=f['depth'],key_deg=f['key_deg'],segment=f['segment']))
        if number%50==0: print(f'FRAME {number}/{len(selected)} elapsed {time.monotonic()-start:.1f}s',flush=True)
    v.save(output/'frame_mapping.json',records)
    if np.array_equal(np.asarray(Image.open(images/'00000.jpg')),np.asarray(Image.open(images/f'{len(selected)-1:05d}.jpg'))):
        raise ValueError('Frozen render')
    # Screen displacement of a full retreat, measured at the grasp point.
    transform=np.asarray(camera.transform)
    points=np.asarray([task.layout.grip_pos(1),task.layout.grip_pos(2)])
    local=(np.linalg.inv(transform)@np.c_[points,np.ones(2)].T).T[:,:3]
    focal=720/(2*np.tan(np.radians(55)/2))
    pixels=local[:,:2]/(-local[:,2,None])*focal
    displacement=float(np.linalg.norm(pixels[1]-pixels[0]))
    if displacement < 30: raise ValueError('Retreat is too small in the selected camera')
    video=output/'front_oblique.mp4'
    fps=24
    if not stills_only:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-framerate',str(fps),
            '-i',str(images/'%05d.jpg'),'-an','-c:v','libx264','-preset','fast','-crf','18',
            '-threads','2','-filter_threads','1','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    report=dict(complete=True,instance_id=instance['instance_id'],family=cfg.task.derived_variant.family_id,
        classification='aligned_solving_kinematic_preview',render_simulation_steps=0,
        physics_qualified=False,counts_as_complete_robotics_demo=False,pickup_release_included=False,
        source_instance=str(Path(instance_path).resolve()),source_instance_sha256=v.sha(Path(instance_path)/'instance.json'),
        cameras=['front_oblique'],camera_transform=transform.tolist(),fps=fps,frames=len(selected),
        duration_s=len(selected)/fps,stills_only=stills_only,max_pose_errors=peaks,
        retreat_screen_displacement_px=displacement,required_retreats=cfg.task.derived_variant.required_retreats,
        cadence='Every second IK frame at 24 fps; at most 2 mm / 1 degree per original IK frame',
        ui_overlays=False,renderer='Genesis CPU rasterizer / Mesa',
        video_sha256=None if stills_only else v.sha(video),frame_mapping_sha256=v.sha(output/'frame_mapping.json'))
    v.save(output/'report.json',report)
    print('FINISHED '+str(output),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stills-only',action='store_true')
    a=p.parse_args()
    render(a.instance,a.output,stills_only=a.stills_only)
