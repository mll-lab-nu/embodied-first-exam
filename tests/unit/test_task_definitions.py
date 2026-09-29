"""Asset declarations and task semantics without constructing a physics scene."""

import numpy as np
import pytest

from topogym.config.registry import task_definition, task_catalog


@pytest.mark.parametrize("task_id", [r["task_id"] for r in task_catalog()])
def test_declarations_have_unique_entities_and_owned_assets(task_id, tmp_path):
    task = task_definition(task_id)(seed=0)
    spec = task.declare(tmp_path / task_id, 0.9196429)
    assert spec.entities and len({e.name for e in spec.entities}) == len(spec.entities)
    for entity in spec.entities:
        assert entity.physics_model in {"rigid", "pbd_cloth", "fem_elastic"}
        assert np.isfinite(entity.position_m).all()
        assert np.linalg.norm(entity.quaternion_wxyz) == pytest.approx(1.0)
        if entity.asset_path:
            from pathlib import Path

            assert Path(entity.asset_path).is_file()
        if entity.physics_model == "fem_elastic":
            assert entity.volume_path is not None
            with np.load(entity.volume_path, allow_pickle=False) as volume:
                rest, spawn, elements = (volume[k] for k in ("rest", "spawn", "elements"))
                assert rest.shape == spawn.shape and elements.shape[1] == 4
                for vertices in (rest, spawn):
                    corners = vertices[elements]
                    assert np.all(np.linalg.det(corners[:, 1:]-corners[:, :1]) > 0)
                assert np.array_equal(volume["material_s_m"], rest[:, 0])
        if "diffuse_texture_path" in entity.surface:
            from pathlib import Path
            from PIL import Image
            from topogym.assets.library import describe_build

            texture = Path(entity.surface["diffuse_texture_path"])
            assert (
                texture.is_file() and texture.parent == Path(entity.asset_path).parent
            )
            assert (
                "color" not in entity.surface
                and "diffuse_texture" not in entity.surface
            )
            with Image.open(texture) as image:
                pixels = np.asarray(image)
                assert image.mode == "RGB" and pixels.dtype == np.uint8
                assert np.any(pixels != pixels[0, 0]), (
                    "A solid image would lose the cloth pattern"
                )
            # The mesh must carry UVs and the texture must be in the asset manifest.
            assert "\nvt " in Path(entity.asset_path).read_text()
            build = describe_build(task_id, texture.parent, task.config, task.seed)
            assert texture.name in build.sha256
    if task_id == "blanket_flatten":
        assert any("diffuse_texture_path" in e.surface for e in spec.entities)
    names = {e.name for e in spec.entities}
    for attachment in spec.attachments:
        assert attachment.soft_entity in names and attachment.rigid_entity in names
        assert attachment.endpoint in {"start", "end"} and attachment.band_length_m > 0
    if task_id in {"orbits", "slotted_post_ring"}:
        assert len(spec.attachments) == 2
    assert not hasattr(task, "scene")


def test_task_rejects_unknown_configuration():
    with pytest.raises(ValueError):
        task_definition("cast_coil")({"old_adapter_config": {}})
