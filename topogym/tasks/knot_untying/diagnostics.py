"""Read-only substep FEM diagnostics and independent swept-surface checks.

ipctk and pyuipc register conflicting pybind enums, so the CCD checker runs
in a spawned CPU process. It observes surfaces; it never edits simulation state.
"""
from collections import deque
from dataclasses import asdict, dataclass
import multiprocessing as mp
import time

import numpy as np


@dataclass(frozen=True)
class StabilityLimits:
    min_volume_ratio: float = .2
    table_penetration_m: float = .00005
    settled_rms_speed_m_s: float = .001
    settled_max_speed_m_s: float = .005
    settled_drift_m: float = .002
    rest_length_relative_change: float = .02
    loaded_length_relative_change: float = .05
    local_axial_strain: float = .20
    settling_window_s: float = 2.
    comparison_rms_m: float = .002
    comparison_max_m: float = .005


LIMITS = StabilityLimits()


def signed_tet_volumes(vertices, elements):
    q = vertices[elements]
    return np.einsum('ij,ij->i', q[:, 1]-q[:, 0],
                     np.cross(q[:, 2]-q[:, 0], q[:, 3]-q[:, 0]))/6


def _ccd_worker(connection, vertices, faces, primary_vertices=None, cross_only=False):
    try:
        import ipctk
        ipctk.set_num_threads(2)
        vertices = np.asfortranarray(vertices, dtype=np.float64)
        faces = np.asfortranarray(faces, dtype=np.int32)
        edges = np.unique(np.sort(np.vstack((faces[:, :2], faces[:, 1:], faces[:, [2, 0]])), axis=1), axis=0)
        mesh = ipctk.CollisionMesh(vertices, np.asfortranarray(edges, dtype=np.int32), faces)
        if primary_vertices is not None:
            # A rigid/FEM audit checks all FEM interactions. Fixed compounds
            # can overlap internally; rigid/rigid pairs belong to their solver.
            primary = np.asarray(primary_vertices, dtype=bool)
            count = int(primary.sum())
            if not np.array_equal(primary, np.arange(len(primary)) < count):
                raise ValueError('Place all FEM vertices before the rigid vertices')
            mesh.can_collide = (ipctk.make_vertex_patches_filter(np.where(primary, 0, 1).astype(np.int32))
                                if cross_only else ipctk.make_static_obstacle_filter(count))
        broad = None  # Toolkit's compiled default broad phase.
        connection.send(dict(initial_intersections=bool(ipctk.has_intersections(mesh, vertices, broad))))
        while True:
            current = connection.recv()
            if current is None:
                break
            if isinstance(current, dict) and current.get('query') == 'minimum_distance':
                points = np.asfortranarray(current['vertices'], dtype=np.float64)
                candidates = ipctk.NormalCollisions()
                candidates.build(mesh, points, float(current['radius']))
                # ipctk 1.6.0 returns squared distance despite the method name.
                distance = (None if candidates.empty() else
                            float(np.sqrt(max(0., candidates.compute_minimum_distance(mesh, points)))))
                connection.send(dict(minimum_distance_m=distance))
                continue
            if isinstance(current, dict):
                vertices = np.asfortranarray(current['previous'], dtype=np.float64)
                current = current['current']
            current = np.asfortranarray(current, dtype=np.float64)
            collision_free = ipctk.is_step_collision_free(mesh, vertices, current, broad_phase=broad)
            connection.send(dict(collision_free=bool(collision_free)))
            vertices = current
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as exc:
        connection.send(dict(error=f'{type(exc).__name__}: {exc}'))
    finally:
        connection.close()


