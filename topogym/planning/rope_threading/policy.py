"""Measured, contact-gated development controller; no body/state writes.

This is an exploratory recipe, not a qualified oracle. Its runner reports
native task success separately from pickup and sampled collision checks.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from topogym.utils.arrays import to_numpy
from topogym.utils.geometry.rope import sample_material_centerline
from .kinematics import ThreadingIK, vertical_pinch, CONTACT_IN_TCP_M


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
        for distance in (.065, .085):
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
        self.phase = 'raise_to_ring'
        p, r = self.tcp('right')
        yield from self.move('right', (p+[0., 0., center[2]+.10-p[2]], r), speed=.04)
        if self.env._task.difficulty == 'very_easy':
            self.phase = 'orient_above_open_cradle'
            target = vertical_pinch(center+[.025, 0., .09], [-1., 0.])
            yield from self.move('right', target, speed=.03)
            self.phase = 'lower_onto_cradle'
            for height in np.linspace(.09, -.0638, 25)[1:]:
                yield from self.move('right', vertical_pinch(center+[.025, 0., height], [-1., 0.]), speed=.015)
                self.require_grip('right')
                if self.env._task.result.metrics.get('draped'):
                    break
        else:
            # Approach axis points through the aperture, with the free end
            # hanging below the feeding fingers for the opposite hand.
            turn = Rotation.from_matrix(np.column_stack([[-1., 0., 0.], [0., 1., 0.], [0., 0., -1.]]))
            def feed_pose(offset):
                contact = center+offset
                return contact-turn.apply(CONTACT_IN_TCP_M), turn
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
