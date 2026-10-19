#!/usr/bin/env python3
"""Embodied Safety Exam's large files: the binary textures and meshes of the realism_v3 asset pack (`.png`, `.obj`) that the
image's build context (images/ese/context/robosafe-src/robosafebench/assets/data/realism_v3/) holds. They are kept
out of git (images/ese/.gitignore) in the public Hugging Face dataset named in images/ese/assets.json (MLL-Lab/robosafe-assets), pinned
by commit and by the sha256 of every file; the pack's JSON metadata, credits and licences stay in git. Build the image
only after `fetch` (context/robosafe-src.sha256 lists these files too, and the Dockerfile checks every one).

usage:
  python3 images/ese/assets.py fetch [<dir>]       download the pinned revision into <dir> (default:
                                                         $RCB_ROBOSAFE_ASSETS or ~/.cache/robosafe-assets), check every
                                                         sha256 and copy the files into the build context
  python3 images/ese/assets.py stage <dir>         check an existing copy and copy it into the build context
  python3 images/ese/assets.py check [<dir>]       check a copy (default: the build context itself)
  python3 images/ese/assets.py pin <dir> <rev>     maintainers: write assets.json from a local copy of revision <rev>
  python3 images/ese/assets.py export <dir>        maintainers: copy the build context's pinned files into <dir>,
                                                         laid out as the dataset (realism_v3/...), to upload

Access: the dataset is public (CC0 1.0 / CC BY 4.0 assets, credits in its realism_v3/credits.json); no login needed. The
fetch uses huggingface_hub when it is installed and falls back to a standard-library download of each pinned file (its
public resolve URL at the pinned revision) when it is not or when its download fails; the other commands use the standard
library.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIN = HERE / "assets.json"
SUFFIXES = (".png", ".obj")


def file_sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load() -> dict:
    return json.loads(PIN.read_text())


def context(pin: dict) -> pathlib.Path:
    return ROOT / pin["context"]


def check(d: pathlib.Path, pin: dict) -> list[str]:
    bad = []
    for rel, want in sorted(pin["files"].items()):
        p = d / rel
        if not p.is_file():
            bad.append(f"{rel}: missing")
        elif file_sha(p) != want:
            bad.append(f"{rel}: sha256 differs from images/ese/assets.json")
    return bad


def stage(d: pathlib.Path, pin: dict) -> None:
    bad = check(d, pin)
    if bad:
        sys.exit("not staged:\n  " + "\n  ".join(bad[:20]))
    dst = context(pin)
    prefix = pin["prefix"]
    for rel in pin["files"]:
        out = dst / rel[len(prefix):]
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d / rel, out)
        os.chmod(out, 0o644)
    print(f"staged {len(pin['files'])} files into {dst.relative_to(ROOT)}")


def fetch_plain(d: pathlib.Path, pin: dict) -> None:
    """Standard-library download of every pinned file from the dataset's public resolve URLs, without content
    encoding (huggingface_hub 1.x through httpx can fail with a brotli DecodingError; seen 2026-10-17)."""
    import urllib.request
    base = f"https://huggingface.co/datasets/{pin['repo']}/resolve/{pin['revision']}/"
    for rel, want in sorted(pin["files"].items()):
        out = d / rel
        if out.is_file() and file_sha(out) == want:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(base + rel, headers={"Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=120) as r, (out.parent / (out.name + ".part")).open("wb") as f:
            shutil.copyfileobj(r, f)
        (out.parent / (out.name + ".part")).replace(out)


def fetch(d: pathlib.Path, pin: dict) -> None:
    if not pin.get("revision"):
        sys.exit("images/ese/assets.json has no revision yet (the dataset has not been pinned)")
    d.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=pin["repo"], repo_type="dataset", revision=pin["revision"], local_dir=str(d),
                          allow_patterns=[pin["prefix"] + "**", "README.md"])
    except Exception as e:  # noqa: BLE001  (no huggingface_hub, or its download failed: the plain one)
        print(f"huggingface_hub download unavailable or failed ({type(e).__name__}); downloading file by file",
              file=sys.stderr)
        try:
            fetch_plain(d, pin)
        except Exception as e2:  # noqa: BLE001
            sys.exit(f"download of {pin['repo']}@{pin['revision'][:12]} failed ({type(e2).__name__})")
    stage(d, pin)


def export(d: pathlib.Path, pin: dict) -> None:
    src = context(pin)
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix in SUFFIXES:
            out = d / pin["prefix"] / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, out)
            n += 1
    print(f"exported {n} files into {d}")


def pin_from(d: pathlib.Path, rev: str) -> dict:
    old = load()
    files = {p.relative_to(d).as_posix(): file_sha(p) for p in sorted((d / old["prefix"]).rglob("*"))
             if p.is_file() and p.suffix in SUFFIXES and ".cache" not in p.parts}
    return {**old, "revision": rev, "files": files}


def main() -> None:
    a = sys.argv[1:]
    default = pathlib.Path(os.environ.get("RCB_ROBOSAFE_ASSETS") or pathlib.Path.home() / ".cache" / "robosafe-assets")
    if not a or a[0] not in ("fetch", "stage", "check", "pin", "export"):
        sys.exit(__doc__)
    pin = load()
    if a[0] == "fetch":
        fetch(pathlib.Path(a[1]) if len(a) > 1 else default, pin)
    elif a[0] == "stage" and len(a) == 2:
        stage(pathlib.Path(a[1]), pin)
    elif a[0] == "check":
        if len(a) > 1:
            d = pathlib.Path(a[1])
        else:   # the build context: its files sit at the paths without the dataset's prefix
            d = context(pin).parent
            pin = {**pin, "files": {pin["context_name"] + rel[len(pin["prefix"]) - 1:]: s
                                    for rel, s in pin["files"].items()}}
        bad = check(d, pin)
        for b in bad[:40]:
            print("FAIL", b)
        if bad:
            sys.exit(1)
        print(f"ok {len(pin['files'])} files match images/ese/assets.json")
    elif a[0] == "pin" and len(a) == 3:
        PIN.write_text(json.dumps(pin_from(pathlib.Path(a[1]), a[2]), indent=1, sort_keys=True) + "\n")
        print(f"wrote {PIN.relative_to(ROOT)}")
    elif a[0] == "export" and len(a) == 2:
        export(pathlib.Path(a[1]), pin)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
