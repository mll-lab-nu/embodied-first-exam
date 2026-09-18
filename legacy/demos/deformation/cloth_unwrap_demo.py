"""Nyx task-design preview: flip a wrapped plate, peel four layers, extract.

Uses the shared table, original-scale Panda/2F-85 and camera pipeline. Cloth
vertices and object poses are prescribed; the PBD entity is a rendering carrier
only. No physics step is taken. Metadata and overlays explicitly retain this
distinction. Run with `run.preview=true` before a full render.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path

import genesis as gs
import hydra
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from demos.deformation._cloth_unwrap_model import WrapModel, smooth
from topogym.primitives.attachment import slerp
from topogym.robot.gripper import as_numpy, robotiq_joint_targets, robotiq_pad_centres, pad_vertices
from topogym.world import StandardTabletopSceneBuilder, nyx

FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
LABELS = {'agentview':'主视角', 'wrist':'腕部视角', 'front_oblique':'侧前方近景'}


def quat(r):
    return r.as_quat()[[3,0,1,2]]


def rot(q):
    return Rotation.from_quat(np.asarray(q)[[1,2,3,0]])


def write_assets(model, output):
    assets = output/'assets'
    assets.mkdir(exist_ok=True)
    uv = model.material.copy()
    lower, upper = uv.min(axis=0), uv.max(axis=0)
    uv = (uv-lower)/(upper-lower)
    lines = [f'v {x:.9f} {y:.9f} {z:.9f}' for x,y,z in model.flat]
    lines += [f'vt {u:.9f} {v:.9f}' for u,v in uv]
    lines += ['f '+' '.join(f'{i+1}/{i+1}' for i in face) for face in model.faces]
    (assets/'cloth.obj').write_text('\n'.join(lines)+'\n')
    # A deterministic woven texture; the cloth stays red on every layer.
    y,x = np.mgrid[:1024,:1024]
    weave = 1.+.045*np.sin(x*np.pi/2)+.035*np.sin(y*np.pi/2)
    tex = np.clip(np.array([162,22,34])[None,None,:]*weave[:,:,None],0,255).astype(np.uint8)
    xy = np.stack((lower[0]+x/1023*(upper[0]-lower[0]),
                   upper[1]-y/1023*(upper[1]-lower[1])),axis=-1)
    hem = np.zeros((1024,1024),bool)
    for i,(axis,sign) in enumerate(model.axes):
        end = sign*(model.half[axis]+model.lengths[i]-.003)
        hem |= (np.abs(xy[:,:,axis]-end)<.0006) & (np.abs(xy[:,:,1-axis])<model.half[1-axis])
    tex[hem & ((x+y)%12<7)] = [212,151,132]
    Image.fromarray(tex).save(assets/'red_weave.png')
    return assets


class Hand:
    def __init__(self, table, cfg):
        self.robot = table.manifest.get('robot')
        self.link = self.robot.get_link('hand')
        self.q = as_numpy(self.robot.get_qpos()).reshape(-1).copy()
        self.q[:7] = cfg.robot_control.home.qpos[:7]
        self.home = self.q.copy()
        self.gap = .04
        self.set_gap(self.gap)
        self.robot.set_qpos(self.q,zero_velocity=True)
        r = rot(as_numpy(self.link.get_quat()).reshape(4))
        pads = robotiq_pad_centres(self.robot)
        closing = r.inv().apply(pads[1]-pads[0]); closing[2]=0
        self.closing = closing/np.linalg.norm(closing)
        self.basis = np.column_stack((self.closing,np.cross([0,0,1],self.closing),[0,0,1]))
        local_points=[];link_ids=[]
        positions=as_numpy(self.robot.get_links_pos(relative=False)).reshape(-1,3)
        rotations=Rotation.from_quat(as_numpy(self.robot.get_links_quat(relative=False)).reshape(-1,4)[:,[1,2,3,0]])
        for i,link in enumerate(self.robot.links):
            if not link.n_geoms or link.name=='link0':continue
            points=as_numpy(link.get_verts()).reshape(-1,3)
            local_points.extend(rotations[i].inv().apply(points-positions[i]))
            link_ids.extend([i]*len(points))
        self.collision_local=np.asarray(local_points);self.collision_link=np.asarray(link_ids,int)

    def table_clearance(self,table_z):
        positions=as_numpy(self.robot.get_links_pos(relative=False)).reshape(-1,3)
        matrices=Rotation.from_quat(as_numpy(self.robot.get_links_quat(relative=False)).reshape(-1,4)[:,[1,2,3,0]]).as_matrix()
        z=np.einsum('ij,ij->i',self.collision_local,matrices[self.collision_link,2,:])+positions[self.collision_link,2]
        return float(z.min()-table_z)

    def set_gap(self,gap):
        for name,value in robotiq_joint_targets(gap).items():
            name = {'right_driver_joint':'finger_joint1','left_driver_joint':'finger_joint2'}.get(name,'r85_'+name)
            self.q[self.robot.get_joint(name).qs_idx_local[0]] = value
        self.gap = gap

    def orient(self, forward, closing):
        forward, closing = np.asarray(forward,float), np.asarray(closing,float)
        world = np.column_stack((closing,np.cross(forward,closing),forward))
        return quat(Rotation.from_matrix(world@self.basis.T))

    def pad_local(self,gap):
        self.set_gap(gap)
        self.robot.set_qpos(self.q,zero_velocity=True)
        p = as_numpy(self.link.get_pos()).reshape(3)
        r = rot(as_numpy(self.link.get_quat()).reshape(4))
        return r.inv().apply(robotiq_pad_centres(self.robot).mean(axis=0)-p)

    def pose(self,grip,q,gap,*,fallback=True):
        offset = self.pad_local(gap)
        target = grip-rot(q).apply(offset)
        solved = self.robot.inverse_kinematics(link=self.link,pos=target,quat=q,init_qpos=self.q,
                    dofs_idx_local=np.arange(7),max_samples=1,max_solver_iters=200,
                    max_step_size=.06,pos_tol=1e-5,rot_tol=1e-4)
        self.q[:7] = as_numpy(solved).reshape(-1)[:7]
        self.robot.set_qpos(self.q,zero_velocity=True)
        pos_error = np.linalg.norm(robotiq_pad_centres(self.robot).mean(axis=0)-grip)
        if fallback and pos_error>.0005:
            # A bad local branch must not make the arm detach from the object.
            # Multi-start IK is used only if continuation from the last frame fails.
            solved = self.robot.inverse_kinematics(link=self.link,pos=target,quat=q,init_qpos=self.home,
                        dofs_idx_local=np.arange(7),max_samples=8,max_solver_iters=250,
                        max_step_size=.10,pos_tol=1e-5,rot_tol=1e-4)
            candidate=as_numpy(solved).reshape(-1)[:7]
            old=self.q[:7].copy();self.q[:7]=candidate
            self.robot.set_qpos(self.q,zero_velocity=True)
            new_error=np.linalg.norm(robotiq_pad_centres(self.robot).mean(axis=0)-grip)
            if new_error<pos_error:pos_error=new_error
            else:
                self.q[:7]=old;self.robot.set_qpos(self.q,zero_velocity=True)
        actual = rot(as_numpy(self.link.get_quat()).reshape(4))
        angle_error = (actual.inv()*rot(q)).magnitude()
        return float(pos_error),float(angle_error)


def build(cfg, output, model):
    assets = write_assets(model,output)
    material = gs.materials.Rigid(needs_coup=False)
    builder = StandardTabletopSceneBuilder(cfg.env,cfg.robot_control,
                    pbd_options=gs.options.PBDOptions(particle_size=.006))
    table = builder.create(show_viewer=False,robot_material=material,table_material=material,
                            static_material=material,decoration_material=material)
    scene,manifest = table.scene,table.manifest
    origin = np.asarray(cfg.env.frames.task.origin)

    def box(name,size,pos,color):
        entity = scene.add_entity(gs.morphs.Box(size=tuple(size),pos=tuple(origin+pos),
                    fixed=True,collision=False),material=material,
                    surface=gs.surfaces.Plastic(color=color,roughness=.6),name=name)
        manifest.add(name,entity)
        return entity

    source = np.asarray(cfg.unwrap.source)
    # Narrow visible pedestal gives the lower finger access to the package edge;
    # the outer free edge itself remains trapped against its central support.
    source_height=source[2]-.003
    box('package_support',[.100,.056,source_height],np.r_[source[:2],source_height/2],(.23,.27,.28))
    work=np.asarray(cfg.unwrap.work)
    box('unwrapping_support',[.100,.056,.090],work+np.array([0,0,-.048]),(.23,.27,.28))
    goal = np.asarray(cfg.unwrap.goal)
    box('extraction_tray',[.196,.120,.006],goal+np.array([0,0,-.017]),(.20,.34,.33))
    for sign in (-1,1):
        box(f'tray_rim_{sign}',[.196,.004,.008],goal+np.array([0,sign*.058,-.012]),(.30,.46,.43))
    board = box('wrapped_plate',model.board_size,source+[0,0,model.board_z],(.31,.56,.64))
    # A small, flush center mark makes it easy to identify the released rigid plate.
    mark = box('plate_mark',[.042,.016,.0006],source+[0,0,model.board_z+.0143],(.82,.88,.86))
    cloth = scene.add_entity(gs.morphs.Mesh(file=str(assets/'cloth.obj'),decimate=False,
                convexify=False,file_meshes_are_zup=True),material=gs.materials.PBD.Cloth(),
                surface=gs.surfaces.Plastic(diffuse_texture=gs.textures.ImageTexture(
                    image_path=str(assets/'red_weave.png')),roughness=.95,double_sided=True),name='red_cloth')
    manifest.add('red_cloth',cloth)
    builder.finalize(table)
    sensors={name:table.cameras[name].sensor for name in cfg.run.record_cameras}
    distances, order = cKDTree(model.flat).query(np.asarray(cloth._vverts))
    if distances.max()>1e-6 or len(np.unique(order))!=len(model.flat):
        raise RuntimeError('Render mesh did not preserve the continuous material mesh')
    return table,cloth,board,mark,sensors,order


def plan(cfg, model, hand):
    u = cfg.unwrap
    fps = int(cfg.run.fps)
    work, source, goal = [np.asarray(u[k],float) for k in ('work','source','goal')]
    down = hand.orient([0,0,-1],[0,1,0])
    side = hand.orient([1,0,0],[0,0,1])
    hand.pose(np.asarray(cfg.env.frames.task.origin)+[-.30,-.22,.23],down,.04)
    qhome = as_numpy(hand.link.get_quat()).reshape(4)
    state = dict(origin=source.copy() if u.opening_down else work.copy(),
                 angle=np.pi if u.opening_down else 0., opened=np.zeros(4),
                 grip=robotiq_pad_centres(hand.robot).mean(axis=0)-np.asarray(cfg.env.frames.task.origin),
                 quat=qhome, gap=.04, board_pos=None, grasp='none')
    frames=[]

    def add(seconds,phase,update=None,**targets):
        start={k:v.copy() if isinstance(v,np.ndarray) else v for k,v in state.items()}
        for step in range(1,round(seconds*fps)+1):
            t=float(smooth(step/round(seconds*fps)))
            for k,value in targets.items():
                if k=='quat':state[k]=slerp(start[k],value,t)
                elif k=='grasp':state[k]=value
                else:state[k]=np.asarray(start[k])+(np.asarray(value)-np.asarray(start[k]))*t
            if update:update(t,start,state)
            bp,bq=model.board_pose(state['origin'],float(state['angle']))
            if state['board_pos'] is not None:bp=state['board_pos']
            frames.append(dict(phase=phase,time_s=len(frames)/fps,
                **{k:v.copy() if isinstance(v,np.ndarray) else v for k,v in state.items()},
                actual_board_pos=bp,actual_board_quat=bq))

    add(1.2,'开口压在底面 · 先改变包裹朝向' if u.opening_down else '开口朝上 · 从最外层开始')
    if u.opening_down:
        grip=source+np.array([-.078,0.,model.mid_z])
        add(.9,'接近包裹侧边',grip=grip+[-.06,0,.06],quat=side)
        add(.7,'调整夹爪姿态 · 接近包裹边缘',grip=grip)
        add(.5,'夹住布和板的共同边缘',gap=.023,grasp='package_assist')
        lift=source.copy();lift[2]=.19
        add(1.0,'整包抬起 · 保持包覆关系',origin=lift,grip=lift+[-.078,0,model.mid_z])

        def flipping(t,start,s):
            s['angle']=np.pi*(1+t)
            s['origin']=lift+(np.r_[work[:2],.19]-lift)*t
            s['grip']=s['origin']+[-.078,0,model.mid_z]
            s['quat']=quat(Rotation.from_rotvec([np.pi*t,0,0])*rot(side))
        add(2.3,'整体翻转 180° · 开口转到上方',flipping)
        add(.9,'放到解包支撑台 · 开口已可访问',origin=work,grip=work+[-.078,0,model.mid_z])
        add(.4,'松开包裹',gap=.034,grasp='none')
        add(.7,'换抓最外层自由边',grip=state['grip']+[-.07,0,.10])
        add(.6,'观察上表面的层叠顺序',grip=work+[-.09,-.09,.22],quat=down)
    else:
        add(.8,'观察上表面的层叠顺序',grip=work+[-.09,-.09,.22],quat=down)
    for flap in range(4):
        tip=model.tip(flap,state['opened'],work)+[0,0,.020]
        add(.65,f'第 {flap+1} 层 · 接近已暴露布边',grip=tip+[0,0,.08],quat=down,gap=.025)
        add(.4,f'第 {flap+1} 层 · 夹取自由边',grip=tip)
        add(.3,f'第 {flap+1} 层 · 夹取自由边',gap=.0015,grasp=f'flap_{flap+1}_assist')
        def peel(t,start,s):
            s['opened'][flap]=t
            s['grip']=model.tip(flap,s['opened'],work)+[0,0,.020]
        add(2.0,f'第 {flap+1} 层 · 向外剥开'+('，暴露下一层' if flap<3 else '，板已暴露'),peel)
        add(.3,f'第 {flap+1} 层 · 放下布边',gap=.025,grasp='none')
        add(.5,'保留已展开部分 · 换抓',grip=state['grip']+[0,0,.10])
    bp,bq=model.board_pose(work,0.)
    add(.7,'板已完全暴露 · 接近两侧',grip=bp+[0,0,.12],quat=down,gap=.04)
    add(.6,'从布中夹取刚性板',grip=bp+[0,0,.007])
    add(.4,'从布中夹取刚性板',gap=.036,grasp='board_assist')
    state['board_pos']=bp.copy()
    add(.9,'取出板 · 与红布分离',board_pos=bp+[0,0,.16],grip=bp+[0,0,.167])
    add(1.0,'移至收纳区',board_pos=goal+[0,0,.16],grip=goal+[0,0,.167])
    add(.8,'放下刚性板',board_pos=goal,grip=goal+[0,0,.007])
    add(.4,'释放板',gap=.042,grasp='none')
    add(.7,'完成 · 红布展开，刚性板已取出',grip=goal+[0,0,.15])
    add(1.5,'完成 · 红布展开，刚性板已取出')
    return frames


def free_joint_route(hand,initial,final,template,table_z):
    """Bidirectional joint-space search for an empty-hand, table-clear move."""
    lower=np.array([-2.8973,-1.7628,-2.8973,-3.0718,-2.8973,-.0175,-2.8973])
    upper=np.array([2.8973,1.7628,2.8973,-.0698,2.8973,3.7525,2.8973])
    rng=np.random.default_rng(12)
    def edge(a,b):
        count=max(2,int(np.ceil(np.abs(b-a).max()/.07))+1)
        for u in np.linspace(0,1,count):
            q=template.copy();q[:7]=a+(b-a)*u
            hand.robot.set_qpos(q,zero_velocity=True)
            if hand.table_clearance(table_z)<.004:return False
        return True
    def extend(tree,target):
        nodes,parents=tree
        nearest=int(np.argmin(np.linalg.norm(np.asarray(nodes)-target,axis=1)))
        delta=target-nodes[nearest];length=np.linalg.norm(delta)
        candidate=nodes[nearest]+delta*min(1.,.45/max(length,1e-12))
        if not edge(nodes[nearest],candidate):return None
        nodes.append(candidate);parents.append(nearest)
        return len(nodes)-1
    def trace(tree,index):
        out=[]
        while index>=0:out.append(tree[0][index]);index=tree[1][index]
        return out[::-1]
    trees=[([initial.copy()],[-1]),([final.copy()],[-1])]
    for iteration in range(1500):
        a=iteration%2;b=1-a
        sample=trees[b][0][-1] if iteration%4==0 else rng.uniform(lower,upper)
        ia=extend(trees[a],sample)
        if ia is None:continue
        target=trees[a][0][ia]
        for _ in range(30):
            ib=extend(trees[b],target)
            if ib is None:break
            if np.linalg.norm(trees[b][0][ib]-target)>1e-6:continue
            pa,pb=trace(trees[a],ia),trace(trees[b],ib)
            route=pa+pb[-2::-1] if a==0 else pb+pa[-2::-1]
            # Deterministic farthest-visible shortcutting keeps free motion short.
            simplified=[route[0]];i=0
            while i<len(route)-1:
                j=len(route)-1
                while j>i+1 and not edge(route[i],route[j]):j-=1
                simplified.append(route[j]);i=j
            print(f'free route: {iteration+1} search iterations, {len(simplified)} waypoints',flush=True)
            return simplified
        if iteration%200==199:print(f'free route search {iteration+1}',flush=True)
    raise RuntimeError('No table-clear empty-hand joint route found within search budget')


def solve_motion(hand,frames,origin,fps,package_seed):
    """Cartesian continuation while holding; joint interpolation for free turns.

