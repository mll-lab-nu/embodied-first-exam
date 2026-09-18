"""Run the staged-lock task with full Franka, passive contacts and grasp weld.

    .venv-gs121-nyx/bin/python -m topogym.tasks.lock_picking.runner
    ... --config-name lock_picking_baseline task.variant=asymmetric task.seed=3
"""
from dataclasses import asdict
from pathlib import Path
from contextlib import ExitStack
import json
import traceback
import subprocess
from importlib.metadata import version
import genesis as gs
import hydra
import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image
from omegaconf import OmegaConf

from topogym.tasks.lock_picking.scene import LockPickingSceneBuilder, numpy
from topogym.tasks.lock_picking.planner import next_entry_angle, insertion_window
from topogym.tasks.lock_picking.grasp import StagedLockGrasp, hand_pose, actual_hand_pose
from scipy.spatial.transform import Rotation
from topogym.primitives.attachment import slerp
from topogym.utils.franka import initialize_franka_controller
from topogym.tasks.lock_picking.evaluator import StagedLockEvaluator
from topogym.world import nyx


def media_index(output,names):
    if json.loads((output/'report.json').read_text()).get('retreat_certificate'):
        from .review import write_review
        write_review(output,names)
        return
    # Preserve the historical four-view overview. Policy profiles produce only
    # their selected, synchronized sensor streams, with no diagnostic fourth view.
    overview=len(names)==4
    if overview:
        inputs=[]
        for name in names: inputs.extend(['-i',str(output/f'{name}.mp4')])
        graph=';'.join(f'[{i}:v]scale=960:540[v{i}]' for i in range(4))
        graph+=';[v0][v1]hstack[top];[v2][v3]hstack[bottom];[top][bottom]vstack[out]'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error',*inputs,
            '-filter_complex',graph,'-map','[out]','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
            '-movflags','+faststart',str(output/'overview.mp4')],check=True)
    html=['<!doctype html><meta charset="utf-8"><title>Staged lock task</title>',
          '<style>body{background:#17212a;color:#eee;font:18px sans-serif;margin:28px} '
          'video,img{max-width:100%}a{color:#8cddff}</style>',
          '<h1>Staged Lock：完整机械臂与接触执行</h1>',
          '<p>Genesis 物理执行 / Nyx 原始相机观察。各路帧号与时间一致。</p>',
          '<p>钥匙从实体承托台抓起；双指接触后启用辅助抓持。圆盘由钥匙碰撞带动。</p>']
    if overview: html.append('<video controls src="overview.mp4"></video>')
    html.append('<p><a href="report.json">运行报告</a> · <a href="camera_rig.json">相机标定</a></p>')
    for name in names:
        html.append(f'<h2>{name}</h2><video controls src="{name}.mp4"></video>')
    (output/'index.html').write_text('\n'.join(html),encoding='utf-8')


