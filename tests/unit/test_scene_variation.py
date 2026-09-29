"""Seeded scene variation: seed -> (tier, pose/appearance draw), nominal tiers untouched."""
import pytest

from topogym.config.registry import TIER_ORDER, seeded_variation, task_definition, variation_catalog
from topogym.config.variation_records import RECORDS
from topogym.tasks.base import merge_parameters
from topogym.tasks.scene_variation import AXES, draw, within_envelope

TASKS = sorted({row["task_id"] for row in RECORDS})


def tier_classes(task_id):
    return [task_definition(task_id, r["variation_id"]) for r in variation_catalog(task_id) if r["pool"] == "tier"]


@pytest.mark.parametrize("task_id", TASKS)
def test_seed_picks_tier_by_modulo(task_id):
    for seed in range(9):
        assert seeded_variation(task_id, seed)["difficulty"] == TIER_ORDER[seed % 3]


def test_seeded_env_resolves_tier_without_building():
    from topogym.simulator.config import SimulatorConfig
    from topogym.simulator.env import Env
    assert Env(SimulatorConfig(task_id="horseshoe_ring", variation_id="seeded", seed=5))._task_class.difficulty == "hard"
    assert Env(SimulatorConfig(task_id="horseshoe_ring", variation_id="seeded"))._task_class is None
    assert Env(SimulatorConfig(task_id="horseshoe_ring", variation_id="easy", seed=5))._task_class.difficulty == "easy"


@pytest.mark.parametrize("task_id", sorted(AXES))
def test_draw_is_pure_in_envelope_and_constructible(task_id):
    for cls in tier_classes(task_id):
        draws = [draw(cls, seed) for seed in range(30)]
        assert draws == [draw(cls, seed) for seed in range(30)]
        assert len({repr(d) for d in draws}) > 1
        for seed, values in enumerate(draws):
            task = cls(values, seed=seed)  # no fixed-parameter or unknown-key violation
            assert within_envelope(cls, task.config)


def test_envelope_rejects_out_of_range_and_unlisted_changes():
    cls = task_definition("horseshoe_ring", "easy")
    x, y = cls.defaults["center_xy_m"]
    assert within_envelope(cls, cls.defaults)
    assert not within_envelope(cls, merge_parameters(cls.defaults, {"center_xy_m": [x+.2, y]}))
    assert not within_envelope(cls, merge_parameters(cls.defaults, {"target_ring_finish": "silver"}))
    assert not within_envelope(cls, merge_parameters(cls.defaults, {"scale": 2.5}))


def test_keyhole_nominal_keeps_strict_qualification():
    from topogym.tasks.cast_keyhole.qualification import placement_qualification
    for cls in tier_classes("cast_keyhole"):
        task = cls(seed=0)
        assert placement_qualification(task) is not None
        moved = cls({"center_xy_m": [cls.defaults["center_xy_m"][0]+.5, cls.defaults["center_xy_m"][1]]}, seed=0)
        assert placement_qualification(moved) is None


def _glb_factors(path):
    import json
    import struct
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    return {m.get("name"): m["pbrMetallicRoughness"]["baseColorFactor"]
            for m in json.loads(data[20:20+length])["materials"]}


def _declare(task_id, tier, overrides, folder):
    task = task_definition(task_id, tier)(overrides, seed=0)
    return task, task.declare(folder, .9196429)


def test_buzz_appearance_edits_visual_glb_only(tmp_path):
    _, nominal = _declare("buzz_wire_3d", "easy", {}, tmp_path/"a")
    _, varied = _declare("buzz_wire_3d", "easy", {"wood_tint": .8, "rail_rgb": [.78, .60, .25]}, tmp_path/"b")
    assert [(e.position_m, e.quaternion_wxyz) for e in nominal.entities] == \
        [(e.position_m, e.quaternion_wxyz) for e in varied.entities]
    for name in ("wire.urdf", "wand.urdf", "base.urdf"):
        assert (tmp_path/"a"/name).read_bytes() == (tmp_path/"b"/name).read_bytes()
    before, after = _glb_factors(tmp_path/"a"/"wire_visual.glb"), _glb_factors(tmp_path/"b"/"wire_visual.glb")
    assert after["wire_posts_wood"][:3] == pytest.approx([.8*v for v in before["wire_posts_wood"][:3]], abs=1e-6)
    assert after["wire_rail_metal"][:3] == pytest.approx([.78, .60, .25])


def test_coil_piece_tint_scales_one_piece(tmp_path):
    _declare("cast_coil", "easy", {}, tmp_path/"a")
    _declare("cast_coil", "easy", {"piece_tint": {"gold": .9, "silver": 1.}}, tmp_path/"b")
    gold = [_glb_factors(tmp_path/k/"coil_gold"/"coil_gold.glb")[None][:3] for k in "ab"]
    silver = [_glb_factors(tmp_path/k/"coil_silver"/"coil_silver.glb")[None] for k in "ab"]
    assert gold[1] == pytest.approx([.9*v for v in gold[0]], abs=1e-6) and silver[0] == silver[1]


def test_knot_pose_moves_and_turns_the_fem_rope(tmp_path):
    import numpy as np
    from scipy.spatial.transform import Rotation
    _, nominal = _declare("knot_untying", "easy", {}, tmp_path/"a")
    _, varied = _declare("knot_untying", "easy", {"origin_xy_m": [-.05, .03], "yaw_deg": 20.,
                                                  "rope_finish": "hemp"}, tmp_path/"b")
    (a,), (b,) = nominal.entities, varied.entities
    assert b.position_m[:2] == (-.05, .03) and a.position_m[:2] == (0, 0)
    with np.load(a.volume_path) as x, np.load(b.volume_path) as y:
        np.testing.assert_allclose(y["spawn"], Rotation.from_euler("z", 20, degrees=True).apply(x["spawn"]), atol=1e-12)
        np.testing.assert_array_equal(x["rest"], y["rest"])
    assert b.surface["color"] != a.surface["color"]
