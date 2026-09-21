"""Controlled initial-state construction, followed by unassisted gravity.

The unfolded mesh defines rest lengths and visual material binding once. We
command bounded particle velocities during preparation, allowing the existing
PBD stretch and self-contact solver to wrinkle the sheet. No particle position,
rest length, topology, support index, or pin is changed. These controls are
procedural preparation, not robot actions or an unassisted physical trajectory.
"""
import numpy as np

from topogym.supervision.pbd_probe import probe_particles


class MaterialVelocityProjection:
    """Remove incompatible edge extension from distributed target velocities.

    Solve a damped least-squares velocity constraint on the original material
    graph. Genesis still integrates positions and handles self contact. The
    projection never changes positions, rest lengths, or the mesh topology.
    """
    def __init__(self, edges, rest, count, strength=64., correction_rate=32., material_uv=None, clearance=0.):
        self.edges, self.rest, self.count = edges, rest, count
        self.strength, self.correction_rate = strength, correction_rate
        self.indices = (edges[:, :, None]*3+np.arange(3)).reshape(-1)
        self.indptr = np.arange(len(edges)+1)*6
        self.material_uv, self.clearance = material_uv, clearance

    def project(self, positions, requested):
        from scipy.sparse import csr_matrix
        from scipy.sparse.linalg import LinearOperator, cg
        from scipy.spatial import cKDTree
        e = self.edges
        delta = positions[e[:, 1]]-positions[e[:, 0]]
        lengths = np.linalg.norm(delta, axis=1)
        unit = delta/lengths[:, None]
        error = self.correction_rate*(lengths-self.rest)
        indices, indptr = self.indices, self.indptr
        if self.clearance:
            pairs = cKDTree(positions).query_pairs(self.clearance*1.4, output_type='ndarray')
            remote = np.linalg.norm(self.material_uv[pairs[:, 1]]-self.material_uv[pairs[:, 0]], axis=1) > self.clearance*2.5
            pairs = pairs[remote]
            offsets = positions[pairs[:, 1]]-positions[pairs[:, 0]]
            distance = np.linalg.norm(offsets, axis=1)
            normals = offsets/np.maximum(distance[:, None], 1e-12)
            separation = self.correction_rate*(self.clearance-distance)
            approach = np.sum((requested[pairs[:, 1]]-requested[pairs[:, 0]])*normals, axis=1)
            active = approach < separation
            # Anticipate self contact during construction instead of asking the
            # servo to drive folded layers through each other. This control is
            # removed together with every other preparation control at release.
            e = np.vstack((e, pairs[active]))
            unit = np.vstack((unit, normals[active]*2))
            error = np.r_[error, -separation[active]*2]
            indices = (e[:, :, None]*3+np.arange(3)).reshape(-1)
            indptr = np.arange(len(e)+1)*6
        data = np.concatenate((-unit, unit), axis=1).reshape(-1)
        a = csr_matrix((data, indices, indptr), shape=(len(e), self.count*3))
        at = a.T.tocsr()
        w = self.strength
        operator = LinearOperator((self.count*3, self.count*3), matvec=lambda v: v+w*(at@(a@v)))
        diag = 1+w*np.bincount(indices, weights=data*data, minlength=self.count*3)
        preconditioner = LinearOperator(operator.shape, matvec=lambda v: v/diag)
        rhs = requested.reshape(-1)-w*(at@error)
        result, status = cg(operator, rhs, x0=requested.reshape(-1), M=preconditioner,
                            rtol=1e-4, atol=1e-7, maxiter=100)
        if status < 0 or not np.isfinite(result).all():
            raise RuntimeError('Material velocity projection failed')
        return result.reshape(-1, 3)


def rotate_vectors(vectors, axis, angles):
    axis = np.asarray(axis, dtype=float)
    axis /= np.linalg.norm(axis)
    a = np.asarray(angles)
    c, s = np.cos(a)[..., None], np.sin(a)[..., None]
    return vectors*c+np.cross(axis, vectors)*s+np.outer(vectors@axis, axis)*(1-c)


