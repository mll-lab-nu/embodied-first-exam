"""Native ALOHA manipulation of the two below-easy Orbits instances.

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
from topogym.utils.geometry.rope import load_centerline_map, sample_material_centerline
from topogym.utils.io import write_json_atomic
from .invariant import Fixture


class EpisodeFinished(RuntimeError):
    pass


class NativeOrbits:
    def __init__(self, session, output, *, variation, close_width_m=.0028):
        self.session = session
        self.output = Path(output)
        self.env = session.env
        self.world, self.robot, self.task = self.env._world, self.env._robot, self.env._task
        if variation not in {'very_easy', 'easier'} or session.config['variation_id'] != variation:
            raise ValueError('Expected the selected frozen below-easy Orbits instance')
        if session.config['task_id'] != 'orbits' or session.config['control_mode'] != 'JOINT_ABS':
            raise ValueError('Expected Orbits JOINT_ABS')
        if session.config.get('grasp_assist', {}).get('model', 'none') != 'none':
            raise ValueError('Native Orbits requires physical grasps')
        if session.n_steps or session._resets:
            raise ValueError('The caller must supply a fresh frozen Session')
        if not .001 <= close_width_m < 2*self.task.layout.cord_radius_m:
            raise ValueError('Pinch width must compress the cord without commanding full closure')
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
        paths = list(self.asset_dir.rglob('cord_volume.npz'))
        if len(paths) != 1:
            raise ValueError('Expected one authored cord volume')
        self.centerline_map = load_centerline_map(paths[0])
        indices, material = self.centerline_map
        self.stations = material[indices].mean(axis=1) if indices.ndim == 2 else material[indices]
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
        return sample_material_centerline(self.world.read_state()['fem']['cord'], *self.centerline_map)

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
        row = dict(phase=self.phase, steps=self.session.n_steps, time_s=self.session.sim_time_s,
                   word=word, cord_bounds_local_m=np.array([self.local(line).min(0), self.local(line).max(0)]),
                   grasps={side: dict(arc_m=arc, error_m=float(np.linalg.norm(self.at(arc, line)-self.contact(side)[0])))
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
        for alpha in np.linspace(0., 1., max(2, steps+1))[1:]:
            points = {s: starts[s]+alpha*(np.asarray(contacts[s])-starts[s]) for s in contacts}
            self.reach_row(self.solve_contacts(points, {s: rotations[s](alpha) for s in contacts}), phase)

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

    def grasp_one(self, side, station):
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
                        pre_q = self.solve_contact_pose(side, point+[0., 0., .06], turn, q)
                        pinch_q = self.solve_contact_pose(side, point, turn, pre_q)
                        if not self.collision_check(pre_q)['passed'] or not self.collision_check(pinch_q)['passed']:
                            continue
                        candidates.append((tilt, pre_q, turn, vertical))
                    except ValueError:
                        continue
                if candidates:
                    break
            if not candidates:
                raise RuntimeError(f'No collision-free pinch and pregrasp for {side} at material {station}')
            _, q, turn, vertical = min(candidates, key=lambda c: c[0])
            self.pinch_turns[side] = vertical
            points[side], turns[side] = point, turn
        pre = self.session.hold_action().astype(np.float64)
        for side in arcs:
            pre[self.session.robot.arm_slice[side]] = q[self.robot._q_indices[side][:6]]
        self.reach_row(pre, 'approach')
        self.hold(.7, 'approach_settle')
        points = {side: self.at(station) for side, station in arcs.items()}
        self.move(points, turns, 'descend', speed=.025)
        # Correct load-dependent PD error using measured pad contact positions.
        for _ in range(5):
            self.hold(.3, 'align_settle')
            errors = {s: self.at(arcs[s])-self.contact(s)[0] for s in arcs}
            if max(np.linalg.norm(e) for e in errors.values()) < .0015:
                break
            for side, error in errors.items():
                self.bias[side] += error
                if np.linalg.norm(self.bias[side]) > .025:
                    raise RuntimeError(f'Excessive contact tracking bias: {side}')
            self.reach_row(self.solve_contacts({s: self.at(arcs[s]) for s in arcs}, turns), 'align')
        else:
            raise RuntimeError('Pads did not align with the live cord')
        self.jaws(dict.fromkeys(arcs, self.close_width), 'pinch')
        self.grasps.update(arcs)
        before = {s: self.at(arcs[s]) for s in arcs}
        self.move({s: self.contact(s)[0]+[0., 0., .012] for s in arcs}, turns, 'test_lift', speed=.015)
        self.hold(.3, 'test_lift_settle')
        for side in arcs:
            point = self.at(arcs[side])
            if point[2]-before[side][2] < .006 or np.linalg.norm(point-self.contact(side)[0]) > .008:
                raise RuntimeError(f'Physical grasp did not follow: {side}')
        return turns

    def grasp_legs(self, *, arc=.225):
        # The zero-ring cord is narrower than the one-ring cord. Simultaneous
        # vertical pinches collide at the palms even though each individual IK
        # is valid. Lift the first hand outward before approaching the second.
        turns = {}
        for side, station in [('left', float(self.stations[-1]-arc)), ('right', arc)]:
            turns.update(self.grasp_one(side, station))
            point = self.local(self.contact(side)[0])
            point[1] = .105 if side == 'left' else -.105
            point[2] = max(point[2]+.045, .075)
            self.move({side: self.world_points(point)}, {side: turns[side]},
                      side+'_grasp_standoff', speed=.025)
            self.hold(.3, side+'_grasp_standoff_settle')
            if np.linalg.norm(self.at(station)-self.contact(side)[0]) > .01:
                raise RuntimeError(f'Grasp slipped during standoff: {side}')
        return turns

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

    def place(self, turns):
        from topogym.evaluation.task_metrics import body_points
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
        handle = body_points(state['bodies']['handle'], self.task.placement_vertices['handle'])
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
                self.peel_ring()
            if stage == 'peel':
                return dict(task_success=bool(self.session.success()), phase=self.phase,
                            scope='one candidate ring pass; full verifier pending')
            turns = self.grasp_legs(arc=.15 if self.variation == 'easier' and stage != 'grasp' else .225)
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


def run_feedback_policy(session, output, *, variation, stage='place', close_width_m=.0028):
    output = prepare_output(session, output, __file__)
    return NativeOrbits(session, output, variation=variation, close_width_m=close_width_m).run(stage=stage)
