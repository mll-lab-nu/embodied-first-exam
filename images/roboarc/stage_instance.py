#!/usr/bin/env python3
"""Stage one RoboARC task's frozen instance from the image into a task directory, and check it against the task's
runtime binding. Standard library only.

usage: python /opt/robotangle/stage_instance.py <base> <dest> [--binding <runtime_binding.json>] [--purge]

The image (images/roboarc/Dockerfile) carries every task's frozen instance, instance.json + instance_assets/, under
/opt/robotangle/instances/<base>/. The files come from the private RoboARC asset dataset (organization members only)
at the revision pinned in images/roboarc/assets.json, and the image build checks each file's sha256 there. A task
directory holds only runtime_binding.json, which names the instance's canonical sha256 and the sha256 of every asset.
This script:
  - copies the instance into <dest>, next to <dest>/runtime_binding.json (--binding copies that file there first);
  - checks both against the binding, by the rule of topogym.simulator.frozen_binding.check_inputs, which every session
    applies again at start;
  - with --purge, removes /opt/robotangle/instances afterwards, so a task image keeps only its own instance.
Privileged tasks run it in environment/Dockerfile and tests/Dockerfile. Standard tasks run it in the sim service's
entrypoint, before `sh /srv/run.sh`, and RCB_INSTANCE points into <dest>.
"""
import hashlib
import json
import os
import pathlib
import shutil
import sys

SRC = pathlib.Path("/opt/robotangle/instances")


def file_sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    purge = "--purge" in argv
    argv = [a for a in argv if a != "--purge"]
    binding = None
    if "--binding" in argv:
        i = argv.index("--binding")
        binding = pathlib.Path(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    base, dest = argv[0], pathlib.Path(argv[1])
    src = SRC / base
    if not (src / "instance.json").is_file():
        print(f"FAIL stage_instance: no frozen instance for {base} in this image ({src})", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    if binding is not None:
        shutil.copyfile(binding, dest / "runtime_binding.json")
    lock = json.loads((dest / "runtime_binding.json").read_text())
    shutil.copyfile(src / "instance.json", dest / "instance.json")
    if (dest / "instance_assets").exists():
        shutil.rmtree(dest / "instance_assets")
    shutil.copytree(src / "instance_assets", dest / "instance_assets", symlinks=True)
    bad = []
    inst = json.loads((dest / "instance.json").read_text())
    canon = hashlib.sha256(json.dumps(inst, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if canon != lock["instance_sha256"]:
        bad.append(f"instance.json {canon[:12]} is not the bound instance {lock['instance_sha256'][:12]}")
    assets = {}
    for p in sorted((dest / "instance_assets").rglob("*")):
        if "__pycache__" in p.parts:
            continue
        if p.is_symlink():
            bad.append(f"symlink in the instance assets: {p}")
        elif p.is_file():
            assets["instance_assets/" + p.relative_to(dest / "instance_assets").as_posix()] = file_sha(p)
    if assets != lock["asset_files"]:
        diff = sorted(set(assets.items()) ^ set(lock["asset_files"].items()))
        bad.append(f"instance_assets differ from the binding ({len(diff)} entries, e.g. {diff[:2]})")
    for p in [dest / "instance.json", *(dest / "instance_assets").rglob("*")]:
        os.chmod(p, 0o755 if p.is_dir() else 0o644)
    for b in bad:
        print(f"FAIL stage_instance {base}: {b}", file=sys.stderr)
    if bad:
        return 1
    if purge:
        shutil.rmtree(SRC)
    print(f"ok stage_instance {base}: instance {canon[:12]}, {len(assets)} asset files -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
