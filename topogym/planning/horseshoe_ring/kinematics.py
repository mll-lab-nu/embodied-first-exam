"""Read-only native IK/FK and imported collision geometry for Horseshoe.

Plans never change a body pose or advance physics. The table, both arms and
all five puzzle bodies participate in collision queries. Finger contact with
the explicitly selected grasp target is the only permitted puzzle contact.
"""
import fcl
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.planning.buzz_wire_3d.kinematics import mesh_object, manager, distance
from topogym.planning.rigid_reference.geometry import matrix
from topogym.planning.rigid_reference.feedback import body_pose
from topogym.solvers.genesis_kinematics import GenesisFKSolver, GenesisIKSolver
from topogym.utils.arrays import to_numpy


class CheckedJointPolicy:
    """Translate Cartesian intent through native checked IK into joint actions."""
    def __init__(self, policy, robot):
        self.policy, self.robot = policy, robot
        self.ik = GenesisIKSolver(robot.entity)

    def __getattr__(self, name):return getattr(self.policy,name)

    def initialize(self, context):
        if context['action_spec']['mode']!='JOINT_ABS':raise ValueError('Expected JOINT_ABS')
        adapted=dict(context,action_spec=dict(context['action_spec'],mode='EE_ABS'))
        self.policy.initialize(adapted)

    def act(self, observation):
        intent=self.policy.act(observation)
        if not intent:return intent
        q=to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy();result={}
        for side,value in intent.items():
            out={k:v for k,v in value.items() if k in {'gripper_position_m','joint_position_rad'}}
            if 'position_world_m' in value:
                group=self.robot.groups[side]
                r=Rotation.from_quat(np.roll(value['orientation_wxyz'],-1))
                p=np.asarray(value['position_world_m'])
                def solve(tp,tr):
                    hand_r=tr*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz,-1)).inv()
                    return self.ik.solve_checked(link_name=group.hand_link,
                        position_world_m=tp-hand_r.apply(group.tcp_position_in_hand_m),
                        orientation_wxyz=hand_r.as_quat()[[3,0,1,2]],initial_qpos=q,
                        joint_dof_indices=self.robot._indices[side][:6],max_solver_iterations=300)
                try:q=solve(p,r)
                except ValueError:
                    nominal=self.policy.nominal_tcp.get(side)
                    if nominal is None:raise
                    np_,nr=nominal;angle=(r*nr.inv()).as_rotvec()
                    # A target just outside the IK tolerance can have a
                    # nearby valid solution that coarse halving skips.
                    # Keep native tolerances and the measured joint seed;
                    # only reduce the controller's optional compensation.
                    refined=getattr(self.policy,'withdrawal_parameters',{}).get('refine_ik_compensation',False)
                    fractions=((.995,.99,.975,.95,.9,.8,.7,.6,.5,.25,0.)
                               if refined else (.5,.25,0.))
                    for fraction in fractions:
                        try:q=solve(np_+fraction*(p-np_),Rotation.from_rotvec(fraction*angle)*nr)
                        except ValueError:
                            if fraction==0.:raise
                            continue
                        self.policy.bias[side]*=fraction
                        self.policy.angle_bias[side]*=fraction
                        self.policy.diagnostics.setdefault('ik_compensation_fraction',{})[side]=fraction
                        break
                out['joint_position_rad']=q[self.robot._q_indices[side][:6]].tolist()
            result[side]=out
        return result


