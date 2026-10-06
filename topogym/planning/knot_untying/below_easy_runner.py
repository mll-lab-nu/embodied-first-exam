"""The below-easy controller, with measured follow-up grasp checks for easier.

These variants retain their recorded joint-step interpolation and ordinary
release. Shared experimental hover/crush policies are qualified separately.
"""
import numpy as np

from .robot_oracle import PRE, Runner
from .simplified_policy import BELOW_EASY, step_with_joint_limit


class EndGraspFailure(RuntimeError):
    """An end grasp did not align with or lift its intended material station."""


def lift_measurement(rope_before, rope_after, contact_before, contact_after):
    rope_lift = float(rope_after[2] - rope_before[2])
    contact_lift = float(contact_after[2] - contact_before[2])
    gap = float(np.linalg.norm(rope_after - contact_after))
    return dict(rope_lift_m=rope_lift, contact_lift_m=contact_lift,
                rope_contact_distance_m=gap,
                followed=bool(contact_lift >= .004 and rope_lift >= .5 * contact_lift and gap <= .008))


class BelowEasyRunner(Runner):
    def __init__(self, args, *, session=None):
        if args.variation not in BELOW_EASY:
            raise ValueError('BelowEasyRunner only supports the two below-easy variants')
        super().__init__(args, session=session)
        # Keep the interpolation used in the qualified very_easy trace, even
        # when the shared Runner has additional rate or release policies.
        self.limiter = None
        self.hover_gate = False
        self.crush_guard = False
        self._end_context = None
        self._end_attempts = []

    def step(self, phase):
        return step_with_joint_limit(self, phase, self.joint_step_limit)

    def _step_once(self, phase):
        self.crush_guard = False
        return super()._step_once(phase)

    def _save_end_attempts(self):
        from topogym.utils.io import write_json_atomic
        write_json_atomic(self.args.output / 'end_grasp_attempts.json', dict(
            scope='Measured easier follow-up grasp alignment and lift checks; not task success or a Harbor grade',
            attempts=self._end_attempts))

    def wait_for_pregrasp(self, sides, plans, phase):
        tracking = super().wait_for_pregrasp(sides, plans, phase)
        if self._end_context is not None:
            # These are the existing coarse approach tolerances. The successful
            # first withdrawal had 13.6 mm air error and 1.6 mm preclose error;
            # an air pose must not be mistaken for the final pinch pose.
            observation = self.robot.observe()
            tracking['targets_m'] = {side: (plans[side][0] + [0., 0., PRE]).tolist() for side in sides}
            tracking['flips'] = {side: int(plans[side][2]) for side in sides}
            tracking['measured_joints_rad'] = {
                side: np.asarray(observation[side]['joint_position_rad']).tolist() for side in sides}
            self._end_context['pregrasp'] = tracking
            self._save_end_attempts()
            if not tracking['ready']:
                raise EndGraspFailure(f'Approach did not reach its position/orientation tolerance: {tracking}')
        return tracking

    def grasp(self, sides, ss, phase):
        context = self._end_context
        if context is None:
            return super().grasp(sides, ss, phase)
        shift = .015 * context['attempt']
        requested = [float(s + shift if s < self.length / 2 else s - shift) for s in ss]
        stations, opening, plans, record = super().place(sides, requested, phase)
        # The legacy placement can update its plan after its last convergence
        # loop. Check the CURRENT material position before closing either jaw.
        from scipy.spatial.transform import Rotation
        live_plans = {side: self.pose(side, s, (plans[side][2],)) for side, s in zip(sides, stations)}
        observation = self.robot.observe()
        errors = {}
        for side in sides:
            actual = observation[side]
            turn = Rotation.from_quat(np.asarray(actual['tcp_orientation_wxyz'])[[1, 2, 3, 0]])
            errors[side] = dict(
                position_m=float(np.linalg.norm(self.tcp(side) - live_plans[side][0])),
                orientation_rad=float((turn.inv() * live_plans[side][1]).magnitude()))
        context.update(stations_m=list(map(float, stations)), alignment=errors, placement=record)
        self._save_end_attempts()
        if any(not np.isfinite(list(e.values())).all() or e['position_m'] > .002 or e['orientation_rad'] > .1
               for e in errors.values()):
            raise EndGraspFailure(f'End-grasp alignment is outside tolerance: {errors}')
        record['verified_preclose_alignment'] = errors
        return super().pinch(sides, stations, opening, live_plans, record, phase)

    def cartesian(self, side, path, turn, phase, **kwargs):
        context = self._end_context
        probe = context is not None and phase == f"d{context['k']}:lift"
        if probe:
            station = self.grasps[side]['s']
            rope_before = self.at(self.line(), station)
            contact_before = self.contact_point(side)
        result = super().cartesian(side, path, turn, phase, **kwargs)
        if probe:
            # Use the existing physical lift and let the torque-limited arm
            # follow it. No attachment or kinematic rope motion is introduced.
            for _ in range(int(np.ceil(.3 / self.dt))):
                self.step(phase + ':check_hold')
            measurement = lift_measurement(rope_before, self.at(self.line(), station),
                                           contact_before, self.contact_point(side))
            context.setdefault('lift_checks', {})[side] = measurement
            self._save_end_attempts()
            if not measurement['followed']:
                raise EndGraspFailure(f'{side} end did not follow the physical lift: {measurement}')
        return result

    def straighten(self, k, cfg):
        if self.args.variation != 'knot_untying_easier':
            return super().straighten(k, cfg)
        from .simplified_policy import reachable_withdrawal
        # After the first deletion the B tail crosses under near its end. A
        # second deletion reuses the successful A anchor at s=15 mm and pulls
        # just inside that crossing, instead of moving both free ends apart.
        # The crossing and pickup coordinates are read from the live rope.
        try:
            for attempt in range(3):
                action = reachable_withdrawal(self, cfg)
                context = dict(k=k, attempt=attempt, kind='follow_up_withdrawal',
                               start_s=float(self.session.sim_time_s), route=action)
                self._end_context = context
                self._end_attempts.append(context)
                self._save_end_attempts()
                self.bias = {side: np.zeros(3) for side in self.bias}
                try:
                    before = len(self.crossings())
                    result = super().withdraw(k, action, cfg)
                    result.update(crossings_before=before, selection='live_follow_up_node_deletion')
                    context.update(status='completed', end_s=float(self.session.sim_time_s))
                    self._save_end_attempts()
                    return result
                except EndGraspFailure as error:
                    context.update(status='grasp_failed', error=str(error), end_s=float(self.session.sim_time_s))
                    self._save_end_attempts()
                    self._end_context = None
                    for side in tuple(self.grasps):
                        self.release(side, cfg.get('lift', .015), f'd{k}:follow_up_retry')
            raise EndGraspFailure('All three measured follow-up grasps failed; no unchecked pull executed')
        finally:
            self._end_context = None
