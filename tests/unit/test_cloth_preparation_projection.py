import numpy as np
from topogym.world.physics.cloth_preparation import MaterialVelocityProjection


def test_projection_preserves_translation_and_reduces_stretching_rate():
    p = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
    projector = MaterialVelocityProjection(np.array([[0, 1], [1, 2]]), np.ones(2), p[:, :2],
        strength=32., correction=16., clearance=.008)
    requested = np.array([[.5, 2., -1.], [1., 2., -1.], [1.5, 2., -1.]])
    result = projector.project(p, requested)
    # The [−1, 0, 1] extension mode has eigenvalue one for this chain.
    expected = np.array([[1-.5/33, 2., -1.], [1., 2., -1.], [1+.5/33, 2., -1.]])
    np.testing.assert_allclose(result, expected, atol=1e-10)
    np.testing.assert_allclose(result.mean(0), requested.mean(0), atol=1e-10)


def test_stretched_edge_receives_opposing_corrections_without_net_motion():
    p = np.array([[0., 0., 0.], [1.1, 0., 0.]])
    projector = MaterialVelocityProjection(np.array([[0, 1]]), np.ones(1),
        np.array([[0., 0.], [1., 0.]]), strength=32., correction=16., clearance=.008)
    result = projector.project(p, np.zeros_like(p))
    assert result[0, 0] > 0 > result[1, 0]
    np.testing.assert_allclose(result.sum(0), 0., atol=1e-10)
