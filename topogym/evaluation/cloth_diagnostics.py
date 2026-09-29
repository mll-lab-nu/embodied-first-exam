"""Particle diagnostics in original material order, without engine mutation.

Panel IDs are material-region labels, not current stack layers. Nearby material
patches are contact candidates, not measured contacts or forces.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


class ClothParticleDiagnostics:
    def __init__(self, material_uv, *, width, panel_fractions, crease_band,
                 particle_size, table_z, table_bounds, particle_start=0,
                 speed_limit=.03, edges=None, rest_lengths=None,
                 support_indices=None, support_weights=None, visual_uv=None):
        self.uv = np.array(material_uv, dtype=float, copy=True)
        fractions = np.asarray(panel_fractions, dtype=float)
        if (self.uv.ndim != 2 or self.uv.shape[1] != 2 or not len(self.uv)
                or not np.isfinite(self.uv).all() or fractions.ndim != 1
                or len(fractions) < 2 or not np.isfinite(fractions).all()
                or np.any(fractions <= 0) or not np.isclose(fractions.sum(), 1)):
            raise ValueError("Invalid material coordinates or panel fractions")
        if not np.isfinite([width, crease_band, particle_size, table_z, speed_limit]).all() or min(width, crease_band, particle_size, speed_limit) <= 0:
            raise ValueError("Invalid diagnostic dimensions or thresholds")
        self.creases = width*(np.cumsum(fractions)[:-1]-.5)
        self.panels = np.searchsorted(self.creases, self.uv[:, 1], side="right")
        self.crease_distance = abs(self.uv[:, 1, None]-self.creases).min(axis=1)
        self.crease_band = crease_band
        self.panel_count = len(fractions)
        self.particle_size, self.table_z = particle_size, table_z
        self.bounds = np.asarray(table_bounds, dtype=float)
        if self.bounds.shape != (2, 2) or not np.isfinite(self.bounds).all() or np.any(self.bounds[0] >= self.bounds[1]):
            raise ValueError("Invalid table bounds")
        if particle_start is not None and (type(particle_start) is not int or particle_start < 0):
            raise ValueError("Invalid original particle offset")
        self.particle_start, self.speed_limit = particle_start, speed_limit
        self.edges = None if edges is None else np.array(edges, dtype=int, copy=True)
        self.rest = None if rest_lengths is None else np.array(rest_lengths, dtype=float, copy=True)
        if self.edges is not None and (self.edges.ndim != 2 or self.edges.shape[1] != 2
                or self.rest is None or self.rest.shape != (len(self.edges),)
                or not np.isfinite(self.rest).all() or np.any(self.rest <= 0)
                or np.any(self.edges < 0) or np.any(self.edges >= len(self.uv))):
            raise ValueError("Invalid actual constraint edges/rest lengths")
        self.supports = None if support_indices is None else np.array(support_indices, copy=True)
        self.weights = None if support_weights is None else np.array(support_weights, copy=True)
        self.visual_uv = None if visual_uv is None else np.array(visual_uv, copy=True)
        if self.supports is not None:
            self._binding_check(self.supports, self.weights)
        self.previous_v = self.previous_time = self.previous_tick = None
        self.peak_speed = np.zeros(len(self.uv))
        self.released_exceedances = np.zeros(len(self.uv), dtype=np.int64)
        self.samples = self.released_samples = 0
        self.first_released_exceedance = None

    def _binding_check(self, indices, weights):
        if (indices.ndim != 2 or not indices.shape[0] or not indices.shape[1] or indices.dtype.kind not in "iu"
                or weights is None or weights.shape != indices.shape
                or np.any(indices < 0) or np.any(indices >= len(self.uv))
                or not np.isfinite(weights).all()
                or self.visual_uv is None or self.visual_uv.shape != (len(indices), 2)
                or not np.isfinite(self.visual_uv).all()):
            raise ValueError("Invalid visual supports/weights/material coordinates")

    def binding_report(self, current=None):
        if self.supports is None:
            return dict(available=False, reason="Actual support table was not recorded")
        indices, weights = (self.supports, self.weights) if current is None else current
        indices, weights = np.asarray(indices), np.asarray(weights)
        self._binding_check(indices, weights)
        if indices.shape != self.supports.shape:
            raise ValueError("Visual binding layout changed")
        distance = np.linalg.norm(self.uv[indices]-self.visual_uv[:, None, :], axis=2)
        changed = np.any(indices != self.supports, axis=1) | np.any(weights != self.weights, axis=1)
        nonlocal_supports = distance > 4*self.particle_size
        return dict(available=True, current_observed=current is not None,
            changed_visual_vertices=int(changed.sum()), changed_visual_ids=np.flatnonzero(changed)[:20].tolist(),
            nonlocal_support_count=int(nonlocal_supports.sum()),
            nonlocal_visual_ids=np.flatnonzero(nonlocal_supports.any(axis=1))[:20].tolist(),
            maximum_material_distance_m=float(distance.max()),
            maximum_weight_sum_error=float(abs(weights.sum(axis=1)-1).max()))

    def sample(self, tick, time_s, stage, positions, velocities, *, current_binding=None, free=None):
        p, v = np.asarray(positions), np.asarray(velocities)
        if p.shape != (len(self.uv), 3) or v.shape != p.shape or not np.isfinite(p).all() or not np.isfinite(v).all():
            raise ValueError("Invalid particle sample in original entity order")
        if not np.isfinite(time_s) or (self.previous_time is not None and (time_s <= self.previous_time or tick <= self.previous_tick)):
            raise ValueError("Diagnostic samples must advance monotonically")
        if free is not None and np.asarray(free).shape != (len(p),):
            raise ValueError("Free flags must use original entity order")
        speed = np.linalg.norm(v, axis=1)
        hot = np.argsort(-speed, kind="stable")[:10]
        near_table = ((abs(p[:, 2]-(self.table_z+self.particle_size/2)) <= .001)
            & np.all((p[:, :2] >= self.bounds[0]) & (p[:, :2] <= self.bounds[1]), axis=1))
        pairs = cKDTree(p).query_pairs(1.05*self.particle_size, output_type="ndarray")
        if len(pairs):
            pairs = pairs[np.linalg.norm(self.uv[pairs[:, 0]]-self.uv[pairs[:, 1]], axis=1) > 2.5*self.particle_size]
        distances = np.linalg.norm(p[pairs[:, 0]]-p[pairs[:, 1]], axis=1) if len(pairs) else np.empty(0)
        stretch = None if self.edges is None else np.linalg.norm(p[self.edges[:, 1]]-p[self.edges[:, 0]], axis=1)/self.rest
        dv = None if self.previous_v is None else v-self.previous_v
        hotspot = []
        for i in hot:
            local_pairs = np.flatnonzero(np.any(pairs == i, axis=1))
            closest = None
            if len(local_pairs):
                at = local_pairs[np.argmin(distances[local_pairs])]
                j = int(pairs[at, 1] if pairs[at, 0] == i else pairs[at, 0])
                closest = dict(particle_id=j, panel_id=int(self.panels[j]), distance_m=float(distances[at]))
            incident = None if self.edges is None else stretch[np.any(self.edges == i, axis=1)]
            visuals = np.empty(0, dtype=int) if self.supports is None else np.flatnonzero(np.any(self.supports == i, axis=1))
            hotspot.append(dict(particle_id=int(i), solver_particle_id=None if self.particle_start is None else int(i+self.particle_start),
                panel_id=int(self.panels[i]), material_uv_m=self.uv[i].tolist(), position_m=p[i].tolist(),
                velocity_m_s=v[i].tolist(), speed_m_s=float(speed[i]), height_above_table_m=float(p[i, 2]-self.table_z),
                crease_distance_m=float(self.crease_distance[i]), near_table=bool(near_table[i]),
                free=None if free is None else bool(free[i]),
                delta_velocity_m_s=None if dv is None else dv[i].tolist(),
                nearest_nonlocal_contact_candidate=closest,
                maximum_incident_edge_ratio=None if incident is None or not len(incident) else float(incident.max()),
                birth_visual_support_count=None if self.supports is None else len(visuals),
                birth_visual_ids=visuals[:20].tolist()))
        by_panel = []
        for panel in range(self.panel_count):
            selected = self.panels == panel
            values = speed[selected]
            by_panel.append(dict(panel_id=panel, particles=int(selected.sum()),
                mean_speed_m_s=float(values.mean()) if len(values) else None,
                maximum_speed_m_s=float(values.max()) if len(values) else None,
                above_speed_limit=int(np.sum(values > self.speed_limit))))
        binding = self.binding_report(current_binding)
        self.samples += 1
        self.peak_speed = np.maximum(self.peak_speed, speed)
        if stage == "released_settle":
            self.released_samples += 1
            self.released_exceedances += speed > self.speed_limit
            if self.first_released_exceedance is None and speed.max() > self.speed_limit:
                self.first_released_exceedance = dict(physics_step=int(tick), sim_time_s=float(time_s), hotspot=hotspot[0])
        self.previous_v, self.previous_time, self.previous_tick = v.copy(), float(time_s), int(tick)
        return dict(physics_step=int(tick), sim_time_s=float(time_s), stage=stage,
            maximum_speed_m_s=float(speed.max()), p99_speed_m_s=float(np.quantile(speed, .99)),
            mean_speed_m_s=float(speed.mean()), above_speed_limit=int(np.sum(speed > self.speed_limit)),
            near_table_particles=int(near_table.sum()), nonlocal_contact_candidate_pairs=len(pairs),
            fixed_particles=None if free is None else int(np.sum(~np.asarray(free, dtype=bool))),
            maximum_edge_ratio=None if stretch is None else float(stretch.max()),
            binding=binding, panels=by_panel, hotspots=hotspot)

    def summary(self):
        order = np.argsort(-self.released_exceedances, kind="stable")[:20]
        return dict(samples=self.samples, released_samples=self.released_samples,
            first_released_speed_exceedance=self.first_released_exceedance,
            first_exceedance_scope="First in the observed samples; a partial historical window can start after the original failure",
            recurrent_hotspots=[dict(particle_id=int(i), panel_id=int(self.panels[i]),
                material_uv_m=self.uv[i].tolist(), released_exceedance_samples=int(self.released_exceedances[i]),
                maximum_observed_speed_m_s=float(self.peak_speed[i])) for i in order if self.released_exceedances[i] > 0],
            coverage=dict(original_particle_order=True, substep_internal_corrections=False,
                rigid_contact_forces=False, exact_self_contact_pairs=False,
                binding_available=self.supports is not None),
            interpretation="Contact candidates are geometric proximity, and delta velocity is not a force attribution.")
