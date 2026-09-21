"""Reject mismatched material identities before restoring a recorded shape."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import numpy as np
from omegaconf import OmegaConf
from topogym.tasks.blanket_flatten.initial_state import restore_selected_shape


class InitialStateChecks(unittest.TestCase):
    def test_same_material_shape_is_a_fresh_zero_velocity_reset(self):
        self.exercise(False)

    def test_different_material_binding_is_rejected_before_position_write(self):
        self.exercise(True)

    def exercise(self, mismatch):
        written = []
        cloth = SimpleNamespace(n_particles=3, _edges_len_rest=np.array([1., 1., np.sqrt(2)]),
                                set_particles_pos=lambda x: written.append(('position', x.copy())),
                                set_particles_vel=lambda x: written.append(('velocity', x)))
        task = SimpleNamespace(cloth=cloth, faces=np.array([[0, 1, 2]]), supports=np.arange(3)[:, None],
                               weights=np.ones((3, 1)), material_uv=np.array([[0., 0.], [1., 0.], [0., 1.]]))
        with TemporaryDirectory() as directory:
            root=Path(directory); source=root/'input.npz'
            np.savez(source, positions=np.array([[[0., 0., 1.], [1., 0., 1.], [0., 1., 1.]]]),
                     faces=task.faces, supports=task.supports, weights=task.weights,
                     material_uv=task.material_uv+(1 if mismatch else 0))
            cfg=OmegaConf.create(dict(path=str(source), frame=-1))
            if mismatch:
                with self.assertRaisesRegex(ValueError, 'material_uv'):
                    restore_selected_shape(task, cfg, root)
                self.assertEqual(written, [])
            else:
                result=restore_selected_shape(task, cfg, root)
                self.assertFalse(result['dynamics_continuation_of_source'])
                self.assertTrue(result['rest_lengths_unchanged'])
                self.assertEqual(result['initialization_position_writes'], 1)
                self.assertEqual(written[-1], ('velocity', 0.))
                np.testing.assert_array_equal(np.load(root/'selected_initial_state.npz')['velocities'], np.zeros((3, 3)))


if __name__ == '__main__':
    unittest.main()
