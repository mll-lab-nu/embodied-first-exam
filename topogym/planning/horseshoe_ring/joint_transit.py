"""Sampled collision-checked free-arm transit with the other arm fixed."""
import numpy as np

# oraclefix2: the search budget counts collision queries instead of wall-clock seconds, so a plan (and the live oracle
# that depends on it) no longer changes with the host's load; the seeded search is then fully reproducible. `seconds`
# keeps its meaning as the budget of an idle host: one ContactHorseshoeIK query costs 10.8 ms of CPU on a lab core
# (92 queries/s at load 37, lab oraclefix2/exp/C1; 60 queries/s were reached under the night's heavier load, when
# ring_grasp's 20 s transits failed and the hard oracle's ring grasp with them, oraclefix2/exp/X7).
QUERIES_PER_SECOND = 100.


def plan_transit(planner, start, goal, bodies, *, side='left', seconds=30., seed=931, direct_only=False):
    if not isinstance(direct_only,bool):raise ValueError('Direct transit option must be boolean')
    indices=planner.robot._q_indices[side][:6]
    other='right' if side=='left' else 'left'
    contacts={other:('horseshoe_left','horseshoe_right')}
    limits=np.asarray(planner.robot.groups[side].arm_limits_rad)
    start=np.asarray(start).copy();goal=np.asarray(goal).copy()
    fixed=np.ones(len(start),dtype=bool);fixed[indices]=False
    if not np.allclose(start[fixed],goal[fixed],atol=1e-12,rtol=0):
        raise ValueError('Free-arm transit must keep all other joints fixed')
    queries=0;budget=int(round(float(seconds)*QUERIES_PER_SECOND))

    def valid(q):
        nonlocal queries
        queries+=1
        return (np.all(q[indices]>=limits[:,0]) and np.all(q[indices]<=limits[:,1]) and
                planner.checker.check(q,body_poses=bodies,contacts=contacts)['passed'])

    def edge(a,b):
        count=max(1,int(np.ceil(np.max(np.abs(a[indices]-b[indices]))/.015)))
        return all(valid(a+(b-a)*u) for u in np.linspace(0,1,count+1)[1:])

    if not valid(start) or not valid(goal):raise ValueError('Free transit endpoint collision')
    if edge(start,goal):return dict(waypoints=[start.tolist(),goal.tolist()],queries=queries,method='direct')
    if direct_only:raise ValueError('No checked direct free-arm transit')
    rng=np.random.default_rng(seed)
    trees=[([start],[-1]),([goal],[-1])]

    def extend(tree,target):
        nodes,parents=tree
        near=int(np.argmin([np.linalg.norm(q[indices]-target[indices]) for q in nodes]))
        delta=target-nodes[near];scale=min(1.,.15/max(float(np.max(np.abs(delta[indices]))),1e-12))
        candidate=nodes[near]+scale*delta
        if not edge(nodes[near],candidate):return None,False
        nodes.append(candidate);parents.append(near)
        return len(nodes)-1,scale==1.

    def branch(tree,index):
        nodes,parents=tree;result=[]
        while index>=0:result.append(nodes[index]);index=parents[index]
        return result[::-1]

    for iteration in range(5000):
        if queries>=budget:break
        active=iteration%2;first,second=trees[active],trees[1-active]
        target=start.copy()
        if rng.random()<.25:target=second[0][rng.integers(len(second[0]))].copy()
        else:target[indices]=rng.uniform(limits[:,0],limits[:,1])
        index,_=extend(first,target)
        if index is None:continue
        for _ in range(100):
            opposite,reached=extend(second,first[0][index])
            if opposite is None:break
            if reached:
                a,b=branch(first,index),branch(second,opposite)
                path=a+b[-2::-1]
                if active:path=path[::-1]
                # Shortcut only after checking the entire replacement edge.
                simplified=[path[0]];i=0
                while i<len(path)-1:
                    j=len(path)-1
                    while j>i+1 and not edge(path[i],path[j]):j-=1
                    simplified.append(path[j]);i=j
                return dict(waypoints=[q.tolist() for q in simplified],queries=queries,
                    method='bidirectional_rrt',iterations=iteration+1,
                    scope='joint samples at at most 0.015 rad; physical execution and audit required')
            if queries>=budget:break
    raise ValueError(f'No free-arm transit within budget; queries={queries}')
