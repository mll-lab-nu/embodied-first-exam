"""Independent physical pickup qualification, using current public step actions."""
import numpy as np
import xml.etree.ElementTree as ET
from scipy.spatial.transform import Rotation, Slerp
from topogym.utils.arrays import to_numpy
from topogym.solvers.genesis_kinematics import GenesisIKSolver, GenesisFKSolver


def transform(position, quaternion):
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_quat(np.asarray(quaternion)[[1,2,3,0]]).as_matrix()
    matrix[:3, 3] = position
    return matrix


class RobotObstacleQuery:
    """Use the actual loaded collision meshes; do not move the live robot."""
    def __init__(self, env, tool):
        import trimesh
        self.fixed = trimesh.collision.CollisionManager()
        self.fixed_meshes = {}
        self.robot = trimesh.collision.CollisionManager()
        self.arms = {side: trimesh.collision.CollisionManager() for side in ('left', 'right')}
        self.arm_links = {side: [] for side in self.arms}
        self.link_meshes = {}
        entity = env._robot.entity
        self.fk = GenesisFKSolver(entity)
        for name, body in env._world.entities.items():
            if name in {'robot', tool}:
                continue
            geoms = getattr(body, 'geoms', ())
            for geom in geoms:
                mesh = trimesh.Trimesh(to_numpy(geom.get_verts()), geom.mesh.faces, process=False)
                key = f'{name}/{geom.idx}'
                self.fixed.add_object(key, mesh)
                self.fixed_meshes[key] = mesh
        for link in entity.links:
            # The fixed mounting links intentionally rest on the lab mount.
            if link.idx_local <= 1 or link.name in {'left/base_link', 'right/base_link'} or not link.geoms:
                continue
            world_to_link = np.linalg.inv(transform(to_numpy(link.get_pos()), to_numpy(link.get_quat())))
            pieces = []
            for geom in link.geoms:
                mesh = trimesh.Trimesh(to_numpy(geom.get_verts()), geom.mesh.faces, process=False)
                mesh.apply_transform(world_to_link)
                pieces.append(mesh)
            mesh = trimesh.util.concatenate(pieces)
            self.robot.add_object(link.name, mesh)
            self.link_meshes[link.name] = link.idx_local
            side = link.name.split('/')[0]
            if side in self.arms:
                self.arms[side].add_object(link.name, mesh)
                self.arm_links[side].append(link.name)

    def clearance(self, qpos):
        pose = self.fk.solve(qpos)
        pos = pose['position_world_m'].reshape(-1,3)
        quat = pose['orientation_wxyz'].reshape(-1,4)
        for name, index in self.link_meshes.items():
            matrix = transform(pos[index], quat[index])
            self.robot.set_transform(name, matrix)
            side = name.split('/')[0]
            if side in self.arms:
                self.arms[side].set_transform(name, matrix)
        distance, names = self.robot.min_distance_other(self.fixed,return_names=True)
        distance = float(distance)
        self.last_nearest = dict(kind='fixture',links=list(names),distance_m=distance)
        if all(self.arm_links.values()):
            cross,names = self.arms['left'].min_distance_other(self.arms['right'],return_names=True)
            if cross < distance:
                distance = float(cross)
                self.last_nearest = dict(kind='inter_arm',links=list(names),distance_m=distance)
        return distance


def grip_target(env):
    task = env._task
    world = env.privileged.get('world')['bodies']
    if task.task_id == 'buzz_wire_3d':
        tool = 'wand'
        a,b,_,_ = task.layout.tool_capsules()[-1]
        local = (a+b)/2
    elif task.task_id == 'lock_picking':
        tool = 'lock_key'
        local = np.array([-task.layout.grip_offset,0,0])
    else:
        raise ValueError('Pickup diagnostic only supports Buzz and Lock')
    body = world[tool]
    r = Rotation.from_quat(np.asarray(body['quaternion_wxyz'])[[1,2,3,0]])
    return tool, np.asarray(body['position_m'])+r.apply(local)


