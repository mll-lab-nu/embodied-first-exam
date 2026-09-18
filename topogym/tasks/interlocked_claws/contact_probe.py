"""Force-driven blocking/free-motion and gravity controls on original meshes."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import generate_assets
from .collision import ClawCollision


def run(output, dt=.002, backend="cpu", sdf_cell=.0015, sdf_max_res=256, constraint_timeconst=.001):
    import genesis as gs
    from .scene import as_numpy

    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    if (output/"report.json").exists():
        raise FileExistsError(output)
    (output/"probe_source.py").write_text(Path(__file__).read_text())
    assembly, geometry = generate_assets(output/"assets")
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    scene = gs.Scene(show_viewer=False,
        sim_options=gs.options.SimOptions(dt=dt, substeps=4, gravity=(0, 0, -9.81)),
        rigid_options=gs.options.RigidOptions(iterations=100, max_collision_pairs=64, constraint_timeconst=constraint_timeconst))
    scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(friction=.3))
    cases = []
    for j, name in enumerate(("blocked_up", "blocked_down", "allowed_short_x", "gravity_drop")):
        translation = np.array([j*.9, 0, 0.])
        if name == "gravity_drop":
            translation[2] = -geometry["assembly_bounds_m"][0][2]+.015
        bodies = []
        for i, b in enumerate(assembly.bodies):
            if name == "gravity_drop" and i == 1:
                continue
            body = scene.add_entity(gs.morphs.URDF(
                file=str(output/"assets"/b.name/f"{b.name}.urdf"),
                pos=b.pose[:3, 3]+translation,
                quat=Rotation.from_matrix(b.pose[:3, :3]).as_quat()[[3, 0, 1, 2]],
                fixed=i == 0 and name != "gravity_drop", align=False, convexify=False, decimate=False),
                material=gs.materials.Rigid(friction=.3, gravity_compensation=0 if name == "gravity_drop" else 1.,
                    sdf_cell_size=sdf_cell, sdf_min_res=32, sdf_max_res=sdf_max_res), name=f"{name}_{i}")
            bodies.append(body)
        moving = bodies[-1]
        cases.append(dict(name=name, bodies=bodies, moving=moving, initial_pose=assembly.bodies[0 if name == "gravity_drop" else 1].pose.copy(),
            translation=translation, stats=dict(max_penetration_m=0., max_contact_force_N=0., contact_steps=0,
                max_triangle_contact_depth_m=0.), trace=[]))
    scene.build()
    solver = scene.sim.rigid_solver
    collision = ClawCollision(assembly)
    for c in cases:
        c["initial_pos"] = as_numpy(c["moving"].get_pos()).copy()
        c["initial_com"] = as_numpy(solver.get_links_pos([c["moving"].base_link_idx], ref="link_com"))[0].copy()
        c["initial_rotation"] = Rotation.from_quat(as_numpy(c["moving"].get_quat())[[1, 2, 3, 0]])
    started = time.monotonic()
    for step in range(1, round(2.5/dt)+1):
        t = step*dt
        forces, torques, links = [], [], []
        for c in cases:
            if c["name"] == "gravity_drop":
                continue
            b = c["moving"]; p = as_numpy(solver.get_links_pos([b.base_link_idx], ref="link_com"))[0]
            r = Rotation.from_quat(as_numpy(b.get_quat())[[1, 2, 3, 0]])
            target = np.array([.005, 0, 0]) if c["name"] == "allowed_short_x" else np.array([0, 0, .025 if c["name"] == "blocked_up" else -.025])
            u = np.clip(t/1.5, 0, 1); blend=u*u*(3-2*u)
            velocity = as_numpy(solver.get_links_vel([b.base_link_idx], ref="link_com"))[0]
            force = 500*(c["initial_com"]+target*blend-p)-35*velocity
            torque = 100*(c["initial_rotation"]*r.inv()).as_rotvec()-2*as_numpy(b.get_ang())
            force *= min(1., 6/max(np.linalg.norm(force), 1e-12))
            torque *= min(1., 10/max(np.linalg.norm(torque), 1e-12))
            forces.append(force); torques.append(torque); links.append(b.base_link_idx)
        solver.apply_links_external_force(np.asarray(forces), links, ref="link_com")
        solver.apply_links_external_torque(np.asarray(torques), links, ref="link_com")
        scene.step()
        ct = {k: as_numpy(v) for k,v in solver.collider.get_contacts().items()}
        for c in cases:
            b = c["moving"]; mask=(ct["link_a"]==b.base_link_idx)|(ct["link_b"]==b.base_link_idx)
            s=c["stats"]
            if mask.any():
                s["max_penetration_m"]=max(s["max_penetration_m"],float(ct["penetration"][mask].max()))
                s["max_contact_force_N"]=max(s["max_contact_force_N"],float(np.linalg.norm(ct["force"][mask],axis=1).max()))
                s["contact_steps"]+=1
            if step%round(.02/dt)==0:
                p=as_numpy(b.get_pos());q=as_numpy(b.get_quat())
                if not np.isfinite(np.r_[p,q]).all():raise RuntimeError("Non-finite contact probe state")
                if c["name"] != "gravity_drop":
                    poses=[]
                    for body in c["bodies"]:
                        pose=np.eye(4);pose[:3,3]=as_numpy(body.get_pos())
                        pose[:3,:3]=Rotation.from_quat(as_numpy(body.get_quat())[[1,2,3,0]]).as_matrix()
                        poses.append(pose)
                    if collision.clearance(poses)<0:
                        s["max_triangle_contact_depth_m"]=max(s["max_triangle_contact_depth_m"],collision.contact_depth())
                c["trace"].append(dict(time_s=t,position=p.tolist(),quat_wxyz=q.tolist(),
                    displacement_m=(p-c["initial_pos"]).tolist(),speed_m_s=float(np.linalg.norm(as_numpy(b.get_vel())))))
        if step%round(.5/dt)==0:print(f"Contact probes {t:.2f}/2.5 s; wall {time.monotonic()-started:.1f}s",flush=True)
    result=[]
    for c in cases:
        s=c["stats"];last=c["trace"][-1];delta=np.asarray(last["displacement_m"])
        tail=[r for r in c["trace"] if r["time_s"]>=2.]
        s["tail_max_speed_m_s"]=max(r["speed_m_s"] for r in tail)
        if c["name"]=="gravity_drop":
            vertices=assembly.bodies[0].mesh.vertices@Rotation.from_quat(np.asarray(last["quat_wxyz"])[[1,2,3,0]]).as_matrix().T+last["position"]
            s["final_lowest_vertex_m"]=float(vertices[:,2].min())
            passed=delta[2]<-.005 and s["max_contact_force_N"]>1 and abs(s["final_lowest_vertex_m"])<.001 and s["tail_max_speed_m_s"]<.01
        elif c["name"]=="allowed_short_x":
            s["target_error_m"]=float(np.linalg.norm(delta-[.005,0,0]))
            passed=s["target_error_m"]<.0005 and s["max_contact_force_N"]<.1
        else:
            passed=abs(delta[2])<.02 and s["max_contact_force_N"]>1 and s["contact_steps"]>10
        result.append(dict(name=c["name"],passed=bool(passed and s["max_penetration_m"]<.001
            and s["max_triangle_contact_depth_m"]<.00015),stats=s,final=last,trace=c["trace"]))
    report=dict(passed=all(c["passed"] for c in result),scope="bounded-force local contact controls; no robot grasp claim",
        dt=dt,backend=backend,substeps=4,constraint_timeconst=constraint_timeconst,physics_steps=step,pose_writes_after_initialization=False,
        friction=.3,sdf_cell_size_m=sdf_cell,sdf_max_res=sdf_max_res,source_mesh_sha256=[b.source["sha256"] for b in assembly.bodies],
        force_limit_N=6,torque_limit_Nm=10,linear_kp=500,linear_kd=35,angular_kp=100,angular_kd=2,
        cases=result,wall_seconds=time.monotonic()-started)
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({**report,"cases":[{k:v for k,v in c.items() if k!='trace'} for c in result]},indent=2),flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--dt",type=float,default=.002)
    p.add_argument("--sdf-cell",type=float,default=.0015);p.add_argument("--sdf-max-res",type=int,default=256)
    p.add_argument("--constraint-timeconst",type=float,default=.001)
    a=p.parse_args()
    if not run(a.output,a.dt,sdf_cell=a.sdf_cell,sdf_max_res=a.sdf_max_res,constraint_timeconst=a.constraint_timeconst)["passed"]:raise SystemExit(1)
