"""State-observed, contact-gated experimental routes for the new knot families.

These routes are candidates until their own continuous physical execution
passes. They never move rope nodes or overwrite simulated robot joint states.
"""
from dataclasses import dataclass, replace

import numpy as np
from omegaconf import OmegaConf

from .diagnostics import LIMITS
from .geometry import KnotLayout, projected_crossings, template_diagram_matches
from .probe_actions import smoothstep
from .robot_probe import RobotGraspActions, TOOL_OFFSET, rotation
from .untying import initial_centerline


@dataclass(frozen=True)
class FamilyRoute:
    route_id: str
    working_end: int
    maximum_regrasps: int
    stroke_m: float = .10
    stroke_s: float = 6.
    maximum_strokes_per_grasp: int = 5
    maximum_total_draw_m: float = 1.20
    support_offset_m: float | None = None
    lateral_clearance_m: float = 0.
    approach_finger_qpos_m: float | None = None
    preopen_upper_with_tail_anchor: bool = False
    preopen_lift_m: float = .06
    preopen_shift_m: tuple = (.12, 0., 0.)
    preopen_anchor_withdraw_m: tuple = (0., -.06, .07)
    preopen_maximum_extra_lift_m: float = 0.
    preopen_regrasp_clearance_m: float = .12
    regrasp_on_material_limits: bool = False
    track_regrasp_translation: bool = False
    spread_before_first_regrasp_m: float = 0.
    check_robot_clearance: bool = False
    preopen_clearance_shift_m: tuple = (0., 0., 0.)
    regrasp_pitch_candidates_deg: tuple = ()
    regrasp_hover_heights_m: tuple = (.04, .06, .08)


ROUTES = {
    'figure_eight': FamilyRoute('figure8_loosen_regrasp_unthread', 1, 2),
    'double_overhand': FamilyRoute('double_overhand_incremental_unwind', 0, 3),
}


def route_for_config(cfg):
    route = ROUTES[str(cfg.task.geometry.family)]
    settings = OmegaConf.to_container(cfg.task.get('route_settings', OmegaConf.create({})), resolve=True)
    route = replace(route, **settings)
    pitches = np.asarray(route.regrasp_pitch_candidates_deg)
    if pitches.ndim != 1 or not np.isfinite(pitches).all() or np.any(abs(pitches) > 60):
        raise ValueError('Regrasp pitch candidates must be finite angles within +/-60 degrees')
    if len(pitches) and not route.check_robot_clearance:
        raise ValueError('Pitched regrasp selection requires robot clearance checks')
    heights = np.asarray(route.regrasp_hover_heights_m)
    if (heights.ndim != 1 or not heights.size or not np.isfinite(heights).all()
            or np.any(heights < .02) or np.any(heights > .08)):
        raise ValueError('Regrasp hover candidates must be in [0.02, 0.08] m')
    if not np.isfinite(route.spread_before_first_regrasp_m) or route.spread_before_first_regrasp_m < 0:
        raise ValueError('Pre-regrasp support spread must be finite and nonnegative')
    if route.approach_finger_qpos_m is not None and not .012 < route.approach_finger_qpos_m <= .037:
        raise ValueError('Approach finger rail displacement must be in (0.012, 0.037] m')
    if route.preopen_upper_with_tail_anchor:
        delta = np.asarray(route.preopen_shift_m, dtype=float)
        clearance_shift = np.asarray(route.preopen_clearance_shift_m, dtype=float)
        if (clearance_shift.shape != (3,) or not np.isfinite(clearance_shift).all()
                or abs(clearance_shift[2]) > 1e-9):
            raise ValueError('Opening clearance shift must be a finite planar vector')
        withdrawal = np.asarray(route.preopen_anchor_withdraw_m, dtype=float)
        if (delta.shape != (3,) or not np.isfinite(delta).all() or abs(delta[2]) > 1e-9
                or np.linalg.norm(delta) <= 0 or not np.isfinite(route.preopen_lift_m)
                or route.preopen_lift_m <= 0 or route.maximum_regrasps < 1):
            raise ValueError('Anchored opening requires a positive lift, finite planar shift and a physical regrasp')
        if withdrawal.shape != (3,) or not np.isfinite(withdrawal).all() or withdrawal[2] <= 0:
            raise ValueError('Anchor withdrawal must rise above the released rope')
        if (not np.isfinite([route.preopen_maximum_extra_lift_m, route.preopen_regrasp_clearance_m]).all()
                or route.preopen_maximum_extra_lift_m < 0 or route.preopen_regrasp_clearance_m < .12):
            raise ValueError('Opening extensions must be bounded and cannot reduce the grasp-separation gate')
    return route


def material_arc(points):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]


def support_material_site(points, arc, route):
    if route.support_offset_m is None and not route.preopen_upper_with_tail_anchor:
        return float(arc[-1]-.015 if route.working_end == 0 else .015), None
    pairs = []
    for hit in projected_crossings(points):
        under = 1 if hit['first_over'] else 0
        values = [float(arc[i]+f*(arc[i+1]-arc[i]))
                  for i, f in zip(hit['segments'], hit['parameters'])]
        pairs.append((values[under], values[1-under]))
    if not pairs:
        raise ValueError('Local support requires an observed underpass')
    _, over = (min if route.working_end == 0 else max)(pairs, key=lambda pair: pair[0])
    if route.preopen_upper_with_tail_anchor:
        # Start on the upper strand, which is accessible from above; the tail
        # anchor holds the knot while that strand is lifted out of the way.
        return float(over), (max(.015, over-.015), min(float(arc[-1]-.015), over+.015))
    crossings = [s for pair in pairs for s in pair]
    lower = max([s for s in crossings if s < over-1e-6]+[.015])
    upper = min([s for s in crossings if s > over+1e-6]+[float(arc[-1]-.015)])
    bounds = (lower+.015, over-.015) if route.support_offset_m < 0 else (over+.015, upper-.015)
    if bounds[1] <= bounds[0]:
        raise ValueError('The overpassing branch has no isolated local support interval')
    return float(np.clip(over+route.support_offset_m, *bounds)), bounds