def fold_target(start, normal_xy, fraction, angle, band):
    """A soft target for a spatial fold of the *current* folded structure."""
    normal = np.r_[normal_xy, 0.].astype(float)
    normal /= np.linalg.norm(normal)
    q = start@normal
    cut = q.min()+fraction*np.ptp(q)
    pivot = normal*cut
    pivot[2] = np.median(start[:, 2])
    axis = np.array([normal[1], -normal[0], 0.])
    weight = np.clip((q-cut)/band, 0., 1.)
    weight = weight*weight*(3-2*weight)
    return rotate_vectors(start-pivot, axis, angle*weight)+pivot


def arc_fold_target(start, normal_xy, fraction, angle, radius, *, shared_tangent=False):
    """Bend nested layers around distinct radii, allowing tangential sliding.

    A horizontal material line follows an arc of its original length. Outside
    that arc the target is a rigid motion; layers nearer the rotation axis use
    a shorter crease band. This is a servo target, not a particle position edit.
    """
    normal = np.r_[normal_xy, 0.].astype(float)
    normal /= np.linalg.norm(normal)
    q = start@normal
    q -= q.min()+fraction*np.ptp(q)
    z = start[:, 2]
    r = z.max()+radius-z
    # A common tangent line keeps nested layers ordered throughout the bend.
    # The older centered-band target is retained solely to reproduce v7/v8.
    half = .5*angle*(r.max() if shared_tangent else r)
    phi = np.clip((q+half)/r, 0., angle)
    tail = np.maximum(q+half-angle*r, 0.)
    folded_q = -half+r*np.sin(phi)+tail*np.cos(angle)
    folded_q = np.where(q < -half, q, folded_q)
    target = start+np.outer(folded_q-q, normal)
    target[:, 2] = z+r*(1-np.cos(phi))+tail*np.sin(angle)
    return target


def twist_target(start, angle, axial_scale, axis=None):
    """Rotate successive whole-bundle cross sections about its long axis."""
    center = start.mean(axis=0)
    local = start-center
    if axis is None:
        axis = np.linalg.eigh(local.T@local)[1][:, -1]
        axis *= 1 if axis[np.argmax(np.abs(axis))] >= 0 else -1
    axial = local@axis
    phase = (axial-(axial.min()+axial.max())/2)/np.ptp(axial)
    target = rotate_vectors(local, axis, phase*angle)
    target += np.outer(axial*(axial_scale-1), axis)
    return target+center, axis