def plan_pickup(env):
    robot = env._robot
    group = robot.groups['arm']
    qs = robot._q_indices['arm'][:len(group.arm_joints)]
    dofs = robot._indices['arm'][:len(group.arm_joints)]
    home = robot.observe()['arm']
    start_p = np.asarray(home['tcp_position_world_m'])
    start_r = Rotation.from_quat(np.asarray(home['tcp_orientation_wxyz'])[[1,2,3,0]])
    tool, target = grip_target(env)
    tool_pose = env.privileged.get('world')['bodies'][tool]
    handle_axis = Rotation.from_quat(np.asarray(tool_pose['quaternion_wxyz'])[[1,2,3,0]]).apply([1,0,0])
    # The original-scale Robotiq closes along hand Y. Pinch across the handle,
    # rather than choosing an IK-valid approach along the length of the key.
    home_closing = start_r.apply([0,1,0])
    yaw0 = np.degrees(np.arctan2(handle_axis[1],handle_axis[0])
                      + np.pi/2 - np.arctan2(home_closing[1],home_closing[0]))
    yaws = [float((yaw0+offset+180)%360-180) for offset in (0,180)]
    # Retain exact cardinal paths for the initial Buzz and Lock configurations,
    # while also handling the rotated handle at Buzz's terminal support.
    yaws = [round(y/90)*90 if abs(y/90-round(y/90)) < 1e-6 else y for y in yaws]
    query = RobotObstacleQuery(env, tool)
    solver = GenesisIKSolver(robot.entity)
    q_home = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    clearance_home = query.clearance(q_home)
    if clearance_home < .0005:
        raise AssertionError(f'Robot home collision clearance {clearance_home}')
    failures = []
    for yaw in yaws:
        grasp_r = Rotation.from_euler('z',yaw,degrees=True)*start_r
        closing_axis = grasp_r.apply([0,1,0])
        if abs(np.dot(closing_axis,handle_axis)) > .2:
            continue
        # Stay above all fixtures while translating between home and the tool.
        cruise_z = max(start_p[2]+.22, target[2]+.25)
        points = [(start_p,start_r), (np.array([*start_p[:2],cruise_z]),start_r),
                  (np.array([*target[:2],cruise_z]),grasp_r), (target,grasp_r)]
        q = q_home.copy(); commands = []; minimum = clearance_home
        minimum_margin = float('inf')
        try:
            for (p0,r0),(p1,r1) in zip(points[:-1],points[1:]):
                count = max(20, int(np.ceil(np.linalg.norm(p1-p0)/.006)))
                rotations = Slerp([0,1], Rotation.concatenate([r0,r1]))
                for alpha in np.linspace(0,1,count+1)[1:]:
                    p = p0+(p1-p0)*alpha
                    r = rotations(alpha)
                    hand = r*Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1,2,3,0]]).inv()
                    q = solver.solve_checked(link_name=group.hand_link,
                        position_world_m=p-hand.apply(group.tcp_position_in_hand_m),
                        orientation_wxyz=hand.as_quat()[[3,0,1,2]],
                        joint_dof_indices=dofs,initial_qpos=q,max_solver_iterations=150)
                    margin = np.min(np.minimum(q[qs]-np.asarray(group.arm_limits_rad)[:,0],
                                                np.asarray(group.arm_limits_rad)[:,1]-q[qs]))
                    if margin < .03:
                        raise AssertionError(f'Joint limit margin {margin}')
                    minimum_margin = min(minimum_margin, float(margin))
                    gap = query.clearance(q)
                    if gap < .0005:
                        raise AssertionError(f'Robot/fixture clearance {gap} at tcp {p.tolist()}')
                    minimum = min(minimum,gap)
                    commands.append({'arm':{'joint_position_rad':q[qs].tolist(),group.gripper_field:0.}})
            # Lift along the vertical initial wire/above the key cradle.
            lift = []
            for dz in np.linspace(0,.06,41)[1:]:
                hand = grasp_r*Rotation.from_quat(np.asarray(group.tcp_orientation_in_hand_wxyz)[[1,2,3,0]]).inv()
                q = solver.solve_checked(link_name=group.hand_link,
                    position_world_m=target+[0,0,dz]-hand.apply(group.tcp_position_in_hand_m),
                    orientation_wxyz=hand.as_quat()[[3,0,1,2]],joint_dof_indices=dofs,
                    initial_qpos=q,max_solver_iterations=150)
                gap = query.clearance(q)
                if gap < .0005:
                    raise AssertionError(f'Lift fixture clearance {gap}')
                minimum = min(minimum, gap)
                margin = np.min(np.minimum(q[qs]-np.asarray(group.arm_limits_rad)[:,0],
                                            np.asarray(group.arm_limits_rad)[:,1]-q[qs]))
                if margin < .03:
                    raise AssertionError(f'Lift joint limit margin {margin}')
                minimum_margin = min(minimum_margin, float(margin))
                lift.append({'arm':{'joint_position_rad':q[qs].tolist(),group.gripper_field:.78}})
            return dict(tool=tool, target=target.tolist(), yaw_deg=yaw,
                        handle_axis_world=handle_axis.tolist(),closing_axis_world=closing_axis.tolist(),
                        minimum_joint_limit_margin_rad=minimum_margin,
                        minimum_fixture_clearance_m=minimum,approach=commands,lift=lift,
                        excluded_from_static_collision=tool,
                        scope='open-gripper robot collision meshes vs fixtures; actual closing and tool contacts require the pickup probe')
        except (ValueError,AssertionError) as error:
            failures.append(dict(yaw_deg=yaw,error=str(error)))
    raise AssertionError(f'No pickup path qualified: {failures}')


