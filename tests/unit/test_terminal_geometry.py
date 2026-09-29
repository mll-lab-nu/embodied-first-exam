import numpy as np
import pytest
from topogym.utils.geometry.rope import centerline_indices, sample_material_centerline, load_centerline_map
from topogym.utils.geometry.passage import aperture_crossings, passage_initial, advance_passage, planar_clearance
from topogym.assets.geometry.rope_volume import write_rope_volume
from topogym.evaluation.task_metrics import soft_speed, body_points, rigid_asset_vertices
from topogym.tasks.base import EntitySpec
from terminal_fixtures import soft, body


def test_generated_rope_map_survives_vertex_permutation(tmp_path):
    path = write_rope_volume(tmp_path/"tube.npz", [[0,0,0], [.1,0,0]], .002, sides=5, profile="structured_baseline")
    indices, material = load_centerline_map(path)
    with np.load(path) as data:
        order = np.random.default_rng(4).permutation(len(material))
        shuffled = centerline_indices(data["rest"][order], material[order])
        state = soft(data["spawn"][order]+[1,2,3])
        state["material_s_m"] = material[order]
        result = sample_material_centerline(state, shuffled, material[order])
        np.testing.assert_allclose(result, data["spawn"][indices]+[1,2,3])
        state["material_s_m"] = state["material_s_m"]+.1
        with pytest.raises(ValueError, match="identity"):
            sample_material_centerline(state, shuffled, material[order])


def test_missing_or_duplicate_material_axis_is_rejected():
    with pytest.raises(ValueError):
        centerline_indices([[0,0,0],[1,0,0],[2,1,0]], [0,1,2])
    with pytest.raises(ValueError):
        centerline_indices([[0,0,0],[0,0,0],[1,0,0]], [0,0,1])


def test_fine_rope_curved_spawn_end_stops_and_material_map(tmp_path):
    angle = np.linspace(0, np.pi/2, 25)
    line = np.column_stack((.05*np.sin(angle), .05*(1-np.cos(angle)), np.zeros(25)))
    path = write_rope_volume(tmp_path/'fine.npz', line, .004, end_stops=True)
    rings, material = load_centerline_map(path)
    with np.load(path) as data:
        for name in ('rest', 'spawn'):
            corners = data[name][data['elements']]
            assert np.all(np.linalg.det(corners[:, 1:]-corners[:, :1]) > 0)
        assert rings.ndim == 2 and rings.shape[1] == 24
        assert np.max(np.diff(material[rings[:, 0]])) <= .001375
        np.testing.assert_allclose(np.linalg.norm(data['rest'][rings[0], 1:], axis=1), .0064)
        # Mapping follows authored material indices, not current world-x or
        # incidental TetGen interior vertex order.
        order = np.random.default_rng(4).permutation(len(material))
        remapped = np.argsort(order)[rings]
        state = soft(data['spawn'][order]+[1,2,3])
        state['material_s_m'] = material[order]
        np.testing.assert_allclose(sample_material_centerline(state, remapped, material[order]), data['centerline']+[1,2,3], atol=1e-12)
        for distance in (material, material.max()-material):
            assert np.count_nonzero(distance <= .004) > 24
        invalid = remapped.copy()
        invalid[0, 0] = invalid[1, 0]
        with pytest.raises(ValueError, match='rings'):
            sample_material_centerline(state, invalid, material[order])


def test_fine_rope_assets_are_reproducible(tmp_path):
    paths = [write_rope_volume(tmp_path/f'{i}.npz', [[0,0,0],[.025,0,0]], .004) for i in range(2)]
    assert paths[0].read_bytes() == paths[1].read_bytes()


def test_open_curve_never_closes_and_opposite_crossings_do_not_cancel():
    hits, ambiguous = aperture_crossings([[-1,0,0],[1,0,0],[-1,0,0]], [0,0,0], [1,0,0], .5)
    assert [h["sign"] for h in hits] == [1,-1] and not ambiguous
    hits, _ = aperture_crossings([[-1,0,0],[-1,2,0],[1,2,0]], [0,0,0], [1,0,0], .5)
    assert hits == []  # An artificial closing segment would cross the disk.


@pytest.mark.parametrize("points", [ [[-1,0,0],[0,0,0],[-1,0,0]], [[0,-2,0],[0,2,0]], [[-1,.5,0],[1,.5,0]] ])
def test_tangent_coplanar_and_rim_are_ambiguous(points):
    assert aperture_crossings(points,[0,0,0],[1,0,0],.5)[1]


def test_crossing_at_vertex_counted_once():
    hits, ambiguous = aperture_crossings([[-1,0,0],[0,0,0],[1,0,0]], [0,0,0], [1,0,0], .5)
    assert len(hits) == 1 and not ambiguous


def test_ordered_multi_station_tick_retreat_retry_and_outside_bypass():
    p = np.array([[-.2,0,0],[-.3,0,0],[-.4,0,0]])
    history = passage_initial(p)
    done, saved, _ = advance_passage(p+[1,0,0],history,[0,0,0],[1,0,0],.1,.05)
    assert done and np.all(saved["stages"] == 2)
    assert np.all(history["stages"] == 0)
    done, back, _ = advance_passage(p,saved,[0,0,0],[1,0,0],.1,.05)
    assert not done and np.all(back["stages"] == 0)
    assert advance_passage(p+[1,0,0],back,[0,0,0],[1,0,0],.1,.05)[0]
    outside = p+[0,1,0]
    assert not advance_passage(outside+[1,0,0],passage_initial(outside),[0,0,0],[1,0,0],.1,.05)[0]
    # Root crosses first even though the final whole strand is on the exit side.
    initial = p[::-1].copy()
    assert not advance_passage(initial+[1,0,0],passage_initial(initial),[0,0,0],[1,0,0],.1,.05)[0]


@pytest.mark.parametrize("points", [ [[0,0,0],[1,1,0],[0,1,0],[1,0,0]], [[0,0,0],[1,0,0],[.2,0,0],[.8,0,0]], [[0,0,0],[1,0,0],[0,0,0]], [[0,0,0],[0,0,1]] ])
def test_projected_crossings_overlap_and_collapse(points):
    assert not planar_clearance(points,np.arange(len(points)),.01)[0]


def test_all_vertex_speed_and_actual_pose():
    state = soft(np.zeros((1000,3)))
    state["velocity_m_s"][-1,0] = .1
    quiet, metrics = soft_speed(state)
    assert not quiet and metrics["maximum_speed_m_s"] == .1
    np.testing.assert_allclose(body_points(body((1,2,3),(0,0,0,1)),[[1,0,0]]),[[0,2,3]],atol=1e-12)


def test_collision_extent_and_fixed_link_origins_are_included(tmp_path):
    path = tmp_path/"body.urdf"
    path.write_text('''<robot name="r"><link name="root"><visual><geometry><box size=".1 .1 .1"/></geometry></visual></link>
    <link name="child"><collision><origin xyz="0 0 .2"/><geometry><sphere radius=".1"/></geometry></collision></link>
    <joint name="j" type="fixed"><parent link="root"/><child link="child"/><origin xyz="1 0 0"/></joint></robot>''')
    points = rigid_asset_vertices(EntitySpec("r","urdf",path))
    assert np.max(points[:,0]) == pytest.approx(1.1)
    assert np.max(points[:,2]) == pytest.approx(.3)