Changing the IK branch while empty-handed is a planned joint movement, never
a per-frame teleport. During holding, the original contact targets are kept.
"""
    joints=[];errors=[]
    previous_phase=None
    for f in frames:
        if f['phase']=='调整夹爪姿态 · 接近包裹边缘' and previous_phase!=f['phase']:
            hand.q[:7]=np.asarray(package_seed)
        e,r=hand.pose(f['grip']+origin,f['quat'],float(f['gap']))
        joints.append(hand.q.copy());errors.append((e,r))
        previous_phase=f['phase']
    joints=np.asarray(joints);errors=np.asarray(errors)
    repaired=[];expanded_frames=[];expanded_joints=[];expanded_errors=[]
    start=0
    while start<len(frames):
        end=start
        while end+1<len(frames) and frames[end+1]['phase']==frames[start]['phase'] and frames[end+1]['grasp']==frames[start]['grasp']:
            end+=1
        jumps=np.abs(np.diff(joints[max(0,start-1):end+1,:7],axis=0))
        needs_repair=(errors[start:end+1,0].max()>.0005 or errors[start:end+1,1].max()>.01
                      or (jumps.size and jumps.max()>.3))
        if needs_repair:
            if any(f['grasp']!='none' for f in frames[start:end+1]):
                raise RuntimeError(f'Cannot repair an IK branch while holding: {frames[start]["phase"]}')
            if errors[end,0]>.0005 or errors[end,1]>.01:
                raise RuntimeError('Free-motion endpoint is not reachable')
            initial=joints[max(0,start-1),:7].copy();final=joints[end,:7].copy()
            # The direct joint blend can dip through the table even when both
            # endpoints are reachable. Route through a raised arm posture and
            # check the actual collision vertices of every moving link.
            candidates=[[initial,final]]
            for middle in ([0.,-.4,0.,-1.7,0.,1.3,0.],
                           [0.,-.8,0.,-2.2,0.,1.4,.785],hand.home[:7]):
                candidates.append([initial,np.asarray(middle),final])
            selected=None
            endpoint_clearances=[]
            for arm_q in (initial,final):
                q=joints[start].copy();q[:7]=arm_q;hand.robot.set_qpos(q,zero_velocity=True)
                endpoint_clearances.append(hand.table_clearance(origin[2]))
            print('free transition endpoints',frames[start]['phase'],endpoint_clearances,flush=True)
            for route in candidates:
                clear=True
                for a,b in zip(route[:-1],route[1:]):
                    for u in np.linspace(0,1,51):
                        q=joints[start].copy();q[:7]=a+(b-a)*smooth(u)
                        hand.robot.set_qpos(q,zero_velocity=True)
                        if hand.table_clearance(origin[2])<.002:
                            clear=False;break
                    if not clear:break
                if clear:selected=route;break
            if selected is None:
                selected=free_joint_route(hand,initial,final,joints[start],origin[2])
            samples=[]
            for a,b in zip(selected[:-1],selected[1:]):
                count=max(15,int(np.ceil(1.5*np.abs(b-a).max()/.12)))
                samples.extend(a+(b-a)*smooth(step/count) for step in range(1,count+1))
            count=len(samples)
            repaired_start=len(expanded_frames)
            for step,arm_q in enumerate(samples,1):
                u=step/count
                i=min(end,start+int(u*(end-start)))
                q=joints[i].copy();q[:7]=arm_q
                hand.robot.set_qpos(q,zero_velocity=True)
                # These free-motion waypoints now come from the actual FK.
                f=frames[i].copy()
                f['grip']=robotiq_pad_centres(hand.robot).mean(axis=0)-origin
                f['quat']=as_numpy(hand.link.get_quat()).reshape(4)
                f['free_motion_mode']='joint_interpolation'
                expanded_frames.append(f);expanded_joints.append(q);expanded_errors.append((0.,0.))
            repaired.append(dict(start=repaired_start,end=len(expanded_frames)-1,phase=frames[start]['phase']))
        else:
            expanded_frames.extend(frames[start:end+1])
            expanded_joints.extend(joints[start:end+1]);expanded_errors.extend(errors[start:end+1])
        start=end+1
    joints=np.asarray(expanded_joints);errors=np.asarray(expanded_errors)
    for i,f in enumerate(expanded_frames):f['time_s']=i/fps
    delta=float(np.abs(np.diff(joints[:,:7],axis=0)).max())
    clearance=float('inf')
    for q in joints:
        hand.robot.set_qpos(q,zero_velocity=True)
        clearance=min(clearance,hand.table_clearance(origin[2]))
    print(f'motion solved: max step {delta:.4f} rad; repaired free transitions {repaired}',flush=True)
    print(f'minimum moving robot/table clearance: {clearance*1000:.3f} mm',flush=True)
    if clearance<0:raise RuntimeError('Moving robot collision geometry crosses the tabletop')
    if errors[:,0].max()>.0005 or errors[:,1].max()>.01 or delta>.35:
        raise RuntimeError('Motion did not pass position, orientation, or continuity checks')
    return expanded_frames,joints,errors,repaired


def fit_primary_camera(table,sensors,cfg,joints):
    """Dolly the shared primary camera back enough to include the whole arm.

    Keep the original viewing direction, FOV and look-at; account for the title
    and footer in the geometric projection bounds. Close-up cameras stay fixed.
    """
    robot=table.manifest.get('robot');adjustments={}
    for name in cfg.run.exterior_cameras:
        cam=table.cameras[name]
        transform=cam.transform.copy();transform[:3,1:3]*=-1
        ext=np.linalg.inv(transform);intr=cam.intrinsics;w,h=cam.res
        left=(20-intr[0,2])/intr[0,0];right=(w-21-intr[0,2])/intr[0,0]
        top=(102-intr[1,2])/intr[1,1];bottom=(h-56-intr[1,2])/intr[1,1]
        retreat=0.
        for i in list(range(0,len(joints),5))+[len(joints)-1]:
            robot.set_qpos(joints[i],zero_velocity=True)
            v=as_numpy(robot.get_vverts()).reshape(-1,3)
            cp=v@ext[:3,:3].T+ext[:3,3]
            need_x=np.where(cp[:,0]>=0,cp[:,0]/right,cp[:,0]/left)
            need_y=np.where(cp[:,1]>=0,cp[:,1]/bottom,cp[:,1]/top)
            retreat=max(retreat,float((np.maximum(need_x,need_y)-cp[:,2]).max()))
        if retreat>0:
            old=np.asarray(cfg.env.cameras[name].pos);look=np.asarray(cfg.env.cameras[name].lookat)
            new=old+(old-look)/np.linalg.norm(old-look)*(retreat+.03)
            cfg.env.cameras[name].pos=new.tolist()
            cam.set_pose(pos=new,lookat=look)
            sensors[name].update_camera_pose(pos=new,lookat=look)
        adjustments[name]=dict(retreat_m=retreat,position=list(cfg.env.cameras[name].pos))
    return adjustments


def write_player(output,report):
    views=''.join(f'<section><h2>{LABELS[n]}</h2><video controls preload="metadata" poster="final_{n}.jpg" src="{n}.mp4"></video><p><a href="{n}.mp4" download>下载视频</a></p></section>' for n in LABELS)
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>红布解包 · 翻转并取出刚性板</title><style>
body{background:#141e25;color:#ebf1f1;font:17px/1.7 system-ui;max-width:1440px;margin:32px auto;padding:0 24px}a{color:#92d8c2}h1{font-size:32px}.tag{color:#e8aa9e}video{width:100%;border-radius:10px}.views{display:grid;grid-template-columns:1fr 1fr;gap:22px}section:first-child{grid-column:1/-1}button{padding:10px 18px;margin:8px 12px 10px 0;cursor:pointer}@media(max-width:750px){.views{display:block}}</style>
<p class="tag">A3 材料访问与层序控制 · 任务机制预览</p><h1>红布包裹刚性板：翻面 → 分层剥开 → 取出</h1>
<p>开口在底面被压住。夹住整包翻转，依次揭开四片叠压布边，最后把板夹出并放到收纳区。</p>
<p>采用一整片连续十字形红布、Panda + 原尺寸 Robotiq 2F-85、共享实验桌面与 Nyx 三路相机。三路视频逐帧同步。</p>
<p><strong>验证范围：</strong>布形、翻转与抓持采用规定轨迹，机械臂由 IK 求解。本片展示任务机制；布料自接触、摩擦、真实抓持、无辅助翻转和“翻转是唯一解”尚未经过动力学验证。</p>
<p><a href="report.json">几何与 IK 报告</a> · <a href="video_validation.json">视频检查</a></p>
<button id="play">从头同步播放</button><button id="pause">全部暂停</button><div class="views">VIEWS</div>
<script>const vs=[...document.querySelectorAll('video')];document.querySelector('#play').onclick=async()=>{vs.forEach(v=>{v.pause();v.currentTime=0});await Promise.all(vs.map(v=>v.play()))};document.querySelector('#pause').onclick=()=>vs.forEach(v=>v.pause());vs[0].addEventListener('seeked',()=>vs.slice(1).forEach(v=>{if(Math.abs(v.currentTime-vs[0].currentTime)>.15)v.currentTime=vs[0].currentTime}));</script></html>'''
    html=html.replace('三路视频逐帧同步。',f'三路视频逐帧同步：{report["duration_s"]:.0f} 秒，{report["fps"]} FPS，每路 {report["frames"]} 帧。')
    (output/'index.html').write_text(html.replace('VIEWS',views))


@hydra.main(version_base='1.3',config_path='../../configs',config_name='cloth_unwrap')
def main(cfg):
    output=Path(cfg.run.output).resolve();output.mkdir(parents=True,exist_ok=True)
    cfg.env.cameras=OmegaConf.create({n:OmegaConf.to_container(cfg.env.cameras[n],resolve=True) for n in cfg.run.record_cameras})
    OmegaConf.save(cfg,output/'config.yaml',resolve=True)
    model=WrapModel(cfg.unwrap)
    gs.init(backend=gs.cuda,logging_level='warning',seed=0)
    table,cloth,board,mark,sensors,order=build(cfg,output,model)
    # Nyx 0.1.4 calls PBD.get_state_render(), which refreshes the render fields
    # again. Keep this override confined to this visual-only scene instance.
    refresh=cloth.solver.update_render_fields
    display_vertices=[None]
    def refresh_preview_geometry():
        refresh()
        if display_vertices[0] is not None:
            cloth.solver.vverts_render.pos.from_numpy(display_vertices[0])
    cloth.solver.update_render_fields=refresh_preview_geometry
    hand=Hand(table,cfg)
    frames=plan(cfg,model,hand)
    origin=np.asarray(cfg.env.frames.task.origin)
    frames,solved_joints,solved_errors,repaired=solve_motion(hand,frames,origin,cfg.run.fps,cfg.unwrap.package_ik_seed)
    camera_fit=fit_primary_camera(table,sensors,cfg,solved_joints)
    OmegaConf.save(cfg,output/'config.yaml',resolve=True)
    media=output/'preview' if cfg.run.preview else output;media.mkdir(exist_ok=True)
    fonts={s:ImageFont.truetype(FONT,s) for s in (18,24,30)}
    audit=[];joint_frames=[];mesh_frames=[]
    exterior_margins={name:float('inf') for name in cfg.run.exterior_cameras}
    with ExitStack() as stack:
        writers={} if cfg.run.preview or cfg.run.audit_only else {n:stack.enter_context(imageio.get_writer(media/f'{n}.mp4',fps=cfg.run.fps,codec='libx264',quality=8,macro_block_size=1,ffmpeg_params=['-movflags','+faststart'])) for n in sensors}
        for i,frame in enumerate(frames):
            v=model.vertices(frame['opened'],frame['origin'],frame['angle'])
            bp,bq=frame['actual_board_pos'],frame['actual_board_quat']
            hand.q=solved_joints[i].copy();hand.robot.set_qpos(hand.q,zero_velocity=True)
            error,angle_error=solved_errors[i]
            metrics=model.audit_frame(v,bp,bq)
            metrics.update(frame=i,phase=frame['phase'],ik_position_error_mm=1000*error,
                           ik_rotation_error_deg=float(np.degrees(angle_error)),
                           pad_table_clearance_mm=float(pad_vertices(hand.robot,'robotiq_2f85')[:,2].min()-origin[2])*1000,
                           robot_table_clearance_mm=hand.table_clearance(origin[2])*1000)
            audit.append(metrics);joint_frames.append(hand.q.copy());mesh_frames.append(v.astype(np.float32))
            if i%10==0 or i==len(frames)-1:
                robot_vertices=as_numpy(hand.robot.get_vverts()).reshape(-1,3)
                for name in exterior_margins:
                    cam=table.cameras[name]
                    transform=cam.transform.copy();transform[:3,1:3]*=-1
                    ext=np.linalg.inv(transform)
                    cp=robot_vertices@ext[:3,:3].T+ext[:3,3]
                    pixels=cp@cam.intrinsics.T;pixels=pixels[:,:2]/pixels[:,2:3]
                    w,h=cam.res
                    margin=min(float(pixels[:,0].min()),float(pixels[:,1].min()-82),
                               float(w-1-pixels[:,0].max()),float(h-36-pixels[:,1].max()))
                    exterior_margins[name]=min(exterior_margins[name],margin)
            if cfg.run.audit_only:continue
            if cfg.run.preview and i%30 and i!=len(frames)-1:continue
            board.set_pos(bp+origin);board.set_quat(bq)
            mark.set_pos(bp+origin+rot(bq).apply([0,0,model.board_size[2]/2+.0003]));mark.set_quat(bq)
            table.scene.visualizer.update_visual_states(force_render=True)
            # Explicit visual-only upload. PBD does not advance and does not
            # determine these vertices. One cloth entity owns the full buffer.
            display_vertices[0]=(v[order]+origin).astype(np.float32)[:,None,:]
            cloth.solver.vverts_render.pos.from_numpy(display_vertices[0])
            next(iter(sensors.values()))._render_current_state()
            for name,sensor in sensors.items():
                im=Image.fromarray(nyx.rgb(sensor));draw=ImageDraw.Draw(im);w,h=im.size
                draw.rectangle((0,0,w,82),fill=(19,28,34));draw.rectangle((0,h-35,w,h),fill=(19,28,34))
                draw.text((18,7),'红布解包 · 翻面与刚性板取出',font=fonts[30 if w>=1200 else 24],fill=(242,242,234))
                draw.text((18,49),frame['phase'],font=fonts[18],fill=(238,174,159))
                draw.text((14,h-30),f'{LABELS[name]} | {frame["time_s"]:05.2f}s | 任务机制预览 · 规定布形 / 辅助抓持',font=fonts[18],fill=(201,211,214))
                if writers:writers[name].append_data(np.asarray(im))
                if cfg.run.preview or i%100==0 or i==len(frames)-1:im.save(media/f'frame_{i:04d}_{name}.jpg',quality=94)
                if i==len(frames)-1:im.save(media/f'final_{name}.jpg',quality=94)
            if i%30==0:print(f'render {i}/{len(frames)} | IK {error*1000:.3f} mm | {frame["phase"]}',flush=True)
    report=dict(kind='Task mechanism preview with prescribed cloth geometry and assisted object poses',
        dynamics_validated=False,flip_necessity_proven=False,cloth_shape='one continuous cross-shaped sheet',
        cameras=list(sensors),frames=len(frames),fps=int(cfg.run.fps),duration_s=len(frames)/cfg.run.fps,
        cloth_vertices=len(model.flat),cloth_faces=len(model.faces),
        max_ik_position_error_mm=max(x['ik_position_error_mm'] for x in audit),
        max_ik_rotation_error_deg=max(x['ik_rotation_error_deg'] for x in audit),
        max_mesh_edge_length_change=max(x['max_edge_length_change'] for x in audit),
        cloth_board_interior_sample_frames=sum(x['cloth_board_interior_samples']>0 for x in audit),
        minimum_cloth_table_clearance_mm=min(x['min_cloth_z'] for x in audit)*1000,
        minimum_finger_pad_table_clearance_mm=min(x['pad_table_clearance_mm'] for x in audit),
        minimum_moving_robot_table_clearance_mm=min(x['robot_table_clearance_mm'] for x in audit),
        max_arm_joint_frame_step_rad=float(np.abs(np.diff(np.array(joint_frames)[:,:7],axis=0)).max()),
        free_joint_transitions=repaired,
        primary_camera_arm_margin_px=exterior_margins,
        primary_camera_framing=camera_fit,
        final_active_assist=frames[-1]['grasp'],
        limitations=['No cloth dynamics or friction validation','No gripper collision/contact dynamics validation',
                     'No cloth self-collision validation','No claim of necessary flipping or unique layer sequence'])
    (media/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (media/'trajectory_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    serial=[{k:v.tolist() if isinstance(v,np.ndarray) else float(v) if isinstance(v,np.floating) else v for k,v in f.items()} for f in frames]
    (media/'frames.json').write_text(json.dumps(serial,ensure_ascii=False,indent=2))
    np.savez_compressed(media/'trajectory.npz',qpos=np.array(joint_frames),positions=np.array(mesh_frames),faces=model.faces)
    if not cfg.run.preview and not cfg.run.audit_only:write_player(output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
