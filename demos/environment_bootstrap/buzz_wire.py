"""Centered passage and deliberate wire-contact tests using finite forces."""
from dataclasses import asdict
from importlib.metadata import version
import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.buzz_wire_3d.probe import BuzzProbeLayout, build_buzz_probe
from topogym.tasks.catalog import baseline_manifest, load_card
from topogym.tasks._rigid_geometry import RingGeometry
from demos.environment_bootstrap.chain_links import array


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("runs/environment_bootstrap/buzz_wire_3d/bend_contact"))
    parser.add_argument("--no-render",action="store_true")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    dt=.002
    baseline=load_card("buzz_wire_3d")["baseline"]
    layout=BuzzProbeLayout(wire_radius_m=baseline["wire_radius_m"],
        curve_radius_m=baseline["min_curvature_radius_m"],ring=RingGeometry(
            radius_m=baseline["loop_centerline_radius_m"],
            tube_radius_m=baseline["loop_tube_radius_m"],density_kg_m3=1500.))
    layout.validate()
    phases=[("settle",2.),("centered_passage",7.),("hold",2.),("press_wall",2.),("return_center",2.),("final_hold",2.)]
    config=dict(layout=asdict(layout),dt=dt,substeps=4,phases=phases,seed=0,
        actuator="finite free-body PD forces/torques with gravity compensation; no pose writes",
        gains=dict(position_N_m=20.,velocity_Ns_m=.8,orientation_Nm_rad=.03,angular_Nms_rad=.003),
        max_force_N=3.,max_torque_Nm=.015,wall_offset_m=.03,
        max_penetration_m=.0005,centered_contact_limit_N=.01,contact_detection_N=.02)
    config["rendering"] = dict(renderer=None if args.no_render else args.renderer, background=None if args.no_render else "compact_lab")
    (output/"config.json").write_text(json.dumps(config,indent=2)+"\n")
    (output/"baseline_manifest.json").write_text(json.dumps(baseline_manifest("buzz_wire_3d"),indent=2,ensure_ascii=False)+"\n")
    import genesis as gs
    gs.init(backend=gs.cuda,logging_level="warning",seed=0)
    started=time.monotonic()
    scene,wire,ring,camera,metadata=build_buzz_probe(layout,output,dt=dt,render=not args.no_render,renderer=args.renderer)
    build_seconds=time.monotonic()-started
    assert ring.n_dofs==6
    writer=None
    if camera:
        import imageio.v2 as imageio
        writer=imageio.get_writer(output/"probe.mp4",fps=20,codec="libx264",macro_block_size=1)
        imageio.imwrite(output/"initial.png",camera.render()[0])
    records=[];statistics={};steps=0;max_penetration=0.;error=None
    start=time.monotonic()
    try:
        for phase,duration in phases:
            stats=dict(max_ring_wire_force_N=0.,max_tracking_error_m=0.,contact_steps=0)
            for j in range(round(duration/dt)):
                u=(j+1)*dt/duration
                progress=0. if phase=="settle" else (u if phase=="centered_passage" else 1.)
                target,qtarget=layout.pose(progress)
                offset=.03*min(1.,u*2) if phase=="press_wall" else (.03*(1-min(1.,u*2)) if phase=="return_center" else 0.)
                target[1]+=offset
                p=array(ring.get_pos()).reshape(3);q=array(ring.get_quat()).reshape(4)
                velocity=array(ring.get_vel()).reshape(3);omega=array(ring.get_ang()).reshape(3)
                orientation_error=(Rotation.from_quat(qtarget[[1,2,3,0]])*Rotation.from_quat(q[[1,2,3,0]]).inv()).as_rotvec()
                force=20*(target-p)-.8*velocity+np.array([0,0,metadata['mass_kg']*9.81])
                torque=.03*orientation_error-.003*omega
                ring.control_dofs_force(np.r_[np.clip(force,-3,3),np.clip(torque,-.015,.015)])
                scene.step();steps+=1
                p=array(ring.get_pos()).reshape(3)
                if not np.isfinite(p).all():raise RuntimeError('Non-finite ring position')
                contacts=ring.get_contacts(with_entity=wire)
                forces=array(contacts['force_a']).reshape(-1,3)
                f=float(np.linalg.norm(forces,axis=1).sum()) if forces.size else 0.
                native=scene.sim.rigid_solver.collider.get_contacts()
                penetration=array(native['penetration'])
                max_penetration=max(max_penetration,float(penetration.max()) if penetration.size else 0.)
                tracking=float(np.linalg.norm(p-target))
                stats['max_ring_wire_force_N']=max(stats['max_ring_wire_force_N'],f)
                stats['max_tracking_error_m']=max(stats['max_tracking_error_m'],tracking)
                stats['contact_steps']+=int(f>.02)
                if j==round(duration/dt)-1:
                    stats['final_tracking_error_m']=tracking
                    stats['actual_offset_y_m']=float(p[1])
                if steps%25==0:
                    records.append(dict(time_s=steps*dt,phase=phase,position_m=p.tolist(),
                        target_m=target.tolist(),ring_wire_force_N=f,tracking_error_m=tracking))
                    if writer:writer.append_data(camera.render()[0])
            statistics[phase]=stats
            if camera:imageio.imwrite(output/f'{phase}.png',camera.render()[0])
            print(phase,stats,flush=True)
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
    finally:
        if writer:writer.close()
    passage=statistics.get('centered_passage',{})
    press=statistics.get('press_wall',{})
    final=statistics.get('final_hold',{})
    checks=dict(completed=len(statistics)==len(phases) and error is None,
        centered_passage_clear=passage.get('max_ring_wire_force_N',float('inf'))<.01,
        centered_tracking=passage.get('max_tracking_error_m',float('inf'))<.012,
        wall_contact_detected=press.get('contact_steps',0)>20,
        wall_blocks_target=press.get('final_tracking_error_m',0)>.005,
        returned_to_center=final.get('final_tracking_error_m',float('inf'))<.004,
        penetration_ok=max_penetration<.0005)
    report=dict(task_id='buzz_wire_3d',scope='planar_bend_fixture_probe',full_task_deployed=False,
        passed=all(checks.values()),checks=checks,error=error,phase_stats=statistics,
        max_penetration_m=max_penetration,physics_steps=steps,simulated_seconds=steps*dt,
        build_seconds=build_seconds,rollout_wall_seconds=time.monotonic()-start,
        geometry=metadata,config=config,genesis_version=version('genesis-world'),pose_writes_after_reset=False)
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (output/'frames.json').write_text(json.dumps(records,indent=2,allow_nan=False)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Buzz wire probe</title>'
        '<h1>电流棒局部接触试验</h1><p>直线与平面单弯；动态环杆由有限力驱动。先居中通过，再故意靠壁，最后回中。</p>'
        '<p><a href="report.json">实际检查报告</a> · <a href="config.json">配置</a></p>'
        + ('<video controls src="probe.mp4" style="max-width:100%"></video>' if camera else '<p>本次未渲染。</p>'))
    print(json.dumps(report,indent=2),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
