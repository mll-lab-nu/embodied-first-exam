"""Check FEM recording gates against real initialized and deliberately invalid states."""
from pathlib import Path
import tempfile
import unittest

import mujoco
import numpy as np

from topogym.tasks.slotted_post_ring.archive import publication_allowed
from topogym.tasks.slotted_post_ring.fem import build_model
from topogym.tasks.slotted_post_ring.fem_fixture import VolumeAudit


class FEMRecordingChecks(unittest.TestCase):
    def test_probes_failed_and_partial_runs_cannot_be_published(self):
        for report in ({'passed': True, 'scope': 'gravity'},
                       {'passed': False, 'full_process_demo': True},
                       {'passed': True, 'full_robot_demo': False}):
            self.assertFalse(publication_allowed(report))
        self.assertTrue(publication_allowed({'passed': True, 'full_process_demo': True}))

    def test_inversion_and_unreleased_tail_fail_auditing(self):
        with tempfile.TemporaryDirectory() as temp:
            model, data, spec = build_model(Path(temp)/'model')
            with np.load(Path(temp)/'model/fem_mesh.npz') as mesh:
                audit = VolumeAudit(model, mesh, spec)
                audit.observe(data, False)
                self.assertTrue(audit.checks()['finite_no_inversion'])
                data.time = 2.
                audit.observe(data, False)
                self.assertFalse(audit.tail_checks()[0]['last_two_seconds_released'])
                data.flexvert_xpos[mesh['elements'][0, 0]] = data.flexvert_xpos[mesh['elements'][0, 1]]
                audit.observe(data, True)
                self.assertFalse(audit.checks()['positive_volume_margin'])


if __name__ == '__main__':
    unittest.main()
