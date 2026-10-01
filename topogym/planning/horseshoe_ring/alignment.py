"""Reposition the right-held shoe while the left hand holds the ring.

The short initial contact release and both passive chains require physical
validation. The subsequent shoe motion is checked against the measured ring,
upper shoe, table and both robot arms; it is not a complete puzzle proof.
"""
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import relative_pose, tcp_pose
from topogym.planning.rigid_reference.geometry import (
    RigidPathChecker, combine_meshes, freeze_scene, interpolate, matrix, pose_dict)
from topogym.utils.io import write_json_atomic


def plan_lower_reposition(planner, observation):
    task=planner.task
    _,_,scene,meshes,identity=freeze_scene('horseshoe_ring',task.difficulty,task.seed,
                                         planner.directory/'geometry_assets')
    if identity['instance_id']!=task.instance_id:
        raise ValueError('Lower reposition geometry differs from the current task')
    bodies,seed=planner.observed(observation)
    pieces=[]
    for name in ('horseshoe_left','target_ring'):
        mesh=meshes[name].copy();mesh.apply_transform(matrix(*bodies[name]));pieces.append(mesh)
    table=trimesh.creation.box(scene.env.world.table.size)
    table.apply_translation(scene.env.world.table.pos);pieces.append(table)
    checker=RigidPathChecker(combine_meshes(pieces),meshes['horseshoe_right'])
    actual=bodies['horseshoe_right'];start=actual;release=[]
    if not checker.initial_free(start):
        for length in (.0001,.0002,.0005,.001,.002,.004):
            for axis in np.eye(3):
                for sign in (-1.,1.):
                    candidate=(actual[0]+sign*length*axis,actual[1])
                    gap=checker.clearance(candidate)
                    release.append(dict(translation_m=(sign*length*axis).tolist(),clearance_m=gap))
                    if gap>checker.margin+checker.error and checker.initial_free(candidate):
                        start=candidate;break
                else:continue
                break
            else:continue
            break
    if not checker.initial_free(start):
        raise ValueError('No free lower-shoe start after the bounded contact-release proposals')
    frame=planner.reference[planner.fold_end_index]
    p,r=relative_pose(frame['horseshoe_left'],frame['horseshoe_right'])
    up,ur=bodies['horseshoe_left'];nominal=(up+ur.apply(p),ur*r)
    rotations=[nominal[1]]+[Rotation.from_rotvec(axis*np.radians(angle))*nominal[1]
                            for axis in np.eye(3) for angle in (-10.,10.)]
    offset=relative_pose(actual,tcp_pose(observation['robot']['right']))
    radius=float(np.linalg.norm(task.placement_vertices['horseshoe_right'],axis=1).max())
    attempts=[]
    for turn in rotations:
        for delta in ([0.,0.,0.],*[axis*s for axis in np.eye(3) for s in (-.01,.01)]):
            goal=(nominal[0]+delta,turn)
            if not checker.initial_free(goal):continue
            edge=checker.edge(start,goal)
            if not edge['passed']:continue
            path=[actual,start,goal];q=seed.copy();rows=[];failure=None
            for index,(a,b) in enumerate(zip(path[:-1],path[1:])):
                motion=np.linalg.norm(a[0]-b[0])+radius*(a[1]*b[1].inv()).magnitude()
                for u in np.linspace(0,1,max(1,int(np.ceil(motion/.0005)))+1):
                    p,r=interpolate(a,b,u);previous=q.copy()
                    try:
                        q=planner.checker.solve('right',(p+r.apply(offset[0]),r*offset[1]),q)
                        checked=planner.checker.check(q,body_poses=dict(bodies,horseshoe_right=(p,r)),
                            contacts={'left':'target_ring','right':('horseshoe_left','horseshoe_right')})
                        if not checked['passed']:raise ValueError(str(checked))
                        if np.max(np.abs(q-previous))>.15:raise ValueError('Joint branch change')
                        rows.append(dict(edge=index,fraction=float(u),qpos=q.tolist()))
                    except ValueError as error:
                        failure=dict(edge=index,fraction=float(u),error=str(error));break
                if failure:break
            attempts.append(dict(goal=pose_dict(goal),failure=failure))
            if failure:continue
            result=dict(passed=True,poses=[pose_dict(p) for p in path],joint_samples=rows,
                free_edge_certificate=edge,contact_release_certified=False,
                contact_release_candidates=release,nominal_folded_lower=pose_dict(nominal),
                observed_state=observation['state'],geometry_identity=identity,attempts=attempts,
                passive_contact_names=['chain_upper_1','chain_lower_1'],
                scope='free edge bounds against measured upper shoe, ring and table; native robot samples; contact prefix and chain response require physics')
            write_json_atomic(planner.directory/'lower_reposition_plan.json',result)
            return result
    write_json_atomic(planner.directory/'lower_reposition_plan.json',dict(passed=False,attempts=attempts))
    raise ValueError('No checked lower-shoe reposition with the ring held fixed')