class SurfaceCCD:
    def __init__(self, vertices, faces, *, primary_vertices=None, cross_only=False):
        self.surface_indices, inverse = np.unique(faces, return_inverse=True)
        local_faces = inverse.reshape(-1, 3)
        context = mp.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_ccd_worker,
            args=(child, vertices[self.surface_indices], local_faces,
                  None if primary_vertices is None else np.asarray(primary_vertices)[self.surface_indices], cross_only), daemon=True)
        self.process.start()
        child.close()
        result = self._receive()
        self.initial_intersections = result['initial_intersections']
        self.checks = 0
        self.failures = 0

    def _receive(self):
        if not self.connection.poll(60):
            raise RuntimeError('Independent CCD worker timed out')
        result = self.connection.recv()
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    def step(self, vertices):
        self.connection.send(vertices[self.surface_indices])
        result = self._receive()
        self.checks += 1
        self.failures += int(not result['collision_free'])
        return result['collision_free']

    def step_between(self, previous, current):
        """Check an explicit observed interval after broad-phase-only intervals."""
        self.connection.send(dict(previous=previous[self.surface_indices], current=current[self.surface_indices]))
        result = self._receive()
        self.checks += 1
        self.failures += int(not result['collision_free'])
        return result['collision_free']

    def minimum_distance(self, vertices, radius):
        """Complete mesh-feature distance, or None when outside the query radius."""
        self.connection.send(dict(query='minimum_distance', vertices=vertices[self.surface_indices], radius=radius))
        return self._receive()['minimum_distance_m']

    def close(self):
        if self.process.is_alive():
            self.connection.send(None)
            self.process.join(5)
        if self.process.is_alive():
            self.process.terminate()
        self.connection.close()


