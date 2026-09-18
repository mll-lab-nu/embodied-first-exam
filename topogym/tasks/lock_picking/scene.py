"""Passive slotted discs and a free rigid key picked up from physical V rests."""
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
import genesis as gs
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.world import StandardTabletopSceneBuilder
from ._staged_lock_geometry import LockGeometry, variant_geometry, write_disc, write_key, write_endpoint, goal_mark_assets, key_rest_layout, write_key_cradle
from ._aperture_outline import paint_aperture_outline

StagedLockLayout = LockGeometry


def numpy(value):
    return value.detach().cpu().numpy() if hasattr(value,'detach') else np.asarray(value)


@dataclass
class StagedLockScene:
    tabletop: Any
    layout: LockGeometry
    discs: list
    key: Any
    endpoint: Any
    cfg: Any
    key_spawn_pos: Any
    force_limit_triggered: bool = False
    max_key_contact_force: float = 0.
    max_contact_penetration: float = 0.
    last_contacts: Any = None
    settling_after_stop: bool = False
    geometry_error_steps: int = 0

    @property
    def scene(self): return self.tabletop.scene
    @property
    def manifest(self): return self.tabletop.manifest
    @property
    def cameras(self): return self.tabletop.cameras

    def state(self):
        g=self.layout
        p=numpy(self.key.get_pos(relative=False)).reshape(3)
        q=numpy(self.key.get_quat(relative=False)).reshape(4)
        rot=Rotation.from_quat(q[[1,2,3,0]]).as_matrix()
        return dict(depth=float((p[0]-g.tip_x(0))/g.pitch),key_deg=float(np.degrees(np.arctan2(rot[1,2],rot[2,2]))),
                    key_tip_pos=p.tolist(),key_quat=q.tolist(),
                    axis_offset=float(np.linalg.norm(p[1:]-[g.center_y,g.axis_z])),
                    axis_tilt_deg=float(np.degrees(np.arccos(np.clip(rot[0,0],-1,1)))),
                    disc_deg=[float(np.degrees(numpy(d.get_qpos()).reshape(-1)[0])) for d in self.discs],
                    disc_speed=[float(numpy(d.get_dofs_velocity()).reshape(-1)[0]) for d in self.discs],
                    linear_speed=float(np.linalg.norm(numpy(self.key.get_vel()))),
                    angular_speed=float(np.linalg.norm(numpy(self.key.get_ang()))))

    def actual_grip_pos(self):
        state=self.state()
        rot=Rotation.from_quat(np.asarray(state['key_quat'])[[1,2,3,0]])
        return np.asarray(state['key_tip_pos'])+rot.apply([-self.layout.grip_offset,0,0])

    def support_state(self):
        contacts=self.last_contacts
        key_links=[link.idx for link in self.key.links]
        rest_links=[link.idx for name,entity in self.manifest.entities.items()
                    if name.startswith('lock_key_rest_') for link in entity.links]
        a,b=numpy(contacts['link_a']),numpy(contacts['link_b'])
        mask=(np.isin(a,key_links)&np.isin(b,rest_links))|(np.isin(b,key_links)&np.isin(a,rest_links))
        force=numpy(contacts['force'])[mask]
        vertical=float(np.abs(force[:,2]).sum()) if len(force) else 0.
        weight=float(self.cfg.physics.key_mass)*9.81
        return dict(contact_count=int(np.count_nonzero(mask)),vertical_contact_force=vertical,weight=weight,
                    weight_supported=bool(.75*weight<vertical<1.25*weight),key_dofs=int(self.key.n_dofs),
                    spawn_pos=list(self.key_spawn_pos),state=self.state())

    def install_contact_guard(self):
        """The force-stop contract applies to every downstream controller."""
        original=self.scene.step
        robot=self.manifest.get('robot')
        key_links=[link.idx for link in self.key.links]
        fixture_links=[link.idx for name,entity in self.manifest.entities.items()
                       if name.startswith('lock_') and name!='lock_key' for link in entity.links]

        def guarded_step(*args,**kwargs):
            if self.force_limit_triggered and not self.settling_after_stop:
                raise RuntimeError('Contact-stop episode is terminal; reset before further actions')
            result=original(*args,**kwargs)
            contacts=self.scene.sim.rigid_solver.collider.get_contacts()
            self.last_contacts=contacts
            penetration=numpy(contacts['penetration'])
            if penetration.size:
                self.max_contact_penetration=max(self.max_contact_penetration,float(penetration.max()))
            a,b=numpy(contacts['link_a']),numpy(contacts['link_b'])
            mask=(np.isin(a,key_links)&np.isin(b,fixture_links))|(np.isin(b,key_links)&np.isin(a,fixture_links))
            force=float(np.linalg.norm(numpy(contacts['force'])[mask],axis=-1).sum()) if np.any(mask) else 0.
            self.max_key_contact_force=max(self.max_key_contact_force,force)
            state=self.state()
            if self.layout.clearance(state['depth'],state['key_deg'],state['disc_deg'],tolerance=2.):
                self.geometry_error_steps+=1
            if force>float(self.cfg.physics.max_key_contact_force) and not self.force_limit_triggered:
                self.force_limit_triggered=True
                robot.control_dofs_position(robot.get_qpos())
                raise RuntimeError(f'Key contact force limit: {force:.3f} N; depth={self.state()["depth"]:.5f}')
            return result
        self.scene.step=guarded_step


