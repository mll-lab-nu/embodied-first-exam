"""Read-only native IK and imported mesh audit for the low-tier reference."""
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.solvers.genesis_kinematics import GenesisIKSolver, GenesisFKSolver
from topogym.utils.arrays import to_numpy
from topogym.planning.rigid_reference.geometry import matrix
from topogym.planning.rigid_reference.feedback import body_pose, tcp_pose
from .simplified_routes import PARTS, world_route


def prepare(env, variant):
    robot, world = env._robot, env._world.read_state()
    initial = {s: body_pose(world["bodies"][n]) for s,n in PARTS.items()}
    measured = robot.observe()
    offsets = {}
    for s,(p,r) in initial.items():
        tp,tr = tcp_pose(measured[s])
        offsets[s] = (r.inv().apply(tp-p), r.inv()*tr)
    motions, object_audit = world_route(variant, initial, env._task.terminal_metadata()["goal_region"])
    ik, fk = GenesisIKSolver(robot.entity), GenesisFKSolver(robot.entity)
    q = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    managers = {n: trimesh.collision.CollisionManager() for n in (*PARTS, *PARTS.values())}
    geometry = []
    def turn(q):
        return Rotation.from_quat(np.asarray(q)[[1,2,3,0]])
    for s in PARTS:
        for link in robot.entity.links:
            if not link.name.startswith(s+"/"):
                continue
            for index, geom in enumerate(link.geoms):
                mesh = geom.mesh.trimesh.copy()
                mesh.apply_transform(matrix(geom.init_pos, turn(geom.init_quat)))
                name = f"{link.name}/{index}"
                managers[s].add_object(name, mesh)
                geometry.append((s,name,link.idx_local,mesh.vertices.copy(),
                                 link.name.rsplit('/',1)[-1] not in {'base_link','waist_link','shoulder_link'}))
        for index, geom in enumerate(env._world.entities[PARTS[s]].links[0].geoms):
            mesh = geom.mesh.trimesh.copy()
            mesh.apply_transform(matrix(geom.init_pos,turn(geom.init_quat)))
            managers[PARTS[s]].add_object(str(index),mesh)
    frames, issues, minimum = [], [], float('inf')
    for motion in motions:
        length = np.linalg.norm(motion.end[0]-motion.start[0])
        angle = (motion.end[1]*motion.start[1].inv()).magnitude()
        count = max(2, int(np.ceil(max(length/.006, angle/np.deg2rad(4))))+1)
        for u in np.linspace(0.,1.,count):
            bodies = {'left': motion.at(u), 'right': initial['right']}
            p,r = bodies['left']; dp,dr=offsets['left']
            group=robot.groups['left']
            tcp_r=r*dr
            hand_r=tcp_r*turn(group.tcp_orientation_in_hand_wxyz).inv()
            q=ik.solve_checked(link_name=group.hand_link,
                position_world_m=p+r.apply(dp)-hand_r.apply(group.tcp_position_in_hand_m),
                orientation_wxyz=hand_r.as_quat()[[3,0,1,2]],initial_qpos=q,
                joint_dof_indices=robot._indices['left'][:6])
            poses=fk.solve(q)
            pp=np.asarray(poses['position_world_m']).reshape(-1,3)
            rr=np.asarray(poses['orientation_wxyz']).reshape(-1,4)
            gap=float('inf')
            for s,n,link,v,table in geometry:
                R=turn(rr[link]); managers[s].set_transform(n,matrix(pp[link],R))
                if table: gap=min(gap,float((R.apply(v)+pp[link])[:,2].min()-env._task.table_height_m))
            minimum=min(minimum,gap)
            for s,n in PARTS.items():
                for key in managers[n]._objs: managers[n].set_transform(key,matrix(*bodies[s]))
            hits={}
            for a,b in [('left','right'),('left','piece_1'),('right','piece_0'),
                        ('left','piece_0'),('right','piece_1'),('piece_0','piece_1')]:
                _,pairs=managers[a].in_collision_other(managers[b],return_names=True)
                if a in PARTS and b==PARTS[a]:
                    fingers=set(robot.groups[a].grasp.finger_links)
                    pairs={p for p in pairs if p[0].rsplit('/',1)[0] not in fingers}
                if pairs: hits[a+'__'+b]=sorted(pairs)
            margins=[]
            for s,g in robot.groups.items():
                joints=q[robot._q_indices[s][:6]]; limits=np.asarray(g.arm_limits_rad)
                margins.append(float(min(np.min(joints-limits[:,0]),np.min(limits[:,1]-joints))))
            if hits or gap < .002 or min(margins)<0:
                issues.append(dict(frame=len(frames),phase=motion.phase,progress=float(u),
                                   collisions=hits,table_clearance_m=gap,joint_margin_rad=min(margins)))
            frames.append(dict(phase=motion.phase,progress=float(u),qpos=q.tolist()))
    audit=dict(passed=not issues,frames=frames,issues=issues,minimum_table_clearance_m=minimum,
               scope='sampled native IK and imported arm, finger, piece meshes; cross-arm/own-piece/opposite-piece/table checks; not continuous robot or full self-collision proof',
               object_route=object_audit)
    return motions, initial, offsets, audit
