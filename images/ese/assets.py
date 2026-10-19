#!/usr/bin/env python3
"""Embodied Safety Exam's large files, kept out of git (images/ese/.gitignore) in Hugging Face datasets, pinned in
images/ese/assets.json by commit and by the sha256 of every file. One entry ("pack") per dataset folder:
  realism_v3       the realism_v3 asset pack's binary textures and meshes (`.png`, `.obj`) under
                   context/ese-src/embodied_safety_exam/assets/data/realism_v3/, from MLL-Lab/robosafe-assets (public;
                   CC0 1.0 / CC BY 4.0 assets, credits in its realism_v3/credits.json)
  third_party      the vendored third-party G1 meshes and GR00T whole-body-control weights (`.STL`, `.onnx`) under
                   context/ese-src/assets/third_party/bigym2/, from the embodied-safety-exam/ folder of the dataset
                   named in assets.json (their LICENSE / NOTICE files stay in git next to them)
The packs' JSON metadata, credits and licences stay in git. Build the image only after `fetch`
(context/ese-src.sha256 lists these files too, and the Dockerfile checks every one).

usage:
  python3 images/ese/assets.py fetch [<dir>]       download the pinned revisions into <dir> (default:
                                                         $RCB_ESE_ASSETS or ~/.cache/robosafe-assets), check every
                                                         sha256 and copy the files into the build context
  python3 images/ese/assets.py stage <dir>         check an existing copy and copy it into the build context
  python3 images/ese/assets.py check [<dir>]       check a copy (default: the build context itself)
  python3 images/ese/assets.py pin <pack> <dir> <rev>   maintainers: write a pack's pins from a local copy of
                                                         revision <rev>
  python3 images/ese/assets.py export <dir>        maintainers: copy the build context's pinned files into <dir>,
                                                         laid out as the datasets (<prefix>...), to upload

Access: a pack whose "private" is false downloads without a login. A private one needs read access to its dataset:
the token comes from $HF_TOKEN or `hf auth login` (never printed). The fetch uses huggingface_hub when it is installed
and falls back to a standard-library download of each pinned file (its resolve URL at the pinned revision) when it is
not or when its download fails; the other commands use the standard library.
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


def file_sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load() -> list[dict]:
    return json.loads(PIN.read_text())["packs"]


def context(pin: dict) -> pathlib.Path:
    return ROOT / pin["context"]


def token(pin: dict) -> str | None:
    """The token for a private pack ($HF_TOKEN, else `hf auth login`'s); None for a public one."""
    if not pin.get("private"):
        return None
    t = os.environ.get("HF_TOKEN")
    if t:
        return t.strip()
    try:
        from huggingface_hub import get_token
        return get_token()
    except ImportError:
        p = pathlib.Path(os.environ.get("HF_HOME", pathlib.Path.home() / ".cache" / "huggingface")) / "token"
        return p.read_text().strip() if p.is_file() else None


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
        sys.exit(f"{pin['name']}: not staged:\n  " + "\n  ".join(bad[:20]))
    dst = context(pin)
    prefix = pin["prefix"]
    for rel in pin["files"]:
        out = dst / rel[len(prefix):]
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d / rel, out)
        os.chmod(out, 0o644)
    print(f"staged {len(pin['files'])} files into {dst.relative_to(ROOT)}")


