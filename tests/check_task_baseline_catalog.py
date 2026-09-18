"""Check namespace isolation and invalid baseline metadata before GPU work."""
from copy import deepcopy
import subprocess
import sys
import unittest

from topogym.tasks.catalog import TASK_IDS, baseline_manifest, load_card, validate_card


class CatalogChecks(unittest.TestCase):
    def test_namespaces_do_not_initialize_physics(self):
        subprocess.run([sys.executable, "-c",
            "import sys, topogym.tasks; "
            "assert 'genesis' not in sys.modules; "
            "assert not any(n.startswith('topogym.tasks_legacy') for n in sys.modules)"], check=True)

    def test_baseline_manifest_is_deterministic_and_unqualified(self):
        for task_id in TASK_IDS:
            a = baseline_manifest(task_id, 7)
            self.assertEqual(a, baseline_manifest(task_id, 7))
            self.assertFalse(a["physics_qualified"])
            self.assertEqual(a["sampling"], "fixed_baseline")

    def test_invalid_axes_and_qualification_are_rejected(self):
        source = load_card("rope_threading")
        for change in (lambda c: c["axes"][0].update(path="missing.radius"),
                       lambda c: c["physics"].update(qualification="passed"),
                       lambda c: c["baseline"]["rope"].update(length_m=float("nan"))):
            card = deepcopy(source)
            change(card)
            with self.assertRaises(ValueError):
                validate_card(card)

    def test_invalid_seeds_and_unknown_task_are_rejected(self):
        for seed in (-1, True, 1.5):
            with self.assertRaises(ValueError): baseline_manifest("lock_picking", seed)
        with self.assertRaises(ValueError): load_card("../tasks_legacy")


if __name__ == "__main__":
    unittest.main()
