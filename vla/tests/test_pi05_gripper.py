"""pi0.5 ALOHA gripper <-> TopoGym opening. Expected values were computed with openpi's own aloha_policy functions
(_gripper_to_angular on the state, _gripper_from_angular on the model value) in the vla-pi05 environment."""
import numpy as np

from vla.models.pi05.gripper import from_openpi_gripper, to_openpi_gripper


def test_states_map_the_topogym_finger_travel_onto_pis_closed_to_open_range():
    # openpi turns these into pi gripper values 0.0, 0.105665 and 0.945653 (its fully open state).
    np.testing.assert_allclose(to_openpi_gripper(np.array([0.0, 0.183, 1.0])), [0.599736, 0.672985, 1.0], atol=1e-6)


def test_actions_map_pis_closed_and_open_onto_topogym_closed_and_open():
    # openpi outputs 0.553378, 0.790087 and 1.026701 for model values 0, 0.5 and 0.9998 (its q99).
    np.testing.assert_allclose(from_openpi_gripper(np.array([0.553378, 0.790087, 1.026701])), [0.0, 0.705561, 0.999387],
                               atol=1e-5)


def test_actions_beyond_the_linkage_limit_stay_fully_open():
    np.testing.assert_allclose(from_openpi_gripper(np.array([1.2, 1.5])), [1.0, 1.0], atol=1e-9)
