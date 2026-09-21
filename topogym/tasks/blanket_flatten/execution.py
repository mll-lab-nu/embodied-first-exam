"""Continuous physical execution, monitored assisted grasps, no particle pose writes."""
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.supervision.pbd_probe import probe_particles, probe_velocities
from .diagnostics import AcceptanceWindow, flatten_gates, health_gates, initial_gates


def array(x):
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


class Execution:
    def __init__(self, task, controller, cfg, output):
        self.task, self.controller, self.cfg, self.output = task, controller, cfg, Path(output)
        self.dt = float(cfg.env.sim.dt)
        self.step_count, self.phase, self.held = 0, 'birth', []
        self.history, self.events, self.frames, self.qframes, self.frame_steps, self.frame_phases = [], [], [], [], [], []
        self.worst = dict(minimum_height_m=float('inf'), maximum_edge_stretch=0.,
                          maximum_visual_edge_stretch=0., minimum_pad_height_m=float('inf'),
                          outside_table_particles=0, nonfinite_steps=0, maximum_tcp_error_m=0.)
        self.table_z = task.tabletop.frames.table_surface_origin[2]
        self.initialized = False
        self.initial_robot_clearance_checks = 0
        self.minimum_initial_robot_clearance = None
        self.motion_robot_clearance_checks = 0
        self.minimum_motion_robot_clearance = None
        self.release_count = 0
        self.preparation_report = None
        self.initial_stability_evidence = None
        self.initial_state_restoration = None
        self.grasp_safety_release = False
        self.stop_requested = False
        self.current_pull = None
        self._step = task.scene.step
        task.scene.step = self.step
        self.next_frame_time = 0.
        self.capture()
        # Birth-clearance rejection can occur before the first physics step.
        # Keep that failure report finite and serializable as well.
        self.worst['minimum_height_m'] = float(self.frames[0][:, 2].min()-self.table_z)
        self.worst['minimum_pad_height_m'] = float(self.controller.lowest_pad_z()-self.table_z)

    @property
    def time(self):
        return self.step_count*self.dt

    def label(self, name, **data):
        self.phase = name
        self.events.append(dict(step=self.step_count, seconds=self.time, phase=name, **data))
        print(f"phase={name} time={self.time:.3f} {json.dumps(data)}", flush=True)

    def capture(self):
        self.frames.append(probe_particles(self.task.cloth).astype(np.float32))
        self.qframes.append(array(self.controller.robot.get_qpos()).astype(np.float32).copy())
        self.frame_steps.append(self.step_count)
        self.frame_phases.append(self.phase)
        self.next_frame_time = self.time+1/float(self.cfg.run.fps)

    def step(self, *args, **kwargs):
        result = self._step(*args, **kwargs)
        self.step_count += 1
        positions = probe_particles(self.task.cloth)
        if not np.isfinite(positions).all():
            self.worst['nonfinite_steps'] += 1
            raise RuntimeError('Nonfinite particle state')
        strain = np.linalg.norm(positions[self.task.edges[:, 1]]-positions[self.task.edges[:, 0]], axis=1)/self.task.rest_lengths
        height = float(positions[:, 2].min()-self.table_z)
        outside = int(np.any((positions[:, :2] < self.task.table_bounds[0]) |
                            (positions[:, :2] > self.task.table_bounds[1]), axis=1).sum())
        pad = float(self.controller.lowest_pad_z()-self.table_z)
        self.worst['minimum_height_m'] = min(self.worst['minimum_height_m'], height)
        self.worst['minimum_pad_height_m'] = min(self.worst['minimum_pad_height_m'], pad)
        self.worst['maximum_edge_stretch'] = max(self.worst['maximum_edge_stretch'], float(strain.max()))
        self.worst['outside_table_particles'] = max(self.worst['outside_table_particles'], outside)
        guard = self.cfg.task.execution.get('release_guard_stretch')
        if self.held and guard is not None and float(strain.max()) >= float(guard):
            # A robot action reacts to strain by letting go. The original hard
            # integrity gate below stays unchanged, including on this step.
            released = self.held
            self.task.cloth.release_particle(particles_idx_local=released)
            self.held = []
            self.release_count += 1
            self.grasp_safety_release = True
            self.label(f'pull_{self.current_pull}_guarded_release',
                       material_stretch=float(strain.max()), particles=released,
                       actual_tcp_m=self.tcp().tolist(), target_placement_completed=False)
        if height < -float(self.cfg.task.initialization.penetration_tolerance_m) or outside:
            raise RuntimeError(f'Particle left tabletop: height={height}, outside={outside}')
        if float(strain.max()) > float(self.cfg.task.initialization.maximum_edge_stretch):
            raise RuntimeError(f'Material overstretch: {strain.max():.4f} at {self.phase}')
        if pad < -.001:
            raise RuntimeError(f'Gripper pad penetrated table by {-pad:.5f} m')
        if self.time+1e-9 >= self.next_frame_time:
            self.capture()
        if self.step_count % int(self.cfg.task.execution.check_every) == 0:
            if self.phase in ('gravity_drop', 'passive_stability') or self.phase.startswith('prepare_'):
                self.check_robot_clearance(positions)
            elif self.phase.endswith('_recenter') or (self.phase.endswith('_approach') and
                    bool(self.cfg.task.execution.get('monitor_free_motion_clearance', False))):
                self.check_robot_clearance(positions, motion=True)
            metrics = self.task.measure()
            self.worst['maximum_visual_edge_stretch'] = max(self.worst['maximum_visual_edge_stretch'],
                                                            metrics['maximum_visual_edge_stretch'])
            self.history.append(dict(step=self.step_count, seconds=self.time, phase=self.phase, metrics=metrics))
            if not all(health_gates(metrics, OmegaConf.to_container(self.cfg.task.initialization)).values()):
                raise RuntimeError(f'Health gate failed at {self.phase}: {metrics}')
            if self.step_count % max(1, round(1/self.dt)) == 0:
                print(f"physics t={self.time:.2f} phase={self.phase} coverage={metrics['coverage_ratio']:.3f} "
                      f"height={metrics['maximum_height_m']:.4f} stretch={metrics['maximum_edge_stretch']:.3f}", flush=True)
        if self.stop_requested:
            raise KeyboardInterrupt
        return result

    def wait(self, seconds):
        for _ in range(int(np.ceil(seconds/self.dt))):
            self.task.scene.step()

    def initialize(self):
        self.label('gravity_drop')
        self.check_robot_clearance(probe_particles(self.task.cloth))
        limits = OmegaConf.to_container(self.cfg.task.initialization, resolve=True)
        window = AcceptanceWindow(limits['stable_seconds'], limits['maximum_window_drift_m'])
        started = self.time
        for _ in range(int(np.ceil(limits['maximum_seconds']/self.dt))):
            self.task.scene.step()
            if self.step_count % int(self.cfg.task.execution.check_every):
                continue
            metrics = self.history[-1]['metrics']
            gates = initial_gates(metrics, limits)
            gates['minimum_time'] = self.time-started >= limits['minimum_seconds']
            if window.update(self.time, probe_particles(self.task.cloth), gates):
                self.initialized = True
                self.label('initial_state_accepted', metrics=metrics)
                return
        raise RuntimeError('Initial-state acceptance timed out')

    def verify_passive_stability(self):
        self.label('passive_stability')
        limits = OmegaConf.to_container(self.cfg.task.initialization)
        window = AcceptanceWindow(limits['stable_seconds'], limits['maximum_window_drift_m'])
        started = self.time
        minimum = float(self.cfg.task.execution.stability_seconds)
        success = False
        while self.time-started < minimum+4:
            self.task.scene.step()
            if self.step_count % int(self.cfg.task.execution.check_every):
                continue
            gates = initial_gates(self.history[-1]['metrics'], limits)
            success = window.update(self.time, probe_particles(self.task.cloth), gates)
            if success and self.time-started >= minimum:
                break
        success = success and self.time-started >= minimum
        evidence = dict(passed=bool(success), gates=gates, passive_seconds=self.time-started,
                        window_seconds=window.duration, maximum_window_drift_m=window.drift_m)
        self.initial_stability_evidence = evidence
        self.label('initial_passive_stability_checked', **evidence)
        return success, evidence

    def check_robot_clearance(self, positions, *, motion=False):
        from .robot_clearance import robot_clearance
        distance = robot_clearance(self.controller.robot, positions, self.task.faces)
        if motion:
            self.motion_robot_clearance_checks += 1
            self.minimum_motion_robot_clearance = distance if self.minimum_motion_robot_clearance is None else min(
                self.minimum_motion_robot_clearance, distance)
        else:
            self.initial_robot_clearance_checks += 1
            self.minimum_initial_robot_clearance = distance if self.minimum_initial_robot_clearance is None else min(
                self.minimum_initial_robot_clearance, distance)
        if distance < float(self.cfg.task.execution.initial_robot_clearance_m):
            raise RuntimeError(f'Unassisted blanket intersects parked robot or clearance too small: {distance:.6f} m')

    def tcp(self):
        p = np.asarray(self.controller.grasp_center_pos(), dtype=float)
        p[2] = self.controller.lowest_pad_z()
        return p

    def move(self, target, *, speed, hold=.25):
        target = np.asarray(target, dtype=float)
        start = self.tcp()
        duration = max(.25, np.linalg.norm(target-start)/speed)
        count = int(np.ceil(duration/self.dt/4))
        for i in range(1, count+1):
            alpha = i/count
            alpha = alpha*alpha*(3-2*alpha)
            desired = start+(target-start)*alpha
            offset = self.tcp()-self.controller.hand_pos()
            self.controller.move_ee_to(desired-offset, quat=[0, 1, 0, 0], steps=4, continuous_ik=True)
            if self.grasp_safety_release:
                return False
        self.hold_tcp(target, hold)
        if self.grasp_safety_release:
            return False
        error = float(np.linalg.norm(self.tcp()-target))
        self.worst['maximum_tcp_error_m'] = max(self.worst['maximum_tcp_error_m'], error)
        if error > float(self.cfg.task.execution.maximum_tracking_error_m):
            raise RuntimeError(f'Robot TCP tracking failed: {error:.4f} m, target {target}, actual {self.tcp()}')
        return True

    def hold_tcp(self, target, seconds):
        for _ in range(int(np.ceil(seconds/self.dt/4))):
            offset = self.tcp()-self.controller.hand_pos()
            self.controller.move_ee_to(np.asarray(target)-offset, quat=[0, 1, 0, 0], steps=4, continuous_ik=True)
            if self.grasp_safety_release:
                return

    def select_corner(self, signs):
        uv_target = np.asarray(signs)*[self.task.layout.length_m/2, self.task.layout.width_m/2]
        distance = np.linalg.norm(self.task.material_uv-uv_target, axis=1)
        return int(distance.argmin())

    def recenter(self, number):
        """Physically unwind the arm between released grasps; never reset poses."""
        if self.held:
            raise RuntimeError('Cannot recenter while grasping the blanket')
        start = self.controller.arm_qpos()
        target = np.asarray(self.cfg.robot_control.home.qpos[:self.controller.arm_joint_count], dtype=float)
        self.label(f'pull_{number}_recenter', start_arm_qpos=start.tolist(), target_arm_qpos=target.tolist())
        speed = float(self.cfg.task.execution.get('recenter_joint_speed_rad_s', .8))
        duration = max(.5, float(np.max(np.abs(target-start)))/speed)
        count = int(np.ceil(duration/self.dt/4))
        self.controller.open_gripper(steps=0)
        for i in range(1, count+1):
            alpha = i/count
            alpha = alpha*alpha*(3-2*alpha)
            self.controller.robot.control_dofs_position(start+(target-start)*alpha, self.controller.arm_dofs)
            self.controller.step(4)
        self.wait(.5)
        error = float(np.max(np.abs(self.controller.arm_qpos()-target)))
        if error > .02:
            raise RuntimeError(f'Arm recenter tracking failed: {error:.4f} rad')
        self.events.append(dict(step=self.step_count, seconds=self.time, phase=f'pull_{number}_recenter_completed',
                                maximum_joint_error_rad=error))

    def pull(self, signs, target, number, *, grasp_site=None):
        cfg = self.cfg.task.execution
        self.current_pull = number
        self.grasp_safety_release = False
        corner = self.select_corner(signs) if grasp_site is None else int(grasp_site['particle'])
        self.label(f'pull_{number}_approach', material_corner=list(signs), particle=corner,
                   target=np.asarray(target).tolist(), grasp_site=grasp_site)
        self.controller.open_gripper(steps=0)
        # Opening proceeds while approaching; the descent takes longer than the
        # calibrated opening time, and bilateral contact is measured below.
        point = probe_particles(self.task.cloth)[corner]
        safe = point.copy()
        safe[2] = max(self.table_z+float(cfg.travel_height_m),
                      float(probe_particles(self.task.cloth)[:, 2].max())+.03)
        current = self.tcp()
        if current[2] < safe[2]:
            self.move([*current[:2], safe[2]], speed=float(cfg.free_speed_m_s))
        lane = cfg.get('approach_lane_x_m')
        if lane is not None:
            # A forward lane prevents an XY chord across the near-base region.
            self.move([float(lane), self.tcp()[1], safe[2]], speed=float(cfg.free_speed_m_s))
            self.move([float(lane), safe[1], safe[2]], speed=float(cfg.free_speed_m_s))
        self.move(safe, speed=float(cfg.free_speed_m_s))
        point = probe_particles(self.task.cloth)[corner]
        # Reject a buried corner: the hand must reach a visible top layer.
        particles = probe_particles(self.task.cloth)
        near = np.linalg.norm(particles[:, :2]-point[:2], axis=1) < .008
        allowed_occlusion = float(cfg.get('maximum_grasp_occlusion_m', .012)) if grasp_site is None else grasp_site['maximum_occlusion_m']
        if particles[near, 2].max()-point[2] > allowed_occlusion:
            raise RuntimeError(f'Corner {signs} is buried under another layer')
        self.label(f'pull_{number}_descend')
        tcp = point+[0, 0, .002]
        self.move(tcp, speed=.065, hold=.5)
        self.label(f'pull_{number}_close')
        self.controller.set_gripper(0., steps=0)
        self.hold_tcp(tcp, float(cfg.gripper_seconds))
        particles = probe_particles(self.task.cloth)
        point = particles[corner]
        near = np.linalg.norm(particles[:, :2]-point[:2], axis=1) < .008
        overhead_depth = float(particles[near, 2].max()-point[2])
        if overhead_depth > allowed_occlusion:
            raise RuntimeError(f'Grasp point became occluded before attachment: {overhead_depth:.6f} m')
        spatial = np.linalg.norm(particles-point, axis=1)
        material = np.linalg.norm(self.task.material_uv-self.task.material_uv[corner], axis=1)
        patch = np.flatnonzero((spatial <= cfg.grasp_radius_m) & (material <= cfg.material_patch_radius_m))
        from topogym.robot.gripper import pad_vertices, robotiq_pad_centres
        from scipy.spatial import ConvexHull
        import trimesh
        pads = pad_vertices(self.controller.robot, 'robotiq_2f85').reshape(2, 8, 3)
        distances = []
        for vertices in pads:
            mesh = trimesh.Trimesh(vertices, ConvexHull(vertices).simplices, process=False)
            _, distance, _ = trimesh.proximity.closest_point_naive(mesh, point[None])
            distances.append(float(distance[0]))
        contact = max(distances) <= cfg.contact_tolerance_m
        if not contact or np.linalg.norm(self.tcp()-point) > .012 or not len(patch):
            raise RuntimeError(f'Grasp proximity failed: pad gaps={distances}, tcp={self.tcp()}, cloth={point}')
        self.task.cloth.fix_particles_to_link(self.controller.ee_link.idx, particles_idx_local=patch.tolist())
        self.held = patch.tolist()
        self.label(f'pull_{number}_attach', particles=self.held, pad_surface_distances_m=distances,
                   overhead_depth_m=overhead_depth, maximum_allowed_occlusion_m=allowed_occlusion,
                   actual_pad_gap_m=float(np.linalg.norm(np.diff(robotiq_pad_centres(self.controller.robot), axis=0))))
        # Reference follows the actual captured material; attachment does not move it.
        offset = self.tcp()-particles[patch].mean(axis=0)
        raised = particles[patch].mean(axis=0).copy()
        boundary = grasp_site is not None
        lift = float(cfg.get('boundary_lift_m', cfg.lift_m)) if boundary else float(cfg.lift_m)
        carry_speed = float(cfg.get('boundary_carry_speed_m_s', cfg.carry_speed_m_s)) if boundary else float(cfg.carry_speed_m_s)
        raised[2] += lift
        self.label(f'pull_{number}_lift', lift_m=lift, carry_speed_m_s=carry_speed)
        self.move(raised+offset, speed=carry_speed)
        if boundary and not self.grasp_safety_release:
            self.hold_tcp(raised+offset, float(cfg.get('boundary_hang_seconds', 0.)))
        target = np.asarray(target, dtype=float)
        high = target.copy(); high[2] = raised[2]
        if not self.grasp_safety_release:
            tcp_goal = high+offset
            path = [tcp_goal[:2]]
            if bool(cfg.get('detour_held_motion_around_base', False)):
                from .grasp_sites import carry_waypoints_xy
                path = carry_waypoints_xy(self.tcp()[:2], tcp_goal[:2],
                    array(self.controller.robot.get_link('link0').get_pos())[:2],
                    cfg.grasp_workspace_radial_m, lane_x=float(cfg.approach_lane_x_m))
            self.label(f'pull_{number}_spread', tcp_waypoints_xy_m=[p.tolist() for p in path])
            for xy in path:
                if not self.move([*xy, tcp_goal[2]], speed=carry_speed):
                    break
        if not self.grasp_safety_release:
            self.label(f'pull_{number}_lower')
            self.move(target+offset, speed=float(cfg.get('lowering_speed_m_s', cfg.carry_speed_m_s)))
        release_tcp = self.tcp().copy()
        if self.held:
            self.task.cloth.release_particle(particles_idx_local=self.held)
            self.held = []
            self.release_count += 1
            self.label(f'pull_{number}_release')
        self.grasp_safety_release = False
        self.controller.open_gripper(steps=0)
        self.hold_tcp(release_tcp, float(cfg.gripper_seconds))
        self.label(f'pull_{number}_retreat')
        self.move([*self.tcp()[:2], self.table_z+float(cfg.travel_height_m)], speed=float(cfg.free_speed_m_s))
        self.wait(.5)
        metrics = self.task.measure()
        self.label(f'pull_{number}_result', metrics=metrics)

    def flatten(self):
        center = np.array([*self.cfg.task.execution.target_center_xy_m,
                           self.table_z+float(self.cfg.task.execution.get('target_release_height_m', .008))])
        yaw = np.radians(float(self.cfg.task.execution.target_yaw_deg))
        rotate = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
        sequence = [tuple(signs) for signs in self.cfg.task.execution.get('corner_sequence',
                    [(-1,-1), (1,-1), (-1,1), (1,1)])]
        cursor = 0
        for i in range(int(self.cfg.task.execution.max_pulls)):
            if i and bool(self.cfg.task.execution.get('return_home_between_pulls', False)):
                self.recenter(i+1)
            signs = sequence[cursor % len(sequence)]
            grasp_site = None
            if bool(self.cfg.task.execution.get('skip_buried_corners', False)):
                particles = probe_particles(self.task.cloth)
                radial_limits = self.cfg.task.execution.get('grasp_workspace_radial_m')
                base_xy = array(self.controller.robot.get_link('link0').get_pos())[:2] if radial_limits is not None else None
                occlusion_limit = float(self.cfg.task.execution.get('maximum_grasp_occlusion_m', .012))
                for offset in range(len(sequence)):
                    candidate = sequence[(cursor+offset) % len(sequence)]
                    corner = self.select_corner(candidate)
                    point = particles[corner]
                    near = np.linalg.norm(particles[:, :2]-point[:2], axis=1) < .008
                    visible = particles[near, 2].max()-point[2] <= occlusion_limit
                    reachable = radial_limits is None or radial_limits[0] <= np.linalg.norm(point[:2]-base_xy) <= radial_limits[1]
                    if visible and reachable:
                        signs = candidate
                        cursor += offset
                        break
                    radius = self.cfg.task.execution.get('fallback_boundary_radius_m')
                    if radius is not None:
                        from .grasp_sites import exposed_boundary_site
                        site = exposed_boundary_site(particles, self.task.material_uv, corner,
                            [self.task.layout.length_m/2, self.task.layout.width_m/2],
                            material_radius=float(radius), maximum_occlusion=min(.003, occlusion_limit),
                            base_xy=base_xy, radial_limits=radial_limits,
                            corner_reason='occluded' if not visible else 'unreachable')
                        if site is not None:
                            signs, grasp_site = candidate, site
                            cursor += offset
                            break
                else:
                    raise RuntimeError('No exposed material corner available for the next pull')
            cursor += 1
            target = center.copy()
            target[:2] += rotate @ (np.asarray(signs)*[self.task.layout.length_m/2-.008, self.task.layout.width_m/2-.008])
            if grasp_site is not None:
                # Place the selected material point at its own flat target.
                scale = 1-.008/np.asarray([self.task.layout.length_m/2, self.task.layout.width_m/2])
                target[:2] = center[:2] + rotate @ (self.task.material_uv[grasp_site['particle']]*scale)
                if bool(self.cfg.task.execution.get('repeat_boundary_corner', True)):
                    cursor -= 1
            first_target = self.cfg.task.execution.get('first_pull_target_xy_m')
            if i == 0 and first_target is not None:
                # Open the bundle without dragging its opposite corner into
                # the robot's near-base reach exclusion region.
                target[:2] = np.asarray(first_target, dtype=float)
            if bool(self.cfg.task.execution.get('project_targets_into_workspace', False)):
                from .grasp_sites import reachable_target_xy
                nominal = target.copy()
                base_xy = array(self.controller.robot.get_link('link0').get_pos())[:2]
                target[:2] = reachable_target_xy(target[:2], base_xy, self.cfg.task.execution.grasp_workspace_radial_m)
                if not np.array_equal(target, nominal):
                    self.label(f'pull_{i+1}_target_adjusted', nominal_target_m=nominal.tolist(), target_m=target.tolist(),
                               reason='boundary placement waypoint outside radial reach range')
            self.pull(signs, target, i+1, grasp_site=grasp_site)
            if all(flatten_gates(self.task.measure(), OmegaConf.to_container(self.cfg.task.success), released=True).values()):
                break

    def final_check(self):
        self.label('final_release_and_retreat')
        if self.held:
            raise RuntimeError('Grasp still active at final check')
        self.move([-.25, -.34, self.table_z+.25], speed=float(self.cfg.task.execution.free_speed_m_s))
        self.label('final_free_settle')
        limits = OmegaConf.to_container(self.cfg.task.success)
        window = AcceptanceWindow(limits['stable_seconds'], limits['maximum_window_drift_m'])
        passed = False
        for _ in range(int(np.ceil(float(self.cfg.task.execution.final_settle_seconds)/self.dt))):
            self.task.scene.step()
            if self.step_count % int(self.cfg.task.execution.check_every):
                continue
            metrics = self.task.measure()
            passed = window.update(self.time, probe_particles(self.task.cloth), flatten_gates(metrics, limits, released=not self.held))
        return passed, dict(window_seconds=window.duration, maximum_window_drift_m=window.drift_m,
                            gates=flatten_gates(self.task.measure(), limits, released=not self.held))

    def save(self, *, success, error=None, final_evidence=None):
        if self.frame_steps[-1] != self.step_count:
            self.capture()
        np.savez_compressed(self.output/'physical_trace.npz', positions=np.asarray(self.frames),
            robot_qpos=np.asarray(self.qframes), steps=np.asarray(self.frame_steps), phases=np.asarray(self.frame_phases),
            dt=self.dt, material_uv=self.task.material_uv, faces=self.task.faces,
            supports=self.task.supports, weights=self.task.weights)
        try:
            final_metrics = self.task.measure()
        except Exception as exc:
            # Diagnostic failures must not discard the otherwise recorded run.
            success = False
            error = f'{error or "Final diagnostics failed"}; {exc}'
            final_metrics = dict(finite=False, diagnostic_error=str(exc))
        report = dict(task_id='blanket_flatten', mode=str(self.cfg.run.mode), success=bool(success), error=error,
            initialization_accepted=self.initialized, physics_steps=self.step_count, simulated_seconds=self.time,
            full_robot_task_verified=bool(success and self.cfg.run.mode == 'robot'),
            live_particle_position_writes=False, live_robot_position_writes_after_home=False,
            grasp_model='geometric bilateral pad proximity, then local particle-to-link assistance',
            maximum_grasp_occlusion_m=float(self.cfg.task.execution.get('maximum_grasp_occlusion_m', .012)),
            robot_soft_coupling=False, active_grasp_particles=self.held, releases=self.release_count,
            health_checked_every_outer_step=True, visual_check_interval_s=int(self.cfg.task.execution.check_every)*self.dt,
            initial_robot_clearance_checks=self.initial_robot_clearance_checks,
            minimum_initial_robot_clearance_m=self.minimum_initial_robot_clearance,
            motion_robot_clearance_checks=self.motion_robot_clearance_checks,
            minimum_motion_robot_clearance_m=self.minimum_motion_robot_clearance,
            worst=self.worst, final=final_metrics, final_evidence=final_evidence, events=self.events,
            history=self.history, binding=self.task.binding_report, birth=self.task.birth_report,
            preparation=self.preparation_report, initial_stability_evidence=self.initial_stability_evidence,
            initial_state_restoration=self.initial_state_restoration,
            frame_count=len(self.frames), fps=int(self.cfg.run.fps))
        (self.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        self.task.scene.step = self._step
        return report
