import unittest
import numpy as np
from scripts.control_transfer.trusted.fly import wind_vector, wind_drag_increment, parameters
from scripts.control_transfer.neuralfly_spec import make_spec


class WindTests(unittest.TestCase):
    def test_calm_compatibility(self):
        for velocity in ([0, 0, 0], [1, -2, 3]):
            np.testing.assert_array_equal(wind_drag_increment(velocity, [0, 0, 0]), [0, 0, 0])

    def test_direction_and_magnitude(self):
        p = parameters(10100)
        for t in np.linspace(0, 10, 20):
            w = wind_vector(t, 4, p)
            self.assertAlmostEqual(np.linalg.norm(w), 8.5 + 2.4 * np.sin(t + p["wind_phase"]))
            self.assertEqual(w[2], 0)
            np.testing.assert_allclose(wind_drag_increment([0, 0, 0], w), 0.045 * np.linalg.norm(w) * w)

    def test_rotation_covariance(self):
        r = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        v, w = np.array([1.0, 2, 3]), np.array([4.0, -5, 0])
        np.testing.assert_allclose(wind_drag_increment(r @ v, r @ w), r @ wind_drag_increment(v, w))

    def test_revision_isolation(self):
        for rev in ("fixed-eight/1", "general-eight/1"):
            self.assertNotIn("dynamics_revision", make_spec(0, rev)["bank"]["held_out"][0])
        s = make_spec(0, "general-eight-wind/1")
        self.assertEqual(s["name"], "neural-fly-vector-wind-v1")
        self.assertTrue(all(c["dynamics_revision"] == "vector-wind/1" for c in s["bank"]["held_out"]))
