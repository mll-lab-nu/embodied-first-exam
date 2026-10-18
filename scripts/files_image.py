#!/usr/bin/env python3
"""Files-only images: files that many task dirs would each carry a copy of live once, in a small pinned image built from
their one source directory in this repository; a task's Dockerfile takes them with `COPY --from=<image@digest>`, so the
task's container gets the same file at the same path (contents, mode, and the content-derived mtime every deployed task
file gets from scripts/stamp_mtimes.py).

images/<name>/FILES.json describes one such image:
  {"image": "<registry ref>:<VERSION>@sha256:<digest>",     the pinned image every task names
   "source": "<repo-relative directory>",                     the files' one source
   "files": {"<file in source>": "<sha256>", ...}}            what the image carries, at /<file>
images/<name>/Dockerfile is `FROM scratch` + `COPY . /`; its build context is images/<name>/context/ (BUILD_CONTEXT;
gitignored), staged by `build` (scripts/build_images.sh skips the image while it is missing). An image a benchmark keeps
private carries images/<name>/BUILD_ONLY (PROTOCOL §1), and hosts pull it with the organization's token.

    python3 scripts/files_image.py check [name ...]       the sources still hash to FILES.json (no docker; generators call it)
    python3 scripts/files_image.py build <name>           stage context/ (stamped copy of the files) and build <image>:<VERSION>
    python3 scripts/files_image.py pin <name> <digest>    after the push: check the pushed image, then pin it in FILES.json
    python3 scripts/files_image.py verify-image <name>    the pinned image carries exactly FILES.json's files and modes

A change to a source file needs a new image version (VERSION, build, push, pin) before the generators render it; their
check modes fail until then.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = {".dockerenv", "etc/hostname", "etc/hosts", "etc/resolv.conf", "etc/mtab"}   # what docker adds to every container


def spec(name: str) -> dict:
    p = ROOT / "images" / name / "FILES.json"
    if not p.is_file():
        raise SystemExit(f"images/{name}/FILES.json: no such files-only image")
    return json.loads(p.read_text())


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


def _mode(p: Path) -> int:
    """The mode a checkout gives a file (git keeps only the executable bit; checkouts are made with umask 022)."""
    return 0o755 if p.stat().st_mode & stat.S_IXUSR else 0o644


def check(name: str) -> list[str]:
    s = spec(name)
    src = ROOT / s["source"]
    bad = [f"{s['source']}/{f}: sha256 {sha256(src / f) if (src / f).is_file() else 'missing'} != images/{name}/FILES.json"
           for f, h in sorted(s["files"].items()) if not (src / f).is_file() or sha256(src / f) != h]
    if bad:
        bad.append(f"-> a changed file needs a new images/{name} version: scripts/files_image.py build / docker push / pin")
    return bad


def stage(name: str) -> Path:
    """images/<name>/context/: the files, each with its checkout mode and its content-derived mtime."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import stamp_mtimes
    s = spec(name)
    ctx = ROOT / "images" / name / "context"
    shutil.rmtree(ctx, ignore_errors=True)
    for f in s["files"]:
        (ctx / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / s["source"] / f, ctx / f)
        (ctx / f).chmod(_mode(ROOT / s["source"] / f))
    stamp_mtimes.stamp_tree(str(ctx), True)
    return ctx


def build(name: str) -> str:
    s = spec(name)
    tag = s["image"].split("@")[0].rsplit(":", 1)[0] + ":" + (ROOT / "images" / name / "VERSION").read_text().strip()
    ctx = stage(name)
    subprocess.run(["docker", "build", "--no-cache", "-q", "-t", tag, "-f", str(ROOT / "images" / name / "Dockerfile"),
                    str(ctx)], check=True)
    return tag


def image_files(ref: str) -> dict[str, tuple[str, int]]:
    """{path: (sha256, mode)} of the regular files in an image (docker export, streamed); links and other members are
    reported as such so that a check sees them."""
    cid = subprocess.run(["docker", "create", ref, "/none"], capture_output=True, text=True, check=True).stdout.strip()
    got: dict[str, tuple[str, int]] = {}
    try:
        p = subprocess.Popen(["docker", "export", cid], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=p.stdout, mode="r|") as t:
            for m in t:
                name = m.name.removeprefix("./").lstrip("/")
                if name in RUNTIME_FILES or name.startswith(("dev/", "proc/", "sys/")) or m.isdir():
                    continue
                if m.isfile():
                    got[name] = (hashlib.sha256(t.extractfile(m).read()).hexdigest(), m.mode & 0o7777)
                else:
                    got[name] = ("not a regular file", m.mode & 0o7777)
        p.wait()
    finally:
        subprocess.run(["docker", "rm", cid], capture_output=True)
    return got


def verify(name: str, ref: str, files: dict | None = None) -> list[str]:
    """Problems with the files <ref> carries against FILES.json's (or the given) {file: sha256} and the sources' modes."""
    s = spec(name)
    src = ROOT / s["source"]
    got = image_files(ref)
    want = {f: (h, _mode(src / f) if (src / f).is_file() else None) for f, h in (files or s["files"]).items()}
    return [f"/{f}: image {got.get(f)} != FILES.json {want.get(f)}" for f in sorted(set(got) | set(want))
            if got.get(f) != want.get(f)]


def pin(name: str, digest: str) -> None:
    """Pin the pushed <image>:<VERSION>@<digest> in FILES.json, with the sources' hashes, once the image is checked to
    carry exactly those files."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise SystemExit(f"pin: {digest!r} is not a digest (sha256:<64 hex>, the part after @ of the pushed RepoDigest)")
    p = ROOT / "images" / name / "FILES.json"
    s = json.loads(p.read_text())
    ver = (ROOT / "images" / name / "VERSION").read_text().strip()
    ref = s["image"].split("@")[0].rsplit(":", 1)[0] + f":{ver}@{digest}"
    files = {f: sha256(ROOT / s["source"] / f) for f in sorted(s["files"])}
    bad = verify(name, ref, files)
    if bad:
        raise SystemExit("pin: the pushed image does not carry the sources' files:\n" + "\n".join(bad))
    p.write_text(json.dumps(dict(s, image=ref, files=files), indent=1) + "\n")


def main(argv: list[str]) -> int:
    cmd, args = (argv[0], argv[1:]) if argv else ("check", [])
    need = {"build": 1, "pin": 2, "verify-image": 1}
    if cmd in need and len(args) != need[cmd]:
        print(__doc__)
        return 2
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
        bad = verify(args[0], image(args[0]))
        print("\n".join(bad) or f"ok {image(args[0])}: {len(spec(args[0])['files'])} files match FILES.json")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
