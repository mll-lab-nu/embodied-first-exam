"""Object-only withdrawal from a measured assembly, before checking the arm.

The positive-clearance route begins at a separately checked contact-release
endpoint. The release itself and passive-body dynamics are not certified.
"""
import time
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.planning.rigid_reference.geometry import (
    RigidPathChecker, combine_meshes, freeze_scene, matrix, pose_dict)
from topogym.planning.rigid_reference.rrt import connect_search
from topogym.utils.io import write_json_atomic
from .oracle import load_reference


def plan_measured_object_route(observation, release, reference_path, output, *, seed=932, wall_s=180.):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    task,_,scene,meshes,identity=freeze_scene('horseshoe_ring','easy',0,output/'geometry_assets')
    world=observation['privileged']['world']['bodies']
    bodies={name:body_pose(world[name]) for name in meshes}
    pieces=[]
    for name,mesh in meshes.items():
        if name!='target_ring':
            piece=mesh.copy();piece.apply_transform(matrix(*bodies[name]));pieces.append(piece)
    table=trimesh.creation.box(scene.env.world.table.size)
    table.apply_translation(scene.env.world.table.pos)
    table.metadata['components']=[dict(name='declared_table',first_face=0,face_count=len(table.faces))]
    pieces.append(table)
    began=time.monotonic()

    class BoundedChecker(RigidPathChecker):
        def clearance(self, pose):
            if time.monotonic()-began>wall_s:raise TimeoutError('Measured object search exhausted its wall budget')
            result=super().clearance(pose)
            if self.queries%1000==0:
                write_json_atomic(output/'query_progress.json',dict(queries=self.queries,elapsed_s=time.monotonic()-began))
            return result

    checker=BoundedChecker(combine_meshes(pieces),meshes['target_ring'])
    prefix=[body_pose(row) for row in release['poses']]
    start=prefix[-1]
    if not checker.initial_free(start):
        raise ValueError('Contact-release endpoint is not free in the complete surface model')
    reference,_=load_reference(reference_path,task.assembly)
    hp,hr=bodies['horseshoe_right']
    rp,rr=relative_pose(reference[-1]['horseshoe_right'],reference[-1]['target_ring'])
    direction=(hr*reference[-1]['horseshoe_right'][1].inv()).apply([-1.,0.,0.])
    remainder=np.vstack([r.apply(task.placement_vertices[n])+p for n,(p,r) in bodies.items() if n!='target_ring'])
    boundary=float((remainder@direction).max())+.005
    current=bodies['target_ring'][1]
    rotations=[current]+[Rotation.from_euler(axis,angle,degrees=True)*current
        for axis in ('x','y','z') for angle in (-45.,45.)]
    rotations += [hr*rr*Rotation.from_euler('z',angle,degrees=True) for angle in range(0,360,60)]
    goals=[]
    for r in rotations:
        for retreat,dz in ((0.,0.),(.025,0.),(.05,-.04),(.075,-.08)):
            p=hp+hr.apply(rp)+retreat*direction+[0,0,dz]
            if float(((r.apply(task.placement_vertices['target_ring'])+p)@direction).min())<boundary:continue
            if checker.clearance((p,r))>checker.margin+checker.error:goals.append((p,r))
    # A measured hanging assembly need not share the canonical exit side.
    # Add separating goals on every world axis; retain full surface/table
    # checks and the same continuous edge requirements for each route.
    for axis in (*np.eye(3),*-np.eye(3)):
        boundary=float((remainder@axis).max())+.008
        for r in rotations[:7]:
            p=bodies['target_ring'][0].copy()
            gap=boundary-float(((r.apply(task.placement_vertices['target_ring'])+p)@axis).min())
            p+=max(0.,gap)*axis
            if checker.clearance((p,r))>checker.margin+checker.error:goals.append((p,r))
    if not goals:raise ValueError('No object-only separating goal found')
    coordinates=np.vstack([start[0],*[p for p,_ in goals],*[p for p,_ in bodies.values()]])
    low=coordinates.min(axis=0)-[.10,.10,.08];high=coordinates.max(axis=0)+[.10,.10,.08]
    # A ring can be almost flat on the table. Its bounding-sphere radius
    # must not exclude these low poses; full geometry checks the actual
    # orientation against the declared table on every accepted edge.
    low[2]=max(low[2],task.table_height_m+.001)
    rng=np.random.default_rng(seed)
    def sample(rng):return rng.uniform(low,high),Rotation.random(random_state=rng)
    def local(rng,pose):
        return np.clip(pose[0]+rng.normal(0,.015,3),low,high),Rotation.from_rotvec(rng.normal(0,.2,3))*pose[1]
    def progress(value):
        write_json_atomic(output/'search_progress.json',dict(value,queries=checker.queries,elapsed_s=time.monotonic()-began))
    path,search=connect_search(checker,start,goals[0],sample,rng=rng,iterations=10000,step_m=.006,
        goal_candidates=goals,local_sample=local,progress=progress,minimum_step_m=.0001)
    if path is None:
        result=dict(passed=False,search=search,scope='finite search failure is not an impossibility proof')
    else:
        for _ in range(60):
            if len(path)<3:break
            a,b=sorted(rng.choice(len(path),2,replace=False))
            if b>a+1 and checker.edge(path[a],path[b])['passed']:path=path[:a+1]+path[b:]
        edges=[checker.edge(a,b) for a,b in zip(path[:-1],path[1:])]
        result=dict(passed=all(row['passed'] for row in edges),poses=[pose_dict(p) for p in path],
            edges=edges,search=search,identity=identity,observed_state=observation['state'],
            contact_release_prefix=release,contact_release_certified=False,
            robot_ik_verified=False,passive_dynamics_verified=False,task_success=False,
            scope='fixed measured remainder; continuous surface-clearance bounds after contact release; no robot or physical qualification')
    result.update(queries=checker.queries,elapsed_s=time.monotonic()-began)
    write_json_atomic(output/'object_route.json',result)
    return result