class HorseshoeIK:
    def __init__(self, env, *, puzzle_clearance_m=.0005):
        self.puzzle_clearance_m=float(puzzle_clearance_m)
        if not np.isfinite(self.puzzle_clearance_m) or not .00005<=self.puzzle_clearance_m<=.0005:
            raise ValueError('Robot/puzzle planning clearance must be between 0.05 and 0.5 mm')
        self.robot = env._robot
        self.seed = to_numpy(self.robot.entity.get_qpos()).reshape(-1).copy()
        self.ik = GenesisIKSolver(self.robot.entity)
        self.fk = GenesisFKSolver(self.robot.entity)
        self.table_height = env._task.table_height_m
        pose = self.fk.solve(self.seed)
        ps = np.asarray(pose['position_world_m']).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        self.shapes = []
        self.by_arm = {}
        by_geom={}
        for link in self.robot.entity.links:
            side = link.name.split('/')[0]
            for geom in link.geoms:
                vertices = rs[link.idx_local].inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-ps[link.idx_local])
                obj = mesh_object(vertices, geom.init_faces)
                self.shapes.append((side, link.name, link.idx_local, vertices, obj))
                by_geom[int(geom.idx)]=(side,link.name,obj)
        # Respect Genesis' authored adjacency and neutral-pose exclusions.
        # Remaining same-arm pairs must not intersect in a candidate pose.
        valid_pairs=env._world.scene.sim.rigid_solver.collider._valid_collision_pairs
        self.self_pairs=[(by_geom[int(a)],by_geom[int(b)]) for a,b in valid_pairs
                         if int(a) in by_geom and int(b) in by_geom
                         and by_geom[int(a)][0]==by_geom[int(b)][0]]
        self.by_arm = {side: manager([x[4] for x in self.shapes if x[0] == side]) for side in self.robot.groups}
        self.nonfinger = {side: manager([x[4] for x in self.shapes if x[0] == side and 'finger' not in x[1]])
                          for side in self.robot.groups}
        self.bodies = {}
        world=env._world.read_state()
        for name in env._task.placement_vertices:
            p,r=body_pose(world['bodies'][name])
            objects = [mesh_object(r.inv().apply(to_numpy(g.get_verts()).reshape(-1, 3)-p), g.init_faces)
                       for link in env._world.entities[name].links for g in link.geoms]
            for obj in objects:obj.setTransform(fcl.Transform(r.as_matrix(),p))
            self.bodies[name] = (objects, manager(objects))

    def solve(self, side, tcp, seed=None):
        p, r = tcp
        group = self.robot.groups[side]
        hand_r = r*Rotation.from_quat(np.roll(group.tcp_orientation_in_hand_wxyz, -1)).inv()
        return self.ik.solve_checked(link_name=group.hand_link,
            position_world_m=p-hand_r.apply(group.tcp_position_in_hand_m),
            orientation_wxyz=hand_r.as_quat()[[3, 0, 1, 2]],
            initial_qpos=self.seed if seed is None else seed,
            joint_dof_indices=self.robot._indices[side][:6], max_solver_iterations=300)

    def check(self, q, *, contacts=None, body_poses=None):
        contacts = contacts or {}
        if body_poses is not None:
            for name,(p,r) in body_poses.items():
                objects,m=self.bodies[name]
                for obj in objects:obj.setTransform(fcl.Transform(r.as_matrix(),p))
                m.update()
        pose = self.fk.solve(q)
        ps = np.asarray(pose['position_world_m']).reshape(-1, 3)
        rs = Rotation.from_quat(np.asarray(pose['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        minimum = float('inf')
        for side, name, index, vertices, obj in self.shapes:
            obj.setTransform(fcl.Transform(rs[index].as_matrix(), ps[index]))
            if name.rsplit('/', 1)[-1] not in {'base_link', 'waist_link', 'shoulder_link'}:
                minimum = min(minimum, float((rs[index].apply(vertices)+ps[index])[:, 2].min()-self.table_height))
        for m in (*self.by_arm.values(), *self.nonfinger.values()):
            m.update()
        issues = []
        inter_arm_pairs=[]
        self_collisions=[]
        for a,b in self.self_pairs:
            if fcl.collide(a[2],b[2],fcl.CollisionRequest(),fcl.CollisionResult()):
                self_collisions.append([a[1],b[1]])
        if self_collisions:issues.append('same_arm_collision')
        if minimum < .0005:
            issues.append('table')
        if distance(self.by_arm['left'], self.by_arm['right']) < .001:
            issues.append('inter_arm')
            for a in (x for x in self.shapes if x[0]=='left'):
                for b in (x for x in self.shapes if x[0]=='right'):
                    gap=fcl.distance(a[4],b[4],fcl.DistanceRequest(),fcl.DistanceResult())
                    if gap<.001:
                        inter_arm_pairs.append([a[1],b[1],float(gap)])
        for side, arm in self.by_arm.items():
            for name, (_, puzzle) in self.bodies.items():
                permitted=contacts.get(side,())
                if isinstance(permitted,str):permitted=(permitted,)
                checked = self.nonfinger[side] if name in permitted else arm
                gap = distance(checked, puzzle)
                if gap < self.puzzle_clearance_m:
                    issues.append(side+'/'+name)
        for side, group in self.robot.groups.items():
            joints = q[self.robot._q_indices[side][:6]]
            limits = np.asarray(group.arm_limits_rad)
            if np.any(joints < limits[:, 0]) or np.any(joints > limits[:, 1]):
                issues.append(side+'/joint_limits')
        return dict(passed=not issues,issues=issues,table_clearance_m=minimum,
                    inter_arm_pairs=inter_arm_pairs,self_collisions=self_collisions)

    def grasp_candidates(self, task, state, side, *, openings=(.027,.018)):
        from topogym.assets.geometry.horseshoe_ring import band_centerline
        openings=tuple(openings)
        if (not openings or len(set(openings))!=len(openings)
                or any(isinstance(v,bool) or not np.isfinite(v) or not .002<v<=.027 for v in openings)):
            raise ValueError('Distinct grasp openings must be above 2 mm and at most 27 mm')
        name = 'horseshoe_'+side
        p, r = body_pose(state['bodies'][name])
        h, unit = task.assembly.template['horseshoe'], task.assembly.unit
        center = ((task.assembly.template['chain']['eye_to_link_center']+h['eye_offset_x'])*unit
                  +band_centerline(h, unit, np.array([np.deg2rad(h['mouth_half_angle_deg'])]))[0, 0])
        sign = -1 if side == 'left' else 1
        body_turn = Rotation.from_euler('z', 0 if side == 'left' else np.pi)
        rows, rejected = [], {}
        for angle in (90, 270, 120, 240, 60, 300, 150, 210, 180, 45, 315):
            a = np.deg2rad(angle)
            point = band_centerline(h, unit, np.array([a]))[0]
            tangent = band_centerline(h, unit, np.array([a+1e-5]))[0]-band_centerline(h, unit, np.array([a-1e-5]))[0]
            radial = np.array([tangent[1], -tangent[0], 0.]);radial /= np.linalg.norm(radial)
            point = body_turn.apply(point)+[sign*center, 0, 0]-task.body_origins[name]
            point_world = p+r.apply(point)
            for flip in (1, -1):
                down = np.array([0., 0., -1.])
                jaw = flip*r.apply(body_turn.apply(radial));jaw[2] = 0.;jaw /= np.linalg.norm(jaw)
                turn = Rotation.from_matrix(np.column_stack([down, jaw, np.cross(down, jaw)]))
                # Aim pads 2 mm above the centre of the 8 mm thick band.
                tcp = point_world+[0, 0, .002]+turn.apply([-.01381, 0., .00055])
                try:
                    pre = self.solve(side, (tcp+[0, 0, .08], turn))
                    target = self.solve(side, (tcp, turn), pre)
                    # A fully open inner finger can enter the neighbouring
                    # ring even though the band is narrow. Screen a smaller
                    # opening as well; the subsequent descent is checked too.
                    for opening in openings:
                        for q in (pre, target):q[self.robot._q_indices[side][6:]]=opening
                        checks=[self.check(pre),self.check(target,contacts={side:name})]
                        if not all(c['passed'] for c in checks):
                            key=str([c['issues'] for c in checks]);rejected[key]=rejected.get(key,0)+1
                            continue
                        rows.append(dict(side=side,angle_deg=angle,flip=flip,point_local_m=point.tolist(),
                            tcp_position_m=tcp.tolist(),tcp_quaternion_wxyz=turn.as_quat()[[3,0,1,2]].tolist(),
                            pre_qpos=pre.tolist(),grasp_qpos=target.tolist(),checks=checks,
                            open_position_m=opening,joint_distance=float(np.linalg.norm(pre-self.seed))))
                except ValueError as error:
                    key=str(error).split(':')[0];rejected[key]=rejected.get(key,0)+1
        return sorted(rows, key=lambda x:x['joint_distance']), rejected

    def plan_fold(self, object_frames, offsets, *, seed=None, stride=10):
        q=self.seed.copy() if seed is None else np.asarray(seed).copy()
        rows=[];failure=None
        indices=sorted(set(range(0,len(object_frames),stride))|{len(object_frames)-1})
        for index in indices:
            bodies=object_frames[index]
            try:
                previous=q.copy()
                for side,(op,orr) in offsets.items():
                    p,r=bodies['horseshoe_'+side]
                    q=self.solve(side,(p+r.apply(op),r*orr),q)
                checked=self.check(q,contacts={s:'horseshoe_'+s for s in offsets},body_poses=bodies)
                row=dict(reference_index=index,qpos=q.tolist(),maximum_joint_change_rad=float(np.abs(q-previous).max()),**checked)
                rows.append(row)
                if not checked['passed']:
                    failure=dict(index=index,reason='collision',checks=checked);break
            except ValueError as error:
                failure=dict(index=index,reason='ik',error=str(error));break
        return dict(passed=failure is None,scope='sampled native IK and collision meshes; passive dynamics unverified',
                    frames=rows,failure=failure)


def plan_oracle(env, reference, *, max_candidates=32, progress=None):
    """Find a grasp pair for the complete fold, then densify its IK audit."""
    from .oracle import balanced_fold,expand_coupled_plan
    from .coupled import CoupledHorseshoeIK
    from topogym.planning.rigid_reference.feedback import relative_pose
    checker=HorseshoeIK(env);state=env._world.read_state()
    selections={s:checker.grasp_candidates(env._task,state,s)[0] for s in ('left','right')}
    # Outer bends with a narrow opening avoid trapping the settled ring
    # between the right fingers during pickup.
    preferences={'left':(180,1),'right':(180,-1)}
    for side,rows in selections.items():
        angle,flip=preferences[side]
        rows.sort(key=lambda row:(abs(row['angle_deg']-angle),row['flip']!=flip,row['joint_distance']))
    xy=np.asarray(env._task.config['center_xy_m'])
    world=balanced_fold(reference,np.r_[xy,env._task.table_height_m+.24])
    attempts=[]
    for left in selections['left']:
        for right in selections['right']:
            if len(attempts)>=max_candidates:return dict(passed=False,attempts=attempts)
            grasps=dict(left=left,right=right)
            offsets={s:relative_pose(body_pose(state['bodies']['horseshoe_'+s]),
                        (np.asarray(g['tcp_position_m']),Rotation.from_quat(np.roll(g['tcp_quaternion_wxyz'],-1))))
                     for s,g in grasps.items()}
            q=checker.seed.copy()
            try:
                for s,g in grasps.items():
                    q[env._robot._q_indices[s][:6]]=np.asarray(g['pre_qpos'])[env._robot._q_indices[s][:6]]
                    q[env._robot._q_indices[s][6:]]=.0162
                    p,r=world[0]['horseshoe_'+s];op,orr=offsets[s]
                    q=checker.solve(s,(p+r.apply(op),r*orr),q)
                candidate=CoupledHorseshoeIK(checker,offsets,q).plan(reference,stride=40)
                if candidate['passed']:
                    refined=checker.plan_fold(expand_coupled_plan(reference,candidate),offsets,
                                               seed=candidate['frames'][0]['qpos'],stride=4)
                    candidate['dense_audit']=refined
                    candidate['passed'] &= refined['passed']
                attempts.append(dict(grasps={s:dict(angle_deg=g['angle_deg'],flip=g['flip']) for s,g in grasps.items()},
                                     passed=candidate['passed'],failure=candidate['failure']))
                if progress:progress(attempts[-1])
                if candidate['passed']:
                    return dict(passed=True,attempts=attempts,fold_plan=candidate,
                                grasps={s:dict(candidates=[g]) for s,g in grasps.items()})
            except ValueError as error:
                attempts.append(dict(passed=False,error=str(error)))
    return dict(passed=False,attempts=attempts)
