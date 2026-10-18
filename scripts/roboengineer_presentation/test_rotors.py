"""Regression checks for motor-driven presentation, independent of body motion."""

import unittest

import numpy as np

from scripts.roboengineer_presentation.rotors import landing_rotors


class LandingRotorTests(unittest.TestCase):
    def test_hover_spins_opposite_pairs_at_force_derived_speed(self):
        rows = [
            {"t": t, "motor_forces": [36, 36, 36, 36]}
            for t in [0, 0.01, 0.02, 0.03, 0.04]
        ]
        result = landing_rotors(rows, [0, 0.04], 1e-6)
        np.testing.assert_allclose(result["rpm"], 6000)
        np.testing.assert_allclose(
            result["phase"][1] - result["phase"][0],
            np.array([1, -1, 1, -1]) * 8 * np.pi,
        )

    def test_shutdown_preserves_phase_and_stops(self):
        rows = [
            {"t": t, "motor_forces": [force] * 4}
            for t, force in [(0, 36), (0.01, 9), (0.02, 0), (0.03, 0), (0.04, 0)]
        ]
        result = landing_rotors(rows, [0, 0.01, 0.02, 0.04], 1e-6)
        np.testing.assert_allclose(result["rpm"][:, 0], [6000, 3000, 0, 0])
        np.testing.assert_array_equal(result["phase"][2], result["phase"][3])
        self.assertGreater(result["phase"][2, 0], 0)

    def test_missing_or_invalid_motor_data_fails_closed(self):
        with self.assertRaises(KeyError):
            landing_rotors([{"t": 0}, {"t": 0.01}], [0], 1e-6)
        for forces in [[-1, 1, 1, 1], [float("nan")] * 4, [1, 1]]:
            with self.assertRaises(ValueError):
                landing_rotors(
                    [
                        {"t": 0, "motor_forces": forces},
                        {"t": 0.01, "motor_forces": forces},
                    ],
                    [0],
                    1e-6,
                )


if __name__ == "__main__":
    unittest.main()
