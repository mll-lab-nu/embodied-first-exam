"""Actual Coil assets with synthetic terminal states; no physics qualification."""
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from topogym.config.registry import task_definition
from terminal_fixtures import body
from test_terminal_settling import geometry


@pytest.fixture(params=("easy", "medium", "hard"))
def coil(request, tmp_path):
    task = task_definition("cast_coil", request.param)()
    task.declare(tmp_path, .75)
    names = tuple(task.local_vertices)
    task.bind({name: SimpleNamespace(links=[SimpleNamespace(idx=i)])
               for i,name in enumerate((*names,"robot","table"))})
    rotation = Rotation.from_euler("z",90,degrees=True)
    bottom = min(rotation.apply(v+task.body_origins[n])[:,2].min() for n,v in task.local_vertices.items())
    origin = np.array([0.,0.,.75-bottom])
    s = geometry(dict(physics_step=0, assist_active=False,
        bodies={n: body(origin+rotation.apply(task.body_origins[n]), rotation.as_quat()[[3,0,1,2]]) for n in names},
        contacts=dict(link_a=np.empty(0,int), link_b=np.empty(0,int),
                      force=np.zeros((0,3)), penetration=np.empty(0))), names)
    _, bounds, _, _ = task.rigid_measurements(s)
    s["release_geometry"]["target_bounds_m"] = {n: np.asarray([bounds[n]]) for n in names}
    return task,s


@pytest.mark.parametrize("air,assist", [(True,True),(True,False),(False,True),(False,False)])
def test_coil_requires_table_release_and_full_confirmation(coil, air, assist):
    task,s = coil
    if air:
        for b in s["bodies"].values(): b["position_m"][2] += .2
        for bounds in s["release_geometry"]["target_bounds_m"].values(): bounds[:,:,2] += .2
    s["assist_active"] = assist
    task.initialize(s)
    for step in range(1,202):
        s["physics_step"] = s["release_geometry"]["physics_step"] = step
        result = task.update(s,.0025)
        if step < 201:
            assert not result.task_success
    assert result.task_success == (not air and not assist)


def test_aligned_coil_with_fingers_still_near_cannot_finish(coil):
    task,s = coil
    s["release_geometry"]["robot_bounds_m"] = s["release_geometry"]["target_bounds_m"]["coil_gold"].copy()
    task.initialize(s)
    for step in range(1,8):
        s["physics_step"] = s["release_geometry"]["physics_step"] = step
        result = task.update(s,.1)
    assert not result.task_success and not result.metrics["final_settling"]["robot_clear"]
