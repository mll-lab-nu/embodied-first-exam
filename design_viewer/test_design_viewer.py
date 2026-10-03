"""Behaviour checks (CPU, no browser). From the worktree root: python -m pytest design_viewer -q
The first run builds the scene cache (hedgehog easy ~25 s)."""
import mujoco
import numpy as np
import pytest

from design_viewer import model as models
from design_viewer import scenes, view
from topogym.config.registry import variation_catalog


def _start(name):
    m = models.build(scenes.build(name))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    return m, d


def _penetration(d):
    return float(max(0., -d.contact.dist[:d.ncon].min(initial=0.)))


def _run(m, d, seconds):
    for _ in range(int(seconds/m.opt.timestep)):
        mujoco.mj_step(m, d)


def test_lists_every_integrated_variation():
    names = scenes.list_scenes()
    for task in scenes.TASKS:
        for row in variation_catalog(task):
            if row["status"] == "integrated":
                assert row["variation_id"] in names


def test_hedgehog_cage_stands_on_its_mount():
    scene = scenes.build("hedgehog_in_cage_medium")
    cage, mount = scene.body("cage"), scene.body("mount")
    assert not cage.free and scene.body("ball").free
    assert (cage.visual.vertices+cage.pos)[:, 2].min() == pytest.approx(mount.pos[2]+mount.visual.bounds[1, 2])


def test_slotted_post_pieces_are_convex_and_keep_the_slot_open():
    scene = scenes.build("slotted_post_ring_easy")
    layout, pieces = scene.extras["layout"], scene.body("post").collision
    assert all(p.is_convex for p in pieces)
    r = layout.slot_width_m/2
    y = np.linspace(-layout.post_depth_m/2+1e-3, layout.post_depth_m/2-1e-3, 5)
    sides = [[s*(r-3e-4), yy, z] for s in (-1, 1) for yy in y
             for z in np.linspace(layout.slot_bottom_m+r, layout.slot_top_m-r, 40)]
    ends = [[(r-1e-3)*np.cos(t), yy, c+s*(r-1e-3)*np.sin(t)]  # <= 1 mm hull bulge at the round ends
            for s, c in ((-1, layout.slot_bottom_m+r), (1, layout.slot_top_m-r)) for t in np.linspace(0, np.pi, 25)
            for yy in y]
    for piece in pieces:
        assert not piece.contains(np.array(sides+ends)).any()


def test_a_truncated_cache_file_is_rebuilt():
    scenes.build("horseshoe_ring_medium")
    path = next((scenes.CACHE/"horseshoe_ring_medium").glob("*.pkl"))
    path.write_bytes(path.read_bytes()[:100])
    assert scenes.build("horseshoe_ring_medium").name == "horseshoe_ring_medium"


# Hedgehog start poses are only collision-free (the ball then tips onto its spikes);
# horseshoe starts from settled rest poses.
@pytest.mark.parametrize("name, settled", [("hedgehog_in_cage_easy", False), ("hedgehog_in_cage_medium", False),
                                           ("horseshoe_ring_easy", True)])
def test_scene_starts_without_penetration(name, settled):
    m, d = _start(name)
    assert _penetration(d) < 5e-4
    start = d.xpos.copy()
    _run(m, d, .5)
    assert np.isfinite(d.qpos).all()
    if settled:
        assert np.linalg.norm(d.xpos-start, axis=1).max() < 2e-3


def test_no_scene_needs_an_engine_plugin():
    """The browser's WebAssembly client crashes on plugins ("invalid plugin slot"), stuck at PARSING."""
    for name in ("hedgehog_in_cage_medium", "horseshoe_ring_easy", "slotted_post_ring_easy"):
        assert _start(name)[0].nplugin == 0, name


