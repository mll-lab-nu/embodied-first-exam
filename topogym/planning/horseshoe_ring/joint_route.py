"""Sampled joint-space transport of a held ring with explicit contact scope."""
import time
from dataclasses import replace

import numpy as np
from scipy.spatial.transform import Rotation

from .ring_route import HeldRingPath
from topogym.planning.buzz_wire_3d.kinematics import distance
from topogym.planning.rigid_reference.geometry import pose_dict
from topogym.utils.io import write_json_atomic


def plan_free_ring_transport(planner, observation, goals, *, iterations=5000, passive_contact_names=()):
    """Search continuous arm configurations, then check dense Cartesian replay.

    Joint-space exploration avoids forcing one fixed world orientation across
    wrist singularities. No simulated robot or object state is modified.
    """
    checker=HeldRingPath(planner,observation,passive_contact_names=passive_contact_names)
    ik=planner.checker;group=planner.robot.groups['left'];ids=planner.robot._q_indices['left'][:6]
    hand=planner.robot.entity.get_link(group.hand_link).idx_local
    limits=np.asarray(group.arm_limits_rad)
    prefix=checker.contact_escape() if passive_contact_names else [checker.start]
    start=checker.seed.copy()
    if len(prefix)>1:start=np.asarray(checker.check(prefix[-1])['qpos'])
    search_seed=int(getattr(planner,'withdrawal_parameters',{}).get('search_seed',922))
    rng=np.random.default_rng(search_seed);phase='search'
    op,orr=checker.offset;queries=0;cache={};began=time.monotonic()
    passive_loops={}
    ring_loop=planner.task.assembly.loops['target_ring']
    def world_loop(loop,p,r):
        return replace(loop,center=p+r.apply(loop.center-planner.task.body_origins[loop.body]),rotation=r*loop.rotation)
    for name,loop in planner.task.assembly.loops.items():
        if loop.body in passive_contact_names:
            passive_loops[name]=world_loop(loop,*checker.bodies[loop.body])
    initial_ring_loop=world_loop(ring_loop,*checker.start)
    initial_linkage={n:initial_ring_loop.linking(loop) for n,loop in passive_loops.items()}
    def pose(q):
        fk=ik.fk.solve(q)
        p=np.asarray(fk['position_world_m']).reshape(-1,3)[hand]
        r=Rotation.from_quat(np.asarray(fk['orientation_wxyz']).reshape(-1,4)[hand,[1,2,3,0]])
        tp=p+r.apply(group.tcp_position_in_hand_m)
        tr=r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz,-1))
        br=tr*orr.inv()
        return tp-br.apply(op),br
    def full(arm):
        q=start.copy();q[ids]=arm;return q
    def valid(arm):
        nonlocal queries
        queries+=1
        if time.monotonic()-began>600:raise TimeoutError('Free-ring transport exceeded 600 s')
        if queries%2000==0:
            write_json_atomic(planner.directory/'free_ring_query_progress.json',
                dict(phase=phase,queries=queries,elapsed_s=time.monotonic()-began))
        key=tuple(np.round(arm,10))
        if key in cache:return cache[key]
        q=full(arm);p,r=pose(q)
        if (r.apply(checker.vertices)+p)[:,2].min()<ik.table_height+.0005:
            cache[key]=False;return False
        checker.set_ring((p,r));ring=ik.bodies['target_ring'][1]
        margin=.00005 if passive_contact_names else .0005
        if min(distance(ring,m) for n,(_,m) in ik.bodies.items()
               if n!='target_ring' and n not in passive_contact_names)<margin:
            cache[key]=False;return False
        # A released body may move on contact, but a candidate should not
        # depend on passing its currently observed closed eye through the
        # ring. Preserve the initial linkage in this conservative snapshot.
        if passive_loops:
            moving_loop=world_loop(ring_loop,p,r)
            if any(moving_loop.linking(loop)!=initial_linkage[n] for n,loop in passive_loops.items()):
                cache[key]=False;return False
        checked=ik.check(q,contacts={'left':'target_ring','right':('horseshoe_left','horseshoe_right')})
        cache[key]=checked['passed'];return cache[key]
    def edge(a,b,step=.01):
        pa,pb=pose(full(a)),pose(full(b))
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/step)),int(np.ceil(checker.motion(pa,pb)/.00075)))
        return all(valid(a+u*(b-a)) for u in np.linspace(0,1,count+1)[1:])
    roots=[]
    for goal in goals:
        checked=checker.check(goal)
        if checked['passed']:
            q=np.asarray(checked['qpos']);arm=q[ids]
            if valid(arm) and all(np.linalg.norm(arm-old)>.1 for old in roots):roots.append(arm)
    if not roots or not valid(start[ids]):raise ValueError('No valid free-ring joint search endpoints')
    trees=[([start[ids].copy()],[-1]),(roots,[-1]*len(roots))]
    def extend(tree,target):
        nodes,parents=tree;i=int(np.argmin(np.linalg.norm(np.asarray(nodes)-target,axis=1)))
        delta=target-nodes[i];length=np.linalg.norm(delta)
        new=nodes[i]+delta*min(1.,.18/max(length,1e-12))
        if not edge(nodes[i],new):return None,False
        nodes.append(new);parents.append(i);return len(nodes)-1,length<=.18
    def ancestry(tree,i):
        result=[]
        while i>=0:result.append(tree[0][i]);i=tree[1][i]
        return result[::-1]
    path=None
    for index in range(iterations):
        if index%100==0:
            write_json_atomic(planner.directory/'free_ring_search_progress.json',
                dict(iteration=index,nodes=[len(t[0]) for t in trees],queries=queries,elapsed_s=time.monotonic()-began))
        side=index%2;tree,other=trees[side],trees[1-side]
        target=(other[0][rng.integers(len(other[0]))] if rng.random()<.25
                else rng.uniform(limits[:,0]+.015,limits[:,1]-.015))
        a,_=extend(tree,target)
        if a is None:continue
        for _ in range(80):
            b,reached=extend(other,tree[0][a])
            if b is None:break
            if reached:
                path=ancestry(tree,a)+ancestry(other,b)[-2::-1]
                if side:path.reverse()
                break
        if path is not None:break
    if path is None:raise ValueError('No free-ring joint route within the finite budget')
    phase='shortcut'
    for _ in range(30):
        if len(path)<3:break
        a,b=sorted(rng.choice(len(path),2,replace=False))
        if b>a+1 and edge(path[a],path[b]):path=path[:a+1]+path[b:]
    poses=list(prefix)
    for a,b in zip(path[:-1],path[1:]):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/.012)))
        poses.extend(pose(full(a+u*(b-a))) for u in np.linspace(0,1,count+1)[1:])
    phase='ordered_replay'
    write_json_atomic(planner.directory/'free_ring_query_progress.json',
        dict(phase=phase,queries=queries,poses=len(poses),elapsed_s=time.monotonic()-began))
    audit=checker.ordered_audit(poses,release_prefix_edges=len(prefix)-1)
    if not audit['passed']:raise ValueError(f'Free-ring Cartesian replay failed: {audit}')
    result=dict(passed=True,poses=[pose_dict(p) for p in poses],ordered_audit=audit,
        joint_knots=[full(a).tolist() for a in path],queries=queries,
        release_prefix_edges=len(prefix)-1,passive_contact_names=list(passive_contact_names),
        static_passive_loop_linkages_preserved_at_joint_checks=True,static_passive_loop_linkages=initial_linkage,
        scope='sampled native joint search and Cartesian replay; allowed passive contact response requires physical execution')
    write_json_atomic(planner.directory/'free_ring_transport_plan.json',result)
    return result
