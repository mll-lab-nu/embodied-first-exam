"""Experimental under-strand pull with the opposite tail held by the robot.

The original nearby support point caused wrist collisions in the model audit.
This candidate holds the far tail instead. It remains unverified until an
actual continuous rollout passes contact, release and final shape checks.
The under-strand pulling idea follows https://arxiv.org/html/2011.04999;
the remote support and particular path are task-specific hypotheses.
"""
import numpy as np

from .geometry import projected_crossings
from .probe_actions import smoothstep
from .robot_probe import RobotGraspActions, rotation


PULL_ARC_M = .25
HOLD_TAIL_OFFSET_M = .015
PULL_DISTANCE_M = .40
PULL_DIRECTION = np.array([-1., 0., 0.])
HOVER_HEIGHT_M = .04
RIGHT_WITHDRAW = np.array([.05, 0., .08])
ADAPTIVE_ROUTES = ('remote_adaptive', 'remote_adaptive_spread')


def grasp_indices(centerline):
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centerline, axis=0), axis=1))]
    return [int(np.argmin(abs(arc-s))) for s in (PULL_ARC_M, arc[-1]-HOLD_TAIL_OFFSET_M)]


def declare_bands(rope, centerline):
    from topogym.primitives.fem_attachment import FEMRopeAttachment
    indices = grasp_indices(centerline)
    return indices, [FEMRopeAttachment(rope, centerline[i], radius=.008, strength=100.) for i in indices]


def initial_centerline(cfg):
    from omegaconf import OmegaConf
    from .geometry import KnotLayout
    points = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True)).centerline()
    yaw = np.radians(float(cfg.task.get('yaw_deg', 0.)))
    c, s = np.cos(yaw), np.sin(yaw)
    points[:, :2] = points[:, :2] @ np.array([[c, s], [-s, c]])
    floor = float(cfg.env.world.table.pos[2])+float(cfg.env.world.table.size[2])/2
    points += np.array([*cfg.task.origin_xy_m, floor])
    return points


def configure_untying_start(cfg):
    from .control import configure_initial_hover
    points = initial_centerline(cfg)
    positions = {side: (points[i], points[i+1]-points[i-1])
                 for side, i in zip(('left', 'right'), grasp_indices(points))}
    # A staging point slightly toward the left base stays inside the arm's
    # workspace before the initial loose curve has settled. The actual grasp
    # target is subsequently measured from the simulated rope.
    point, tangent = positions['left']
    positions['left'] = (point+[-.02, 0, 0], tangent)
    point, tangent = positions['right']
    positions['right'] = (point+[.03, 0, 0], tangent)
    result = configure_initial_hover(cfg, positions, height=HOVER_HEIGHT_M)
    result['left_initial_staging_offset_m'] = [-.02, 0, 0]
    result['right_initial_staging_offset_m'] = [.03, 0, 0]
    return result


class UntyingFixtureActions:
    """Isolate the rope action; this is never a robot qualification."""
    stage = 'settle'

    def __init__(self):
        self.bands, self.events, self.samples = [], [], []
        self.origins = None

    def specification(self):
        return dict(kind='experimental_remote_anchor_fixture', duration_s=33.,
                    pull_material_arc_m=PULL_ARC_M, hold_distance_from_far_end_m=HOLD_TAIL_OFFSET_M,
                    band_radius_m=.008, strength=100., settle_s=3., lift_m=.015,
                    pull_distance_m=PULL_DISTANCE_M, pull_direction=PULL_DIRECTION.tolist(),
                    release_s=28., post_release_s=5., robot_grasp_executed=False)

    def declare(self, base, rope, centerline, backend):
        self.ring_indices, self.bands = declare_bands(rope, centerline)

    def update(self, t):
        if t < 3.:
            return
        if self.origins is None:
            self.origins = [band.attach().copy() for band in self.bands]
            self.events.append(dict(time_s=t, event='engage_fixture'))
        if t < 5.:
            self.stage = 'lift'
            delta = np.array([0., 0., .015*smoothstep((t-3)/2)])
        elif t < 25.:
            self.stage = 'pull'
            delta = PULL_DIRECTION*PULL_DISTANCE_M*smoothstep((t-5)/20)+[0, 0, .015]
        elif t < 28.:
            self.stage = 'lower'
            delta = PULL_DIRECTION*PULL_DISTANCE_M+[0, 0, .015*(1-smoothstep((t-25)/3))]
        else:
            self.stage = 'released'
            if any(b.active for b in self.bands):
                for band in self.bands:
                    band.release()
                self.events.append(dict(time_s=t, event='release_all'))
            return
        self.bands[0].drive_to(self.origins[0]+delta)

    def observe(self, t, monitor):
        if monitor.count % max(1, round(.1/monitor.dt)) == 0:
            self.samples.append(dict(time_s=t, stage=self.stage, crossing_count=len(projected_crossings(monitor.last_centers))))
        if monitor.maxima['max_total_length_relative_change'] > .05:
            raise RuntimeError('Pull candidate exceeded the loaded length-change limit')

    def report(self):
        last = self.samples[-1] if self.samples else {}
        checks = dict(released=not any(b.active for b in self.bands),
                      final_no_projected_crossing=last.get('crossing_count') == 0,
                      post_release_observed=last.get('time_s', 0.) >= 33.-1e-8)
        return dict(kind='experimental_remote_anchor_fixture', checks=checks, passed=all(checks.values()),
                    events=self.events, final_active_constraints=sum(b.active for b in self.bands),
                    robot_grasp_executed=False, untying_fixture_only=True)