def fetch_plain(d: pathlib.Path, pin: dict) -> None:
    """Standard-library download of every pinned file from the dataset's resolve URLs, without content encoding
    (huggingface_hub 1.x through httpx can fail with a brotli DecodingError; seen 2026-10-17)."""
    import urllib.parse
    import urllib.request
    base = f"https://huggingface.co/datasets/{pin['repo']}/resolve/{pin['revision']}/"
    headers = {"Accept-Encoding": "identity"}
    tok = token(pin)
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    for rel, want in sorted(pin["files"].items()):
        out = d / rel
        if out.is_file() and file_sha(out) == want:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(base + urllib.parse.quote(rel), headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r, (out.parent / (out.name + ".part")).open("wb") as f:
            shutil.copyfileobj(r, f)
        (out.parent / (out.name + ".part")).replace(out)


def fetch(d: pathlib.Path, pin: dict) -> None:
    if not pin.get("revision"):
        sys.exit(f"images/ese/assets.json: pack {pin['name']} has no revision yet (the dataset has not been pinned)")
    d.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=pin["repo"], repo_type="dataset", revision=pin["revision"], local_dir=str(d),
                          allow_patterns=[pin["prefix"] + "**"], token=token(pin) or False)
        if check(d, pin):
            raise ValueError("incomplete download")
    except Exception as e:  # noqa: BLE001  (no huggingface_hub, or its download failed: the plain one)
        print(f"{pin['name']}: huggingface_hub download unavailable or failed ({type(e).__name__}); downloading file by "
              "file", file=sys.stderr)
        try:
            fetch_plain(d, pin)
        except Exception as e2:  # noqa: BLE001
            hint = " (a private dataset: $HF_TOKEN or `hf auth login` with read access)" if pin.get("private") else ""
            sys.exit(f"download of {pin['repo']}@{pin['revision'][:12]} failed ({type(e2).__name__}){hint}")
    stage(d, pin)


def export(d: pathlib.Path, pin: dict) -> None:
    src = context(pin)
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix in pin["suffixes"]:
            out = d / pin["prefix"] / p.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, out)
            n += 1
    print(f"{pin['name']}: exported {n} files into {d}")


def pin_from(pin: dict, d: pathlib.Path, rev: str) -> dict:
    files = {p.relative_to(d).as_posix(): file_sha(p) for p in sorted((d / pin["prefix"]).rglob("*"))
             if p.is_file() and p.suffix in pin["suffixes"] and ".cache" not in p.parts}
    return {**pin, "revision": rev, "files": files}


def main() -> None:
    a = sys.argv[1:]
    default = pathlib.Path(os.environ.get("RCB_ESE_ASSETS") or pathlib.Path.home() / ".cache" / "robosafe-assets")
    if not a or a[0] not in ("fetch", "stage", "check", "pin", "export"):
        sys.exit(__doc__)
    packs = load()
    if a[0] == "fetch":
        for pin in packs:
            fetch((pathlib.Path(a[1]) if len(a) > 1 else default) / pin["repo"].replace("/", "--"), pin)
    elif a[0] == "stage" and len(a) == 2:
        for pin in packs:
            stage(pathlib.Path(a[1]) / pin["repo"].replace("/", "--"), pin)
    elif a[0] == "check":
        bad, n = [], 0
        for pin in packs:
            if len(a) > 1:
                d = pathlib.Path(a[1]) / pin["repo"].replace("/", "--")
            else:   # the build context: its files sit at the paths without the dataset's prefix
                d = context(pin).parent
                pin = {**pin, "files": {pin["context_name"] + rel[len(pin["prefix"]) - 1:]: s
                                        for rel, s in pin["files"].items()}}
            bad += [f"{pin['name']}: {b}" for b in check(d, pin)]
            n += len(pin["files"])
        for b in bad[:40]:
            print("FAIL", b)
        if bad:
            sys.exit(1)
        print(f"ok {n} files match images/ese/assets.json")
    elif a[0] == "pin" and len(a) == 4:
        new = [pin_from(p, pathlib.Path(a[2]), a[3]) if p["name"] == a[1] else p for p in packs]
        if new == packs and not any(p["name"] == a[1] for p in packs):
            sys.exit(f"no pack {a[1]!r} in images/ese/assets.json")
        PIN.write_text(json.dumps({"packs": new}, indent=1, sort_keys=True) + "\n")
        print(f"wrote {PIN.relative_to(ROOT)}")
    elif a[0] == "export" and len(a) == 2:
        for pin in packs:
            export(pathlib.Path(a[1]), pin)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
