#!/usr/bin/env python3
"""Files-only images: files that many task dirs would each carry a copy of live once, in a small pinned image built from
their one source directory in this repository; a task's Dockerfile takes them with `COPY --from=<image@digest>`, so the
task's container gets the same file at the same path (contents, mode, and the content-derived mtime every deployed task
file gets from scripts/stamp_mtimes.py).

images/<name>/FILES.json describes one such image:
  {"image": "<registry ref>:<VERSION>@sha256:<digest>",     the pinned image every task names
   "source": "<repo-relative directory>",                     the files' one source (the build context)
   "files": {"<file in source>": "<sha256>", ...}}            what the image carries, at /<file>
images/<name>/Dockerfile is `FROM scratch` plus one COPY of those files to /; images/<name>/BUILD_CONTEXT points at the
source (scripts/build_images.sh), images/<name>/VERSION is the tag.

    python3 scripts/files_image.py check [name ...]       the sources still hash to FILES.json (no docker; generators call it)
    python3 scripts/files_image.py build <name>           build <image>:<VERSION> from a stamped copy of the files (docker)
    python3 scripts/files_image.py pin <name> <digest>    after the push: put the digest and the files' hashes in FILES.json
    python3 scripts/files_image.py verify-image <name>    the pinned image carries exactly FILES.json's files (docker)

A change to a source file therefore needs a new image version (build, push, pin) before the generators render it; the
generators' check modes fail until then.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = {".dockerenv", "etc/hostname", "etc/hosts", "etc/resolv.conf"}   # what docker adds to every container


def spec(name: str) -> dict:
    return json.loads((ROOT / "images" / name / "FILES.json").read_text())


def image(name: str) -> str:
    return spec(name)["image"]


def copy_line(name: str, file: str, dest: str) -> str:
    """The Dockerfile line that puts the image's /<file> at <dest> (a file path)."""
    s = spec(name)
    if file not in s["files"]:
        raise KeyError(f"images/{name}/FILES.json has no {file}")
    return f"COPY --from={s['image']} /{file} {dest}"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check(name: str) -> list[str]:
    s = spec(name)
    src = ROOT / s["source"]
    bad = [f"{s['source']}/{f}: sha256 {sha256(src / f) if (src / f).is_file() else 'missing'} != images/{name}/FILES.json"
           for f, h in sorted(s["files"].items()) if not (src / f).is_file() or sha256(src / f) != h]
    if bad:
        bad.append(f"-> a changed file needs a new images/{name} version: scripts/files_image.py build / docker push / pin")
    return bad


def build(name: str) -> str:
    sys.path.insert(0, str(ROOT / "scripts"))
    import stamp_mtimes
    s = spec(name)
    tag = s["image"].split("@")[0].rsplit(":", 1)[0] + ":" + (ROOT / "images" / name / "VERSION").read_text().strip()
    with tempfile.TemporaryDirectory(dir="/data/kangrui/tmp" if Path("/data/kangrui/tmp").is_dir() else None) as td:
        for f in s["files"]:
            (Path(td) / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / s["source"] / f, Path(td) / f)
            (Path(td) / f).chmod(0o644)
        stamp_mtimes.stamp_tree(td, True)
        subprocess.run(["docker", "build", "--no-cache", "-q", "-t", tag, "-f", str(ROOT / "images" / name / "Dockerfile"), td],
                       check=True)
    return tag


def pin(name: str, digest: str) -> None:
    p = ROOT / "images" / name / "FILES.json"
    s = json.loads(p.read_text())
    ver = (ROOT / "images" / name / "VERSION").read_text().strip()
    s["image"] = s["image"].split("@")[0].rsplit(":", 1)[0] + f":{ver}@{digest}"
    s["files"] = {f: sha256(ROOT / s["source"] / f) for f in sorted(s["files"])}
    p.write_text(json.dumps(s, indent=1) + "\n")


def verify_image(name: str) -> list[str]:
    s = spec(name)
    cid = subprocess.run(["docker", "create", s["image"], "/none"], capture_output=True, text=True, check=True).stdout.strip()
    try:
        tar = subprocess.run(["docker", "export", cid], capture_output=True, check=True).stdout
    finally:
        subprocess.run(["docker", "rm", cid], capture_output=True)
    got = {}
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            if m.isfile() and m.name.removeprefix("./").lstrip("/") not in RUNTIME_FILES and not m.name.removeprefix("./").lstrip("/").startswith("dev/"):
                got[m.name.removeprefix("./").lstrip("/")] = hashlib.sha256(t.extractfile(m).read()).hexdigest()
    want = s["files"]
    return [f"/{f}: image {got.get(f)} != FILES.json {want.get(f)}" for f in sorted(set(got) | set(want))
            if got.get(f) != want.get(f)]


def main(argv: list[str]) -> int:
    cmd, args = (argv[0], argv[1:]) if argv else ("check", [])
    if cmd == "check":
        names = args or sorted(p.parent.name for p in (ROOT / "images").glob("*/FILES.json"))
        bad = [e for n in names for e in check(n)]
        print("\n".join(bad) or f"ok files images: {', '.join(names)} match their sources")
        return 1 if bad else 0
    if cmd == "build":
        print(build(args[0]))
        return 0
    if cmd == "pin":
        pin(args[0], args[1])
        print(image(args[0]))
        return 0
    if cmd == "verify-image":
        bad = verify_image(args[0])
        print("\n".join(bad) or f"ok {image(args[0])}: {len(spec(args[0])['files'])} files match FILES.json")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
