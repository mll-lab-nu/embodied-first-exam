"""Behaviour checks for the design viewer (CPU only, no browser).

Run from the worktree root: python -m pytest scripts/design_viewer -q
The first run builds hedgehog easy (~25 s); later runs read the cache.
"""
import subprocess
import sys
import time

import mujoco
import numpy as np
import pytest
import trimesh

from scripts.design_viewer import mjcf, scenes
from topogym.config.registry import variation_catalog


def test_lists_every_integrated_variation():
    names = scenes.list_scenes()
    for task in scenes.TASKS:
        for row in variation_catalog(task):
            if row["status"] == "integrated":
                assert row["variation_id"] in names


def test_hedgehog_cage_stands_on_its_mount():
    scene = scenes.build("hedgehog_in_cage_medium")
    cage, ball = scene.body("cage"), scene.body("ball")
    assert not cage.free and ball.free
    bottom = (cage.visual.vertices+cage.pos)[:, 2].min()
    assert bottom == pytest.approx(scene.body("mount").visual.bounds[1, 2]+scene.body("mount").pos[2], abs=1e-6)
    assert scene.extras["cage_pos"] == pytest.approx(cage.pos)


def test_hedgehog_override_reaches_the_generator():
    base = scenes.build("hedgehog_in_cage_easy")
    wide = scenes.build("hedgehog_in_cage_easy", {"window_widths": 28})
    # Wider windows leave fewer closed wall segments between them.
    assert len(wide.body("cage").collision) < len(base.body("cage").collision)


def test_unknown_override_is_rejected():
    with pytest.raises(KeyError):
        scenes.build("hedgehog_in_cage_easy", {"no_such_key": 1})


def test_second_build_reads_the_cache():
    scenes.build("hedgehog_in_cage_easy")
    start = time.perf_counter()
    scenes.build("hedgehog_in_cage_easy")
    assert time.perf_counter()-start < 2


def test_cache_written_by_the_cli_loads_in_another_module():
    path = scenes.cache_path("horseshoe_ring_hard")
    path.unlink(missing_ok=True)
    subprocess.run([sys.executable, "-m", "scripts.design_viewer.scenes", "--scene", "horseshoe_ring_hard"],
                   check=True, cwd=scenes.ROOT, capture_output=True)
    assert path.exists()
    assert scenes.build("horseshoe_ring_hard").name == "horseshoe_ring_hard"


def test_horseshoe_bodies_and_chain():
    scene = scenes.build("horseshoe_ring_easy")
    free = sorted(b.name for b in scene.bodies if b.free)
    assert free == ["chain_lower_1", "chain_upper_1", "horseshoe_left", "horseshoe_right", "target_ring"]
    assert len(scene.extras["edges"]) == 4
    capsules = [c for c in scene.body("target_ring").collision if not isinstance(c, trimesh.Trimesh)]
    assert capsules and all(c[0] == "capsule" for c in capsules)


def test_slotted_post_pieces_are_convex_and_keep_the_slot_open():
    scene = scenes.build("slotted_post_ring_easy")
    layout = scene.extras["layout"]
    pieces = scene.body("post").collision
    assert all(p.is_convex for p in pieces)
    r = layout.slot_width_m/2
    y = np.linspace(-layout.post_depth_m/2+1e-3, layout.post_depth_m/2-1e-3, 5)
    # Straight sides: 0.3 mm inside the slot wall.
    z = np.linspace(layout.slot_bottom_m+r, layout.slot_top_m-r, 40)
    side = np.array([[s*(r-3e-4), yy, zz] for s in (-1, 1) for yy in y for zz in z])
    # Rounded ends: at most 1 mm of hull bulge into the slot.
    a = np.linspace(0, np.pi, 25)
    ends = np.array([[(r-1e-3)*np.cos(t), yy, c+s*(r-1e-3)*np.sin(t)]
                     for s, c in ((-1, layout.slot_bottom_m+r), (1, layout.slot_top_m-r)) for t in a for yy in y])
    for piece in pieces:
        assert not piece.contains(np.vstack([side, ends])).any()
    assert scene.extras["cord"].shape[1] == 3


# --- mjcf.py ---------------------------------------------------------------

def _model(name, gripper=False):
    model = mjcf.build(scenes.build(name), gripper=gripper)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def _run(model, data, seconds):
    for _ in range(int(seconds/model.opt.timestep)):
        mujoco.mj_step(model, data)


def _pair_contacts(model, data, body_a, prefix_b):
    a = model.body(body_a).id
    count = 0
    for c in data.contact[:data.ncon]:
        bodies = {model.geom_bodyid[c.geom1], model.geom_bodyid[c.geom2]}
        if a in bodies and any(model.body(b).name.startswith(prefix_b) for b in bodies - {a}):
            count += 1
    return count


# Hedgehog start poses are collision-free only ("gravity_settled": False): the ball tips onto
# its spikes. Horseshoe starts from settled rest poses.
@pytest.mark.parametrize("name, settled", [("hedgehog_in_cage_easy", False), ("hedgehog_in_cage_medium", False),
                                           ("horseshoe_ring_easy", True)])