def first_under_grasp(points, arc, working_end, *, clearance_m=.025):
    """Choose just after the first underpass when walking from the free end.

    Material coordinates use the undeformed reference; crossing locations are
    measured from the current ordered centerline, including subsegment offsets.
    """
    under = []
    for hit in projected_crossings(points):
        side = 1 if hit['first_over'] else 0
        i, fraction = hit['segments'][side], hit['parameters'][side]
        under.append(arc[i]+fraction*(arc[i+1]-arc[i]))
    if not under:
        return None
    cross_s = min(under) if working_end == 0 else max(under)
    target_s = cross_s+clearance_m*(1 if working_end == 0 else -1)
    if not .015 < target_s < arc[-1]-.015:
        raise ValueError('The underpass leaves no material for a physical grasp')
    return float(target_s)


def initial_grasp_sites(cfg):
    route = route_for_config(cfg)
    points = initial_centerline(cfg)
    arc = material_arc(points)
    pull = first_under_grasp(points, arc, route.working_end)
    if route.preopen_upper_with_tail_anchor:
        pull = .015 if route.working_end == 0 else float(arc[-1]-.015)
    support, _ = support_material_site(points, arc, route)
    indices = [int(np.argmin(abs(arc-s))) for s in (pull, support)]
    return points, arc, indices


def configure_family_start(cfg):
    from .control import configure_initial_hover
    points, _, indices = initial_grasp_sites(cfg)
    # Initial hover is declared before build; contact is acquired after settle.
    result = configure_initial_hover(cfg, {
        side: (points[i], points[i+1]-points[i-1])
        for side, i in zip(('left', 'right'), indices)}, height=.04)
    result.update(family=str(cfg.task.geometry.family),
                  route_id=ROUTES[str(cfg.task.geometry.family)].route_id)
    return result


