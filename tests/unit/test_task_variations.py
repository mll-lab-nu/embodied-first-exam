"""Canonical Task selection, aliases, explicit placeholders and instance identity."""

import pytest
from topogym.config.registry import task_catalog, task_definition
from topogym.config.registry import (
    available_variations, resolve_variation, variation_catalog, variation_registration, TaskSupportError,
)


def test_base_works_for_every_task_without_changing_identity():
    for record in task_catalog():
        task_id = record["task_id"]
        assert "base" in available_variations(task_id)
        values = resolve_variation(task_id, "base", {}, 7)
        assert task_definition(task_id)(values, seed=7).task_id == task_id


def test_variations_merge_overrides_and_do_not_mutate_defaults():
    overrides = {"geometry": {"rope_radius_m": 0.004}}
    params = resolve_variation("knot_untying", "hard", overrides, 4)
    assert params["geometry"]["planar_scale_m"] == .0325
    assert params["geometry"]["rope_radius_m"] == 0.004
    params["geometry"]["planar_scale_m"] = .026
    assert (
        resolve_variation("knot_untying", "hard", {}, 4)["geometry"][
            "planar_scale_m"
        ]
        == .0325
    )
    assert overrides == {"geometry": {"rope_radius_m": 0.004}}
    assert resolve_variation("blanket_flatten", "three_folds", {}, 1)["fold_count"] == 3
    with pytest.raises(ValueError, match="no migrated"):
        resolve_variation("cast_keyhole", "unmigrated_legacy_run", {}, 1)


def test_all_tiers_have_modules_and_aliases_are_unique():
    from importlib import import_module
    from topogym.tasks.base import UnavailableTaskDefinition
    for task in task_catalog():
        rows = variation_catalog(task["task_id"])
        assert {r["difficulty"] for r in rows if r["difficulty"]} == {"easy", "medium", "hard"}
        names = []
        for row in rows:
            names.extend([row["variation_id"], *row["aliases"]])
            module, cls = row["implementation"].split(":")
            definition = getattr(import_module(module), cls)
            assert definition.variation_id == row["variation_id"]
            if row["status"] != "integrated":
                assert row["variation_id"] not in available_variations(task["task_id"])
                # A blocked tier may have a concrete constructor while its
                # initial-state resources are still being qualified.
                if issubclass(definition, UnavailableTaskDefinition):
                    with pytest.raises(NotImplementedError, match=row["variation_id"]):
                        definition()
                with pytest.raises(TaskSupportError, match="unavailable"):
                    task_definition(task["task_id"], row["variation_id"])
        assert len(names) == len(set(names)), names


def test_aliases_share_physical_identity_but_distinct_claw_geometry_does_not():
    ids = []
    for tier in ("easy", "medium", "hard"):
        cls = task_definition("interlocked_claws", tier)
        assert cls is task_definition("interlocked_claws", f"interlocked_claws_{tier}")
        ids.append(cls(seed=7).instance_id)
    assert len(set(ids)) == 3
    assert task_definition("cast_coil") is task_definition("cast_coil", "easy")
    # The old unscaled figure-eight alias must not silently select the scaled tier.
    with pytest.raises(ValueError, match="no migrated"):
        task_definition("knot_untying", "figure_eight")


def test_archived_settings_are_unavailable_and_defaults_use_selected_tiers():
    import json
    from pathlib import Path
    # Keep the selection contract independent of historical source archives.
    fixture = json.loads((Path(__file__).resolve().parents[1] /
                          "fixtures/retired_variations.json").read_text())
    for row in fixture["retired_variations"]:
        for name in row["names"]:
            assert name not in available_variations(row["task_id"])
            with pytest.raises(ValueError, match="no migrated"):
                task_definition(row["task_id"], name)
    for task_id, target in fixture["base_redirects"].items():
        assert task_definition(task_id) is task_definition(task_id, "easy")
        assert variation_registration(task_id, "base")["variation_id"] == target
    # Orbits preserves the existing base alias while its new tiers are qualified.
    assert variation_registration("orbits", "base")["variation_id"] == "orbits_reference85"
    assert task_definition("orbits", "easy").defaults["geometry"]["ring_count"] == 2
    from topogym.tasks.task_variations.knot_untying import VARIATIONS
    assert VARIATIONS["hard"]["geometry"]["planar_scale_m"] == .0325
    assert "figure_eight" not in VARIATIONS and "left_overhand" not in VARIATIONS


def test_setting_dimensions_cannot_silently_change_difficulty():
    with pytest.raises(ValueError, match="defines this setting"):
        task_definition("fiber_bundling", "hard")({"geometry": {"fiber_count": 4}})
    with pytest.raises(ValueError, match="defines this setting"):
        task_definition("buzz_wire_3d", "easy")({"linear_scale": .6})
    cfg = task_definition("knot_untying", "hard")({"geometry": {"rope_radius_m": .003}}).config
    assert cfg["geometry"]["planar_scale_m"] == .0325
    assert cfg["geometry"]["crossing_height_m"] == .010


@pytest.mark.parametrize('tier,count', [('easy', 2), ('medium', 3), ('hard', 4)])
def test_orbits_ring_count_is_fixed_and_qualification_is_not_inherited(tier, count):
    cls = task_definition('orbits', tier)
    task = cls(seed=0)
    assert task.config['geometry'].get('ring_count', 4) == count
    assert task.config['cord_profile'] == 'compact_external_handle_v1'
    assert task.config['linear_scale'] == .85
    assert not task.goal_complete
    with pytest.raises(ValueError, match='defines this setting'):
        cls({'geometry': {'ring_count': 3 if count == 2 else 2}})


def test_simulator_selects_concrete_class_and_refuses_placeholder_before_build():
    from topogym import make, env_list
    env = make("cast_keyhole", variation_id="hard", enable_rgb=False)
    try:
        assert env._task_class is task_definition("cast_keyhole", "hard")
        assert env.support_report()["variation"]["family_id"] == "turnback"
    finally:
        env.close()
    with pytest.raises(TaskSupportError):
        make("blanket_flatten", variation_id="blanket_flatten_corner_cross_twist")
    details = {row["task_id"]: row for row in env_list(details=True)}
    assert len(details) == 13
    assert details["orbits"]["base_variation"] == "orbits_reference85"
    assert all(r["status"] == "integrated" for r in details["orbits"]["variation_details"])
