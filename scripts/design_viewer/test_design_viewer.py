"""Behaviour checks for the design viewer (CPU only, no browser).

Run from the worktree root: python -m pytest scripts/design_viewer -q
The first run builds hedgehog easy (~25 s); later runs read the cache.
"""
import time

import numpy as np
import pytest
import trimesh

from scripts.design_viewer import scenes
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
