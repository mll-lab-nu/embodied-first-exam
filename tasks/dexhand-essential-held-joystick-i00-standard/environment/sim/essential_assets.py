"""Resolve task-owned offline object assets in authoring and frozen copies."""

from pathlib import Path


def asset_dir(spec):
    here = Path(__file__).resolve().parent
    authoring = here.parent / "task_library" / spec["id"] / "assets"
    if authoring.is_dir():
        return authoring
    return here / "object_assets" / spec["id"]


def asset_path(spec, filename):
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Object assets must use task-relative paths")
    path = asset_dir(spec) / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return str(path.resolve())
