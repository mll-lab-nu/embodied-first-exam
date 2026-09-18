"""Measured-pose assisted grasp, lift, two-hand transfer and full release.

The soft band can engage only after BOTH physical fingers contact its FEM
surface. Its targets follow measured link poses, never desired IK poses.
"""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .probe_actions import smoothstep


TOOL_OFFSET = np.array([.143, 0., -.0038])


def rotation(quat_wxyz):
    return Rotation.from_quat(np.asarray(quat_wxyz)[[1, 2, 3, 0]])


def configure_contact_start(cfg):
    from .untying import initial_centerline
    from .control import configure_initial_hover
    points = initial_centerline(cfg)
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    index = int(np.argmin(abs(arc-(arc[-1]-.015))))
    return configure_initial_hover(cfg, {'left': (points[index], points[index+1]-points[index-1])}, height=.05)


class RobotGraspActions:
    def __init__(self):
        self.bands, self.events, self.samples = [], [], []
        self.owners, self.offsets = {}, {}
        self.motion = {}
        self.closed = {}
        self.finger_gaps = {}
        self.contact_checkers = {}
        self.stage = 'settle'
        self.max_follow_error = 0.
        self.max_rigid_penetration = 0.
        self.max_joint_limit_violation = 0.
        self.max_native_pose_error = 0.
        self.worst_native_pose_link = None
        self.worst_rigid_contact = None

    def specification(self):
        return dict(kind='assisted_grasp', robot='aloha', duration_s=48.,
                    tail_grasp_distances_m=[.015, .085], band_radius_m=.008, strength=100.,
                    tool_offset_in_gripper_link_m=TOOL_OFFSET.tolist(),
                    engagement='both native IPC finger surfaces within contact d_hat of band surface',
                    contact_distance_method='ipctk vertex-face and edge-edge features; null gap means outside query radius',
                    follow='measured gripper_link position and rotation',
                    release_s=40., post_release_s=8., maximum_follow_error_m=.002,
                    maximum_rigid_penetration_m=.0005,
                    maximum_native_robot_surface_error_m=.002,
                    stages=[['settle', 0, 10], ['left_approach', 10, 14], ['left_lower', 14, 18],
                            ['left_close', 18, 20], ['left_lift', 20, 23], ['right_approach', 23, 27],
                            ['right_lower', 27, 31], ['right_close', 31, 33], ['transfer', 33, 36],
                            ['right_lower_to_table', 36, 39], ['release', 39, 40], ['withdraw', 40, 43],
                            ['free_settle', 43, 48]])

    def declare(self, base, rope, centerline, backend):
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centerline, axis=0), axis=1))]
        self.ring_indices = [int(np.argmin(abs(arc-(arc[-1]-distance)))) for distance in (.015, .085)]
        for index in self.ring_indices:
            self.bands.append(FEMRopeAttachment(rope, centerline[index], radius=.008, strength=100.))

    def configure(self, task, controller, monitor):
        from .control import BoundedAlohaIK
        self.task, self.controller, self.monitor = task, controller, monitor
        self.ik = BoundedAlohaIK(task, controller)
        self.approaches = {}
        self.skin_ids = np.unique(monitor.faces)
        self.contact_distance = float(task.backend.rope_cfg.fem.contact_d_hat)
        solver = task.scene.sim.rigid_solver
        if not (solver._enable_collision and solver._enable_self_collision and solver._enable_neutral_collision):
            raise ValueError('Robot qualification requires collision, self-collision and neutral-pose collision pairs')
        self.homes = {side: (self.tool_position(arm), arm.hand_quat()) for side, arm in controller.arms.items()}
        for arm in controller.arms.values():
            arm.open_gripper()
        if not hasattr(monitor.ccd, 'surface'):
            raise ValueError('Robot probe requires native rigid surface CCD')
        self.native_robot_parts = [(part, controller.robot.get_link(part['name'])) for part in monitor.ccd.parts
                                   if part['name'].startswith(('left/', 'right/'))]

    @staticmethod
    def tool_position(arm):
        return arm.hand_pos()+rotation(arm.hand_quat()).apply(TOOL_OFFSET)

    def band_pose(self, band, side):
        index = self.ring_indices[band]
        centers = self.monitor.last_centers
        tangent = centers[index+1]-centers[index-1]
        tangent[2] = 0.
        tangent /= np.linalg.norm(tangent)
        # Pick the wrist-roll branch with the shorter rotation from home.
        options = []
        for z_axis in (tangent, -tangent):
            x_axis = np.array([0., 0., -1.])
            R = Rotation.from_matrix(np.column_stack((x_axis, np.cross(z_axis, x_axis), z_axis)))
            distance = (rotation(self.homes[side][1]).inv()*R).magnitude()
            options.append((distance, R.as_quat()[[3, 0, 1, 2]]))
        quat = min(options, key=lambda item: item[0])[1]
        center = self.monitor.last_positions[self.bands[band].indices].mean(axis=0)
        return center, quat

    def move(self, side, position, quat):
        target = self.ik.solve(side, np.asarray(position)-rotation(quat).apply(TOOL_OFFSET), quat)
        self.controller.arms[side].set_arm_qpos(target)

    def approach(self, side, position, quat, fraction):
        # Solve the hover pose from the neutral branch before moving. Cartesian
        # orientation interpolation from home previously drove forearm_roll to
        # -pi, although the same hover pose has a solution near zero roll.
        if side not in self.approaches:
            arm = self.controller.arms[side]
            start = arm.arm_qpos()
            end = self.ik.solve(side, np.asarray(position)-rotation(quat).apply(TOOL_OFFSET), quat,
                                seed=np.asarray(self.controller.cfg.home[side][:6]))
            self.approaches[side] = (start, end)
        start, end = self.approaches[side]
        u = float(smoothstep(fraction))
        self.controller.arms[side].set_arm_qpos((1-u)*start+u*end)

    def interpolate(self, side, start, end, quat_start, quat_end, fraction):
        u = float(smoothstep(fraction))
        R = Slerp([0., 1.], Rotation.from_quat(np.array([quat_start, quat_end])[:, [1, 2, 3, 0]]))(u)
        self.move(side, np.asarray(start)*(1-u)+np.asarray(end)*u, R.as_quat()[[3, 0, 1, 2]])

    def gaps(self, side, band):
        from .diagnostics import SurfaceCCD
        fem = self.monitor.last_positions
        band_faces = self.monitor.faces[np.all(np.isin(self.monitor.faces, self.bands[band].indices), axis=1)]
        result = []
        for finger in ('left', 'right'):
            key = (side, band, finger)
            part = next(p for p in self.monitor.ccd.parts if p['name'] == f'{side}/{finger}_finger_link')
            positions = np.vstack((fem, part['previous']))
            if key not in self.contact_checkers:
                faces = np.vstack((band_faces, part['faces']+len(fem)))
                self.contact_checkers[key] = SurfaceCCD(positions, faces,
                    primary_vertices=np.arange(len(positions)) < len(fem), cross_only=True)
            distance = self.contact_checkers[key].minimum_distance(positions, self.contact_distance+1e-6)
            result.append(float('inf') if distance is None else distance)
        return result

    def close_contact_monitors(self):
        for checker in self.contact_checkers.values():
            checker.close()

    def close(self, side, band, t, start):
        arm = self.controller.arms[side]
        if band in self.owners:
            arm.set_gripper(self.closed[side])
            return
        gaps = self.gaps(side, band)
        self.finger_gaps[side] = [gap if np.isfinite(gap) else None for gap in gaps]
        # Stop closing at contact; a position target beyond contact would add
        # unnecessary squeeze before the explicitly assisted grasp engages.
        if max(gaps) <= self.contact_distance+1e-6:
            positions = self.monitor.last_positions[self.bands[band].indices]
            self.offsets[band] = rotation(arm.hand_quat()).inv().apply(positions-arm.hand_pos())
            self.bands[band]._handle.engage(positions)
            self.bands[band].active = True
            self.owners[band] = side
            self.closed[side] = float(arm.gripper_qpos()[0])
            arm.set_gripper(self.closed[side])
            self.events.append(dict(time_s=t, event='contact_then_assisted_grasp', band=band,
                                    owner=side, native_finger_gaps_m=gaps))
        else:
            arm.set_gripper(.037-.025*float(smoothstep((t-start)/1.6)))

    def release(self, side, t):
        for band in [i for i, owner in self.owners.items() if owner == side]:
            self.bands[band].release()
            del self.owners[band]
            self.events.append(dict(time_s=t, event='release_band', band=band, owner=side))
        self.controller.arms[side].open_gripper()

    def update(self, t):
        if t < 10.:
            return
        if 'left' not in self.motion:
            center, quat = self.band_pose(0, 'left')
            self.motion['left'] = (center, quat)
        left, lq = self.motion['left']
        if t < 14.:
            self.stage = 'left_approach'
            self.approach('left', left+[0, 0, .05], lq, (t-10)/4)
        elif t < 18.:
            self.stage = 'left_lower'
            self.move('left', left+[0, 0, .05*(1-smoothstep((t-14)/4))], lq)
        elif t < 20.:
            self.stage = 'left_close'
            self.move('left', left, lq)
            self.close('left', 0, t, 18.)
        elif t < 23.:
            if 0 not in self.owners:
                raise RuntimeError('Left fingers did not establish a physical grasp')
            self.stage = 'left_lift'
            self.move('left', left+[0, 0, .03*smoothstep((t-20)/3)], lq)
        else:
            if 'right' not in self.motion:
                self.motion['right'] = self.band_pose(1, 'right')
            right, rq = self.motion['right']
            self.move('left', left+[0, 0, .03+(.08*smoothstep((t-33)/3) if t >= 33 else 0.)], lq)
            if t < 27.:
                self.stage = 'right_approach'
                self.approach('right', right+[0, 0, .05], rq, (t-23)/4)
            elif t < 31.:
                self.stage = 'right_lower'
                self.move('right', right+[0, 0, .05*(1-smoothstep((t-27)/4))], rq)
            elif t < 33.:
                self.stage = 'right_close'
                self.move('right', right, rq)
                self.close('right', 1, t, 31.)
            elif t < 36.:
                if 1 not in self.owners:
                    raise RuntimeError('Right fingers did not establish the receiving grasp')
                self.stage = 'transfer'
                self.release('left', t)
                self.move('right', right, rq)
            else:
                lowered = right.copy()
                lowered[2] = self.monitor.floor+.0048
                if t < 39.:
                    self.stage = 'right_lower_to_table'
                    self.interpolate('right', right, lowered, rq, rq, (t-36)/3)
                elif t < 40.:
                    self.stage = 'release'
                    self.move('right', lowered, rq)
                    self.release('right', t)
                else:
                    self.stage = 'withdraw' if t < 43. else 'free_settle'
                    self.move('right', lowered+[0, 0, .08*smoothstep((t-40)/3)], rq)
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            targets = arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band])
            self.bands[band]._handle.update_targets(targets)

    def observe(self, t, monitor):
        from topogym.world.rope import tensor_to_numpy
        for part, link in self.native_robot_parts:
            position = np.asarray(tensor_to_numpy(link.get_pos())).reshape(-1, 3)[0]
            quat = np.asarray(tensor_to_numpy(link.get_quat())).reshape(-1, 4)[0]
            rendered = rotation(quat).apply(part['local'])+position
            error = float(np.linalg.norm(rendered-part['previous'], axis=1).max())
            if error > self.max_native_pose_error:
                self.max_native_pose_error = error
                self.worst_native_pose_link = part['name']
        if self.max_native_pose_error > .002:
            raise RuntimeError('Native IPC and Genesis robot surfaces diverged by more than 2 mm')
        limits = np.asarray(self.controller.cfg.robot.arm_joint_limits)
        for arm in self.controller.arms.values():
            angles = arm.arm_qpos()
            violation = max(0., float(np.max(limits[:, 0]-angles)), float(np.max(angles-limits[:, 1])))
            self.max_joint_limit_violation = max(self.max_joint_limit_violation, violation)
        if self.max_joint_limit_violation > 1e-5:
            raise RuntimeError('Actual robot state exceeded an arm joint limit')
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            targets = arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band])
            error = float(np.linalg.norm(monitor.last_positions[self.bands[band].indices]-targets, axis=1).max())
            self.max_follow_error = max(self.max_follow_error, error)
        contacts = self.task.scene.sim.rigid_solver.collider.get_contacts()
        penetration = np.asarray(tensor_to_numpy(contacts['penetration']))
        if penetration.size and float(penetration.max()) > self.max_rigid_penetration:
            index = int(np.argmax(penetration))
            links = self.task.scene.sim.rigid_solver.links
            self.worst_rigid_contact = dict(time_s=t, penetration_m=float(penetration.max()),
                links=[links[int(np.asarray(tensor_to_numpy(contacts[key])).ravel()[index])].name
                       for key in ('link_a', 'link_b')])
        self.max_rigid_penetration = max(self.max_rigid_penetration, float(penetration.max()) if penetration.size else 0.)
        self.samples.append(dict(time_s=t, stage=self.stage, owners=dict(self.owners),
                                 left_tool=self.tool_position(self.controller.left).tolist(),
                                 right_tool=self.tool_position(self.controller.right).tolist(),
                                 max_native_robot_surface_error_m=self.max_native_pose_error,
                                 last_native_finger_gaps_m=dict(self.finger_gaps),
                                 robot=self.controller.state()))
        if self.stage.endswith('close') or self.owners:
            coupling = self.task.scene.sim.coupler._coupling_data
            forces = ({link.name: coupling.out_forces[0, i].tolist() for i, link in enumerate(coupling.links)
                       if 'finger' in link.name}
                      if self.controller.robot.material.coup_type == 'two_way_soft_constraint' else None)
            self.samples[-1]['native_coupling_forces_world_n'] = forces
            self.samples[-1]['gripper_targets'] = {s: a.current_gripper_qpos for s, a in self.controller.arms.items()}
        if self.max_rigid_penetration > .0005:
            raise RuntimeError('Robot/table or robot self-contact exceeded the rigid penetration limit')

    def report(self):
        acquired = {event['owner'] for event in self.events if event['event'] == 'contact_then_assisted_grasp'}
        checks = dict(two_physical_grasps=acquired == {'left', 'right'},
                      transfer_observed=any(s['stage'] == 'transfer' for s in self.samples),
                      released=not self.owners,
                      post_release_observed=bool(self.samples and self.samples[-1]['time_s'] >= 48.-1e-8),
                      pose_follow_error=self.max_follow_error <= .002,
                      actual_arm_joint_limits=self.max_joint_limit_violation <= 1e-5,
                      native_robot_surface_alignment=self.max_native_pose_error <= .002,
                      rigid_contact_penetration=self.max_rigid_penetration <= .0005)
        return dict(kind='assisted_grasp', events=self.events, checks=checks, passed=all(checks.values()),
                    final_active_constraints=len(self.owners), max_pose_follow_error_m=self.max_follow_error,
                    max_rigid_contact_penetration_m=self.max_rigid_penetration,
                    worst_rigid_contact=self.worst_rigid_contact,
                    ik_max_position_residual_m=self.ik.max_position_residual,
                    ik_max_rotation_residual_rad=self.ik.max_rotation_residual,
                    ik_initial_position_residual_m=self.ik.initial_position_residual,
                    ik_initial_rotation_residual_rad=self.ik.initial_rotation_residual,
                    max_actual_joint_limit_violation_rad=self.max_joint_limit_violation,
                    max_native_robot_surface_error_m=self.max_native_pose_error,
                    worst_native_pose_link=self.worst_native_pose_link,
                    last_native_finger_gaps_m=self.finger_gaps,
                    material_vertices=[band.indices.tolist() for band in self.bands],
                    scope='declared two tail bands, lift and transfer; no claim of pure frictional grasp')


