"""Checked common tilts while both shoes are still held separately.

Robot screening transports the observed assembly rigidly. The ring and
chains are not constrained during execution; their gravity response needs
independent physical validation.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.rigid_reference.feedback import relative_pose, tcp_pose
from topogym.planning.rigid_reference.geometry import pose_dict
from topogym.utils.io import write_json_atomic


def plan_folded_tilt(planner, observation, angle_deg, *, translation_m=(0.,0.,0.), roll_deg=0., yaw_deg=0.):
    angle_deg=float(angle_deg);roll_deg=float(roll_deg);yaw_deg=float(yaw_deg);translation=np.asarray(translation_m,dtype=float)
    if (not np.isfinite([angle_deg,roll_deg,yaw_deg]).all() or not -150<=angle_deg<=150
            or not -180<=roll_deg<=180 or not -180<=yaw_deg<=180 or (angle_deg==0 and roll_deg==0 and yaw_deg==0)
            or translation.shape!=(3,) or not np.isfinite(translation).all()):
        raise ValueError('Invalid folded tilt')
    hands=observation['privileged']['world']['grasp']['hands']
    if any(not hands[s]['binding'] or hands[s]['binding']['target'][0]!='horseshoe_'+s for s in ('left','right')):
        raise ValueError('Folded settling requires a separate shoe held by each arm')
    bodies,q=planner.observed(observation)
    offsets={s:relative_pose(bodies['horseshoe_'+s],tcp_pose(observation['robot'][s])) for s in ('left','right')}
    center=np.mean([bodies['horseshoe_'+s][0] for s in offsets],axis=0)
    direction=(bodies['horseshoe_right'][1]*planner.reference[-1]['horseshoe_right'][1].inv()).apply([-1.,0.,0.])
    axis=np.cross(direction,[0.,0.,-1.]);length=np.linalg.norm(axis)
    if length<1e-8:raise ValueError('Folded exit direction is already vertical')
    axis/=length
    rows=[];previous=q.copy();margins={s:np.full(6,np.inf) for s in offsets}
    waypoints=[(u*translation,Rotation.identity()) for u in np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(translation)/.001))+1))]
    def tilted(u):
        return Rotation.from_euler('z',u*yaw_deg,degrees=True)*Rotation.from_rotvec(axis*np.deg2rad(u*angle_deg))
    waypoints += [(translation,tilted(u)) for u in np.linspace(0,1,int(np.ceil(max(abs(angle_deg),abs(yaw_deg))/.5))+1)[1:]]
    pitched=tilted(1.)
    waypoints += [(translation,pitched*Rotation.from_rotvec(direction*np.deg2rad(a)))
                  for a in np.linspace(0,roll_deg,int(np.ceil(abs(roll_deg)/.5))+1)[1:]]
    for index,(shift,turn) in enumerate(waypoints):
        world={n:(center+shift+turn.apply(p-center),turn*r) for n,(p,r) in bodies.items()}
        if min(float((r.apply(planner.task.placement_vertices[n])+p)[:,2].min()) for n,(p,r) in world.items())<planner.checker.table_height+.00005:
            raise ValueError(f'Rigid screening assembly reaches the table at sample {index}')
        for side,(op,orr) in offsets.items():
            p,r=world['horseshoe_'+side];q=planner.checker.solve(side,(p+r.apply(op),r*orr),q)
        checked=planner.checker.check(q,contacts={s:'horseshoe_'+s for s in offsets},body_poses=world)
        if np.abs(q-previous).max()>.15:raise ValueError(f'Tilt joint branch change at sample {index}')
        if not checked['passed']:raise ValueError(f'Tilt collision at sample {index}: {checked}')
        for side in offsets:
            arm=q[planner.robot._q_indices[side][:6]];limits=np.asarray(planner.robot.groups[side].arm_limits_rad)
            margins[side]=np.minimum(margins[side],np.minimum(arm-limits[:,0],limits[:,1]-arm))
        rows.append(dict(shoes={s:pose_dict(world['horseshoe_'+s]) for s in offsets},qpos=q.tolist()))
        previous=q.copy()
    result=dict(passed=True,angle_deg=angle_deg,roll_deg=roll_deg,yaw_deg=yaw_deg,axis_world=axis.tolist(),translation_m=translation.tolist(),
        poses=rows,minimum_joint_margins_rad={s:v.tolist() for s,v in margins.items()},
        observed_state=observation['state'],scope='sampled native bimanual IK/collisions; rigid assembly screening only; passive gravity response unverified')
    write_json_atomic(planner.directory/'folded_tilt_plan.json',result)
    return result


def folded_ring_metric(planner, observation):
    bodies,_=planner.observed(observation)
    hp,hr=bodies['horseshoe_right'];rp,rr=bodies['target_ring']
    reference=planner.reference[planner.fold_end_index]
    direction=(hr*reference['horseshoe_right'][1].inv()).apply([-1.,0.,0.])
    expected=float((reference['target_ring'][0]-reference['horseshoe_right'][0])@np.array([-1.,0.,0.]))
    actual=float((rp-hp)@direction)
    observed_relative=relative_pose(bodies['horseshoe_right'],bodies['target_ring'])
    expected_relative=relative_pose(reference['horseshoe_right'],reference['target_ring'])
    ring=rr.apply(planner.task.placement_vertices['target_ring'])+rp
    remainder=np.vstack([r.apply(planner.task.placement_vertices[n])+p for n,(p,r) in bodies.items() if n!='target_ring'])
    axes=[direction,*np.eye(3),*-np.eye(3)]
    separation=max(float((ring@axis).min()-(remainder@axis).max()) for axis in axes)
    return dict(longitudinal_position_m=actual,reference_longitudinal_position_m=expected,
                longitudinal_error_m=abs(actual-expected),maximum_separating_gap_m=separation,
                reference_position_error_m=float(np.linalg.norm(observed_relative[0]-expected_relative[0])),
                reference_rotation_error_rad=float((observed_relative[1]*expected_relative[1].inv()).magnitude()))
