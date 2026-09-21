"""Two externally driven cloth grips; no robot or particle-position animation.

Each grip fixes a material patch and prescribes bounded particle velocities.
The PBD solver integrates those velocities and solves the remaining cloth under
unchanged gravity, material constraints and self-contact. End-band grips model
holding several folded layers together, not two point contacts or frictional
robot fingers. Subsequent corner grips are small connected material patches.
"""
import json
from pathlib import Path
import shutil
import signal
import traceback

import hydra
import numpy as np
from omegaconf import OmegaConf

from topogym.supervision.pbd_probe import probe_particles
from .diagnostics import AcceptanceWindow, flatten_gates, health_gates, initial_gates
from .preparation import rotate_vectors


def corner_patch(uv, corner, radius):
    distance = np.linalg.norm(uv-np.asarray(corner), axis=1)
    indices = np.flatnonzero(distance <= radius)
    if len(indices) < 3:
        raise ValueError('A virtual grip needs at least three material particles')
    return indices


def bounded_grip_velocity(current, target, dt, maximum_speed):
    velocity = (np.asarray(target)-np.asarray(current))/dt
    scale = min(1., maximum_speed/max(float(np.linalg.norm(velocity, axis=1).max()), 1e-12))
    return velocity*scale


def upright_grip_targets(point_groups, target_span, center_z, fraction):
    """Turn a two-ended bundle upright while each held patch stays rigid."""
    if len(point_groups) != 2 or not 0 <= fraction <= 1:
        raise ValueError('Uprighting requires two grips and a fraction in [0, 1]')
    centers = [p.mean(axis=0) for p in point_groups]
    midpoint = np.mean(centers, axis=0)
    span = np.linalg.norm(centers[1]-centers[0])
    if span <= 1e-6 or target_span <= 0:
        raise ValueError('Grip span must be positive')
    destination = midpoint.copy()
    destination[2] = center_z
    scale = 1+fraction*(target_span/span-1)
    return [rotate_vectors(p-c+(c-midpoint)*scale, [0., 1., 0.], fraction*np.pi/2)
            +midpoint+(destination-midpoint)*fraction for p, c in zip(point_groups, centers)]


def corner_material_rotation(offsets, material_uv):
    """Fit a rigid wrist turn: material u points down, material v points +y."""
    uv = material_uv-material_uv.mean(axis=0)
    if np.linalg.matrix_rank(uv) < 2:
        raise ValueError('Corner material patch must span two dimensions')
    target = np.column_stack((np.zeros(len(uv)), uv[:, 1], -uv[:, 0]))
    left, _, right = np.linalg.svd(offsets.T@target)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(right.T@left.T)
    rotation = right.T@correction@left.T
    rms = float(np.sqrt(np.mean(np.sum((offsets@rotation.T-target)**2, axis=1))))
    return rotation, rms


def edge_following_lay_targets(offsets, held_y, free_edge_center, material_span,
                               start_z, landing_z, fraction):
    """Lower first, then lay along the observed free edge without feeding slack."""
    if material_span <= 0 or not 0 <= fraction <= 1 or landing_z > start_z:
        raise ValueError('Invalid laying span, height or progress')
    height = landing_z+(start_z-landing_z)*np.cos(fraction*np.pi/2)
    dz = height-free_edge_center[2]
    reach = np.sqrt(max(0., material_span**2-dz**2))
    angle = np.arctan2(reach, max(dz, 1e-9))
    return [rotate_vectors(o, [0., 1., 0.], -angle)+
            np.array([free_edge_center[0]-reach, y, height])
            for o, y in zip(offsets, held_y, strict=True)]


