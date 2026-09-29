from dataclasses import dataclass
from types import SimpleNamespace
import numpy as np
from scipy.spatial.transform import Rotation
from topogym.tasks.horseshoe_ring.common import HorseshoeRingTask
from terminal_fixtures import placement, region


@dataclass
class Loop:
    body: str
    center: np.ndarray
    rotation: object
    linked: bool = True
    def linking(self, other):
        return int(self.linked and other.linked)


def test_ring_placement_requires_permanent_chain_connections():
    task = HorseshoeRingTask()
    state = placement(task,("target_ring",),("shoe_a","shoe_b"))
    loops = {name:Loop(name,np.zeros(3),Rotation.identity()) for name in ("shoe_a","shoe_b")}
    task.assembly = SimpleNamespace(loops=loops,edges=[("shoe_a","shoe_b")])
    task.body_origins = {name:np.zeros(3) for name in loops}
    assert task.evaluate_goal_region(state,region())[0]
    loops["shoe_a"].linked = False
    assert task.evaluate_goal_region(state,region())[1] == "Physical chain/eye connection lost"
