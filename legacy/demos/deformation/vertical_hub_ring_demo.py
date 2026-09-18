"""Vertical grooved hub: one actual gripper grasp at a time, no fixture pins.

FEM/IPC resolves every unsupported part. Local soft grasp constraints represent
the currently closed gripper only. The arm follows prescribed IK poses.
"""
from contextlib import ExitStack
from html import escape
import json
from pathlib import Path
import time

import genesis as gs
import hydra
import imageio.v2 as imageio
import igl
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation
import trimesh

from demos.deformation.ring_lip_gripper_demo import GripperPose, CONTACT_LINKS, FONT, points, pad_gaps, downward_quat
from topogym.primitives.attachment import slerp
from topogym.primitives.fem_attachment import FEMRopeAttachment
from topogym.robot.gripper import as_numpy
from topogym.tasks_legacy.deformation._ring_lip_geometry import sector_mesh
from topogym.world import StandardTabletopSceneBuilder, nyx
from topogym.world.closed_band import closed_transport_frames, closed_tube_mesh, TOPDOWN_PROJECTION
from topogym.world.rope import tube_morph, write_obj
from topogym.world.rope_backends import rope_backend


def radial(angle):
    return np.array([0., np.sin(angle), np.cos(angle)])


def radial_quat(angle,tilt=0.):
    tangent=np.array([0., np.cos(angle), -np.sin(angle)])
    axis=-radial(angle)*np.cos(tilt)+np.array([np.sin(tilt),0.,0.])
    return Rotation.from_matrix(np.column_stack((tangent,np.cross(axis,tangent),axis))).as_quat()[[3,0,1,2]]


def hub_rotation(cfg):
    return Rotation.from_euler('z',cfg.get('axis_yaw_deg',0.),degrees=True)


def front_quat(tangent,axis=np.array([1.,0.,0.])):
    tangent=np.asarray(tangent).copy();tangent-=np.dot(tangent,axis)*axis
    tangent/=np.linalg.norm(tangent)
    return Rotation.from_matrix(np.column_stack((tangent,np.cross(axis,tangent),axis))).as_quat()[[3,0,1,2]]


def reading(vertices,cfg,top_indices=None,material_groups=None):
    d=hub_rotation(cfg).inv().apply(np.asarray(vertices)-np.asarray(cfg.center))
    r=np.linalg.norm(d[:,1:],axis=1)
    inside=(abs(d[:,0])<=cfg.groove_half_width+.001)&(r>=cfg.bed_radius-.001)&(r<=cfg.flange_radius+.001)
    angles=np.arctan2(d[:,1],d[:,2]);bins=np.linspace(-np.pi,np.pi,25)
    coverage=[int((inside&(angles>=a)&(angles<b)).sum()) for a,b in zip(bins[:-1],bins[1:])]
    result=dict(seated_fraction=float(inside.mean()),angular_bins_occupied=sum(n>0 for n in coverage),
                axial_range_mm=(1000*np.array([d[:,0].min(),d[:,0].max()])).tolist(),
                radial_range_mm=(1000*np.array([r.min(),r.max()])).tolist(),
                success=bool(inside.all() and all(n>0 for n in coverage)))
    if top_indices is not None:
        p=d[top_indices].mean(0);rr=np.linalg.norm(p[1:])
        in_groove=bool(abs(p[0])<=cfg.groove_half_width-cfg.tube_radius+.001
                    and cfg.bed_radius+cfg.tube_radius-.002<=rr<=cfg.flange_radius-.002)
        retained=bool(abs(p[0])<=cfg.groove_half_width+cfg.flange_thickness+cfg.tube_radius+.002
                    and cfg.bed_radius+cfg.tube_radius-.002<=rr<=cfg.flange_radius+cfg.tube_radius+.002 and p[2]>0)
        result.update(top_material_supported=retained,top_material_in_groove=in_groove,
                      initial_patch_angle_deg=float(np.degrees(np.arctan2(p[1],p[2]))),
                      top_material_center_mm=(p*1000).tolist())
    if material_groups is not None:
        line=np.asarray([d[ids].mean(0) for ids in material_groups])
        az=np.arctan2(line[:,1],line[:,2])
        winding=float(np.angle(np.exp(1j*(np.roll(az,-1)-az))).sum()/(2*np.pi))
        result.update(material_winding_about_axis=winding,
                      material_centerline_length_m=float(np.linalg.norm(np.roll(line,-1,axis=0)-line,axis=1).sum()))
        result['success']=bool(result['success'] and abs(abs(winding)-1)<1e-4)
    return result


