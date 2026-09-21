"""Evidence reuse must not hide an executed physical implementation change."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

from topogym.tasks.rope_threading.qualification import (digest, implementation_equivalence,
    compare_trajectories, physical_profile, verify_for_execution)

DRIVER = 'topogym/tasks/rope_threading/physics_probe.py'
OLD = '''def main():
    reference_mode = args.mode in ("reference_prefix", "full_threading")
    stiffness = 50000
    if reference_mode:
        actions = Robot(settle_s=5)
    scene.step()
'''
NEW = OLD.replace('settle_s=5', 'settle_s=20')


class EvidenceReuseChecks(unittest.TestCase):
    def config(self):
        from omegaconf import OmegaConf
        return OmegaConf.create(dict(env=dict(sim={'dt': .005}, world={'table': {}}, robot_mount={}),
            robot_control={'gain': 100}, task=dict(rope={'E': 50000}, validation=dict(
                final_post_sequence_settle_s=20., max_unsupported_release_height_m=.09))))

    def test_observation_duration_is_separate_from_physical_parameters(self):
        cfg = self.config(); baseline = physical_profile(cfg)
        cfg.task.validation.final_post_sequence_settle_s = 60.
        self.assertEqual(physical_profile(cfg), baseline)
        cfg.task.validation.max_unsupported_release_height_m = .20
        self.assertNotEqual(physical_profile(cfg), baseline)
        cfg.task.validation.max_unsupported_release_height_m = .09
        cfg.task.rope.E = 40000
        self.assertNotEqual(physical_profile(cfg), baseline)

    def test_execution_cannot_shorten_the_qualified_settling(self):
        import json
        from unittest.mock import patch
        cfg = self.config()
        evidence = dict(passed=True, profile=physical_profile(cfg), reference_speed=3.,
                        minimum_robot_settling_s=20., reference_sha256={}, source_sha256={})
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'qualification.json'; p.write_text(json.dumps(evidence))
            with patch('topogym.tasks.rope_threading.qualification.summarize', return_value=evidence):
                for duration in (5., float('nan')):
                    cfg.task.validation.final_post_sequence_settle_s = duration
                    with self.assertRaisesRegex(ValueError, 'settling observation'):
                        verify_for_execution(p, cfg, 3., tmp)
                cfg.task.validation.final_post_sequence_settle_s = 60.
                result = verify_for_execution(p, cfg, 3., tmp)
                self.assertEqual(result['execution_settling_s'], 60.)

    def check_pair(self, old, new, mode='ring_contact', tamper=False):
        with tempfile.TemporaryDirectory() as tmp:
            roots = [Path(tmp)/name for name in ('old', 'new')]
            specs = []
            for root, source in zip(roots, (old, new)):
                path = root/'implementation'/DRIVER
                path.parent.mkdir(parents=True)
                path.write_text(source)
                specs.append(dict(mode=mode, source_sha256={DRIVER: digest(path)}))
            if tamper:
                (roots[0]/'implementation'/DRIVER).write_text(new)
            return implementation_equivalence(roots[0], specs[0], roots[1], specs[1])

    def test_unexecuted_robot_settling_change_can_reuse_nonrobot_probe(self):
        for mode in ('ring_contact', 'free_settle'):
            self.assertTrue(self.check_pair(OLD, NEW, mode)['passed'])

    def test_robot_probe_must_be_rerun(self):
        for mode in ('reference_prefix', 'full_threading'):
            self.assertFalse(self.check_pair(OLD, NEW, mode)['passed'])

    def test_material_and_branch_condition_changes_require_new_evidence(self):
        self.assertFalse(self.check_pair(OLD, NEW.replace('50000', '40000'))['passed'])
        self.assertFalse(self.check_pair(OLD, NEW.replace('"full_threading"', '"ring_contact"'))['passed'])

    def test_changed_saved_source_is_rejected(self):
        self.assertFalse(self.check_pair(OLD, NEW, tamper=True)['passed'])

    def test_nonrobot_else_branch_remains_part_of_comparison(self):
        old = OLD.replace('    scene.step()', '    else:\n        force = 1\n    scene.step()')
        self.assertFalse(self.check_pair(old, old.replace('force = 1', 'force = 2'))['passed'])

    def test_extra_observation_is_explicitly_outside_paired_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a', Path(tmp)/'b'
            a.mkdir(); b.mkdir()
            np.savez(a/'trajectory.npz', times=[0., 1., 2.], centerlines=np.zeros((3, 81, 3)))
            longer = np.zeros((4, 81, 3))
            longer[-1] = 1.  # No counterpart exists; no comparison claim is allowed here.
            np.savez(b/'trajectory.npz', times=[0., 1., 2., 3.], centerlines=longer)
            result = compare_trajectories(a, b)
            self.assertTrue(result['passed'])
            self.assertEqual(result['sampled_seconds'], 2.)
            self.assertEqual(result['trajectory_end_times_s'], [2., 3.])
            self.assertEqual(result['unpaired_tail_seconds'], [0., 1.])


if __name__ == '__main__':
    unittest.main()
