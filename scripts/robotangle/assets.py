#!/usr/bin/env python3
"""RoboTangle's large files: the private Hugging Face dataset eai-v2-internal/robotangle-assets, pinned by commit and
by the sha256 of every file in scripts/robotangle/assets.json. They are kept out of git (CONTRIBUTING: no files > 2 MB).

usage:
  python3 scripts/robotangle/assets.py fetch <dir>      download the pinned revision into <dir> and check every sha256
  python3 scripts/robotangle/assets.py check <dir>      check an existing copy only
  python3 scripts/robotangle/assets.py pin <dir> <rev>  maintainers: write assets.json from a local copy of revision <rev>

The dataset holds:
  instances/<base>/instance.json, instance_assets/**   the frozen instance of each task base. Task directories keep only
                                                       runtime_binding.json, which pins the same hashes; the image stages
                                                       the instance (images/robotangle/stage_instance.py)
  image/release-<commit9>.tar.gz                       git archive of the release commit (release.json), the paths the
                                                       image copies
  image/uipc-prebuilt/                                 the audited libuipc wheel and its uipc-build.json
Access: a member of eai-v2-internal, logged in with `hf auth login` or with HF_TOKEN in the environment. The token is
never printed. fetch needs huggingface_hub (pip install huggingface_hub); check and pin use the standard library only.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PIN = HERE / "assets.json"


def file_sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def canonical_sha(p: pathlib.Path) -> str:
    """topogym.simulator.frozen_binding.canonical_hash of a JSON file (what runtime_binding.json names)."""
    v = json.loads(p.read_text())
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def check(d: pathlib.Path, pin: dict) -> list[str]:
    bad = []
    for rel, want in sorted(pin["files"].items()):
        p = d / rel
        if not p.is_file():
            bad.append(f"{rel}: missing")
        elif file_sha(p) != want:
            bad.append(f"{rel}: sha256 differs from scripts/robotangle/assets.json")
    for base, rec in sorted(pin["instances"].items()):
        p = d / "instances" / base / "instance.json"
        if p.is_file() and canonical_sha(p) != rec["instance_sha256"]:
            bad.append(f"instances/{base}/instance.json: canonical sha256 differs")
    return bad


def fetch(d: pathlib.Path, pin: dict) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("fetch needs huggingface_hub: pip install huggingface_hub (then `hf auth login`)")
    d.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(repo_id=pin["repo"], repo_type="dataset", revision=pin["revision"], local_dir=str(d),
                          allow_patterns=["instances/**", "image/**", "SHA256SUMS", "README.md"])
    except Exception as e:  # noqa: BLE001  the message names the repository, never the token
        sys.exit(f"download of {pin['repo']}@{pin['revision'][:12]} failed ({type(e).__name__}): this needs read access "
                 "to the private dataset (a member of eai-v2-internal; `hf auth login` or HF_TOKEN)")


def pin_from(d: pathlib.Path, rev: str) -> dict:
    files = {p.relative_to(d).as_posix(): file_sha(p) for p in sorted(d.rglob("*"))
             if p.is_file() and p.relative_to(d).parts[0] in ("instances", "image") and ".cache" not in p.parts}
    inst = {p.parent.name: {"instance_sha256": canonical_sha(p)} for p in sorted((d / "instances").glob("*/instance.json"))}
    old = json.loads(PIN.read_text()) if PIN.is_file() else {}
    return {"repo": old.get("repo", "eai-v2-internal/robotangle-assets"), "repo_type": "dataset", "private": True,
            "revision": rev, "release_archive": next(k for k in files if k.startswith("image/release-")),
            "instances": inst, "files": files}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("fetch", "check", "pin"):
        print(__doc__, file=sys.stderr)
        return 2
    d = pathlib.Path(argv[1])
    if argv[0] == "pin":
        PIN.write_text(json.dumps(pin_from(d, argv[2]), indent=1, sort_keys=True) + "\n")
        print(f"wrote {PIN}")
        return 0
    pin = json.loads(PIN.read_text())
    if argv[0] == "fetch":
        fetch(d, pin)
    bad = check(d, pin)
    for b in bad:
        print("FAIL", b)
    if not bad:
        print(f"ok {pin['repo']}@{pin['revision'][:12]}: {len(pin['files'])} files match scripts/robotangle/assets.json ({d})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
