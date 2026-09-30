"""Read-only final placement candidates for an already extracted ring."""
import numpy as np
from scipy.spatial.transform import Rotation

from .ring_route import HeldRingPath
from topogym.planning.buzz_wire_3d.kinematics import distance
from topogym.planning.rigid_reference.feedback import relative_pose, tcp_pose
from topogym.planning.rigid_reference.geometry import interpolate, pose_dict
from topogym.utils.io import write_json_atomic


def place_ring(planner, observation):
    checker=HeldRingPath(planner,observation)
    region=planner.task.goal_region
    start=checker.start
    # The placement rule leaves ring attitude free. A downward-facing tool
    # can carry the ring by its upper arc with useful table/wrist clearance.
    # Include these poses explicitly instead of only flipping its exit pose.
    rotations=[]
    for yaw in (0.,45.,-45.,90.,-90.,180.):
        down=np.array([0.,0.,-1.]);a=np.deg2rad(yaw)
        jaw=np.array([np.sin(a),np.cos(a),0.])
        tcp_rotation=Rotation.from_matrix(np.column_stack([down,jaw,np.cross(down,jaw)]))
        rotations.append(tcp_rotation*checker.offset[1].inv())
    rotations.append(start[1])
    for yaw in (0.,90.,-90.,180.):
        for axis in ('x','y'):
            rotations.append(Rotation.from_euler('z',yaw,degrees=True)*
                             Rotation.from_euler(axis,180.,degrees=True)*start[1])
    remainder=np.vstack([r.apply(planner.task.placement_vertices[n])+p
        for n,(p,r) in checker.bodies.items() if n!='target_ring'])
    outside_x=min(float(remainder[:,0].min())-checker.radius-.04,-.44)
    attempts=[];free_goals=[]
    for rotation in rotations:
        for height in (.12,.15,.09):
            goal=(np.r_[region.center_xy_m,region.table_height_m+height],rotation)
            if not region.contains(rotation.apply(checker.vertices)+goal[0]):continue
            checked=checker.check(goal)
            if not checked['passed']:
                attempts.append(dict(goal=pose_dict(goal),endpoint=checked));continue
            free_goals.append(goal)
            outside=(np.array([outside_x,start[0][1],start[0][2]]),start[1])
            low=(np.array([outside_x,start[0][1],region.table_height_m+.22]),start[1])
            front=(np.array([outside_x,goal[0][1],low[0][2]]),start[1])
            turned=(front[0],rotation)
            for path in ([start,goal],[start,outside,low,front,turned,goal]):
                try:audit=checker.ordered_audit(path)
                except TimeoutError as error:
                    write_json_atomic(planner.directory/'ring_placement_plan.json',
                        dict(passed=False,attempts=attempts,error=str(error)))
                    raise
                if not audit['passed']:
                    attempts.append(dict(goal=pose_dict(goal),audit=audit));continue
                result=dict(passed=True,poses=[pose_dict(p) for p in path],ordered_audit=audit,
                            attempts=attempts,scope='sampled held-ring route into the fixed goal; actual goal remains unverified')
                write_json_atomic(planner.directory/'ring_placement_plan.json',result)
                return result
    if free_goals:
        from .joint_route import plan_free_ring_transport
        try:
            result=plan_free_ring_transport(planner,observation,free_goals)
            result.update(attempts=attempts,method='joint_search_then_dense_cartesian_replay')
            write_json_atomic(planner.directory/'ring_placement_plan.json',result)
            return result
        except (ValueError,TimeoutError) as error:attempts.append(dict(joint_search_error=str(error)))
    write_json_atomic(planner.directory/'ring_placement_plan.json',dict(passed=False,attempts=attempts))
    raise ValueError('No checked fixed-region ring placement route')


def place_remainder(planner, observation):
    bodies,seed=planner.observed(observation)
    checker=planner.checker;region=planner.task.goal_region
    first=bodies['horseshoe_right']
    offset=relative_pose(first,tcp_pose(observation['robot']['right']))
    names=planner.task.placement_remainder
    n=np.asarray(region.separator_normal_xy)
    attempts=[]
    for yaw in (-30.,-45.,-15.,0.,30.):
        turn=Rotation.from_euler('z',yaw,degrees=True)
        for dz in (-.03,0.,-.06):
            for dx in (0.,.05,-.05):
                shifted={name:(first[0]+[dx,0,dz]+turn.apply(bodies[name][0]-first[0]),
                               turn*bodies[name][1]) for name in names}
                cloud=np.vstack([r.apply(planner.task.placement_vertices[name])+p
                                 for name,(p,r) in shifted.items()])
                separation=max(0.,float((cloud[:,:2]@n).max())-region.separator_offset_m+.03)
                shift=np.r_[-separation*n,0.]
                target=(shifted['horseshoe_right'][0]+shift,shifted['horseshoe_right'][1])
                q=seed.copy();rows=[];failure=None
                for u in np.linspace(0,1,101):
                    p,r=interpolate(first,target,u);common=r*first[1].inv()
                    world=dict(bodies,**{name:(p+common.apply(bodies[name][0]-first[0]),
                                                   common*bodies[name][1]) for name in names})
                    if any((br.apply(planner.task.placement_vertices[name])+bp)[:,2].min()<checker.table_height+.0005
                           for name,(bp,br) in world.items()):
                        failure=dict(reason='table',fraction=float(u));break
                    try:
                        previous=q.copy()
                        q=checker.solve('right',(p+r.apply(offset[0]),r*offset[1]),q)
                        checked=checker.check(q,body_poses=world,
                            contacts={'left':'target_ring','right':('horseshoe_left','horseshoe_right')})
                        ring=checker.bodies['target_ring'][1]
                        gap=min(distance(ring,checker.bodies[name][1]) for name in names)
                        if not checked['passed'] or gap<.0005 or np.abs(q-previous).max()>.15:
                            failure=dict(fraction=float(u),check=checked,ring_clearance_m=gap);break
                    except ValueError as error:
                        failure=dict(fraction=float(u),error=str(error));break
                    rows.append(dict(fraction=float(u),right_pose=pose_dict((p,r)),qpos=q.tolist()))
                if failure:
                    attempts.append(dict(yaw_deg=yaw,dz=dz,dx=dx,failure=failure));continue
                if not all(region.system_side(br.apply(planner.task.placement_vertices[name])+bp)
                           for name,(bp,br) in world.items() if name in names):
                    raise ValueError('Predicted remainder does not clear the fixed separator')
                result=dict(passed=True,poses=[row['right_pose'] for row in rows[::10]],
                            joint_samples=rows,attempts=attempts,
                            scope='sampled rigid support transport; upper shoe and chains remain passive in execution')
                write_json_atomic(planner.directory/'remainder_placement_plan.json',result)
                return result
    write_json_atomic(planner.directory/'remainder_placement_plan.json',dict(passed=False,attempts=attempts))
    raise ValueError('No checked supported-assembly route behind the fixed separator')
