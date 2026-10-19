"""Omit exact asset duplicates from a build context; restore before installation.

Both installed trees retain their original paths and bytes. This tool does not
choose, fetch, or publish an asset host.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path("assets/third_party")
PACKAGE = Path("embodied_safety_exam/assets/data/third_party")


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Asset symlinks are not permitted: " + str(path))
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = {
                "sha256": sha(path), "bytes": path.stat().st_size}
    if not result:
        raise ValueError("Empty or missing asset tree: " + str(directory))
    return result


def stage(source, manifest):
    expected = inventory(source / ROOT)
    if inventory(source / PACKAGE) != expected:
        raise ValueError("Root and package asset trees differ; no files removed")
    value = {"schema": "ese.third-party-context/1", "root": ROOT.as_posix(),
             "package": PACKAGE.as_posix(), "files": expected,
             "duplicate_bytes_omitted": sum(x["bytes"] for x in expected.values())}
    # Seal first, and remove only the package duplicate in this disposable context.
    with manifest.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    shutil.rmtree(str(source / PACKAGE))


def restore(source, manifest):
    value = json.loads(manifest.read_text())
    if (value.get("schema"), value.get("root"), value.get("package")) != (
            "ese.third-party-context/1", ROOT.as_posix(), PACKAGE.as_posix()):
        raise ValueError("Unexpected asset manifest layout")
    for relative in value["files"]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
            raise ValueError("Unsafe asset path: " + relative)
    if inventory(source / ROOT) != value["files"]:
        raise ValueError("Root assets do not match the sealed original bytes")
    target = source / PACKAGE
    if target.exists():
        raise ValueError("Package duplicate must be absent before restoration")
    shutil.copytree(str(source / ROOT), str(target))
    if inventory(target) != value["files"]:
        raise ValueError("Restored package assets differ")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stage", "restore"))
    parser.add_argument("source_tree", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    {"stage": stage, "restore": restore}[args.operation](args.source_tree, args.manifest)
