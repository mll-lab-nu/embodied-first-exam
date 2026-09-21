"""Audit an unforced volumetric-FEM episode; old 1D qualification does not carry over."""
import argparse
from collections import deque
from dataclasses import asdict
import json
from pathlib import Path
import time

import mujoco
import numpy as np

from .fem import FEMSettings, build_model, signed_volumes
from .geometry import SlottedPostLayout
from .physics import contact_summary, node_positions


def settle(output, settings=FEMSettings(), seconds=10., layout=SlottedPostLayout()):
    if not np.isfinite(seconds) or seconds < .05:
        raise ValueError('At least 0.05 seconds required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model, data, spec = build_model(output/'model', settings, layout=layout)
    mesh = np.load(output/'model/fem_mesh.npz')
    elements, reference = mesh['elements'], mesh['reference_volumes']
    ids = model.flex_vertbodyid.copy()
    velocity_ids = model.jnt_dofadr[model.body_jntadr[ids]]
    center_ids = mesh['center_indices']
    reference_lengths = np.asarray(spec['cord_segment_lengths'])
    rigid_names = ['target_ring', 'disc_left', 'disc_right', 'bead_left', 'bead_right']
    rigid_ids = [model.body(n).id for n in rigid_names]
    tail = deque(); qpos=[]; qvel=[]; timestamps=[]; nodes=[]; samples=[]
    depths={}; max_endpoint=0.; max_local_strain=0.; max_total_strain=0.
    min_volume=1.; max_volume=1.; table_penetration=0.; failure=None
    solver_iteration_max=0;solver_budget_exhaustions=0
    max_principal_strain=0.
    p0=mesh['rest'][elements]
    rest_inverse=np.linalg.inv(np.stack([p0[:, i]-p0[:, 0] for i in (1, 2, 3)], axis=2))
    stride=max(1, round(.05/settings.dt)); steps=round(seconds/settings.dt)
    clock=time.monotonic(); last_progress=clock-30
    for step in range(steps+1):
        # Split step: observe the same forward kinematics/contact state
        # used by the solve, avoiding a redundant full constraint solve.
        mujoco.mj_step1(model, data)
        vertices=data.flexvert_xpos.copy()
        actual=vertices[center_ids]
        velocity=data.qvel[velocity_ids[:, None]+np.arange(3)]
        finite=np.isfinite(vertices).all() and np.isfinite(data.qvel).all()
        J=signed_volumes(vertices, elements)/reference if finite else np.full(len(elements), -np.inf)
        min_volume=min(min_volume, float(J.min())); max_volume=max(max_volume, float(J.max()))
        for key, depth in contact_summary(model, data).items():
            depths[key]=max(depths.get(key, 0.), depth)
        for side, node in (('left', 0), ('right', -1)):
            max_endpoint=max(max_endpoint, float(np.linalg.norm(
                data.site_xpos[model.site(f'disc_{side}_anchor').id]-actual[node])))
        lengths=np.linalg.norm(np.diff(actual, axis=0), axis=1)
        max_local_strain=max(max_local_strain, float(np.max(abs(lengths/reference_lengths-1))))
        max_total_strain=max(max_total_strain, abs(float(lengths.sum()/reference_lengths.sum()-1)))
        table_penetration=max(table_penetration, -float(vertices[:, 2].min()))
        rv=[]
        for body in rigid_ids:
            v=np.zeros(6)
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
            rv.append([np.linalg.norm(v[3:]), np.linalg.norm(v[:3])])
        speed=np.linalg.norm(velocity, axis=1)
        metrics=[float(data.time), float(speed.max()), float(np.sqrt(np.mean(speed**2))),
                 float(np.max(np.asarray(rv)[:, 0])), float(np.max(np.asarray(rv)[:, 1]))]
        tail.append(metrics)
        while len(tail)>1 and tail[1][0] < data.time-2:
            tail.popleft()
        warnings={mujoco.mjtWarning(i).name:int(w.number) for i,w in enumerate(data.warning) if w.number}
        if not finite or min_volume <= 0 or warnings:
            failure=dict(time_s=float(data.time), finite=bool(finite), min_J=min_volume, warnings=warnings)
        if step%stride==0 and (output/'STOP').exists():
            failure=dict(time_s=float(data.time),reason='explicit stop request; partial episode')
        if step%stride==0 or step==steps or failure:
            if finite:
                p=vertices[elements]
                F=np.stack([p[:, i]-p[:, 0] for i in (1, 2, 3)],axis=2)@rest_inverse
                max_principal_strain=max(max_principal_strain,float(np.max(abs(np.linalg.svd(F,compute_uv=False)-1))))
            qpos.append(data.qpos.copy());qvel.append(data.qvel.copy())
            timestamps.append(float(data.time));nodes.append(actual.copy())
            samples.append(metrics+[float(J.min()),float(J.max()),max_endpoint])
        if time.monotonic()-last_progress >= 20 or step==steps or failure:
            status=dict(simulated_s=float(data.time), requested_s=seconds, wall_s=time.monotonic()-clock,
                        min_J=min_volume, max_contact_m=max(depths.values(),default=0.),
                        max_local_axial_strain=max_local_strain, speed_m_s=metrics[1])
            (output/'progress.json').write_text(json.dumps(status,indent=2)+'\n')
            print(json.dumps(status),flush=True);last_progress=time.monotonic()
        if failure or step==steps:
            break
        mujoco.mj_step2(model,data)
        solver_iteration_max=max(solver_iteration_max,int(data.solver_niter.max()))
        solver_budget_exhaustions+=int(data.solver_niter.max()>=model.opt.iterations)
    tail=np.asarray(tail)
    tail_max=tail[:,1:].max(axis=0)
    tail_nodes=np.asarray(nodes)[np.asarray(timestamps)>=data.time-2-1e-8]
    drift=float(np.linalg.norm(tail_nodes-tail_nodes[0],axis=2).max())
    checks=dict(completed=bool(data.time>=seconds-settings.dt/2),
        finite_no_inversion=bool(finite and min_volume>0 and not warnings),
        solver_converged=solver_budget_exhaustions==0,
        positive_volume_margin=min_volume>.2, contact_depth=max(depths.values(),default=0.)<.0005,
        terminal_attachment=max_endpoint<.0005, table_surface_clearance=table_penetration<.0005,
        total_axial_strain=max_total_strain<.05,local_axial_strain=max_local_strain<.20,
        tail_window_complete=bool(data.time>=2 and tail[-1,0]-tail[0,0]>=2-settings.dt*1.1),
        settled_speed=bool(tail_max[0]<.005 and tail_max[1]<.001 and tail_max[2]<.002 and tail_max[3]<.03),
        settled_centerline_drift=drift<.002)
    report=dict(scope='volumetric_fem_gravity_probe',passed=all(checks.values()),checks=checks,
        engine='MuJoCo',engine_version=mujoco.__version__,integrator=settings.integrator,solver='Newton',
        solver_iteration_max=solver_iteration_max,solver_budget_exhaustions=solver_budget_exhaustions,
        settings=asdict(settings),layout=asdict(layout),fem=spec['fem'],material_calibrated=False,
        constitutive_checks=spec['constitutive_checks'],native_elasticity_input=spec['native_elasticity_input'],
        pose_writes_after_initialization=False,external_force_driven=False,full_robot_demo=False,
        full_fem_solution_verified=False,fps=20,simulated_seconds=float(data.time),
        audit_frequency='every integration step except principal strain at recorded frames',
        min_volume_ratio=min_volume,max_volume_ratio=max_volume,max_contact_depth_m=depths,
        max_endpoint_error_m=max_endpoint,max_local_axial_strain=max_local_strain,
        max_total_axial_strain=max_total_strain,max_recorded_principal_strain=max_principal_strain,
        max_table_penetration_m=table_penetration,
        final_two_seconds_maxima=dict(zip(('fem_max_speed_m_s','fem_rms_speed_m_s',
            'rigid_linear_speed_m_s','rigid_angular_speed_rad_s'),tail_max.tolist())),
        recorded_tail_centerline_drift_m=drift,failure=failure,warnings=warnings,
        independent_surface_ccd_verified=False,
        limitations=['Authored isotropic continuum; not a calibrated braided-rope model',
            'Contact depth audit uses engine contacts; no independent swept-surface certification',
            'Single center vertex terminal constraints approximate freely pivoting knots'],
        wall_seconds=time.monotonic()-clock)
    np.savez_compressed(output/'states.npz',qpos=qpos,qvel=qvel,time_s=timestamps,cord_nodes=nodes)
    np.savez_compressed(output/'final_state.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
    np.savez_compressed(output/'fem_metrics.npz',samples=samples)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=10.)
    p.add_argument('--dt',type=float,default=FEMSettings.dt)
    p.add_argument('--integrator',choices=('Euler','discrete'),default=FEMSettings.integrator)
    p.add_argument('--segment',type=float,default=FEMSettings.segment_m)
    p.add_argument('--radial-segments',type=int,default=FEMSettings.radial_segments)
    p.add_argument('--young',type=float,default=FEMSettings.young_pa)
    p.add_argument('--bead-mouth-fillet',type=float,default=0.)
    p.add_argument('--poisson',type=float,default=FEMSettings.poisson)
    p.add_argument('--rayleigh',type=float,default=FEMSettings.rayleigh_s)
    p.add_argument('--mass-damping',type=float,default=FEMSettings.mass_damping_rate_s_inv)
    p.add_argument('--slot-width',type=float,default=.028)
    p.add_argument('--solver-tolerance',type=float,default=FEMSettings.solver_tolerance)
    p.add_argument('--solver-iterations',type=int,default=FEMSettings.solver_iterations)
    p.add_argument('--contact-time',type=float,default=FEMSettings.contact_time_s)
    a=p.parse_args()
    report=settle(a.output,FEMSettings(dt=a.dt,integrator=a.integrator,segment_m=a.segment,radial_segments=a.radial_segments,
        young_pa=a.young,poisson=a.poisson,rayleigh_s=a.rayleigh,bead_mouth_fillet_m=a.bead_mouth_fillet,
        mass_damping_rate_s_inv=a.mass_damping,solver_tolerance=a.solver_tolerance,
        solver_iterations=a.solver_iterations,contact_time_s=a.contact_time),a.seconds,
        SlottedPostLayout(slot_width_m=a.slot_width))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
