"""Circular symmetry: material spin cannot change the chosen world grasp."""
from types import SimpleNamespace
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.horseshoe_ring.physical_plan import tracked_ring_grasp_frame


def test_circular_material_spin_preserves_gravity_grasp():
    base = Rotation.from_euler("zy", [20, 10], degrees=True)
    holder = {"rotation": base}
    motion = SimpleNamespace(instance={}, body_pose=lambda n: (np.array([.1, .05, 1.2]), holder["rotation"]),
        task=SimpleNamespace(assembly=SimpleNamespace(unit=.002, template={"target_ring": {"centerline_radius": 29}},
            loops={"target_ring": SimpleNamespace(rotation=Rotation.from_euler("y", 90, degrees=True))})))
    choice = dict(angle=0., beta=-30., roll=1, gravity_angle_offset_deg=0.)
    before = tracked_ring_grasp_frame(motion, choice)
    for spin in (30, 75, 150, 270):
        holder["rotation"] = base*Rotation.from_euler("x", spin, degrees=True)
        after = tracked_ring_grasp_frame(motion, choice)
        np.testing.assert_allclose(after[0], before[0], atol=1e-12, rtol=0)
        np.testing.assert_allclose(after[1].as_matrix(), before[1].as_matrix(), atol=1e-12, rtol=0)
    # Historical baselines explicitly retain the older material-angle recipe.
    motion.instance = None
    assert np.linalg.norm(tracked_ring_grasp_frame(motion, choice)[0]-before[0]) > .01