def schedule_joint_commands(commands, interval_s, max_skip=3):
    """Subdivide large IK increments before selecting speed-bounded commands."""
    # Retain the checked path, avoiding unnecessarily slow dense IK samples.
    # Arc length in the joint infinity norm bounds every commanded joint.
    if len(commands) < 2:
        return commands
    cap = 1.2*interval_s
    dense = [commands[0]]
    for command in commands[1:]:
        previous = np.asarray(dense[-1]['arm']['joint_position_rad'])
        target = np.asarray(command['arm']['joint_position_rad'])
        count = max(1, int(np.ceil(np.max(abs(target-previous))/cap)))
        for alpha in np.linspace(0,1,count+1)[1:]:
            dense.append({'arm': {**command['arm'],
                'joint_position_rad': (previous+alpha*(target-previous)).tolist()}})
    commands = dense
    q = np.asarray([c['arm']['joint_position_rad'] for c in commands])
    arc = np.r_[0.,np.cumsum(np.max(abs(np.diff(q,axis=0)),axis=1))]
    indices = [0]
    while indices[-1] < len(commands)-1:
        index = min(len(commands)-1,int(np.searchsorted(arc,arc[indices[-1]]+cap,side='right')-1))
        indices.append(max(indices[-1]+1,min(index,indices[-1]+max_skip)))
    result = [commands[i] for i in indices]
    velocity = np.max(abs(np.diff(np.asarray([c['arm']['joint_position_rad'] for c in result]),axis=0)),initial=0)/interval_s
    assert velocity <= 1.2+1e-8
    return result


