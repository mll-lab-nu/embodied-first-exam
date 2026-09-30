"""Tier geometry and the explicit separation of layout from stable qualification."""
from copy import deepcopy

import numpy as np
import pytest

from topogym.config.registry import task_definition, variation_registration
from topogym.tasks.base import InitialStateSpec
from topogym.utils.io import sha256_file
from topogym.world.initial_state import save_numeric_archive, restore_declared_initial_state


def test_gathered_tiers_change_only_twist_and_keep_flat_material_birth(tmp_path):
    configs, births, targets = [], [], []
    uv = np.array([[x, y] for x in (-.3, 0., .3) for y in (-.24, 0., .24)])
    for tier, angle in (("easy", 0.), ("medium", 135.), ("hard", 270.)):
        cls = task_definition("blanket_flatten", tier)
        task = cls({"initialization_mode": "flat_for_preparation"}, seed=0)
        assert task.config["gathered_profile"]["twist_angle_deg"] == angle
        config = deepcopy(task.config)
        config["gathered_profile"].pop("twist_angle_deg")
        configs.append(config)
        spec = task.declare(tmp_path/tier, .9196429)
        assert spec.initial_state is None
        births.append(task.birth_vertices)
        assert np.ptp(task.birth_vertices[:, 2]) == 0.
        targets.append(task.preparation_target(uv))
        assert task.model_revision == variation_registration("blanket_flatten", tier)["model_revision"]
        with pytest.raises(ValueError, match="defines this setting"):
            cls({"gathered_profile": {"twist_angle_deg": angle+1}})
        with pytest.raises(ValueError, match="flat preparation"):
            cls({"initialization_mode": "authored"}).declare(tmp_path/"invalid", .9)
    assert configs[0] == configs[1] == configs[2]
    np.testing.assert_array_equal(births[0], births[1])
    np.testing.assert_array_equal(births[0], births[2])
    assert not np.allclose(targets[0], targets[1])
    assert not np.allclose(targets[1], targets[2])


def test_historical_settings_keep_their_family_and_parameters():
    five = task_definition("blanket_flatten", "five_folds")(seed=7)
    roll = task_definition("blanket_flatten", "fold_roll")(seed=7)
    assert five.family_id == "simple_folds" and five.config["fold_count"] == 5
    assert roll.family_id == "fold_roll" and roll.config["roll_fold_count"] == 5
    assert five.model_revision == roll.model_revision == "simulator_v1"


@pytest.mark.parametrize("tier", ("easy", "medium", "hard"))
def test_packaged_representative_matches_default_scene_identity(tier, tmp_path):
    from topogym.assets.library import describe_build
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    from topogym.world.initial_state import read_archive_manifest, scene_identity
    config = SimulatorConfig(task_id="blanket_flatten", variation_id=tier, seed=0)
    task = task_definition("blanket_flatten", tier)(seed=0)
    scene = load_scene_config(config)
    table = scene.env.world.table
    spec = task.declare(tmp_path/tier, float(table.pos[2]+table.size[2]/2))
    assert spec.initial_state.acceptance == "scene_layout"
    metadata = read_archive_manifest(spec.initial_state.manifest_path,
        expected_sha256=spec.initial_state.sha256)["metadata"]
    build = describe_build(task.task_id, tmp_path/tier, task.config, 0)
    assert scene_identity(config, scene, task, spec, build) == metadata["identity"]
    assert metadata["identity"]["parameters"]["gathered_profile"]["twist_angle_deg"] == task.config["gathered_profile"]["twist_angle_deg"]
    with pytest.raises(ValueError, match="No frozen Blanket"):
        task_definition("blanket_flatten", tier)(seed=123456).declare(tmp_path/"unprepared", .9)


def layout_qualification():
    return dict(passed=False, scope="scene_layout", scene_layout_passed=True,
        binding={"passed": True}, preparation=dict(completed=False, scene_layout_completed=True,
            final_tick=100, release_tick=75, gravity_restored=True, rest_unchanged=True,
            binding_unchanged=True, position_writes=0, rest_writes=0, support_writes=0, pins_added=0,
            final_gates=dict(finite=True, all_on_table=True, no_table_penetration=True,
                material_intact=True, visual_intact=True, crumpled=True, landed=True,
                nonlocal_particle_clearance=True, settled=False)))


def test_layout_archive_needs_explicit_opt_in_and_never_claims_stability(tmp_path, monkeypatch):
    import topogym.world.physics.pbd_initial_state as codec
    qualification = layout_qualification()
    path = save_numeric_archive(tmp_path/"state", {}, {"qualification": qualification})
    monkeypatch.setattr(codec, "restore_initial_state", lambda *a, **kw: {"qualification": qualification})
    with pytest.raises(ValueError, match="released preparation qualification"):
        restore_declared_initial_state(None, None, InitialStateSpec(path, sha256_file(path)), identity={})
    result = restore_declared_initial_state(None, None,
        InitialStateSpec(path, sha256_file(path), acceptance="scene_layout"), identity={})
    assert result["qualification"]["passed"] is False
    assert result["qualification"]["preparation"]["final_gates"]["settled"] is False


@pytest.mark.parametrize("failure", ["material_intact", "visual_intact", "nonlocal_particle_clearance",
    "all_on_table", "missing_gate", "pin", "binding", "unreleased", "incomplete"])
def test_layout_acceptance_does_not_bypass_geometry_or_binding(tmp_path, failure):
    qualification = layout_qualification()
    preparation = qualification["preparation"]
    if failure in preparation["final_gates"]:
        preparation["final_gates"][failure] = False
    elif failure == "missing_gate":
        preparation["final_gates"].pop("finite")
    elif failure == "pin":
        preparation["pins_added"] = 1
    elif failure == "binding":
        preparation["binding_unchanged"] = False
    elif failure == "unreleased":
        preparation["final_tick"] = preparation["release_tick"]
    elif failure == "incomplete":
        preparation["scene_layout_completed"] = False
    path = save_numeric_archive(tmp_path/"state", {}, {"qualification": qualification})
    with pytest.raises(ValueError, match="scene-layout qualification"):
        restore_declared_initial_state(None, None,
            InitialStateSpec(path, sha256_file(path), acceptance="scene_layout"), identity={})
