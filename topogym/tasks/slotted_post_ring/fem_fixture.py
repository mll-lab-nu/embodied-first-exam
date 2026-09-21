"""Continuous force-driven FEM solution recording with volumetric acceptance gates.

External forces act on rigid puzzle pieces only. The cord evolves through FEM,
contacts and the two terminal attachments. This is not a robot demonstration.
"""
import argparse
from collections import deque
from dataclasses import asdict
import json
from itertools import chain
from pathlib import Path
import shutil
import time

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .fem import FEMSettings, build_model, signed_volumes
from .fixture import cord_disk_crossings, interactive_stages, pose
from .geometry import SlottedPostLayout
from .physics import capture_sources, contact_summary


def minimum_jerk(u, seconds):
    """Keep endpoint roundoff inside Slerp's closed interpolation interval."""
    u = float(np.clip(u, 0., 1.))
    return float(np.clip(u**3*(10-15*u+6*u*u), 0., 1.)), 30*u*u*(1-u)**2/seconds


class VolumeAudit:
    def __init__(self, model, mesh, spec):
        self.model = model
        self.elements = mesh['elements']
        self.reference = mesh['reference_volumes']
        self.center = mesh['center_indices']
        self.lengths = np.asarray(spec['cord_segment_lengths'])
        ids = model.flex_vertbodyid
        self.velocity_ids = model.jnt_dofadr[model.body_jntadr[ids]][:, None] + np.arange(3)
        self.rigids = [model.body(n).id for n in
                       ('target_ring', 'bead_left', 'bead_right', 'disc_left', 'disc_right')]
        self.anchors = [model.site(f'disc_{side}_anchor').id for side in ('left', 'right')]
        self.depths = {}; self.min_J = 1.; self.max_J = 1.
        self.endpoint = 0.; self.local_strain = 0.; self.total_strain = 0.
        self.table_penetration = 0.; self.iterations = 0; self.exhaustions = 0
        self.tail = deque(); self.finite = True; self.warnings = {}

    def observe(self, data, released):
        vertices = data.flexvert_xpos
        self.nodes = vertices[self.center].copy()
        self.finite = bool(np.isfinite(vertices).all() and np.isfinite(data.qvel).all())
        J = signed_volumes(vertices, self.elements)/self.reference if self.finite else [-np.inf]
        self.min_J = min(self.min_J, float(np.min(J)))
        self.max_J = max(self.max_J, float(np.max(J)))
        for kind, depth in contact_summary(self.model, data).items():
            self.depths[kind] = max(self.depths.get(kind, 0.), depth)
        for site, node in zip(self.anchors, (0, -1)):
            self.endpoint = max(self.endpoint, float(np.linalg.norm(data.site_xpos[site]-self.nodes[node])))
        lengths = np.linalg.norm(np.diff(self.nodes, axis=0), axis=1)
        self.local_strain = max(self.local_strain, float(np.max(abs(lengths/self.lengths-1))))
        self.total_strain = max(self.total_strain, abs(float(lengths.sum()/self.lengths.sum()-1)))
        self.table_penetration = max(self.table_penetration, -float(vertices[:, 2].min()))
        speed = np.linalg.norm(data.qvel[self.velocity_ids], axis=1)
        rigid_speed = []
        for body in self.rigids:
            v = np.zeros(6)
            mujoco.mj_objectVelocity(self.model, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
            rigid_speed.append([np.linalg.norm(v[3:]), np.linalg.norm(v[:3])])
        self.metrics = [float(data.time), float(speed.max()), float(np.sqrt(np.mean(speed**2))),
                        float(np.max(np.asarray(rigid_speed)[:, 0])),
                        float(np.max(np.asarray(rigid_speed)[:, 1])), bool(released)]
        self.tail.append(self.metrics)
        while len(self.tail) > 1 and self.tail[1][0] < data.time-2:
            self.tail.popleft()
        self.warnings = {mujoco.mjtWarning(i).name: int(w.number)
                         for i, w in enumerate(data.warning) if w.number}

    def solved(self, data):
        count = int(data.solver_niter.max())
        self.iterations = max(self.iterations, count)
        self.exhaustions += int(count >= self.model.opt.iterations)

    def tail_checks(self):
        tail = np.asarray(self.tail)
        maximum = tail[:, 1:5].max(axis=0)
        return dict(last_two_seconds_released=bool(tail[-1, 0]-tail[0, 0] >= 2-self.model.opt.timestep*1.1
                    and np.all(tail[:, 5])),
                    final_fem_speed=bool(maximum[0] < .005 and maximum[1] < .001),
                    final_rigid_speed=bool(maximum[2] < .002 and maximum[3] < .03)), maximum

    def checks(self):
        return dict(finite_no_inversion=self.finite and self.min_J > 0 and not self.warnings,
                    positive_volume_margin=self.min_J > .2,
                    contact_depth=max(self.depths.values(), default=0.) < .0005,
                    terminal_attachment=self.endpoint < .0005,
                    local_axial_strain=self.local_strain < .20,
                    total_axial_strain=self.total_strain < .05,
                    table_surface_clearance=self.table_penetration < .0005,
                    solver_converged=self.exhaustions == 0)


def execute(output, schedule, settings, layout, initial_seconds=4., max_settle_extra=30.,
            force_limit=4., torque_limit=.3, model_source=None, initial_checkpoint=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    continuation = None
    if (model_source is None) != (initial_checkpoint is None):
        raise ValueError('Checkpoint probes need both model source and checkpoint')
    if model_source is None:
        model, data, spec = build_model(output/'model', settings, layout)
    else:
        # Development-only continuation; it cannot qualify or publish a full
        # process. The clean complete recording always starts from assembly.
        source = Path(model_source)
        shutil.copytree(source/'model', output/'model')
        capture_sources(output)
        spec = json.loads((output/'model/model_spec.json').read_text())
        settings = FEMSettings(**spec['settings'])
        layout = SlottedPostLayout(**spec['layout'])
        model = mujoco.MjModel.from_binary_path(str(output/'model/scene.mjb'))
        data = mujoco.MjData(model)
        with np.load(initial_checkpoint) as state:
            data.qpos[:] = state['qpos']; data.qvel[:] = state['qvel']
            continuation = dict(source=str(source),checkpoint=str(initial_checkpoint),
                                checkpoint_time_s=float(state['time_s']),
                                scope='development-only physical-state continuation')
        mujoco.mj_forward(model,data)
    mesh = np.load(output/'model/fem_mesh.npz')
    audit = VolumeAudit(model, mesh, spec)
    if initial_seconds < 0:
        raise ValueError('Initial duration must be nonnegative')
    prefix = [['initial_gravity', initial_seconds, {}]] if initial_seconds else []
    streaming = not isinstance(schedule, (list, tuple))
    requested = [] if streaming else prefix + list(schedule)
    planned_count = None if streaming else len(requested)
    stages = chain(prefix, schedule) if streaming else iter(requested)
    if not streaming and not requested:
        raise ValueError('At least one stage is required')
    (output/'requested_schedule.json').write_text(json.dumps(requested, indent=2)+'\n')
    qpos=[]; qvel=[]; times=[]; phases=[]; nodes=[]; actions=[]; metrics=[]
    errors={}; angle_errors={}; executed=[]; stage_results=[]
    max_force=0.; max_torque=0.; steps=0; failure=None
    clock=time.monotonic(); progress_clock=clock-60
    stride=max(1, round(.05/settings.dt))
    (output/'checkpoints').mkdir()

    def record(phase):
        if times and abs(times[-1]-data.time) < settings.dt/2:
            return
        qpos.append(data.qpos.copy()); qvel.append(data.qvel.copy()); times.append(float(data.time))
        phases.append(phase); nodes.append(audit.nodes.copy()); actions.append(data.xfrc_applied.copy())
        metrics.append(audit.metrics.copy())

    for name, seconds, commands in stages:
        if not np.isfinite(seconds) or seconds <= 0:
            raise ValueError('Each stage needs a positive finite duration')
        if streaming:
            requested.append([name,seconds,commands])
            (output/'requested_schedule.json').write_text(json.dumps(requested,indent=2)+'\n')
        ids={n:model.body(n).id for n in commands}
        starts={n:pose(data, body) for n, body in ids.items()}
        ends={n:(np.asarray(v[0]), Rotation.from_quat(v[1]) if v[1] is not None else starts[n][1])
              for n, v in commands.items()}
        lerps={n:Slerp([0,1], Rotation.from_matrix([starts[n][1].as_matrix(), ends[n][1].as_matrix()]))
               for n in commands}
        errors[name]={n:0. for n in commands}; angle_errors[name]={n:0. for n in commands}
        phase_start=float(data.time)
        extension=max_settle_extra if name == 'release_and_settle' else 0.
        for tick in range(round((seconds+extension)/settings.dt)):
            mujoco.mj_step1(model, data)
            smooth,ds=minimum_jerk((tick+1)*settings.dt/seconds,seconds)
            data.xfrc_applied[:]=0
            for n, body in ids.items():
                actual, rotation=pose(data, body)
                target=(1-smooth)*starts[n][0]+smooth*ends[n][0]
                v=np.zeros(6)
                mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
                mass=model.body_mass[body]; kp=400. if n.startswith('bead') else 1200.
                force=kp*(target-actual)+2*np.sqrt(kp*mass)*(ds*(ends[n][0]-starts[n][0])-v[3:])
                force += [0,0,mass*9.81]
                force *= min(1., force_limit/max(np.linalg.norm(force), 1e-12))
                torque=np.zeros(3)
                if commands[n][1] is not None:
                    angle=(lerps[n]([smooth])[0]*rotation.inv()).as_rotvec()
                    torque=3.*angle-.04*v[:3]
                    torque *= min(1., torque_limit/max(np.linalg.norm(torque), 1e-12))
                    angle_errors[name][n]=max(angle_errors[name][n], float(np.linalg.norm(angle)))
                data.xfrc_applied[body]=np.r_[force,torque]
                errors[name][n]=max(errors[name][n], float(np.linalg.norm(target-actual)))
                max_force=max(max_force,float(np.linalg.norm(force)))
                max_torque=max(max_torque,float(np.linalg.norm(torque)))
            audit.observe(data, not commands)
            if not audit.finite or audit.min_J <= .2 or audit.warnings:
                failure=dict(phase=name,time_s=float(data.time),reason='finite/volume/warning gate',
                             min_J=audit.min_J,warnings=audit.warnings)
            if steps % stride == 0:
                record(name)
                if (output/'STOP').exists():
                    failure=dict(phase=name,time_s=float(data.time),reason='explicit stop; partial episode')
            if time.monotonic()-progress_clock >= 20:
                status=dict(phase=name,simulated_s=float(data.time),wall_s=time.monotonic()-clock,
                            min_J=audit.min_J,max_contact_m=max(audit.depths.values(),default=0.),
                            local_strain=audit.local_strain,speed_m_s=audit.metrics[1],tracking=errors[name])
                (output/'progress.json').write_text(json.dumps(status,indent=2)+'\n')
                print(json.dumps(status),flush=True);progress_clock=time.monotonic()
            if failure:
                record(name);break
            mujoco.mj_step2(model,data);audit.solved(data);steps+=1
            if name == 'release_and_settle' and tick+1 >= round(seconds/settings.dt) and steps%stride == 0:
                if all(audit.tail_checks()[0].values()):
                    break
        mujoco.mj_forward(model,data)
        audit.observe(data,not commands)
        # A checkpoint is evidence only; the next stage retains this same MjData.
        np.savez_compressed(output/'checkpoints'/f'{name}.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
        executed.append([name,float(data.time)-phase_start,commands])
        result=dict(phase=name,time_s=float(data.time),tracking=errors[name],
                    cord_disk_crossings=cord_disk_crossings(model,data),checks=audit.checks())
        stage_results.append(result)
        print(json.dumps(result),flush=True)
        # Preserve a playable partial trace if an unexpected later exception
        # occurs during a long run. It is never marked as a complete process.
        np.savez_compressed(output/'states.npz',qpos=qpos,qvel=qvel,time_s=times,phase=phases,
                            cord_nodes=nodes,xfrc_applied=actions)
        (output/'report.json').write_text(json.dumps(dict(
            scope='volumetric_fem_force_driven_partial',passed=False,full_process_demo=False,
            full_robot_demo=False,fps=20,simulated_seconds=float(data.time),
            completed_stages=stage_results,recording_complete=False),indent=2)+'\n')
        if failure:break
        if streaming:
            print(json.dumps(dict(awaiting_next_stage=True,time_s=float(data.time),
                                  completed_phase=name)),flush=True)
    # Frames occur on the same fixed 20 Hz clock, including the last state.
    record(name)
    ring=data.xpos[model.body('target_ring').id].copy()
    tail_checks,tail_max=audit.tail_checks()
    checks=audit.checks() | tail_checks | dict(
        completed_schedule=(planned_count is None or len(executed)==planned_count) and failure is None,
        ring_away_from_post=float(np.linalg.norm(ring[:2])) > .19,
        ring_on_table=bool(abs(ring[2]-.01)<.002),
        cord_clear_of_ring_disk=cord_disk_crossings(model,data)==0,
        no_active_external_hold=not np.any(data.xfrc_applied),
        tracking=max((v for stage in errors.values() for v in stage.values()),default=0.) < .005,
        rotation_tracking=max((v for stage in angle_errors.values() for v in stage.values()),default=0.) < .10)
    passed=bool(all(checks.values()))
    complete = passed and continuation is None
    report=dict(scope='volumetric_fem_checkpoint_probe' if continuation else
                      'volumetric_fem_force_driven_full_process',passed=passed,checks=checks,
        full_process_demo=complete,full_fem_solution_verified=complete,full_robot_demo=False,
        continuation=continuation,
        robot_execution=False,external_force_driven=True,pose_writes_after_initialization=False,
        continuous_episode=continuation is None,material_calibrated=False,independent_surface_ccd_verified=False,
        engine='MuJoCo',engine_version=mujoco.__version__,settings=asdict(settings),layout=asdict(layout),
        fem=spec['fem'],fps=20,simulated_seconds=float(data.time),wall_seconds=time.monotonic()-clock,
        stage_errors_m=errors,stage_rotation_errors_rad=angle_errors,stages=stage_results,
        final_ring_position=ring.tolist(),final_cord_disk_crossings=cord_disk_crossings(model,data),
        max_contact_depth_m=audit.depths,min_volume_ratio=audit.min_J,max_volume_ratio=audit.max_J,
        max_endpoint_error_m=audit.endpoint,max_local_axial_strain=audit.local_strain,
        max_total_axial_strain=audit.total_strain,max_table_penetration_m=audit.table_penetration,
        solver_iteration_max=audit.iterations,solver_budget_exhaustions=audit.exhaustions,
        final_two_seconds_maxima=dict(zip(('fem_max_speed_m_s','fem_rms_speed_m_s',
            'rigid_linear_speed_m_s','rigid_angular_speed_rad_s'),tail_max.tolist())),
        max_external_force_n=max_force,max_external_torque_nm=max_torque,
        controller_limits=dict(force_n=force_limit,torque_nm=torque_limit),
        max_simultaneous_driven_bodies=max(len(stage[2]) for stage in executed),
        interactive_stages=streaming,simulation_time_pauses_between_commands=streaming,
        audit_frequency='every integration step',failure=failure,warnings=audit.warnings)
    np.savez_compressed(output/'states.npz',qpos=qpos,qvel=qvel,time_s=times,phase=phases,
                        cord_nodes=nodes,xfrc_applied=actions)
    np.savez_compressed(output/'fem_metrics.npz',samples=metrics)
    np.savez_compressed(output/'final_state.npz',qpos=data.qpos,qvel=data.qvel,time_s=data.time)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'schedule.json').write_text(json.dumps(executed,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    stage_input=p.add_mutually_exclusive_group(required=True)
    stage_input.add_argument('--schedule',type=Path)
    stage_input.add_argument('--interactive',action='store_true',
                             help='Read JSON stages from stdin, preserving one continuous MjData episode')
    p.add_argument('--model-source',type=Path,help='Development checkpoint probe only')
    p.add_argument('--initial-checkpoint',type=Path)
    p.add_argument('--dt',type=float,default=.0005)
    p.add_argument('--rayleigh',type=float,default=.00005)
    p.add_argument('--young',type=float,default=FEMSettings.young_pa)
    p.add_argument('--mass-damping',type=float,default=2.)
    p.add_argument('--solver-tolerance',type=float,default=FEMSettings.solver_tolerance)
    p.add_argument('--solver-iterations',type=int,default=FEMSettings.solver_iterations)
    p.add_argument('--contact-time',type=float,default=FEMSettings.contact_time_s)
    p.add_argument('--integrator',choices=('Euler','discrete'),default='discrete')
    p.add_argument('--slot-width',type=float,default=.036)
    p.add_argument('--initial-seconds',type=float,default=4.)
    p.add_argument('--max-settle-extra',type=float,default=30.)
    a=p.parse_args()
    report=execute(a.output,interactive_stages() if a.interactive else json.loads(a.schedule.read_text()),
        FEMSettings(dt=a.dt,rayleigh_s=a.rayleigh,young_pa=a.young,mass_damping_rate_s_inv=a.mass_damping,
                    integrator=a.integrator,solver_tolerance=a.solver_tolerance,
                    solver_iterations=a.solver_iterations,contact_time_s=a.contact_time),
        SlottedPostLayout(slot_width_m=a.slot_width),a.initial_seconds,a.max_settle_extra,
        model_source=a.model_source,initial_checkpoint=a.initial_checkpoint)
    if not report['passed']:raise SystemExit(1)
