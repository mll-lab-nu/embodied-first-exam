"""Measured, contact-gated development controller; no body/state writes.

This is an exploratory recipe, not a qualified oracle. Its runner reports
native task success separately from pickup and sampled collision checks.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from topogym.utils.arrays import to_numpy
from topogym.utils.geometry.rope import sample_material_centerline
from .kinematics import ThreadingIK, vertical_pinch, CONTACT_IN_TCP_M
from topogym.planning.oracle_ik import simplified_tier, active_scope
from topogym.planning.oracle_path import joint_samples


def rolled_pinch(point, tail_xy, roll_deg=0., flip=1):
    """vertical_pinch turned about the rope axis: 90 deg puts the jaws vertical, approach from the side."""
    _, turn = vertical_pinch(point, tail_xy, flip)
    axis = np.r_[np.asarray(tail_xy, float)[:2], 0.]
    turn = Rotation.from_rotvec(np.deg2rad(roll_deg)*axis/np.linalg.norm(axis))*turn
    return np.asarray(point, float)-turn.apply(CONTACT_IN_TCP_M), turn


class ThreadingPolicy:
    def __init__(self, env, *, part='solve', speed_scale=1.):
        self.env, self.part = env, part
        self.speed_scale = float(speed_scale)
        if not 0 < self.speed_scale <= 3:
            raise ValueError('speed_scale must be in (0, 3]')
        self.kin = ThreadingIK(env)
        self.phase, self.tracking, self.planning = 'home', {}, []
        self.program = None
        self.pickup_passed = False

    def initialize(self, context):
        if context['action_spec']['mode'] != 'JOINT_ABS' or context['action_spec']['robot_id'] != 'aloha':
            raise ValueError('Threading development policy requires ALOHA JOINT_ABS')
        self.dt = context['timing_spec']['control_dt_s']
        self.fingers = {side: float(self.env._robot.observe()[side]['finger_position_m'][0])
                        for side in ('left', 'right')}

    def act(self, observation):
        self.obs = observation
        if not observation['privileged']['world']['ipc']['native_valid']:
            raise RuntimeError('Native IPC validity failed')
        if self.program is None:
            self.program = self.actions()
        return next(self.program, None)

    def time(self):
        return float(self.obs['state']['sim_time_s'])

    def qpos(self):
        return to_numpy(self.env._robot.entity.get_qpos()).reshape(-1).copy()

    def action(self, q):
        return {side: dict(joint_position_rad=q[self.env._robot._q_indices[side][:6]].tolist(),
                           gripper_position_m=self.fingers[side]) for side in ('left', 'right')}

    def hold(self, seconds):
        q, start = self.qpos(), self.time()
        while self.time()-start < seconds-1e-10:
            yield self.action(q)

    def tcp(self, side):
        value = self.obs['robot'][side]
        return np.asarray(value['tcp_position_world_m']), Rotation.from_quat(
            np.asarray(value['tcp_orientation_wxyz'])[[1, 2, 3, 0]])

    def end_point(self, distance):
        points = sample_material_centerline(self.obs['privileged']['world']['fem']['rope'],
                                             *self.env._task.centerline_map)
        s = self.env._task.centerline_map[1][self.env._task.centerline_map[0]].mean(axis=1)
        return np.array([np.interp(s[-1]-distance, s, points[:, axis]) for axis in range(3)])

    def move_q(self, target, duration):
        start_q, start = self.qpos(), self.time()
        arm_indices = np.r_[self.env._robot._q_indices['left'][:6], self.env._robot._q_indices['right'][:6]]
        # Collision audit includes all interpolated arm configurations. Live
        # finger values are used because opening changes their swept geometry.
        count = max(2, int(np.ceil(abs(target-start_q).max()/.015))+1)
        for u in np.linspace(0., 1., count):
            q = start_q+u*(target-start_q)
            for side in ('left', 'right'):
                q[self.env._robot._q_indices[side][6:]] = self.fingers[side]
            audit = self.kin.check(q)
            if not audit['passed']:
                raise RuntimeError(f'{self.phase}: sampled collision check failed: {audit}')
        duration = max(duration, 1.5*abs(target[arm_indices]-start_q[arm_indices]).max()/.65, .05)/self.speed_scale
        self.planning.append(dict(phase=self.phase, duration_s=float(duration), samples=count,
                                  target_qpos=target.tolist(), last_clearance=audit))
        while self.time()-start < duration-1e-10:
            u = min(1., (self.time()-start+self.dt)/duration)
            yield self.action(start_q+(3*u*u-2*u*u*u)*(target-start_q))
        deadline = self.time()+2.
        while True:
            error = float(abs(self.qpos()[arm_indices]-target[arm_indices]).max())
            self.tracking = dict(maximum_joint_error_rad=error)
            if error < .007:
                break
            if self.time() > deadline:
                raise RuntimeError(f'{self.phase}: joint target did not settle: {error}')
            yield self.action(target)

    def move(self, side, target, *, speed=.05, linear=True):
        p0, r0 = self.tcp(side)
        p, r = target
        count = max(1, int(np.ceil(np.linalg.norm(p-p0)/.02))) if linear else 1
        rotations = Slerp([0., 1.], Rotation.from_quat([r0.as_quat(), r.as_quat()]))
        for u in np.linspace(0., 1., count+1)[1:]:
            pose = (p0+u*(p-p0), rotations(u))
            q = self.kin.solve(side, pose, self.qpos())
            yield from self.move_q(q, max(np.linalg.norm(p-p0)/count/speed,
                                          (r0.inv()*r).magnitude()/count/.5))

    def acquire(self, side):
        # Avoid storing a large closing error in the position servo. In the
        # soft rope, commanding the mechanical stop can invert material before
        # the first assisted solve even after bilateral admission succeeds.
        self.fingers[side] = min(self.fingers[side], .018)
        deadline, next_close = self.time()+4., self.time()+.25
        q = self.qpos()
        while self.time() < deadline:
            hand = self.obs['privileged']['world']['grasp']['hands'][side]
            self.tracking = dict(grasp_phase=hand['phase'], rejection=hand.get('rejection'))
            if hand['phase'] == 'holding' and hand['solved_ticks'] > 0:
                return
            if hand['phase'] not in {'qualifying', 'registered'} and self.time() >= next_close:
                self.fingers[side] = max(.002, self.fingers[side]-.00025)
                next_close = self.time()+.05
            yield self.action(q)
        raise RuntimeError(f'{side} failed bilateral contact-gated rope acquisition')

    def require_grip(self, side):
        if self.obs['privileged']['world']['grasp']['hands'][side]['phase'] != 'holding':
            raise RuntimeError(f'{side} lost the physical rope grasp')

    def plan_pickup(self):
        """Audit the entire approach/descent before committing to a grasp pose."""
        trials = []
        # easier: the feeding grasp must stay in the judged 120 mm end band with its
        # 18 mm material patch, and leave the longest tail for the receiving hand.
        for distance in ((.10, .095) if self.env._task.difficulty == 'easier' else (.065, .085)):
            point = self.end_point(distance)
            tangent = self.end_point(distance-.01)-self.end_point(distance+.01)
            for flip in (1, -1):
                q = self.qpos()
                q[self.env._robot._q_indices['right'][6:]] = .037
                target = vertical_pinch(point, tangent, flip)
                trial = dict(distance_m=distance, flip=flip, accepted=False)
                try:
                    for height in (.07, .0525, .035, .0175, 0.):
                        next_q = self.kin.solve('right', (target[0]+[0., 0., height], target[1]), q)
                        count = max(2, int(np.ceil(abs(next_q-q).max()/.025))+1)
                        for u in np.linspace(0., 1., count):
                            audit = self.kin.check(q+u*(next_q-q))
                            if not audit['passed']:
                                raise ValueError(str(audit))
                        q = next_q
                    trial['accepted'] = True
                    trials.append(trial)
                    self.planning.append(dict(phase='whole_pickup_preflight', candidates=trials))
                    return distance, flip
                except ValueError as error:
                    trial['error'] = str(error)
                    trials.append(trial)
        self.planning.append(dict(phase='whole_pickup_preflight', candidates=trials))
        raise RuntimeError(f'No collision-free pickup candidate: {trials}')

    def plan_ring_transfer(self, center):
        """Try complete approach/feed routes without advancing the live scene.

        Intermediate height, yaw and (very_easy) jaw tilt are recipe choices. Every candidate keeps
        the same material contact point and passes the existing fixture, table,
        self-collision and joint-limit checks along its joint segments.
        """
        trials = []
        p0, r0 = self.tcp('right')
        from itertools import product
        very_easy = self.env._task.difficulty == 'very_easy'
        # very_easy: the tail crosses the cradle plane along its normal, so the
        # open semicircle's tips are never in the way. Carry the rope below the
        # ring centre (heights here are negative), slide the 65-85 mm tail
        # through the plane, then lower onto the inner rim (rope centre 65 mm
        # below the ring centre). Nothing needs to rise above the ring.
        # easier: the feeding hand stays on the entrance side and only the tail
        # (grasp 95-100 mm from the end) passes the ring along its normal; the
        # hand stops 35-45 mm before the plane, the closest checked clearance.
        options = (product((-.035, -.045, -.025), (0., -10., 10.), (0., 15., -15.), (None,)) if very_easy else
                   product((-.01, 0., .01), (0.,), (0., 30., -30.), (.035, .045)))
        for height, yaw, turn_deg, feed_x in options:
            trial = dict(height_m=height, yaw_deg=yaw, accepted=False)
            if very_easy:
                trial['tilt_deg'] = turn_deg
                def pinch(x, z):
                    return vertical_pinch(center+[x, 0., z], [-1., 0.], yaw_deg=yaw, tilt_deg=turn_deg)
                # 100 mm: the tail tip stays 15 mm or more short of the plane.
                route = [('carry_beside_cradle', pinch(.10, height), .03, False),
                         ('slide_tail_through_cradle', pinch(.025, height), .02, True)]
                route.extend(('lower_onto_cradle', pinch(.025, z), .015, True)
                             for z in np.linspace(height, -.066, 13)[1:])
            else:
                trial.update(roll_deg=turn_deg, feed_x_m=feed_x)
                # 130 mm: the tail tip stays 30 mm or more short of the plane.
                route = [('carry_to_ring_entrance', rolled_pinch(center+[.13, 0., height], [-1., 0.], turn_deg), .03, False),
                         ('feed_tail_through_ring', rolled_pinch(center+[feed_x, 0., height], [-1., 0.], turn_deg), .015, True)]
            try:
                trial.update(accepted=True, samples=self.audit_route('right', route))
                trials.append(trial)
                self.planning.append(dict(phase='whole_ring_transfer_preflight', candidates=trials,
                    scope='sampled rigid geometry; soft rope and grasp require live feedback'))
                return route
            except ValueError as error:
                trial.update(accepted=False, error=str(error))
                trials.append(trial)
        self.planning.append(dict(phase='whole_ring_transfer_preflight', candidates=trials))
        raise RuntimeError(f'No checked ring-transfer candidate in the current search: {trials}')

    def audit_route(self, side, route):
        """IK, public bounds and sampled collision checks for a whole route from the live pose."""
        q, previous, samples = self.qpos(), self.tcp(side), 0
        for phase, (p, r), _, linear in route:
            start_p, start_r = previous
            count = max(1, int(np.ceil(max(np.linalg.norm(p-start_p)/.02,
                (r*start_r.inv()).magnitude()/.1)))) if linear else 1
            turns = Slerp([0., 1.], Rotation.from_quat([start_r.as_quat(), r.as_quat()]))
            for u in np.linspace(0., 1., count+1)[1:]:
                try:
                    next_q = self.kin.solve(side, (start_p+u*(p-start_p), turns(u)), q)
                except ValueError as error:
                    raise ValueError(f'{phase}: {error}') from None
                for candidate in joint_samples(q, next_q):
                    for hand in ('left', 'right'):
                        candidate[self.env._robot._q_indices[hand][6:]] = self.fingers[hand]
                    scope = active_scope(self.env._robot.entity)
                    public = scope.check_public_bounds(candidate) if scope is not None else dict(passed=True)
                    audit = self.kin.check(candidate) if public['passed'] else public
                    samples += 1
                    if not audit['passed']:
                        raise ValueError(f'{phase}: {audit}')
                q = next_q
            previous = p, r
        return samples

    def plan_receive(self, center, normal, feed_contact, grip_distance):
        """Receiving grasp from the side (jaws vertical) on the tail predicted past the plane.

        The tail is taken as straight along -normal from the feeding contact;
        the live grasp re-aims on the measured rope.
        """
        trials = []
        for distance in (.03, .025, .02, .015):
            point = feed_contact-(grip_distance-distance)*normal
            axial = float((point-center) @ normal)
            # The left arm reaches the exit side only 35 mm or more past the plane; keep 5 mm.
            if axial > -.04:
                trials.append(dict(distance_m=distance, axial_m=axial, accepted=False, error='too close to the plane'))
                continue
            for roll in (90., -90., 60., -60.):
                pose = rolled_pinch(point, -normal[:2], roll, flip=-1)
                approach = pose[1].apply([1., 0., 0.])
                # Stage 50 mm back along the approach (100 mm is out of the left arm's reach),
                # before the tail arrives. The joint move ends 40 mm further from the ring:
                # straight from home it grazed the ring (0.2-0.5 mm, v19 run 6).
                stage = pose[0]-.05*approach
                route = [('left_clear_of_ring', (stage-.04*normal, pose[1]), .03, False),
                         ('left_stage', (stage, pose[1]), .02, True),
                         ('left_receive', pose, .015, True)]
                trial = dict(distance_m=distance, axial_m=axial, roll_deg=roll, accepted=False)
                try:
                    trial.update(accepted=True, samples=self.audit_route('left', route))
                    trials.append(trial)
                    self.planning.append(dict(phase='receive_preflight', candidates=trials))
                    return route, distance, roll
                except ValueError as error:
                    trial['error'] = str(error)
                    trials.append(trial)
        self.planning.append(dict(phase='receive_preflight', candidates=trials))
        raise RuntimeError(f'No checked receiving grasp: {trials}')

    def actions(self):
        self.fingers['right'] = .037
        self.phase = 'open_at_home'
        yield from self.hold(.15)
        self.phase = 'plan_complete_pickup'
        distance, flip = self.plan_pickup()
        point = self.end_point(distance)
        tangent = self.end_point(distance-.01)-self.end_point(distance+.01)
        pinch = vertical_pinch(point, tangent, flip)
        self.phase = 'approach_from_home'
        yield from self.move('right', (pinch[0]+[0., 0., .07], pinch[1]), linear=False)
        self.phase = 'descend_to_rope'
        # Use the current rope, after the approach has physically settled it.
        point = self.end_point(distance)
        pinch = vertical_pinch(point, tangent, flip)
        yield from self.move('right', pinch, speed=.02)
        self.phase = 'right_acquire'
        yield from self.acquire('right')
        patch = self.obs['privileged']['world']['grasp']['hands']['right']['binding']['indices']
        before_lift = np.asarray(self.obs['privileged']['world']['fem']['rope']['position_m'])[patch].mean(axis=0)
        self.phase = 'pickup_lift'
        p, r = self.tcp('right')
        yield from self.move('right', (p+[0., 0., .04], r), speed=.025)
        self.require_grip('right')
        after_lift = np.asarray(self.obs['privileged']['world']['fem']['rope']['position_m'])[patch].mean(axis=0)
        self.tracking = dict(held_material_lift_m=float(after_lift[2]-before_lift[2]))
        if self.tracking['held_material_lift_m'] < .025:
            raise RuntimeError('Healthy binding did not lift its material patch by 25 mm')
        self.pickup_passed = True
        if self.part == 'pickup':
            return
        ring = self.env._task.layout.rings()[0]
        center = np.asarray(ring['center_m'])+[0., 0., self.env._task.table_height_m]
        if simplified_tier(self.env) is not None:
            self.phase = 'plan_complete_ring_transfer'
            normal = np.asarray(ring['normal'])
            for phase, target, speed, linear in self.plan_ring_transfer(center):
                if phase == 'feed_tail_through_ring':
                    # Stage the receiving hand while the tail is still on the entrance side:
                    # a later joint move swept the fed tail 44 mm aside (v19 run 4).
                    self.fingers['left'] = .037
                    self.phase = 'open_receiving_hand'
                    yield from self.hold(.15)
                    self.phase = 'plan_receive'
                    receive, receive_distance, roll = self.plan_receive(
                        center, normal, target[0]+target[1].apply(CONTACT_IN_TCP_M), distance)
                    for name, pose, speed_m_s, straight in receive[:2]:
                        self.phase = name
                        yield from self.move('left', pose, speed=speed_m_s, linear=straight)
                self.phase = phase
                yield from self.move('right', target, speed=speed, linear=linear)
                self.require_grip('right')
                if phase == 'lower_onto_cradle' and self.env._task.result.metrics.get('draped'):
                    break
            if self.env._task.difficulty == 'very_easy':
                # The held rope sits higher than the nominal pad contact (v19 run: 2.9 mm
                # above the rim at -66 mm). Close the gap on the measured rim clearance.
                self.phase = 'press_onto_rim'
                for _ in range(12):
                    metrics = self.env._task.result.metrics
                    if metrics.get('draped'):
                        break
                    p, r = self.tcp('right')
                    drop = min(.003, max(.0005, metrics['minimum_rim_clearance_m']-.0003))
                    self.planning.append(dict(phase='press_onto_rim', drop_m=drop,
                        rim_clearance_m=metrics['minimum_rim_clearance_m'], tcp_z_m=float(p[2])))
                    yield from self.move('right', (p-[0., 0., drop], r), speed=.005)
                    self.require_grip('right')
        else:
            self.phase = 'raise_to_ring'
            p, r = self.tcp('right')
            yield from self.move('right', (p+[0., 0., center[2]+.10-p[2]], r), speed=.04)
        if self.env._task.difficulty == 'very_easy' and simplified_tier(self.env) is None:
            self.phase = 'orient_above_open_cradle'
            target = vertical_pinch(center+[.025, 0., .09], [-1., 0.])
            yield from self.move('right', target, speed=.03)
            self.phase = 'lower_onto_cradle'
            for height in np.linspace(.09, -.0638, 25)[1:]:
                yield from self.move('right', vertical_pinch(center+[.025, 0., height], [-1., 0.]), speed=.015)
                self.require_grip('right')
                if self.env._task.result.metrics.get('draped'):
                    break
        elif self.env._task.difficulty == 'easier':
            # Relay: the left hand takes the tail on the exit side, both hold,
            # the right lets go and backs off, then the left pulls the end
            # further through along the ring normal.
            self.require_grip('right')
            # Re-aim the position on the tail as it is now; keep the checked orientation
            # (a re-measured tangent can leave the left arm's reach, v19 run 2: 29 mm).
            turn = receive[2][1][1]
            planned = receive[2][1][0]+turn.apply(CONTACT_IN_TCP_M)
            # Take the grasp point that is 35 mm past the plane now (v19 run 3: fingers 0.07 mm from the ring).
            for choice in sorted({receive_distance, .02, .015}, reverse=True):
                point = self.end_point(choice)
                if (point-center) @ normal <= -.035:
                    break
            self.planning.append(dict(phase='left_receive_target', planned_distance_m=receive_distance,
                planned_axial_m=float((planned-center) @ normal), distance_m=choice,
                axial_m=float((point-center) @ normal), shift_m=(point-planned).tolist()))
            self.phase = 'left_receive'
            yield from self.move('left', (point-turn.apply(CONTACT_IN_TCP_M), turn), speed=.015)
            p, r = self.tcp('left')
            offset = self.end_point(choice)-(p+r.apply(CONTACT_IN_TCP_M))
            # Pad-contact error in the hand frame: approach axis, jaw axis, along the rope.
            self.planning.append(dict(phase='left_receive_alignment', distance_m=choice, roll_deg=roll,
                contact_error_hand_m=r.inv().apply(offset).tolist(), contact_error_world_m=offset.tolist()))
            self.phase = 'left_acquire'
            yield from self.acquire('left')
            yield from self.hold(.05)
            self.require_grip('right')
            self.phase = 'right_release'
            self.fingers['right'] = .037
            yield from self.hold(.15)
            self.phase = 'right_withdraw'
            p, r = self.tcp('right')
            yield from self.move('right', (p+[.06, 0., 0.], r), speed=.02)
            yield from self.move('right', (p+[.06, 0., .04], r), speed=.02)
            self.require_grip('left')
            self.phase = 'left_pull_through'
            p, r = self.tcp('left')
            yield from self.move('left', (p-.06*normal, r), speed=.015)
            self.require_grip('left')
        elif self.env._task.difficulty != 'very_easy':
            # Approach axis points through the aperture, with the free end
            # hanging below the feeding fingers for the opposite hand.
            turn = Rotation.from_matrix(np.column_stack([[-1., 0., 0.], [0., 1., 0.], [0., 0., -1.]]))
            def feed_pose(offset):
                contact = center+offset
                return contact-turn.apply(CONTACT_IN_TCP_M), turn
            if simplified_tier(self.env) is None:
                self.phase = 'align_ring_entrance'
                yield from self.move('right', feed_pose([.15, 0., .025]), speed=.025)
                self.phase = 'feed_through_ring'
                yield from self.move('right', feed_pose([-.10, 0., .025]), speed=.015)
            self.require_grip('right')
            self.fingers['left'] = .037
            self.phase = 'open_receiving_hand'
            yield from self.hold(.15)
            point = self.end_point(.018)
            receive = Rotation.from_matrix(np.column_stack([[1., 0., 0.], [0., -1., 0.], [0., 0., -1.]]))
            target = point-receive.apply(CONTACT_IN_TCP_M)
            self.phase = 'left_approach'
            yield from self.move('left', (target+[-.06, 0., 0.], receive), linear=False)
            self.phase = 'left_receive'
            point = self.end_point(.018)
            yield from self.move('left', (point-receive.apply(CONTACT_IN_TCP_M), receive), speed=.015)
            yield from self.acquire('left')
            yield from self.hold(.05)
            self.require_grip('right')
            self.phase = 'right_release'
            self.fingers['right'] = .037
            yield from self.hold(.15)
            self.phase = 'right_withdraw'
            yield from self.move('right', feed_pose([.15, 0., .025]), speed=.02)
            self.require_grip('left')
        self.phase = 'confirm_native_terminal'
        yield from self.hold(10.)
