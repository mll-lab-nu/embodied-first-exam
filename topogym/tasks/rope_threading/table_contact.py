"""Analytic tabletop contact for the rope inside the finite table footprint.

The visible and rigid-collision table remains the original box. Only its
native FEM contact pair is replaced by a coplanar ground primitive, with the
same mixed friction and resistance. Every observed FEM substep must stay
strictly inside the finite tabletop; this is not an infinite-table task.
"""
import numpy as np


class AnalyticTableContact:
    def __init__(self, coupler, rope, table, table_position, table_size):
        self.coupler, self.rope, self.table = coupler, rope, table
        position, size = np.asarray(table_position, float), np.asarray(table_size, float)
        self.height = float(position[2]+size[2]/2)
        self.lower, self.upper = position[:2]-size[:2]/2, position[:2]+size[:2]/2
        self.required_margin = .01
        self.minimum_margin = float('inf')
        self.observed_steps = 0
        self.registered = False
        self.original_register = coupler._register_contact_pairs
        coupler._register_contact_pairs = self._register

    def _register(self):
        import uipc
        self.original_register()
        c = self.coupler
        tab = c._ipc_contact_tabular
        rope_element = c._ipc_fem_contacts[self.rope]
        table_element = c._ipc_abd_contacts[self.table]
        old = tab.at(rope_element.id(), table_element.id())
        self.friction = float(old.friction_rate())
        self.resistance = float(old.resistance())
        if not old.is_enabled():
            raise RuntimeError('The original FEM/table contact pair must be enabled')
        tab.insert(rope_element, table_element, self.friction, self.resistance, False)
        plane_element = tab.create('threading_analytic_table')
        plane = uipc.geometry.ground(self.height, np.array([0., 0., 1.]))
        plane_element.apply_to(plane)
        c._ipc_objects.create('threading_analytic_table').geometries().create(plane)
        # Explicitly disable every other plane pair, including the robot,
        # fixtures, default element, and the plane itself.
        elements = [tab.default_element(), c._ipc_no_collision_contact, plane_element]
        for contacts in (c._ipc_fem_contacts, c._ipc_cloth_contacts,
                         c._ipc_abd_contacts, c._ipc_ground_contacts):
            elements.extend(contacts.values())
        elements = {element.id(): element for element in elements}
        if set(elements) != set(range(tab.element_count())):
            raise RuntimeError('Unaccounted contact elements in analytic tabletop registration')
        for element in elements.values():
            tab.insert(plane_element, element, 0., 0., False)
        tab.insert(plane_element, rope_element, self.friction, self.resistance, True)
        replacement = tab.at(plane_element.id(), rope_element.id())
        self.registered = bool(not tab.at(rope_element.id(), table_element.id()).is_enabled()
            and replacement.is_enabled()
            and replacement.friction_rate() == self.friction
            and replacement.resistance() == self.resistance
            and all(not tab.at(plane_element.id(), i).is_enabled()
                    for i in elements if i != rope_element.id()))
        if not self.registered:
            raise RuntimeError('Failed to install the exclusive coplanar FEM/table contact pair')

    def finish_build(self):
        self.coupler._register_contact_pairs = self.original_register

    def observe(self, positions, *, initial=False):
        points = np.asarray(positions, float)[:, :2]
        margin = float(min(np.min(points-self.lower), np.min(self.upper-points)))
        self.minimum_margin = min(self.minimum_margin, margin)
        if not initial:
            self.observed_steps += 1
        if not np.isfinite(margin) or margin < self.required_margin:
            raise RuntimeError('Rope left the qualified interior of the finite tabletop')

    def specification(self):
        return dict(model='analytic_plane_with_finite_table_interior_guard',
            plane_height_m=self.height, table_lower_xy_m=self.lower.tolist(),
            table_upper_xy_m=self.upper.tolist(), required_interior_margin_m=self.required_margin,
            rope_table_pair_friction=self.friction, rope_table_pair_resistance=self.resistance,
            original_fem_table_box_pair_disabled=True, all_other_plane_pairs_disabled=True,
            rigid_robot_table_contact='original finite box', registered=self.registered)

    def report(self, observed_steps):
        checks = dict(exclusive_coplanar_replacement=self.registered,
            finite_footprint_observed_every_substep=self.observed_steps == observed_steps > 0,
            remained_inside_finite_table=self.minimum_margin >= self.required_margin)
        return dict(**self.specification(), checks=checks, passed=all(checks.values()),
            observed_steps=self.observed_steps, minimum_interior_margin_m=self.minimum_margin)
