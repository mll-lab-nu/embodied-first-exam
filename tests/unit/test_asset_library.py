"""Packaged asset identity, tamper detection, output boundaries and primitive-only builds."""

import hashlib
import json
import pytest
import topogym.assets.library as library


def test_every_catalog_resource_is_present_and_valid():
    catalog = json.loads((library.RESOURCE_ROOT / "catalog.json").read_text())
    assert catalog["resources"]
    for identity in catalog["resources"]:
        assert library.resource_path(identity).is_file()
    with pytest.raises(ValueError):
        library.resource_path("unknown/resource")


def test_catalog_rejects_tampering_and_path_escape(tmp_path, monkeypatch):
    root = tmp_path / "resources"
    root.mkdir()
    data = root / "mesh.obj"
    data.write_text("mesh")
    outside = tmp_path / "outside.obj"
    outside.write_text("outside")
    records = {
        "ok": {
            "path": "mesh.obj",
            "sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        },
        "escape": {
            "path": "../outside.obj",
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        },
    }
    (root / "catalog.json").write_text(json.dumps({"resources": records}))
    monkeypatch.setattr(library, "RESOURCE_ROOT", root)
    assert library.resource_path("ok") == data
    data.write_text("modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        library.resource_path("ok")
    with pytest.raises(FileNotFoundError):
        library.resource_path("escape")


def test_generated_build_records_files_but_does_not_require_a_mesh(tmp_path):
    assert not library.describe_build("primitive", tmp_path / "empty", {}, 1).files
    target = tmp_path / "assets"
    target.mkdir()
    (target / "mesh.obj").write_text("mesh")
    build = library.describe_build("fixture", target, {"size": 1}, 2)
    assert build.files == {"mesh.obj": "mesh.obj"} and build.seed == 2
    assert build.sha256["mesh.obj"] == hashlib.sha256(b"mesh").hexdigest()
    external = tmp_path / "other.obj"
    external.write_text("external")
    (target / "external.obj").symlink_to(external)
    with pytest.raises(ValueError, match="escape"):
        library.describe_build("fixture", target, {}, 2)
