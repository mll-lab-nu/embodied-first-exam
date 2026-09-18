"""Longer free settling and bounded-force positive/negative contact controls.

Motion cases fix the silver plate and drive gold by external wrench. This is an
explicit bench qualification, not a robot grasp or an official disassembly.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .collision import CompoundCollision
from .geometry import generate_assets, KeyholeAssembly, ASSET_ROOT


def array(value):
    return value.detach().cpu().numpy() if hasattr(value,"detach") else np.asarray(value)


def evidence_fingerprint():
    folder = Path(__file__).parent
    paths = [ASSET_ROOT/"template.json",folder/"geometry.py",folder/"collision.py",folder/"physics_probe.py"]
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def specifications():
    assembly = KeyholeAssembly()
    gold,silver = assembly.bodies
    collision = CompoundCollision(silver.collision,gold.collision)
    cases = [dict(name="settle_baseline",kind="settle",yaw_deg=-12.,lift_m=.0005),
             dict(name="settle_yaw30",kind="settle",yaw_deg=30.,lift_m=.0005),
             dict(name="settle_drop2mm",kind="settle",yaw_deg=-12.,lift_m=.002)]
    for sign in (-1,1):
        cases.append(dict(name=f"allowed_x_{sign:+d}",kind="allowed",axis=0,sign=sign,travel_m=.0015))
        for axis in range(3):
            direction = np.eye(3)[axis]*sign
            lo,hi = 0.,.001
            while collision.gap(np.eye(3),direction*hi) >= 0 and hi < .08:
                lo,hi = hi,hi+.001
            if hi >= .08:
                raise RuntimeError("Expected blocked straight pull is not blocked")
            for _ in range(16):
                mid = (lo+hi)/2
                if collision.gap(np.eye(3),direction*mid) > 0:
                    lo = mid
                else:
                    hi = mid
            cases.append(dict(name=f"blocked_{'xyz'[axis]}_{sign:+d}",kind="blocked",axis=axis,sign=sign,
                              first_contact_m=(lo+hi)/2,travel_m=hi+.012))
    return cases


def build_probe(output,dt,selected):
    import genesis as gs

    assembly,report = generate_assets(output/"assets")
    scene = gs.Scene(show_viewer=False,sim_options=gs.options.SimOptions(dt=dt,substeps=4,gravity=(0,0,-9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True,enable_self_collision=True,
            iterations=100,max_collision_pairs=32768,constraint_timeconst=.001))
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.35))
    collision = CompoundCollision(assembly.bodies[1].collision,assembly.bodies[0].collision)
    cases,entities = [],[]
    for index,spec in enumerate(selected):
        settle = spec["kind"] == "settle"
        rotation = Rotation.identity()
        origin = np.array([index%4*.7,index//4*.7,.35])
        if settle:
            rotation = (Rotation.from_euler("z",spec["yaw_deg"],degrees=True)
                        *Rotation.from_euler("y",90,degrees=True)*Rotation.from_euler("z",45,degrees=True))
            bottom = min(rotation.apply(b.visual.vertices)[:,2].min() for b in assembly.bodies)
            origin[2] = -bottom+spec["lift_m"]
        bodies,indices,centers = [],[],[]
        for number,item in enumerate(report["bodies"]):
            name = item["name"]
            center = np.asarray(item["origin_m"])
            body = scene.add_entity(gs.morphs.URDF(file=str((output/"assets"/name/f"{name}.urdf").resolve()),
                pos=origin+rotation.apply(center),quat=rotation.as_quat()[[3,0,1,2]],
                fixed=number==1 and not settle,align=False,convexify=True,decimate=False,merge_fixed_links=False),
                material=gs.materials.Rigid(friction=.35,gravity_compensation=0. if settle else 1.),
                name=f"{spec['name']}_{name}")
            bodies.append(body)
            indices.append(len(entities))
            entities.append(body)
            centers.append(center)
        cases.append(dict(spec=spec,rotation=rotation,origin=origin,bodies=bodies,indices=indices,centers=centers,
            gold_inertia=np.asarray(report["bodies"][0]["inertia_kg_m2"]),
            collision=collision,stats=dict(max_contact_penetration_m=0.,max_pair_penetration_m=0.,
                min_sampled_sat_gap_m=float("inf"),max_contact_force_N=0.,contact_steps=0,
                max_displacement_m=0.,max_linear_speed_m_s=0.,max_angular_speed_rad_s=0.,
                max_position_error_m=0.,max_rotation_error_rad=0.,max_force_N=0.,max_torque_Nm=0.,
                max_direction_travel_m=0.,tail_linear_speed_m_s=0.,tail_angular_speed_rad_s=0.),trace=[]))
    scene.build()
    for c in cases:
        expected = [6,6] if c["spec"]["kind"]=="settle" else [6,0]
        if [b.n_dofs for b in c["bodies"]] != expected:
            raise RuntimeError("Unexpected constraints")
        if [len(b.geoms) for b in c["bodies"]] != [62,67] or not all(g.is_convex for b in c["bodies"] for g in b.geoms):
            raise RuntimeError("Convex collision partitions changed on load")
    return scene,cases,entities


def run_probe(output,dt=.001,only=None,precision="64"):
    import genesis as gs

    if not np.isfinite(dt) or not 0 < dt <= .001:
        raise ValueError("Require 0 < dt <= 1 ms")
    if precision not in ("32", "64"):
        raise ValueError("Expected 32 or 64 bit precision")
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    selected = [s for s in specifications() if only is None or s["name"] in only]
    if not selected or (only and set(only)-{s["name"] for s in selected}):
        raise ValueError("Unknown or empty case selection")
    config = dict(dt=dt,precision=precision,substeps=4,iterations=100,friction=.35,constraint_timeconst=.001,
        max_collision_pairs=32768,duration_s=5.,sample_interval_s=.005,seed=0,
        controller=dict(kp_position=3000.,kd_position=80.,rotation_frequency_rad_s=200.,rotation_damping_ratio=1.,
                        rotation_model="world inertia normalized PD plus gyroscopic compensation",
                        force_limit_N=20.,torque_limit_Nm=3.),
        phases=dict(initial_hold_s=.3,move_s=1.2,loaded_hold_s=.7,drive_release_s=2.2),
        cases=selected,pose_writes_after_reset=False,robot_present=False,
        fixed_silver_only_in_motion_bench=True,gravity_compensation_only_in_motion_bench=True)
    thresholds = dict(contact_penetration_m=.0005,sampled_sat_penetration_m=.0005,
        allowed_position_error_m=.0005,allowed_rotation_error_rad=.01,
        blocked_overtravel_m=.002,blocked_target_error_m=.005,blocked_rotation_error_rad=.05,
        final_linear_speed_m_s=.01,final_angular_speed_rad_s=.1,settle_max_displacement_m=.05,
        settle_tail_position_drift_m=.0002,settle_tail_rotation_drift_rad=.005)
    fingerprint = evidence_fingerprint()
    (output/"config.json").write_text(json.dumps(dict(config=config,thresholds=thresholds,fingerprint=fingerprint),indent=2)+"\n")
    gs.init(backend=gs.cuda,precision=precision,logging_level="warning",seed=0)
    started = time.monotonic()
    scene,cases,entities = build_probe(output,dt,selected)
    solver = scene.sim.rigid_solver
    links = [b.base_link_idx for b in entities]
    controlled = [c for c in cases if c["spec"]["kind"]!="settle"]
    driven_links = [c["bodies"][0].base_link_idx for c in controlled]
    initial = array(solver.get_links_pos(links,relative=True)).copy()
    steps = round(config["duration_s"]/dt)
    for step in range(steps):
        now = step*dt
        pos,quat = array(solver.get_links_pos(links,relative=True)),array(solver.get_links_quat(links,relative=True))
        vel,ang = array(solver.get_links_vel(links)),array(solver.get_links_ang(links))
        rotations = Rotation.from_quat(quat[:,[1,2,3,0]])
        commands,torques = [],[]
        for c in controlled:
            i = c["indices"][0]
            spec,stats = c["spec"],c["stats"]
            u = np.clip((now-.3)/1.2,0,1)
            blend = 6*u**5-15*u**4+10*u**3
            derivative = 30*u*u*(1-u)**2/1.2 if 0 < u < 1 else 0.
            direction = np.eye(3)[spec["axis"]]*spec["sign"]
            shift = direction*spec["travel_m"]
            target = c["origin"]+c["centers"][0]+blend*shift
            target_v = derivative*shift
            rot_error = rotations[i].inv().as_rotvec()
            gains = config["controller"]
            force = gains["kp_position"]*(target-pos[i])+gains["kd_position"]*(target_v-vel[i])
            R = rotations[i].as_matrix()
            inertia = R@c["gold_inertia"]@R.T
            frequency = gains["rotation_frequency_rad_s"]
            acceleration = frequency**2*rot_error-2*gains["rotation_damping_ratio"]*frequency*ang[i]
            torque = inertia@acceleration+np.cross(ang[i],inertia@ang[i])
            force *= min(1.,gains["force_limit_N"]/max(float(np.linalg.norm(force)),1e-12))
            torque *= min(1.,gains["torque_limit_Nm"]/max(float(np.linalg.norm(torque)),1e-12))
            if now >= 2.2:
                force,torque = np.zeros(3),np.zeros(3)
            commands.append(force)
            torques.append(torque)
            c["target"] = target
            stats["max_force_N"] = max(stats["max_force_N"],float(np.linalg.norm(force)))
            stats["max_torque_Nm"] = max(stats["max_torque_Nm"],float(np.linalg.norm(torque)))
        if controlled:
            solver.apply_links_external_force(np.asarray(commands),driven_links,ref="link_com")
            solver.apply_links_external_torque(np.asarray(torques),driven_links,ref="link_com")
        scene.step()
        pos,quat = array(solver.get_links_pos(links,relative=True)),array(solver.get_links_quat(links,relative=True))
        vel,ang = array(solver.get_links_vel(links)),array(solver.get_links_ang(links))
        if not np.isfinite(np.r_[pos.ravel(),quat.ravel(),vel.ravel(),ang.ravel()]).all():
            raise RuntimeError(f"Non-finite physical state at step {step}")
        rotations = Rotation.from_quat(quat[:,[1,2,3,0]])
        contact = {k:array(v) for k,v in solver.collider.get_contacts().items()}
        ga,gb = contact["geom_a"],contact["geom_b"]
        sample = (step+1)%max(1,round(.005/dt))==0
        for c in cases:
            spec,stats = c["spec"],c["stats"]
            ig,isilver = c["indices"]
            masks = [((ga>=b.geom_start)&(ga<b.geom_end))|((gb>=b.geom_start)&(gb<b.geom_end)) for b in c["bodies"]]
            all_contacts,pair = masks[0]|masks[1],masks[0]&masks[1]
            if all_contacts.any():
                stats["max_contact_penetration_m"] = max(stats["max_contact_penetration_m"],float(contact["penetration"][all_contacts].max()))
            if pair.any():
                stats["max_pair_penetration_m"] = max(stats["max_pair_penetration_m"],float(contact["penetration"][pair].max()))
                stats["max_contact_force_N"] = max(stats["max_contact_force_N"],float(np.linalg.norm(contact["force"][pair],axis=-1).max()))
                stats["contact_steps"] += 1
            speed = float(np.linalg.norm(vel[c["indices"]],axis=1).max())
            spin = float(np.linalg.norm(ang[c["indices"]],axis=1).max())
            stats["max_linear_speed_m_s"] = max(stats["max_linear_speed_m_s"],speed)
            stats["max_angular_speed_rad_s"] = max(stats["max_angular_speed_rad_s"],spin)
            stats["max_displacement_m"] = max(stats["max_displacement_m"],float(np.linalg.norm(pos[c["indices"]]-initial[c["indices"]],axis=1).max()))
            relative_R = rotations[isilver].inv()*rotations[ig]
            gold_origin = pos[ig]-rotations[ig].apply(c["centers"][0])
            silver_origin = pos[isilver]-rotations[isilver].apply(c["centers"][1])
            relative_t = rotations[isilver].inv().apply(gold_origin-silver_origin)
            if spec["kind"]!="settle":
                error = float(np.linalg.norm(pos[ig]-c["target"]))
                angle = float(relative_R.magnitude())
                stats["max_position_error_m"] = max(stats["max_position_error_m"],error)
                stats["max_rotation_error_rad"] = max(stats["max_rotation_error_rad"],angle)
                travel = float(relative_t[spec["axis"]]*spec["sign"])
                stats["max_direction_travel_m"] = max(stats["max_direction_travel_m"],travel)
                if now < 2.2:
                    c["loaded_error_m"] = error
                    c["loaded_travel_m"] = travel
            if now >= 4.5:
                stats["tail_linear_speed_m_s"] = max(stats["tail_linear_speed_m_s"],speed)
                stats["tail_angular_speed_rad_s"] = max(stats["tail_angular_speed_rad_s"],spin)
            if sample:
                gap = c["collision"].gap(relative_R.as_matrix(),relative_t)
                stats["min_sampled_sat_gap_m"] = min(stats["min_sampled_sat_gap_m"],gap)
                c["trace"].append(dict(time_s=(step+1)*dt,relative_translation_m=relative_t.tolist(),
                    relative_quaternion_xyzw=relative_R.as_quat().tolist(),sat_gap_m=gap,
                    body_positions_m=pos[c["indices"]].tolist(),body_quaternions_wxyz=quat[c["indices"]].tolist()))
            c["final_translation"],c["final_rotation"] = relative_t,relative_R
        if (step+1)%max(1,round(.5/dt))==0:
            print(f"Keyhole contact suite {step+1}/{steps}; {time.monotonic()-started:.1f}s wall",flush=True)
    reports = []
    for c in cases:
        spec,stats = c["spec"],c["stats"]
        contact_ok = stats["max_contact_penetration_m"]<.0005 and stats["min_sampled_sat_gap_m"]>-.0005
        rest_ok = stats["tail_linear_speed_m_s"]<.01 and stats["tail_angular_speed_rad_s"]<.1
        tail = [f for f in c["trace"] if f["time_s"]>=4.5]
        base_positions = np.asarray(tail[0]["body_positions_m"])
        base_rotations = Rotation.from_quat(np.asarray(tail[0]["body_quaternions_wxyz"])[:,[1,2,3,0]])
        tail_drift = max(float(np.linalg.norm(np.asarray(f["body_positions_m"])-base_positions,axis=1).max()) for f in tail)
        tail_angle = max(float((base_rotations.inv()*Rotation.from_quat(np.asarray(f["body_quaternions_wxyz"])[:,[1,2,3,0]])).magnitude().max()) for f in tail)
        if spec["kind"]=="settle":
            behavior = stats["max_displacement_m"]<.05 and tail_drift<.0002 and tail_angle<.005
        elif spec["kind"]=="allowed":
            behavior = stats["max_position_error_m"]<.0005 and stats["max_rotation_error_rad"]<.01
        else:
            behavior = (stats["contact_steps"]>0 and c["loaded_error_m"]>.005 and
                stats["max_direction_travel_m"]<spec["first_contact_m"]+.002 and stats["max_rotation_error_rad"]<.05)
        result = dict(**spec,**stats,passed=bool(contact_ok and rest_ok and behavior),
            contact_reliable=bool(contact_ok),rest_verified=bool(rest_ok),expected_behavior_verified=bool(behavior),
            loaded_error_m=c.get("loaded_error_m"),loaded_travel_m=c.get("loaded_travel_m"),
            tail_position_drift_m=tail_drift,tail_rotation_drift_rad=tail_angle,
            final_relative_translation_m=c["final_translation"].tolist(),
            final_relative_quaternion_xyzw=c["final_rotation"].as_quat().tolist(),
            body_dofs=[b.n_dofs for b in c["bodies"]])
        reports.append(result)
        (output/f'{spec["name"]}_trace.json').write_text(json.dumps(c["trace"],allow_nan=False)+"\n")
        print(spec["name"],result["passed"],"penetration",stats["max_contact_penetration_m"],"SAT",stats["min_sampled_sat_gap_m"],flush=True)
    report = dict(scope="5-second settling and bounded-force contact bench; not official route or robot execution",
        config=config,thresholds=thresholds,fingerprint=fingerprint,source_changed_during_run=fingerprint!=evidence_fingerprint(),genesis_version=version("genesis-world"),
        passed=all(c["passed"] for c in reports),cases=reports,physics_steps=steps,simulated_seconds=steps*dt,
        wall_seconds=time.monotonic()-started,pose_writes_after_reset=False,sat_sample_interval_s=.005,
        continuous_collision_certificate=False,official_route_verified=False,robot_grasp_verified=False,
        formal_demo_qualified=False)
    (output/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dt",type=float,default=.001)
    parser.add_argument("--precision",choices=("32","64"),default="64")
    parser.add_argument("--only",nargs="+")
    args = parser.parse_args()
    result = run_probe(args.output,args.dt,args.only,args.precision)
    if not result["passed"]:
        raise SystemExit("One or more checks failed; inspect report.json")


if __name__=="__main__":
    main()
