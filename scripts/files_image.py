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

    python3 scripts/files_image.py check [name ...]       the sources still hash to FILES.json (no docker)
    python3 scripts/files_image.py build <name>           stage context/ (stamped copy of the files) and build <image>:<VERSION>
    python3 scripts/files_image.py pin <name> <digest>    after the push: check the pushed image, then pin it in FILES.json
    python3 scripts/files_image.py verify-image <name>    the pinned image carries exactly FILES.json's files and modes

CI checks that read a task's files see a build context as its image holds it: copied() gives the sources of the files its
Dockerfile copies from a pinned files-only image; copied_from() also returns the COPY --from lines of a files-only image it
cannot resolve (a check reports them).

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


PACKAGES = ("ghcr.io/mll-lab-nu/efe", "ghcr.io/mll-lab-nu/efe-private")   # one public, one private package: <name>-<version> tags


def _repo(ref: str) -> str:
    """What names the image in a reference (no version, no digest): its repository, or for the efe / efe-private
    packages (tags <name>-<version>) the package and <name>."""
    name = ref.split("@", 1)[0]
    repo, tag = name.rsplit(":", 1) if ":" in name.rsplit("/", 1)[-1] else (name, "")
    if repo in PACKAGES and tag:
        m = re.match(r"^(.*?)-(\d+\.\d+.*|latest)$", tag)
        return f"{repo}:{m.group(1) if m else tag}"
    return repo


def _versioned(image: str, ver: str) -> str:
    """The image's reference at another version (no digest)."""
    r = _repo(image)
    return f"{r}-{ver}" if r.split(":", 1)[0] in PACKAGES and ":" in r.rsplit("/", 1)[-1] else f"{r}:{ver}"


def copied_from(dockerfile: Path) -> tuple[dict[str, Path], list[str]]:
    """({container path: source file in this repository}, problems) of the Dockerfile's COPY --from lines that name a
    files-only image (a repository of images/*/FILES.json, or any *-files repository). A line resolves when it names the
    pinned image@digest, carries no other flag, and copies one file or one directory of the image (`/<dir>/`: every file
    of FILES.json under it, to <dest>/<path below it>), or several files into one directory (`/<a> /<b> <dir>/`: each
    keeps its basename); anything else is a problem, never silently skipped."""
    if not dockerfile.is_file():
        return {}, []
    specs = {p.parent.name: spec(p.parent.name) for p in sorted((ROOT / "images").glob("*/FILES.json"))}
    by_repo = {_repo(s["image"]): n for n, s in specs.items()}
    out: dict[str, Path] = {}
    bad: list[str] = []
    text = re.sub(r"\\\n", " ", dockerfile.read_text(errors="replace"))      # line continuations
    for line in text.splitlines():
        words = line.split()
        if len(words) < 2 or words[0].upper() != "COPY" or not any(w.startswith("--from=") for w in words[1:]):
            continue
        flags = [w for w in words[1:] if w.startswith("--")]
        args = [w for w in words[1:] if not w.startswith("--")]
        ref = next(w for w in flags if w.startswith("--from="))[len("--from="):]
        name = by_repo.get(_repo(ref))
        if name is None:
            if _repo(ref).endswith("-files"):
                bad.append(f"{dockerfile}: {line.strip()}: a files-only image without images/*/FILES.json")
            continue                                                  # another stage or image (e.g. the monitor's)
        s = specs[name]
        if ref != s["image"]:
            bad.append(f"{dockerfile}: {line.strip()}: not the pinned {s['image']} (images/{name}/FILES.json)")
            continue
        if len(flags) != 1 or len(args) < 2 or not all(a.startswith("/") for a in args) \
                or (len(args) > 2 and not args[-1].endswith("/")):
            bad.append(f"{dockerfile}: {line.strip()}: a files-only image line is `COPY --from=<image> /<file or dir> /<dest>` "
                       "or `COPY --from=<image> /<file>... /<dest dir>/`")
            continue
        dest = args[-1]
        for a in args[:-1]:
            src = a.strip("/")
            if src in s["files"]:
                out[dest + src.rsplit("/", 1)[-1] if dest.endswith("/") else dest] = ROOT / s["source"] / src
                continue
            if len(args) > 2:
                bad.append(f"{dockerfile}: {line.strip()}: images/{name}/FILES.json has no file /{src}")
                continue
            under = sorted(f for f in s["files"] if not src or f.startswith(src + "/"))
            if not under:
                bad.append(f"{dockerfile}: {line.strip()}: images/{name}/FILES.json has no /{src}")
            for f in under:
                out[dest.rstrip("/") + "/" + f[len(src):].lstrip("/")] = ROOT / s["source"] / f
    return out, bad


def copied(dockerfile: Path) -> dict[str, Path]:
    """{container path: its source in this repository} of every file a Dockerfile takes from a files-only image: what a
    check that reads a build context's files reads for those. copied_from() also returns the lines it cannot resolve."""
    return copied_from(dockerfile)[0]




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
    tag = _versioned(s["image"], (ROOT / "images" / name / "VERSION").read_text().strip())
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
    ref = _versioned(s["image"], ver) + f"@{digest}"
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
