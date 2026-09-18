"""Route differences must survive retiming while ignoring sample density."""
import numpy as np

from topogym.tasks.horseshoe_ring.family_space import arc_sample, route_distance


def test_retiming_and_duplicate_holds_do_not_make_a_new_route():
    route=np.array([[0.,0.,0.],[.1,0.,0.],[.1,.1,0.]])
    dense=np.vstack([np.repeat(route[:1],20,axis=0),
        np.column_stack([np.linspace(0,.1,101),np.zeros(101),np.zeros(101)]),
        np.column_stack([np.full(11,.1),np.linspace(0,.1,11),np.zeros(11)])])
    result=route_distance(route,dense)
    assert result['sampled_hausdorff_mm']<1e-8
    assert result['maximum_directed_fraction_above_threshold']==0


def test_a_sustained_different_corridor_passes_distance_gate():
    route=np.column_stack([np.linspace(0,.2,101),np.zeros(101),np.zeros(101)])
    result=route_distance(route,route+[0,0,.06])
    assert abs(result['directed_p95_max_mm']-60)<1e-8
    assert result['maximum_directed_fraction_above_threshold']==1


def test_stationary_stage_stays_stationary():
    np.testing.assert_array_equal(arc_sample(np.array([[1.,2.,3.]]),count=10),np.tile([1.,2.,3.],(10,1)))
