import numpy as np
import pytest
from topogym.world.physics.pbd_table_friction import friction_velocity, TabletopPBDFriction


def test_contact_friction_is_dissipative_and_does_not_pin_or_affect_flight():
    p = np.array([[0, 0, .004], [0, 0, .1], [0, 0, .004], [2, 0, .004]])
    v = np.array([[.5, -.4, -.02]]*4)
    free = [True, True, False, True]
    result = friction_velocity(p, v, free, bounds=([-.5, -.5], [.5, .5]), surface_z=0.,
        radius=.004, tolerance=.001, normal_acceleration=9.81, dt=.0025, static_mu=.5, kinetic_mu=.4)
    np.testing.assert_array_equal(result[1:], v[1:])
    np.testing.assert_array_equal(result[:, 2], v[:, 2])
    assert np.linalg.norm(result[0, :2]) == pytest.approx(np.linalg.norm(v[0, :2])-.4*9.81*.0025)
    assert np.dot(result[0, :2], v[0, :2]) > 0


def test_static_contact_stops_only_within_normal_load_budget():
    p, v = np.array([[0, 0, .004]]), np.array([[.005, 0., .01]])
    options = dict(bounds=([-.5, -.5], [.5, .5]), surface_z=0., radius=.004,
        tolerance=.001, dt=.0025, static_mu=.5, kinetic_mu=.4)
    np.testing.assert_array_equal(friction_velocity(p, v, [True], normal_acceleration=0, **options), v)
    np.testing.assert_array_equal(friction_velocity(p, v, [True], normal_acceleration=9.81, **options), [[0, 0, .01]])


@pytest.mark.parametrize("parameters", [{"static_mu": -1}, {"static_mu": .2, "kinetic_mu": .4}, {"contact_tolerance_m": 0}])
def test_invalid_coefficients_rejected(parameters):
    with pytest.raises(ValueError):
        TabletopPBDFriction(("blanket",), ([-1, -1], [1, 1]), 0., **parameters)
