"""Articulated finite-radius cord and closed terminal attachment in MuJoCo.

This module supplies a physical planning sandbox. Mocap grasp fixtures are
explicit local probes, not robot execution or a qualification of the task.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.spatial.transform import Rotation

from .geometry import OrbitsLayout


def vector(x):
    return " ".join(f"{v:.12g}" for v in np.asarray(x).ravel())


def resample(points, spacing=.006):
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    samples = np.linspace(0., arc[-1], int(np.ceil(arc[-1]/spacing))+1)
    return np.column_stack([np.interp(samples, arc, points[:, i]) for i in range(3)])


def working_cord(layout, spacing=.006):
    """Legacy folded slack used by the recorded development probes.

    This doubles back beyond the handle. New bimanual scenes use
    natural_working_state instead; retain this shape for old probe/fixture parity.
    """
    l = layout
    z = l.base_height_m+l.cord_radius_m+.0015
    control = np.array([[l.post_x[-1], l.bight_radius_m, z],
                        [.185, .012, z], [.215, .04, .005],
                        [.265, .14, .005], [.42, .16, .005],
                        [.54, .10, .005], [.52, .025, .005],
                        [.39, .015, .005],
                        [l.eyes[1, 0]+.012, l.eyes[1, 1], l.handle_height_m+.014],
                        [l.eyes[1, 0], l.eyes[1, 1], l.handle_height_m+.010],
                        [l.eyes[1, 0], l.eyes[1, 1], l.handle_height_m*.55]])
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(control,axis=0),axis=1))]
    positive=PchipInterpolator(arc,control,axis=0)(np.linspace(0,arc[-1],700))
    negative=positive.copy();negative[:,1]*=-1
    theta=np.linspace(-np.pi/2,-3*np.pi/2,80)
    bend=np.column_stack([l.post_x[-1]+l.bight_radius_m*np.cos(theta),
                          l.bight_radius_m*np.sin(theta),np.full(len(theta),z)])
    # Each half uses identical material sampling so the true bight is a vertex.
    left=resample(np.vstack([negative[::-1],bend[1:41]]),spacing)
    right=left[::-1].copy();right[:,1]*=-1
    left[-1,1]=right[0,1]=0.
    return np.vstack([left,right[1:]])


def natural_working_state(layout, *, handle_x_m=.60, cord_length_m=None,
                          spacing=.0075):
    """Lay one open oval around post5, with the free handle at its far end.

    Slack bows outward on either side; neither leg doubles back past its eye.
    Length is preserved from the legacy working cord unless explicitly supplied.
    Returned points describe the rest shape, not positions driven during motion.
    """
    from dataclasses import replace
    from scipy.optimize import brentq
    from .geometry import cord_centerline
    l = layout
    if not np.isfinite([handle_x_m, spacing]).all() or spacing <= 0:
        raise ValueError('Handle position and spacing must be finite; spacing positive')
    placed = replace(l, handle_x_m=float(handle_x_m)).validate()
    if cord_length_m is None:
        old = working_cord(l, spacing)
        cord_length_m = float(np.linalg.norm(np.diff(old, axis=0), axis=1).sum())
    if not np.isfinite(cord_length_m) or cord_length_m <= 0:
        raise ValueError('Cord length must be positive and finite')
    dense = cord_centerline(placed)
    half = dense[len(dense)//2:].copy()
    half = np.vstack([[l.post_x[-1]-l.bight_radius_m, 0, half[0, 2]], half])
    t = np.clip((half[:, 0]-l.post_x[-1]) /
                (placed.eyes[1, 0]-.006*l.template_scale-l.post_x[-1]), 0, 1)
    samples = int(np.ceil(cord_length_m/(2*spacing)))+1

    def shaped(width):
        points = half.copy()
        points[:, 1] += width*np.sin(np.pi*t)**2
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        query = np.linspace(0, arc[-1], samples)
        return np.column_stack([np.interp(query, arc, points[:, i]) for i in range(3)])

    def excess(width):
        return 2*np.linalg.norm(np.diff(shaped(width), axis=0), axis=1).sum()-cord_length_m

    if excess(0) > 1e-10:
        raise ValueError('Cord too short to reach the requested handle position')
    width = brentq(excess, 0, cord_length_m/2, xtol=1e-12)
    positive = shaped(width)
    negative = positive[::-1].copy(); negative[:, 1] *= -1
    points = np.vstack([negative, positive[1:]])
    handle = np.array([handle_x_m, 0, l.handle_height_m/2+l.clearance_m])
    return points, handle


def build_probe(path, *, dt=.0005, spacing=.006, model_kind="flex", initial_points=None,
                handle_position=None):
    l=OrbitsLayout().scaled(.75)
    points=working_cord(l,spacing) if initial_points is None else np.asarray(initial_points).copy()
    hand_origin=np.array([l.handle_x_m,0,l.handle_height_m/2+.00135])
    hand_position=hand_origin if handle_position is None else np.asarray(handle_position)
    root=ET.Element('mujoco',model='orbits_physical_probe')
    ET.SubElement(root,'compiler',angle='radian',autolimits='true')
    ET.SubElement(root,'option',timestep=str(dt),gravity='0 0 -9.81',
                  integrator='implicitfast',solver='Newton',iterations='80',
                  tolerance='1e-9',jacobian='sparse')
    defaults=ET.SubElement(root,'default')
    ET.SubElement(defaults,'geom',friction='.25 .001 .00001',solref='.001 1',
                  solimp='.9999 .99999 .0001',condim='3',density='700')
    world=ET.SubElement(root,'worldbody')
    ET.SubElement(world,'light',pos='0 -.4 1.2',diffuse='.8 .8 .8')
    ET.SubElement(world,'geom',name='table',type='plane',size='1 1 .01',rgba='.75 .75 .75 1')
    wood=dict(rgba='.42 .22 .10 1',contype='1',conaffinity='1')
    ET.SubElement(world,'geom',name='base',type='box',pos=vector([0,0,l.base_height_m/2]),
                  size=vector([l.base_length_m/2,l.base_width_m/2,l.base_height_m/2]),**wood)
    for i,(x,z) in enumerate(zip(l.post_x,[l.ball_z,*l.ring_z])):
        ET.SubElement(world,'geom',name=f'post_{i+1}',type='cylinder',
                      fromto=vector([x,0,l.base_height_m,x,0,z]),size=str(l.post_radius_m),**wood)
    ET.SubElement(world,'geom',name='ball',type='sphere',pos=vector([l.post_x[0],0,l.ball_z]),
                  size=str(l.ball_radius_m),**wood)
    for i,(x,z) in enumerate(zip(l.ring_x,l.ring_z)):
        theta=np.arange(97)*2*np.pi/96
        circle=np.column_stack([x+l.ring_radius_m*np.cos(theta),l.ring_radius_m*np.sin(theta),np.full(97,z)])
        for j,(a,b) in enumerate(zip(circle[:-1],circle[1:])):
            ET.SubElement(world,'geom',name=f'ring_{i+1}_{j}',type='capsule',
                          fromto=vector([a,b]),size=str(l.ring_tube_radius_m),**wood)
    handle=ET.SubElement(world,'body',name='handle',pos=vector(hand_position))
    ET.SubElement(handle,'freejoint',name='handle_free')
    ET.SubElement(handle,'geom',name='handle_geom',type='ellipsoid',
                  size=vector([l.handle_length_m/2,l.handle_width_m/2,l.handle_height_m/2]),mass='.012',**wood)
    # Convex prisms preserve both bores. The 48-sided outer ellipse and
    # 24-sided bores deviate from the visual surfaces by at most 0.054 mm.
    import trimesh
    from shapely import affinity
    from shapely.geometry import Point
    handle.remove(handle.find('geom'))
    ET.SubElement(handle,'inertial',pos='0 0 0',mass='.012',diaginertia='0.000001 0.000003 0.000003')
    asset=ET.SubElement(root,'asset')
    outline=affinity.scale(Point(l.handle_x_m,0).buffer(1,quad_segs=12),
                          xfact=l.handle_length_m/2,yfact=l.handle_width_m/2)
    for eye in l.eyes:outline=outline.difference(Point(*eye).buffer(l.handle_eye_radius_m,quad_segs=6))
    mesh=trimesh.creation.extrude_polygon(outline,l.handle_height_m,engine='earcut')
    mesh.apply_translation([0,0,l.clearance_m])
    zmin,zmax=mesh.bounds[:,2]
    for i,face in enumerate(mesh.faces[np.all(np.isclose(mesh.vertices[mesh.faces,2],zmax),axis=1)]):
        high=mesh.vertices[face].copy();low=high.copy();low[:,2]=zmin
        vertices=np.vstack([low,high])-hand_origin
        name=f'handle_prism_{i}'
        ET.SubElement(asset,'mesh',name=name,vertex=vector(vertices),face='0 2 1 3 4 5 0 1 4 0 4 3 1 2 5 1 5 4 2 0 3 2 3 5')
        ET.SubElement(handle,'geom',name=name,type='mesh',mesh=name,mass='0',**wood)
    equality=ET.SubElement(root,'equality')
    contact=ET.SubElement(root,'contact')
    parent=world;old_r=Rotation.identity();old_p=np.zeros(3)
    for i,(a,b) in enumerate(zip(points[:-1],points[1:])):
        direction=(b-a)/np.linalg.norm(b-a)
        y=np.cross([0,0,1],direction)
        if np.linalg.norm(y)<1e-8:y=np.cross([0,1,0],direction)
        y/=np.linalg.norm(y)
        r=Rotation.from_matrix(np.column_stack([direction,y,np.cross(direction,y)]))
        body=ET.SubElement(parent,'body',name=f'cord_{i}',pos=vector(old_r.inv().apply(a-old_p)),
                          quat=vector((old_r.inv()*r).as_quat()[[3,0,1,2]]))
        if i==0:ET.SubElement(body,'freejoint',name='cord_free')
        else:ET.SubElement(body,'joint',name=f'bend_{i}',type='ball',damping='0.000001',armature='1e-9')
        ET.SubElement(body,'geom',name=f'cord_geom_{i}',type='capsule',
                      fromto=vector([0,0,0,np.linalg.norm(b-a),0,0]),size=str(l.cord_radius_m),
                      rgba='.95 .78 .03 1')
        ET.SubElement(body,'site',name=f'node_{i}',pos='0 0 0',size='.001',rgba='0 0 0 0')
        if i==len(points)-2:
            ET.SubElement(body,'site',name=f'node_{i+1}',pos=vector([np.linalg.norm(b-a),0,0]),size='.001',rgba='0 0 0 0')
        for j in range(max(0,i-2),i):ET.SubElement(contact,'exclude',body1=f'cord_{j}',body2=f'cord_{i}')
        if i<5 or i>len(points)-7:ET.SubElement(contact,'exclude',body1='handle',body2=f'cord_{i}')
        parent,old_r,old_p=body,r,a
    for i,end in enumerate([0,len(points)-1]):
        ET.SubElement(handle,'site',name=f'eye_{i}',pos=vector(points[end]-hand_position),size='.001',rgba='0 0 0 0')
        ET.SubElement(equality,'connect',name=f'terminal_{i}',site1=f'eye_{i}',site2=f'node_{end}',solref='.002 1')
    midpoint=len(points)//2
    for name,pos,site in [('bight',points[midpoint],f'node_{midpoint}'),('handle',hand_position,'handle_center')]:
        anchor=ET.SubElement(world,'body',name=f'probe_{name}',mocap='true',pos=vector(pos))
        ET.SubElement(anchor,'site',name=f'probe_{name}_site',size='.002',rgba='0 .5 1 1')
        if name=='handle':ET.SubElement(handle,'site',name=site,pos='0 0 0',size='.001',rgba='0 0 0 0')
        ET.SubElement(equality,'connect',name=f'grasp_{name}',site1=f'probe_{name}_site',site2=site,solref='.003 1')
    for i in range(2):
        anchor=ET.SubElement(world,'body',name=f'probe_fold_{i}',mocap='true',pos=vector(points[midpoint]))
        ET.SubElement(anchor,'site',name=f'probe_fold_site_{i}',size='.002',rgba='0 .5 1 1')
        ET.SubElement(equality,'connect',name=f'grasp_fold_{i}',site1=f'probe_fold_site_{i}',
                      site2=f'node_{midpoint}',active='false',solref='.003 1')
    if model_kind == 'flex':
        # Independent translational nodes keep the constraint Jacobian local.
        world.remove(world.find("body[@name='cord_0']"))
        root.remove(contact)
        for i,point in enumerate(points):
            body=ET.SubElement(world,'body',name=f'cord_{i}',pos=vector(point))
            ET.SubElement(body,'inertial',pos='0 0 0',mass=str(700*np.pi*l.cord_radius_m**2*spacing),diaginertia='1e-9 1e-9 1e-9')
            for axis in np.eye(3):ET.SubElement(body,'joint',type='slide',axis=vector(axis),damping='.0002')
            ET.SubElement(body,'site',name=f'node_{i}',pos='0 0 0',size='.001',rgba='0 0 0 0')
        deformable=ET.SubElement(root,'deformable')
        flex=ET.SubElement(deformable,'flex',name='cord',dim='1',radius=str(l.cord_radius_m),
                          body=' '.join(f'cord_{i}' for i in range(len(points))),
                          element=' '.join(f'{i} {i+1}' for i in range(len(points)-1)),rgba='.95 .78 .03 1')
        ET.SubElement(flex,'contact',selfcollide='auto',internal='false',friction='.25 .001 .00001',
                      solref='.001 1',solimp='.9999 .99999 .0001')
        ET.SubElement(equality,'flex',flex='cord',solref='.001 1',solimp='.99 .999 .0005')
    ET.indent(root)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(root).write(path,encoding='unicode')
    model=mujoco.MjModel.from_xml_path(str(path))
    return model,points,l


class Probe:
    def __init__(self,path,*,checkpoint_each_phase=False,
                 max_penetration_m=None, max_grasp_error_m=None, **kwargs):
        self.folder=Path(path).parent
        self.checkpoint_each_phase=checkpoint_each_phase
        self.max_penetration_m=max_penetration_m
        self.max_grasp_error_m=max_grasp_error_m
        self.model,self.initial,self.layout=build_probe(path,**kwargs)
        self.data=mujoco.MjData(self.model)
        self.nodes=[self.model.site(f'node_{i}').id for i in range(len(self.initial))]
        self.bight_id=self.model.body('probe_bight').mocapid[0]
        self.handle_id=self.model.body('probe_handle').mocapid[0]
        self.fold_ids=[self.model.body(f'probe_fold_{i}').mocapid[0] for i in range(2)]
        self.held_nodes=None
        self.frames=[];self.metrics=[]
        self.step_count=0
        self.events=[]
        mujoco.mj_forward(self.model,self.data)

    def points(self):
        return self.data.site_xpos[self.nodes].copy()

    def grasp_nodes(self,indices):
        self.data.eq_active[self.model.equality('grasp_bight').id]=False
        self.held_nodes=list(indices)
        current=self.points()[indices]
        self.fold_offsets=current-current.mean(0)
        for i,node in enumerate(indices):
            eid=self.model.equality(f'grasp_fold_{i}').id
            self.model.eq_obj2id[eid]=self.model.site(f'node_{node}').id
            self.data.mocap_pos[self.fold_ids[i]]=current[i]
            self.data.eq_active[eid]=True
        self.events.append(dict(time_s=self.data.time,event='fixture_grasp_nodes',nodes=list(map(int,indices)),points_m=current.tolist()))
        return current.mean(0)

    def grasp_midpoint(self):
        return self.grasp_node(len(self.initial)//2)

    def grasp_node(self, index):
        """Acquire one material point; an interior strand forms a new bight."""
        point=self.points()[index]
        for i in range(2):self.data.eq_active[self.model.equality(f'grasp_fold_{i}').id]=False
        self.model.eq_obj2id[self.model.equality('grasp_bight').id]=self.nodes[index]
        self.data.mocap_pos[self.bight_id]=point
        self.data.eq_active[self.model.equality('grasp_bight').id]=True
        self.held_nodes=None
        self.events.append(dict(time_s=self.data.time,event='fixture_grasp_material_point',node=int(index),point_m=point.tolist()))
        return point

    def pin_node(self, slot, index):
        """Use one auxiliary fixture without releasing the other material hold."""
        point = self.points()[index]
        eid = self.model.equality(f'grasp_fold_{slot}').id
        self.model.eq_obj2id[eid] = self.nodes[index]
        self.data.mocap_pos[self.fold_ids[slot]] = point
        self.data.eq_active[eid] = True
        self.events.append(dict(time_s=self.data.time, event='fixture_pin_material_point',
                                slot=int(slot), node=int(index), point_m=point.tolist()))
        return point

    def restore(self,folder):
        path=Path(folder)
        with np.load(path if path.is_file() else path/'checkpoint.npz') as state:
            for name in ('qpos','qvel','mocap_pos','mocap_quat','eq_active'):
                getattr(self.data,name)[:]=state[name]
            self.data.time=float(state['time_s'])
            if 'eq_obj2id' in state:self.model.eq_obj2id[:]=state['eq_obj2id']
            if 'held_nodes' in state and len(state['held_nodes']):
                self.held_nodes=state['held_nodes'].tolist()
                self.fold_offsets=state['fold_offsets']
        mujoco.mj_forward(self.model,self.data)

    def move(self,name,bight=None,handle=None,seconds=2.,span=None,anchors=None,
             step_callback=None):
        if step_callback is not None and not callable(step_callback):
            raise TypeError('step_callback must be callable')
        start=self.data.mocap_pos.copy();target=start.copy()
        if span is not None:
            if self.held_nodes is None:raise ValueError('Spreading requires two material grasps')
            self.fold_offsets[:,1]=np.sign(self.fold_offsets[:,1])*span/2
            if bight is None:bight=start[self.fold_ids].mean(0)
        if bight is not None:
            if self.held_nodes is None:target[self.bight_id]=bight
            else:target[self.fold_ids]=np.asarray(bight)+self.fold_offsets
        if handle is not None:target[self.handle_id]=handle
        for slot, point in (anchors or {}).items():
            anchor = (self.bight_id if slot == 'bight' else
                      self.handle_id if slot == 'handle' else self.fold_ids[slot])
            target[anchor]=point
        if not np.isfinite(seconds) or seconds <= 0 or not np.isfinite(target).all():
            raise ValueError('Probe motion requires finite targets and positive duration')
        # A necessary physical bound: the straight distance between two held
        # material points cannot exceed the intervening rest length. Obstacle
        # detours can require more length, so passing this is not a path proof.
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(self.initial, axis=0), axis=1))]
        held_targets = []
        for key in ('grasp_bight', 'grasp_fold_0', 'grasp_fold_1'):
            eid = self.model.equality(key).id
            if not self.data.eq_active[eid]:
                continue
            node = self.nodes.index(int(self.model.eq_obj2id[eid]))
            body = self.model.site_bodyid[self.model.eq_obj1id[eid]]
            held_targets.append((node, target[self.model.body_mocapid[body]]))
        for i, (a, pa) in enumerate(held_targets):
            for b, pb in held_targets[i+1:]:
                if np.linalg.norm(pa-pb) > abs(arc[b]-arc[a])+.001:
                    raise ValueError(f'Grasps {a} and {b} exceed intervening cord length')
        steps=round(seconds/self.model.opt.timestep)
        if steps < 1:
            raise ValueError('Probe duration is shorter than one simulation step')
        self.events.append(dict(event='fixture_motion_command',phase=name,
            time_s=float(self.data.time),duration_s=float(seconds),
            start_mocap_positions_m=start.tolist(),target_mocap_positions_m=target.tolist(),
            active_equalities=self.data.eq_active.tolist(),
            target_site_ids=self.model.eq_obj2id.tolist()))
        penetration=0.;error=0.;worst_contact=None
        if not self.frames:
            self.frames.append((self.data.time,name,self.points(),self.data.qpos.copy()))
        for i in range(steps):
            u=(i+1)/steps;s=u*u*(3-2*u)
            self.data.mocap_pos[:]=start+s*(target-start)
            if step_callback is not None:
                step_callback(self.model,self.data)
            mujoco.mj_step(self.model,self.data)
            self.step_count += 1
            if i%10==0:
                mujoco.mj_kinematics(self.model,self.data)
                for contact in self.data.contact:
                    if -contact.dist > penetration:
                        penetration=float(-contact.dist)
                        worst_contact=dict(time_s=float(self.data.time),
                            geometry=[self.model.geom(int(g)).name if g >= 0 else 'flex_cord'
                                      for g in contact.geom],
                            flex_elements=contact.elem.tolist(), position_m=contact.pos.tolist())
                active = [self.model.equality(key).id for key in
                          ('grasp_bight','grasp_handle','grasp_fold_0','grasp_fold_1')
                          if self.data.eq_active[self.model.equality(key).id]]
                held = [self.nodes.index(int(self.model.eq_obj2id[e])) for e in active
                        if int(self.model.eq_obj2id[e]) in self.nodes]
                if active:
                    errors = self.data.site_xpos[self.model.eq_obj1id[active]]-self.data.site_xpos[self.model.eq_obj2id[active]]
                    error=max(error,float(np.linalg.norm(errors,axis=1).max()))
                if ((self.max_penetration_m is not None and penetration > self.max_penetration_m) or
                    (self.max_grasp_error_m is not None and error > self.max_grasp_error_m)):
                    self.events.append(dict(event='physical_probe_guard_stop',phase=name,
                        time_s=float(self.data.time),penetration_m=penetration,
                        grasp_error_m=error,worst_contact=worst_contact))
                    self.save(self.folder)
                    raise RuntimeError(f'{name}: physical probe guard stopped motion: '
                                       f'penetration={penetration:.6f}, grasp_error={error:.6f}')
            if self.step_count%50==0:
                mujoco.mj_kinematics(self.model,self.data)
                self.frames.append((self.data.time,name,self.points(),self.data.qpos.copy()))
        mujoco.mj_kinematics(self.model,self.data)
        self.metrics.append(dict(phase=name,time_s=self.data.time,penetration_m=penetration,grasp_error_m=error,bight=self.points()[len(self.initial)//2].tolist()))
        self.metrics[-1]['held_material_nodes']=held
        self.metrics[-1]['worst_contact']=worst_contact
        self.metrics[-1]['held_points']=self.points()[held].tolist()
        from .verification import threading_signature
        signature=threading_signature(self.points(),self.layout)
        self.metrics[-1]['winding']=signature['planar_post_winding']
        self.metrics[-1]['ring_crossing_counts']=[len(v) for v in signature['ring_disk_crossings']]
        print(self.metrics[-1],flush=True)
        if self.checkpoint_each_phase:
            checkpoint=self.folder/'phase_checkpoints'/f'{len(self.metrics):03d}.npz'
            checkpoint.parent.mkdir(parents=True,exist_ok=True)
            self.save_checkpoint(checkpoint)
            self.metrics[-1]['checkpoint']=str(checkpoint.relative_to(self.folder))
            self.save(self.folder)

    def save_checkpoint(self,path):
        np.savez_compressed(path,qpos=self.data.qpos,qvel=self.data.qvel,
                            time_s=self.data.time,mocap_pos=self.data.mocap_pos,mocap_quat=self.data.mocap_quat,
                            eq_active=self.data.eq_active,eq_obj2id=self.model.eq_obj2id,
                            held_nodes=[] if self.held_nodes is None else self.held_nodes,
                            fold_offsets=getattr(self,'fold_offsets',np.zeros((2,3))))

    def save(self,folder):
        import json
        folder=Path(folder)
        if not self.frames or self.frames[-1][0] != self.data.time:
            self.frames.append((self.data.time,'final',self.points(),self.data.qpos.copy()))
        np.savez_compressed(folder/'probe_trajectory.npz',time_s=[f[0] for f in self.frames],phase=[f[1] for f in self.frames],points=[f[2] for f in self.frames],qpos=[f[3] for f in self.frames])
        self.save_checkpoint(folder/'checkpoint.npz')
        (folder/'probe_report.json').write_text(json.dumps(dict(scope='mocap_fixture_physics_probe_not_robot',metrics=self.metrics,events=self.events),indent=2)+'\n')
