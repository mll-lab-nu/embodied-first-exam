"""Physical execution and recording for three trajectory-first cage families."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import time
from types import SimpleNamespace

import fcl
import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
import trimesh

from .inverse_window import SEED, Kinematics, SolidOracle, config, save, sha
from .family_motion import OUTPUT, FAMILIES
from .geometry import HedgehogLayout, load_template, clearance_samples
from .plan_escape import interpolate
from .stability import array


def admitted(folder):
    folder = Path(folder)
    cert = json.loads((folder / "certificate.json").read_text())
    if not (cert["passed"] and cert["continuous_clearance_lower_bound_m"] > .0001
            and cert["ik_sha256"] == sha(folder / "ik_before_geometry.json")
            and cert["asset_manifest_sha256"] == sha(folder / "assets/sha256.json")):
        raise ValueError("Missing or stale complete path certificate")
    for name, digest in cert["source_fingerprints"].items():
        if sha(Path(__file__).with_name(name)) != digest:
            raise ValueError(f"Certificate source changed: {name}")
    for name, digest in json.loads((folder / "assets/sha256.json").read_text()).items():
        if sha(folder / "assets" / name) != digest:
            raise ValueError(f"Changed scene asset: {name}")
    return json.loads((folder / "ik_before_geometry.json").read_text()), cert


class RobotAudit:
    def __init__(self, folder):
        self.kin = Kinematics(); m = self.kin.model
        self.oracle = SolidOracle(Path(folder) / "assets")
        fixed = fcl.Transform(self.kin.cage_r.as_matrix(), self.kin.cage_origin)
        for obj in self.oracle.objects[0]: obj.setTransform(fixed)
        self.oracle.managers[0].update()
        self.geoms = []
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]): continue
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = m.mesh(m.geom_dataid[i])
                v = m.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]]
                hull = trimesh.convex.convex_hull(v)
                shape = fcl.Convex(hull.vertices, len(hull.faces), np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel())
                vertices = hull.vertices
            elif m.geom_type[i] == mujoco.mjtGeom.mjGEOM_BOX:
                size = m.geom_size[i]
                shape = fcl.Box(*(2*size)); vertices = trimesh.bounds.corners(np.array([-size, size]))
            else: raise ValueError("Unvalidated robot collider type")
            name = m.body(m.geom_bodyid[i]).name
            self.geoms.append((i, name, fcl.CollisionObject(shape), vertices))
        self.all_robot = fcl.DynamicAABBTreeCollisionManager()
        self.all_robot.registerObjects([g[2] for g in self.geoms]); self.all_robot.setup()
        self.nonfinger = fcl.DynamicAABBTreeCollisionManager()
        self.nonfinger.registerObjects([g[2] for g in self.geoms if g[1] not in ("left_finger", "right_finger")]); self.nonfinger.setup()
        self.mount = fcl.CollisionObject(fcl.Box(.22, .22, .10), fcl.Transform(np.array([.06, .2, self.kin.cage_origin[2]-.17])))

    @staticmethod
    def depth(a, b):
        data = fcl.CollisionData(request=fcl.CollisionRequest(num_max_contacts=100, enable_contact=True))
        a.collide(b, data, fcl.defaultCollisionCallback)
        return max((c.penetration_depth for c in data.result.contacts), default=0.)

    def check(self, q, ball_world=None):
        self.kin.q[:] = q; self.kin.forward()
        m, d = self.kin.model, self.kin.data
        errors = []
        if any(c.dist < -.0001 for c in d.contact): errors.append("robot self collision")
        for i, name, obj, v in self.geoms:
            r, p = d.geom_xmat[i].reshape(3, 3), d.geom_xpos[i] + self.kin.mount
            obj.setTransform(fcl.Transform(r, p))
            if name != "link0" and (v@r.T+p)[:, 2].min() < self.kin.mount[2]-.0001:
                errors.append(f"table: {name}")
        self.all_robot.update(); self.nonfinger.update()
        if ball_world is None:
            pose = self.kin.ball_pose()
            p = self.kin.cage_origin + self.kin.cage_r.apply(pose[:3])
            r = self.kin.cage_r * Rotation.from_quat(pose[3:])
        else:
            p = np.array(ball_world[0]); r = Rotation.from_quat(ball_world[1])
        transform = fcl.Transform(r.as_matrix(), p)
        for obj in self.oracle.objects[1]: obj.setTransform(transform)
        self.oracle.managers[1].update()
        for label, a, b in (("robot/cage", self.all_robot, self.oracle.managers[0]),
                            ("robot/mount", self.all_robot, self.mount),
                            ("nonfinger/ball", self.nonfinger, self.oracle.managers[1])):
            depth = self.depth(a, b)
            if depth > .0001: errors.append(dict(pair=label, depth_m=depth))
        return errors


def plan_audit(folder):
    folder = Path(folder); trace, cert = admitted(folder); check = RobotAudit(folder)
    errors = []; samples = 0
    for i, frame in enumerate(trace["frames"]):
        qa = np.array(frame["qpos"]); qb = np.array(trace["frames"][min(i+1, len(trace["frames"])-1)]["qpos"])
        n = max(1, int(np.ceil(np.max(abs(qb-qa))/.01)))
        for t in np.linspace(0, 1, n+1)[:-1]:
            bad = check.check((1-t)*qa+t*qb); samples += 1
            if bad:
                errors.append(dict(frame=i, u=float(t), errors=bad)); break
        if errors: break
        if i % 100 == 0: print(f"Robot audit {i}/{len(trace['frames'])}", flush=True)
    result = dict(passed=not errors, errors=errors, samples=samples, maximum_joint_sample_step_rad=.01,
        certificate_sha256=sha(folder / "certificate.json"), ik_sha256=sha(folder / "ik_before_geometry.json"))
    save(folder / "robot_audit.json", result); print(json.dumps(result), flush=True)
    if errors: raise ValueError("Robot clearance failed")


def build_scene(folder, cfg):
    import genesis as gs
    from topogym.world import StandardTabletopSceneBuilder
    folder = Path(folder); assets = folder / "assets"
    template_data = json.loads((assets / "template.json").read_text())
    if len(template_data["hedgehog"]["spikes"]) == 10:
        template_data = load_template(assets / "template.json")
    elif not (len(template_data["hedgehog"]["spikes"]) == 6
              and template_data["hedgehog"]["spike_shape"] == "cylinder"):
        raise ValueError("Unsupported fixed-spike prototype")
    layout = HedgehogLayout(template_data, 3.)
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control,
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            enable_joint_limit=True, max_collision_pairs=16384, iterations=100,
            constraint_timeconst=.0012, noslip_iterations=5))
    base = builder.create(show_viewer=False, include_robot=True,
        robot_material=gs.materials.Rigid(gravity_compensation=1.))
    kin = Kinematics(); origin, rotation = kin.cage_origin, kin.cage_r
    floor = float(cfg.env.frames.table_surface.origin[2])
    mount = base.manifest.add("hedgehog_mount", base.scene.add_entity(gs.morphs.Box(
        pos=(.06, .2, floor+.05), size=(.22, .22, .1), fixed=True),
        surface=gs.surfaces.Plastic(color=(.16, .20, .24)), name="hedgehog_mount"))
    cage = base.manifest.add("hedgehog_cage", base.scene.add_entity(gs.morphs.URDF(
        file=str((assets / "cage.urdf").resolve()), pos=origin, quat=rotation.as_quat()[[3, 0, 1, 2]],
        fixed=True, convexify=True, decimate=False, merge_fixed_links=False),
        material=gs.materials.Rigid(friction=.3), name="hedgehog_cage"))
    initial = json.loads((folder / "ik_before_geometry.json").read_text())["frames"][0]["ball_pose"]
    br = rotation * Rotation.from_quat(initial[3:]); bp = origin + rotation.apply(initial[:3])
    ball = base.manifest.add("hedgehog_ball", base.scene.add_entity(gs.morphs.URDF(
        file=str((assets / "hedgehog.urdf").resolve()), pos=bp, quat=br.as_quat()[[3, 0, 1, 2]],
        fixed=False, convexify=True, decimate=False, merge_fixed_links=False),
        material=gs.materials.Rigid(friction=.3), name="hedgehog_ball"))
    builder.finalize(base)
    loaded = []
    for name, entity in (("cage", cage), ("hedgehog", ball)):
        files = sorted(assets.glob(f"{name}_collision_*.obj"))
        if len(entity.geoms) != len(files): raise ValueError("Loaded compound cell count changed")
        # Genesis may internally anchor free bodies at their COM/principal axes.
        # Public relative poses retain the authored frame; compare in that frame.
        user_r = Rotation.from_quat(array(entity.get_quat())[[1,2,3,0]]).as_matrix()
        solver_r = Rotation.from_quat(array(entity.get_quat(relative=False))[[1,2,3,0]]).as_matrix()
        anchor = np.eye(4); anchor[:3,:3] = user_r.T@solver_r
        anchor[:3,3] = user_r.T@(array(entity.get_pos(relative=False))-array(entity.get_pos()))
        maximum = 0.
        for geom, file in zip(entity.geoms, files):
            source = trimesh.load(file, force="mesh")
            transform = np.eye(4); transform[:3, :3] = Rotation.from_quat(np.asarray(geom.init_quat)[[1, 2, 3, 0]]).as_matrix()
            transform[:3, 3] = geom.init_pos
            actual = geom.mesh.trimesh.copy().apply_transform(anchor@transform)
            error = float(abs(actual.bounds-source.bounds).max()); maximum = max(maximum, error)
            if not geom.is_convex or error > 1e-7: raise ValueError(f"Loaded collider differs: {name}: {error}")
        loaded.append(dict(name=name, cells=len(files), maximum_bounds_error_m=maximum,
                           solver_to_authored_frame=anchor.tolist(), passed=True))
    return SimpleNamespace(scene=base.scene, manifest=base.manifest, cameras=base.cameras, ball=ball,
        cage=cage, mount=mount, origin=origin, rotation=rotation, layout=layout, loaded_audit=loaded)


def execute(folder, substeps=10, backend="cuda"):
    folder = Path(folder); trace, cert = admitted(folder)
    check = json.loads((folder / "robot_audit.json").read_text())
    if not check["passed"] or check["certificate_sha256"] != sha(folder / "certificate.json"):
        raise ValueError("A current robot clearance check is required")
    output = folder / ("physics" if substeps==10 else f"physics_substeps{substeps}")
    if (output / "report.json").exists(): raise ValueError("Preserve the existing physics run")
    output.mkdir(parents=True, exist_ok=True)
    cfg = config(); cfg.env.cameras = {}; cfg.env.renderer.type = "rasterizer"
    cfg.env.sim.dt = .005; cfg.env.sim.substeps = substeps; cfg.env.genesis.precision = "64"
    cfg.env.genesis.backend=backend
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    import genesis as gs
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets
    gs.init(backend=gs.cuda if backend=="cuda" else gs.cpu, precision="64", logging_level="warning", seed=0)
    task = build_scene(folder, cfg)
    cage_radius=float(json.loads((folder/"assets/asset_report.json").read_text())["maximum_radial_extent_m"])
    c = initialize_franka_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, settle_steps=0)
    ball = task.ball; solver = task.scene.sim.rigid_solver
    q = np.array(trace["frames"][0]["qpos"])
    for name, value in robotiq_joint_targets(.0054).items():
        name = {"right_driver_joint":"finger_joint1", "left_driver_joint":"finger_joint2"}.get(name, "r85_"+name)
        q[c.robot.get_joint(name).qs_idx_local[0]] = value
    c.robot.set_qpos(q, zero_velocity=True); c.robot.control_dofs_position(q[:7], c.arm_dofs)
    c.set_gripper(.0044, steps=0)
    fingers = {c.robot.get_link(n).idx for n in ("left_finger", "right_finger")}
    robot_links = {link.idx for link in c.robot.links if link.idx!=c.robot.base_link_idx}
    fixtures = {task.cage.base_link_idx, task.mount.base_link_idx, task.manifest.get("table").base_link_idx}
    step_count=0; phase="pregrasp_contact"; welded=False; rows=[]; grasp_event=None
    max_cage_pen=0.; max_robot_pen=0.; max_pen=0.; max_tracking=0.; started=time.monotonic()
    def pose(): return array(ball.get_pos()), Rotation.from_quat(array(ball.get_quat())[[1,2,3,0]])
    def record():
        p, r = pose()
        rows.append(dict(physics_step=step_count, time_s=step_count*.005, phase=phase,
            ball_position_m=p.tolist(), ball_quaternion_xyzw=r.as_quat().tolist(), robot_qpos=array(c.robot.get_qpos()).tolist(),
            linear_speed_m_s=float(np.linalg.norm(array(ball.get_vel()))), angular_speed_rad_s=float(np.linalg.norm(array(ball.get_ang()))),
            grasp_constraint_active=welded))
    def step():
        nonlocal step_count, max_cage_pen, max_robot_pen, max_pen
        task.scene.step(); step_count+=1
        ct=solver.collider.get_contacts(as_tensor=True,to_torch=True)
        la,lb,pen=(array(ct[k]) for k in ("link_a","link_b","penetration"))
        mask=((la==ball.base_link_idx)&(lb==task.cage.base_link_idx))|((lb==ball.base_link_idx)&(la==task.cage.base_link_idx))
        robot_mask=(np.isin(la,list(robot_links))&np.isin(lb,list(fixtures)))|(np.isin(lb,list(robot_links))&np.isin(la,list(fixtures)))
        max_cage_pen=max(max_cage_pen,float(pen[mask].max(initial=0)))
        max_robot_pen=max(max_robot_pen,float(pen[robot_mask].max(initial=0)))
        max_pen=max(max_pen,float(pen[(la==ball.base_link_idx)|(lb==ball.base_link_idx)].max(initial=0)))
        if max_cage_pen>.00015 or max_robot_pen>.00015: raise ValueError("Physical cage/robot penetration exceeded limit")
        if step_count%2==0:
            record()
            if not np.isfinite(np.r_[rows[-1]["robot_qpos"],rows[-1]["ball_position_m"]]).all(): raise ValueError("Nonfinite physical state")
        if step_count%400==0: print(f"physics {step_count*.005:.1f}s {phase}; wall {time.monotonic()-started:.1f}s",flush=True)
    def drive_hand(position, rotation, steps=2):
        target,error=c.robot.inverse_kinematics(link=c.ee_link,pos=position,quat=rotation.as_quat()[[3,0,1,2]],
            init_qpos=c.robot.get_qpos(),dofs_idx_local=c.arm_dofs,max_samples=1,max_solver_iters=300,
            pos_tol=1e-5,rot_tol=1e-4,return_error=True)
        if np.linalg.norm(array(error))>.002 or np.max(abs(array(target)[:7]-c.arm_qpos()))>.3:
            raise ValueError("Live IK failed or changed branch")
        c.robot.control_dofs_position(target[:7],c.arm_dofs)
        for _ in range(steps): step()
    def move(a,b,hp,hr,speed=.012,angular=.4):
        nonlocal max_tracking
        a,b=np.array(a),np.array(b);ra,rb=Rotation.from_quat(a[3:]),Rotation.from_quat(b[3:]);delta=(rb*ra.inv()).as_rotvec()
        duration=max(np.linalg.norm(b[:3]-a[:3])/speed,np.linalg.norm(delta)/angular,.25)*1.875
        count=max(2,int(np.ceil(duration/.01)))
        for i in range(1,count+1):
            t=i/count;u=10*t**3-15*t**4+6*t**5
            p=task.origin+task.rotation.apply(a[:3]+u*(b[:3]-a[:3]));r=task.rotation*Rotation.from_rotvec(u*delta)*ra
            drive_hand(p+r.apply(hp),r*hr)
            max_tracking=max(max_tracking,float(np.linalg.norm(pose()[0]-p)))
        for _ in range(20):step()
    record(); result=dict(passed=False,complete=False)
    try:
        for _ in range(80):
            step();ct=c.robot.get_contacts(with_entity=ball)
            touched=set(array(ct["link_a"]).tolist())|set(array(ct["link_b"]).tolist())
            if fingers.issubset(touched):break
        else:raise ValueError("No simultaneous bilateral finger contact")
        p,r=pose();hp=r.inv().apply(c.hand_pos()-p);hr=r.inv()*Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        solver.add_weld_constraint(c.ee_link.idx,ball.base_link_idx);welded=True
        grasp_event=dict(physics_step=step_count,finger_links=sorted(fingers),simultaneous_contact=True)
        phase="hold_grasp"
        for _ in range(100):step()
        p,r=pose();actual=np.r_[task.rotation.inv().apply(p-task.origin),(task.rotation.inv()*r).as_quat()]
        path=trace["proposed_path"]
        phase="align_with_verified_path";move(actual,path[0],hp,hr)
        for i,(a,b) in enumerate(zip(path[:-1],path[1:])):
            phase=trace["extraction_phases"][i]
            move(a,b,hp,hr)
        points,radii=clearance_samples(task.layout);p,r=pose();world=r.apply(points)+p
        margin=float(np.min(np.linalg.norm(world[:,:2]-task.origin[:2],axis=1)-radii)-cage_radius)
        if margin<.003:raise ValueError("Hedgehog not fully outside before placement")
        result["outside_margin_before_release_m"]=margin
        for label,a,b in zip(trace["release_phases"],trace["release_path"][:-1],trace["release_path"][1:]):
            phase=label;move(a,b,hp,hr,speed=.03,angular=.6)
        phase="release";solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx);welded=False;c.open_gripper(steps=0)
        for _ in range(150):step()
        hand_p=c.hand_pos();hand_r=Rotation.from_quat(c.hand_quat()[[1,2,3,0]])
        for t in np.linspace(0,1,100):drive_hand(hand_p+[0,0,.08*t],hand_r)
        phase="final_settle"
        for _ in range(1000):step()
        if rows[-1]["physics_step"]!=step_count:record()
        p,r=pose();world=r.apply(points)+p
        margin=float(np.min(np.linalg.norm(world[:,:2]-task.origin[:2],axis=1)-radii)-cage_radius)
        speed=float(np.linalg.norm(array(ball.get_vel())));angular=float(np.linalg.norm(array(ball.get_ang())))
        result.update(passed=bool(margin>.003 and speed<.001 and angular<np.deg2rad(.5)
            and max_cage_pen<.0001 and max_robot_pen<.0001),complete=True,grasp_released=True,
            outside_margin_after_release_m=margin,final_linear_speed_m_s=speed,final_angular_speed_rad_s=angular)
    except Exception as exc:
        result.update(passed=False,error=str(exc),failed_phase=phase);print(f"FAILED: {exc}",flush=True)
    finally:
        if welded:solver.delete_weld_constraint(c.ee_link.idx,ball.base_link_idx)
        result.update(physics_steps=step_count,simulated_seconds=step_count*.005,dt=.005,substeps=substeps,
            precision_bits=64,backend=backend,pregrasp_start=True,assisted_grasp=True,contact_gate=grasp_event,
            live_object_pose_overwrites=False,live_robot_pose_overwrites=False,geometry_modified=True,
            max_cage_penetration_m=max_cage_pen,max_robot_fixture_penetration_m=max_robot_pen,
            max_all_ball_contact_penetration_m=max_pen,max_position_tracking_error_m=max_tracking,
            loaded_collision_audit=task.loaded_audit,asset_manifest_sha256=sha(folder/"assets/sha256.json"),
            ik_sha256=sha(folder/"ik_before_geometry.json"),runner_sha256=sha(Path(__file__)))
        save(output/"trajectory.json",rows);save(output/"report.json",result)
        print(json.dumps(result,indent=2),flush=True)
    if not result["passed"]:raise ValueError("Complete physical run did not pass")


def audit(folder, substeps=10):
    folder=Path(folder);admitted(folder)
    output=folder/("physics" if substeps==10 else f"physics_substeps{substeps}")
    report=json.loads((output/"report.json").read_text());rows=json.loads((output/"trajectory.json").read_text())
    if not report["passed"] or not report["grasp_released"]:raise ValueError("Full extraction and release required")
    hashes={n:sha(output/n) for n in ("report.json","trajectory.json")}
    oracle=SolidOracle(folder/"assets");check=RobotAudit(folder);kin=check.kin
    poses=[np.r_[kin.cage_r.inv().apply(np.array(row["ball_position_m"])-kin.cage_origin),
        (kin.cage_r.inv()*Rotation.from_quat(row["ball_quaternion_xyzw"])).as_quat()] for row in rows]
    minimum=float("inf");errors=[];samples=0
    cage_radius=float(json.loads((folder/"assets/asset_report.json").read_text())["maximum_radial_extent_m"])
    for i,(a,b) in enumerate(zip(poses[:-1],poses[1:])):
        if min(np.linalg.norm(a[:2]),np.linalg.norm(b[:2]))-np.linalg.norm(b[:3]-a[:3]) <= cage_radius+.092:
            for q in interpolate(a,b,.0001):
                gap=oracle.distance(q);minimum=min(minimum,gap);samples+=1
                if gap<=.0001:errors.append(dict(frame=i,gap_m=gap));break
        # Audit every saved robot state, including release and retreat.
        row=rows[i];bad=check.check(row["robot_qpos"],(row["ball_position_m"],row["ball_quaternion_xyzw"]))
        if bad:errors.append(dict(frame=i,robot_errors=bad))
        if errors:break
        if i%500==0:print(f"Actual-state audit {i}/{len(rows)}",flush=True)
    last=rows[-1];bad=check.check(last["robot_qpos"],(last["ball_position_m"],last["ball_quaternion_xyzw"]))
    if bad:errors.append(dict(frame=len(rows)-1,robot_errors=bad))
    tail=[r for r in rows if r["time_s"]>=last["time_s"]-2]
    positions=np.array([r["ball_position_m"] for r in tail]);drift=float(np.linalg.norm(positions-positions[0],axis=1).max())
    speed=max(r["linear_speed_m_s"] for r in tail);angular=max(r["angular_speed_rad_s"] for r in tail)
    release=[r for r in rows if r["phase"] in ("release","final_settle")]
    freed=bool(release) and not any(r["grasp_constraint_active"] for r in release)
    mesh=trimesh.load(folder/"assets/hedgehog.obj",force="mesh")
    bottom=float((Rotation.from_quat(last["ball_quaternion_xyzw"]).apply(mesh.vertices)+last["ball_position_m"])[:,2].min()-kin.mount[2])
    if not freed or drift>.0002 or speed>.001 or angular>np.deg2rad(.5) or bottom<-.0001:errors.append("Release/rest verification failed")
    if any(sha(output/n)!=h for n,h in hashes.items()):raise ValueError("Input changed during audit")
    result=dict(passed=not errors,errors=errors,source_sha256=hashes,states_checked=i+2,
        geometric_samples=samples,minimum_sampled_clearance_m=minimum,continuous_interpolation_clearance_lower_bound_m=minimum-.0001,
        material_motion_bound_m=.0001,grasp_constraint_removed=freed,final_2s_drift_m=drift,
        final_2s_max_speed_m_s=speed,final_2s_max_angular_speed_rad_s=angular,lowest_point_above_table_m=bottom,
        scope="independent convex solid and robot checks; continuity bound applies to interpolation of actual saved states")
    save(output/"audit.json",result);print(json.dumps(result,indent=2),flush=True)
    if errors:raise ValueError("Physical state audit failed")


def render(folder, backend="cuda", *, video_prefix=None):
    folder=Path(folder);admitted(folder);physical=folder/"physics"
    audit_result=json.loads((physical/"audit.json").read_text())
    if not audit_result["passed"] or any(sha(physical/n)!=h for n,h in audit_result["source_sha256"].items()):
        raise ValueError("A current physical audit must pass before recording")
    rows=json.loads((physical/"trajectory.json").read_text());report=json.loads((physical/"report.json").read_text())
    times=np.array([r["time_s"] for r in rows]);fps=12
    targets=np.arange(0,times[-1]+1e-8,1/fps);indices=[int(np.argmin(abs(times-t))) for t in targets];indices[-1]=len(rows)-1
    frames=[dict(rows[i],source_trace_index=i) for i in indices]
    output=folder/"recording"
    if (output/"recording_report.json").exists():raise ValueError("Preserve the existing recording")
    output.mkdir(parents=True,exist_ok=True);save(output/"render_frames.json",frames)
    cfg=config();cfg.env.renderer.spp=16;cfg.env.genesis.precision="64"
    cfg.env.genesis.backend=backend
    if backend=="cpu":cfg.env.renderer.type="rasterizer"
    cfg.env.cameras.front_oblique.pos=[.55,-.18,1.55]
    cfg.env.cameras.front_oblique.lookat=[-.03,.10,1.12]
    cfg.env.cameras.front_oblique.fov=48
    OmegaConf.save(cfg,output/"config.yaml",resolve=True)
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image,ImageDraw
    from topogym.utils.franka import initialize_franka_controller
    gs.init(backend=gs.cuda if backend=="cuda" else gs.cpu,precision="64",logging_level="warning",seed=0)
    task=build_scene(folder,cfg)
    c=initialize_franka_controller(scene=task.scene,manifest=task.manifest,robot_cfg=cfg.robot_control,settle_steps=0)
    names=("agentview","front_oblique","wrist");camera_poses=[];phases=[];kin=Kinematics();max_fk_error=0.
    with ExitStack() as stack:
        from .geometry import ROOT
        destinations = {}
        for n in names if video_prefix is not None else (*names, "three_views"):
            destination = (ROOT/"demos/hedgehog_in_cage"/n/f"{video_prefix}_{n}.mp4"
                           if video_prefix is not None else output/f"{n}.mp4")
            if destination.exists(): raise ValueError(f"Preserve existing video: {destination}")
            destination.parent.mkdir(parents=True,exist_ok=True)
            destinations[n]=destination
        writers={n:stack.enter_context(imageio.get_writer(destination,fps=fps,codec="libx264",quality=7,
            macro_block_size=1,ffmpeg_params=["-threads","2"],ffmpeg_log_level="error")) for n,destination in destinations.items()}
        for i,row in enumerate(frames):
            c.robot.set_qpos(row["robot_qpos"]);task.ball.set_pos(row["ball_position_m"])
            task.ball.set_quat(np.array(row["ball_quaternion_xyzw"])[[3,0,1,2]])
            task.scene.visualizer.update_visual_states(force_render=True);task.cameras["wrist"].move_to_attach()
            kin.q=np.array(row["robot_qpos"]);hp,_=kin.forward();error=float(np.linalg.norm(c.hand_pos()-hp));max_fk_error=max(max_fk_error,error)
            if error>.00002:raise ValueError("Recorded robot differs from audited FK")
            changed=not phases or phases[-1]["name"]!=row["phase"]
            if changed:phases.append(dict(name=row["phase"],frame=i,time_s=i/fps))
            grid=Image.new("RGB",(1440,360))
            for j,n in enumerate(names):
                rgb=task.cameras[n].render(force_render=True)[0].copy();writers[n].append_data(rgb)
                if changed or i==len(frames)-1:Image.fromarray(rgb).save(output/f'{row["phase"]}_{n}.jpg')
                tile=Image.fromarray(rgb).resize((480,360));draw=ImageDraw.Draw(tile)
                draw.rectangle((0,0,480,25),fill=(20,28,35));draw.text((10,6),n,fill="white");grid.paste(tile,(480*j,0))
            if "three_views" in writers: writers["three_views"].append_data(np.asarray(grid))
            camera_poses.append({n:np.asarray(task.cameras[n].transform).tolist() for n in names})
            if i%48==0:print(f"Record {i+1}/{len(frames)}: {row['phase']}",flush=True)
    save(output/"camera_poses.json",camera_poses)
    result=dict(passed=True,frames=len(frames),fps=fps,duration_s=len(frames)/fps,phases=phases,
        actual_physics_states=True,kinematic_rehearsal=False,renderer_backend=backend,renderer_type=str(cfg.env.renderer.type),physics_steps=report["physics_steps"],
        rendering_physics_steps=0,maximum_pad_fk_error_m=max_fk_error,loaded_collision_audit=task.loaded_audit,
        source_physical_sha256=audit_result["source_sha256"],render_frames_sha256=sha(output/"render_frames.json"),
        asset_manifest_sha256=sha(folder/"assets/sha256.json"),pregrasp_start=True,assisted_grasp=True,grasp_released=True,
        video_files={n:str(p.relative_to(ROOT)) for n,p in destinations.items()})
    save(output/"recording_report.json",result);print(json.dumps(result,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=("plan-audit","physics","audit","render"))
    p.add_argument("family",choices=FAMILIES);p.add_argument("--output",type=Path,default=OUTPUT);p.add_argument("--substeps",type=int,default=10);p.add_argument("--backend",choices=("cuda","cpu"),default="cuda")
    a=p.parse_args(); a.output=a.output/a.family
    if a.action=="plan-audit":plan_audit(a.output)
    elif a.action=="physics":execute(a.output,a.substeps,a.backend)
    elif a.action=="audit":audit(a.output,a.substeps)
    else:render(a.output,a.backend)


if __name__=="__main__":main()
