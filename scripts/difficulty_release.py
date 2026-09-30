#!/usr/bin/env python3
"""Source inventories and release bundles; no simulator, credentials or Git required."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("topogym", "assets/robots", "configs", "requirements", "images", "scripts",
           "bash_scripts", "harbor_templates", "harbor_agents", "ci_checks")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_files(root):
    files = {}
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*")):
            rel = path.relative_to(root)
            if (not path.is_file() or "__pycache__" in rel.parts or path.suffix in (".pyc", ".log")
                    or any(p.startswith(".env") or p == ".secrets" for p in rel.parts)):
                continue
            if path.is_symlink():
                raise ValueError(f"source requires real files: {rel}")
            files[rel.as_posix()] = sha(path)
    files[".dockerignore"] = sha(root / ".dockerignore")
    return files


def runtime_files(files):
    # Matches the simulator build inputs, independent of experiment scripts/seeds.
    omitted = {"agents", "planning", "data", "deferred", "legacy", "redundants", "rollout_simulation"}
    return {p: h for p, h in files.items() if (
        (p.startswith("topogym/") and not set(Path(p).parts) & omitted and not p.endswith(".md"))
        or p.startswith("assets/robots/") or p.startswith("images/topogym/")
        or p in (".dockerignore", "scripts/prepare_nyx_studio.py", "requirements/uv-topogym-gs121.txt",
                 "requirements/uv-topogym-gs121-nyx.txt", "requirements/difficulty-eval-runtime.lock"))}


def build_info(root, bootstrap_sha=""):
    files = source_files(root)
    identity = digest(files)
    result = dict(schema_version=1, release_id=identity, bootstrap_sha=bootstrap_sha,
                  source_sha256=identity, files=files, runtime_inputs_sha256=digest(runtime_files(files)),
                  harbor_version="0.23.0", harbor_patch_sha256=files.get("images/difficulty-eval/patch_harbor.py"),
                  codex_version="0.157.0", platform="linux/amd64")
    (root / "build-info.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def load_build_info(root):
    path = root / "build-info.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or digest(data["files"]) != data["source_sha256"]:
        raise ValueError("invalid release build-info")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-info")
    build.add_argument("--bootstrap-sha", default="")
    bundle = sub.add_parser("bundle", help="create a Docker-only source distribution; no images are pushed")
    bundle.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-info":
        print(json.dumps({k: v for k, v in build_info(ROOT, args.bootstrap_sha).items() if k != "files"}))
    else:
        files = source_files(ROOT)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves earlier release artifacts.
        with args.output.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for name in sorted(files):
                archive.add(ROOT / name, arcname="topogym/" + name, recursive=False)
            for name in ("docker_quickstart_zh.md", "difficulty_sweep_delivery_plan_zh.md"):
                archive.add(ROOT / "docs/rcb" / name, arcname="topogym/docs/rcb/" + name)
            import io
            readme = ('# TopoGym Docker evaluation\n\nRun `bash run_difficulty_trials.sh --help`.\n\n'
                      'See [Docker quickstart](docs/rcb/docker_quickstart_zh.md).\n').encode()
            entry = tarfile.TarInfo("topogym/README.md"); entry.size = len(readme); entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(readme))
            archive.add(ROOT / "bash_scripts/run_difficulty_trials.sh", arcname="topogym/run_difficulty_trials.sh")
        print(f"{args.output}: sha256={sha(args.output)}; source={digest(files)}")


if __name__ == "__main__":
    main()
