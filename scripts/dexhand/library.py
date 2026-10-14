#!/usr/bin/env python3
"""Inspect the independently owned DexHand task folders before generation."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
LIBRARY = HERE / "task_library"
sys.path.insert(0, str(HERE / "shared"))
from checker import Checker  # noqa: E402

ASSET_SUFFIXES = {".obj", ".stl", ".msh", ".ply", ".png", ".jpg", ".jpeg", ".mtl", ".txt", ".json", ".xml", ".hdr", ".exr"}


def inspect():
    entries = json.loads((LIBRARY / "index.json").read_text())["tasks"]
    ids = [entry["id"] for entry in entries]
    modules = [entry["module"] for entry in entries]
    if len(set(ids)) != len(ids) or len(set(modules)) != len(modules):
        raise ValueError("Task IDs and scene module names must be unique")
    records = []
    for entry in entries:
        family = entry["id"]
        if not re.fullmatch(r"essential_[a-z0-9_]+", family) or not entry["module"].isidentifier():
            raise ValueError(f"Invalid task registration: {entry}")
        if not isinstance(entry["free_objects"], bool):
            raise ValueError(f"free_objects must be a boolean: {family}")
        folder = LIBRARY / family
        for filename in ("task.json", "scene.py", "render.json", "README.md", "assets/manifest.json"):
            if not (folder / filename).is_file():
                raise ValueError(f"Missing task-owned file: {family}/{filename}")
        spec = json.loads((folder / "task.json").read_text())
        if spec["id"] != family:
            raise ValueError(f"Task ID differs from its folder: {family}")
        Checker(spec)
        manifest = json.loads((folder / "assets/manifest.json").read_text())
        if manifest.get("schema_version") != 1:
            raise ValueError(f"Unsupported asset manifest: {family}")
        runtime_files = manifest.get("runtime_files", [])
        if len(set(runtime_files)) != len(runtime_files):
            raise ValueError(f"Duplicate runtime asset: {family}")
        declared_hashes = manifest.get("files_sha256", manifest.get("sha256", {}))
        if set(declared_hashes) != set(runtime_files):
            raise ValueError(f"Asset checksums must cover exactly the runtime inventory: {family}")
        files = {}
        for filename in runtime_files:
            relative = Path(filename)
            if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in ASSET_SUFFIXES:
                raise ValueError(f"Only offline object assets and credits can be packaged: {family}/{filename}")
            path = folder / "assets" / relative
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"Missing or linked asset: {path}")
            files[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
            if files[filename] != declared_hashes[filename]:
                raise ValueError(f"Asset checksum differs from its manifest: {family}/{filename}")
        records.append({"id": family, "module": entry["module"], "folder": str(folder),
                        "runtime_asset_count": len(files), "runtime_asset_sha256": files})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        records = inspect()
    except (OSError, KeyError, ValueError) as error:
        print(f"FAIL task library: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"tasks": records}, indent=2))
    else:
        for record in records:
            print(f"{record['id']}: {record['runtime_asset_count']} offline assets")
        print(f"Task library: {len(records)} independently owned folders verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
