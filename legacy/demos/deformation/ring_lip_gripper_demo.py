"""Pick up a free ring, place it, and seat it with the closed 2F-85 fingers.

The real gripper collision meshes participate in FEM/IPC. Only the pickup may
use a local grasp assist; every push runs with ALL material constraints off.
The arm follows prescribed IK joint poses, not a torque-control validation.
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
import igl
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

from topogym.primitives.attachment import slerp
from topogym.primitives.fem_attachment import FEMRopeAttachment
from topogym.robot.gripper import as_numpy,robotiq_joint_targets
from topogym.tasks_legacy.deformation._ring_lip_geometry import sector_mesh,lip_bounds,seat_report,validate_geometry,inside_fixture
from topogym.world import StandardTabletopSceneBuilder,nyx
from topogym.world.closed_band import closed_transport_frames,closed_tube_mesh,TOPDOWN_PROJECTION
from topogym.world.rope import tube_morph,write_obj
from topogym.world.rope_backends import rope_backend

FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
CONTACT_LINKS=('r85_base','r85_right_driver','r85_left_driver','r85_right_coupler','r85_left_coupler',
               'r85_right_spring_link','r85_left_spring_link','r85_right_follower','r85_left_follower',
               'left_finger','right_finger')


def points(x): return as_numpy(x).reshape(-1,3)


def lip_coverage(material,cfg,index):
    delta=np.asarray(material)[:,:2]-np.asarray(cfg.center);r=np.linalg.norm(delta,axis=1)
    angle=np.angle(np.exp(1j*(np.arctan2(delta[:,1],delta[:,0])-np.radians(cfg.lip_angles_deg[index]))))
    lo,hi=lip_bounds(cfg,index);bins=np.radians(np.linspace(-cfg.lip_arc_deg/2,cfg.lip_arc_deg/2,6))
    return [int(((angle>=a)&(angle<b)&(r>=lo)&(r<=hi)&(material[:,2]<cfg.wall_z)).sum())
            for a,b in zip(bins[:-1],bins[1:])]


def pad_gaps(robot,material_points):
    """Distance from the actual selected material to each real pad surface."""
    result={}
    for name in ('left_finger','right_finger'):
        distance=float('inf')
        for geom in robot.get_link(name).geoms:
            values,*_=igl.signed_distance(np.asarray(material_points,dtype=float),
                    points(geom.get_verts()).astype(float),np.asarray(geom.init_faces,dtype=np.int32))
            distance=min(distance,float(abs(values).min()))
        result[name]=distance
    return result


def joint_name(name):
    return {'right_driver_joint':'finger_joint1','left_driver_joint':'finger_joint2'}.get(name,'r85_'+name)


def downward_quat(angle=0.,tilt=0.):
    tangent=np.array([-np.sin(angle),np.cos(angle),0.])
    if tangent[0]<-1e-6: tangent=-tangent
    axis=np.array([np.sin(tilt)*np.cos(angle),np.sin(tilt)*np.sin(angle),-np.cos(tilt)])
    return Rotation.from_matrix(np.column_stack((tangent,np.cross(axis,tangent),axis))).as_quat()[[3,0,1,2]]


def build(cfg,output,replay=False,with_cameras=True):
    g=cfg.install;validate_geometry(g)
    asset=output/'assets';asset.mkdir(parents=True,exist_ok=True)
    backend=rope_backend(g.rope)
    origin=np.asarray(cfg.env.frames.task.origin)
    if not replay:
        backend.pre_scene();options=backend.scene_options()
        static=backend.static_rigid_material()
        robot_material=gs.materials.Rigid(coup_type='two_way_soft_constraint',coup_links=CONTACT_LINKS,
                                        coup_friction=float(cfg.gripper_demo.contact_friction))
    else:
        options={'fem_options':gs.options.FEMOptions()}
        static=gs.materials.Rigid(needs_coup=False);robot_material=static
    builder=StandardTabletopSceneBuilder(cfg.env,cfg.robot_control,scene_options=options)
    table=builder.create(show_viewer=False,include_robot=True,robot_material=robot_material,
                        table_material=static,static_material=static,
                        decoration_material=gs.materials.Rigid(needs_coup=False))
    scene=table.scene;manifest=table.manifest
    center=origin+np.r_[g.center,0.]
    solids={}
    def solid(name,mesh,color):
        path=asset/f'{name}.obj';mesh.export(path)
        entity=scene.add_entity(gs.morphs.Mesh(file=str(path),pos=tuple(center),fixed=True,
                    convexify=False,decimate=False,file_meshes_are_zup=True),material=static,
                    surface=gs.surfaces.Plastic(color=color,roughness=.5),name=name)
        manifest.add(name,entity);solids[name]=mesh
    solid('groove_floor',sector_mesh(g.base_inner,g.base_outer,g.get('base_bottom',.003),g.floor_z),(.22,.29,.33))
    solid('groove_inner_wall',sector_mesh(g.base_inner,g.groove_inner,g.floor_z,g.wall_z),(.52,.59,.60))
    solid('groove_outer_wall',sector_mesh(g.groove_outer,g.base_outer,g.floor_z,g.wall_z),(.52,.59,.60))
    for i in range(int(g.lip_count)):
        a=g.lip_angles_deg[i];lo,hi=lip_bounds(g,i)
        solid(f'local_lip_{i+1}',sector_mesh(lo,hi,g.wall_z,g.lip_top_z,a-g.lip_arc_deg/2,
                                          a+g.lip_arc_deg/2,segments=12),(.84,.53,.19))
    spawn_center=np.asarray(g.center if cfg.run.mode=='push_only' else g.source_center)
    spawn_center=spawn_center+np.asarray(cfg.run.get('spawn_offset',[0.,0.]))
    spawn_z=float(g.spawn_z if cfg.run.mode=='push_only' else g.source_z)
    angles=np.linspace(0,2*np.pi,144,endpoint=False)
    line=np.c_[g.radius*np.cos(angles),g.radius*np.sin(angles),np.full(len(angles),spawn_z)]
    frames=closed_transport_frames(line,tube_radius=g.tube_radius,projection=TOPDOWN_PROJECTION)
    v,f=closed_tube_mesh(line,frames,radius=g.tube_radius,radial_segments=8)
    write_obj(asset/'closed_ring.obj',v+origin+np.r_[spawn_center,0.],f)
    ring=scene.add_entity(tube_morph(asset/'closed_ring.obj',g.rope),material=backend.material(),
                     surface=gs.surfaces.Plastic(color=(.09,.47,.40),roughness=.65),name='elastic_ring')
    manifest.add('elastic_ring',ring)
    grasp=None
    if not replay:
        a=np.radians(g.pickup_angle_deg)
        p=origin+np.r_[spawn_center+g.radius*np.array([np.cos(a),np.sin(a)]),spawn_z]
        grasp=FEMRopeAttachment(ring,p,float(cfg.gripper_demo.pickup_patch_radius),strength=g.rope.fem.follow_strength)
    builder.finalize(table)
    sensors={name:table.cameras[name].sensor for name in cfg.run.record_cameras} if replay and with_cameras else {}
    return table,ring,grasp,sensors


class GripperPose:
    """Actual original-scale asset FK, including the aperture-dependent tip."""
    def __init__(self,table,cfg):
        self.table=table;self.cfg=cfg;self.robot=table.manifest.get('robot');self.hand=self.robot.get_link('hand')
        self.q=as_numpy(self.robot.get_qpos()).reshape(-1).copy();self.q[:7]=cfg.robot_control.home.qpos[:7]
        self.half_gap=float(cfg.gripper_demo.open_half_gap)
        self.set_gap(self.half_gap);self.robot.set_qpos(self.q,zero_velocity=True)
        self.pos=points(self.hand.get_pos())[0]
        self.quat=as_numpy(self.hand.get_quat()).reshape(4)
        self.max_error=0.

    def set_gap(self,gap):
        self.half_gap=float(gap)
        for name,value in robotiq_joint_targets(gap).items():
            self.q[self.robot.get_joint(joint_name(name)).qs_idx_local[0]]=value

    def pad_tip_local(self,gap=None):
        old=self.q.copy();old_gap=self.half_gap
        if gap is not None:self.set_gap(gap)
        self.robot.set_qpos(self.q,zero_velocity=True)
        hp=points(self.hand.get_pos())[0];hq=as_numpy(self.hand.get_quat()).reshape(4)
        r=Rotation.from_quat(hq[[1,2,3,0]])
        v=np.concatenate([points(self.robot.get_link(n).get_verts()) for n in ('left_finger','right_finger')])
        local=r.inv().apply(v-hp)
        result=np.array([0.,0.,float(local[:,2].max())])
        if gap is not None:self.q=old;self.half_gap=old_gap;self.robot.set_qpos(old,zero_velocity=True)
        return result

    def target(self,pos,quat,gap):
        self.pos=np.asarray(pos);self.quat=np.asarray(quat);self.set_gap(gap)
        q=self.robot.inverse_kinematics(link=self.hand,pos=self.pos,quat=self.quat,init_qpos=self.q,
             dofs_idx_local=np.arange(7),max_samples=1,max_solver_iters=160,max_step_size=.06,
             pos_tol=1e-5,rot_tol=1e-4)
        self.q[:7]=as_numpy(q).reshape(-1)[:7]
        self.robot.set_qpos(self.q,zero_velocity=True)
        error=np.linalg.norm(points(self.hand.get_pos())[0]-self.pos)
        self.max_error=max(self.max_error,float(error))
        return float(error)


def simulate(cfg,output):
    if any(side!='inner' for side in cfg.install.lip_sides[:int(cfg.install.lip_count)]):
        raise ValueError('This contact-push planner currently supports inner-side lips only')
    cfg.env.cameras=OmegaConf.create({})
    table,ring,grasp,_=build(cfg,output)
    robot=GripperPose(table,cfg);scene=table.scene;g=cfg.install;d=cfg.gripper_demo
    origin=np.asarray(cfg.env.frames.task.origin);dt=float(cfg.env.sim.dt);stride=round(1/(dt*cfg.run.fps))
    initial=points(ring.get_state().pos).copy();elements=as_numpy(ring.get_el2v()).astype(int)
    rest=initial[elements];inv_rest=np.linalg.inv(np.stack([rest[:,i]-rest[:,0] for i in (1,2,3)],2))
    states=[];joints=[];meta=[];step=0;maxstrain=0.;minvolume=1.;phase='观察初始位置'
    band_local=None;started=time.monotonic();phase_reports=[];pickup_checks={};completed=False

    def save():
        report=seat_report(points(ring.get_state().pos)-origin,g)
        hold_ids=[i for i,m in enumerate(meta) if m['phase']=='释放后检查整圈保持']
        hold=[meta[i] for i in hold_ids]
        coverage=[lip_coverage(points(ring.get_state().pos)-origin,g,i) for i in range(int(g.lip_count))]
        push_constraints=sum(int(m['grasp_assist']) for m in meta if '卡唇' in m['phase'])
        release_drift=float(np.linalg.norm(np.asarray(states)[hold_ids]-states[hold_ids[0]],axis=2).max()) if hold else None
        report.update(success=bool(completed and report['success'] and all(v['seated_fraction']==1 for v in hold)
                                  and maxstrain<=g.max_principal_strain and minvolume>0 and push_constraints==0
                                  and all(all(n>0 for n in bins) for bins in coverage)),
                      kind='Real 2F85 collision geometry + FEM IPC; prescribed IK arm',
                      mode=str(cfg.run.mode),completed=completed,pickup_assist=bool(d.pickup_assist),
                      push_material_constraint_frames=push_constraints,additional_tool=False,frames=len(states),fps=int(cfg.run.fps),
                      max_principal_strain=maxstrain,min_tet_volume_ratio=minvolume,
                      max_ik_error_mm=robot.max_error*1000,phase_reports=phase_reports,
                      pickup_checks=pickup_checks,
                      under_lip_nodes_in_five_angular_bins=coverage,
                      release_hold_max_vertex_drift_mm=None if release_drift is None else release_drift*1000,
                      released_hold_seconds=len(hold)/cfg.run.fps,final_active_grasps=int(grasp.active),
                      simulation_seconds=step*dt,wall_seconds=time.monotonic()-started)
        np.savez_compressed(output/'trajectory.npz',positions=np.asarray(states,dtype=np.float32),
                            qpos=np.asarray(joints,dtype=np.float32),initial=initial,elements=elements)
        (output/'frames.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        return report

    def move(seconds,label,pos=None,quat=None,gap=None):
        nonlocal step,phase,maxstrain,minvolume
        phase=label;start=robot.pos.copy();sq=robot.quat.copy();sg=robot.half_gap
        target=start if pos is None else np.asarray(pos);tq=sq if quat is None else np.asarray(quat)
        tg=sg if gap is None else float(gap);count=max(1,round(seconds/dt))
        for k in range(1,count+1):
            u=k/count;u=u*u*(3-2*u)
            p=start+(target-start)*u;q=slerp(sq,tq,u);aperture=sg+(tg-sg)*u
            error=robot.target(p,q,aperture)
            if error>.003:raise RuntimeError(f'IK missed {phase} by {error*1000:.2f} mm')
            if grasp.active:
                hp=points(robot.hand.get_pos())[0];hq=as_numpy(robot.hand.get_quat()).reshape(4)
                grasp._handle.update_targets(hp+Rotation.from_quat(hq[[1,2,3,0]]).apply(band_local))
            scene.step();step+=1
            if step%stride==0:
                ps=points(ring.get_state().pos).copy();tet=ps[elements]
                deform=np.stack([tet[:,i]-tet[:,0] for i in (1,2,3)],2)@inv_rest
                maxstrain=max(maxstrain,float(abs(np.linalg.svd(deform,compute_uv=False)-1).max()))
                minvolume=min(minvolume,float(np.linalg.det(deform).min()))
                reading=seat_report(ps-origin,g)
                states.append(ps);joints.append(as_numpy(robot.robot.get_qpos()).reshape(-1).copy())
                meta.append(dict(frame=len(states)-1,time_s=step*dt,phase=phase,
                                 grasp_assist=grasp.active,seated_fraction=reading['seated_fraction'],
                                 half_gap_m=robot.half_gap))
                if maxstrain>g.max_principal_strain or minvolume<=0:
                    raise RuntimeError('Soft-ring deformation exceeded the configured numerical limit')
            if step%100==0:
                print(f'{phase}: t={step*dt:.1f}s seated={meta[-1]["seated_fraction"]:.3f} '
                      f'strain={maxstrain:.3f} minV={minvolume:.3f} wall={time.monotonic()-started:.1f}s',flush=True)
        phase_reports.append(dict(phase=phase,time_s=step*dt,**seat_report(points(ring.get_state().pos)-origin,g)))

    try:
        move(1.,'观察初始位置')
        if cfg.run.mode!='push_only':
            a=np.radians(g.pickup_angle_deg);q=downward_quat(a)
            p=grasp.band_center();tip=robot.pad_tip_local(d.grasp_half_gap)
            # Pinch the lower end of both real pads; leave 0.5 mm above the table.
            contact=p+np.array([0,0,-g.tube_radius+.0007])
            hand=contact-Rotation.from_quat(q[[1,2,3,0]]).apply(tip)
            move(1.5,'张开夹爪，接近槽外绳圈',pos=hand+[0,0,.09],quat=q,gap=d.open_half_gap)
            move(1.,'对准绳圈局部抓取位置',pos=hand)
            move(1.2,'合拢夹爪抓住绳圈',gap=d.grasp_half_gap)
            if d.pickup_assist:
                hp=points(robot.hand.get_pos())[0];hq=as_numpy(robot.hand.get_quat()).reshape(4)
                ps=points(ring.get_state().pos)[grasp.indices]
                gaps=pad_gaps(robot.robot,ps)
                pickup_checks['pad_surface_gaps_mm']={k:v*1000 for k,v in gaps.items()}
                if max(gaps.values())>.002:
                    raise RuntimeError(f'Pickup material has not reached both pads: {gaps}')
                band_local=Rotation.from_quat(hq[[1,2,3,0]]).inv().apply(ps-hp)
                grasp.attach(ps.mean(0))
            move(2.,'提起绳圈',pos=robot.pos+[0,0,d.lift_height])
            pickup_checks['lowest_ring_point_after_lift_mm']=float((points(ring.get_state().pos)[:,2].min()-origin[2])*1000)
            if pickup_checks['lowest_ring_point_after_lift_mm']<100:
                raise RuntimeError('The whole ring did not clear the table during pickup')
            delta=np.r_[np.asarray(g.center)-np.asarray(g.source_center)+np.asarray(d.placement_offset),0.]
            move(2.5,'搬运绳圈至槽位上方',pos=robot.pos+delta)
            move(2.,'降低绳圈，建立槽上初始位置',pos=hand+delta+[0,0,g.spawn_z-g.source_z])
            grasp.release();band_local=None
            move(1.,'张开夹爪，放下绳圈',gap=d.open_half_gap)
            move(1.,'抬起并准备闭合头部',pos=robot.pos+[0,0,.10])
            if cfg.run.mode=='pickup_only':
                move(float(g.release_s),'检查搬运后绳圈位置')
                return
        move(1.,'合拢夹爪形成推压头',gap=d.push_half_gap)
        tip_local=robot.pad_tip_local(d.push_half_gap)
        for i in range(int(g.lip_count)):
            for offset in (0., -6., 6.):
                a=np.radians(g.lip_angles_deg[i]+offset)
                radial=np.array([np.cos(a),np.sin(a),0.]);q=downward_quat(a)
                ps=points(ring.get_state().pos)-origin
                az=np.arctan2(ps[:,1]-g.center[1],ps[:,0]-g.center[0])
                mask=abs(np.angle(np.exp(1j*(az-a))))<np.radians(7.)
                top=float(ps[mask,2].max())
                if top<float(g.wall_z)-.0005:
                    continue
                high=mask&(ps[:,2]>top-.002)
                actual_radius=float(np.median(np.linalg.norm(ps[high,:2]-np.asarray(g.center),axis=1)))
                # Use the SIDE of the closed pads to move the ring clear of the
                # lip. All lateral motion stays above the fixed lip top.
                pad_half_width=.0089
                start_radius=actual_radius-g.tube_radius-pad_half_width-.002
                edge=lip_bounds(g,i)[1]
                end_radius=edge+.003-pad_half_width
                if start_radius>=end_radius:
                    continue
                tip_z=max(float(g.lip_top_z)+.001,top-2*g.tube_radius+.002)
                p=origin+np.r_[g.center,0.]+start_radius*radial+np.array([0,0,tip_z])
                hand=p-Rotation.from_quat(q[[1,2,3,0]]).apply(tip_local)
                move(1.2,f'闭合头部接近卡唇 {i+1}',pos=hand+[0,0,.065],quat=q)
                move(.7,f'卡唇 {i+1}：对准绳段侧面',pos=hand)
                move(1.1,f'卡唇 {i+1}：侧向微推越过唇边',pos=hand+(end_radius-start_radius)*radial)
                move(.5,f'卡唇 {i+1}：保持，等待软环落入')
                move(.7,f'卡唇 {i+1}：抬头检查',pos=robot.pos+[0,0,.065])
        def covered(index):
            return all(n>0 for n in lip_coverage(points(ring.get_state().pos)-origin,g,index))
        for i in range(int(g.lip_count)):
            if covered(i):continue
            a=np.radians(g.lip_angles_deg[i]);radial=np.array([np.cos(a),np.sin(a),0.])
            q=downward_quat(a,np.radians(-15.))
            p=origin+np.r_[g.center,0.]+.117*radial+np.array([0,0,.055])
            hand=p-Rotation.from_quat(q[[1,2,3,0]]).apply(tip_local)
            move(1.2,f'卡唇 {i+1}：调整闭合指端接近角度',pos=hand,quat=q)
            for height in (.022,.020,.018):
                move(.8,f'卡唇 {i+1}：倾斜轻压，送至唇下',pos=hand+[0,0,height-.055])
                move(.3,f'卡唇 {i+1}：检查唇下覆盖')
                if covered(i):break
            move(.8,f'卡唇 {i+1}：撤去指端压力',pos=robot.pos+[0,0,.065])
        move(1.5,'撤开机械臂',pos=robot.pos+[-.07,-.10,.05],quat=np.array([0.,1.,0.,0.]))
        move(float(g.release_s),'释放后检查整圈保持')
        completed=True
    finally:
        grasp.release()
        report=save();print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


def audit(cfg,output):
    """Sample real gripper collision surfaces against the fixed fixture."""
    cfg.env.cameras=OmegaConf.create({})
    table,ring,_,_=build(cfg,output,replay=True,with_cameras=False)
    robot=table.manifest.get('robot');origin=np.asarray(cfg.env.frames.task.origin)
    data=np.load(output/'trajectory.npz');meta=json.loads((output/'frames.json').read_text())
    geoms=[geom for name in CONTACT_LINKS for geom in robot.get_link(name).geoms]
    violations=[];minimum_table_clearance=float('inf')
    # Subdivide each real collision triangle into a uniform barycentric lattice.
    # Ten samples per triangle supplement original vertices for the thin lips.
    weights=np.asarray([(i/3,j/3,1-(i+j)/3) for i in range(4) for j in range(4-i)])
    for frame,q in enumerate(data['qpos']):
        robot.set_qpos(q,zero_velocity=True)
        count=0
        for geom in geoms:
            v=points(geom.get_verts())-origin
            faces=np.asarray(geom.init_faces,dtype=int)
            samples=np.einsum('ki,fij->fkj',weights,v[faces]).reshape(-1,3)
            minimum_table_clearance=min(minimum_table_clearance,float(samples[:,2].min()))
            count+=int(inside_fixture(samples,cfg.install).sum())
        if count:violations.append(dict(frame=frame,time_s=meta[frame]['time_s'],phase=meta[frame]['phase'],samples=count))
    result=dict(sampled_frames=len(meta),fixture_intrusion_frames=violations,
                minimum_table_clearance_mm=minimum_table_clearance*1000,
                push_assist_frames=sum(bool(m['grasp_assist']) for m in meta if '卡唇' in m['phase']),
                scope='Discrete surface samples of the actual gripper collision meshes, not continuous collision detection')
    (output/'gripper_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


def render(cfg,output):
    recorded=OmegaConf.load(output/'simulation_config.yaml')
    recorded_geometry=OmegaConf.to_container(recorded.install,resolve=True)
    current_geometry=OmegaConf.to_container(cfg.install,resolve=True)
    for geometry in (recorded_geometry,current_geometry):geometry.setdefault('base_bottom',.003)
    if recorded_geometry!=current_geometry:
        raise ValueError('Geometry differs from the recorded simulation')
    data=np.load(output/'trajectory.npz');meta=json.loads((output/'frames.json').read_text())
    table,ring,_,sensors=build(cfg,output,replay=True)
    if not np.allclose(points(ring.get_state().pos),data['initial'],atol=1e-7):raise ValueError('Vertex order mismatch')
    robot=table.manifest.get('robot');media=output/'preview' if cfg.run.preview else output;media.mkdir(exist_ok=True)
    fonts={s:ImageFont.truetype(FONT,s) for s in (18,24,30)}
    with ExitStack() as stack:
        writers={n:stack.enter_context(imageio.get_writer(media/f'{n}.mp4',fps=cfg.run.fps,codec='libx264',
                    quality=8,macro_block_size=1,ffmpeg_params=['-movflags','+faststart'])) for n in sensors} if not cfg.run.preview else {}
        for i,(ps,q,info) in enumerate(zip(data['positions'],data['qpos'],meta)):
            if cfg.run.preview and i%40 and i!=len(meta)-1:continue
            ring.set_pos(table.scene.sim.cur_substep_local,gs.tensor(ps[None],dtype=gs.tc_float))
            robot.set_qpos(q,zero_velocity=True)
            table.scene.visualizer.update_visual_states(force_render=True)
            next(iter(sensors.values()))._render_current_state()
            for name,sensor in sensors.items():
                im=Image.fromarray(nyx.rgb(sensor));draw=ImageDraw.Draw(im);w,h=im.size
                draw.rectangle((0,0,w,82),fill=(19,28,34));draw.rectangle((0,h-36,w,h),fill=(19,28,34))
                draw.text((18,8),'绳圈安装 · 夹取搬运 → 闭合夹爪推压',font=fonts[30 if w>=1200 else 24],fill=(240,245,239))
                draw.text((18,49),info['phase'],font=fonts[18],fill=(145,218,198))
                label={'agentview':'主视角','wrist':'腕部视角','front_oblique':'侧前方'}[name]
                draw.text((14,h-30),f'{label} | {info["time_s"]:05.2f}s | Robotiq 2F-85 接触推压 / FEM-IPC',font=fonts[18],fill=(205,211,212))
                if cfg.run.preview or i%100==0 or i==len(meta)-1:im.save(media/f'frame_{i:04d}_{name}.jpg',quality=93)
                if writers:writers[name].append_data(np.asarray(im))
            if i%40==0:print(f'render {i}/{len(meta)}',flush=True)
    if not cfg.run.preview:
        write_player(output)


def write_player(output):
    report=json.loads((output/'report.json').read_text())
    status='释放后整圈保持入槽' if report['success'] else '实验轨迹：尚未通过最终入槽检查'
    views=''.join(f'<section><h2>{title}</h2><video controls preload="metadata" src="{name}.mp4"></video>'
                  f'<p><a href="{name}.mp4" download>下载此视角</a></p></section>'
                  for name,title in [('agentview','主视角'),('wrist','腕部视角'),('front_oblique','侧前方视角')])
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>软环安装 · 夹取与闭合指端推压</title>
<style>body{background:#131c22;color:#edf1ec;font:17px/1.6 system-ui,sans-serif;max-width:1440px;margin:32px auto;padding:0 24px}a{color:#91dac6}video{width:100%;border-radius:12px}.views{display:grid;grid-template-columns:1fr 1fr;gap:24px}section:first-child{grid-column:1/-1}section{margin:8px 0}button{padding:10px 20px;margin:8px 12px 8px 0;cursor:pointer}@media(max-width:760px){.views{display:block}}</style>
<h1>闭合软环安装 · 3 段局部卡唇</h1>
<p>槽外张爪抓取 → 搬运放下 → 合拢指端 → 侧向推挤与下压 → 释放检查</p>
<p>Franka Panda + 原尺寸 Robotiq 2F-85。通过闭合夹爪本体接触软环完成推压。</p>
<p>STATUS · 三路视频来自同一份逐帧仿真记录。</p>
<p>仿真范围：FEM / IPC 软环与夹爪接触；机械臂按 IK 轨迹运动。搬运阶段使用两侧指垫接触后启用的局部抓持辅助，放下后解除；全部推压阶段均无材料位置约束。</p>
<p><a href="report.json">仿真报告</a> · <a href="trajectory_validation.json">轨迹验收</a> · <a href="gripper_audit.json">夹爪几何检查</a> · <a href="video_validation.json">视频检查</a></p>
<button id="play">从头同步播放</button><button id="pause">全部暂停</button>
<div class="views">VIEWS</div>
<script>const videos=[...document.querySelectorAll('video')];
document.querySelector('#play').onclick=async()=>{videos.forEach(v=>v.pause());videos.forEach(v=>v.currentTime=0);await Promise.all(videos.map(v=>v.play()));};
document.querySelector('#pause').onclick=()=>videos.forEach(v=>v.pause());
videos[0].addEventListener('seeked',()=>videos.slice(1).forEach(v=>{if(Math.abs(v.currentTime-videos[0].currentTime)>.15)v.currentTime=videos[0].currentTime;}));
</script></html>'''
    (output/'index.html').write_text(html.replace('STATUS',status).replace('VIEWS',views))


@hydra.main(version_base='1.3',config_path='../../configs',config_name='ring_lip_gripper')
def main(cfg):
    output=Path(cfg.run.output).resolve();output.mkdir(parents=True,exist_ok=True)
    cfg.env.cameras=OmegaConf.create({name:OmegaConf.to_container(cfg.env.cameras[name],resolve=True) for name in cfg.run.record_cameras})
    gs.init(backend=gs.cuda,logging_level='warning',seed=0)
    if not cfg.run.get('audit',False):
        OmegaConf.save(cfg,output/('simulation_config.yaml' if cfg.run.probe else 'render_config.yaml'),resolve=True)
    if cfg.run.get('audit',False):audit(cfg,output)
    elif cfg.run.probe:simulate(cfg,output)
    else:render(cfg,output)


if __name__=='__main__':main()
