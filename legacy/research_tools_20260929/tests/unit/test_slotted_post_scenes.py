"""Frozen tiers preserve the puzzle's apertures, routing and FEM attachments."""
from dataclasses import asdict
import hashlib
import numpy as np
import pytest

from topogym.config.registry import task_definition
from topogym.assets.geometry.slotted_post_ring import SlottedPostLayout


@pytest.mark.parametrize('tier,diameter', [('easy', .108), ('medium', .105), ('hard', .102)])
def test_frozen_scene_geometry_and_reproducible_assets(tier, diameter, tmp_path):
    cls = task_definition('slotted_post_ring', tier)
    first, second = cls(seed=0), cls(seed=0)
    a, b = first.declare(tmp_path/'a', .9196429), second.declare(tmp_path/'b', .9196429)
    layout = first.layout
    assert 2*layout.ring_inner_radius == pytest.approx(diameter)
    report = a.metadata['geometry_report']
    assert report['passed'] and not report['physics_qualified'] and not report['solution_verified']
    assert not first.goal_complete
    assert len(a.attachments) == 2
    assert {e.name for e in a.entities if e.fixed} == {'base', 'post'}
    assert {e.name for e in a.entities if e.physics_model == 'fem_elastic'} == {'cord'}
    for path in (tmp_path/'a').iterdir():
        assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256((tmp_path/'b'/path.name).read_bytes()).digest(), path.name
    assert first.instance_id == second.instance_id
    # Conservative polygonal aperture bounds, not just ideal torus dimensions.
    inner_bound = layout.ring_inner_radius*np.cos(np.pi/128)
    assert inner_bound > np.hypot(layout.post_width_m, layout.post_depth_m)/2
    assert layout.disc_radius_m*np.cos(np.pi/128) > layout.ring_inner_radius
    assert layout.slot_width_m == .028
    # A ring can be lifted above the constant-section post once the cord route
    # permits it. This geometric relation alone is not a full extraction path.
    assert report['aperture_margins']['ring_post_radial_margin_m'] > .012


def test_tier_overrides_cannot_turn_into_clearance36_or_lose_end_retention():
    ids = set()
    for tier in ('easy', 'medium', 'hard'):
        cls = task_definition('slotted_post_ring', tier)
        ids.add(cls().instance_id)
        for change in ({'slot_width_m': .036}, {'ring_major_radius_m': .08}, {'disc_radius_m': .01}):
            with pytest.raises(ValueError, match='defines this setting'):
                cls({'geometry': change})
    assert len(ids) == 3
    assert task_definition('slotted_post_ring') is task_definition('slotted_post_ring', 'hard')
    assert SlottedPostLayout(**asdict(SlottedPostLayout())).validate()