def inside_solids(vertices,cfg,tolerance=.00015):
    d=hub_rotation(cfg).inv().apply(np.asarray(vertices)-np.asarray(cfg.center));r=np.linalg.norm(d[:,1:],axis=1)
    w=cfg.groove_half_width;t=cfg.flange_thickness
    inside=(r<cfg.bed_radius-tolerance)&(abs(d[:,0])<w-tolerance)
    inside|=(r>cfg.bed_radius-.004+tolerance)&(r<cfg.flange_radius-tolerance)&(abs(d[:,0])>w+tolerance)&(abs(d[:,0])<w+t-tolerance)
    inside|=(r<.018-tolerance)&(abs(d[:,0]-.055)<.045-tolerance)
    def box(center,half):return np.all(abs(d-np.asarray(center))<np.asarray(half)-tolerance,axis=1)
    inside|=box([.112,0,-cfg.center[2]/2],[.0275,.0325,cfg.center[2]/2])
    inside|=box([.10,0,.006-cfg.center[2]],[.085,.105,.006])
    return inside


def build(cfg,output,replay=False,with_cameras=True):
    g=cfg.hub;asset=output/'assets';asset.mkdir(parents=True,exist_ok=True)
    if not (2*g.tube_radius+.001<2*g.groove_half_width and g.flange_radius>g.bed_radius+2*g.tube_radius):
        raise ValueError('Hub groove does not contain the ring cross-section')
    backend=rope_backend(g.rope);origin=np.asarray(cfg.env.frames.task.origin)
    if replay:
        options={'fem_options':gs.options.FEMOptions()};static=gs.materials.Rigid(needs_coup=False);robot_mat=static
    else:
        backend.pre_scene();options=backend.scene_options();static=backend.static_rigid_material()
        robot_mat=gs.materials.Rigid(coup_type='two_way_soft_constraint',coup_links=CONTACT_LINKS,
                                    coup_friction=float(cfg.gripper_demo.contact_friction))
    builder=StandardTabletopSceneBuilder(cfg.env,cfg.robot_control,scene_options=options)
    table=builder.create(show_viewer=False,include_robot=True,robot_material=robot_mat,table_material=static,
                        static_material=static,decoration_material=gs.materials.Rigid(needs_coup=False))
    scene=table.scene;manifest=table.manifest;center=origin+np.asarray(g.center);solids={}
    frame=hub_rotation(g);rot=(frame*Rotation.from_euler('y',90,degrees=True)).as_matrix()
    def solid(name,mesh,color,at=center):
        path=asset/f'{name}.obj'
        if replay:
            if not path.exists():raise FileNotFoundError(f'Missing recorded fixture geometry: {path}')
            mesh=trimesh.load(path,force='mesh',process=False)
        else:mesh.export(path)
        entity=scene.add_entity(gs.morphs.Mesh(file=str(path),pos=tuple(at),fixed=True,convexify=False,
            decimate=False,file_meshes_are_zup=True),material=static,
            surface=gs.surfaces.Plastic(color=color,roughness=.45),name=name)
        manifest.add(name,entity);solids[name]=(mesh,np.asarray(at))
    def cylinder(radius,length):
        mesh=trimesh.creation.cylinder(radius=radius,height=length,sections=128)
        mesh.vertices=mesh.vertices@rot.T;return mesh
    width=float(g.groove_half_width);thickness=float(g.flange_thickness)
    solid('hub_bed',cylinder(g.bed_radius,2*width),(.43,.50,.53))
    for side in (-1,1):
        a,b=sorted((side*width,side*(width+thickness)))
        mesh=sector_mesh(g.bed_radius-.004,g.flange_radius,a,b)
        mesh.vertices=mesh.vertices@rot.T
        solid('front_flange' if side<0 else 'rear_flange',mesh,(.72,.51,.23))
    solid('hub_axle',cylinder(.018,.090),(.30,.35,.39),center+frame.apply([.055,0,0]))
    pedestal=trimesh.creation.box(extents=[.055,.065,g.center[2]])
    pedestal.vertices=frame.apply(pedestal.vertices)
    solid('hub_pedestal',pedestal,(.33,.39,.43),center+frame.apply([.112,0,-g.center[2]/2]))
    foot=trimesh.creation.box(extents=[.17,.21,.012])
    foot.vertices=frame.apply(foot.vertices)
    solid('hub_foot',foot,(.30,.35,.38),center+frame.apply([.10,0,.006-g.center[2]]))
    theta=np.linspace(0,2*np.pi,144,endpoint=False)
    line=np.c_[g.ring_radius*np.cos(theta),g.ring_radius*np.sin(theta),np.full(len(theta),g.source_z)]
    frames=closed_transport_frames(line,tube_radius=g.tube_radius,projection=TOPDOWN_PROJECTION)
    v,f=closed_tube_mesh(line,frames,radius=g.tube_radius,radial_segments=8)
    spawn=origin+np.r_[g.source_center,0.]
    write_obj(asset/'ring.obj',v+spawn,f)
    ring=scene.add_entity(tube_morph(asset/'ring.obj',g.rope),material=backend.material(),
            surface=gs.surfaces.Plastic(color=(.09,.47,.40),roughness=.65),name='elastic_ring')
    manifest.add('elastic_ring',ring);grasps=[]
    if not replay:
        for angle in np.linspace(0,2*np.pi,8,endpoint=False):
            p=spawn+np.array([g.ring_radius*np.cos(angle),g.ring_radius*np.sin(angle),g.source_z])
            grasps.append(FEMRopeAttachment(ring,p,cfg.gripper_demo.pickup_patch_radius,strength=g.rope.fem.follow_strength))
    builder.finalize(table)
    sensors={name:table.cameras[name].sensor for name in cfg.run.record_cameras} if replay and with_cameras else {}
    return table,ring,grasps,sensors,solids