def execute_pickup(env, evidence, plan, *, release=False):
    """Physically pick up; the separate terminal probe also returns/releases."""
    query = RobotObstacleQuery(env, plan['tool'])
    group = env._robot.groups['arm']
    indices = env._robot._q_indices['arm'][:len(group.arm_joints)]
    def scheduled(commands, max_skip=3):
        result = schedule_joint_commands(commands,
            env.config.physics_dt_s*env.config.control_decimation, max_skip)
        q = to_numpy(env._robot.entity.get_qpos()).reshape(-1).copy()
        # Interpolated IK increments receive the same geometric clearance check.
        for command in result:
            q[indices] = command['arm']['joint_position_rad']
            assert query.clearance(q) >= .0005, 'Resampled path fixture collision'
        return result
    def sample(action, phase):
        observation, _, terminated, truncated, info = env.step(action)
        evidence.sample(env, observation, info, action=action, label=phase)
        contacts = env.privileged.get('world')['contacts']
        unexpected = 0.
        for a,b,force in zip(contacts['link_a'],contacts['link_b'],contacts['force']):
            other = int(b) if int(a) in all_pads else int(a) if int(b) in all_pads else None
            if other is not None and other not in robot_links and other not in tool_links:
                unexpected += float(np.linalg.norm(force))
        evidence.report['maximum_pad_fixture_force_N'] = max(
            evidence.report.get('maximum_pad_fixture_force_N',0.),unexpected)
        if unexpected > .05:
            evidence.save()
            raise AssertionError(f'Unexpected pad contact with a fixture during {phase}: {unexpected} N')
        if terminated or truncated:
            raise AssertionError(f'Episode ended during {phase}: {info}')
        return info

    tool = plan['tool']
    def position():
        return np.asarray(env.privileged.get('world')['bodies'][tool]['position_m'])

    links = ET.parse(env._world.entities[tool].morph.file).findall('link')
    assert len(links) == 1, 'Pickup COM measurement requires a single rigid link'
    inertial = links[0].find('inertial/origin')
    local_com = np.fromstring(inertial.get('xyz'), sep=' ')
    def center_of_mass():
        body = env.privileged.get('world')['bodies'][tool]
        rotation = Rotation.from_quat(np.asarray(body['quaternion_wxyz'])[[1,2,3,0]])
        return np.asarray(body['position_m'])+rotation.apply(local_com)

    initial = position().copy()
    initial_com = center_of_mass()
    initial_grip = grip_target(env)[1]
    tool_links = {link.idx for link in env._world.entities[tool].links}
    pads = ({'left_finger','r85_right_silicone_pad'},
            {'right_finger','r85_left_silicone_pad'})
    pad_links = [{link.idx for link in env._robot.entity.links if link.name in names} for names in pads]
    assert all(pad_links), 'Both original Robotiq pad link groups are required'
    all_pads = set.union(*pad_links)
    robot_links = {link.idx for link in env._robot.entity.links}
    def pad_forces():
        contacts = env.privileged.get('world')['contacts']
        forces = [0.,0.]
        for a,b,force in zip(contacts['link_a'],contacts['link_b'],contacts['force']):
            other = int(b) if int(a) in tool_links else int(a) if int(b) in tool_links else None
            for side,links in enumerate(pad_links):
                if other in links:
                    forces[side] += float(np.linalg.norm(force))
        return forces
    with evidence.stage('home_to_pickup'):
        approach = scheduled(plan['approach'])
        evidence.report['pickup_schedule'] = dict(approach_steps=len(approach),max_commanded_joint_speed_rad_s=1.2)
        for command in approach:
            sample(command,'approach')
        for _ in range(20):
            sample(plan['approach'][-1],'settle_at_grip')
            if np.linalg.norm(np.asarray(env._robot.observe()['arm']['tcp_position_world_m'])-plan['target']) < .003:
                break
        actual = env._robot.observe()['arm']['tcp_position_world_m']
        assert np.linalg.norm(np.asarray(actual)-plan['target']) < .006
    with evidence.stage('physical_grasp'):
        for value in np.linspace(0,.78,21)[1:]:
            sample({'arm':{'gripper_position_rad':float(value)}},'close_gripper')
        # Native PD gains do not imply instantaneous closure. Wait for measured
        # bilateral pad contact before lifting, without changing model gains.
        sustained = 0
        relative_points = []
        contact_trace = []
        for wait in range(200):
            sample({},'establish_pad_contact')
            forces = pad_forces()
            measured = env._robot.observe()['arm']
            rotation = Rotation.from_quat(np.asarray(measured['tcp_orientation_wxyz'])[[1,2,3,0]])
            relative = rotation.inv().apply(grip_target(env)[1]-measured['tcp_position_world_m'])
            relative_points.append(relative)
            drift = float(np.linalg.norm(np.ptp(relative_points[-10:],axis=0)))
            sustained = sustained+1 if min(forces) > 3. else 0
            contact_trace.append(dict(step=wait+1,pad_force_N=forces,relative_span_m=drift))
            if sustained >= 10 and drift < .001:
                break
        evidence.report['grasp_contact'] = dict(pad_force_N=forces,
            driver_positions_rad=env._robot.observe()['arm']['finger_position_rad'].tolist(),
            additional_closure_steps=wait+1,required_force_each_pad_N=3.,required_consecutive_samples=10,
            relative_grip_span_limit_m=.001,contact_trace=contact_trace)
        evidence.save()
        assert sustained >= 10 and drift < .001, 'No stable bilateral grasp; pickup not attempted'
    with evidence.stage('physical_lift'):
        lift = scheduled(plan['lift'],max_skip=1)
        for command in lift:
            sample(command,'lift')
        lifted = position().copy()
        lifted_com = center_of_mass()
        lifted_grip = grip_target(env)[1]
        evidence.report['pickup_measurement'] = dict(initial_root_m=initial.tolist(),
            lifted_root_m=lifted.tolist(), root_frame_lift_m=float(lifted[2]-initial[2]),
            inertial_center_local_m=local_com.tolist(),
            initial_com_m=initial_com.tolist(), lifted_com_m=lifted_com.tolist(),
            center_of_mass_lift_m=float(lifted_com[2]-initial_com[2]),
            grip_point_lift_m=float(lifted_grip[2]-initial_grip[2]),
            mechanism='physical finger contact only; no attachment or pose correction')
        evidence.save()
        assert lifted_com[2]-initial_com[2] > .035, 'Tool centre of mass did not lift'
        assert lifted_grip[2]-initial_grip[2] > .035, 'Tool grip point did not lift'
    if not release:
        evidence.report['pickup_scope'] = 'home approach, physical pickup and withdrawal; no release or route traversal claim'
        return
    with evidence.stage('return_and_release_at_initial_support'):
        for command in reversed(lift):
            sample(command,'lower')
        command = plan['approach'][-1]
        command = {'arm':{**command['arm'],'gripper_position_rad':.78}}
        sample(command,'support')
        for value in np.linspace(.78,0,21)[1:]:
            sample({'arm':{'gripper_position_rad':float(value)}},'release')
        for command in list(reversed(plan['approach']))[:25]:
            sample(command,'retreat')
        for _ in range(20):
            sample({},'settle_released')
        released = position()
        evidence.report['pickup_measurement']['released_m'] = released.tolist()
        assert np.linalg.norm(released-initial) < .02, 'Tool did not remain on the pickup support'
    evidence.report['pickup_scope'] = 'pickup/lift/return to initial support; no route traversal or terminal release claim'


