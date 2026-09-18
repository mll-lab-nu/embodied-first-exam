"""Physical positive/negative aperture controls, separate from robot execution.

Two six-DOF keys face identical fixed first discs. A finite force controller
attempts the same insertion with aligned and deliberately wrong orientation.
Gravity is disabled only in this isolated aperture bench, disclosed in reports.
"""
from dataclasses import asdict
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.lock_picking._staged_lock_geometry import LockGeometry, write_disc, write_key
from demos.environment_bootstrap.chain_links import array
from topogym.core import EntityManifest
from topogym.world.presentation import add_preview_camera


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('runs/environment_bootstrap/lock_picking/aperture_controls'))
    parser.add_argument('--renderer',choices=('nyx','rasterizer'),default='nyx')
    args=parser.parse_args()
    import genesis as gs
    import imageio.v2 as imageio
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    g=LockGeometry(slots=((-60.,-30.,0.),(-60.,),(0.,)),initial_disc_deg=(0.,0.,0.),
                   slot_half_deg=8.,bore_radius=.0075)
    g.validate()
    dt=.002
    config=dict(geometry=asdict(g),dt=dt,substeps=8,gravity=[0,0,0],
        rendering=dict(renderer=args.renderer,background="compact_lab"),
        disc_x_m=.15,key_start_x_m=.12,target_x_m=.18,angles_deg=[0,45],
        max_actuator_force_per_axis_N=.2,max_actuator_torque_per_axis_Nm=.02,
        constraint_timeconst_s=.001,friction=.01,iterations=100,seconds=4.)
    (output/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    gs.init(backend=gs.cuda,logging_level='warning',seed=0)
    scene=gs.Scene(show_viewer=False,sim_options=gs.options.SimOptions(dt=dt,substeps=8,gravity=(0,0,0)),
        rigid_options=gs.options.RigidOptions(enable_collision=True,iterations=100,
            max_collision_pairs=512,constraint_timeconst=.001))
    keys=[];discs=[];targets=[];quaternions=[]
    for i,angle in enumerate(config['angles_deg']):
        y=(-.13,.13)[i]
        folder=output/'assets'/str(i)
        path=write_disc(g,g.slots[0],folder/'disc',.2,.03,(.7,.5,.2),fixed=True)
        discs.append(scene.add_entity(gs.morphs.URDF(file=str(path),pos=(.15,y,.5),fixed=True,
            merge_fixed_links=False,convexify=True,decimate=False),material=gs.materials.Rigid(friction=.01)))
        path=write_key(g,folder/'key',.12)
        q=Rotation.from_euler('x',-angle,degrees=True).as_quat()[[3,0,1,2]]
        keys.append(scene.add_entity(gs.morphs.URDF(file=str(path),pos=(.12,y,.5),quat=q,
            fixed=False,align=False,merge_fixed_links=False,convexify=True,decimate=False),
            material=gs.materials.Rigid(friction=.01)))
        targets.append(np.array([.18,y,.5]));quaternions.append(q)
    camera=add_preview_camera(scene,EntityManifest(),res=(960,600),pos=(.65,-.65,.95),
                             lookat=(0,0,.5),fov=44,renderer=args.renderer)
    scene.build()
    imageio.imwrite(output/'initial.png',camera.render()[0])
    force_max=[0.,0.];max_penetration=0.;records=[]
    for step in range(round(4/dt)):
        for key,target,qtarget in zip(keys,targets,quaternions):
            p=array(key.get_pos()).reshape(3);q=array(key.get_quat()).reshape(4)
            v=array(key.get_vel()).reshape(3);w=array(key.get_ang()).reshape(3)
            rot=(Rotation.from_quat(qtarget[[1,2,3,0]])*Rotation.from_quat(q[[1,2,3,0]]).inv()).as_rotvec()
            force=np.array([10,40,40])*(target-p)-2*v
            torque=.05*rot-.004*w
            key.control_dofs_force(np.r_[np.clip(force,-.2,.2),np.clip(torque,-.02,.02)])
        scene.step()
        for i,key in enumerate(keys):
            contacts=key.get_contacts(with_entity=discs[i])
            f=array(contacts['force_a']).reshape(-1,3)
            force_max[i]=max(force_max[i],float(np.linalg.norm(f,axis=1).sum()) if f.size else 0.)
        penetration=array(scene.sim.rigid_solver.collider.get_contacts()['penetration'])
        if penetration.size:max_penetration=max(max_penetration,float(penetration.max()))
        if step%25==0:
            records.append(dict(time_s=(step+1)*dt,key_positions=[array(k.get_pos()).tolist() for k in keys]))
    positions=[array(k.get_pos()).reshape(3).tolist() for k in keys]
    checks=dict(aligned_passes=positions[0][0]>.16,wrong_orientation_blocked=positions[1][0]<.148,
        blocking_contact_recorded=force_max[1]>.02,penetration_ok=max_penetration<.0005,
        free_keys=all(k.n_dofs==6 for k in keys))
    report=dict(task_id='lock_picking',scope='isolated_fixed_disc_aperture_controls',passed=all(checks.values()),
        checks=checks,final_key_positions_m=positions,max_key_disc_force_N=force_max,
        max_penetration_m=max_penetration,config=config,pose_writes_after_reset=False,
        limitation='Gravity-free finite-force fixture probe; full gravity/robot evidence is a separate rollout.')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (output/'frames.json').write_text(json.dumps(records,indent=2,allow_nan=False)+'\n')
    imageio.imwrite(output/'final.png',camera.render()[0])
    print(json.dumps(report,indent=2),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
