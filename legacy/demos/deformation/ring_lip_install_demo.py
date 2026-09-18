"""Closed-ring lip installation: FEM/IPC experiment and synchronized IK replay.

The FEM run uses ONE local soft grasp at a time. Previously installed material
has no pins or goal attraction. Replay adds the shared Panda/Robotiq and a slim
installation tool; arm/tool contact dynamics are not claimed by this demo.

  python -m demos.deformation.ring_lip_install_demo run.probe=true run.render=false
  python -m demos.deformation.ring_lip_install_demo
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import time

import genesis as gs
import hydra
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

from topogym.primitives.fem_attachment import FEMRopeAttachment
from topogym.primitives.attachment import slerp
from topogym.robot.gripper import robotiq_joint_targets, as_numpy
from topogym.tasks_legacy.deformation._ring_lip_geometry import (
    sector_mesh, validate_geometry, lip_bounds, clearance_radius, seat_report, inside_fixture,
)
from topogym.world import StandardTabletopSceneBuilder, nyx
from topogym.world.closed_band import closed_transport_frames, closed_tube_mesh, TOPDOWN_PROJECTION
from topogym.world.rope import write_obj, tube_morph
from topogym.world.rope_backends import rope_backend

FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'


def vec(x):
    return as_numpy(x).reshape(-1, 3)


def build(cfg, output, *, replay=False):
    g = cfg.install
    geometry = validate_geometry(g)
    asset = output/'assets'
    asset.mkdir(parents=True, exist_ok=True)
    origin = np.asarray(cfg.env.frames.task.origin)
    center = np.r_[g.center, 0.]+origin
    backend = rope_backend(g.rope)
    if replay:
        options = {'fem_options': gs.options.FEMOptions()}
        static = gs.materials.Rigid(needs_coup=False)
    else:
        backend.pre_scene()
        options = backend.scene_options()
        static = backend.static_rigid_material()
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control, scene_options=options)
    table = builder.create(show_viewer=False, include_robot=replay,
                           robot_material=gs.materials.Rigid(needs_coup=False),
                           table_material=static, static_material=static,
                           decoration_material=gs.materials.Rigid(needs_coup=False))
    scene, manifest = table.scene, table.manifest

    def solid(name, mesh, color):
        path = asset/f'{name}.obj'
        mesh.export(path)
        entity = scene.add_entity(
            gs.morphs.Mesh(file=str(path), pos=tuple(center), fixed=True, convexify=False,
                           decimate=False, file_meshes_are_zup=True),
            material=static,
            surface=gs.surfaces.Plastic(color=color, roughness=.45), name=name)
        manifest.add(name, entity)

    solid('groove_floor', sector_mesh(.074, .137, .009, g.floor_z), (.22,.29,.33))
    solid('groove_inner_wall', sector_mesh(.074, g.groove_inner, g.floor_z, g.wall_z), (.52,.59,.60))
    solid('groove_outer_wall', sector_mesh(g.groove_outer, .137, g.floor_z, g.wall_z), (.52,.59,.60))
    for i in range(int(g.lip_count)):
        angle = float(g.lip_angles_deg[i])
        lo, hi = lip_bounds(g, i)
        solid(f'local_lip_{i+1}', sector_mesh(lo,hi,g.wall_z,g.lip_top_z,
              angle-g.lip_arc_deg/2,angle+g.lip_arc_deg/2,segments=12), (.84,.53,.19))
        # Distinct physical fasteners mark the three local arcs.
        for da in (-6.,6.):
            a = np.radians(angle+da)
            r = g.groove_outer+.007 if g.lip_sides[i]=='outer' else g.groove_inner-.006
            pos = center+np.array([r*np.cos(a),r*np.sin(a),g.lip_top_z+.001])
            entity = scene.add_entity(gs.morphs.Cylinder(pos=tuple(pos),radius=.0018,height=.002,
                                       fixed=True,collision=False),
                                       material=gs.materials.Rigid(needs_coup=False),
                                       surface=gs.surfaces.Plastic(color=(.15,.18,.19)))
            manifest.add(f'lip_{i+1}_bolt_{da}',entity)

    angles = np.linspace(0,2*np.pi,144,endpoint=False)
    line = np.column_stack((g.radius*np.cos(angles),g.radius*np.sin(angles),np.full(len(angles),g.spawn_z)))
    frames = closed_transport_frames(line,tube_radius=g.tube_radius,projection=TOPDOWN_PROJECTION)
    vertices, faces = closed_tube_mesh(line,frames,radius=g.tube_radius,radial_segments=8)
    write_obj(asset/'closed_ring.obj',vertices+center,faces)
    ring = scene.add_entity(tube_morph(asset/'closed_ring.obj',g.rope),material=backend.material(),
                             surface=gs.surfaces.Plastic(color=(.09,.47,.40),roughness=.68),name='elastic_ring')
    manifest.add('elastic_ring',ring)
    bands = []
    if not replay:
        for i in range(int(g.lip_count)):
            # One patch spans a short lip; patches on different lips are disjoint.
            for delta in (0.,):
                a = np.radians(g.lip_angles_deg[i]+delta)
                p = center+np.array([g.radius*np.cos(a),g.radius*np.sin(a),g.spawn_z])
                bands.append((i,delta,FEMRopeAttachment(ring,p,g.patch_radius,strength=g.rope.fem.follow_strength)))

    sensors, tool = {}, []
    if replay:
        # Tool coordinates are in the shared hand frame (+z towards fingertips).
        # A 12 mm handle is held by 2F-85; a narrow 3 mm shaft reaches the opening.
        for name,z,length,radius,color in (
            ('tool_handle',.110,.032,.006,(.20,.25,.28)),
            ('tool_shaft',.164,.076,.0015,(.60,.64,.64)),
            ('tool_tip',.202,.006,.002,(.84,.65,.30))):
            entity = scene.add_entity(gs.morphs.Cylinder(pos=(0,0,2),radius=radius,height=length,
                                      fixed=True,collision=False),material=gs.materials.Rigid(needs_coup=False),
                                      surface=gs.surfaces.Plastic(color=color,roughness=.4),name=name)
            manifest.add(name,entity)
            tool.append((entity,np.array([0,0,z])))
    builder.finalize(table)
    if replay:
        sensors = {name:table.cameras[name].sensor for name in cfg.run.record_cameras}
    return table,ring,bands,sensors,tool,geometry


def simulate(cfg, output):
    cfg.env.cameras = OmegaConf.create({})
    table,ring,bands,_,_,geometry = build(cfg,output)
    g = cfg.install
    scene = table.scene
    origin = np.asarray(cfg.env.frames.task.origin)
    dt = float(cfg.env.sim.dt)
    stride = round(1/(dt*cfg.run.fps))
    if abs(stride*dt*cfg.run.fps-1)>1e-8:
        raise ValueError('Frame rate must divide simulation time')
    initial = vec(ring.get_state().pos).copy()
    elements = as_numpy(ring.get_el2v()).astype(int)
    rest = initial[elements]
    rest_matrix = np.stack([rest[:,j]-rest[:,0] for j in (1,2,3)],axis=2)
    inv_rest = np.linalg.inv(rest_matrix)
    positions, tips, quats, metadata = [], [], [], []
    step = 0
    active = False
    tip = origin + np.array([g.center[0]-.03,g.center[1]-.17,.17])
    quat = np.array([0.,1.,0.,0.])
    started = time.monotonic()
    maximum_strain = 0.
    minimum_volume_ratio = 1.

    def advance(seconds,phase,target=None,band=None,target_quat=None):
        nonlocal step,tip,quat,maximum_strain,minimum_volume_ratio
        start = tip.copy()
        start_quat = quat.copy()
        count = max(1,round(seconds/dt))
        for k in range(1,count+1):
            u = k/count
            u = u*u*(3-2*u)
            if target is not None:
                tip = start+(target-start)*u
            if target_quat is not None:
                quat = slerp(start_quat,target_quat,u)
            if band is not None:
                band.drive_to(tip)
            scene.step()
            step += 1
            if step%stride==0:
                points = vec(ring.get_state().pos).copy()
                tet = points[elements]
                deformation = np.stack([tet[:,j]-tet[:,0] for j in (1,2,3)],axis=2)@inv_rest
                stretches = np.linalg.svd(deformation,compute_uv=False)
                maximum_strain = max(maximum_strain,float(np.max(np.abs(stretches-1))))
                minimum_volume_ratio = min(minimum_volume_ratio,float(np.linalg.det(deformation).min()))
                positions.append(points)
                tips.append(tip.copy())
                quats.append(quat.copy())
                reading = seat_report(points-origin,g)
                metadata.append(dict(frame=len(positions)-1,time_s=step*dt,phase=phase,active=active,
                                     seated_fraction=reading['seated_fraction']))
            if step%100==0:
                print(f'{phase}: t={step*dt:.1f}s seated={metadata[-1]["seated_fraction"]:.3f} '
                      f'wall={time.monotonic()-started:.1f}s',flush=True)
        if band is not None:
            print(f'  patch follow error: {np.linalg.norm(band.band_center()-tip)*1000:.2f} mm',flush=True)

    advance(1.,'观察与选择起点')
    for i,delta,band in bands:
        p = band.band_center()
        angle = np.arctan2(p[1]-origin[1]-g.center[1],p[0]-origin[0]-g.center[0])
        sign = 1 if g.lip_sides[i]=='outer' else -1
        tilt = np.radians(48.)
        zaxis = np.array([sign*np.sin(tilt)*np.cos(angle),sign*np.sin(tilt)*np.sin(angle),-np.cos(tilt)])
        xaxis = np.array([-np.sin(angle),np.cos(angle),0.])
        yaxis = np.cross(zaxis,xaxis)
        tool_quat = Rotation.from_matrix(np.column_stack((xaxis,yaxis,zaxis))).as_quat()[[3,0,1,2]]
        above = p + np.array([0,0,.070])
        advance(.8,f'接近卡唇 {i+1}',target=above,target_quat=tool_quat)
        advance(.4,f'建立局部定位 {i+1}',target=p)
        band.attach(p)
        active = True
        radial = clearance_radius(g,i)
        enter = origin+np.array([g.center[0]+radial*np.cos(angle),g.center[1]+radial*np.sin(angle),g.spawn_z])
        advance(1.,f'卡唇 {i+1}：局部侧移',target=enter,band=band)
        low = enter.copy(); low[2] = origin[2]+g.floor_z+g.tube_radius+.0008
        advance(1.,f'卡唇 {i+1}：越过开放入口',target=low,band=band)
        seated = origin+np.array([g.center[0]+g.radius*np.cos(angle),g.center[1]+g.radius*np.sin(angle),low[2]-origin[2]])
        advance(1.,f'卡唇 {i+1}：送至唇下',target=seated,band=band)
        advance(.2,f'卡唇 {i+1}：保持局部就位',band=band)
        band.release(); active=False
        advance(.35,'退出局部开口',target=low)
        advance(.5,'换位至相邻软环段',target=tip+np.array([0,0,.070]))
    release_start = vec(ring.get_state().pos).copy()
    advance(.8,'撤去安装工具',target=origin+np.array([g.center[0]-.06,-.21,.17]),target_quat=np.array([0.,1.,0.,0.]))
    advance(float(g.release_s),'全部约束释放：检查整圈保持')
    final = vec(ring.get_state().pos)
    report = seat_report(final-origin,g)
    hold_samples=metadata[-round(g.release_s*cfg.run.fps):]
    hold_seated=all(s['seated_fraction']==1. for s in hold_samples)
    within_strain=maximum_strain<=float(g.max_principal_strain)
    report['success']=bool(report['success'] and hold_seated and within_strain and minimum_volume_ratio>0)
    report.update(geometry=geometry,kind='FEM IPC local assisted installation experiment',
                  robot_dynamics_validated=False,grasp='One local FEM soft constraint at a time; no installed-region pins',
                  initial_condition='Closed ring pre-aligned above the groove, supported by the lip tops',
                  frames=len(positions),fps=int(cfg.run.fps),simulation_seconds=step*dt,
                  wall_seconds=time.monotonic()-started,final_active_grasps=0,
                  released_hold_seconds=float(g.release_s),
                  remained_seated_during_entire_hold=hold_seated,
                  final_drift_since_release_mm=float(np.max(np.linalg.norm(final-release_start,axis=1))*1000),
                  max_principal_strain=maximum_strain,min_tet_volume_ratio=minimum_volume_ratio,
                  permitted_numerical_principal_strain=float(g.max_principal_strain),
                  within_numerical_strain_envelope=within_strain,
                  material_calibrated_to_real_elastomer=False)
    np.savez_compressed(output/'trajectory.npz',positions=np.asarray(positions,dtype=np.float32),
                        tips=np.asarray(tips),quats=np.asarray(quats),initial=initial,elements=elements)
    (output/'frames.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


def replay(cfg,output):
    recorded=OmegaConf.load(output/'simulation_config.yaml')
    if OmegaConf.to_container(recorded.install,resolve=True)!=OmegaConf.to_container(cfg.install,resolve=True):
        raise ValueError('Installation geometry/material differs from the saved simulation. Run a new probe in a new output directory.')
    data = np.load(output/'trajectory.npz')
    metadata = json.loads((output/'frames.json').read_text())
    report = json.loads((output/'report.json').read_text())
    if not cfg.run.preview and not report['success']:
        raise ValueError('The saved FEM trajectory failed verification; use preview mode to inspect it.')
    media = output/'preview' if cfg.run.preview else output
    media.mkdir(parents=True,exist_ok=True)
    table,ring,_,sensors,tool,_ = build(cfg,output,replay=True)
    if not np.allclose(vec(ring.get_state().pos),data['initial'],atol=1e-7):
        raise RuntimeError('Replay tetrahedral vertex order differs from the simulated mesh')
    robot = table.manifest.get('robot')
    hand = robot.get_link('hand')
    q = as_numpy(robot.get_qpos()).copy().reshape(-1)
    q[:7] = np.asarray(cfg.robot_control.home.qpos[:7])
    for name,value in robotiq_joint_targets(.006).items():
        name = {'right_driver_joint':'finger_joint1','left_driver_joint':'finger_joint2'}.get(name,'r85_'+name)
        q[robot.get_joint(name).qs_idx_local[0]] = value
    robot.set_qpos(q,zero_velocity=True)
    max_error = 0.
    records = []
    tool_local=[]
    for z0,z1,radius in ((.094,.126,.006),(.126,.202,.0015),(.199,.205,.002)):
        for z in np.linspace(z0,z1,max(3,int((z1-z0)/.001))):
            for a in np.linspace(0,2*np.pi,12,endpoint=False):
                tool_local.append([radius*np.cos(a),radius*np.sin(a),z])
    tool_local=np.asarray(tool_local)
    exterior_margins={name:float('inf') for name in cfg.run.exterior_cameras}
    fonts = {size:ImageFont.truetype(FONT,size) for size in (18,24,30)}
    writers = {}
    with ExitStack() as stack:
        for name in sensors:
            if cfg.run.preview:
                continue
            writers[name] = stack.enter_context(imageio.get_writer(media/f'{name}.mp4',fps=cfg.run.fps,
                                    codec='libx264',quality=8,macro_block_size=1,ffmpeg_params=['-movflags','+faststart']))
        last_phase = None
        for index,(points,tip,info) in enumerate(zip(data['positions'],data['tips'],metadata)):
            # Actual FEM samples are replayed verbatim; no goal-shape blend.
            ring.set_pos(table.scene.sim.cur_substep_local,gs.tensor(points[None],dtype=gs.tc_float))
            quat = data['quats'][index]
            # The round installation tool is invariant to roll. Keep its x axis
            # near world +x instead of forcing the wrist to follow the arc yaw.
            zaxis=Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()[:,2]
            original_tilt=np.arctan2(np.linalg.norm(zaxis[:2]),-zaxis[2])
            scaled_tilt=original_tilt*float(cfg.run.tool_tilt_deg)/48.
            xy=zaxis[:2]/max(np.linalg.norm(zaxis[:2]),1e-12)
            zaxis=np.r_[xy*np.sin(scaled_tilt),-np.cos(scaled_tilt)]
            xaxis=np.array([1.,0.,0.])-zaxis*zaxis[0]
            xaxis/=np.linalg.norm(xaxis)
            quat=Rotation.from_matrix(np.column_stack((xaxis,np.cross(zaxis,xaxis),zaxis))).as_quat()[[3,0,1,2]]
            # Physical tip is at +0.205 in the hand frame; contact at tube top.
            target_rotation=Rotation.from_quat(quat[[1,2,3,0]])
            target = tip+np.array([0,0,cfg.install.tube_radius])-target_rotation.apply([0,0,.205])
            result = robot.inverse_kinematics(link=hand,pos=target,quat=quat,init_qpos=q,
                         dofs_idx_local=np.arange(7),max_samples=1,max_solver_iters=200,
                         pos_tol=1e-5,rot_tol=1e-4,max_step_size=.08)
            q[:7] = as_numpy(result).reshape(-1)[:7]
            robot.set_qpos(q,zero_velocity=True)
            hpos = vec(hand.get_pos())[0]
            hquat = as_numpy(hand.get_quat()).reshape(-1)
            rotation = Rotation.from_quat(hquat[[1,2,3,0]])
            error = float(np.linalg.norm(hpos-target))
            max_error = max(max_error,error)
            for entity,offset in tool:
                entity.set_pos(hpos+rotation.apply(offset))
                entity.set_quat(hquat)
            tool_points=hpos+rotation.apply(tool_local)-np.asarray(cfg.env.frames.task.origin)
            overlaps=int(inside_fixture(tool_points,cfg.install).sum())
            if not cfg.run.preview and (error>.001 or overlaps):
                raise RuntimeError(f'Replay frame {index}: IK error {error*1000:.3f} mm, tool-fixture overlaps {overlaps}')
            records.append(dict(frame=index,ik_error_mm=error*1000,qpos=q.tolist(),
                                tool_quat_wxyz=quat.tolist(),tool_fixture_overlap_samples=overlaps))
            if index%10==0 or index==len(metadata)-1:
                vertices=vec(robot.get_vverts())
                for name in cfg.run.exterior_cameras:
                    cam=table.cameras[name]
                    transform=cam.transform.copy();transform[:3,1:3]*=-1
                    extrinsics=np.linalg.inv(transform)
                    cp=vertices@extrinsics[:3,:3].T+extrinsics[:3,3]
                    px=cp@cam.intrinsics.T;px=px[:,:2]/px[:,2:3]
                    width,height=cam.res
                    # Keep the arm clear of the video title and footer too.
                    margin=min(float(px[:,0].min()),float(px[:,1].min()-84),
                               float(width-1-px[:,0].max()),float(height-37-px[:,1].max()))
                    exterior_margins[name]=min(exterior_margins[name],margin)
            if cfg.run.preview and index%40 and index!=len(metadata)-1:
                continue
            # Replay does not advance scene time. Explicitly refresh Nyx's
            # transforms and shared image cache after loading every sample.
            table.scene.visualizer.update_visual_states(force_render=True)
            next(iter(sensors.values()))._render_current_state()
            for name,sensor in sensors.items():
                rgb = nyx.rgb(sensor)
                image = Image.fromarray(rgb)
                draw = ImageDraw.Draw(image)
                w,h = image.size
                title_size = 30 if w>=1200 else 24
                draw.rectangle((0,0,w,84),fill=(19,28,34))
                draw.text((20,9),f'闭合软环安装 · {cfg.install.lip_count} 段局部卡唇',font=fonts[title_size],fill=(241,243,237))
                draw.text((20,49),info['phase'],font=fonts[18],fill=(145,218,198))
                draw.rectangle((0,h-36,w,h),fill=(19,28,34))
                label={'agentview':'主视角','front_oblique':'侧前方','wrist':'腕部视角'}[name]
                draw.text((14,h-30),f'{label}  |  {info["time_s"]:05.2f} s  |  FEM 接触仿真 + 机械臂 IK / 辅助安装头',font=fonts[18],fill=(200,206,207))
                if not cfg.run.preview:
                    writers[name].append_data(np.asarray(image))
                if cfg.run.preview or index in (0,len(metadata)-1) or info['phase'] != last_phase:
                    image.save(media/f'frame_{index:04d}_{name}.jpg',quality=92)
                if index==len(metadata)-1:
                    image.save(media/f'final_{name}.png')
            last_phase = info['phase']
            if index%40==0:
                print(f'render {index}/{len(metadata)} max_ik_error={max_error*1000:.3f} mm',flush=True)
    (media/'robot_replay.json').write_text(json.dumps(dict(max_ik_position_error_mm=max_error*1000,
                robot_contact_dynamics=False,exterior_arm_margin_px=exterior_margins,
                tool_fixture_overlap_frames=sum(r['tool_fixture_overlap_samples']>0 for r in records),
                frames=records),indent=2))
    if cfg.run.preview:
        return
    report['replay_max_ik_position_error_mm'] = max_error*1000
    report['replay_tool_fixture_overlap_frames']=sum(r['tool_fixture_overlap_samples']>0 for r in records)
    report['replay_full_arm_camera_margin_px']=exterior_margins
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    camera_rig={name:nyx.camera_kwargs(cfg.env.cameras[name],table.manifest) for name in sensors}
    (output/'camera_rig.json').write_text(json.dumps(camera_rig,indent=2))
    write_media_index(output,int(cfg.install.lip_count))


def write_media_index(output,lip_count):
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>闭合软环安装</title>
<style>body{background:#131c22;color:#edf1ec;font:18px sans-serif;max-width:1440px;margin:32px auto;padding:0 24px}a{color:#91dac6}video{width:100%;border-radius:12px}.views{display:grid;grid-template-columns:1fr 1fr;gap:24px}section:first-child{grid-column:1/-1}section{margin:16px 0}button{padding:10px 20px;margin-right:10px}@media(max-width:760px){.views{display:block}}</style>
<h1>闭合软环安装 · LIP_COUNT 段局部卡唇</h1>
<p>Franka Panda + Robotiq 2F-85 · 细安装头 · 三路同步视频</p>
<p>软环采用 FEM / IPC 接触仿真，每次只驱动一个局部区域。机械臂采用 IK 重放；安装头与软环之间使用辅助约束，尚未验证完整机械臂接触动力学。初始软环已对齐并搭在卡唇上。</p>
<p><a href="report.json">仿真报告</a> · <a href="camera_rig.json">相机参数</a></p>
<button onclick="document.querySelectorAll('video').forEach(v=>{v.currentTime=0;v.play()})">三路同步播放</button><button onclick="document.querySelectorAll('video').forEach(v=>v.pause())">全部暂停</button>
<div class="views">
'''
    for name,title in [('agentview','主视角'),('wrist','腕部视角'),('front_oblique','侧前方视角')]:
        html += f'<section><h2>{title}</h2><video controls preload="metadata" src="{name}.mp4"></video></section>'
    (output/'index.html').write_text(html.replace('LIP_COUNT',str(lip_count))+'</div></html>',encoding='utf-8')


@hydra.main(version_base='1.3',config_path='../../configs',config_name='ring_lip_install')
def main(cfg):
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    names=list(cfg.run.record_cameras)
    cfg.env.cameras=OmegaConf.create({name:OmegaConf.to_container(cfg.env.cameras[name],resolve=True) for name in names})
    gs.init(backend=gs.cuda,logging_level='warning',seed=0)
    OmegaConf.save(cfg,output/('simulation_config.yaml' if cfg.run.probe else 'render_config.yaml'),resolve=True)
    if cfg.run.probe:
        simulate(cfg,output)
    elif cfg.run.render:
        replay(cfg,output)


if __name__=='__main__':
    main()