def plan_layout_reach(env):
    """Sample representative approaches; no rope motion or grasp is claimed."""
    import itertools
    task, robot = env._task, env._robot
    table_z = float(to_numpy(env._world.entities['table'].get_AABB()).reshape(-1,3)[:,2].max())
    if task.task_id == 'rope_threading':
        centerline = task.layout.centerline()+[0,0,table_z]
        targets = [(f'rope_end_{i}', p+[0,0,.03]) for i,p in enumerate(centerline[[0,-1]])]
        targets += [(r['name']+'_entry', np.asarray(r['center_m'])+[0,0,table_z]
                     +.06*np.asarray(r['normal'])) for r in task.layout.rings()]
        ignored = 'rope'
    elif task.task_id == 'orbits':
        layout = task.layout
        rotation = Rotation.from_euler('z',task.config['yaw_deg'],degrees=True)
        local = [('handle_approach', [layout.handle_x_m,0,layout.handle_height_m+.035])]
        local += [(f'ring_{i}_approach',[x,0,z+.06])
                  for i,(x,z) in enumerate(zip(layout.ring_x,layout.ring_z))]
        targets = [(name,task.origin+rotation.apply(p)) for name,p in local]
        ignored = 'handle'
    else:
        raise ValueError('Layout probe requires Rope Threading or Orbits')
    query = RobotObstacleQuery(env,ignored)
    solver = GenesisIKSolver(robot.entity)
    home_q = to_numpy(robot.entity.get_qpos()).reshape(-1).copy()
    home = robot.observe()
    home_gap = query.clearance(home_q)
    home_nearest = dict(query.last_nearest)
    open_q = home_q.copy()
    for side,group in robot.groups.items():
        open_q[robot._q_indices[side][len(group.arm_joints):]] = group.gripper_limits[1]
    opening_gap = home_gap
    opening = []
    for fraction in np.linspace(0,1,16)[1:]:
        candidate = home_q+fraction*(open_q-home_q)
        gap = query.clearance(candidate); opening_gap = min(opening_gap,gap)
        if gap < .0005:
            return dict(passed=False,targets=[],home_gap_m=home_gap,home_nearest=home_nearest,
                opening_failure=query.last_nearest,scope='home finger-opening sweep failed; no approach qualified')
        opening.append({side:{group.gripper_field:float(candidate[robot._q_indices[side][-1]])}
                        for side,group in robot.groups.items()})
    home_q = open_q
    results = []
    for name,target in targets:
        attempts = []; qualified = None
        sides = sorted(robot.groups,key=lambda side: np.linalg.norm(
            np.asarray(home[side]['tcp_position_world_m'])-target))
        for side in sides:
            group = robot.groups[side]
            qs = robot._q_indices[side][:len(group.arm_joints)]
            dofs = robot._indices[side][:len(group.arm_joints)]
            start = np.asarray(home[side]['tcp_position_world_m'])
            start_r = Rotation.from_quat(np.asarray(home[side]['tcp_orientation_wxyz'])[[1,2,3,0]])
            options = (itertools.product((.08,.04,.16),(95,65,35),(0,-30,30,-60,60))
                       if task.task_id == 'orbits' else
                       itertools.product((.08,.16),(35,65),(0,90,-90,180)))
            for cruise_offset,pitch,yaw in options:
                # Bend the wrist while rising; an upright Cartesian rise with
                # fixed orientation takes this home pose near wrist_angle=0.
                tilted = start_r*Rotation.from_euler('y',35,degrees=True)
                end_r = Rotation.from_euler('z',yaw,degrees=True)*start_r*Rotation.from_euler('y',pitch,degrees=True)
                cruise = max(start[2],target[2])+cruise_offset
                nodes = [(start,start_r),(start+[0,0,.025],tilted),
                         (np.r_[start[:2],cruise],tilted),(np.r_[target[:2],cruise],tilted),
                         (np.r_[target[:2],cruise],end_r),(target,end_r)]
                if task.task_id == 'rope_threading':
                    nodes = [(start,start_r),(start+[0,0,.025],tilted),
                             (np.r_[start[:2],cruise],tilted),(np.r_[start[:2],cruise],end_r),
                             (np.r_[target[:2],cruise],end_r),(target,end_r)]
                q = home_q.copy(); clearance = query.clearance(q); margin = float('inf'); path = []
                try:
                    for (p0,r0),(p1,r1) in zip(nodes[:-1],nodes[1:]):
                        rotations = Slerp([0,1],Rotation.concatenate([r0,r1]))
                        count = max(10,int(np.ceil(np.linalg.norm(p1-p0)/.006)),
                                    int(np.ceil((r0.inv()*r1).magnitude()/np.radians(1))))
                        for alpha in np.linspace(0,1,count+1)[1:]:
                            p = p0+alpha*(p1-p0)
                            hand = rotations(alpha)*Rotation.from_quat(
                                np.asarray(group.tcp_orientation_in_hand_wxyz)[[1,2,3,0]]).inv()
                            candidate = solver.solve_checked(link_name=group.hand_link,
                                position_world_m=p-hand.apply(group.tcp_position_in_hand_m),
                                orientation_wxyz=hand.as_quat()[[3,0,1,2]], joint_dof_indices=dofs,
                                initial_qpos=q,max_solver_iterations=150)
                            if np.max(abs(candidate[qs]-q[qs])) > .2:
                                raise AssertionError(f'Discontinuous IK branch: previous={q[qs].tolist()}, next={candidate[qs].tolist()}, tcp={p.tolist()}')
                            q = candidate
                            gap = query.clearance(q); clearance = min(clearance,gap)
                            if gap < .0005:
                                raise AssertionError(f'Fixture/inter-arm gap {gap}: {query.last_nearest}, tcp={p.tolist()}')
                            limits = np.asarray(group.arm_limits_rad)
                            current = float(np.min(np.minimum(q[qs]-limits[:,0],limits[:,1]-q[qs])))
                            margin = min(margin,current)
                            if current < .03:
                                raise AssertionError(f'Joint limit margin {current}')
                            path.append(q[qs].tolist())
                    qualified = dict(arm=side,yaw_deg=yaw,pitch_deg=pitch,cruise_offset_m=cruise_offset,minimum_fixture_and_inter_arm_gap_m=clearance,
                        minimum_joint_margin_rad=margin,joint_waypoints=path)
                    break
                except (ValueError,AssertionError) as error:
                    attempts.append(dict(arm=side,yaw_deg=yaw,pitch_deg=pitch,cruise_offset_m=cruise_offset,error=str(error)))
            if qualified is not None:
                break
        results.append(dict(point=name,target_world_m=target.tolist(),passed=qualified is not None,
                            qualified=qualified,rejected_attempts=attempts))
    return dict(passed=all(r['passed'] for r in results),targets=results,
                home_gap_m=home_gap,home_nearest=home_nearest,
                opening_minimum_clearance_m=opening_gap,opening_commands=opening,
                scope='independent home approaches with open grippers; loaded robot vs rigid fixtures and opposite arm; no live motion, same-arm self-collision audit or deformable grasp qualification',
                excluded_tool=ignored)