class LockPickingSceneBuilder:
    def __init__(self,env_cfg,task_cfg,robot_cfg):
        self.env_cfg,self.task_cfg,self.robot_cfg=env_cfg,task_cfg,robot_cfg

    def build(self,*,show_viewer=False,before_finalize=None,asset_dir=None):
        t=self.task_cfg
        g=variant_geometry(LockGeometry.from_config(t.geometry),str(t.variant),int(t.seed))
        folder=Path(asset_dir or f'.cache/topogym/staged_lock/{t.variant}_{t.seed}').resolve()
        folder.mkdir(parents=True,exist_ok=True)
        builder=StandardTabletopSceneBuilder(self.env_cfg,self.robot_cfg,
            rigid_options=gs.options.RigidOptions(enable_collision=True,enable_self_collision=True,
                enable_joint_limit=bool(t.physics.get('enable_joint_limit',True)),max_collision_pairs=800,iterations=100,
                max_dynamic_constraints=4,constraint_timeconst=float(t.physics.contact_timeconst)))
        base=builder.create(show_viewer=show_viewer,include_robot=True,
                            robot_material=gs.materials.Rigid(gravity_compensation=1.0,friction=1.0))
        scene,manifest=base.scene,base.manifest
        material=gs.materials.Rigid(friction=float(t.physics.friction))
        discs=[]
        floor=float(self.env_cfg.frames.table_surface.origin[2])
        colors=((.76,.53,.23),(.20,.43,.60),(.72,.34,.22))
        stops=t.get('rotor_stops')
        outline=t.get('visual', {}).get('aperture_outline')
        if stops is not None and len(stops)!=3:
            raise ValueError('Provide one stop range for each of the three rotors')
        for i in range(3):
            stop=None if stops is None else stops[i]
            if stop is not None and not stop.bounds_deg[0] <= g.initial_disc_deg[i] <= stop.bounds_deg[1]:
                raise ValueError('Initial rotor angle is outside its physical stop range')
            path=write_disc(g,g.slots[i],folder/f'disc{i}',float(t.physics.disc_mass),float(t.physics.disc_damping),colors[i],stop=stop,mount_z=floor+.028-g.axis_z)
            paint_aperture_outline(path,g,g.slots[i],colors[i],outline)
            discs.append(manifest.add(f'lock_disc_{i+1}',scene.add_entity(
                gs.morphs.URDF(file=str(path),pos=(g.disc_x(i),g.center_y,g.axis_z),fixed=True,
                               convexify=True,decimate=False,merge_fixed_links=False,default_armature=0.),material=material,name=f'lock_disc_{i+1}')))
            if stop is not None:
                manifest.add(f'lock_stop_frame_{i+1}',scene.add_entity(gs.morphs.URDF(
                    file=str(path.parent/'limits'/'stop_frame.urdf'),
                    pos=(g.disc_x(i),g.center_y,g.axis_z),fixed=True,
                    convexify=True,decimate=False,merge_fixed_links=False),
                    material=gs.materials.Rigid(friction=.3),name=f'lock_stop_frame_{i+1}'))
        path=write_endpoint(g,folder/'endpoint')
        endpoint=manifest.add('lock_endpoint',scene.add_entity(gs.morphs.URDF(file=str(path),
            pos=(g.disc_x(3),g.center_y,g.axis_z),fixed=True,convexify=True,decimate=False,merge_fixed_links=False),material=material,name='lock_endpoint'))
        for name,path in goal_mark_assets(g,folder/'endpoint').items():
            color=(.96,.96,.88) if name=='label' else (.58,.62,.63)
            manifest.add(f'lock_goal_{name}',scene.add_entity(gs.morphs.Mesh(file=str(path),
                pos=(g.disc_x(3),g.center_y,g.axis_z),fixed=True,collision=False,decimate=False),
                surface=gs.surfaces.Plastic(color=color),name=f'lock_goal_{name}'))
        key_finish=None
        if str(self.env_cfg.renderer.type)=='nyx':
            for rule in self.env_cfg.get('appearance',[]):
                if fnmatchcase('lock_key',str(rule.pattern)):
                    key_finish=rule if rule.get('embed_urdf_pbr',False) else None
        path=write_key(g,folder/'key',float(t.physics.key_mass),visual_finish=key_finish)
        rest=key_rest_layout(g)
        key_spawn_pos=(g.tip_x(0),g.center_y,rest['resting_axis_z']+float(t.initialization.spawn_clearance))
        key_q=Rotation.from_euler('x',-g.initial_key_deg,degrees=True).as_quat()[[3,0,1,2]]
        key=manifest.add('lock_key',scene.add_entity(gs.morphs.URDF(file=str(path),
            pos=key_spawn_pos,quat=key_q, fixed=False,align=False,convexify=True,decimate=False,merge_fixed_links=False,default_armature=0.),
            material=material,name='lock_key'))
        floor=float(self.env_cfg.frames.table_surface.origin[2])

        def box(name,pos,size,color,collision=True):
            return manifest.add(name,scene.add_entity(gs.morphs.Box(pos=pos,size=size,fixed=True,collision=collision),
                surface=gs.surfaces.Plastic(color=color),name=name))

        start=g.tip_x(0)-g.grip_offset-.025
        end=g.disc_x(3)+.045
        integrated=stops is not None and any(s.get('style','rails')=='single_ring' for s in stops)
        box('lock_base',((start+end)/2,g.center_y,floor+.014),
            (end-start,max(2*g.disc_radius+.05,2.9*g.disc_radius if integrated else 0),.028),(.15,.19,.22))
        for i in range(4):
            if i<3 and stops is not None and stops[i].get('style','rails')=='single_ring':
                continue  # The fixed ring asset includes its matching mounting legs.
            x=g.disc_x(i)
            support_top=g.axis_z-g.disc_radius-.006
            if i==3: support_top=g.axis_z-g.disc_radius+.002
            box(f'lock_pedestal_{i}',(x,g.center_y,(floor+.028+support_top)/2),
                (.022,2*g.disc_radius+.03,support_top-floor-.028),(.32,.36,.39))
            # The target is a bolted panel seated on its pedestal, rather than
            # a fourth rotor held in the same pair of bearing supports.
            if i==3: continue
            bearing_bottom=support_top-.001
            bearing_top=g.axis_z+.015
            for sign in (-1,1):
                box(f'lock_bearing_{i}_{sign}',
                    (x,g.center_y+sign*(g.disc_radius+.008),(bearing_bottom+bearing_top)/2),
                    (.018,.012,bearing_top-bearing_bottom),(.28,.31,.34))
        if bool(t.initialization.rest_enabled):
            box('lock_key_rest_tray',((rest['tray_start']+rest['tray_end'])/2,g.center_y,rest['tray_top']-rest['tray_thickness']/2),
                (rest['tray_end']-rest['tray_start'],rest['tray_width'],rest['tray_thickness']),(.36,.40,.43))
            paths=write_key_cradle(rest,folder/'key_rest')
            for i,x in enumerate(rest['cradle_x']):
                bottom=floor+.028;top=rest['tray_top']-rest['tray_thickness']
                box(f'lock_key_rest_post_{i}',(x,g.center_y,(bottom+top)/2),(.024,.04,top-bottom),(.32,.36,.39))
                for j,path in enumerate(paths):
                    manifest.add(f'lock_key_rest_cradle_{i}_{j}',scene.add_entity(gs.morphs.Mesh(
                        file=str(path),pos=(x,g.center_y,rest['tray_top']),fixed=True,convexify=True,decimate=False),
                        material=gs.materials.Rigid(friction=.6),surface=gs.surfaces.Plastic(color=(.23,.27,.30)),
                        name=f'lock_key_rest_cradle_{i}_{j}'))
        result=StagedLockScene(base,g,discs,key,endpoint,t,key_spawn_pos)
        if before_finalize is not None: before_finalize(result)
        builder.finalize(base)
        for entity,angle in zip(discs,g.initial_disc_deg):
            entity.set_qpos([np.radians(angle)],zero_velocity=True)
        result.install_contact_guard()
        return result