def simulate(cfg,output):
    cfg.env.cameras=OmegaConf.create({});table,ring,grasps,_,_=build(cfg,output)
    robot=GripperPose(table,cfg);scene=table.scene;g=cfg.hub;d=cfg.gripper_demo
    if g.get('initial_arm_qpos') is not None:
        robot.q[:7]=g.initial_arm_qpos;robot.robot.set_qpos(robot.q,zero_velocity=True)
        robot.pos=points(robot.hand.get_pos())[0];robot.quat=as_numpy(robot.hand.get_quat()).reshape(4)
    frame=hub_rotation(g);axis=frame.apply([1.,0.,0.])
    def rdir(angle):return frame.apply(radial(angle))
    def rquat(angle,tilt=0.):return (frame*Rotation.from_quat(radial_quat(angle,tilt)[[1,2,3,0]])).as_quat()[[3,0,1,2]]
    origin=np.asarray(cfg.env.frames.task.origin);center=origin+np.asarray(g.center)
    initial=points(ring.get_state().pos).copy();elements=as_numpy(ring.get_el2v()).astype(int)
    source=origin+np.r_[g.source_center,0.]
    initial_angles=np.arctan2(initial[:,1]-source[1],initial[:,0]-source[0])
    edges=np.linspace(-np.pi,np.pi,33)
    material_groups=[np.flatnonzero((initial_angles>=a)&(initial_angles<b)) for a,b in zip(edges[:-1],edges[1:])]
    rest=initial[elements];inverse=np.linalg.inv(np.stack([rest[:,i]-rest[:,0] for i in (1,2,3)],2))
    active=None;local=None;step=0;dt=float(cfg.env.sim.dt);stride=round(1/(dt*cfg.run.fps))
    states=[];joints=[];meta=[];phases=[];grasp_checks=[];maxstrain=0.;minvolume=1.;completed=False;error=None
    start_time=time.monotonic()
    def state():return reading(points(ring.get_state().pos)-origin,g,grasps[0].indices,material_groups)
    def move(seconds,label,pos=None,quat=None,gap=None):
        nonlocal step,maxstrain,minvolume
        start=robot.pos.copy();sq=robot.quat.copy();sg=robot.half_gap
        end=start if pos is None else np.asarray(pos);eq=sq if quat is None else np.asarray(quat);eg=sg if gap is None else gap
        count=max(1,round(seconds/dt))
        for k in range(1,count+1):
            u=k/count;u=u*u*(3-2*u)
            missed=robot.target(start+u*(end-start),slerp(sq,eq,u),sg+u*(eg-sg))
            if missed>.003:raise RuntimeError(f'IK error in {label}: {missed*1000:.2f} mm')
            if active is not None:
                hp=points(robot.hand.get_pos())[0];hq=as_numpy(robot.hand.get_quat()).reshape(4)
                grasps[active]._handle.update_targets(hp+Rotation.from_quat(hq[[1,2,3,0]]).apply(local))
            scene.step();step+=1
            if step%stride==0:
                ps=points(ring.get_state().pos).copy();tet=ps[elements]
                F=np.stack([tet[:,i]-tet[:,0] for i in (1,2,3)],2)@inverse
                maxstrain=max(maxstrain,float(abs(np.linalg.svd(F,compute_uv=False)-1).max()))
                minvolume=min(minvolume,float(np.linalg.det(F).min()))
                states.append(ps);joints.append(as_numpy(robot.robot.get_qpos()).reshape(-1).copy())
                meta.append(dict(frame=len(meta),time_s=step*dt,phase=label,active_grasp=active,
                    half_gap_m=robot.half_gap,**state()))
                if maxstrain>g.max_principal_strain or minvolume<=0:
                    raise RuntimeError('Numerical deformation limit exceeded')
            if step%100==0:print(f'{label}: t={step*dt:.1f} seated={meta[-1]["seated_fraction"]:.3f} '
                f'top={meta[-1]["top_material_supported"]} strain={maxstrain:.3f} wall={time.monotonic()-start_time:.1f}',flush=True)
        phases.append(dict(phase=label,time_s=step*dt,**state()))
    def engage(index):
        nonlocal active,local
        if active is not None:raise RuntimeError('Only one gripper grasp may be active')
        ps=points(ring.get_state().pos)[grasps[index].indices]
        gaps=pad_gaps(robot.robot,ps);grasp_checks.append(dict(material_patch=index,time_s=step*dt,
            pad_surface_gaps_mm={n:v*1000 for n,v in gaps.items()}))
        if max(gaps.values())>.002:raise RuntimeError(f'Both pads did not contact patch {index}: {gaps}')
        hp=points(robot.hand.get_pos())[0];hq=as_numpy(robot.hand.get_quat()).reshape(4)
        local=Rotation.from_quat(hq[[1,2,3,0]]).inv().apply(ps-hp)
        grasps[index].attach(ps.mean(0));active=index
    def carry(seconds,label,target,quat=None):
        q=robot.quat if quat is None else np.asarray(quat)
        hand=np.asarray(target)-Rotation.from_quat(q[[1,2,3,0]]).apply(local.mean(0))
        move(seconds,label,pos=hand,quat=q)
    def release(label,direction):
        nonlocal active,local
        grasps[active].release();active=None;local=None
        move(.6,label,gap=g.release_half_gap)
        move(.8,'抬离轮缘，松手观察',pos=robot.pos+.065*np.asarray(direction))
        move(.5,'张爪准备换抓',gap=d.open_half_gap)
    try:
        move(1.,'桌面上的自由弹性圈')
        p=grasps[0].band_center();q=downward_quat(0.);tip=robot.pad_tip_local(d.grasp_half_gap)
        hand=p+np.array([0,0,-g.tube_radius+.0007])-Rotation.from_quat(q[[1,2,3,0]]).apply(tip)
        move(1.4,'张爪接近桌面绳圈',pos=hand+[0,0,.09],quat=q,gap=d.open_half_gap)
        move(.8,'对准局部绳段',pos=hand)
        move(.8,'合拢夹爪抓取',gap=d.grasp_half_gap);engage(0)
        move(2.,'提起，观察自由段下垂',pos=robot.pos+[0,0,g.source_lift])
        if cfg.run.strategy=='bottom_first':
            q=rquat(0.,np.radians(g.bottom_tilt_deg))
            carry(3.,'转动绳圈，让下方自由弧段接近轮缘',center+frame.apply([-.09,0,g.bottom_start_radius]),q)
            carry(1.,'从下方绕过轮缘，建立接触',center+frame.apply([-.04,0,g.bottom_start_radius]))
            carry(2.,'尝试保持下方接触，向上展开绳圈',center+frame.apply([-.04,0,g.bottom_finish_radius]))
            carry(1.,'把上方抓持段送过轮缘',center+frame.apply([0,0,g.bottom_finish_radius]))
            release('松爪，让弹性圈自行回落',-axis)
            move(1.,'撤开机械臂',pos=robot.pos-axis*.06+[0,0,.07])
            move(float(g.release_s),'无夹持释放保持检查');completed=True
            return
        hook_quat=rquat(0.,np.radians(g.hook_tilt_deg))
        carry(2.,'转到轮面方向，搬到前上方',center+frame.apply([-.065,0,g.hook_radius]),hook_quat)
        carry(1.,'让上方弧段越过连续轮缘',center+g.hook_radius*rdir(0.))
        if g.get('hook_seat_radius',0):
            carry(1.5,'调整夹爪方向，保留轮面上的自由弧段',center+g.hook_radius*rdir(0.),rquat(0.))
            carry(1.,'把上方短段放入凹槽',center+g.hook_seat_radius*rdir(0.))
        move(.5,'让自由弧段与轮毂接触')
        release('松开上段，让轮毂承托',rdir(0.) if g.get('hook_seat_radius',0) else -axis)
        move(1.2,'检查无夹持的上段保持')
        if not state()['top_material_supported']:raise RuntimeError('The hub did not retain the released top material')
        if cfg.run.stage=='top_only':return
        order=[4] if cfg.run.strategy=='straight_pull' else [2,6,4]
        for index in order:
            p=grasps[index].band_center();a=index*np.pi/4
            current=frame.inv().apply(p-center);rr=np.linalg.norm(current[1:])
            if abs(current[0])<g.groove_half_width-g.tube_radius and g.bed_radius<rr<g.flange_radius-g.tube_radius:
                phases.append(dict(phase=f'材料段 {index} 已由接触自然就位',time_s=step*dt,**state()));continue
            tangent=grasps[(index+1)%8].band_center()-grasps[(index-1)%8].band_center()
            q=front_quat(tangent,axis);tip=robot.pad_tip_local(d.grasp_half_gap)
            hand=p-Rotation.from_quat(q[[1,2,3,0]]).apply(tip-[0,0,g.tube_radius-.0007])
            move(1.2,f'从前侧访问自由段 {index}',pos=hand-.07*axis,quat=q,gap=d.open_half_gap)
            move(.8,f'对准自由段 {index}',pos=hand)
            move(.8,f'换抓材料段 {index}',gap=d.grasp_half_gap);engage(index)
            target=center+g.clearance_radius*rdir(a)-.065*axis
            carry(1.8,'直接下拉自由段' if cfg.run.strategy=='straight_pull' else f'展开并绕向轮毂第 {index} 段',target)
            carry(1.3,f'调整抓持方向，接近第 {index} 段',target,rquat(a))
            carry(1.,f'第 {index} 段越过轮缘',center+g.clearance_radius*rdir(a))
            release(f'释放第 {index} 段，观察其余部分',rdir(a))
            move(.7,'检查已装部分与剩余自由段')
        move(1.2,'撤开机械臂',pos=robot.pos+[-.08,-.06,.10])
        move(float(g.release_s),'无夹持释放保持检查');completed=True
    except Exception as exc:
        error=str(exc);raise
    finally:
        for grasp in grasps:grasp.release()
        hold=[m for m in meta if m['phase']=='无夹持释放保持检查']
        final=state();final.update(success=bool(completed and final['success'] and hold and all(m['success'] for m in hold)),
            completed=completed,error=error,strategy=cfg.run.strategy,stage=cfg.run.stage,
            frames=len(meta),fps=cfg.run.fps,simulation_seconds=step*dt,wall_seconds=time.monotonic()-start_time,
            max_principal_strain=maxstrain,min_tet_volume_ratio=minvolume,max_ik_error_mm=robot.max_error*1000,
            grasp_assist_disabled_observation_seconds=len(hold)/cfg.run.fps,phase_reports=phases,grasp_checks=grasp_checks,
            installed_material_constraints=0,maximum_simultaneous_grasps=1,
            scope='FEM/IPC; one local assisted gripper grasp; prescribed IK arm; no hub attachment or installed-region pins')
        np.savez_compressed(output/'trajectory.npz',positions=np.asarray(states,dtype=np.float32),
            qpos=np.asarray(joints,dtype=np.float32),initial=initial,elements=elements,
            top_indices=grasps[0].indices)
        (output/'frames.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
        (output/'report.json').write_text(json.dumps(final,ensure_ascii=False,indent=2))
        print(json.dumps(final,ensure_ascii=False,indent=2),flush=True)


def audit(cfg,output):
    cfg.env.cameras=OmegaConf.create({});table,_,_,_,_=build(cfg,output,replay=True,with_cameras=False)
    robot=table.manifest.get('robot');origin=np.asarray(cfg.env.frames.task.origin)
    data=np.load(output/'trajectory.npz');meta=json.loads((output/'frames.json').read_text())
    weights=np.asarray([(i/3,j/3,1-(i+j)/3) for i in range(4) for j in range(4-i)])
    geoms=[geom for name in CONTACT_LINKS for geom in robot.get_link(name).geoms]
    arm_geoms=[(link.name,geom) for link in robot.links if link.name not in CONTACT_LINKS for geom in link.geoms]
    violations=[];arm_violations=[];material_violations=[];material_arm_violations=[];minimum_table=float('inf')
    for frame,q in enumerate(data['qpos']):
        robot.set_qpos(q,zero_velocity=True);count=0
        for geom in geoms:
            v=points(geom.get_verts())-origin;faces=np.asarray(geom.init_faces,dtype=int)
            samples=np.einsum('ki,fij->fkj',weights,v[faces]).reshape(-1,3)
            minimum_table=min(minimum_table,float(samples[:,2].min()))
            count+=int(inside_solids(samples,cfg.hub).sum())
        if count:violations.append(dict(frame=frame,time_s=meta[frame]['time_s'],phase=meta[frame]['phase'],samples=count))
        for name,geom in arm_geoms:
            v=points(geom.get_verts())-origin;faces=np.asarray(geom.init_faces,dtype=int)
            samples=np.einsum('ki,fij->fkj',weights,v[faces]).reshape(-1,3)
            count=int(inside_solids(samples,cfg.hub).sum())
            if count:arm_violations.append(dict(frame=frame,link=name,samples=count))
            distance,*_=igl.signed_distance((data['positions'][frame]-origin).astype(float),v.astype(float),faces)
            count=int((distance<-.00015).sum())
            if count:material_arm_violations.append(dict(frame=frame,link=name,nodes=count))
        count=int(inside_solids(data['positions'][frame]-origin,cfg.hub).sum())
        if count:material_violations.append(dict(frame=frame,nodes=count))
    result=dict(sampled_frames=len(meta),fixture_intrusion_frames=violations,minimum_table_clearance_mm=minimum_table*1000,
                arm_fixture_intrusions=arm_violations,material_fixture_intrusions=material_violations,
                material_arm_intrusions=material_arm_violations,
                minimum_ring_table_clearance_mm=float((data['positions'][:,:,2]-origin[2]).min()*1000),
                tolerance_mm=.15,scope='Discrete samples of collision triangles and FEM nodes, not continuous collision detection')
    (output/'gripper_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    release_audit(cfg,output,robot)


def release_audit(cfg,output,robot=None):
    """Opening the gripper or disabling its assist does not prove release."""
    if robot is None:
        cfg.env.cameras=OmegaConf.create({});table,_,_,_,_=build(cfg,output,replay=True,with_cameras=False)
        robot=table.manifest.get('robot')
    origin=np.asarray(cfg.env.frames.task.origin);data=np.load(output/'trajectory.npz')
    meta=json.loads((output/'frames.json').read_text());samples=[]
    geoms=[geom for name in CONTACT_LINKS for geom in robot.get_link(name).geoms]
    for i,m in enumerate(meta):
        if m['phase'] not in ('无夹持释放保持检查','张爪后观察最终接触状态'):continue
        robot.set_qpos(data['qpos'][i],zero_velocity=True);minimum=float('inf')
        for geom in geoms:
            distance,*_=igl.signed_distance((data['positions'][i]-origin).astype(float),
                (points(geom.get_verts())-origin).astype(float),np.asarray(geom.init_faces,dtype=int))
            minimum=min(minimum,float(abs(distance).min()))
        samples.append(dict(frame=i,time_s=m['time_s'],minimum_tool_clearance_mm=minimum*1000))
    result=dict(tool_clear_during_observation=bool(samples and all(s['minimum_tool_clearance_mm']>3 for s in samples)),
                clearance_threshold_mm=3.,observation_seconds=len(samples)/cfg.run.fps,samples=samples,
                scope='Distance to all real gripper collision meshes; assist-off alone is not accepted as release')
    (output/'release_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('Tool fully clear during observation:',result['tool_clear_during_observation'],flush=True)


def render(cfg,output):
    recorded=OmegaConf.load(output/'simulation_config.yaml')
    if OmegaConf.to_container(recorded.hub,resolve=True)!=OmegaConf.to_container(cfg.hub,resolve=True):
        raise ValueError('Hub geometry or material differs from the simulation')
    data=np.load(output/'trajectory.npz');meta=json.loads((output/'frames.json').read_text())
    report=json.loads((output/'report.json').read_text())
    inspection=json.loads((output/'inspection.json').read_text()) if (output/'inspection.json').exists() else {}
    title='竖直轮毂 · 弹性绳圈安装' if report['success'] else '竖直轮毂 · 诊断原型（未完成安装）'
    table,ring,_,sensors,_=build(cfg,output,replay=True)
    if not np.allclose(points(ring.get_state().pos),data['initial'],atol=1e-7):raise ValueError('FEM vertex order differs')
    robot=table.manifest.get('robot');media=output/'preview' if cfg.run.preview else output;media.mkdir(exist_ok=True)
    fonts={s:ImageFont.truetype(FONT,s) for s in (18,24,30)}
    with ExitStack() as stack:
        writers={name:stack.enter_context(imageio.get_writer(media/f'{name}.mp4',fps=cfg.run.fps,codec='libx264',
            quality=8,macro_block_size=1,ffmpeg_params=['-movflags','+faststart'])) for name in sensors} if not cfg.run.preview else {}
        for i,(v,q,m) in enumerate(zip(data['positions'],data['qpos'],meta)):
            if cfg.run.preview and i%40 and i!=len(meta)-1:continue
            ring.set_pos(table.scene.sim.cur_substep_local,gs.tensor(v[None],dtype=gs.tc_float));robot.set_qpos(q,zero_velocity=True)
            table.scene.visualizer.update_visual_states(force_render=True);next(iter(sensors.values()))._render_current_state()
            for name,sensor in sensors.items():
                im=Image.fromarray(nyx.rgb(sensor));draw=ImageDraw.Draw(im);w,h=im.size
                draw.rectangle((0,0,w,82),fill=(19,28,34));draw.rectangle((0,h-36,w,h),fill=(19,28,34))
                draw.text((18,8),title,font=fonts[30 if w>=1200 else 24],fill=(240,245,239))
                phase='张爪后观察最终接触状态' if m['phase']=='无夹持释放保持检查' else m['phase']
                if m['phase']=='无夹持释放保持检查' and inspection.get('result')=='gripper_hang':
                    phase='张爪后观察：绳圈仍挂在手指上'
                draw.text((18,49),phase,font=fonts[18],fill=(145,218,198))
                label={'agentview':'主视角','wrist':'腕部视角','front_oblique':'轮毂近景'}[name]
                draw.text((14,h-30),f'{label} | {m["time_s"]:05.2f}s | 单臂抓持 / FEM-IPC 接触',font=fonts[18],fill=(205,211,212))
                if cfg.run.preview or i%100==0 or i==len(meta)-1:im.save(media/f'frame_{i:04d}_{name}.jpg',quality=93)
                if writers:writers[name].append_data(np.asarray(im))
            if i%40==0:print(f'render {i}/{len(meta)}',flush=True)
    if not cfg.run.preview:write_index(output)


def write_index(output):
    report=json.loads((output/'report.json').read_text())
    successful=report['success']
    status='已完成安装与松手保持' if successful else '诊断演示：本次未完成安装'
    note=('这是一条安装轨迹；尚未证明复杂协调是必要的。' if successful else
          '本次展示实际抓取、下垂和接触结果；尚未验证成功安装，也不能据此宣称任务必需复杂策略。')
    if (output/'inspection.json').exists():
        note+=' '+escape(json.loads((output/'inspection.json').read_text())['observation'])
    videos=''.join(f'<section><h2>{name}</h2><video controls preload="metadata" playsinline '
        f'poster="frame_0000_{key}.jpg" src="{key}.mp4"></video><a href="{key}.mp4">下载视频</a></section>'
        for key,name in [('agentview','主视角'),('wrist','腕部视角'),('front_oblique','轮毂近景')])
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>竖直轮毂与弹性绳圈</title><style>
body{{margin:0;background:#10191e;color:#e8efed;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1600px;margin:auto;padding:28px}}
h1{{font-size:29px}}h2{{font-size:18px}}a{{color:#91ddc8}}.status{{color:#f0c986}}.videos{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}
.videos section:first-child{{grid-column:1/-1}}video{{width:100%;background:#000}}button{{padding:9px 18px;margin:4px 10px 14px 0;cursor:pointer}}
input{{width:100%}}details{{margin:24px 0}}@media(max-width:800px){{.videos{{display:block}}}}
</style><main><h1>竖直轮毂 · FEM 弹性绳圈</h1><p class="status">{status}</p><p>{note}</p>
<button id="play">同步播放</button><button id="pause">全部暂停</button><button id="restart">从头播放</button>
<input id="scrub" type="range" min="0" max="{report['simulation_seconds']}" step="0.05" value="0" aria-label="三个视角的共同播放时间">
<div class="videos">{videos}</div><details><summary>实验记录与边界</summary>
<p>{report['simulation_seconds']:.2f} 秒，{report['frames']} 帧，{report['fps']} FPS。三个视角来自同一次物理仿真。</p>
<p>Franka Panda + 原尺寸 Robotiq 2F-85。当前抓取小段使用局部辅助约束；轮毂和已安装材料之间没有固定约束。机械臂跟随 IK 姿态。</p>
<p>最大主应变 {report['max_principal_strain']:.3f}，最小单元体积比 {report['min_tet_volume_ratio']:.3f}。这些是数值记录，不代表真实材料强度标定。</p>
<p>终止信息：{escape(str(report['error'] or '脚本执行结束'))}</p>
<a href="report.json">物理结果</a> · <a href="gripper_audit.json">几何检查</a> · <a href="trajectory_validation.json">轨迹验证</a> ·
<a href="release_audit.json">实际脱离工具检查</a> ·
<a href="../../../docs/progress/2026-09-15_vertical_hub_ring_assessment_zh.md">任务评估</a></details></main>
<script>
const vs=[...document.querySelectorAll('video')],s=document.querySelector('#scrub');
const sync=t=>vs.forEach(v=>{{v.currentTime=t}});
const play=()=>Promise.allSettled(vs.map(v=>v.play()));
document.querySelector('#play').onclick=()=>{{sync(vs[0].currentTime);play()}};
document.querySelector('#pause').onclick=()=>vs.forEach(v=>v.pause());
document.querySelector('#restart').onclick=()=>{{sync(0);play()}};
s.oninput=()=>sync(+s.value);vs[0].ontimeupdate=()=>{{s.value=vs[0].currentTime}};
</script></html>'''
    (output/'index.html').write_text(page)


@hydra.main(version_base='1.3',config_path='../../configs',config_name='vertical_hub_ring')
def main(cfg):
    output=Path(cfg.run.output).resolve();output.mkdir(parents=True,exist_ok=True)
    auditing=cfg.run.get('audit',False) or cfg.run.get('release_audit',False)
    if not cfg.run.probe or auditing:
        recorded=OmegaConf.load(output/'simulation_config.yaml')
        cfg.hub=recorded.hub
    cfg.env.cameras=OmegaConf.create({name:OmegaConf.to_container(cfg.env.cameras[name],resolve=True) for name in cfg.run.record_cameras})
    gs.init(backend=gs.cuda,logging_level='warning',seed=0)
    if not auditing:
        OmegaConf.save(cfg,output/('simulation_config.yaml' if cfg.run.probe else 'render_config.yaml'),resolve=True)
    if cfg.run.get('audit',False):audit(cfg,output)
    elif cfg.run.get('release_audit',False):release_audit(cfg,output)
    elif cfg.run.probe:simulate(cfg,output)
    else:render(cfg,output)


if __name__=='__main__':main()