def search_threading_layout(env):
    """Rigidly reposition the complete assembly in collision queries only."""
    import itertools
    import trimesh
    from pathlib import Path
    from omegaconf import OmegaConf
    import topogym
    assert env._task.task_id == 'rope_threading'
    query = RobotObstacleQuery(env,'rope')
    names={r['name']+suffix for r in env._task.layout.rings() for suffix in ('','_stand','_base')}
    assembly=trimesh.collision.CollisionManager(); vertices=[]; object_names=[]
    for name,mesh in query.fixed_meshes.items():
        if name.split('/')[0] in names:
            assembly.add_object(name,mesh);object_names.append(name);vertices.append(mesh.vertices)
    rope=env._world.entities['rope']
    positions=env.privileged.get('world')['fem']['rope']['position_m']
    mesh=trimesh.Trimesh(positions,rope.surface_triangles,process=False)
    assembly.add_object('rope',mesh);object_names.append('rope');vertices.append(mesh.vertices)
    robot=trimesh.collision.CollisionManager()
    for link in env._robot.entity.links:
        for geom in link.geoms:
            robot.add_object(f'{link.name}/{geom.idx}',trimesh.Trimesh(to_numpy(geom.get_verts()),geom.mesh.faces,process=False))
    vertices=np.vstack(vertices)
    camera=OmegaConf.load(Path(topogym.__file__).parent/'config/profiles/camera_configs/aloha_observation.yaml').cameras.cam_high
    forward=np.asarray(camera.lookat)-camera.pos;forward/=np.linalg.norm(forward)
    right=np.cross(forward,camera.up);right/=np.linalg.norm(right);up=np.cross(right,forward)
    vertical=np.tan(np.radians(camera.fov/2));horizontal=vertical*camera.res[0]/camera.res[1]
    table=to_numpy(env._world.entities['table'].get_AABB()).reshape(-1,3)
    translation=np.asarray(env._task.layout.translation_m);anchor=translation+[0,0,float(table[:,2].max())]
    candidates=[]; rejected=dict(camera=0,table=0,robot=0)
    for angle,dx,dy in itertools.product((-30,-15,0,15,30),np.linspace(-.12,.12,13),np.linspace(-.12,.12,13)):
        rotation=Rotation.from_euler('z',angle,degrees=True).as_matrix()
        matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=anchor+[dx,dy,0]-rotation@anchor
        posed=vertices@rotation.T+matrix[:3,3]
        relative=posed-np.asarray(camera.pos);depth=relative@forward
        frame=max(float(np.max(abs(relative@right)/(depth*horizontal))),float(np.max(abs(relative@up)/(depth*vertical))))
        if np.any(depth<=0) or frame>=.98:
            rejected['camera']+=1;continue
        if np.any(posed[:,:2]<table[:,:2].min(0)+.015) or np.any(posed[:,:2]>table[:,:2].max(0)-.015):
            rejected['table']+=1;continue
        for name in object_names:assembly.set_transform(name,matrix)
        gap,pair=assembly.min_distance_other(robot,return_names=True)
        if gap < .01:
            rejected['robot']+=1;continue
        score=np.hypot(dx,dy)+abs(angle)*.001-.1*min(gap,.04)
        candidates.append(dict(score=float(score),translation_m=(translation+[dx,dy,0]).tolist(),
            yaw_deg=float(env._task.layout.yaw_deg+angle),home_robot_clearance_m=float(gap),
            nearest_objects=list(pair),high_camera_extent=frame))
    candidates.sort(key=lambda row:row['score'])
    return dict(passed=bool(candidates),candidates=candidates[:20],qualified_count=len(candidates),rejected=rejected,
        scope='candidate rigid transforms of all rings, supports and initial FEM rope; actual loaded robot including mounting feet; no live pose writes; needs a newly generated scene and full qualification')


