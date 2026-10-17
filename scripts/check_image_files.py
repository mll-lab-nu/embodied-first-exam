#!/usr/bin/env python3
"""Check that an image built from a build context holds that context's files, byte for byte (issue #258).

    python3 scripts/check_image_files.py <image> <context dir> [--dockerfile F] [--json]

Defence in depth next to scripts/stamp_mtimes.py: BuildKit can put another build's same-name context file into an image
(see that script). A runner that builds a task image itself (a re-grade, a validation) calls this right after the build.
It reads the final stage's COPY / ADD lines of the Dockerfile (default <context>/Dockerfile; WORKDIR, globs, a
directory source, the JSON form; COPY --from and remote ADD sources are skipped), maps every context file they copy to
its path in the image, reads those paths out of a created (never started) container with `docker cp`, and compares
sha256. Exit 0: every copied file that is in the image matches; 1: a file differs (listed; a Dockerfile that edits a
copied file with RUN also lands here: read the list); 2: the check could not run. A copied file missing from the image
(removed by a later RUN, excluded by .dockerignore) is listed, not a failure. Standard library and the docker CLI.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tarfile
import uuid


def instructions(text: str) -> list[tuple[str, str]]:
    """(KEYWORD, rest) of every instruction, continuation lines joined, comments dropped"""
    out, cur = [], ""
    for line in text.splitlines():
        s = line.strip()
        if not cur and (not s or s.startswith("#")):
            continue
        if cur and s.startswith("#"):
            continue
        if s.endswith("\\"):
            cur += s[:-1] + " "
            continue
        cur += s
        kw, _, rest = cur.strip().partition(" ")
        out.append((kw.upper(), rest.strip()))
        cur = ""
    if cur.strip():
        kw, _, rest = cur.strip().partition(" ")
        out.append((kw.upper(), rest.strip()))
    return out


def copy_args(rest: str) -> tuple[list[str], list[str]] | None:
    """(sources, [dest]) of a COPY/ADD line; None for COPY --from / a heredoc"""
    if "<<" in rest:
        return None
    if rest.lstrip().startswith("["):
        try:
            parts = json.loads(rest)
        except ValueError:
            return None
        flags = []
    else:
        parts = shlex.split(rest)
        flags = [p for p in parts if p.startswith("--")]
        parts = [p for p in parts if not p.startswith("--")]
    if any(f.startswith("--from") for f in flags) or len(parts) < 2:
        return None
    return parts[:-1], [parts[-1]]


def expected(ctx: str, dockerfile: str) -> dict[str, str]:
    """image path -> context file (relative) for every file the final stage copies"""
    ins = instructions(open(dockerfile).read())
    last = max((i for i, (k, _) in enumerate(ins) if k == "FROM"), default=-1)
    workdir, out = "/", {}
    for kw, rest in ins[last + 1:]:
        if kw == "WORKDIR":
            workdir = posixpath.normpath(posixpath.join(workdir, rest.strip().strip('"')))
            continue
        if kw not in ("COPY", "ADD"):
            continue
        a = copy_args(rest)
        if a is None:
            continue
        srcs, (dest,) = a
        if kw == "ADD" and any(re.match(r"^[a-z]+://|^git@", s) for s in srcs):
            continue
        files = []
        for s in srcs:
            s = s.lstrip("/")
            hits = sorted(glob.glob(os.path.join(ctx, s))) if any(c in s for c in "*?[") else [os.path.join(ctx, s)]
            files += [h for h in hits if os.path.exists(h)]
        if not files:
            continue
        ddir = dest.endswith("/") or len(files) > 1 or os.path.isdir(files[0])
        droot = posixpath.normpath(posixpath.join(workdir, dest))
        for f in files:
            if kw == "ADD" and os.path.isfile(f) and re.search(r"\.(tar|tgz|tar\.(gz|bz2|xz|zst))$", f):
                continue                                   # ADD extracts a local archive
            if os.path.isdir(f):
                for dp, dns, fns in os.walk(f):
                    for fn in fns:
                        p = os.path.join(dp, fn)
                        if os.path.isfile(p) and not os.path.islink(p):
                            out[posixpath.join(droot, os.path.relpath(p, f).replace(os.sep, "/"))] = os.path.relpath(p, ctx)
            elif os.path.isfile(f) and not os.path.islink(f):
                out[posixpath.join(droot, os.path.basename(f)) if ddir else droot] = os.path.relpath(f, ctx)
    return out


def sha_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def image_file(docker: list[str], ctr: str, path: str) -> tuple[str, str | None]:
    """('file', sha) / ('dir', None) / ('missing', None) for one path of the container"""
    p = subprocess.run(docker + ["cp", f"{ctr}:{path}", "-"], capture_output=True)
    if p.returncode:
        return "missing", None
    with tarfile.open(fileobj=io.BytesIO(p.stdout), mode="r:") as tf:
        m = tf.next()
        if m is None:
            return "missing", None
        if m.isdir():
            return "dir", None
        if m.issym() or m.islnk():
            return "link", None
        return "file", hashlib.sha256(tf.extractfile(m).read()).hexdigest()


def check(image: str, ctx: str, dockerfile: str | None = None, docker: list[str] | None = None) -> dict:
    docker = docker or ["docker"]
    ctx = os.path.abspath(ctx)
    exp = expected(ctx, dockerfile or os.path.join(ctx, "Dockerfile"))
    ctr = f"rcb-imgcheck-{uuid.uuid4().hex[:12]}"
    c = subprocess.run(docker + ["create", "--name", ctr, image, "/rcb-imgcheck-never-run"], capture_output=True, text=True)
    if c.returncode:
        raise RuntimeError(f"docker create {image}: {(c.stderr or c.stdout).strip()[-300:]}")
    res = {"image": image, "context": ctx, "compared": 0, "mismatch": [], "missing": []}
    try:
        for ipath, rel in sorted(exp.items()):
            kind, h = image_file(docker, ctr, ipath)
            if kind == "dir":                              # COPY file dest-without-slash onto an existing directory
                ipath = posixpath.join(ipath, posixpath.basename(rel))
                kind, h = image_file(docker, ctr, ipath)
            if kind != "file":
                res["missing"].append({"file": rel, "image_path": ipath, "found": kind})
                continue
            res["compared"] += 1
            want = sha_file(os.path.join(ctx, rel))
            if h != want:
                res["mismatch"].append({"file": rel, "image_path": ipath, "context_sha256": want, "image_sha256": h})
    finally:
        subprocess.run(docker + ["rm", "-f", ctr], capture_output=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("context")
    ap.add_argument("--dockerfile")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args()
    try:
        r = check(a.image, a.context, a.dockerfile, shlex.split(os.environ.get("DOCKER", "docker")))
    except (OSError, RuntimeError, ValueError) as e:
        print(f"check_image_files: could not check {a.image}: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=1))
    for m in r["mismatch"]:
        print(f"MISMATCH {m['file']} -> {m['image_path']}: the image's copy is not the context's file")
    for m in r["missing"]:
        print(f"not in image: {m['file']} -> {m['image_path']} ({m['found']})")
    print(f"check_image_files: {a.image}: {r['compared']} compared, {len(r['mismatch'])} mismatched, {len(r['missing'])} not in image")
    return 1 if r["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