def prepare(execution, cfg):
    task, cloth = execution.task, execution.task.cloth
    saved_gravity = cloth.solver._gravity.to_numpy().copy()
    report = dict(kind='bounded_velocity_controlled_preparation', completed=False,
                  construction=str(cfg.get('construction', 'corner_cross_twist')),
                  sequence=[], position_writes=0, rest_length_writes=0, binding_rebuilt=False,
                  gravity_during_preparation=[0., 0., 0.], pinned_particles=0,
                  velocity_control_steps=0, robot_manipulation=False,
                  target_tracking_tolerance_m=float(cfg.target_rms_tolerance_m),
                  all_controlled_targets_reached=False, unmet_target_stages=[])
    execution.preparation_report = report
    start_time = execution.time
    rest_before = cloth._edges_len_rest.copy()
    projector = MaterialVelocityProjection(task.edges, task.rest_lengths, cloth.n_particles,
        float(cfg.velocity_projection_strength), float(cfg.velocity_correction_rate_s),
        task.material_uv, float(cfg.preparation_layer_clearance_m))
    report['material_velocity_projection'] = dict(strength=projector.strength,
                                                correction_rate_s=projector.correction_rate,
                                                layer_clearance_m=projector.clearance)
    report['minimum_motion_scale'] = 1.
    gain, speed = float(cfg.servo_gain_s), float(cfg.maximum_speed_m_s)
    axial_scale = cfg.gathered.axial_scale if report['construction'] == 'longitudinal_gather' else cfg.twist_axial_scale
    if gain <= 0 or speed <= 0 or not 0 < axial_scale <= 1:
        raise ValueError('Invalid preparation servo or axial scale')

    def servo(target, controlled):
        positions = probe_particles(cloth)
        requested = gain*(target-positions)
        requested[~controlled] = 0.
        stretch = np.max(np.linalg.norm(positions[task.edges[:, 1]]-positions[task.edges[:, 0]], axis=1)/task.rest_lengths)
        scale = float(np.clip((float(cfg.pause_motion_stretch)-stretch)/
                              (float(cfg.pause_motion_stretch)-float(cfg.slow_motion_stretch)), 0., 1.))
        requested *= scale
        report['minimum_motion_scale'] = min(report['minimum_motion_scale'], scale)
        requested *= np.minimum(1., speed/np.maximum(np.linalg.norm(requested, axis=1), 1e-12))[:, None]
        velocities = projector.project(positions, requested)
        velocities *= min(1., speed/max(float(np.linalg.norm(velocities, axis=1).max()), 1e-12))
        cloth.set_particles_vel(velocities)
        report['velocity_control_steps'] += 1
        task.scene.step()

    def drive(name, target_at, seconds, parameters, controlled=None):
        if controlled is None:
            controlled = np.ones(cloth.n_particles, dtype=bool)
        parameters = {**parameters, 'controlled_particles': int(np.count_nonzero(controlled))}
        execution.label('prepare_'+name, **parameters)
        steps = int(np.ceil(seconds/execution.dt))
        for step in range(1, steps+1):
            t = step/steps
            smooth = t*t*(3-2*t)
            target = target_at(smooth)
            servo(target, controlled)
        for step in range(int(np.ceil(float(cfg.maximum_hold_seconds)/execution.dt))):
            servo(target, controlled)
            if (step+1)*execution.dt >= float(cfg.hold_seconds):
                error = np.sqrt(np.mean(np.sum((probe_particles(cloth)[controlled]-target[controlled])**2, axis=1)))
                if error <= float(cfg.target_rms_tolerance_m):
                    break
        execution.label('prepare_material_relaxation', after_stage=name)
        for _ in range(int(np.ceil(float(cfg.between_stage_relax_seconds)/execution.dt))):
            servo(probe_particles(cloth), np.ones(cloth.n_particles, dtype=bool))
        state = probe_particles(cloth)
        item = dict(name=name, seconds=execution.time, parameters=parameters,
                    target_rms_error_m=float(np.sqrt(np.mean(np.sum((state-target)**2, axis=1)))),
                    controlled_rms_error_m=float(np.sqrt(np.mean(np.sum((state[controlled]-target[controlled])**2, axis=1)))),
                    extent_m=np.ptp(state, axis=0).tolist(), metrics=task.measure())
        report['sequence'].append(item)
        if item['controlled_rms_error_m'] > float(cfg.target_rms_tolerance_m):
            report['unmet_target_stages'].append(name)
        np.savez_compressed(execution.output/f'prepared_{name}.npz', positions=state,
                            faces=task.faces, material_uv=task.material_uv)
        execution.label('prepared_'+name, target_rms_error_m=item['target_rms_error_m'])

    try:
        cloth.solver._gravity.from_numpy(np.zeros_like(saved_gravity))
        execution.check_robot_clearance(probe_particles(cloth))
        if report['construction'] == 'longitudinal_gather':
            from .gathered_geometry import gathered_target
            from omegaconf import OmegaConf
            origin = np.r_[np.asarray(execution.cfg.task.origin_xy_m),
                           execution.table_z+task.layout.drop_clearance_m]
            def target(gather, twist):
                return gathered_target(task.material_uv, task.layout.length_m, task.layout.width_m,
                                       gather, twist, cfg.gathered)+origin
            report['gathered_geometry'] = OmegaConf.to_container(cfg.gathered, resolve=True)
            report['target_center_world_m'] = origin.tolist()
            drive('longitudinal_gather', lambda t: target(t, 0.), float(cfg.gather_seconds),
                  dict(crease_count=len(cfg.gathered.panel_fractions)-1,
                       target_geometry='unequal_longitudinal_pleats'))
            drive('whole_bundle_twist', lambda t: target(1., t), float(cfg.twist_seconds),
                  dict(angle_deg=float(cfg.gathered.twist_angle_deg), axis=[1., 0., 0.],
                       axial_scale=float(cfg.gathered.axial_scale), end_fraction=.12,
                       target_geometry='material_coordinate_whole_bundle_torsion'))
        else:
            for fold in cfg.folds:
                state = probe_particles(cloth).copy()
                angle = np.radians(float(fold.angle_deg))
                fraction = float(fold.get('guide_fraction', 0.))
                controlled = None
                if fraction:
                    normal = np.asarray(fold.normal_xy, dtype=float)
                    q = state[:, :2]@normal
                    q = (q-q.min())/np.ptp(q)
                    # Move the far edge, while allowing the opposite end and the
                    # layer interiors to slide. Clamping both ends of a thick stack
                    # imposes incompatible arc lengths during the cross-fold.
                    controlled = q >= 1-fraction
                arc = cfg.get('fold_target', 'soft_rotation') == 'nested_arcs'
                target_function = ((lambda *args: arc_fold_target(*args, shared_tangent=bool(cfg.get('shared_tangent', False))))
                                   if arc else fold_target)
                fold_width = float(cfg.inner_fold_radius_m if arc else cfg.transition_band_m)
                drive(str(fold.name), lambda t: target_function(state, fold.normal_xy, float(fold.fraction),
                    t*angle, fold_width), float(fold.seconds),
                    dict(normal_xy=list(fold.normal_xy), angle_deg=float(fold.angle_deg), fraction=float(fold.fraction),
                         guide_fraction=fraction, target_geometry='nested_arcs' if arc else 'soft_rotation'), controlled)

            state = probe_particles(cloth).copy()
            _, axis = twist_target(state, 0., 1.)
            q = state@axis
            q = (q-q.min())/np.ptp(q)
            cap = float(cfg.twist_end_fraction)
            controlled = (q <= cap) | (q >= 1-cap)
            drive('whole_bundle_twist', lambda t: twist_target(state, t*np.radians(float(cfg.twist_angle_deg)),
                  1+t*(float(cfg.twist_axial_scale)-1), axis)[0], float(cfg.twist_seconds),
                  dict(angle_deg=float(cfg.twist_angle_deg), axis=axis.tolist(), axial_scale=float(cfg.twist_axial_scale),
                       end_fraction=cap), controlled)

        if cfg.get('axial_bunching'):
            bunch = cfg.axial_bunching
            state = probe_particles(cloth).copy()
            q = (task.material_uv[:, 0]+task.layout.length_m/2)/task.layout.length_m
            pivot_fraction = float(bunch.pivot_fraction)
            pivot = np.median(state[np.abs(q-pivot_fraction) < .04, 0])
            scales = np.where(q < pivot_fraction, float(bunch.left_scale), float(bunch.right_scale))
            target = state.copy()
            target[:, 0] = pivot+(state[:, 0]-pivot)*scales
            cap = float(bunch.end_fraction)
            controlled = (q < cap) | (q > 1-cap) | (np.abs(q-pivot_fraction) < .04)
            drive('axial_bunching', lambda t: state+t*(target-state), float(bunch.seconds),
                  dict(pivot_fraction=pivot_fraction, left_scale=float(bunch.left_scale),
                       right_scale=float(bunch.right_scale), end_fraction=cap,
                       target_geometry='asymmetric_end_and_middle_guided_axial_compression'), controlled)

        state = probe_particles(cloth).copy()
        shift = np.r_[np.asarray(execution.cfg.task.origin_xy_m)-state[:, :2].mean(axis=0),
                      execution.table_z+float(cfg.release_clearance_m)-state[:, 2].min()]
        drive('lower_for_release', lambda t: state+t*shift, float(cfg.lowering_seconds),
              dict(release_clearance_m=float(cfg.release_clearance_m)))
        # Remove all distributed control before judging the gravity trajectory.
        execution.label('prepare_free_relaxation')
        cloth.set_particles_vel(0.)
        execution.wait(float(cfg.relax_seconds))
        np.savez_compressed(execution.output/'prepared_release.npz', positions=probe_particles(cloth),
                            faces=task.faces, material_uv=task.material_uv)
        report['release_state'] = task.measure()
        report['release_seconds'] = execution.time
        report['release_step'] = execution.step_count
        report['elapsed_seconds'] = execution.time-start_time
        report['rest_lengths_unchanged'] = bool(np.array_equal(rest_before, cloth._edges_len_rest))
        report['completed'] = True
        report['all_controlled_targets_reached'] = not report['unmet_target_stages']
        execution.label('prepared_release', metrics=report['release_state'])
    finally:
        cloth.solver._gravity.from_numpy(saved_gravity)
        report['restored_gravity'] = saved_gravity.tolist()