class FamilyUntyingActions(RobotGraspActions):
    def __init__(self, cfg):
        super().__init__()
        self.family = str(cfg.task.geometry.family)
        self.route = route_for_config(cfg)
        self.route_profile = cfg.task.get('route_profile')
        self.layout = KnotLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
        self.phase = 'settle'
        self.phase_start = 0.
        self.duration = 10.
        self.regrasps = self.strokes_at_grasp = self.total_strokes = 0
        self.total_draw = self.current_grasp_draw = 0.
        self.released_at = None
        self.final_observation_end = None
        self.constraint_samples = []
        self.previous_crossings = None
        self.support_band = self.pull_band = None
        self.phase_targets = {}
        self.pregrasp_settle_report = None
        self.support_lifted = False
        self.draw_tool_height = None
        self.support_hold_height = None
        self.worst_follow = None
        self.tail_anchor_acquired = False
        self.upper_opened = False
        self.opening_extra_lift = 0.
        self.support_spread_completed = False
        self.worst_robot_overlap = None
        self.grasp_hover_height = .04
        self.opening_clearance_shift_completed = False
        self.gripper_floor_geometries = None
        self.worst_gripper_floor_clearance = None

    def specification(self):
        return dict(kind='assisted_grasp', family=self.family, route_id=self.route.route_id,
            scope='experimental family route; success and difficulty require observed evidence',
            working_end=self.route.working_end, initial_unpinned_endpoints=2,
            initial_grasp=('working-end tail first, then upper strand at first underpass'
                if self.route.preopen_upper_with_tail_anchor else 'first underpass + 25 mm inward material; '+
                ('isolated overpassing branch' if self.route.support_offset_m is not None else 'opposite tip - 15 mm')),
            engagement='both physical IPC finger surfaces within contact d_hat before assistance',
            follow='measured gripper_link poses', maximum_planned_cartesian_segment_speed_m_s=.03,
            joint_space_approach_speed_covered_by_this_bound=False,
            commanded_joint_targets_recorded=True,
            stroke_m=self.route.stroke_m, stroke_s=self.route.stroke_s,
            maximum_regrasps=self.route.maximum_regrasps,
            maximum_total_draw_m=self.route.maximum_total_draw_m,
            maximum_strokes_per_grasp=self.route.maximum_strokes_per_grasp,
            route_profile=self.route_profile, support_offset_m=self.route.support_offset_m,
            lateral_clearance_m=self.route.lateral_clearance_m,
            approach_finger_qpos_m=self.route.approach_finger_qpos_m,
            preopen_upper_with_tail_anchor=self.route.preopen_upper_with_tail_anchor,
            preopen_lift_m=self.route.preopen_lift_m if self.route.preopen_upper_with_tail_anchor else None,
            preopen_shift_m=list(self.route.preopen_shift_m) if self.route.preopen_upper_with_tail_anchor else None,
            preopen_anchor_withdraw_m=(list(self.route.preopen_anchor_withdraw_m)
                                      if self.route.preopen_upper_with_tail_anchor else None),
            preopen_maximum_extra_lift_m=self.route.preopen_maximum_extra_lift_m,
            preopen_regrasp_clearance_m=self.route.preopen_regrasp_clearance_m,
            regrasp_on_material_limits=self.route.regrasp_on_material_limits,
            track_regrasp_translation=self.route.track_regrasp_translation,
            spread_before_first_regrasp_m=self.route.spread_before_first_regrasp_m,
            check_robot_clearance=self.route.check_robot_clearance,
            preopen_clearance_shift_m=list(self.route.preopen_clearance_shift_m),
            regrasp_pitch_candidates_deg=list(self.route.regrasp_pitch_candidates_deg),
            regrasp_hover_heights_m=list(self.route.regrasp_hover_heights_m),
            regrasp_robot_planning_clearance_m=.003 if self.route.check_robot_clearance else None,
            measured_robot_overlap_limit_m=.0005 if self.route.check_robot_clearance else None,
            regrasp_tracking_speed_m_s=.006 if self.route.track_regrasp_translation else None,
            regrasp_tracking_maximum_correction_m=.010 if self.route.track_regrasp_translation else None,
            underpass_material_margin_m=.008 if self.route.regrasp_on_material_limits else None,
            finger_qpos_semantics='ALOHA rail displacement, not physical jaw aperture',
            full_open_after_final_withdraw=True,
            pregrasp_free_settle_s=10., pregrasp_free_length_limit=LIMITS.rest_length_relative_change,
            feed_m=.012, feed_s=3., lift_m=.015, support_lift_m=.012,
            support_lift_once=True, support_minimum_table_clearance_m=.002, post_release_s=9.,
            draw_height_held_across_strokes=True,
            placement='measured lowest held-band vertex to 3 mm above table; empty hands stay clear',
            closed_loop='actual crossings, tangent and material slack at stroke boundaries; underpass and band pose before each grasp',
            force_control=False, diagnostic_projection='XY only',
            difficulty_qualified=False)

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        self.arc = material_arc(centerline)
        pull_s = first_under_grasp(centerline, self.arc, self.route.working_end)
        if self.route.preopen_upper_with_tail_anchor:
            pull_s = .015 if self.route.working_end == 0 else float(self.arc[-1]-.015)
        support_s, _ = support_material_site(centerline, self.arc, self.route)
        # Capacity only. Every band remains inactive until real finger contact.
        # A retreating underpass can move into a formerly straight tail. Keep
        # inactive capacity there as well; actual dual-contact gating is unchanged.
        candidates = sorted(set([pull_s, support_s, .015, self.arc[-1]-.015,
                                 *np.arange(.18, self.arc[-1]-.18, .025),
                                 *np.arange(.015, .18, .025),
                                 *np.arange(self.arc[-1]-.18, self.arc[-1]-.015, .025)]))
        self.ring_indices = sorted(set(int(np.argmin(abs(self.arc-s))) for s in candidates))
        self.support_band = int(np.argmin([abs(self.arc[i]-support_s) for i in self.ring_indices]))
        self.pull_band = int(np.argmin([abs(self.arc[i]-pull_s) for i in self.ring_indices]))
        self.bands = [FEMRopeAttachment(rope, centerline[i], radius=.008, strength=100.)
                      for i in self.ring_indices]

    def configure(self, task, controller, monitor):
        super().configure(task, controller, monitor)
        if self.route.regrasp_pitch_candidates_deg:
            from .robot_clearance import gripper_geometry
            self.gripper_floor_geometries = {side: gripper_geometry(self.ik, side) for side in controller.arms}
        self.commanded_qpos = {side: np.asarray(controller.cfg.home[side][:6]).copy()
                               for side in controller.arms}
        if np.intersect1d(self.bands[self.pull_band].indices, self.bands[self.support_band].indices).size:
            raise ValueError('Initial grasp bands overlap material vertices')

    def move(self, side, position, quat):
        super().move(side, position, quat)
        self.commanded_qpos[side] = self.ik.previous[side].copy()

    def approach(self, side, position, quat, fraction):
        super().approach(side, position, quat, fraction)
        start, end = self.approaches[side]
        u = float(smoothstep(fraction))
        self.commanded_qpos[side] = (1-u)*start+u*end

    def release(self, side, t):
        # Release the band first, open enough to clear the strand, and withdraw
        # before the final full opening so adjacent loops are not swept aside.
        super().release(side, t, open_qpos=self.route.approach_finger_qpos_m)

    def _transition(self, phase, duration, t):
        self.phase, self.phase_start, self.duration = phase, t, duration
        self.phase_targets = {}
        self.events.append(dict(time_s=t, event='phase', phase=phase,
                                planned_duration_s=duration,
                                crossings=len(projected_crossings(self.monitor.last_centers))))

    def _hold(self, side):
        if side in self.motion:
            point, quat = self.motion[side]
            self.move(side, point, quat)

    def _record_motion(self, side):
        arm = self.controller.arms[side]
        self.motion[side] = (self.tool_position(arm).copy(), arm.hand_quat().copy())

    def _pull_band_candidates(self, *, minimum_separation_m=.12):
        points = self.monitor.last_centers
        target = first_under_grasp(points, self.arc, self.route.working_end)
        if target is None:
            return None
        support = points[self.ring_indices[self.support_band]]
        choices = []
        for band, index in enumerate(self.ring_indices):
            if band == self.support_band or abs(self.arc[index]-target) > .040:
                continue
            if np.linalg.norm(points[index]-support) < minimum_separation_m:
                continue
            if np.intersect1d(self.bands[band].indices, self.bands[self.support_band].indices).size:
                continue
            choices.append((abs(self.arc[index]-target), band))
        return choices

    def _choose_pull_band(self):
        choices = self._pull_band_candidates()
        if choices is None:
            return False
        if not choices:
            raise RuntimeError('No declared underpass band has safe two-gripper separation')
        self.pull_band = min(choices)[1]
        return True

    def _finish_or_extend_opening(self, t):
        """Keep the tail anchor until observed grasp geometry has clearance."""
        if self.route.preopen_maximum_extra_lift_m:
            choices = self._pull_band_candidates(
                minimum_separation_m=self.route.preopen_regrasp_clearance_m)
            if choices == []:
                remaining = self.route.preopen_maximum_extra_lift_m-self.opening_extra_lift
                if remaining < 1e-6:
                    raise RuntimeError('Opening lift budget exhausted without a separated underpass grasp')
                step = min(.02, remaining)
                start, quat = self.motion['right']
                end = start+np.array([0., 0., step])
                length = abs(self.arc[self.ring_indices[self.pull_band]]-
                             self.arc[self.ring_indices[self.support_band]])
                if np.linalg.norm(end-self.motion['left'][0]) > .96*length:
                    raise RuntimeError('Extra opening lift would exhaust anchored material slack')
                previous = self.ik.previous['right'].copy()
                try:
                    self.ik.solve('right', end-rotation(quat).apply(TOOL_OFFSET), quat)
                finally:
                    self.ik.previous['right'] = previous
                self.opening_extra_lift += step
                self._transition('open_upper_clearance', max(2., 1.5*step/.025), t)
                self.phase_targets['right'] = (start.copy(), end, quat)
                self.events.append(dict(time_s=t, event='observed_opening_clearance_extension',
                    additional_lift_m=step, accumulated_extra_lift_m=self.opening_extra_lift,
                    required_candidate_separation_m=self.route.preopen_regrasp_clearance_m))
                return
        shift = np.asarray(self.route.preopen_clearance_shift_m)
        if not self.opening_clearance_shift_completed and np.linalg.norm(shift) > 1e-9:
            if self.owners.get(self.pull_band) != 'left' or self.owners.get(self.support_band) != 'right':
                raise RuntimeError('Opening clearance shift requires both physical grasps')
            start, quat = self.motion['right']
            end = start+shift
            length = abs(self.arc[self.ring_indices[self.pull_band]]-
                         self.arc[self.ring_indices[self.support_band]])
            if np.linalg.norm(end-self.motion['left'][0]) > .96*length:
                raise RuntimeError('Opening clearance shift would exhaust anchored material slack')
            previous = self.ik.previous['right'].copy()
            try:
                self.ik.solve('right', end-rotation(quat).apply(TOOL_OFFSET), quat)
            finally:
                self.ik.previous['right'] = previous
            self._transition('open_upper_clearance_shift', max(6., 1.5*np.linalg.norm(shift)/.025), t)
            self.phase_targets['right'] = (start.copy(), end, quat)
            self.events.append(dict(time_s=t, event='opening_robot_clearance_shift',
                shift_m=shift.tolist(), endpoint_m=end.tolist(),
                both_grasp_owners=dict(self.owners)))
            return
        self.upper_opened = True
        self.release('left', t)
        self._record_motion('left')
        self.regrasps += 1
        self._transition('anchor_regrasp_raise',
            max(4., 1.5*np.linalg.norm(self.route.preopen_anchor_withdraw_m)/.025), t)

    def _choose_support_band(self):
        if self.route.support_offset_m is None and not self.route.preopen_upper_with_tail_anchor:
            return
        points = self.monitor.last_centers
        target, bounds = support_material_site(points, self.arc, self.route)
        choices = [(abs(self.arc[i]-target), band) for band, i in enumerate(self.ring_indices)
                   if bounds[0] <= self.arc[i] <= bounds[1] and abs(self.arc[i]-target) <= .025]
        if not choices:
            raise RuntimeError('No declared band remains on the observed local overpassing branch')
        self.support_band = min(choices)[1]

    def _start_lateral_clearance(self, t):
        self._record_motion('left')
        points = self.monitor.last_centers
        i = self.ring_indices[self.pull_band]
        tangent = (points[i+1]-points[i-1])*(1 if self.route.working_end == 0 else -1)
        tangent[2] = 0.
        if np.linalg.norm(tangent) < 1e-8:
            raise RuntimeError('Degenerate strand tangent before lateral clearance')
        tangent /= np.linalg.norm(tangent)
        direction = np.cross([0., 0., 1.], tangent)
        start, quat = self.motion['left']
        support = self.motion['right'][0]
        if direction @ (start-support) < 0:
            direction *= -1
        end = start+direction*self.route.lateral_clearance_m
        length = abs(self.arc[i]-self.arc[self.ring_indices[self.support_band]])
        if np.linalg.norm(end-support) > .96*length:
            raise RuntimeError('Lateral clearance would exhaust the available material slack')
        previous = self.ik.previous['left'].copy()
        try:
            self.ik.solve('left', end-rotation(quat).apply(TOOL_OFFSET), quat)
        finally:
            self.ik.previous['left'] = previous
        self._transition('lateral_clearance', max(6., 1.5*self.route.lateral_clearance_m/.025), t)
        self.phase_targets['left'] = (start.copy(), end, quat)
        self.events.append(dict(time_s=t, event='observed_lateral_target', direction=direction.tolist(),
            endpoint_m=end.tolist(), support_band=self.support_band,
            reference_material_slack_m=length-float(np.linalg.norm(end-support))))

    def _checked_regrasp_candidate(self, side):
        from scipy.spatial.transform import Rotation
        from .robot_clearance import checked_grasp_approach
        choices = sorted(self._pull_band_candidates() or [])
        target = first_under_grasp(self.monitor.last_centers, self.arc, self.route.working_end)
        sign = 1 if self.route.working_end == 0 else -1
        for _, band in choices:
            inward = sign*(self.arc[self.ring_indices[band]]-target)+.025
            if inward < .008:
                continue
            point, quat = self.band_pose(band, side)
            for pitch in self.route.regrasp_pitch_candidates_deg:
                for flip in (False, True):
                    base = rotation(quat)*(Rotation.from_rotvec([np.pi, 0., 0.])
                                           if flip else Rotation.identity())
                    orientation = base*Rotation.from_euler('y', pitch, degrees=True)
                    candidate = orientation.as_quat()[[3, 0, 1, 2]]
                    event = dict(time_s=self.monitor.count*self.monitor.dt, band=band,
                        pitch_deg=float(pitch), flipped_tangent=flip,
                        inward_of_first_underpass_m=float(inward))
                    try:
                        checked = checked_grasp_approach(self.ik, self.controller, side, point, candidate,
                            self.route.approach_finger_qpos_m or .037, floor_height_m=self.monitor.floor,
                            hover_heights_m=self.route.regrasp_hover_heights_m)
                    except ValueError as exc:
                        self.events.append(dict(event='regrasp_candidate_rejected', reason=str(exc), **event))
                        continue
                    self.events.append(dict(event='observed_regrasp_candidate_selected', **event))
                    return band, (point, candidate), checked
        raise ValueError('No observed underpass band and pitched pose passed robot/table clearance')

    def _prepare_grasp(self, side):
        band = self.support_band if side == 'right' else self.pull_band
        checked = None
        if side == 'left' and self.regrasps and self.route.regrasp_pitch_candidates_deg:
            band, self.grasp_target, checked = self._checked_regrasp_candidate(side)
            self.pull_band = band
        else:
            self.grasp_target = self.band_pose(band, side)
        self.grasp_target_origin = self.grasp_target[0].copy()
        self.grasp_tracking_last_time = None
        self.approaches.pop(side, None)
        self.approach_finger_start = float(self.controller.arms[side].gripper_qpos()[0])
        self.grasp_hover_height = .04
        if self.route.check_robot_clearance and self.regrasps:
            from .robot_clearance import checked_grasp_approach
            if checked is None:
                checked = checked_grasp_approach(self.ik, self.controller, side, *self.grasp_target,
                    self.route.approach_finger_qpos_m or .037,
                    hover_heights_m=self.route.regrasp_hover_heights_m)
            self.grasp_hover_height = checked['hover_height_m']
            self.approaches[side] = (checked['start_qpos'], checked['end_qpos'])
            self.events.append(dict(event='checked_robot_regrasp_approach', side=side,
                time_s=self.monitor.count*self.monitor.dt, hover_height_m=self.grasp_hover_height,
                minimum_checked_clearance_m=checked['minimum_checked_clearance_m'],
                minimum_checked_table_clearance_m=checked['minimum_checked_table_clearance_m'],
                scope=checked['scope']))
        self.events.append(dict(event='observed_grasp_target', side=side, band=band,
            reference_arc_m=float(self.arc[self.ring_indices[band]]),
            tool_target_m=self.grasp_target[0].tolist(), tool_quaternion_wxyz=self.grasp_target[1].tolist(),
            time_s=self.monitor.count*self.monitor.dt))

    def _track_regrasp_translation(self, side, t):
        if (not self.route.track_regrasp_translation or not self.regrasps or side != 'left'
                or self.owners.get(self.pull_band) == side):
            return
        desired = self.monitor.last_positions[self.bands[self.pull_band].indices].mean(axis=0)
        if np.linalg.norm(desired-self.grasp_target_origin) > .010:
            raise RuntimeError('Unheld regrasp band moved beyond the 10 mm tracking envelope')
        if self.grasp_tracking_last_time is None:
            self.grasp_tracking_last_time = t
            return
        dt = t-self.grasp_tracking_last_time
        self.grasp_tracking_last_time = t
        if dt < 0:
            raise ValueError('Regrasp tracking requires increasing simulation time')
        point, quat = self.grasp_target
        delta = desired-point
        distance = float(np.linalg.norm(delta))
        if distance:
            point = point+delta*min(1., .006*dt/distance)
        # Only command the robot target. The free FEM band is never moved or
        # attached here, and the pose stops tracking once dual contact engages.
        self.grasp_target = (point, quat)

    def _start_draw(self, t):
        self._record_motion('left')
        points = self.monitor.last_centers
        i = self.ring_indices[self.pull_band]
        direction = (points[i+1]-points[i-1])*(1 if self.route.working_end == 0 else -1)
        direction[2] = 0.
        if np.linalg.norm(direction) < 1e-8:
            raise RuntimeError('Degenerate observed under-strand tangent')
        direction /= np.linalg.norm(direction)
        if self.strokes_at_grasp:
            # Continue the strand's observed direction of extraction, oriented
            # consistently with the previous stroke to avoid a sudden reversal.
            if direction @ self.draw_direction < 0:
                direction *= -1
            direction = direction+self.draw_direction
            direction /= np.linalg.norm(direction)
        self.draw_direction = direction
        start, quat = self.motion['left']
        end = start+direction*self.route.stroke_m
        lowest = float(self.monitor.last_positions[self.bands[self.pull_band].indices, 2].min())
        if self.draw_tool_height is None:
            self.draw_tool_height = float(start[2])
        # Re-anchoring XY to the measured pose must not accumulate vertical
        # tracking error over successive horizontal strokes.
        self.draw_tool_height = max(self.draw_tool_height, float(start[2])+self.monitor.floor+.003-lowest)
        end[2] = self.draw_tool_height
        if 1.5*np.linalg.norm(end-start)/self.route.stroke_s > .03:
            raise RuntimeError('Observed clearance correction exceeds the planned Cartesian speed bound')
        support = self.motion['right'][0]
        length = abs(self.arc[self.ring_indices[self.pull_band]]-self.arc[self.ring_indices[self.support_band]])
        if np.linalg.norm(end-support) > .96*length:
            if self.route.regrasp_on_material_limits and self.strokes_at_grasp:
                return False
            raise RuntimeError('Next stroke would exhaust the available material slack')
        if self.current_grasp_draw+self.route.stroke_m > .55+1e-9:
            if self.route.regrasp_on_material_limits and self.strokes_at_grasp:
                return False
            raise RuntimeError('Current grasp reached the checked 550 mm motion envelope')
        # Solve the endpoint before committing a new physical stroke.
        previous = self.ik.previous['left'].copy()
        try:
            self.ik.solve('left', end-rotation(quat).apply(TOOL_OFFSET), quat)
        finally:
            self.ik.previous['left'] = previous
        self.previous_crossings = len(projected_crossings(points))
        self._transition('draw_layer', self.route.stroke_s, t)
        self.phase_targets['left'] = (start.copy(), end, quat)
        self.events.append(dict(time_s=t, event='observed_draw_target', direction=direction.tolist(),
                                endpoint_m=end.tolist(), pull_band=self.pull_band,
                                reference_material_slack_m=length-float(np.linalg.norm(end-support))))
        return True

    def _held_band_reached_underpass(self):
        target = first_under_grasp(self.monitor.last_centers, self.arc, self.route.working_end)
        if target is None:
            return False
        sign = 1 if self.route.working_end == 0 else -1
        held = self.arc[self.ring_indices[self.pull_band]]
        # The band must remain inward of the first underpass. Once that
        # crossing is passed, drawing an outer-tail grasp can retighten the
        # remaining knot. Use an 8 mm reference-arc margin, on the scale of
        # the attachment's nominal spatial radius.
        return sign*(held-target)+.025 < .008

    def _begin_regrasp(self, t, reason):
        if self.route.spread_before_first_regrasp_m and not self.support_spread_completed:
            if self.owners.get(self.pull_band) != 'left' or self.owners.get(self.support_band) != 'right':
                raise RuntimeError('Pre-regrasp support spread requires both physical grasps')
            self._record_motion('left')
            self._record_motion('right')
            if self.draw_tool_height is not None:
                point, quat = self.motion['left']
                point = point.copy()
                point[2] = self.draw_tool_height
                self.motion['left'] = (point, quat)
            self._preserve_support_height()
            start, quat = self.motion['right']
            direction = start-self.motion['left'][0]
            direction[2] = 0.
            if np.linalg.norm(direction) < 1e-8:
                raise RuntimeError('Pre-regrasp support spread has no observed planar direction')
            direction /= np.linalg.norm(direction)
            end = start+direction*self.route.spread_before_first_regrasp_m
            length = abs(self.arc[self.ring_indices[self.pull_band]]-
                         self.arc[self.ring_indices[self.support_band]])
            if np.linalg.norm(end-self.motion['left'][0]) > .96*length:
                raise RuntimeError('Pre-regrasp support spread would exhaust material slack')
            previous = self.ik.previous['right'].copy()
            try:
                self.ik.solve('right', end-rotation(quat).apply(TOOL_OFFSET), quat)
            finally:
                self.ik.previous['right'] = previous
            self._transition('spread_before_regrasp',
                max(6., 1.5*self.route.spread_before_first_regrasp_m/.025), t)
            self.phase_targets['right'] = (start.copy(), end, quat)
            self.events.append(dict(event='observed_support_spread', time_s=t, reason=reason,
                direction=direction.tolist(), endpoint_m=end.tolist(),
                reference_material_slack_m=length-float(np.linalg.norm(end-self.motion['left'][0]))))
            return
        if self.regrasps >= self.route.maximum_regrasps:
            raise RuntimeError('Family route exhausted its allowed physical regrasps')
        self.events.append(dict(time_s=t, event='regrasp_decision', reason=reason,
                                previous_band=self.pull_band))
        self.release('left', t)
        self._record_motion('left')
        self.regrasps += 1
        self._transition('regrasp_raise', 4., t)

    def _begin_release(self, t):
        for side in ('left', 'right'):
            self._record_motion(side)
        targets = {}
        for side in ('left', 'right'):
            start, quat = self.motion[side]
            end = start.copy()
            held = [band for band, owner in self.owners.items() if owner == side]
            if held:
                lowest = min(float(self.monitor.last_positions[self.bands[band].indices, 2].min())
                             for band in held)
                # Tool center and held rope center do not coincide after real
                # finger contact. Use observed material geometry for placement.
                end[2] += self.monitor.floor+.003-lowest
            targets[side] = (start.copy(), end, quat)
        travel = max(abs(end[2]-start[2]) for start, end, _ in targets.values())
        self._transition('lower_release', max(3., 1.5*travel/.03), t)
        self.phase_targets = targets

    def _preserve_support_height(self):
        point, quat = self.motion['right']
        if self.support_hold_height is None:
            self.support_hold_height = float(point[2])
        point = point.copy()
        point[2] = self.support_hold_height
        self.motion['right'] = (point, quat)

    def _check_support_clearance(self):
        clearance = float(self.monitor.last_positions[self.bands[self.support_band].indices, 2].min()
                          - self.monitor.floor)
        if clearance < .002:
            raise RuntimeError('Support strand still against the table; refusing to feed it laterally')

    def _advance(self, t):
        phase = self.phase
        if phase == 'settle':
            report = self.monitor.report()
            report['checks']['total_length'] = (
                self.monitor.maxima['max_total_length_relative_change'] < LIMITS.rest_length_relative_change)
            report['checks']['task_preserved'] = template_diagram_matches(
                projected_crossings(self.monitor.last_centers), self.family)
            report['mechanical_checks_passed'] = all(report['checks'].values())
            self.pregrasp_settle_report = report
            if not report['mechanical_checks_passed']:
                failed = [key for key, passed in report['checks'].items() if not passed]
                raise RuntimeError(f'Canonical scene failed its pre-grasp free-settle gate: {failed}')
            self._choose_support_band()
            if self.route.preopen_upper_with_tail_anchor:
                self._prepare_grasp('left')
                self._transition('left_approach', 2., t)
            elif not self._choose_pull_band():
                raise RuntimeError('The knot released itself before robot manipulation')
            else:
                self._prepare_grasp('right')
                self._transition('right_approach', 2., t)
        elif phase.endswith('_approach'):
            # Leave 6 mm/s of the existing 30 mm/s Cartesian bound for
            # translation tracking when a higher checked hover is selected.
            self._transition(phase.replace('approach', 'lower'),
                max(3., 1.5*self.grasp_hover_height/.024), t)
        elif phase in ('left_lower', 'right_lower'):
            self._transition(phase.replace('lower', 'close'), 2., t)
        elif phase == 'right_close':
            if self.owners.get(self.support_band) != 'right':
                raise RuntimeError('Support hand did not acquire both-finger contact')
            self._record_motion('right')
            if self.route.preopen_upper_with_tail_anchor and not self.upper_opened:
                self._transition('open_upper_lift', max(4., 1.5*self.route.preopen_lift_m/.025), t)
            else:
                self._prepare_grasp('left')
                self._transition('left_approach', 2., t)
        elif phase == 'left_close':
            if self.owners.get(self.pull_band) != 'left':
                raise RuntimeError('Manipulating hand did not acquire both-finger contact')
            self._record_motion('left')
            if self.route.preopen_upper_with_tail_anchor and not self.tail_anchor_acquired:
                self.tail_anchor_acquired = True
                self._transition('anchor_lift', 3., t)
            else:
                self.strokes_at_grasp = 0
                self.current_grasp_draw = 0.
                self.draw_tool_height = None
                self._transition('lift_understrand', 3., t)
        elif phase == 'anchor_lift':
            self._record_motion('left')
            clearance = float(self.monitor.last_positions[self.bands[self.pull_band].indices, 2].min()
                              - self.monitor.floor)
            if clearance < .002:
                raise RuntimeError('Tail anchor remains against the table before upper-strand opening')
            self._choose_support_band()
            self._prepare_grasp('right')
            self._transition('right_approach', 2., t)
        elif phase == 'open_upper_lift':
            self._record_motion('right')
            self._check_support_clearance()
            self._preserve_support_height()
            self.support_lifted = True
            start, quat = self.motion['right']
            end = start+np.asarray(self.route.preopen_shift_m)
            length = abs(self.arc[self.ring_indices[self.pull_band]]-
                         self.arc[self.ring_indices[self.support_band]])
            if np.linalg.norm(end-self.motion['left'][0]) > .96*length:
                raise RuntimeError('Upper-strand opening would exhaust anchored material slack')
            previous = self.ik.previous['right'].copy()
            try:
                self.ik.solve('right', end-rotation(quat).apply(TOOL_OFFSET), quat)
            finally:
                self.ik.previous['right'] = previous
            self._transition('open_upper_shift', max(6., 1.5*np.linalg.norm(end-start)/.025), t)
            self.phase_targets['right'] = (start.copy(), end, quat)
        elif phase == 'open_upper_shift':
            self._record_motion('right')
            self._preserve_support_height()
            self._finish_or_extend_opening(t)
        elif phase == 'open_upper_clearance':
            self.support_hold_height = float(self.phase_targets['right'][1][2])
            self._record_motion('right')
            self._check_support_clearance()
            self._preserve_support_height()
            self._finish_or_extend_opening(t)
        elif phase == 'open_upper_clearance_shift':
            self.opening_clearance_shift_completed = True
            self._record_motion('right')
            self._check_support_clearance()
            self._preserve_support_height()
            self._finish_or_extend_opening(t)
        elif phase == 'lift_understrand':
            self._record_motion('left')
            self._record_motion('right')
            self._check_support_clearance()
            self._preserve_support_height()
            self.support_lifted = True
            self._transition('feed_slack', 3., t)
        elif phase == 'feed_slack':
            self._record_motion('right')
            self._preserve_support_height()
            if self.route.lateral_clearance_m:
                self._start_lateral_clearance(t)
            else:
                self._start_draw(t)
        elif phase == 'lateral_clearance':
            self.total_draw += self.route.lateral_clearance_m
            self.current_grasp_draw += self.route.lateral_clearance_m
            if not projected_crossings(self.monitor.last_centers):
                self._begin_release(t)
            else:
                self._start_draw(t)
        elif phase == 'draw_layer':
            self._record_motion('left')
            self.strokes_at_grasp += 1
            self.total_strokes += 1
            self.current_grasp_draw += self.route.stroke_m
            self.total_draw += self.route.stroke_m
            count = len(projected_crossings(self.monitor.last_centers))
            if not count:
                self._begin_release(t)
            else:
                if self.total_draw >= self.route.maximum_total_draw_m-1e-9:
                    raise RuntimeError('Family route reached its total draw limit with crossings remaining')
                changed_layer = self.previous_crossings-count >= 2
                changed_underpass = (self.route.regrasp_on_material_limits
                                     and self._held_band_reached_underpass())
                regrasp = ((self.family == 'double_overhand' and changed_layer)
                           or changed_underpass
                           or self.strokes_at_grasp >= self.route.maximum_strokes_per_grasp)
                if regrasp:
                    self._begin_regrasp(t, 'held_band_reached_underpass' if changed_underpass
                        else 'crossing_layer_changed' if self.family == 'double_overhand' and changed_layer
                        else 'strokes_per_grasp')
                else:
                    if self._start_draw(t) is False:
                        self._begin_regrasp(t, 'next_stroke_exceeds_existing_material_or_travel_limit')
        elif phase in ('regrasp_raise', 'anchor_regrasp_raise'):
            if not self._choose_pull_band():
                self._begin_release(t)
            else:
                self._prepare_grasp('left')
                self._transition('left_approach', 3., t)
        elif phase == 'spread_before_regrasp':
            self.support_spread_completed = True
            self._record_motion('right')
            self._preserve_support_height()
            if not projected_crossings(self.monitor.last_centers):
                self._begin_release(t)
            else:
                self._begin_regrasp(t, 'observed_after_support_spread')
        elif phase == 'lower_release':
            for side in ('left', 'right'):
                self._record_motion(side)
                self.release(side, t)
            self.released_at = t
            self.final_observation_end = t+9.
            self._transition('release_withdraw', 4., t)
        elif phase == 'release_withdraw':
            for side in ('left', 'right'):
                self._record_motion(side)
            self._transition('post_release', 5., t)

    def update(self, t):
        if t >= self.phase_start+self.duration-1e-8 and self.phase != 'post_release':
            self._advance(t)
        self.stage = self.phase
        u = smoothstep((t-self.phase_start)/self.duration)
        if self.phase.startswith(('left_', 'right_')):
            side = self.phase.split('_')[0]
            other = 'right' if side == 'left' else 'left'
            self._hold(other)
            if self.phase.endswith(('lower', 'close')):
                self._track_regrasp_translation(side, t)
            point, quat = self.grasp_target
            if self.phase.endswith('approach'):
                self.approach(side, point+[0, 0, self.grasp_hover_height], quat, (t-self.phase_start)/self.duration)
                if self.route.approach_finger_qpos_m is not None:
                    self.controller.arms[side].set_gripper(self.approach_finger_start+
                        (self.route.approach_finger_qpos_m-self.approach_finger_start)*u)
            elif self.phase.endswith('lower'):
                self.move(side, point+[0, 0, self.grasp_hover_height*(1-u)], quat)
                if self.route.approach_finger_qpos_m is not None:
                    self.controller.arms[side].set_gripper(self.route.approach_finger_qpos_m)
            else:
                self.move(side, point, quat)
                self.close(side, self.pull_band if side == 'left' else self.support_band, t, self.phase_start,
                           start_qpos=self.route.approach_finger_qpos_m)
        elif self.phase == 'anchor_lift':
            self._hold('right')
            point, quat = self.motion['left']
            self.move('left', point+[0, 0, .012*u], quat)
        elif self.phase == 'open_upper_lift':
            self._hold('left')
            point, quat = self.motion['right']
            self.move('right', point+[0, 0, self.route.preopen_lift_m*u], quat)
        elif self.phase in ('open_upper_shift', 'open_upper_clearance',
                            'open_upper_clearance_shift', 'spread_before_regrasp'):
            self._hold('left')
            start, end, quat = self.phase_targets['right']
            self.move('right', start+(end-start)*u, quat)
        elif self.phase == 'lift_understrand':
            for side, height in (('left', .015), ('right', 0. if self.support_lifted else .012)):
                point, quat = self.motion[side]
                self.move(side, point+[0, 0, height*u], quat)
        elif self.phase in ('regrasp_raise', 'anchor_regrasp_raise'):
            self._hold('right')
            point, quat = self.motion['left']
            delta = (np.asarray(self.route.preopen_anchor_withdraw_m)
                     if self.phase == 'anchor_regrasp_raise' else np.array([0., 0., .07]))
            self.move('left', point+delta*u, quat)
        elif self.phase == 'feed_slack':
            self._hold('left')
            point, quat = self.motion['right']
            direction = self.motion['left'][0]-point
            direction[2] = 0.
            direction /= np.linalg.norm(direction)
            self.move('right', point+direction*.012*u, quat)
        elif self.phase in ('draw_layer', 'lateral_clearance'):
            self._hold('right')
            start, end, quat = self.phase_targets['left']
            self.move('left', start+(end-start)*u, quat)
        elif self.phase == 'lower_release':
            for side, (start, end, quat) in self.phase_targets.items():
                self.move(side, start+(end-start)*u, quat)
        elif self.phase == 'release_withdraw':
            for side in ('left', 'right'):
                point, quat = self.motion[side]
                self.move(side, point+[0, 0, .08*u], quat)
        elif self.phase == 'post_release':
            for side in ('left', 'right'):
                self._hold(side)
                if self.route.approach_finger_qpos_m is not None:
                    self.controller.arms[side].open_gripper()
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            self.bands[band]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band]))

    def observe(self, t, monitor):
        super().observe(t, monitor)
        if self.route.check_robot_clearance:
            from .robot_clearance import measured_robot_overlap
            overlap = measured_robot_overlap(self.ik, self.controller,
                floor_height_m=monitor.floor, gripper_geometries=self.gripper_floor_geometries)
            if self.gripper_floor_geometries is not None:
                gap = overlap['gripper_floor_clearance_m']
                if self.worst_gripper_floor_clearance is None or gap < self.worst_gripper_floor_clearance['gap_m']:
                    self.worst_gripper_floor_clearance = dict(time_s=t, phase=self.phase, gap_m=gap)
                if gap < -LIMITS.table_penetration_m:
                    raise RuntimeError('Measured gripper geometry exceeds the frozen table-penetration limit')
            if self.worst_robot_overlap is None or overlap['penetration_m'] > self.worst_robot_overlap['penetration_m']:
                self.worst_robot_overlap = dict(time_s=t, phase=self.phase, **overlap)
            if overlap['penetration_m'] > .0005:
                raise RuntimeError('Measured robot poses exceed the 0.5 mm robot-overlap limit')
        self.samples[-1]['commanded_arm_qpos'] = {side: values.tolist()
                                                for side, values in self.commanded_qpos.items()}
        errors = {}
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            targets = arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band])
            distances = np.linalg.norm(monitor.last_positions[self.bands[band].indices]-targets, axis=1)
            index = int(np.argmax(distances))
            errors[side] = float(distances[index])
            if self.worst_follow is None or errors[side] > self.worst_follow['error_m']:
                self.worst_follow = dict(time_s=t, side=side, band=band,
                    material_vertex=int(self.bands[band].indices[index]), error_m=errors[side])
        self.samples[-1]['grasp_follow_error_m'] = errors
        if monitor.maxima['max_total_length_relative_change'] > .05:
            raise RuntimeError('Family route exceeded the frozen loaded length-change limit')
        if monitor.min_J <= LIMITS.min_volume_ratio:
            raise RuntimeError('Family route crossed the frozen nondegeneracy limit')
        if monitor.maxima['max_local_axial_strain'] >= LIMITS.local_axial_strain:
            raise RuntimeError('Family route crossed the frozen local axial-strain limit')
        if self.max_follow_error > .002:
            raise RuntimeError('Family route exceeded the assisted-grasp pose-follow limit')
        if monitor.count % max(1, round(.1/monitor.dt)) == 0 and self.owners:
            left = self.tool_position(self.controller.left)
            right = self.tool_position(self.controller.right)
            length = abs(self.arc[self.ring_indices[self.pull_band]]-self.arc[self.ring_indices[self.support_band]])
            self.constraint_samples.append(dict(time_s=t, phase=self.phase,
                physical_grasp_owners=dict(self.owners), endpoint_span_m=float(np.linalg.norm(left-right)),
                reference_material_length_m=float(length),
                reference_material_slack_m=float(length-np.linalg.norm(left-right)),
                projected_crossing_count=len(projected_crossings(monitor.last_centers)),
                force_measured=False))

    def finished(self, t):
        return self.final_observation_end is not None and t >= self.final_observation_end-1e-8

    def report(self):
        result = super().report()
        checks = result['checks']
        checks.pop('transfer_observed')
        checks['pregrasp_settle_passed'] = bool(self.pregrasp_settle_report
            and self.pregrasp_settle_report['mechanical_checks_passed'])
        checks['post_release_observed'] = bool(self.samples and self.finished(self.samples[-1]['time_s']))
        final_centers = getattr(self.monitor, 'last_centers', self.task.centerline)
        checks['final_no_projected_crossings'] = not projected_crossings(final_centers)
        released = [points for sample, points in zip(self.monitor.samples, self.monitor.centers)
                    if self.released_at is not None and sample['time_s'] >= self.released_at+4.]
        checks['released_window_no_crossings'] = bool(released) and all(not projected_crossings(p) for p in released)
        if self.route.check_robot_clearance:
            checks['sampled_robot_clearance'] = bool(self.worst_robot_overlap is not None
                and self.worst_robot_overlap['penetration_m'] <= .0005)
        if self.route.regrasp_pitch_candidates_deg:
            checks['sampled_gripper_table_clearance'] = bool(self.worst_gripper_floor_clearance is not None
                and self.worst_gripper_floor_clearance['gap_m'] >= -LIMITS.table_penetration_m)
        result.update(passed=all(checks.values()), family=self.family, route_id=self.route.route_id,
            regrasp_count=self.regrasps, total_draw_m=self.total_draw, total_strokes=self.total_strokes,
            opening_extra_lift_m=self.opening_extra_lift,
            support_spread_completed=self.support_spread_completed,
            worst_robot_overlap=self.worst_robot_overlap,
            worst_gripper_floor_clearance=self.worst_gripper_floor_clearance,
            released_at_s=self.released_at, constraint_samples=self.constraint_samples,
            pregrasp_settle_report=self.pregrasp_settle_report,
            worst_grasp_follow=self.worst_follow,
            difficulty_qualified=False, precision_manipulation_qualified=False,
            scope='experimental observed-underpass family route; contact-gated assistance; no transfer or force-control claim')
        return result
