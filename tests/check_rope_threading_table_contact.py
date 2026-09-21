"""Check native contact-pair replacement and the finite-table guard on CPU."""
import unittest
from types import SimpleNamespace

import numpy as np
import uipc

from topogym.tasks.rope_threading.table_contact import AnalyticTableContact


class TableContactChecks(unittest.TestCase):
    def build_contact(self):
        scene = uipc.Scene(uipc.Scene.default_config())
        tab = scene.contact_tabular()
        rope, table, ring = object(), object(), object()
        a, b, c = (tab.create(name) for name in ('rope', 'table', 'ring'))
        none = tab.create('none')
        tab.insert(a, b, .173205, 1e9, True)
        tab.insert(a, c, .25, 2e9, True)
        coupler = SimpleNamespace(_register_contact_pairs=lambda: None,
            _ipc_contact_tabular=tab, _ipc_objects=scene.objects(),
            _ipc_fem_contacts={rope: a}, _ipc_abd_contacts={table: b, ring: c},
            _ipc_cloth_contacts={}, _ipc_ground_contacts={}, _ipc_no_collision_contact=none)
        contact = AnalyticTableContact(coupler, rope, table, [0., 0., .9], [1.5, 1.4, .04])
        coupler._register_contact_pairs()
        return contact, scene, tab, a, b, c

    def test_replacement_keeps_coefficients_and_other_contacts(self):
        contact, scene, tab, rope, table, ring = self.build_contact()
        self.assertFalse(tab.at(rope.id(), table.id()).is_enabled())
        unchanged = tab.at(rope.id(), ring.id())
        self.assertTrue(unchanged.is_enabled())
        self.assertEqual(unchanged.friction_rate(), .25)
        self.assertEqual(unchanged.resistance(), 2e9)
        plane = tab.element_count()-1
        active = [i for i in range(tab.element_count()) if tab.at(plane, i).is_enabled()]
        self.assertEqual(active, [rope.id()])
        replacement = tab.at(plane, rope.id())
        self.assertEqual(replacement.friction_rate(), .173205)
        self.assertEqual(replacement.resistance(), 1e9)
        self.assertAlmostEqual(contact.height, .92)

    def test_full_substep_coverage_and_table_edge_are_required(self):
        contact, scene, *_ = self.build_contact()
        points = np.array([[0., 0., .925], [.1, .2, .93]])
        contact.observe(points, initial=True)
        self.assertFalse(contact.report(1)['passed'])
        contact.observe(points)
        self.assertTrue(contact.report(1)['passed'])
        self.assertFalse(contact.report(2)['passed'])
        with self.assertRaisesRegex(RuntimeError, 'finite tabletop'):
            contact.observe(np.array([[.745, 0., .925]]))
        self.assertFalse(contact.report(2)['passed'])


if __name__ == '__main__':
    unittest.main()