class VirtualHands:
    def __init__(self, task, cfg, output, restoration):
        self.task, self.cfg, self.output = task, cfg, Path(output)
        self.dt, self.step_count = float(cfg.env.sim.dt), 0
        self.table_z = float(task.tabletop.frames.table_surface_origin[2])
        self.phase, self.stop_requested = 'initial_passive_settle', False
        self.grips, self.events, self.history = [], [], []
        self.frames, self.steps, self.phases, self.hand_frames = [], [], [], []
        self.worst = dict(nonfinite_steps=0, minimum_height_m=float('inf'),
                          maximum_edge_stretch=0., maximum_visual_edge_stretch=0., outside_table_particles=0)
        self.restoration = restoration
        self.rest = task.cloth._edges_len_rest.copy()
        self.initialized = False
        self.releases = 0
        self.maximum_grips = 0
        self.capture()
        self.worst['minimum_height_m'] = float(self.frames[0][:, 2].min()-self.table_z)

    @property
    def time(self):
        return self.step_count*self.dt

    def label(self, phase, **data):
        self.phase = phase
        event = dict(phase=phase, step=self.step_count, seconds=self.time, **data)
        self.events.append(event)
        print(json.dumps(event), flush=True)

    def capture(self):
        p = probe_particles(self.task.cloth)
        self.frames.append(p.astype(np.float32))
        self.steps.append(self.step_count)
        self.phases.append(self.phase)
        centers = np.full((2, 3), np.nan, dtype=np.float32)
        for i, grip in enumerate(self.grips):
            centers[i] = p[grip['indices']].mean(axis=0)
        self.hand_frames.append(centers)

    def step(self):
        self.task.scene.step()
        self.step_count += 1
        p = probe_particles(self.task.cloth)
        if not np.isfinite(p).all():
            self.worst['nonfinite_steps'] += 1
            raise RuntimeError('Nonfinite particle state')
        stretch = float(np.max(np.linalg.norm(p[self.task.edges[:, 1]]-p[self.task.edges[:, 0]], axis=1)/self.task.rest_lengths))
        height = float(p[:, 2].min()-self.table_z)
        outside = int(np.any((p[:, :2] < self.task.table_bounds[0]) | (p[:, :2] > self.task.table_bounds[1]), axis=1).sum())
        self.worst['maximum_edge_stretch'] = max(self.worst['maximum_edge_stretch'], stretch)
        self.worst['minimum_height_m'] = min(self.worst['minimum_height_m'], height)
        self.worst['outside_table_particles'] = max(self.worst['outside_table_particles'], outside)
        if self.step_count % round(1/(self.dt*float(self.cfg.run.fps))) == 0:
            self.capture()
        if stretch > float(self.cfg.task.initialization.maximum_edge_stretch) or height < -.001 or outside:
            raise RuntimeError(f'Cloth health rejected at {self.phase}: stretch={stretch}, height={height}, outside={outside}')
        if self.step_count % int(self.cfg.task.execution.check_every) == 0:
            metrics = self.task.measure()
            self.worst['maximum_visual_edge_stretch'] = max(self.worst['maximum_visual_edge_stretch'], metrics['maximum_visual_edge_stretch'])
            self.history.append(dict(seconds=self.time, phase=self.phase, metrics=metrics))
            if not all(health_gates(metrics, OmegaConf.to_container(self.cfg.task.initialization)).values()):
                raise RuntimeError(f'Health gates failed: {metrics}')
            print(f'physics t={self.time:.2f} phase={self.phase} coverage={metrics["coverage_ratio"]:.4f} height={metrics["maximum_height_m"]:.4f} stretch={stretch:.4f}', flush=True)
        if self.stop_requested:
            raise KeyboardInterrupt
        return stretch

    def grasp(self, groups, kind):
        if self.grips or not 1 <= len(groups) <= 2:
            raise ValueError('Release before changing the at-most-two grips')
        flat = np.concatenate(groups)
        if len(np.unique(flat)) != len(flat):
            raise ValueError('Virtual grips must not overlap')
        p = probe_particles(self.task.cloth)
        for indices in groups:
            center = p[indices].mean(axis=0)
            self.grips.append(dict(indices=indices, center=center, offsets=p[indices]-center))
            self.task.cloth.fix_particles(indices)
        self.maximum_grips = max(self.maximum_grips, len(self.grips))
        self.label('grasp_'+kind, kind=kind, groups=[i.tolist() for i in groups],
                   centers=[g['center'].tolist() for g in self.grips],
                   extent_m=[np.ptp(p[i], axis=0).tolist() for i in groups],
                   selection='material-coordinate oracle; no finger accessibility claim')

    def release(self):
        for grip in self.grips:
            self.task.cloth.set_particles_vel(0., grip['indices'])
            self.task.cloth.release_particle(grip['indices'])
        self.grips = []
        self.releases += 1
        self.label('release_all_virtual_grips')

    def release_one(self, index):
        grip = self.grips.pop(index)
        self.task.cloth.set_particles_vel(0., grip['indices'])
        self.task.cloth.release_particle(grip['indices'])
        self.releases += 1
        self.label('release_one_virtual_grip', released_particles=grip['indices'].tolist(), remaining_grips=len(self.grips))

    def drive(self, name, targets, seconds, hold=.4):
        self.label(name)
        elapsed, progress, strain = 0., 0., 1.
        cfg = self.cfg.task.virtual_hands
        while progress < seconds+hold:
            if elapsed > 3*(seconds+hold)+5:
                raise RuntimeError(f'Strain-limited motion stalled at {name}')
            scale = float(np.clip((float(cfg.pause_stretch)-strain)/(float(cfg.pause_stretch)-float(cfg.slow_stretch)), 0., 1.))
            scale = max(float(cfg.get('minimum_motion_scale', 0.)), scale)
            progress += self.dt*scale
            alpha = min(1., progress/seconds)
            alpha = alpha*alpha*(3-2*alpha)
            p = probe_particles(self.task.cloth)
            for grip, target in zip(self.grips, targets(alpha), strict=True):
                indices = grip['indices']
                v = bounded_grip_velocity(p[indices], target, self.dt, float(cfg.maximum_speed_m_s))
                self.task.cloth.set_particles_vel(v, indices)
            strain = self.step()
            elapsed += self.dt
        np.savez_compressed(self.output/f'{name}.npz', positions=probe_particles(self.task.cloth),
                            material_uv=self.task.material_uv, faces=self.task.faces)
        self.label(name+'_finished', metrics=self.task.measure())

    def settle(self, seconds, *, final=False):
        if self.grips:
            raise ValueError('Passive settling requires released grips')
        limits = OmegaConf.to_container(self.cfg.task.success if final else self.cfg.task.initialization)
        window = AcceptanceWindow(limits['stable_seconds'], limits['maximum_window_drift_m'])
        passed, gates = False, {}
        for _ in range(round(seconds/self.dt)):
            self.step()
            if self.step_count % int(self.cfg.task.execution.check_every) == 0:
                metrics = self.history[-1]['metrics']
                gates = flatten_gates(metrics, limits, released=True) if final else initial_gates(metrics, limits)
                passed = window.update(self.time, probe_particles(self.task.cloth), gates)
        if window.previous_time is None or self.time > window.previous_time:
            metrics = self.task.measure()
            gates = flatten_gates(metrics, limits, released=True) if final else initial_gates(metrics, limits)
            passed = window.update(self.time, probe_particles(self.task.cloth), gates)
        return bool(passed), dict(gates=gates, passive_seconds=seconds, window_seconds=window.duration,
                                 maximum_window_drift_m=window.drift_m)

    def unfold(self):
        from .gathered_geometry import gathered_target
        p, uv = probe_particles(self.task.cloth), self.task.material_uv
        length, width = self.task.layout.length_m, self.task.layout.width_m
        cfg = self.cfg.task.virtual_hands
        groups = [np.flatnonzero(sign*uv[:, 0] >= length/2-float(cfg.end_band_m)) for sign in (-1, 1)]
        self.grasp(groups, 'two_folded_end_bands')
        centers = [g['center'].copy() for g in self.grips]
        offsets = [g['offsets'].copy() for g in self.grips]
        lift = float(cfg.untwist_lift_m)
        slack = float(cfg.get('end_slack_m', 0.))
        raised_centers = [c+[-sign*slack, 0, lift] for sign, c in zip((-1, 1), centers)]
        self.drive('lift_twisted_bundle', lambda t: [o+c+(goal-c)*t for o, c, goal in zip(offsets, centers, raised_centers)], 4.)
        reference = gathered_target(uv, length, width, 1., 0., self.cfg.task.preparation.gathered)
        angles = []
        for indices, offset in zip(groups, offsets):
            r = reference[indices]-reference[indices].mean(axis=0)
            angles.append(float(np.arctan2(np.sum(offset[:, 2]*r[:, 1]-offset[:, 1]*r[:, 2]),
                                          np.sum(offset[:, 1]*r[:, 1]+offset[:, 2]*r[:, 2]))))
        self.label('untwist_plan', end_rotation_deg=(-np.degrees(angles)).tolist())
        self.drive('untwist_opposite_ends', lambda t: [rotate_vectors(o, [1., 0., 0.], -angle*t)+c
                   for o, c, angle in zip(offsets, raised_centers, angles)], float(cfg.untwist_seconds))
        handoff_in_air = bool(cfg.get('handoff_in_air', False))
        if handoff_in_air:
            upright = bool(cfg.get('upright_before_release', False))
            if upright:
                p = probe_particles(self.task.cloth)
                patches = [p[g['indices']].copy() for g in self.grips]
                material_span = abs(np.diff([uv[g['indices'], 0].mean() for g in self.grips])[0])
                self.drive('rotate_bundle_upright_with_two_grips',
                           lambda t: upright_grip_targets(patches, .985*material_span,
                                                        self.table_z+length/2+.11, t),
                           float(cfg.upright_seconds), hold=1.)
            self.release_one(1)
            p = probe_particles(self.task.cloth)
            indices = self.grips[0]['indices']
            c = p[indices].mean(axis=0)
            o = p[indices]-c
            goal = c.copy()
            goal[2] = max(c[2], self.table_z+length+.07)
            self.drive('suspend_with_one_end_band', lambda t: [o+c+(goal-c)*t],
                       1.5 if upright else float(cfg.suspend_seconds), hold=1.)
            if probe_particles(self.task.cloth)[:, 2].min() < self.table_z+.02:
                raise RuntimeError('Whole strip did not clear the table before corner handoff')
            # Release the broad end band before acquiring the two corner patches;
            # no solver step or particle-position edit occurs during this ideal handoff.
            self.release()
        else:
            rotated = [rotate_vectors(o, [1., 0., 0.], -angle) for o, angle in zip(offsets, angles)]
            landed = [np.array([c[0], c[1], self.table_z+.004-o[:, 2].min()]) for c, o in zip(raised_centers, rotated)]
            self.drive('lower_untwisted_bundle', lambda t: [o+c*(1-t)+goal*t
                       for o, c, goal in zip(rotated, raised_centers, landed)], 4.)
            self.release()
            self.label('untwisted_free_settle')
            self.settle(1.)

        groups = [corner_patch(uv, [-length/2, sign*width/2], float(cfg.corner_radius_m)) for sign in (-1, 1)]
        self.grasp(groups, 'two_adjacent_corners')
        p = probe_particles(self.task.cloth)
        centers = [p[i].mean(axis=0) for i in groups]
        offsets = [p[i]-c for i, c in zip(groups, centers)]
        center_xy = np.asarray(self.cfg.task.origin_xy_m)
        lay_length = length-.02
        far_x = center_xy[0]+lay_length/2
        # Remove table friction before opening the pleats. Opening and sweeping
        # sideways while the lower layers remain on the table can trap a crease.
        suspended = [np.array([c[0], c[1], self.table_z+length+.05]) for c in centers]
        self.drive('suspend_folded_sheet_vertically', lambda t: [o+c+(goal-c)*t for o, c, goal in zip(offsets, centers, suspended)],
                   1. if handoff_in_air else float(cfg.suspend_seconds), hold=.8)
        coupled_alignment = False
        opening_offsets = lambda t: offsets
        peel = 0.
        if bool(cfg.get('align_corner_grips', False)):
            from scipy.spatial.transform import Rotation
            turns, errors = zip(*(corner_material_rotation(o, uv[i]) for o, i in zip(offsets, groups)))
            vectors = [Rotation.from_matrix(r).as_rotvec() for r in turns]
            angles = [np.linalg.norm(v) for v in vectors]
            axes = [v/a if a > 1e-9 else np.array([1.,0.,0.]) for v, a in zip(vectors, angles)]
            self.label('corner_orientation_plan', rotation_vectors_deg=np.degrees(vectors).tolist(),
                       material_frame_fit_rms_m=list(errors))
            peel = float(cfg.get('opening_peel_m', 0.))
            coupled_alignment = bool(cfg.get('align_while_opening', False))
            if coupled_alignment:
                opening_offsets = lambda t: [rotate_vectors(o, axis, angle*t) for o, axis, angle in zip(offsets, axes, angles)]
            else:
                self.drive('align_corner_grips_for_unfolding', lambda t: [rotate_vectors(o, axis, angle*t)+c+
                           [peel*np.sin(np.pi*t), 0, 0] for o, c, axis, angle in zip(offsets, suspended, axes, angles)],
                           float(cfg.alignment_seconds), hold=.5)
                offsets = [o@r.T for o, r in zip(offsets, turns)]
        opened = [np.array([np.mean(centers, axis=0)[0], center_xy[1]+.99*uv[indices, 1].mean(), self.table_z+length+.05])
                  for indices in groups]
        self.drive('open_suspended_folded_width', lambda t: [o+c+(goal-c)*t+
                   [peel*np.sin(np.pi*t) if coupled_alignment else 0., 0, 0]
                   for o, c, goal in zip(opening_offsets(t), suspended, opened)],
                   float(cfg.open_seconds), hold=.8)
        if coupled_alignment:
            offsets = [o@r.T for o, r in zip(offsets, turns)]
        raised = [np.array([far_x, c[1], c[2]]) for c in opened]
        self.drive('move_open_sheet_above_landing_edge', lambda t: [o+c+(goal-c)*t for o, c, goal in zip(offsets, opened, raised)],
                   4., hold=.4)
        landing_height = float(cfg.get('landing_grip_height_m', .02))
        lay_rotation = np.radians(float(cfg.get('corner_lay_rotation_deg', 0.)))
        if bool(cfg.get('lay_track_free_edge', False)):
            free_edge = np.flatnonzero(uv[:, 0] >= length/2-.01)
            span = float(cfg.landing_span_fraction)*(uv[free_edge, 0].mean()-
                   np.mean([uv[g['indices'], 0].mean() for g in self.grips]))
            self.label('edge_following_lay_plan', free_edge_particles=free_edge.tolist(),
                       material_span_m=float(span), selection='observed material edge; position feedback only')
            self.drive('lay_open_sheet_on_table', lambda t: edge_following_lay_targets(
                offsets, [c[1] for c in raised], probe_particles(self.task.cloth)[free_edge].mean(axis=0),
                span, raised[0][2], self.table_z+landing_height, t), float(cfg.lay_seconds), hold=.5)
        else:
            self.drive('lay_open_sheet_on_table', lambda t: [rotate_vectors(o, [0., 1., 0.], lay_rotation*t)+np.array([far_x-lay_length*np.sin(t*np.pi/2),
                       goal[1], self.table_z+landing_height+(length+.05-landing_height)*np.cos(t*np.pi/2)]) for o, goal in zip(offsets, raised)],
                       float(cfg.lay_seconds), hold=.5)
        self.release()

    def save(self, success, error, evidence):
        if self.steps[-1] != self.step_count:
            self.capture()
        rest_unchanged = np.array_equal(self.rest, self.task.cloth._edges_len_rest)
        success = bool(success and rest_unchanged and not self.grips)
        np.savez_compressed(self.output/'physical_trace.npz', positions=np.asarray(self.frames),
            steps=self.steps, phases=self.phases, dt=self.dt, hand_centers=np.asarray(self.hand_frames),
            material_uv=self.task.material_uv, faces=self.task.faces, supports=self.task.supports, weights=self.task.weights)
        report = dict(task_id='blanket_flatten', mode='external', success=success, full_robot_task_verified=False,
            error=error, simulated_seconds=self.time, physics_steps=self.step_count, frame_count=len(self.frames),
            fps=int(self.cfg.run.fps), initialization_accepted=self.initialized,
            manipulation_model='two velocity-driven fixed material patches; broad multilayer end bands then local corners',
            selection_model='material-coordinate oracle, no physical finger accessibility validation',
            gravity_unchanged=True, live_particle_position_writes=False, rest_lengths_unchanged=rest_unchanged,
            maximum_simultaneous_grips=self.maximum_grips, active_grasp_particles=[int(i) for g in self.grips for i in g['indices']],
            releases=self.releases, worst=self.worst, final=self.task.measure(), final_evidence=evidence,
            events=self.events, history=self.history, initial_state_restoration=self.restoration,
            binding=self.task.binding_report, birth=self.task.birth_report)
        (self.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        return report


@hydra.main(version_base='1.3', config_path='../../../configs', config_name='blanket_flatten_virtual_hands')
def main(cfg):
    import genesis as gs
    from .scene import BlanketSceneBuilder
    from .initial_state import restore_selected_shape
    output = Path(cfg.run.output).resolve()
    if (output/'config.yaml').exists():
        raise FileExistsError(f'Preserving existing run: {output}')
    output.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(cfg, output/'config.yaml', resolve=True)
    (output/'source_snapshot').mkdir()
    for path in Path(__file__).parent.glob('*.py'):
        shutil.copy2(path, output/'source_snapshot'/path.name)
    cfg.env.cameras = {}
    gs.init(backend=getattr(gs, str(cfg.env.genesis.backend)), precision=str(cfg.env.genesis.precision),
            seed=int(cfg.task.geometry.seed), logging_level='warning')
    task = BlanketSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=output/'assets', include_robot=False)
    restoration = restore_selected_shape(task, cfg.task.initial_state_recording, output)
    execution = VirtualHands(task, cfg, output, restoration)
    previous = signal.signal(signal.SIGINT, lambda *_: setattr(execution, 'stop_requested', True))
    success, error, evidence = False, None, None
    try:
        execution.initialized, _ = execution.settle(2.5)
        if not execution.initialized:
            raise RuntimeError('Selected initial shape failed acceptance')
        execution.unfold()
        execution.label('final_unassisted_settle')
        success, evidence = execution.settle(float(cfg.task.virtual_hands.final_settle_seconds), final=True)
    except (Exception, KeyboardInterrupt) as exc:
        error = str(exc) or 'Interrupted after a completed physics step'
        traceback.print_exc()
    finally:
        signal.signal(signal.SIGINT, previous)
        report = execution.save(success, error, evidence)
        print(f'success={report["success"]} report={output/"report.json"}', flush=True)
    if not report['success']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
