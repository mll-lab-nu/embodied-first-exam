#!/usr/bin/env python3
"""Files-only images: files that many task dirs would each carry a copy of live once, in a small pinned image built from
their one source directory in this repository; a task's Dockerfile takes them with `COPY --from=<image@digest>`, so the
task's container gets the same file at the same path (contents, mode, and the content-derived mtime every deployed task
file gets from scripts/stamp_mtimes.py).

images/<name>/FILES.json describes one such image:
  {"image": "<registry ref>:<VERSION>@sha256:<digest>",     the pinned image every task names
   "source": "<repo-relative directory>",                     the files' one source
   "files": {"<file in source>": "<sha256>", ...}}            what the image carries, at /<file>
A source too large for git lives in a Hugging Face dataset instead (FILES.json "hf": {"repo": "MLL-Lab/<dataset>",
"revision": "<commit>", "path": "<folder in the dataset>"}; "source" is then images/<name>/context/, not in git):
`fetch` downloads every file of "files" from <path>/<file> at that commit into the source directory and checks its
sha256 (build, digest and check fetch first). MLL-Lab/embodied-first-exam-public is public: no login. A private
dataset (MLL-Lab/embodied-first-exam) needs read access: the token comes from $HF_TOKEN or `hf auth login`.
The image is written directly from FILES.json and the sources (no Dockerfile, no docker build): one uncompressed layer
whose tar lists the parent directories and then the files in sorted order, owner 0:0, the checkout mode of each file
(0755 / 0644: git keeps only the executable bit), the content-derived mtime of scripts/stamp_mtimes.py (to the
nanosecond), directories at the fixed mtime 1000000000; the config holds only the platform and the layer's diff id, no
build time or history. So any checkout of the same sources builds the same bytes and the same digest as the pushed
image, and a user can build a private files-only image instead of pulling it. Its tag is
ghcr.io/mll-lab-nu/efe:<name>-<VERSION>, or efe-private:<name>-<VERSION> when images/<name>/BUILD_ONLY marks it private
(PROTOCOL §1: hosts pull it with the organization's token).

    python3 scripts/files_image.py fetch [name ...]       download the pinned files of the images whose source is a Hugging
                                                          Face dataset ("hf" in FILES.json) and check them
    python3 scripts/files_image.py check [name ...]       the sources still hash to FILES.json (no docker)
    python3 scripts/files_image.py digest [name ...]      the digest a build gives, against the pinned one (no docker)
    python3 scripts/files_image.py build <name> [--out F] build <tag>@<digest> and `docker load` it (--out: also write
                                                          the OCI archive to F); says whether it is the pinned image
    python3 scripts/files_image.py push <name> <user>     push the build to the registry under <tag>, byte for byte (the
                                                          token on stdin: gh auth token | ... push <name> <user>)
    python3 scripts/files_image.py pin <name> <digest>    after the push: check the pushed image, then pin it in FILES.json
    python3 scripts/files_image.py verify-image <name>    the pinned image carries exactly FILES.json's files and modes

A task's Dockerfile names the image by digest (`COPY --from=<tag>@sha256:<digest>`); so does a sidecar's own Dockerfile
(environment/sim/ or environment/scorer/, compose `build: context: sim`: the directory at /srv and the shared files at
their paths under /srv, where the directory's copies would have been). Docker's containerd image store
(the default of Docker Engine 29 and Docker Desktop: `docker info -f '{{.DriverStatus}}'` names
io.containerd.snapshotter.v1) resolves that reference to a loaded image with that digest, so a task builds from a local
`build` without the registry; the classic store (overlay2) knows digests only of pulled images and asks the registry.
`docker push` from the classic store would recompress the layer (another digest): push with `push`.

CI checks that read a task's files see a build context as its image holds it: copied() gives the sources of the files its
Dockerfile copies from a pinned files-only image; copied_from() also returns the COPY --from lines of a files-only image it
cannot resolve (a check reports them).

A change to a source file needs a new image version (VERSION, build, push, pin) before the generators render it; their
check modes fail until then.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
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


_FETCHED: set[str] = set()


def copied_from(dockerfile: Path) -> tuple[dict[str, Path], list[str]]:
    """({container path: source file in this repository}, problems) of the Dockerfile's COPY --from lines that name a
    files-only image (a repository of images/*/FILES.json, or any *-files repository). A line resolves when it names the
    pinned image@digest, carries no other flag, and copies one file or one directory of the image (`/<dir>/`: every file
    of FILES.json under it, to <dest>/<path below it>), or several files into one directory (`/<a> /<b> <dir>/`: each
    keeps its basename); anything else is a problem, never silently skipped. The sources of an image pinned to a Hugging
    Face dataset are fetched first (once per process)."""
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
        if s.get("hf") and ref == s["image"] and name not in _FETCHED:   # its sources come from a dataset: fetch them once
            fetch(name)
            _FETCHED.add(name)
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


def _hf_token() -> str | None:
    """The Hugging Face token for a private dataset: $HF_TOKEN, else the one `hf auth login` stored; never printed."""
    t = os.environ.get("HF_TOKEN")
    if t:
        return t.strip()
    try:
        from huggingface_hub import get_token
        return get_token()
    except ImportError:
        p = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "token"
        return p.read_text().strip() if p.is_file() else None


def fetch(name: str) -> int:
    """Download the files of an image whose source is a Hugging Face dataset at its pinned commit into the source
    directory (a file already there with the pinned sha256 is kept); the number downloaded. Each file is checked
    against FILES.json before it replaces anything."""
    s = spec(name)
    hf = s.get("hf")
    if not hf:
        return 0
    src = ROOT / s["source"]
    base = f"https://huggingface.co/datasets/{hf['repo']}/resolve/{hf['revision']}/{hf['path'].strip('/')}/"
    token, n = None, 0
    for f, want in sorted(s["files"].items()):
        out = src / f
        if out.is_file() and sha256(out) == want:
            continue
        if token is None:
            token = _hf_token() or ""
        headers = {"Accept-Encoding": "identity"}       # no content encoding: the bytes as stored
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(base + urllib.parse.quote(f), headers=headers),
                                        timeout=300) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            hint = (" (a private dataset: $HF_TOKEN or `hf auth login` with read access to it)"
                    if e.code in (401, 403, 404) else "")
            raise SystemExit(f"fetch {name}: {hf['repo']}@{hf['revision'][:12]} {hf['path']}/{f}: HTTP {e.code}{hint}")
        if hashlib.sha256(data).hexdigest() != want:
            raise SystemExit(f"fetch {name}: {hf['path']}/{f}: sha256 differs from images/{name}/FILES.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        tmp.write_bytes(data)
        tmp.chmod(0o644)
        tmp.replace(out)
        n += 1
    return n


def check(name: str) -> list[str]:
    s = spec(name)
    if s.get("hf"):
        fetch(name)
    src = ROOT / s["source"]
    bad = [f"{s['source']}/{f}: sha256 {sha256(src / f) if (src / f).is_file() else 'missing'} != images/{name}/FILES.json"
           for f, h in sorted(s["files"].items()) if not (src / f).is_file() or sha256(src / f) != h]
    if bad:
        bad.append(f"-> a changed file needs a new images/{name} version: scripts/files_image.py build / push / pin")
    return bad


DIR_MTIME = 1_000_000_000                     # the directories' fixed mtime (2001-09-09)
LAYER = "application/vnd.oci.image.layer.v1.tar"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"


def tag(name: str) -> str:
    """<package>:<name>-<VERSION>: efe-private when images/<name>/BUILD_ONLY marks the image private, else efe."""
    pkg = PACKAGES[1] if (ROOT / "images" / name / "BUILD_ONLY").exists() else PACKAGES[0]
    return f"{pkg}:{name}-{(ROOT / 'images' / name / 'VERSION').read_text().strip()}"


def _json(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":")).encode()


def _digest(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def oci(name: str) -> tuple[bytes, dict[str, bytes]]:
    """(manifest, {digest: blob}) of the image, from FILES.json's file list and the sources alone: the same bytes from
    any checkout of the same sources (see the module docstring). Refuses sources that no longer match FILES.json."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import stamp_mtimes
    bad = check(name)
    if bad:
        raise SystemExit("\n".join(bad))
    s = spec(name)
    src = ROOT / s["source"]
    files = sorted(s["files"])
    dirs = sorted({"/".join(f.split("/")[:i]) for f in files for i in range(1, f.count("/") + 1)})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as t:
        for d in dirs:
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = tarfile.DIRTYPE, 0o755, DIR_MTIME, 0, 0, "", ""
            t.addfile(ti)
        for f in files:
            data = (src / f).read_bytes()
            ns = stamp_mtimes.stamp_of(hashlib.sha256(data).digest())
            ti = tarfile.TarInfo(f)
            ti.size, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = len(data), _mode(src / f), ns // 10**9, 0, 0, "", ""
            ti.pax_headers = {"mtime": f"{ns // 10**9}.{ns % 10**9:09d}"}
            t.addfile(ti, io.BytesIO(data))
    layer = buf.getvalue()
    config = _json({"architecture": "amd64", "os": "linux", "config": {},
                    "rootfs": {"type": "layers", "diff_ids": [_digest(layer)]}})
    manifest = _json({"schemaVersion": 2, "mediaType": MANIFEST,
                      "config": {"mediaType": CONFIG, "digest": _digest(config), "size": len(config)},
                      "layers": [{"mediaType": LAYER, "digest": _digest(layer), "size": len(layer)}]})
    return manifest, {_digest(config): config, _digest(layer): layer}


def archive(name: str, out) -> str:
    """Write the image as an OCI image-layout archive (with docker's manifest.json, for `docker load`) to the binary
    file object out; the image's digest."""
    manifest, blobs = oci(name)
    d, ref = _digest(manifest), tag(name)
    m = json.loads(manifest)
    index = _json({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
                   "manifests": [{"mediaType": MANIFEST, "digest": d, "size": len(manifest),
                                  "annotations": {"io.containerd.image.name": ref,
                                                  "org.opencontainers.image.ref.name": ref.rsplit(":", 1)[1]}}]})
    legacy = _json([{"Config": "blobs/sha256/" + m["config"]["digest"][7:], "RepoTags": [ref],
                     "Layers": ["blobs/sha256/" + m["layers"][0]["digest"][7:]]}])
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as t:
        for n, b in [("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'), ("index.json", index), ("manifest.json", legacy),
                     ("blobs/sha256/" + d[7:], manifest)] + [("blobs/sha256/" + k[7:], v) for k, v in sorted(blobs.items())]:
            ti = tarfile.TarInfo(n)
            ti.size, ti.mode, ti.mtime = len(b), 0o644, DIR_MTIME
            t.addfile(ti, io.BytesIO(b))
    return d


def containerd_store() -> bool:
    out = subprocess.run(["docker", "info", "-f", "{{json .DriverStatus}}"], capture_output=True, text=True).stdout
    return "io.containerd.snapshotter" in out


def build(name: str, out: str | None = None) -> str:
    """Build the image, `docker load` it as <tag> and return <tag>@<digest> (and the archive at out, if given)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = out or os.path.join(tmp, "image.tar")
        with open(path, "wb") as f:
            d = archive(name, f)
        subprocess.run(["docker", "load", "-q", "-i", path], check=True, stdout=subprocess.DEVNULL)
    ref = f"{tag(name)}@{d}"
    pinned = image(name)
    if pinned == ref:
        print(f"{name}: the pinned image (FILES.json), built locally", file=sys.stderr)
    else:
        print(f"{name}: not the pinned {pinned} (another version or other sources, or a pin from before reproducible "
              "builds: pull that one)", file=sys.stderr)
    if not containerd_store():
        print("note: this Docker uses the classic image store, which resolves `COPY --from=<tag>@<digest>` only for a "
              "pulled image; with the containerd image store (Docker Engine 29's default; \"features\": "
              "{\"containerd-snapshotter\": true} in /etc/docker/daemon.json) the task builds use this local build",
              file=sys.stderr)
    return ref


def _registry(ref: str) -> tuple[str, str, str]:
    """(registry host, repository, tag) of a ghcr.io-style reference."""
    host, rest = ref.split("/", 1)
    repo, t = rest.rsplit(":", 1)
    return host, repo, t


def push(name: str, user: str, token: str) -> str:
    """Push the build, byte for byte, under <tag> (blobs first, then the manifest); its digest."""
    manifest, blobs = oci(name)
    host, repo, t = _registry(tag(name))
    basic = base64.b64encode(f"{user}:{token}".encode()).decode()
    rq = urllib.request.Request(f"https://{host}/token?scope=repository:{repo}:pull,push&service={host}",
                                headers={"Authorization": f"Basic {basic}"})
    with urllib.request.urlopen(rq, timeout=60) as r:
        bearer = {"Authorization": "Bearer " + json.loads(r.read())["token"]}

    def call(method, url, data=None, headers=None):
        req = urllib.request.Request(url, data=data, method=method, headers={**bearer, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.status, r.headers
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code == 404:
                return 404, e.headers
            raise SystemExit(f"push {name}: {method} {url.split('?')[0]}: HTTP {e.code} {e.read()[:300]!r}")
    base = f"https://{host}/v2/{repo}"
    for d, b in blobs.items():
        if call("HEAD", f"{base}/blobs/{d}")[0] == 200:
            continue
        _, h = call("POST", f"{base}/blobs/uploads/", b"", {"Content-Length": "0"})
        loc = urllib.parse.urljoin(base + "/", h["Location"])
        call("PUT", loc + ("&" if "?" in loc else "?") + "digest=" + urllib.parse.quote(d), b,
             {"Content-Type": "application/octet-stream", "Content-Length": str(len(b))})
    _, h = call("PUT", f"{base}/manifests/{t}", manifest, {"Content-Type": MANIFEST})
    d = _digest(manifest)
    if h.get("Docker-Content-Digest", d) != d:
        raise SystemExit(f"push {name}: the registry stored {h.get('Docker-Content-Digest')}, not {d}")
    return f"{tag(name)}@{d}"


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
    ref = f"{tag(name)}@{digest}"
    files = {f: sha256(ROOT / s["source"] / f) for f in sorted(s["files"])}
    bad = verify(name, ref, files)
    if bad:
        raise SystemExit("pin: the pushed image does not carry the sources' files:\n" + "\n".join(bad))
    p.write_text(json.dumps(dict(s, image=ref, files=files), indent=1) + "\n")


def main(argv: list[str]) -> int:
    cmd, args = (argv[0], argv[1:]) if argv else ("check", [])
    out = None
    if cmd == "build" and "--out" in args:
        i = args.index("--out")
        out, args = args[i + 1] if i + 1 < len(args) else None, args[:i] + args[i + 2:]
    need = {"build": 1, "push": 2, "pin": 2, "verify-image": 1}
    if cmd in need and len(args) != need[cmd]:
        print(__doc__)
        return 2
    names = args or sorted(p.parent.name for p in (ROOT / "images").glob("*/FILES.json"))
    if cmd == "fetch":
        for n in names:
            if spec(n).get("hf"):
                k = fetch(n)
                print(f"{n}: {len(spec(n)['files'])} files in {spec(n)['source']} ({k} downloaded)")
        return 0
    if cmd == "check":
        bad = [e for n in names for e in check(n)]
        print("\n".join(bad) or f"ok files images: {', '.join(names)} match their sources")
        return 1 if bad else 0
    if cmd == "digest":
        rc = 0
        for n in names:
            ref = f"{tag(n)}@{_digest(oci(n)[0])}"
            same = ref == image(n)
            rc |= 0 if same else 1
            print(f"{ref}  {'= pinned' if same else '!= pinned ' + image(n)}")
        return rc
    if cmd == "build":
        print(build(args[0], out))
        return 0
    if cmd == "push":
        token = sys.stdin.readline().strip()
        if not token:
            raise SystemExit("push: no token on stdin (gh auth token | python3 scripts/files_image.py push <name> <user>)")
        print(push(args[0], args[1], token))
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