def plan_home_clearance(env):
    """Check home and finger opening against actual rigid and FEM surfaces."""
    import trimesh
    robot=env._robot
    assert set(robot.groups)=={'left','right'}, 'This probe uses ALOHA finger rails'
    query=RobotObstacleQuery(env,'__none__')
    soft=env.privileged.get('world')['fem']
    for name,state in soft.items():
        body=env._world.entities[name]
        query.fixed.add_object(name+'/fem_surface',trimesh.Trimesh(
            state['position_m'],body.surface_triangles,process=False))
    home=to_numpy(robot.entity.get_qpos()).reshape(-1).copy();opened=home.copy()
    for side,group in robot.groups.items():
        opened[robot._q_indices[side][len(group.arm_joints):]]=group.gripper_limits[1]
    samples=[]
    for fraction in np.linspace(0,1,16):
        gap=query.clearance(home+fraction*(opened-home))
        samples.append(dict(fraction=float(fraction),clearance_m=gap,nearest=query.last_nearest))
    minimum=min(row['clearance_m'] for row in samples)
    return dict(passed=minimum>=.01,minimum_clearance_m=minimum,required_clearance_m=.01,
        samples=samples,scope='actual loaded rigid/FEM collision surfaces; home and full opening sweep; no live robot motion or same-arm self-collision audit')