class RobotUntyingActions(RobotGraspActions):
    """Two physical grasps, under-strand pull, release and five-second check."""
    def __init__(self, *, route='remote_left', yaw_deg=0., spread_span_m=.78, spread_duration_s=20.):
        super().__init__()
        if not np.isfinite([spread_span_m, spread_duration_s]).all() or min(spread_span_m, spread_duration_s) <= 0:
            raise ValueError('Spread span and duration must be finite and positive')
        self.spread_span_m = float(spread_span_m)
        self.spread_duration_s = float(spread_duration_s)
        self.route = route
        self.pull_distance = PULL_DISTANCE_M
        self.pull_end = None
        self.extension_start = None
        self.finished_draw = None
        self.commanded_draw = 0.
        self.spread_start = None
        self.right_spread_m = 0.
        self.grasp_material_length_m = None
        if route in ('remote_left', 'remote_extended', *ADAPTIVE_ROUTES):
            self.pull_direction = PULL_DIRECTION.copy()
            self.left_withdraw = np.array([0., 0., .10])
            if route in ('remote_extended', *ADAPTIVE_ROUTES):
                self.pull_distance = .45
                self.left_withdraw = np.array([.06, 0., .08])
        elif route == 'understrand':
            yaw = np.radians(yaw_deg)
            c, s = np.cos(yaw), np.sin(yaw)
            transform = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            # The initial under-strand segment points away from its first
            # crossing approximately along (-2, +3) in the layout frame.
            # Preserve that direction when rotating the scene for arm reach.
            self.pull_direction = transform @ (np.array([-2., 3., 0.])/np.sqrt(13.))
            self.left_withdraw = transform @ np.array([.07, -.04, .08])
        else:
            raise ValueError(f'Unknown untying route: {route}')
        self.finished_draw = self.pull_distance

    def draw_distance(self, t):
        """Finish smooth strokes before deciding whether another is needed."""
        if t < 40.:
            self.commanded_draw = self.pull_distance*smoothstep((t-20)/20)
            return self.commanded_draw
        if self.pull_end is not None:
            return self.finished_draw
        if self.route not in ADAPTIVE_ROUTES:
            self.pull_end = 40.
            self.commanded_draw = self.finished_draw
            return self.finished_draw
        if self.spread_start is not None:
            if t >= self.spread_start+self.spread_duration_s-1e-8:
                self.pull_end = t
                self.events.append(dict(time_s=t, event='finish_pull', distance_m=self.finished_draw,
                                        crossing_count=len(projected_crossings(self.monitor.last_centers)),
                                        reason='spread_complete'))
            self.commanded_draw = self.finished_draw
            return self.finished_draw
        if self.extension_start is not None:
            u = (t-self.extension_start)/3.
            if u < 1.-1e-10:
                self.commanded_draw = self.finished_draw+.025*smoothstep(u)
                return self.commanded_draw
            self.finished_draw += .025
            self.extension_start = None
        crossings = len(projected_crossings(self.monitor.last_centers))
        if crossings == 0 or self.finished_draw >= .55-1e-8:
            if crossings and self.route == 'remote_adaptive_spread':
                self.start_spread(t)
            else:
                self.pull_end = t
                self.events.append(dict(time_s=t, event='finish_pull', distance_m=self.finished_draw,
                                        crossing_count=crossings, reason='clear' if crossings == 0 else 'distance_cap'))
        else:
            self.extension_start = t
            self.events.append(dict(time_s=t, event='extra_pull', from_distance_m=self.finished_draw,
                                    to_distance_m=self.finished_draw+.025, duration_s=3., crossing_count=crossings))
        self.commanded_draw = self.finished_draw
        return self.finished_draw

    def start_spread(self, t):
        """Open a residual loop without pulling the held material taut."""
        span = self.spread_span_m
        if self.grasp_material_length_m is None or span > .98*self.grasp_material_length_m:
            raise RuntimeError('Loop-spreading target leaves insufficient material slack')
        left = self.motion['left'][0]+self.pull_direction*self.finished_draw+[0, 0, .015]
        right = self.motion['right'][0]
        delta = left-right
        square = span**2-float(delta[1:] @ delta[1:])
        if square <= 0:
            raise RuntimeError('Loop-spreading target is incompatible with the grasp positions')
        spread = float(delta[0]+np.sqrt(square))
        if not 0. < spread <= .4:
            raise RuntimeError('Loop-spreading target lies outside the checked 400 mm envelope')
        if 1.5*spread/self.spread_duration_s > .03+1e-10:
            raise RuntimeError('Loop-spreading target exceeds the 30 mm/s speed limit')
        self.spread_start, self.right_spread_m = t, spread
        self.events.append(dict(time_s=t, event='spread_loop', left_draw_m=self.finished_draw,
                                right_spread_m=spread, target_span_m=span, duration_s=self.spread_duration_s))

    def right_displacement(self, t):
        return np.array([0. if self.spread_start is None else
                         self.right_spread_m*smoothstep((t-self.spread_start)/self.spread_duration_s), 0., 0.])

    def finished(self, t):
        return self.route in ADAPTIVE_ROUTES and self.pull_end is not None and t >= self.pull_end+11.-1e-8

    def specification(self):
        result = super().specification()
        result.update(duration_s=51., task='experimental_remote_anchor_understrand_pull',
                      route=self.route,
                      pull_material_arc_m=PULL_ARC_M, hold_distance_from_far_end_m=HOLD_TAIL_OFFSET_M,
                      pull_distance_m=self.pull_distance, pull_direction=self.pull_direction.tolist(),
                      maximum_pull_speed_m_s=1.5*self.pull_distance/20., hover_height_m=HOVER_HEIGHT_M,
                      lift_m=.015, right_withdraw_delta_m=RIGHT_WITHDRAW.tolist(),
                      left_withdraw_delta_m=self.left_withdraw.tolist(),
                      release_s=43., post_release_s=8.,
                      stages=[['settle', 0, 3], ['right_approach', 3, 5], ['right_lower', 5, 8],
                              ['right_close', 8, 10], ['left_approach', 10, 12], ['left_lower', 12, 15],
                              ['left_close', 15, 17], ['left_lift', 17, 20], ['pin_pull', 20, 40],
                              ['lower', 40, 43], ['release_withdraw', 43, 46], ['free_settle', 46, 51]])
        result.pop('tail_grasp_distances_m')
        if self.route in ADAPTIVE_ROUTES:
            result.update(duration_s=63., minimum_duration_s=51., release_s=None, post_release_s=8.,
                          maximum_pull_distance_m=.55, extra_stroke_m=.025, extra_stroke_duration_s=3.,
                          extra_stroke_max_speed_m_s=.0125,
                          stop_rule='at each completed stroke: no XY crossings, or 550 mm cap',
                          post_pull_sequence_s=dict(lower=3., withdraw=3., free_settle=5.))
            result['stages'] = result['stages'][:9]+[
                ['conditional_extra_pull', 40, 52],
                ['lower', 'pull_end', 'pull_end+3'],
                ['release_withdraw', 'pull_end+3', 'pull_end+6'],
                ['free_settle', 'pull_end+6', 'pull_end+11']]
            if self.route == 'remote_adaptive_spread':
                result.update(duration_s=63.+self.spread_duration_s, residual_loop_span_m=self.spread_span_m,
                              maximum_right_spread_m=.4, right_spread_duration_s=self.spread_duration_s,
                              maximum_right_spread_speed_m_s=.03,
                              stop_rule=f'complete smooth left strokes; if crossings remain at 550 mm, spread right hand to {1000*self.spread_span_m:g} mm span before release')
                result['stages'].insert(10, ['conditional_spread_loop', 52, 52+self.spread_duration_s])
        return result

    def declare(self, base, rope, centerline, backend):
        self.ring_indices, self.bands = declare_bands(rope, centerline)
        lo, hi = self.ring_indices
        self.grasp_material_length_m = float(np.linalg.norm(np.diff(centerline[lo:hi+1], axis=0), axis=1).sum())

    def update(self, t):
        if t < 3.:
            return
        if 'right' not in self.motion:
            self.motion['right'] = self.band_pose(1, 'right')
        right, rq = self.motion['right']
        right_delta = self.right_displacement(t)
        if t < 5.:
            self.stage = 'right_approach'
            self.approach('right', right+[0, 0, HOVER_HEIGHT_M], rq, (t-3)/2)
        elif t < 8.:
            self.stage = 'right_lower'
            self.move('right', right+[0, 0, HOVER_HEIGHT_M*(1-smoothstep((t-5)/3))], rq)
        elif t < 10.:
            self.stage = 'right_close'
            self.move('right', right, rq)
            self.close('right', 1, t, 8.)
        else:
            holding = self.pull_end is None or t < self.pull_end+3.
            if 1 not in self.owners and holding:
                raise RuntimeError('Support fingers did not establish a physical grasp')
            if holding:
                self.move('right', right+right_delta, rq)
            if 'left' not in self.motion:
                self.motion['left'] = self.band_pose(0, 'left')
            left, lq = self.motion['left']
            if t < 12.:
                self.stage = 'left_approach'
                self.approach('left', left+[0, 0, HOVER_HEIGHT_M], lq, (t-10)/2)
            elif t < 15.:
                self.stage = 'left_lower'
                self.move('left', left+[0, 0, HOVER_HEIGHT_M*(1-smoothstep((t-12)/3))], lq)
            elif t < 17.:
                self.stage = 'left_close'
                self.move('left', left, lq)
                self.close('left', 0, t, 15.)
            else:
                if 0 not in self.owners and holding:
                    raise RuntimeError('Pulling fingers did not establish a physical grasp')
                if t < 20.:
                    self.stage = 'left_lift'
                    delta = np.array([0., 0., .015*smoothstep((t-17)/3)])
                elif self.pull_end is None:
                    distance = self.draw_distance(t)
                    self.stage = ('spread_loop' if self.spread_start is not None else
                                  'pin_pull' if t < 40. else 'pin_pull_extra')
                    delta = self.pull_direction*distance+[0, 0, .015]
                elif t < self.pull_end+3.:
                    self.stage = 'lower'
                    delta = self.pull_direction*self.finished_draw+[0, 0, .015*(1-smoothstep((t-self.pull_end)/3))]
                else:
                    elapsed = t-self.pull_end-3.
                    self.stage = 'release_withdraw' if elapsed < 3. else 'free_settle'
                    self.release('left', t)
                    self.release('right', t)
                    delta = self.pull_direction*self.finished_draw+self.left_withdraw*smoothstep(elapsed/3)
                    self.move('right', right+right_delta+RIGHT_WITHDRAW*smoothstep(elapsed/3), rq)
                self.move('left', left+delta, lq)
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            self.bands[band]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band]))

    def observe(self, t, monitor):
        super().observe(t, monitor)
        if monitor.maxima['max_total_length_relative_change'] > .05:
            raise RuntimeError('Pull candidate exceeded the loaded length-change limit')

    def report(self):
        result = super().report()
        checks = result['checks']
        checks.pop('transfer_observed')
        checks['post_release_observed'] = bool(self.pull_end is not None and self.samples
                                               and self.samples[-1]['time_s'] >= self.pull_end+11.-1e-8)
        checks['final_no_projected_crossing'] = len(projected_crossings(self.monitor.last_centers)) == 0
        released = [curve for sample, curve in zip(self.monitor.samples, self.monitor.centers)
                    if self.pull_end is not None and sample['time_s'] >= self.pull_end+6.]
        checks['released_window_no_crossings'] = bool(released) and all(not projected_crossings(curve) for curve in released)
        result.update(passed=all(checks.values()), route=self.route,
                      pull_direction=self.pull_direction.tolist(),
                      last_pull_target_distance_m=self.commanded_draw, pull_finished_s=self.pull_end,
                      scope='experimental remote-tail anchor and under-strand pull; no transfer claimed')
        if self.route == 'remote_adaptive_spread':
            result.update(spread_started_s=self.spread_start, right_spread_target_m=self.right_spread_m,
                          spread_span_m=self.spread_span_m, spread_duration_s=self.spread_duration_s,
                          grasp_material_length_m=self.grasp_material_length_m)
        return result
