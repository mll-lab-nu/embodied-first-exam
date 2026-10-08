"""Native ALOHA manipulation of the two below-easy Orbits instances (rigid link chain cord since 2026-10-07).

The caller owns the frozen Session and recording. This module only reads the
live scene and submits public JOINT_ABS actions. Candidate routes are development
policies; only an independent Harbor grade establishes a solution.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys

import fcl
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
import trimesh

from topogym.planning.harbor_bridge.actions import public_action
from topogym.planning.harbor_bridge.callbacks import prepare_output
from topogym.planning.knot_untying.artifacts import save_recording
from topogym.planning.knot_untying.kinematics import (
    CONTACT_IN_TCP_M, KnotIK, vertical_pinch,
)
from topogym.evaluation.task_metrics import body_points
from topogym.utils.io import write_json_atomic
from .invariant import Fixture
from topogym.planning.oracle_ik import active_scope, scoped_session_oracle


class EpisodeFinished(RuntimeError):
    pass


class GraspNotFollowing(RuntimeError):
    """The test lift raised the pads but not the cord; the cord still lies where it was."""


class NativeOrbits:
    def __init__(self, session, output, *, variation, close_width_m=None):
        self.session = session
        self.output = Path(output)
        self.env = session.env
        self.world, self.robot, self.task = self.env._world, self.env._robot, self.env._task
        if variation not in {'very_easy', 'easier'} or session.config['variation_id'] != variation:
            raise ValueError('Expected the selected frozen below-easy Orbits instance')
        if session.config['task_id'] != 'orbits' or session.config['control_mode'] != 'JOINT_ABS':
            raise ValueError('Expected Orbits JOINT_ABS')
        # Physical pinches, or the rigid-chain tiers' contact weld on any link (acquired when both fingers touch it
        # closing, released when the jaws open).
        if session.config.get('grasp_assist', {}).get('model', 'none') not in {'none', 'contact_weld_v1'}:
            raise ValueError('Native Orbits takes physical grasps or the contact weld')
        if session.n_steps or session._resets:
            raise ValueError('The caller must supply a fresh frozen Session')
        # Close 3 mm below the chain diameter: the pads stop on the rigid capsule and the larger finger position error
        # presses harder. At 1.5 mm below the 6 mm chain, opening the loop drew it 16 mm through the left pads
        # (2026-10-07). The 3.74 mm team-standard chain stops at the 1 mm floor.
        diameter = 2*self.task.CHAIN_RADIUS_M
        close_width_m = max(diameter-.003, .001) if close_width_m is None else close_width_m
        if not .001 <= close_width_m < diameter:
            raise ValueError('Pinch width must press the cord without commanding full closure')
        self.close_width = float(close_width_m)
        self.variation = variation
        self.dt = float(self.env.timing_spec['control_dt_s'])
        limit = getattr(sys.modules[type(session).__module__], 'JOINT_STEP_LIMIT_RAD', None)
        if limit is None or not np.isfinite(limit) or limit <= 0:
            raise ValueError('Missing the installed standard joint-step contract')
        self.joint_step = .975*float(limit)
        self.ik = KnotIK(self.world, self.robot, self.task.table_height_m)
        self.full_q = self.ik.seed.copy()
        fk = self.ik.fk.solve(self.full_q)
        positions = np.asarray(fk['position_world_m']).reshape(-1, 3)
        self.arm_bases = {link.name.split('/')[0]: positions[link.idx_local].copy()
                          for link in self.robot.entity.links if link.name.endswith('/base_link')}
        self.rotation = Rotation.from_euler('z', self.task.config['yaw_deg'], degrees=True)
        self.origin = np.asarray(self.task.origin)
        self.asset_dir = Path(self.env._asset_build.root)
        # Material stations along the chain: each link root, then the last link's tip (metres from the first eye).
        self.stations = np.r_[0., np.cumsum(self.task.link_lengths)]
        self.fixture = Fixture(self.task.layout, ring_pts=180)
        self.obstacles = []
        for name in self.task.placement_remainder:
            meshes = list(self.asset_dir.rglob(name+'.obj'))
            if len(meshes) != 1:
                raise ValueError(f'Missing fixture mesh {name}')
            mesh = trimesh.load(meshes[0], force='mesh', process=False)
            # Preserve each torus aperture; a convex hull would close it.
            model = fcl.BVHModel()
            model.beginModel(len(mesh.vertices), len(mesh.faces))
            model.addSubModel(np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int32))
            model.endModel()
            self.obstacles.append((name, fcl.CollisionObject(model, fcl.Transform(self.origin))))
        self.bias = {side: np.zeros(3) for side in self.robot.groups}
        self.pinch_turns = {}
        self.grasps = {}
        self.phase = 'initial'
        self.trace = []
        write_json_atomic(self.output/'policy_contract.json', dict(
            variation=variation, layout=asdict(self.task.layout), goal=asdict(self.task.goal_region),
            joint_step_rad=self.joint_step, close_width_m=self.close_width,
            grasp_assist='none', scope='candidate native policy; verifier required'))

    def local(self, points):
        return self.rotation.inv().apply(np.asarray(points)-self.origin)

    def world_points(self, points):
        return self.rotation.apply(points)+self.origin

    def line(self):
        """The chain's centreline in the world: every link root and the last link's tip."""
        links = self.world.read_state()['articulations']['cord']['links']
        names, last = self.task.link_names, self.task.link_lengths[-1]
        return np.vstack([body_points(links[name], [[0., 0., 0.]]) for name in names]
                         + [body_points(links[names[-1]], [[last, 0., 0.]])])

    def at(self, arc, line=None):
        line = self.line() if line is None else line
        return np.array([np.interp(arc, self.stations, line[:, k]) for k in range(3)])

    def contact(self, side):
        observed = self.robot.observe()[side]
        turn = Rotation.from_quat(np.asarray(observed['tcp_orientation_wxyz'])[[1, 2, 3, 0]])
        return np.asarray(observed['tcp_position_world_m'])+turn.apply(CONTACT_IN_TCP_M), turn

    def command_q(self, row):
        native = self.session.robot.command(np.asarray(row, dtype=np.float64))
        q = self.full_q.copy()
        for side, group in self.robot.groups.items():
            ids = self.robot._q_indices[side]
            q[ids[:6]] = native[side]['joint_position_rad']
            q[ids[6:]] = native[side][group.gripper_field]
        return q

    def collision_check(self, q):
        result = self.ik.check(q)
        contacts = []
        for side, link, index, vertices, shape in self.ik.shapes:
            for name, obstacle in self.obstacles:
                if fcl.collide(shape, obstacle, fcl.CollisionRequest(), fcl.CollisionResult()):
                    contacts.append((link, name))
        if contacts:
            result['passed'] = False
            result['fixture_contacts'] = contacts
        return result

    def record_progress(self, *, force=False):
        if not force and self.session.n_steps % 8:
            return
        line = self.line()
        word = self.fixture.describe(self.local(line))
        # The contact weld's state per hand (holding / its bound link): a pinch touching two links' grasp regions does
        # not weld and holds by friction only.
        hands = self.world.read_state().get('grasp', {}).get('hands', {})
        assist = {side: dict(phase=h.get('phase'), target=(h.get('binding') or {}).get('target'), rejection=h.get('rejection'))
                  for side, h in hands.items()}
        row = dict(phase=self.phase, steps=self.session.n_steps, time_s=self.session.sim_time_s,
                   word=word, cord_bounds_local_m=np.array([self.local(line).min(0), self.local(line).max(0)]),
                   grasps={side: dict(arc_m=arc, error_m=float(np.linalg.norm(self.at(arc, line)-self.contact(side)[0])),
                                      assist=assist.get(side))
                           for side, arc in self.grasps.items()},
                   metrics=dict(self.task.result.metrics), safety=self.session.safety(),
                   task_success=bool(self.session.success()), episode_end=self.session.episode_end)
        self.trace.append(row)
        write_json_atomic(self.output/'native_progress.json', row)
        if self.session._recording is not None:
            save_recording(self.session, self.output/'trajectory.partial.npz')
        print(f"{self.session.sim_time_s:7.2f}s {self.phase}: word={word[0]} grasps={row['grasps']}", flush=True)

    def submit(self, desired, phase):
        """One actual step, reanchored to targets accepted by the Session guard."""
        s = self.session
        if s.episode_done or s.episode_end is not None:
            raise EpisodeFinished(s.episode_end or 'step_limit')
        self.phase = phase
        previous = s.hold_action().astype(np.float64)
        row = np.asarray(desired, dtype=np.float64).copy()
        for side, sl in s.robot.arm_slice.items():
            row[sl] = previous[sl]+np.clip(row[sl]-previous[sl], -self.joint_step, self.joint_step)
        # IK may return a joint exactly at its model limit (very_easy's left approach: forearm roll at -pi), one float32
        # step outside the public adapter's range; clamp only that rounding margin. Larger excursions still raise.
        clipped = s.robot.clip(row)
        if np.max(np.abs(clipped-row)) <= 1e-4:
            row = clipped
        row = public_action(s, row)
        check = self.collision_check(self.command_q(row))
        if not check['passed']:
            raise RuntimeError(f'Unsafe command in {phase}: {check}')
        ended = s.step(row)
        self.full_q = self.command_q(s.hold_action())
        self.record_progress(force=ended)
        if ended:
            raise EpisodeFinished(s.episode_end or 'step_limit')

    def reach_row(self, target, phase, *, max_seconds=12.):
        # Native table clipping can reject a target. Never extrapolate beyond it
        # or keep trying an unreachable target indefinitely.
        for _ in range(int(np.ceil(max_seconds/self.dt))):
            if np.max(np.abs(self.session.hold_action()-target)) < 2e-6:
                return
            self.submit(target, phase)
        raise RuntimeError(f'Accepted targets did not converge in {phase}')

    # Joint orderings for a long reach, as indices into the moving arm's six joints; () moves all together. Wrist first
    # keeps the gripper folded while the arm swings: very_easy's direct right approach swept its gripper past the
    # parked left one (inter_arm 0.44 mm, local Harbor run 2026-10-06), though both endpoints passed.
    REACH_STAGES = ((), (3, 4, 5), (1, 2, 4), (0,))

    def planned_rows(self, start, target):
        """The rows submit() sends from start toward target when every row is accepted."""
        rows, current = [], np.asarray(start, dtype=np.float64)
        while np.max(np.abs(current-target)) >= 2e-6:
            row = np.asarray(target, dtype=np.float64).copy()
            for sl in self.session.robot.arm_slice.values():
                row[sl] = current[sl]+np.clip(row[sl]-current[sl], -self.joint_step, self.joint_step)
            rows.append(row)
            current = row
        return rows

    def clear_waypoints(self, target):
        """Waypoints of the first joint ordering whose every planned row passes collision_check, else None."""
        start = self.session.hold_action().astype(np.float64)
        target = np.asarray(target, dtype=np.float64)
        for stage in self.REACH_STAGES:
            waypoints = [target]
            if stage:
                mid = start.copy()
                for sl in self.session.robot.arm_slice.values():
                    joints = np.arange(sl.start, sl.stop)[list(stage)]
                    mid[joints] = target[joints]
                waypoints.insert(0, mid)
            current, clear = start, True
            for waypoint in waypoints:
                clear = all(self.collision_check(self.command_q(row))['passed']
                            for row in self.planned_rows(current, waypoint))
                if not clear:
                    break
                current = waypoint
            if clear:
                return waypoints
        return None

    def reach_checked(self, target, phase):
        """reach_row along the first joint ordering whose every planned row passes collision_check."""
        waypoints = self.clear_waypoints(target)
        if waypoints is None:
            raise RuntimeError(f'No collision-free joint ordering in {phase}')
        for waypoint in waypoints:
            self.reach_row(waypoint, phase)

    def hold(self, seconds, phase):
        for _ in range(int(np.ceil(seconds/self.dt))):
            self.submit(self.session.hold_action(), phase)

    def width(self, side, width_m):
        native = self.session.robot.width_to_native(side, width_m)
        return self.session.robot.native_to_action(side, native)

    def jaws(self, widths, phase, seconds=.5):
        start = self.session.hold_action().astype(np.float64)
        end = start.copy()
        for side, width in widths.items():
            end[self.session.robot.grip_index[side]] = self.width(side, width)
        for alpha in np.linspace(0., 1., max(2, int(np.ceil(seconds/self.dt))))[1:]:
            self.submit(start+alpha*(end-start), phase)

    def support_gap(self, q, side):
        fk = self.ik.fk.solve(q)
        positions = np.asarray(fk['position_world_m']).reshape(-1, 3)
        turns = Rotation.from_quat(np.asarray(fk['orientation_wxyz']).reshape(-1, 4)[:, [1, 2, 3, 0]])
        gap = float('inf')
        lay = self.task.layout
        for arm, index, vertices in self.ik.gripper_covers:
            if arm != side:
                continue
            points = self.local(turns[index].apply(vertices)+positions[index])
            on_base = (np.abs(points[:, 0]) <= lay.base_length_m/2) & (np.abs(points[:, 1]) <= lay.base_width_m/2)
            heights = np.where(on_base, lay.base_height_m, 0.)
            gap = min(gap, float(np.min(points[:, 2]-heights)))
        return gap

    def solve_contact_pose(self, side, point, turn, q):
        tcp = np.asarray(point)+self.bias[side]-turn.apply(CONTACT_IN_TCP_M)
        raise_m = 0.
        for _ in range(4):
            result = self.ik.solve(side, (tcp+[0., 0., raise_m], turn), q)
            gap = self.support_gap(result, side)
            if gap >= .0005:
                return result
            raise_m += .0006-gap
            if raise_m > .003:
                break
        raise ValueError(f'No close contact pose above the support surface: {side}')

    def solve_contacts(self, contacts, turns):
        q = self.full_q.copy()
        for side, point in contacts.items():
            q = self.solve_contact_pose(side, point, turns[side], q)
        row = self.session.hold_action().astype(np.float64)
        for side in contacts:
            row[self.session.robot.arm_slice[side]] = q[self.robot._q_indices[side][:6]]
        check = self.collision_check(self.command_q(row))
        if not check['passed']:
            raise RuntimeError(f'Unsafe Cartesian endpoint in {self.phase}: {check}')
        return row

    def move(self, contacts, turns, phase, *, speed=.04):
        starts = {side: self.contact(side)[0] for side in contacts}
        initial_turns = {side: self.contact(side)[1] for side in contacts}
        rotations = {s: Slerp([0., 1.], Rotation.concatenate([initial_turns[s], turns[s]])) for s in contacts}
        distance = max(np.linalg.norm(np.asarray(contacts[s])-starts[s]) for s in contacts)
        angle = max((initial_turns[s].inv()*turns[s]).magnitude() for s in contacts)
        steps = int(np.ceil(max(distance/speed, angle/.5)/self.dt))
        previous = self.session.hold_action().astype(np.float64)
        for alpha in np.linspace(0., 1., max(2, steps+1))[1:]:
            points = {s: starts[s]+alpha*(np.asarray(contacts[s])-starts[s]) for s in contacts}
            row = self.solve_contacts(points, {s: rotations[s](alpha) for s in contacts})
            # One interpolation step turns a joint by a few hundredths of a radian. A larger change is another IK
            # branch, and walking the joints across it swings the gripper off the path: very_easy's right lean met
            # the forearm-roll limit and the swing threw the cord out of the pads (2026-10-07).
            for side in contacts:
                sl = self.session.robot.arm_slice[side]
                jump = float(np.max(np.abs(row[sl]-previous[sl])))
                if jump > .5:
                    raise RuntimeError(f'IK branch change in {phase}: {side} joint jump {jump:.2f} rad')
            self.reach_row(row, phase)
            previous = row

    def roll_margin(self, side, q):
        """Smallest travel left to a limit of the forearm-roll and wrist-rotate joints (arm joints 3 and 5)."""
        limits = np.asarray(self.robot.groups[side].arm_limits_rad)
        joints = np.asarray(q)[self.robot._q_indices[side][:6]]
        return float(min(min(joints[i]-limits[i, 0], limits[i, 1]-joints[i]) for i in (3, 5)))

    def transport_turns(self, points, *, tilt_deg=45.):
        """Tilt each wrist toward its reach direction while retaining the pinch."""
        turns = {}
        for side, point in points.items():
            direction = np.asarray(point)-self.arm_bases[side]
            direction[2] = 0.
            direction /= np.linalg.norm(direction)
            turn = Rotation.from_rotvec(np.cross([0., 0., -1.], direction)*np.radians(tilt_deg))
            turns[side] = turn*self.pinch_turns[side]
        return turns

    def grasp_one(self, side, station, *, pre_height=.06):
        """Approach one strand with the other hand held at its accepted target."""
        arcs = {side: station}
        self.jaws(dict.fromkeys(arcs, .022), 'open')
        points, turns = {}, {}
        line = self.line()
        q = self.full_q.copy()
        for side, station in arcs.items():
            point = self.at(station, line)
            tangent = self.at(station+.006, line)-self.at(station-.006, line)
            direction = point-self.arm_bases[side]
            direction[2] = 0.
            direction /= np.linalg.norm(direction)
            axis = np.cross([0., 0., -1.], direction)
            preferred_flip = 1 if side == 'left' else -1
            candidates = []
            for flip in (preferred_flip, -preferred_flip):
                _, vertical = vertical_pinch(point, tangent, flip)
                for tilt in (0., 15., 30., 45.):
                    turn = Rotation.from_rotvec(axis*np.radians(tilt))*vertical
                    try:
                        pre_q = self.solve_contact_pose(side, point+[0., 0., pre_height], turn, q)
                        pinch_q = self.solve_contact_pose(side, point, turn, pre_q)
                        if not self.collision_check(pre_q)['passed'] or not self.collision_check(pinch_q)['passed']:
                            continue
                        candidates.append((tilt, pre_q, turn, vertical, self.roll_margin(side, pinch_q)))
                    except ValueError:
                        continue
            if not candidates:
                raise RuntimeError(f'No collision-free pinch and pregrasp for {side} at material {station}')
            # Candidates keeping 0.8 rad of forearm-roll and wrist-rotate travel first (the two-finger pinch is the
            # same grip turned 180 deg, so the other flip usually has it): a right grip at the forearm-roll limit
            # could not lean 45 deg without an IK branch change (2026-10-07). Then preferred flip, least tilt; take
            # the first whose whole approach is clear, not only its endpoints: with the other hand parked over the
            # narrow very_easy loop, the least-tilted pregrasp's path crossed it in every joint ordering.
            candidates.sort(key=lambda c: c[4] < .8)
            hold = self.session.hold_action().astype(np.float64)
            for tilt, q, turn, vertical, _ in candidates:
                pre = hold.copy()
                pre[self.session.robot.arm_slice[side]] = q[self.robot._q_indices[side][:6]]
                waypoints = self.clear_waypoints(pre)
                if waypoints is not None:
                    break
            else:
                pre = hold.copy()
                pre[self.session.robot.arm_slice[side]] = candidates[0][1][self.robot._q_indices[side][:6]]
                blocked = next((check for row in self.planned_rows(hold, pre)
                                if not (check := self.collision_check(self.command_q(row)))['passed']), None)
                raise RuntimeError(f'No collision-free approach for {side} at material {station}; '
                                   f'direct path of the first candidate: {blocked}')
            self.pinch_turns[side] = vertical
            points[side], turns[side] = point, turn
        for waypoint in waypoints:
            self.reach_row(waypoint, 'approach')
        self.hold(.7, 'approach_settle')
        points = {side: self.at(station) for side, station in arcs.items()}
        self.move(points, turns, 'descend', speed=.025)
        # Correct load-dependent PD error using measured pad contact positions.
        flat = False
        for _ in range(5):
            self.hold(.3, 'align_settle')
            errors = {s: self.at(arcs[s])-self.contact(s)[0] for s in arcs}
            # Once the support has refused a lower target (below), only the in-plane error can still be corrected.
            if max(np.linalg.norm(e[:2] if flat else e) for e in errors.values()) < .0015:
                break
            for side, error in errors.items():
                self.bias[side] += error
                if np.linalg.norm(self.bias[side]) > .025:
                    raise RuntimeError(f'Excessive contact tracking bias: {side}')
            try:
                row = self.solve_contacts({s: self.at(arcs[s]) for s in arcs}, turns)
            except ValueError:
                # A cord resting on the table lies below the lowest pad height the support allows, and pads still
                # descending read high: no lower target has a pose above the table / base. Correct in plane only.
                flat = True
                for side, error in errors.items():
                    self.bias[side][2] -= error[2]
                row = self.solve_contacts({s: self.at(arcs[s]) for s in arcs}, turns)
            self.reach_row(row, 'align')
        else:
            raise RuntimeError('Pads did not align with the live cord')
        self.jaws(dict.fromkeys(arcs, self.close_width), 'pinch')
        self.grasps.update(arcs)
        before = {s: self.at(arcs[s]) for s in arcs}
        self.move({s: self.contact(s)[0]+[0., 0., .012] for s in arcs}, turns, 'test_lift', speed=.015)
        self.hold(.3, 'test_lift_settle')
        for side in arcs:
            point = self.at(arcs[side])
            # 3 mm: the arm's position control trails the 12 mm test lift, 3.7 mm with the limp chain and 7.6 mm with
            # the stiff one, the pinched cord within 1 mm of the pads in both (local very_easy, 2026-10-07). A slip
            # shows as the pads leaving the cord.
            if point[2]-before[side][2] < .003 or np.linalg.norm(point-self.contact(side)[0]) > .008:
                raise GraspNotFollowing(f'Physical grasp did not follow: {side}')
        return turns

    def grasp_retry(self, side, station, *, pre_height=.06):
        """grasp_one, once more after a pinch that did not lift the cord: pads on a cord lying on its support reach
        only its upper half, and such a pinch held 3 times in 5 (2026-10-07)."""
        try:
            return self.grasp_one(side, station, pre_height=pre_height)
        except GraspNotFollowing:
            self.grasps.pop(side, None)
        self.jaws({side: .022}, 'regrasp_open')
        point, turn = self.contact(side)
        self.move({side: point+[0., 0., .06]}, {side: turn}, 'regrasp_lift', speed=.025)
        self.bias[side] = np.zeros(3)
        return self.grasp_one(side, station, pre_height=pre_height)

    def grasp_legs(self, *, arc=.225, right_arc=None):
        # The zero-ring cord is narrower than the one-ring cord. Simultaneous
        # vertical pinches collide at the palms even though each individual IK
        # is valid. Lift the first hand outward before approaching the second.
        # arc: material from the far end to the left grip; right_arc (default arc) from the start to the right grip.
        turns = {}
        right_arc = arc if right_arc is None else right_arc
        order = [('left', float(self.stations[-1]-arc)), ('right', right_arc)]
        if self.variation == 'very_easy':
            # Right first: the left hand parked at x 0.195 m blocked every swept right approach to its grip at
            # x 0.13 m (gripper bases touching, 2026-10-07); the right one parked higher is clear of the left reach.
            order.reverse()
        for side, station in order:
            turns.update(self.grasp_retry(side, station))
            point = self.local(self.contact(side)[0])
            if self.variation == 'very_easy':
                # Lift the leg straight up 6 cm: a sideways pull dragged the cord to the handle along the table and
                # drew it through the pads (42 mm slip, 2026-10-06). The stiff loop's grips lie 0.21 m apart, so the
                # parked hand leaves the other's approach clear.
                point[2] = .06
            else:
                point[1] = .105 if side == 'left' else -.105
                point[2] = max(point[2]+.045, .075)
            self.move({side: self.world_points(point)}, {side: turns[side]},
                      side+'_grasp_standoff', speed=.025)
            self.hold(.3, side+'_grasp_standoff_settle')
            if np.linalg.norm(self.at(station)-self.contact(side)[0]) > .01:
                raise RuntimeError(f'Grasp slipped during standoff: {side}')
        return turns

    def ring_hole_lift(self):
        """easier, standard solution, first half of the first ball pass (user, 2026-10-07): reach down through the ring
        hole to the deepest point of the bight around the ring's support post, pinch it there and lift it straight up
        through the hole above the ball top. The resized fixture leaves 108 mm between the support-side rim and the
        ball; the bight's deepest point lies 63 mm inside the rim and 45 mm from the ball."""
        lay = self.task.layout
        local = self.local(self.line())
        word = self.fixture.describe(local)
        if word[2] != 2:
            raise RuntimeError(f'Unexpected one-ring initial word: {word}')
        centre, aperture = lay.ring_x[0], lay.ring_radius_m-lay.ring_tube_radius_m
        inside = np.flatnonzero(np.hypot(local[:, 0]-centre, local[:, 1]) < aperture)
        if not len(inside):
            raise RuntimeError('No cord lies under the ring hole')
        # The bight around the support post reaches toward the ball post, at -x.
        station = float(self.stations[inside[np.argmin(local[inside, 0])]])
        for side in ('right', 'left'):
            try:
                turns = self.grasp_retry(side, station, pre_height=.25)
                break
            except RuntimeError as error:
                if 'No collision-free' not in str(error) or side == 'left':
                    raise
                print(f'ring-hole pinch: {error}; trying the left hand', flush=True)
        point = self.local(self.contact(side)[0])
        top = lay.ball_z+lay.ball_radius_m
        self.move({side: self.world_points([point[0], point[1], top+.06])}, {side: turns[side]},
                  'bight_up_through_hole', speed=.02)
        self.hold(.5, 'bight_up_settle')
        if np.linalg.norm(self.at(station)-self.contact(side)[0]) > .02:
            raise RuntimeError('The bight slipped while lifted through the ring hole')
        return side, station, turns

    def peel_ring(self):
        """Candidate fresh-bight ball pass, checked against the live cord word.

        The lower material station must occupy negative local y at the neck.
        Reversing those branches adds a turn instead of removing the ring word.
        This route needs native physical qualification; its topological model
        alone does not establish that the robot can execute it.
        """
        lay = self.task.layout
        initial = self.fixture.describe(self.local(self.line()))
        if initial[2] != 2:
            raise RuntimeError(f'Unexpected one-ring initial word: {initial}')
        turns = self.grasp_one('left', .65)
        current = self.local(self.contact('left')[0])
        self.move({'left': self.world_points([current[0], current[1], .18])},
                  turns, 'fresh_bight_lift', speed=.025)
        upper = {'left': self.world_points([lay.post_x[0]+.05, .06, .23])}
        turns.update(self.transport_turns(upper, tilt_deg=60.))
        self.move(upper, turns, 'fresh_bight_carry', speed=.025)
        self.hold(.5, 'fresh_bight_settle')
        turns.update(self.grasp_one('right', .50))
        span = self.grasps['left']-self.grasps['right']
        half_width = .06
        neck = (lay.ring_z[0]+lay.ring_tube_radius_m+lay.ball_z-lay.ball_radius_m)/2
        height = neck+np.sqrt((span/2)**2-half_width**2)
        stages = [('bight_spread', lay.post_x[0]+.05, .23),
                  ('bight_over_ball', lay.post_x[0]-.04, .23),
                  ('bight_lower', lay.post_x[0]-.04, height),
                  ('bight_wrap', lay.post_x[0]+.018, height)]
        for phase, x, z in stages:
            goals = {s: self.world_points([x, half_width if s == 'left' else -half_width, z]) for s in turns}
            turns.update(self.transport_turns(goals, tilt_deg=60.))
            self.move(goals, turns, phase, speed=.02)
            self.hold(.3, phase+'_settle')
            for side, arc in self.grasps.items():
                if np.linalg.norm(self.at(arc)-self.contact(side)[0]) > .012:
                    raise RuntimeError(f'Fresh-bight grasp slipped: {side}')
        if self.fixture.describe(self.local(self.line()))[2] != 1:
            raise RuntimeError('The candidate ring pass did not remove exactly one ball letter')
        self.jaws(dict.fromkeys(turns, .022), 'ring_pass_release')
        self.grasps.clear()
        self.move({s: self.contact(s)[0]+[0., 0., .10] for s in turns}, turns, 'ring_pass_retreat')
        self.hold(1., 'ring_pass_settle')
        if self.fixture.describe(self.local(self.line()))[2] != 1:
            raise RuntimeError('Ring passage did not persist after release')

    def clear_single_post(self, turns):
        lay = self.task.layout
        if self.variation == 'very_easy':
            # Reverse ring toss with the stiff loop (2026-10-07): lift both grips straight up to 0.25 m, the loop
            # keeping its authored opening around the post and ball, then carry it 0.10 m toward the handle so the
            # bight passes over the ball. MuJoCo two-point lift of the same chain: hands at 0.20-0.30 m and a carry of
            # 0.06-0.20 m all came off 8.6-9.0 mm from the post and ball; 0.36 m was out of the arms' reach. A limp
            # loop hung into the hands' vertical plane and pressed a strand on the post, which the ball caught (runs
            # 14-17).
            points = {s: self.local(self.contact(s)[0]) for s in turns}
            for phase, dx, z in (('lift_loop', 0., .25), ('carry_over_ball', .10, .25)):
                goals = {s: self.world_points([p[0]+dx, p[1], z]) for s, p in points.items()}
                self.move(goals, turns, phase, speed=.025)
                self.hold(.3, phase+'_settle')
            if self.fixture.describe(self.local(self.line()))[1] != 0:
                raise RuntimeError('Cord remains linked to the fixture after the lift over the ball')
            return
        # The free bight can hang by at most half the material between grips.
        slack = abs(self.grasps['left']-self.grasps['right'])/2
        z = lay.ball_z+lay.ball_radius_m+slack+.025
        points = {s: self.local(self.contact(s)[0]) for s in turns}
        if z > .35:
            goals = {s: self.world_points([p[0], p[1], max(p[2], .20)]) for s, p in points.items()}
            self.move(goals, turns, 'prepare_high_lift')
            turns.update(self.transport_turns(goals))
        self.move({s: self.world_points([p[0], p[1], z]) for s, p in points.items()}, turns, 'lift_over_ball')
        self.hold(.5, 'lift_settle')
        goals = {s: self.world_points([.15, p[1], z]) for s, p in points.items()}
        turns.update(self.transport_turns(goals))
        self.move(goals, turns, 'clear_ball')
        self.hold(.5, 'clear_settle')
        if self.fixture.describe(self.local(self.line()))[1] != 0:
            raise RuntimeError('Cord remains linked to the fixture after the candidate ball pass')

    def cord_extent(self):
        """Fixture-frame bounds of the live chain and handle."""
        state = self.world.read_state()
        handle = body_points(state['articulations']['cord']['links']['handle'], self.task.handle_vertices)
        points = self.local(np.vstack([self.line(), handle]))
        return points.min(0), points.max(0)

    def place_over(self, turns):
        """very_easy, stiff loop (2026-10-07): carry the freed loop over the fixture with upright grippers, then set it
        down so that each grip lands where it lay at the start, shifted by the offset that centres the resting loop and
        handle on the goal region (beyond the post, away from the handle); the stiff loop lies back in its authored
        shape, 0.385 m of the region's 0.40 m along the fixture axis. Going beside the fixture instead needed a wrist
        tilted across the fixture axis, which twisted the loop held by both hands until the team-standard chain's weld
        on the left let go (relative pose error, local runs 8 and 10). Nominal IK, upright: hands at 0.30 m reach from the
        freed position to 0.40 m back (the freed position itself only just); the goal itself only lower."""
        lay = self.task.layout
        rest_line, rest_lo, rest_hi = self.rest
        goal = self.local(np.r_[self.task.goal_region.center_xy_m, self.task.table_height_m])
        offset = goal[:2]-(rest_lo[:2]+rest_hi[:2])/2
        rest = {s: self.local(self.at(a, rest_line)[None])[0] for s, a in self.grasps.items()}
        target = {s: np.r_[rest[s][:2]+offset, rest[s][2]+.02] for s in rest}
        start = {s: self.local(self.contact(s)[0][None])[0] for s in turns}

        def go(points, phase):
            self.move({s: self.world_points(points[s]) for s in turns}, turns, phase, speed=.025)
            self.hold(.5, phase+'_settle')

        # Back 5 cm first, the bight end over the ball: there the chain hangs least (1.6 cm above the ball top with the
        # hands at 0.25 m, local run 11) and the heavy handle, hanging lowest, is still at the far end. Rising at the
        # freed position toward 0.32 m met the left arm's reach and its jerk tore the weld (run 11); upright, the hands
        # reach 0.30 m from here on.
        top = lay.ball_z+lay.ball_radius_m
        chain_low = self.local(self.line())[:, 2].min()
        if chain_low < top+.01:
            raise RuntimeError(f'The chain hangs at {chain_low:.3f} m, within 1 cm of the ball top {top:.3f} m')
        go({s: np.r_[p[0]-.05, p[1], p[2]] for s, p in start.items()}, 'back_over_post')
        # Then only as high as the measured loop needs: its lowest point, chain or handle, 2 cm above the ball top
        # (0.295 m for the hands, run 12).
        lo, _ = self.cord_extent()
        z = max(p[2] for p in start.values())+max(0., top+.02-lo[2])
        if z > .30:
            raise RuntimeError(f'The hanging loop needs the hands at {z:.3f} m to cross 2 cm above the ball top')
        go({s: np.r_[p[0]-.05, p[1], z] for s, p in start.items()}, 'raise_over_fixture')
        go({s: np.r_[p[0]-.40, p[1], z] for s, p in start.items()}, 'over_fixture')
        go({s: np.r_[p[0]-.40, p[1], .16] for s, p in start.items()}, 'lower_past_fixture')
        cord = {s: self.local(self.at(a)[None])[0] for s, a in self.grasps.items()}
        go({s: self.local(self.contact(s)[0][None])[0]+np.r_[target[s][:2]-cord[s][:2], 0.] for s in turns},
           'over_goal')
        # Down until the grips are 2 cm above where they lay: the rest of the loop is on the table by then.
        cord = {s: self.local(self.at(a)[None])[0] for s, a in self.grasps.items()}
        go({s: self.local(self.contact(s)[0][None])[0]+target[s]-cord[s] for s in turns}, 'lower_into_goal')
        # Centre the measured loop and handle on the region before letting go: set down by the resting shape alone it
        # landed 2.4 cm off, its bight 15 mm outside, where the region leaves 7.5 mm a side (local run 13).
        for _ in range(2):
            lo, hi = self.cord_extent()
            error = goal[:2]-(lo[:2]+hi[:2])/2
            if np.max(np.abs(error)) < .002:
                break
            go({s: self.local(self.contact(s)[0][None])[0]+np.r_[error, 0.] for s in turns}, 'centre_in_goal')
        self.jaws(dict.fromkeys(turns, .022), 'release')
        self.grasps.clear()
        self.move({s: self.contact(s)[0]+[0., 0., .07] for s in turns}, turns, 'retreat')
        self.hold(20., 'goal_settle')

    def place(self, turns):
        if self.variation == 'very_easy':
            return self.place_over(turns)
        lay = self.task.layout
        hang = max(max(self.grasps['right'], self.stations[-1]-self.grasps['left'])+lay.handle_length_m,
                   abs(self.grasps['left']-self.grasps['right'])/2)
        z = lay.ball_z+lay.ball_radius_m+hang+.025
        points = {s: self.local(self.contact(s)[0]) for s in turns}
        goals = {s: self.world_points([p[0], p[1], z]) for s, p in points.items()}
        turns.update(self.transport_turns(goals))
        self.move(goals, turns, 'raise_for_transfer')
        self.hold(.7, 'transfer_settle')
        state = self.world.read_state()
        handle = body_points(state['articulations']['cord']['links']['handle'], self.task.handle_vertices)
        lowest = min(self.line()[:, 2].min(), handle[:, 2].min())-self.task.table_height_m
        if lowest <= lay.ball_z+lay.ball_radius_m+.008:
            raise RuntimeError('The whole cord and handle have not cleared the ball height')
        goal = self.local(np.r_[self.task.goal_region.center_xy_m, self.task.table_height_m])
        # Cross the fixture while the whole assembly is above it. Lower on the
        # goal side before moving farther back, to stay inside arm reach.
        exit_x = -lay.base_length_m/2-.065
        goals = {s: self.world_points([exit_x, p[1], z]) for s, p in points.items()}
        turns.update(self.transport_turns(goals))
        self.move(goals, turns, 'transfer_above_fixture', speed=.03)
        self.hold(.7, 'transfer_exit_settle')
        if self.local(self.line())[:, 0].max() > -lay.ball_radius_m-.02:
            raise RuntimeError('Cord still overlaps the fixture before lowering')
        for x, height, phase in [(exit_x, .22, 'lower_after_fixture'),
                                 (goal[0], .22, 'carry_to_goal'),
                                 (goal[0], .11, 'lower_into_goal')]:
            goals = {s: self.world_points([x, goal[1]+p[1], height]) for s, p in points.items()}
            turns.update(self.transport_turns(goals))
            self.move(goals, turns, phase, speed=.025)
        self.hold(1., 'placement_settle')
        self.jaws(dict.fromkeys(turns, .022), 'release')
        self.grasps.clear()
        self.move({s: self.contact(s)[0]+[0., 0., .07] for s in turns}, turns, 'retreat')
        self.hold(20., 'goal_settle')

    def run(self, *, stage='place'):
        if stage not in {'grasp', 'peel', 'clear', 'place'}:
            raise ValueError('Unknown development stage')
        try:
            self.record_progress(force=True)
            if stage != 'grasp' and self.variation == 'easier':
                self.ring_hole_lift()
                raise RuntimeError('easier development: stopped after the ring-hole lift')
            if stage == 'peel':
                return dict(task_success=bool(self.session.success()), phase=self.phase,
                            scope='one candidate ring pass; full verifier pending')
            if self.variation == 'very_easy':
                # The resting loop, where place_over sets it down again.
                self.rest = (self.line(), *self.cord_extent())
                # Left 0.18 m from its end, right 0.225 m from the start: both flat on the 2 mm base or the table
                # (0.15 m rises toward the handle eye and a pinch there missed, 2026-10-07). 0.47 m of the 0.88 m chain
                # stays around the post.
                turns = self.grasp_legs(arc=.18, right_arc=.225)
            else:
                turns = self.grasp_legs(arc=.15 if stage != 'grasp' else .225)
            if stage in {'clear', 'place'}:
                self.clear_single_post(turns)
            if stage == 'place':
                self.place(turns)
        except EpisodeFinished:
            pass
        finally:
            self.record_progress(force=True)
            write_json_atomic(self.output/'native_trace.json', self.trace)
        return dict(task_success=bool(self.session.success()), steps=self.session.n_steps,
                    phase=self.phase, scope='native development stage; independent verifier required')


def chain_free_check(env):
    """The IK candidates' swept check without the cord, as for the FEM cord it replaced (soft material was never in
    it). It carries only a held link with the hand; the rest of the loop, which hangs from the hands and moves with
    them, stood as fixed obstacles touching the fingers and refused every motion (local very_easy, 2026-10-07). The
    fixture, table and the other arm stay checked."""
    from topogym.planning.oracle_path import SceneCandidateCheck
    check = SceneCandidateCheck(env)
    check.shapes = [s for s in check.shapes if s.entity != 'cord']
    return check


@scoped_session_oracle
def run_feedback_policy(session, output, *, variation, stage='place', close_width_m=None):
    output = prepare_output(session, output, __file__)
    scope = active_scope()
    if scope is not None and scope.validator is None:
        scope.validator = chain_free_check(session.env)
    return NativeOrbits(session, output, variation=variation, close_width_m=close_width_m).run(stage=stage)
