"""Shared material-region admission/state for FEM and PBD grasp adapters.

Only array/geometry selection is shared; each backend owns its real constraints.
Local offsets and material selection extracted from the historical Knot/Blanket
helpers listed in soft_grasp_assist_engineering_plan_20260927_zh.md.
"""
from copy import deepcopy
import hashlib
import numpy as np
from scipy.spatial import cKDTree, ConvexHull
from topogym.robot.grasp_geometry import read_grasp_geometry
from topogym.utils.arrays import to_numpy
from topogym.utils.grasp import (closed_fraction, rotation, material_patch,
                                material_components, surface_distances, exposed_patch)


class SoftGraspBackend:
    def __init__(self, world, robot, config):
        self.world, self.robot, self.config = world, robot, config
        self.hands = {n: robot.entity.get_link(g.hand_link) for n, g in robot.groups.items()}
        self.specs = {s.entity: s for s in config.targets}
        self.entities = {n: world.entities[n] for n in self.specs}
        self.regions, self.active, self.last_candidates = {}, {}, {}
        self.material, self.identities, self.edges, self.rest_lengths = {}, {}, {}, {}
        self._last_health = {}
        self._admission = {}

    def initialize_material(self, name, coordinates, rest_positions, edges=None):
        uv = np.asarray(coordinates, dtype=float)
        self.material[name] = uv
        self.identities[name] = hashlib.sha256(uv.tobytes()).hexdigest()
        spec = self.specs[name]
        if spec.material_min_m and len(spec.material_min_m) != uv.shape[1]:
            raise ValueError("Grasp material bounds dimension mismatch")
        if edges is None:
            tree = cKDTree(uv)
            distance, neighbors = tree.query(uv, k=min(5, len(uv)))
            spacing = np.median(distance[:, 1])
            edges = sorted(tree.query_pairs(1.6*spacing))
        edges = np.asarray(edges, dtype=int).reshape(-1, 2)
        lengths = np.linalg.norm(np.asarray(rest_positions)[edges[:, 1]]-np.asarray(rest_positions)[edges[:, 0]], axis=1)
        valid = lengths > 1e-10
        self.edges[name], self.rest_lengths[name] = edges[valid], lengths[valid]

    def fraction(self, hand):
        group = self.robot.groups[hand]
        return closed_fraction(self.robot.capture_state().targets[hand][group.gripper_field],
                               group.grasp.open_position, group.grasp.closed_position)

    def finger_fractions(self, hand):
        group = self.robot.groups[hand]
        q = to_numpy(self.robot.entity.get_qpos()).reshape(-1)
        return [closed_fraction(q[self.robot.entity.get_joint(n).qs_idx_local[0]],
                                group.grasp.open_position, group.grasp.closed_position) for n in group.finger_joints]

    def allowed(self, name):
        uv, spec = self.material[name], self.specs[name]
        mask = np.ones(len(uv), dtype=bool)
        if spec.material_min_m:
            mask &= np.all((uv >= spec.material_min_m) & (uv <= spec.material_max_m), axis=1)
        return mask

    def candidate_mask(self, name):
        return self.allowed(name)

    def candidates(self, hand):
        geometry = read_grasp_geometry(self.robot, hand)
        group = self.robot.groups[hand]
        tcp = geometry['position'] + rotation(geometry['quaternion']).apply(group.tcp_position_in_hand_m)
        results = []
        for name, spec in self.specs.items():
            x, uv = self.positions(name), self.material[name]
            near = self.candidate_mask(name) & (np.linalg.norm(x-tcp, axis=1) <= self.config.max_tcp_distance_m)
            indices = np.flatnonzero(near)
            strain = self.strain_ratio(name, x)
            self._admission[hand] = dict(entity=name, nearby_vertices=len(indices), qualified_region_centers=0,
                                         max_material_edge_ratio=strain, occluded_region_centers=0,
                                         obstacle_rejected_region_centers=0,
                                         require_exposed_patch=spec.require_exposed_patch)
            # A transient squeeze must settle before registering a constraint;
            # do not acquire an already unhealthy shape and lose it next tick.
            if not np.isfinite(x).all() or strain > spec.max_strain_ratio:
                self._admission[hand]['rejection'] = 'material_strain_or_nonfinite'
                continue
            if not len(indices):
                continue
            # Bilateral evidence belongs to one local material region. The
            # two fingers normally touch different vertices on that region.
            # Requiring a single vertex to be close to both incorrectly rejects
            # valid cloth patches and thicker rope cross-sections.
            nearby = np.flatnonzero(np.linalg.norm(x-tcp, axis=1) <=
                                    self.config.max_tcp_distance_m+spec.spatial_radius_m)
            distances = np.full((2, len(x)), np.inf)
            inside_finger = np.zeros(len(x), dtype=bool)
            for side, (vertices, faces) in enumerate(geometry['surfaces']):
                distances[side, nearby] = surface_distances(x[nearby], vertices, faces)
                hull = ConvexHull(vertices)
                signed = (x[nearby] @ hull.equations[:, :3].T + hull.equations[:, 3]).max(axis=1)
                inside_finger[nearby] |= signed < -self.config.max_penetration_m
            contact = (distances <= spec.contact_distance_m) & self.candidate_mask(name)[None, :]
            self._admission[hand]['minimum_finger_distances_m'] = distances.min(axis=1).tolist()
            patches = {}
            for center in indices:
                center = int(center)
                patch = material_patch(x, uv, center, spatial_radius_m=spec.spatial_radius_m,
                                       material_radius_m=spec.material_radius_m)
                if (not len(patch) or not np.all(self.allowed(name)[patch]) or inside_finger[patch].any()
                        or not np.all(contact[:, patch].any(axis=1))):
                    continue
                patches[center] = patch
            self._admission[hand]['qualified_region_centers'] = len(patches)
            for component in material_components(list(patches), uv, spec.material_radius_m):
                previous = self.last_candidates.get((hand, name))
                ordered = sorted(map(int, component), key=lambda i: (i != previous, np.linalg.norm(x[i]-tcp), i))
                for center in ordered:
                    patch = patches[center]
                    if (spec.require_exposed_patch and not exposed_patch(x, uv, patch, radius=spec.spatial_radius_m,
                                                                          clearance=spec.contact_distance_m)):
                        self._admission[hand]['occluded_region_centers'] += 1
                        continue
                    if self.penetration_reason(name, patch):
                        self._admission[hand]['obstacle_rejected_region_centers'] += 1
                        continue
                    key = (name, center)
                    # Never mutate an owned region while considering another hand.
                    if key not in self.active:
                        self.regions[key] = dict(indices=patch.tolist(), evidence=dict(
                            source=self.evidence_source, physics_step=self.world.physics_step,
                            finger_surface_gaps_m=distances[:, patch].min(axis=1).tolist()))
                    self.last_candidates[hand, name] = center
                    results.append(key)
                    break
        return sorted(results)

    def conflicts(self, first, second):
        first, second = tuple(first), tuple(second)
        if first[0] != second[0]:
            return False
        a, b = self.regions[first]['indices'], self.regions[second]['indices']
        return bool(np.intersect1d(a, b).size)

    def acquire(self, hand, target):
        key = tuple(target)
        if key in self.active:
            raise RuntimeError("Material region already held")
        x = self.positions(key[0])[self.regions[key]['indices']]
        parent = self.hands[hand]
        pos, quat = to_numpy(parent.get_pos()).reshape(3), to_numpy(parent.get_quat()).reshape(4)
        binding = dict(hand=hand, target=key, indices=list(self.regions[key]['indices']),
                       material_identity=self.identities[key[0]],
                       local_offsets=rotation(quat).inv().apply(x-pos).tolist(),
                       finger_fractions=self.finger_fractions(hand),
                       acquisition_evidence=deepcopy(self.regions[key]['evidence']))
        self.attach_native(binding)
        self.active[key] = deepcopy(binding)
        if not self.exists(binding):
            raise RuntimeError("Native soft grasp creation failed")
        return binding

    def targets(self, binding):
        parent = self.hands[binding['hand']]
        return to_numpy(parent.get_pos()).reshape(3) + rotation(to_numpy(parent.get_quat()).reshape(4)).apply(binding['local_offsets'])

    def release(self, binding):
        self.detach_native(binding)
        self.active.pop(tuple(binding['target']))

    def penetration_reason(self, name, indices):
        """Guard actual convex rigid obstacles; this is not a contact solver."""
        x = self.positions(name)[indices]
        for entity_name, entity in self.world.entities.items():
            if entity_name == 'robot' or not hasattr(entity, 'links'):
                continue
            for link in entity.links:
                for geom in link.geoms:
                    if not geom.is_convex:
                        continue
                    v = to_numpy(geom.get_verts()).reshape(-1, 3)
                    if len(v) < 4 or np.linalg.matrix_rank(v-v.mean(axis=0)) < 3:
                        continue
                    if np.any(x.max(axis=0) < v.min(axis=0)) or np.any(x.min(axis=0) > v.max(axis=0)):
                        continue
                    planes = ConvexHull(v).equations
                    distance = (x @ planes[:, :3].T + planes[:, 3]).max(axis=1)
                    if np.any(distance < -self.config.max_penetration_m):
                        return 'material_obstacle_penetration'
        return None

    def check_health(self, binding):
        name = binding['target'][0]
        x = self.positions(name)
        error = float(np.linalg.norm(x[binding['indices']]-self.targets(binding), axis=1).max())
        strain = self.strain_ratio(name, x)
        self._last_health[binding['hand']] = dict(max_follow_error_m=error, max_material_edge_ratio=strain)
        if not np.isfinite(x).all():
            return 'nonfinite_material'
        if np.max(np.asarray(binding['finger_fractions'])-self.finger_fractions(binding['hand'])) > self.config.max_finger_opening_fraction:
            return 'physical_fingers_opened'
        if error > self.config.max_translation_error_m:
            return 'material_follow_error'
        if strain > self.specs[name].max_strain_ratio:
            return 'material_strain'
        return self.penetration_reason(name, binding['indices'])

    def strain_ratio(self, name, positions):
        edges = self.edges[name]
        return float((np.linalg.norm(positions[edges[:, 1]]-positions[edges[:, 0]], axis=1)
                      / self.rest_lengths[name]).max()) if len(edges) else 1.

    def capture(self):
        return deepcopy(dict(schema_version=1, identities=self.identities,
            regions=list(self.regions.items()), active=list(self.active.items()),
            last_candidates=list(self.last_candidates.items()), health=self._last_health, admission=self._admission))

    def restore(self, state):
        if state['schema_version'] != 1 or state['identities'] != self.identities:
            raise ValueError("Soft grasp material identity mismatch")
        saved = deepcopy(state)
        self.regions = {tuple(k): v for k, v in saved['regions']}
        self.active = {tuple(k): v for k, v in saved['active']}
        self.last_candidates = {tuple(k): v for k, v in saved['last_candidates']}
        self._last_health = saved['health']
        self._admission = saved['admission']

    def verify_bindings(self, bindings):
        expected = {tuple(b['target']) for b in bindings}
        if expected != set(self.active) or any(not self.exists(b) for b in bindings):
            raise ValueError("Restored soft ownership differs from native constraints")
        self.verify_native_ownership(bindings)

    def read_model(self):
        return dict(constraint_model=self.config.model, acquisition_evidence=self.evidence_source,
                    sampling_scope='one geometry sample per World tick; no contact-force claim',
                    reaction_force=None, health=deepcopy(self._last_health), admission=deepcopy(self._admission),
                    collision_scope='native backend contacts; convex obstacle penetration guard at World ticks')
