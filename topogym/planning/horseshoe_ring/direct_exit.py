"""Check short exits from a measured contact state with every body present."""
import numpy as np

from .ring_route import HeldRingPath
from topogym.planning.rigid_reference.geometry import pose_dict
from topogym.utils.io import write_json_atomic


def plan_direct_exit(planner, observation):
    """Try separating planes in world and measured object directions.

    All four remainder bodies are collision obstacles. The measured initial
    contact neighbourhood keeps HeldRingPath's existing numerical allowance;
    subsequent motion must have positive clearance from every body.
    """
    checker=HeldRingPath(planner,observation)
    measured=checker.bodies.copy()
    try:
        escape=checker.contact_escape()
    except ValueError as error:
        result=dict(passed=False,attempts=[],reason='local_contact_release',error=str(error))
        write_json_atomic(planner.directory/'direct_exit_plan.json',result)
        return result
    release_edges=len(escape)-1
    p,r=escape[-1]
    remainder=np.vstack([br.apply(planner.task.placement_vertices[n])+bp
                        for n,(bp,br) in measured.items() if n!='target_ring'])
    ring=r.apply(checker.vertices)+p
    axes=[*np.eye(3),*r.as_matrix().T,*measured['horseshoe_right'][1].as_matrix().T]
    directions=[]
    for axis in axes:
        for sign in (1.,-1.):
            d=sign*axis
            if all(np.linalg.norm(d-old)>.01 for old in directions):directions.append(d)
    candidates=[]
    for d in directions:
        shift=float((remainder@d).max()-(ring@d).min())+.005
        if shift<=0:
            result=dict(passed=True,separated=release_edges==0,poses=[pose_dict(p) for p in escape],
                        direction=d.tolist(),separating_plane_margin_m=.005,
                        release_prefix_edges=release_edges,
                        ordered_audit=checker.ordered_audit(escape,release_prefix_edges=release_edges))
            write_json_atomic(planner.directory/'direct_exit_plan.json',result);return result
        candidates.append((shift,d))
    attempts=[]
    for shift,d in sorted(candidates,key=lambda item:item[0]):
        goal=(p+shift*d,r)
        endpoint=checker.check(goal)
        if not endpoint['passed']:
            attempts.append(dict(translation_m=shift,direction=d.tolist(),endpoint=endpoint));continue
        audit=checker.ordered_audit([*escape,goal],release_prefix_edges=release_edges)
        if not audit['passed']:
            attempts.append(dict(translation_m=shift,direction=d.tolist(),audit=audit));continue
        result=dict(passed=True,separated=False,poses=[pose_dict(v) for v in [*escape,goal]],
            release_prefix_edges=release_edges,
            direction=d.tolist(),separating_plane_margin_m=.005,ordered_audit=audit,attempts=attempts,
            observed_bodies={n:pose_dict(p) for n,p in measured.items()},
            scope='sampled all-body native IK/collision exit; measured initial contact and dynamics require physical validation')
        write_json_atomic(planner.directory/'direct_exit_plan.json',result);return result
    result=dict(passed=False,attempts=attempts)
    write_json_atomic(planner.directory/'direct_exit_plan.json',result)
    return result