def test_scene_starts_without_penetration(name, settled):
    model, data = _model(name)
    assert mjcf.penetration(model, data) < 5e-4
    start = data.xpos.copy()
    _run(model, data, .5)
    assert np.isfinite(data.qpos).all()
    if settled:
        assert np.linalg.norm(data.xpos-start, axis=1).max() < 2e-3


def test_pin_holds_a_body_against_gravity():
    model, data = _model("hedgehog_in_cage_medium")
    ball = model.body("ball").id
    data.qpos[model.joint("ball_free").qposadr[0]+2] += .01  # lift clear of the floor
    mujoco.mj_forward(model, data)
    z = data.xpos[ball, 2]
    mjcf.hold(model, data, "ball", "pin")
    _run(model, data, .5)
    assert abs(data.xpos[ball, 2]-z) < 5e-4
    mjcf.release(model, data)
    _run(model, data, .3)
    assert data.xpos[ball, 2] < z-5e-3


def test_grip_moves_the_body_with_the_gripper_and_ignores_finger_contacts():
    model, data = _model("hedgehog_in_cage_medium", gripper=True)
    ball = model.body("ball").id
    # Ball in free air beside the cage, pinch point on its core: the fingers overlap it.
    data.qpos[model.joint("ball_free").qposadr[0]:][:3] = [.4, 0, .3]
    mujoco.mj_forward(model, data)
    mjcf.place_gripper(model, data, data.xpos[ball], azimuth_deg=0, standoff=0)
    assert _pair_contacts(model, data, "ball", "g_") > 0
    mjcf.hold(model, data, "ball", "grip")
    mujoco.mj_forward(model, data)
    assert _pair_contacts(model, data, "ball", "g_") == 0
    wrist = model.body("wrist").id

    def offset():  # ball position in the wrist frame; the pair may turn as one body
        return data.xmat[wrist].reshape(3, 3).T@(data.xpos[ball]-data.xpos[wrist])
    start = offset()
    data.qvel[model.joint("wrist_free").dofadr[0]+2] = .1  # move up
    _run(model, data, .3)
    assert data.xpos[ball, 2] > .3+5e-3
    assert np.linalg.norm(offset()-start) < 1e-3
    mjcf.release(model, data)
    mujoco.mj_forward(model, data)
    assert _pair_contacts(model, data, "ball", "g_") > 0


def test_mouse_perturbation_drives_the_gripper_and_it_stops_on_release():
    model, data = _model("hedgehog_in_cage_easy", gripper=True)
    base = model.body("g_base").id
    # Same calls as the browser: select on a rendered scene, then spring force toward the drag target.
    pert, camera, scene = mujoco.MjvPerturb(), mujoco.MjvCamera(), mujoco.MjvScene(model, 20000)
    mujoco.mjv_defaultFreeCamera(model, camera)
    mujoco.mjv_updateScene(model, data, mujoco.MjvOption(), None, camera, mujoco.mjtCatBit.mjCAT_ALL, scene)
    pert.select, pert.active = base, mujoco.mjtPertBit.mjPERT_TRANSLATE | mujoco.mjtPertBit.mjPERT_ROTATE
    mujoco.mjv_initPerturb(model, data, scene, pert)
    start = data.xpos[base].copy()
    pert.refpos[:] = start+[0, 0, .05]
    pert.refselpos[:] = pert.refpos
    turn = np.array([np.cos(np.pi/8), 0, 0, np.sin(np.pi/8)])  # 45 deg about world z
    mujoco.mju_mulQuat(pert.refquat, turn, data.xquat[base].copy())
    for _ in range(int(1./model.opt.timestep)):
        data.xfrc_applied[:] = 0
        mujoco.mjv_applyPerturbForce(model, data, pert)
        mujoco.mj_step(model, data)
    assert data.xpos[base, 2]-start[2] > .04
    err = np.zeros(3)
    mujoco.mju_subQuat(err, pert.refquat, data.xquat[base])
    assert np.degrees(np.linalg.norm(err)) < 15
    data.xfrc_applied[:] = 0
    _run(model, data, .3)
    moving = data.xpos[base].copy()
    _run(model, data, .5)
    assert np.linalg.norm(data.xpos[base]-moving) < 2e-3


def test_slotted_cord_settles_through_the_slot_once():
    model, data = _model("slotted_post_ring_easy")
    layout = scenes.build("slotted_post_ring_easy").extras["layout"]
    _run(model, data, 1.)
    assert np.isfinite(data.qpos).all()
    pts = mjcf.cord_points(model, data)
    crossing = np.flatnonzero(pts[:-1, 1]*pts[1:, 1] < 0)
    xs = [pts[i, 0]+(pts[i+1, 0]-pts[i, 0])*(-pts[i, 1])/(pts[i+1, 1]-pts[i, 1]) for i in crossing]
    assert sum(abs(x) < layout.slot_width_m/2 for x in xs) == 1
    assert sum(x > layout.post_width_m/2 for x in xs) == 1