class FemDiagnostics:
    """Sample native libuipc velocities, not Genesis' stale FEM velocity buffer."""
    def __init__(self, task, *, sample_interval_s=.02, loaded=False, audit_rigid=False):
        import uipc
        import torch
        from scipy.spatial import cKDTree
        from topogym.world.genesis_ipc_vertex_constraints import _straighten_positions
        from topogym.world.rope import make_elastic_tube_mesh, tensor_to_numpy

        self.task, self.loaded = task, loaded
        self.coupler = task.scene.sim.coupler
        self.feature = self.coupler._ipc_world.features().find(uipc.core.FiniteElementStateAccessorFeature)
        # pyuipc 0.0.25's create_geometry/copy_to does not populate vertex
        # attributes. Its explicit CUDA-buffer accessors do expose the state.
        parts = getattr(task, 'diagnostic_parts', [(task.rope, task.centerline)])
        self.vertex_count = sum(rope.n_vertices for rope, _ in parts)
        if self.feature.vertex_count() != self.vertex_count:
            raise ValueError('Diagnostics must cover every native FEM entity in insertion order')
        self.native_buffers = [torch.empty((self.vertex_count, 3), dtype=torch.float64,
                                          device='cuda') for _ in range(2)]
        self.native_views = [uipc.backend.BufferView(buffer.data_ptr(), 0, self.vertex_count,
                                                    24, 24, 'cuda') for buffer in self.native_buffers]
        positions, elements, faces, rest_parts, rings, edges = [], [], [], [], [], []
        vertex_offset = ring_offset = 0
        self.material_slices = []
        for rope, centerline in parts:
            initial = np.asarray(tensor_to_numpy(rope.init_positions), dtype=float)
            positions.append(initial)
            elements.append(np.asarray(rope.elems)+vertex_offset)
            faces.append(np.asarray(rope.surface_triangles)+vertex_offset)
            rest_parts.append(_straighten_positions(initial, centerline))
            skin, _ = make_elastic_tube_mesh(centerline, radius=task.layout.rope_radius_m,
                                           radial_segments=task.layout.radial_segments)
            distances, indices = cKDTree(initial).query(skin[:-2])
            if distances.max() > 1e-6:
                raise ValueError('FEM boundary does not preserve the material sampling rings')
            rings.append(indices.reshape(-1, task.layout.radial_segments)+vertex_offset)
            edges.extend((i, i+1) for i in range(ring_offset, ring_offset+len(centerline)-1))
            self.material_slices.append((ring_offset, ring_offset+len(centerline)))
            ring_offset += len(centerline)
            vertex_offset += len(initial)
        self.initial = np.vstack(positions)
        self.elements, self.faces = np.vstack(elements), np.vstack(faces)
        rest = np.vstack(rest_parts)
        self.rest_volumes = signed_tet_volumes(rest, self.elements)
        self.mass = np.zeros(len(rest))
        rho = float(task.rope.material.rho)
        np.add.at(self.mass, self.elements.ravel(), np.repeat(abs(self.rest_volumes)*rho/4, 4))
        self.rings = np.vstack(rings)
        self.material_edges = np.asarray(edges)
        centerlines = np.vstack([centerline for _, centerline in parts])
        self.initial_lengths = np.linalg.norm(centerlines[self.material_edges[:, 1]]-
                                             centerlines[self.material_edges[:, 0]], axis=1)
        self.floor = task.tabletop.frames.table_surface_origin[2]
        self.dt = float(task.scene.sim._substep_dt)
        self.interval = max(1, round(sample_interval_s/self.dt))
        if audit_rigid:
            from .rigid_diagnostics import NativeRigidSurfaceCCD
            self.ccd = NativeRigidSurfaceCCD(task, self.initial, self.faces)
        else:
            self.ccd = SurfaceCCD(self.initial, self.faces)
        self.count = 0
        self.samples, self.centers = [], []
        self.window = deque()
        self.maxima = dict(max_speed_m_s=0., max_table_penetration_m=0.,
                           max_total_length_relative_change=0., max_local_axial_strain=0.,
                           max_vertex_displacement_m=0., max_kinetic_energy_j=0.)
        initial_J = signed_tet_volumes(self.initial, self.elements)/self.rest_volumes
        self.min_J = float(initial_J.min())
        self.last_J_quantiles = np.quantile(initial_J, [0., .01, .5, .99, 1.]).tolist()
        self.failures = []
        self.elapsed_diagnostics_s = 0.
        self._original_couple = None

    def native_state(self):
        import torch
        self.feature.copy_position_to(self.native_views[0], 0, self.vertex_count)
        self.feature.copy_velocity_to(self.native_views[1], 0, self.vertex_count)
        torch.cuda.synchronize()
        return tuple(buffer.cpu().numpy().copy() for buffer in self.native_buffers)

    def install(self):
        if self.ccd.initial_intersections:
            self.failures.append(dict(time_s=0., reason='initial_surface_intersection'))
            raise ValueError('Initial FEM surfaces intersect; refusing simulation')
        self._original_couple = self.coupler.couple

        def observed(f):
            self._original_couple(f)
            self.observe()

        self.coupler.couple = observed

    def observe(self):
        start = time.perf_counter()
        positions, velocity = self.native_state()
        # Preserve the rejected state too, so a failure can be inspected.
        self.last_positions, self.last_velocity = positions, velocity
        self.count += 1
        t = self.count*self.dt
        if not np.isfinite(positions).all() or not np.isfinite(velocity).all():
            self.failures.append(dict(time_s=t, reason='nonfinite_state'))
            raise RuntimeError('Nonfinite FEM state')
        J = signed_tet_volumes(positions, self.elements)/self.rest_volumes
        self.last_J_quantiles = np.quantile(J, [0., .01, .5, .99, 1.]).tolist()
        minimum = float(J.min())
        self.min_J = min(self.min_J, minimum)
        if minimum <= 0:
            self.failures.append(dict(time_s=t, reason='inverted_tetrahedron'))
            raise RuntimeError('Inverted FEM tetrahedron')
        ccd_free = self.ccd.step(positions)
        if not ccd_free:
            self.failures.append(dict(time_s=t, reason='swept_surface_intersection'))
            raise RuntimeError('Independent surface CCD rejected the substep')
        speed = np.linalg.norm(velocity, axis=1)
        centers = positions[self.rings].mean(axis=1)
        lengths = np.linalg.norm(centers[self.material_edges[:, 1]]-
                                 centers[self.material_edges[:, 0]], axis=1)
        metrics = dict(time_s=t, min_J=minimum, rms_speed_m_s=float(np.sqrt(np.mean(speed**2))),
            max_speed_m_s=float(speed.max()), max_table_penetration_m=max(0., float(self.floor-positions[:, 2].min())),
            max_total_length_relative_change=abs(float(lengths.sum()/self.initial_lengths.sum()-1)),
            max_local_axial_strain=float(np.abs(lengths/self.initial_lengths-1).max()),
            max_vertex_displacement_m=float(np.linalg.norm(positions-self.initial, axis=1).max()),
            max_kinetic_energy_j=float(.5*np.sum(self.mass*speed**2)))
        for key in self.maxima:
            self.maxima[key] = max(self.maxima[key], metrics[key])
        if metrics['max_table_penetration_m'] > LIMITS.table_penetration_m:
            self.failures.append(dict(time_s=t, reason='table_penetration'))
            raise RuntimeError('Rope penetrated table')
        self.window.append((t, positions, metrics))
        while len(self.window) > 1 and self.window[1][0] <= t-LIMITS.settling_window_s:
            self.window.popleft()
        if self.count % self.interval == 0 or self.count == 1:
            self.samples.append(metrics)
            self.centers.append(centers.astype(np.float32))
        self.last_centers = centers
        self.elapsed_diagnostics_s += time.perf_counter()-start

    def report(self):
        window = list(self.window)
        final = window[-1][1] if window else self.initial
        drift = float(max((np.linalg.norm(p-window[0][1], axis=1).max() for _, p, _ in window), default=0.))
        window_rms = max((m['rms_speed_m_s'] for _, _, m in window), default=0.)
        window_max = max((m['max_speed_m_s'] for _, _, m in window), default=0.)
        limit = LIMITS.loaded_length_relative_change if self.loaded else LIMITS.rest_length_relative_change
        checks = dict(finite_no_inversion=not any(f['reason'] in ('nonfinite_state', 'inverted_tetrahedron')
                                                for f in self.failures), nondegenerate=self.min_J > LIMITS.min_volume_ratio,
            initial_surface_intersection_free=not self.ccd.initial_intersections,
            every_substep_surface_ccd=self.ccd.checks == self.count and self.ccd.failures == 0,
            table_clearance=self.maxima['max_table_penetration_m'] <= LIMITS.table_penetration_m,
            total_length=self.maxima['max_total_length_relative_change'] < limit,
            local_axial_strain=self.maxima['max_local_axial_strain'] < LIMITS.local_axial_strain,
            settling_window_complete=bool(window and window[-1][0]-window[0][0] >= LIMITS.settling_window_s-self.dt*1.01),
            settled_rms_speed=window_rms < LIMITS.settled_rms_speed_m_s,
            settled_max_speed=window_max < LIMITS.settled_max_speed_m_s,
            settled_drift=drift < LIMITS.settled_drift_m)
        return dict(checks=checks, mechanical_checks_passed=all(checks.values()),
            limits=asdict(LIMITS), substeps_observed=self.count, simulated_seconds=self.count*self.dt,
            min_J=self.min_J, extrema=dict(self.maxima), tail_window_rms_speed_m_s=window_rms,
            final_J_quantiles=dict(zip(('min', 'p01', 'median', 'p99', 'max'),
                                      getattr(self, 'last_J_quantiles', []))),
            tail_window_max_speed_m_s=window_max, tail_window_drift_m=drift,
            diagnostics_wall_seconds=self.elapsed_diagnostics_s, failures=[dict(f) for f in self.failures],
            ccd_method=getattr(self.ccd, 'method', 'ipctk 1.6.0; actual FEM surface; linear sweep at every IPC substep'),
            rigid_ccd_queries=getattr(self.ccd, 'rigid_queries', None),
            rigid_pairs_rejected_by_swept_aabb=getattr(self.ccd, 'separated_pairs', None),
            velocity_source='libuipc FiniteElementStateAccessorFeature',
            final_nodes_count=len(final), force_measurements_available=False,
            energy_scope='native kinetic energy only; no claim of full elastic-energy audit')

    def close(self):
        if self._original_couple is not None:
            self.coupler.couple = self._original_couple
        self.ccd.close()
