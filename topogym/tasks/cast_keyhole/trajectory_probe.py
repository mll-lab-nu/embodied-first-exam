"""Dynamic tracking of a certified full route using a disclosed force bench.

Gold is held by a fixed fixture. Silver is a free body driven by bounded force
and torque, including gravity support. This verifies the complete puzzle motion
before adding robot grasps; it is not a robot demonstration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision, Motion
from .geometry import KeyholeBody, write_body
from .physics_probe import array
from .solution import load_solution, require_current_full_certificate


def schedule(motions, speed=.12, angular_speed=.8):
    durations = []
    for motion in motions:
        # Canonical plate radius < 120 mm at scale 3. The caller supplies the
        # actual mesh radius through the material-point bound below instead.
        rotation = Rotation.from_matrix(motion.pose(1.)[0]@motion.pose(0.)[0].T).magnitude()
        if isinstance(motion,Motion) and motion.axis is not None:
            rotation = abs(motion.angle_rad)
        # Conservative envelope includes the complete 3x plate; scale checked.
        corners = np.array([[x,y,z] for x in (-.039,.039) for y in (-.105,.102) for z in (-.0045,.0045)])
        duration = max(.4,1.875*motion.speed_bound(corners)/speed,1.875*rotation/angular_speed)
        durations.append(duration)
    return np.r_[0.,np.cumsum(durations)]


def target(motion, u, du, ddu, center):
    R,t = motion.pose(u)
    if isinstance(motion,Motion) and motion.axis is not None:
        rotvec = motion.axis*motion.angle_rad
        offset = t+R@center-motion.pivot
        position = motion.pivot+offset
        velocity = np.cross(rotvec*du,offset)
        acceleration = np.cross(rotvec*ddu,offset)+np.cross(rotvec*du,np.cross(rotvec*du,offset))
    else:
        rotvec = Rotation.from_matrix(motion.end_rotation@motion.start_rotation.T).as_rotvec()
        shift = motion.end_translation-motion.start_translation
        offset = R@center
        position = t+offset
        velocity = shift*du+np.cross(rotvec*du,offset)
        acceleration = shift*ddu+np.cross(rotvec*ddu,offset)+np.cross(rotvec*du,np.cross(rotvec*du,offset))
    return position,R,velocity,rotvec*du,acceleration,rotvec*ddu


def run(solution,certificate,output,dt=.001):
    if not np.isfinite(dt) or not 0 < dt <= .001:
        raise ValueError("dt must be positive and <= 1 ms")
    if json.loads(Path(certificate).read_text()).get("certificate_type") == "current_instance_path_v1":
        from .instance_solution import require_current_instance_certificate
        require_current_instance_certificate(solution,certificate)
    else:
        require_current_full_certificate(solution,certificate)
    data,meshes,cells,motions = load_solution(solution)
    if data["scale"] != 3.:
        raise ValueError("The validated controller/envelope uses scale 3")
    import genesis as gs
    output = Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    boundaries = schedule(motions)
    config = dict(dt=dt,precision="64",substeps=4,iterations=100,constraint_timeconst=.001,
        gravity=[0,0,-9.81],friction=.35,position_frequency_rad_s=90.,rotation_frequency_rad_s=90.,
        damping_ratio=1.,force_limit_N=20.,torque_limit_Nm=3.,max_material_speed_m_s=.12,
        max_angular_speed_rad_s=.8,initial_hold_s=.5,final_hold_s=1.,
        motion_durations_s=np.diff(boundaries).tolist(),robot_present=False,
        gold_fixed_fixture=True,material_gravity_compensation=False,
        controller_supplies_gravity_support=True,pose_writes_after_reset=False)
    (output/"config.json").write_text(json.dumps(config,indent=2)+"\n")
    records = []
    for name,mesh,parts,color in zip(("gold","silver"),meshes,cells,((.61,.43,.12,1),(.56,.61,.66,1))):
        body=KeyholeBody("keyhole_"+name,mesh,parts,color,[])
        records.append(write_body(output/"assets"/name,body,6600.))
    gs.init(backend=gs.cuda,precision="64",logging_level="warning",seed=0)
    scene = gs.Scene(show_viewer=False,sim_options=gs.options.SimOptions(dt=dt,substeps=4,gravity=(0,0,-9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True,enable_self_collision=True,
            iterations=100,max_collision_pairs=8192,constraint_timeconst=.001))
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.35))
    origin = np.array([0.,0.,.40])
    entities=[]
    for i,(name,rec) in enumerate(zip(("gold","silver"),records)):
        R,t = (np.eye(3),np.zeros(3)) if i==0 else motions[0].pose(0.)
        entities.append(scene.add_entity(gs.morphs.URDF(
            file=str(output/"assets"/name/f"keyhole_{name}.urdf"),pos=origin+t+R@rec["origin_m"],
            quat=Rotation.from_matrix(R).as_quat()[[3,0,1,2]],fixed=i==0,align=False,
            convexify=True,decimate=False,merge_fixed_links=False),material=gs.materials.Rigid(friction=.35)))
    scene.build()
    gold,silver=entities
    if [b.n_dofs for b in entities]!=[0,6] or [len(b.geoms) for b in entities]!=[62,67]:
        raise RuntimeError("Unexpected fixture or collision partition")
    center=np.array(records[1]["origin_m"]);mass=records[1]["mass_kg"]
    inertia=np.array(records[1]["inertia_kg_m2"])
    collision=CompoundCollision(*cells)
    solver=scene.sim.rigid_solver;link=silver.base_link_idx
    duration=boundaries[-1]+1.5;steps=int(np.ceil(duration/dt))
    stats=dict(max_position_error_m=0.,max_rotation_error_rad=0.,max_contact_penetration_m=0.,
        min_sampled_sat_gap_m=float("inf"),max_force_N=0.,max_torque_Nm=0.,max_speed_m_s=0.,
        tail_linear_speed_m_s=0.,tail_angular_speed_rad_s=0.)
    trace=[];started=time.monotonic();aborted=None
    for step in range(steps):
        now=step*dt;tau=np.clip(now-.5,0,boundaries[-1])
        index=min(int(np.searchsorted(boundaries,tau,side="right")-1),len(motions)-1)
        length=boundaries[index+1]-boundaries[index]
        s=np.clip((tau-boundaries[index])/length,0,1)
        u=10*s**3-15*s**4+6*s**5
        du=30*s*s*(1-s)**2/length if .5 < now < .5+boundaries[-1] else 0.
        ddu=60*s*(1-3*s+2*s*s)/(length*length) if .5 < now < .5+boundaries[-1] else 0.
        p,R,v,w,a,alpha=target(motions[index],u,du,ddu,center);p+=origin
        actual_p=array(silver.get_pos());actual_R=Rotation.from_quat(array(silver.get_quat())[[1,2,3,0]])
        actual_v=array(silver.get_vel());actual_w=array(silver.get_ang())
        error=p-actual_p;rot_error=(Rotation.from_matrix(R)*actual_R.inv()).as_rotvec()
        frequency=config["position_frequency_rad_s"]
        force=mass*(a+[0,0,9.81]+frequency**2*error+2*frequency*(v-actual_v))
        world_inertia=actual_R.as_matrix()@inertia@actual_R.as_matrix().T
        frequency=config["rotation_frequency_rad_s"]
        torque=world_inertia@(alpha+frequency**2*rot_error+2*frequency*(w-actual_w))
        torque+=np.cross(actual_w,world_inertia@actual_w)
        force*=min(1.,20./max(np.linalg.norm(force),1e-12));torque*=min(1.,3./max(np.linalg.norm(torque),1e-12))
        solver.apply_links_external_force(np.asarray([force]),[link],ref="link_com")
        solver.apply_links_external_torque(np.asarray([torque]),[link],ref="link_com")
        scene.step()
        values=np.r_[array(silver.get_qpos()),array(silver.get_vel()),array(silver.get_ang())]
        if not np.isfinite(values).all():
            aborted="non-finite physical state";break
        for key,value in (("max_position_error_m",np.linalg.norm(error)),("max_rotation_error_rad",np.linalg.norm(rot_error)),
                          ("max_force_N",np.linalg.norm(force)),("max_torque_Nm",np.linalg.norm(torque)),
                          ("max_speed_m_s",np.linalg.norm(actual_v))):stats[key]=max(stats[key],float(value))
        contacts=solver.collider.get_contacts();depth=array(contacts["penetration"])
        if depth.size:stats["max_contact_penetration_m"]=max(stats["max_contact_penetration_m"],float(depth.max()))
        if now>duration-.5:
            stats["tail_linear_speed_m_s"]=max(stats["tail_linear_speed_m_s"],float(np.linalg.norm(actual_v)))
            stats["tail_angular_speed_rad_s"]=max(stats["tail_angular_speed_rad_s"],float(np.linalg.norm(actual_w)))
        if (step+1)%max(1,round(.005/dt))==0:
            q=array(silver.get_qpos());r=Rotation.from_quat(q[[4,5,6,3]]).as_matrix();t=q[:3]-origin-r@center
            gap=collision.gap(r,t);stats["min_sampled_sat_gap_m"]=min(stats["min_sampled_sat_gap_m"],gap)
            trace.append(dict(time_s=(step+1)*dt,stage=data["motions"][index]["stage"],motion=index,
                silver_translation_m=t.tolist(),silver_quaternion_xyzw=q[[4,5,6,3]].tolist(),sat_gap_m=gap))
            if gap<-.0005 or np.linalg.norm(error)>.003:
                aborted=f"tracking/contact limit exceeded in {motions[index].name}";break
        if (step+1)%max(1,round(2./dt))==0:
            print(f"Route bench {now+dt:.1f}/{duration:.1f}s, {data['motions'][index]['stage']}; wall {time.monotonic()-started:.1f}s",flush=True)
    q=array(silver.get_qpos());r=Rotation.from_quat(q[[4,5,6,3]]).as_matrix();t=q[:3]-origin-r@center
    final_gap=collision.gap(r,t)
    passed=bool(aborted is None and stats["max_contact_penetration_m"]<.0005 and
        stats["min_sampled_sat_gap_m"]>-.0005 and stats["max_position_error_m"]<.0005 and
        stats["max_rotation_error_rad"]<.005 and stats["tail_linear_speed_m_s"]<.001 and
        stats["tail_angular_speed_rad_s"]<.01 and final_gap>.020)
    report=dict(scope=__doc__,config=config,passed=passed,aborted=aborted,**stats,
        final_separation_lower_bound_m=final_gap,physics_steps=step+1,simulated_seconds=(step+1)*dt,
        solution_sha256=hashlib.sha256(Path(solution).read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        final_silver_translation_m=t.tolist(),final_silver_quaternion_xyzw=q[[4,5,6,3]].tolist(),
        continuous_target_certificate=True,actual_sat_sampling_s=.005,
        robot_execution_verified=False,formal_demo_qualified=False,pose_writes_after_reset=False)
    (output/"trajectory.json").write_text(json.dumps(trace,allow_nan=False)+"\n")
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution",type=Path,required=True)
    parser.add_argument("--certificate",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dt",type=float,default=.001)
    args=parser.parse_args()
    if not run(args.solution,args.certificate,args.output,args.dt)["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