def move(controller,pos,quat,steps):
    start=controller.hand_pos();start_q=controller.hand_quat()
    count=max(1,int(steps)//5)
    for i in range(1,count+1):
        t=i/count
        controller.move_ee_to(start+(np.asarray(pos)-start)*t,quat=slerp(start_q,quat,t),
                              continuous_ik=True,steps=5)
    controller.step(120)
    error=float(np.linalg.norm(controller.hand_pos()-pos))
    if error>getattr(controller,'task_follow_error',.012):
        raise RuntimeError(f'Arm missed commanded pose by {error:.4f} m')
    return error


def open_before_withdrawal(task, controller, status):
    """Wait for measured aperture and loss of key contact before withdrawing."""
    status['phase']='release_open'
    controller.open_gripper(0)
    # Retreat is along the handle axis, so the handle radius determines the
    # swept clearance. A nominal maximum opening can remain unreachable under
    # linkage loading even after the actual fingers safely clear the handle.
    goal=float(task.layout.handle_radius)+.010
    if float(controller.cfg.gripper.open_qpos)<goal:
        raise RuntimeError('Configured gripper opening cannot clear the key handle')
    stable=0
    limit=int(np.ceil(8./float(task.scene.dt)))
    for step in range(limit):
        controller.step(1)
        contacts=controller.robot.get_contacts(with_entity=task.key)
        forces=numpy(contacts['force_a']).reshape(-1,3)
        contact_force=float(np.linalg.norm(forces,axis=1).sum()) if forces.size else 0.
        half_gap=float(np.min(controller.gripper_qpos()))
        status.update(release_required_half_gap_m=goal,release_measured_half_gap_m=half_gap,
                      release_robot_key_force_N=contact_force)
        opened=half_gap>=goal
        stable=stable+1 if opened and contact_force<.01 else 0
        if stable>=20:
            status['release_open_wait_s']=(step+1)*float(task.scene.dt)
            status['release_measured_half_gap_m']=float(np.min(controller.gripper_qpos()))
            status['release_robot_key_force_N']=contact_force
            status['phase']='release_withdraw'
            return
    raise RuntimeError(f'Gripper did not physically open and clear the key within 8 seconds: '
                       f'half_gap={half_gap:.6f}, required={goal:.6f}, contact={contact_force:.6f} N')


def execute(task,c,status,decisions):
    g=task.layout
    assist=StagedLockGrasp(task,c)
    motion=task.cfg.motion
    c.task_follow_error=float(task.cfg.assist.max_follow_error)
    status['phase']='initial_rest'
    c.step(int(task.cfg.initialization.hold_steps))
    pos,q=actual_hand_pose(task)
    status['phase']='approach'
    # Clear the enlarged, lowered mechanism before rotating the gripper.
    # Rotating while translating directly from home sweeps a finger through it.
    move(c,c.hand_pos()+np.array([0,0,.23]),c.hand_quat(),200)
    # The longer 2F-85 puts the flange farther behind the grasp reference.
    # Approach vertically over the handle to avoid an unreachable folded wrist.
    backoff=0. if getattr(c,'is_robotiq',False) else -.08
    move(c,pos+np.array([backoff,0,.20]),q,300)
    move(c,pos,q,200)
    c.set_gripper(float(motion.grasp_qpos),steps=c.gripper_settle_steps(100))
    status['phase']='grasp'
    if bool(task.cfg.assist.enabled): assist.attach()
    status['grasp_weld']=assist.active
    try:
        status['phase']='pickup_lift'
        # Clear the real V blocks before leveling the free key at the entrance.
        move(c,c.hand_pos()+np.array([0,0,.045]),c.hand_quat(),180)
        status['phase']='entry_align'
        state=task.state()
        pos,q=hand_pose(g,0.,state['key_deg'],roll_bias_deg=float(motion.get('grasp_roll_bias_deg',0.)))
        move(c,pos,q,180)
        limited=str(motion.get('strategy','free_discs'))=='limited_reindex'
        if limited:
            from topogym.tasks.lock_picking.oracle import execute_reindex
            execute_reindex(task,c,move,status,decisions)
        for level in ([] if limited else range(4)):
            state=task.state()
            target=next_entry_angle(g,state,level)
            if status.get('oracle_mode')=='blind': target=0.
            status['phase']=f'align_{level+1}'
            pos,q=hand_pose(g,state['depth'],target)
            move(c,pos,q,int(motion.turn_steps))
            state=task.state()
            if status.get('oracle_mode')!='blind':
                for _ in range(3):
                    state=task.state()
                    direction,margin=insertion_window(g,state,level)
                    pos,q=hand_pose(g,state['depth'],direction)
                    move(c,pos,q,100)
            else: direction,margin=0.,None
            decisions.append(dict(level=level+1,before=state,target_angle=target,insertion_angle=direction,margin=margin))
            print(f'Before insert {level+1}: {task.state()}',flush=True)
            status['phase']=f'insert_{level+1}'
            pos,q=hand_pose(g,level+1,direction)
            move(c,pos,q,int(motion.move_steps))
            actual=task.state()
            if abs(actual['depth']-(level+1))>.04 and status.get('oracle_mode')!='blind':
                # A blocked move can leave a passive disc at a contact edge.
                # Re-read it, center within the common window, and retry once.
                direction,margin=insertion_window(g,actual,level)
                pos,q=hand_pose(g,actual['depth'],direction)
                move(c,pos,q,100)
                pos,q=hand_pose(g,level+1,direction)
                move(c,pos,q,int(motion.move_steps))
                actual=task.state()
            print(f'Level {level+1}: {actual}',flush=True)
            if abs(actual['depth']-(level+1))>.04:
                raise RuntimeError(f'Insertion blocked at level {level+1}: {actual}')
        status['phase']='release'
        assist.detach();status['grasp_weld']=False
        if bool(motion.get('measured_release_gate',False)):
            open_before_withdrawal(task,c,status)
        else:
            c.open_gripper(c.gripper_settle_steps(80) if limited else 80)
        if limited:
            move(c,c.hand_pos()+np.array([-.07,0,0]),c.hand_quat(),180)
        move(c,c.hand_pos()+np.array([-.09,0,.07]),c.hand_quat(),160)
        status['phase']='settle'
        c.step(int(task.cfg.success.hold_steps))
        return assist.attach_error
    finally:
        assist.detach();status['grasp_weld']=False


def run(cfg, scene_builder=LockPickingSceneBuilder):
    output=Path(cfg.run.output).resolve();output.mkdir(parents=True,exist_ok=True)
    # Select actual policy/recording sensors, preserving the shared wrist rig.
    names=list(cfg.run.record_cameras)
    exterior_names=list(cfg.run.exterior_cameras)
    if len(set(names))!=len(names) or 'wrist' not in names or not set(exterior_names).issubset(names):
        raise ValueError('Select unique cameras including wrist and all exterior_cameras')
    cfg.env.cameras=OmegaConf.create({name:OmegaConf.to_container(cfg.env.cameras[name],resolve=True)
        for name in names})
    gs.init(backend=gs.cuda if str(cfg.env.genesis.backend)=='cuda' else gs.cpu,logging_level='warning',seed=int(cfg.task.seed))
    is_nyx=str(cfg.env.renderer.type)=='nyx'
    task=scene_builder(cfg.env,cfg.task,cfg.robot_control).build(
        show_viewer=bool(cfg.run.viewer),asset_dir=output/'assets')
    sensors={name:camera.sensor for name,camera in task.cameras.items()} if is_nyx else {}
    OmegaConf.save(cfg,output/'config.yaml',resolve=True)
    (output/'layout.json').write_text(json.dumps(asdict(task.layout),indent=2))
    if str(cfg.task.motion.get('strategy','free_discs'))=='limited_reindex':
        from topogym.tasks.lock_picking.certificate import certificate
        (output/'retreat_certificate.json').write_text(json.dumps(certificate(task.layout,cfg.task.rotor_stops),indent=2)+'\n')
    controller=initialize_franka_controller(scene=task.scene,manifest=task.manifest,
        robot_cfg=cfg.robot_control,settle_steps=int(cfg.task.initialization.settle_steps))
    initial_support=task.support_state()
    key_link=task.key.get_link('key')
    inertia_rot=Rotation.from_quat(np.asarray(key_link.inertial_quat)[[1,2,3,0]]).as_matrix()
    initial_support.update(key_mass=float(key_link.inertial_mass),
        key_com_local=np.asarray(key_link.inertial_pos).tolist(),
        key_inertia_local=(inertia_rot@np.asarray(key_link.inertial_i)@inertia_rot.T).tolist())
    (output/'initial_support.json').write_text(json.dumps(initial_support,indent=2)+'\n')

    rig_error=0.
    def render(name):
        nonlocal rig_error
        camera=task.cameras[name]
        if getattr(camera,'_attached_link',None) is not None: camera.move_to_attach()
        if is_nyx:
            sensor=sensors[name]
            rgb=nyx.rgb(sensor)
            if sensor._attached_pos is not None:
                pos,lookat,up=[getattr(sensor,f'_attached_{key}')[0].cpu().numpy() for key in ('pos','lookat','up')]
            else:
                pos,lookat,up=[np.asarray(getattr(sensor._options,key)) for key in ('pos','lookat','up')]
            error=float(np.max(np.abs(nyx.pos_lookat_up_to_T(pos,lookat,up)-camera.transform)))
            rig_error=max(rig_error,error)
            if error>5e-5: raise RuntimeError(f'Nyx camera differs from calibrated rig: {name}, {error}')
            return rgb
        return camera.render()[0]

    def snapshot(label):
        for name in task.cameras:
            Image.fromarray(render(name)).save(output/f'{label}_{name}.png')

    def frame_bounds(vertices,camera_names=None):
        result={}
        for name in exterior_names if camera_names is None else camera_names:
            cam=task.cameras[name]
            if getattr(cam,'_attached_link',None) is not None: cam.move_to_attach()
            # Genesis 1.2.1 exposes extrinsics as a cached_property. Recompute
            # from the current rig so wrist projections follow the moving hand.
            camera_to_world=cam.transform.copy()
            camera_to_world[:3,1:3]*=-1
            extrinsics=np.linalg.inv(camera_to_world)
            p=vertices@extrinsics[:3,:3].T+extrinsics[:3,3]
            pixels=p@cam.intrinsics.T
            pixels=pixels[:,:2]/pixels[:,2:3]
            width,height=cam.res
            margin=min(float(pixels[:,0].min()),float(pixels[:,1].min()),
                       float(width-1-pixels[:,0].max()),float(height-1-pixels[:,1].max()))
            result[name]=dict(min_margin_px=margin,all_visual_vertices_in_frame=bool(margin>=0 and np.all(p[:,2]>cam.near)),
                bbox_xyxy_px=[float(pixels[:,0].min()),float(pixels[:,1].min()),float(pixels[:,0].max()),float(pixels[:,1].max())])
        return result

    def arm_framing():
        return frame_bounds(numpy(controller.robot.get_vverts()).reshape(-1,3))

    def mechanism_framing():
        return frame_bounds(np.concatenate([numpy(entity.get_vverts()).reshape(-1,3)
            for name,entity in task.manifest.entities.items() if name.startswith('lock_')]))

    def aperture_framing():
        # Geometric projection, not a visibility/occlusion or segmentation test.
        g=task.layout;state=task.state();result={}
        for i,angle in enumerate([*state['disc_deg'],g.endpoint_deg]):
            slots=g.slots[i] if i<3 else (0.,)
            a=np.arange(720)*.5
            err=np.minimum.reduce([np.abs((a-s+180)%360-180) for s in slots])
            radius=np.where(err<=g.slot_half_deg,g.slot_radius,g.bore_radius)
            theta=np.radians(a+angle)
            points=np.c_[np.full(len(a),g.disc_x(i)),g.center_y+radius*np.sin(theta),g.axis_z+radius*np.cos(theta)]
            result[f'layer_{i+1}']=frame_bounds(points,names)
        result['leading_tab_center']=frame_bounds(np.asarray([state['key_tip_pos']]),names)
        return result

    def camera_rig():
        result={}
        for name,cam in task.cameras.items():
            if getattr(cam,'_attached_link',None) is not None: cam.move_to_attach()
            direction=cam.transform[:3,2]
            result[name]=dict(config=OmegaConf.to_container(cfg.env.cameras[name],resolve=True),
                intrinsics=cam.intrinsics.tolist(),initial_world_transform=cam.transform.tolist(),
                optical_axis_elevation_deg=float(np.degrees(np.arctan2(abs(direction[2]),np.linalg.norm(direction[:2])))),
                acute_angle_to_insertion_axis_deg=float(np.degrees(np.arccos(np.clip(abs(direction[0]),0,1)))))
        return result

    (output/'camera_rig.json').write_text(json.dumps(camera_rig(),indent=2)+'\n')

    snapshot('initial')
    if cfg.run.camera_audit_source:
        # Explicit pose replay for camera calibration only. It never produces a
        # task success report or videos; the actual recording must execute anew.
        source=Path(cfg.run.camera_audit_source).resolve()
        frames=json.loads(source.read_text())
        phases=('approach','align_1','insert_1','align_2','insert_2','align_3','insert_3','align_4','insert_4','settle')
        selected=[next(f for f in frames if f['grasp_weld'])]
        selected += [f for f in frames if f['phase']=='approach' and f['step']%100==0]
        selected += [next(f for f in reversed(frames) if f['phase']==phase) for phase in phases]
        audit=[]
        for f in selected:
            controller.robot.set_qpos(f['robot_qpos'],zero_velocity=True)
            controller.robot.control_dofs_position(f['robot_qpos'])
            pos=f.get('key_tip_pos',[task.layout.tip_x(f['depth']),task.layout.center_y,task.layout.axis_z])
            quat=f.get('key_quat',Rotation.from_euler('x',-f['key_deg'],degrees=True).as_quat()[[3,0,1,2]].tolist())
            task.key.set_qpos([*pos,*quat],zero_velocity=True)
            for disc,angle in zip(task.discs,f['disc_deg']): disc.set_qpos([np.radians(angle)],zero_velocity=True)
            task.scene.step()  # Refresh kinematics and Nyx's sensor frame cache.
            label=f"audit_{f['step']:04d}_{f['phase']}"
            snapshot(label)
            fingers=np.concatenate([numpy(controller.robot.get_link(n).get_verts()).reshape(-1,3)
                                    for n in ('left_finger','right_finger')])
            audit.append(dict(label=label,source_step=f['step'],arm=arm_framing(),mechanism=mechanism_framing(),
                              finger_collision_bounds=frame_bounds(fingers,['wrist']),aperture_projections=aperture_framing()))
        (output/'camera_audit.json').write_text(json.dumps(dict(kind='pose_replay_camera_audit_only',source=str(source),
            nyx_camera_pose_max_error=rig_error,checkpoints=audit),indent=2)+'\n')
        print(f'Camera pose audit saved (not a physics rollout): {output}',flush=True)
        return
    if cfg.run.inspect_only or cfg.run.build_only:
        print(f'Full-arm scene built: {output}',flush=True);return
    if not initial_support['weight_supported'] or initial_support['key_dofs']!=6:
        raise RuntimeError(f'Initial key must rest under gravity before grasp: {initial_support}')
    status=dict(phase='initial',grasp_weld=False,oracle_mode=str(cfg.run.oracle_mode))
    records=[];steps=0;max_penetration=0.;max_robot_fixture_force=0.;geometry_errors=0
    max_key_fixture_force=0.
    framing=arm_framing()
    mechanism_bounds=mechanism_framing()
    wrist_up_min=None
    grasp_snapshot_saved=False
    robot_links={link.idx for link in controller.robot.links}
    fixture_links={link.idx for name,entity in task.manifest.entities.items()
                   if name.startswith('lock_') and name!='lock_key' for link in entity.links}
    original_step=task.scene.step
    decisions=[];error=None;attach_error=None
    with ExitStack() as stack:
        writers={name:stack.enter_context(imageio.get_writer(str(output/f'{name}.mp4'),
            fps=int(cfg.recording.fps),codec='libx264',quality=8,macro_block_size=1,ffmpeg_log_level='error'))
            for name in task.cameras} if cfg.recording.enabled else {}

        def step(*args,**kwargs):
            nonlocal steps,max_penetration,geometry_errors,max_robot_fixture_force,wrist_up_min,grasp_snapshot_saved
            steps+=1
            result=original_step(*args,**kwargs)
            # Every physics step, audit contacts and structural geometry. These
            # are evaluator/oracle logs, never embedded in sensor observations.
            state=task.state()
            collisions=task.last_contacts
            penetration=numpy(collisions['penetration'])
            if penetration.size: max_penetration=max(max_penetration,float(penetration.max()))
            a,b=numpy(collisions['link_a']),numpy(collisions['link_b'])
            bad=(np.isin(a,list(robot_links)) & np.isin(b,list(fixture_links))) | (np.isin(b,list(robot_links)) & np.isin(a,list(fixture_links)))
            if np.any(bad):
                max_robot_fixture_force=max(max_robot_fixture_force,float(np.linalg.norm(numpy(collisions['force'])[bad],axis=-1).max()))
            problems=task.layout.clearance(state['depth'],state['key_deg'],state['disc_deg'],tolerance=2.)
            if problems: geometry_errors+=1
            if steps % int(cfg.recording.every_n_steps)==0:
                for accumulated,current in ((framing,arm_framing()),(mechanism_bounds,mechanism_framing())):
                    for name,values in current.items():
                        accumulated[name]['min_margin_px']=min(accumulated[name]['min_margin_px'],values['min_margin_px'])
                        accumulated[name]['all_visual_vertices_in_frame'] &= values['all_visual_vertices_in_frame']
                        a=accumulated[name]['bbox_xyxy_px'];b=values['bbox_xyxy_px']
                        accumulated[name]['bbox_xyxy_px']=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                task.cameras['wrist'].move_to_attach()
                wrist_up_z=float(task.cameras['wrist'].transform[2,1])
                if status['grasp_weld']:
                    wrist_up_min=wrist_up_z if wrist_up_min is None else min(wrist_up_min,wrist_up_z)
                save_grasp=status['grasp_weld'] and not grasp_snapshot_saved
                for name,writer in writers.items():
                    rgb=render(name)
                    writer.append_data(rgb)
                    if save_grasp: Image.fromarray(rgb).save(output/f'grasp_{name}.png')
                if writers and save_grasp: grasp_snapshot_saved=True
                records.append(dict(step=steps,time_s=steps*float(cfg.env.sim.dt),**status,**state,
                                    robot_qpos=numpy(controller.robot.get_qpos()).tolist(),
                                    hand_pos=controller.hand_pos().tolist(),max_penetration=max_penetration,
                                    support_contacts=task.support_state()['contact_count'],
                                    geometry_errors=problems,wrist_up_z=wrist_up_z,
                                    aperture_projections=aperture_framing()))
            return result

        task.scene.step=step
        try:
            attach_error=execute(task,controller,status,decisions)
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}'
            traceback.print_exc()
            if task.force_limit_triggered:
                status['phase']='contact_stop'
                task.settling_after_stop=True
                try: controller.step(100)
                finally: task.settling_after_stop=False
        finally:
            task.scene.step=original_step
    snapshot('final')
    max_penetration=task.max_contact_penetration
    max_key_fixture_force=task.max_key_contact_force
    geometry_errors=task.geometry_error_steps
    result=StagedLockEvaluator().evaluate(task,execution_ok=error is None,
        grasp_released=not status['grasp_weld'],max_geometry_error=geometry_errors)
    result.update(error=error,physics_steps=steps,seconds=steps*float(cfg.env.sim.dt),
        max_contact_penetration=max_penetration,geometry_error_steps=geometry_errors,
        max_robot_fixture_contact_force=max_robot_fixture_force,max_key_fixture_contact_force=max_key_fixture_force,
        arm_framing=framing,mechanism_framing=mechanism_bounds,
        wrist_up_z_min_during_grasp=wrist_up_min,nyx_camera_pose_max_error=rig_error,
        grasp_attach_error=attach_error,decisions=decisions,variant=str(cfg.task.variant),seed=int(cfg.task.seed),
        initial_support=initial_support,
        versions={name:version(name) for name in ('genesis-world','gs-nyx','gs-nyx-plugin')},
        force_limit_triggered=task.force_limit_triggered,
        scene_builder=f'{scene_builder.__module__}.{scene_builder.__name__}',
        full_arm=True,robot_gravity_compensation=1.0,disc_actuators=False,mechanism_pose_writes_after_reset=False,
        recorded_cameras=names,exterior_cameras=exterior_names,
        grasp_assistance='runtime solver weld after proximity, finger closure and contact checks',
        guide='none: free 6-DOF key; physical tray/V rests, finger weld while grasped, and aperture contacts',
        renderer=str(cfg.env.renderer.type),release_observation={k:v for k,v in status.items() if k.startswith('release_')})
    if scene_builder.__module__.startswith('topogym.tasks.lock_picking.'):
        result['source_evaluator_task_id']=result['task_id']
        result['task_id']='lock_picking'
    if max_penetration > float(cfg.task.physics.max_penetration):
        result['success']=False;result['penetration_limit_exceeded']=True
    if max_robot_fixture_force>1.0:
        result['success']=False;result['robot_fixture_collision']=True
    if str(cfg.task.motion.get('strategy','free_discs'))=='limited_reindex':
        from topogym.tasks.lock_picking.certificate import certificate,measured_retreat_cycles
        proof=certificate(task.layout,cfg.task.rotor_stops)
        cycles=measured_retreat_cycles(records)
        result.update(retreat_certificate=proof,observed_retreat_count=len(cycles),
            retreat_cycles=cycles,global_6d_unique_solution_verified=False,
            demo_requirements_met=bool(result['success'] and len(cycles)==2 and
                all(v['all_visual_vertices_in_frame'] for v in framing.values())))
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'frames.json').write_text(json.dumps(records,indent=2)+'\n')
    if cfg.recording.enabled: media_index(output,names)
    print(json.dumps(result,indent=2),flush=True)
    if not result['success']: raise SystemExit(1)


@hydra.main(version_base='1.3',config_path='../../../configs',config_name='lock_picking_baseline')
def main(cfg):
    run(cfg)


if __name__=='__main__': main()