class RobotContactActions(RobotGraspActions):
    """Short contact diagnosis; does not qualify the two-hand transfer gate."""
    def specification(self):
        result = super().specification()
        result.update(duration_s=18., release_s=12., post_release_s=6.,
                      stages=[['settle', 0, 3], ['left_approach', 3, 5], ['left_lower', 5, 7],
                              ['left_close', 7, 9], ['left_lift', 9, 11], ['left_lower', 11, 12],
                              ['release_withdraw', 12, 13], ['free_settle', 13, 18]])
        return result

    def update(self, t):
        if t < 3.:
            return
        if 'left' not in self.motion:
            self.motion['left'] = self.band_pose(0, 'left')
        left, quat = self.motion['left']
        if t < 5.:
            self.stage = 'left_approach'
            self.approach('left', left+[0, 0, .05], quat, (t-3)/2)
        elif t < 7.:
            self.stage = 'left_lower'
            self.move('left', left+[0, 0, .05*(1-smoothstep((t-5)/2))], quat)
        elif t < 9.:
            self.stage = 'left_close'
            self.move('left', left, quat)
            self.close('left', 0, t, 7.)
        elif t < 11.:
            if 0 not in self.owners:
                raise RuntimeError('Contact diagnosis did not establish a physical grasp')
            self.stage = 'left_lift'
            self.move('left', left+[0, 0, .02*smoothstep((t-9)/2)], quat)
        elif t < 12.:
            self.stage = 'left_lower'
            self.move('left', left+[0, 0, .02*(1-smoothstep(t-11))], quat)
        else:
            self.stage = 'release_withdraw' if t < 13 else 'free_settle'
            self.release('left', t)
            self.move('left', left+[0, 0, .06*smoothstep(t-12)], quat)
        for band, side in self.owners.items():
            arm = self.controller.arms[side]
            self.bands[band]._handle.update_targets(arm.hand_pos()+rotation(arm.hand_quat()).apply(self.offsets[band]))

    def report(self):
        result = super().report()
        checks = result['checks']
        checks.pop('transfer_observed')
        checks.pop('two_physical_grasps')
        checks['one_physical_grasp'] = any(e['event'] == 'contact_then_assisted_grasp' for e in self.events)
        checks['post_release_observed'] = bool(self.samples and self.samples[-1]['time_s'] >= 18.-1e-8)
        result.update(passed=all(checks.values()), scope='single-hand contact diagnosis; no two-hand transfer qualification')
        return result