def test_slotted_cord_settles_through_the_slot_once():
    m, d = _start("slotted_post_ring_easy")
    layout = scenes.build("slotted_post_ring_easy").extras["layout"]
    _run(m, d, 1.)
    p = d.xpos[[i for i in range(m.nbody) if m.body(i).name.startswith("cordB")]]
    xs = [p[i, 0]-p[i, 1]*(p[i+1, 0]-p[i, 0])/(p[i+1, 1]-p[i, 1]) for i in np.flatnonzero(p[:-1, 1]*p[1:, 1] < 0)]
    assert sum(abs(x) < layout.slot_width_m/2 for x in xs) == 1
    assert sum(x > layout.post_width_m/2 for x in xs) == 1


def _mouse(m, d, body, active):
    """Select `body` the way the browser does; returns the perturbation to steer."""
    pert, camera, scn = mujoco.MjvPerturb(), mujoco.MjvCamera(), mujoco.MjvScene(m, 20000)
    mujoco.mjv_defaultFreeCamera(m, camera)
    mujoco.mjv_updateScene(m, d, mujoco.MjvOption(), None, camera, mujoco.mjtCatBit.mjCAT_ALL, scn)
    pert.select, pert.active = m.body(body).id, active
    mujoco.mjv_initPerturb(m, d, scn, pert)
    return pert


def _hold_mouse(m, d, pert, seconds=1.5):
    for _ in range(int(seconds/m.opt.timestep)):
        d.xfrc_applied[:] = 0
        mujoco.mjv_applyPerturbForce(m, d, pert)
        mujoco.mj_step(m, d)


def test_mouse_pull_lifts_the_horseshoe_ring():
    m, d = _start("horseshoe_ring_easy")
    pert = _mouse(m, d, "target_ring", mujoco.mjtPertBit.mjPERT_TRANSLATE)
    z = d.xpos[pert.select, 2]
    pert.refselpos[:] = pert.refselpos+[0, 0, .1]  # drag 10 cm up
    _hold_mouse(m, d, pert)
    assert d.xpos[pert.select, 2]-z > .05


def test_mouse_turn_rotates_the_horseshoe_ring():
    m, d = _start("horseshoe_ring_easy")
    pert = _mouse(m, d, "target_ring", mujoco.mjtPertBit.mjPERT_ROTATE)
    start = d.xquat[pert.select].copy()
    mujoco.mju_mulQuat(pert.refquat, [np.cos(np.pi/8), 0, np.sin(np.pi/8), 0], start)  # turn 45 deg
    _hold_mouse(m, d, pert)
    turned = np.zeros(3)
    mujoco.mju_subQuat(turned, d.xquat[pert.select], start)
    assert np.degrees(np.linalg.norm(turned)) > 25


def test_hold_keeps_a_body_in_place_and_holding_again_lets_it_go():
    m, d = _start("hedgehog_in_cage_medium")
    ball = m.body("ball").id
    d.qpos[m.joint("ball_free").qposadr[0]+2] += .01  # lift clear of the floor
    mujoco.mj_forward(m, d)
    z = d.xpos[ball, 2]
    models.toggle_hold(m, d, "ball")
    _run(m, d, .5)
    assert abs(d.xpos[ball, 2]-z) < 5e-4 and models.held(m, d) == ["ball"]
    models.toggle_hold(m, d, "ball")
    _run(m, d, .3)
    assert d.xpos[ball, 2] < z-5e-3 and models.held(m, d) == []


def test_release_all_keeps_the_cord_attached():
    m, d = _start("slotted_post_ring_easy")
    models.toggle_hold(m, d, "target_ring")
    models.release_all(m, d)
    assert models.held(m, d) == [] and d.eq_active[[i for i in range(m.neq) if not m.equality(i).name]].all()


def test_a_selection_from_the_previous_model_is_ignored():
    m, _ = _start("horseshoe_ring_easy")
    assert view.selected_body(m, m.nbody+5) == ""
    assert view.selected_body(m, m.body("target_ring").id) == "target_ring"
