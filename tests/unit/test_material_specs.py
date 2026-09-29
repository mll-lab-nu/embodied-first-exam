"""Physical materials remain separate from renderer surfaces and reject invalid constants."""

import pytest
from topogym.assets.materials import MaterialSpec, rope_fem_parameters


def test_new_rope_recipe_has_distinct_scene_identity(monkeypatch):
    from topogym.config.registry import variation_catalog, task_definition
    suffix = '_fem_soft50_fine_v1'
    for family in ('rope_threading', 'knot_untying', 'orbits', 'slotted_post_ring'):
        for row in variation_catalog(family):
            if row['status'] != 'integrated':
                continue
            cls = task_definition(family, row['variation_id'])
            assert cls.model_revision == row['model_revision']
            assert cls.model_revision.endswith(suffix)
            current = cls(seed=7).instance_id
            with monkeypatch.context() as patch:
                patch.setattr(cls, 'model_revision', cls.model_revision[:-len(suffix)])
                assert cls(seed=7).instance_id != current


@pytest.mark.parametrize(
    "model,params",
    [
        ("unknown", {}),
        ("fem_elastic", {"E": 0}),
        ("fem_elastic", {"rho": -1}),
        ("fem_elastic", {"nu": 0.5}),
        ("rigid", {"friction": float("nan")}),
        ("pbd_cloth", {"stretch_compliance": -1}),
    ],
)
def test_invalid_materials(model, params):
    with pytest.raises(ValueError):
        MaterialSpec(model, params)


def test_explicit_fem_parameters_are_declarations_not_runtime_capabilities():
    spec = MaterialSpec("fem_elastic", rope_fem_parameters())
    assert spec.parameters["E"] > 0 and spec.parameters["rho"] > 0
    from topogym.world.physics.ipc import require_episode_checkpoint

    with pytest.raises(RuntimeError, match="CUDA"):
        require_episode_checkpoint("cpu")
