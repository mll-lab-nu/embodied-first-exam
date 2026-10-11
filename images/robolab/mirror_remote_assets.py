#!/usr/bin/env python3
"""Make RoboLab's asset library self-contained: copy every remote file its USD layers reference into the image and point
the layers at the copies.

RoboLab's scenes reference NVIDIA's public Omniverse content bucket by URL: the MDL material modules of the tables, the
bins and the robot with their textures, and a few props. Kit fetches them when a scene is built. A container without
that network access (the agent's egress is the model APIs only, docs/PROTOCOL.md §2.7) cannot: the materials fail to
compile ("could not find module ... in module path", "Unable to find SdrShaderNode") and the table renders as a red
surface, while physics is unchanged. The image therefore holds the files (images/robolab/Dockerfile runs this script
last).

    python mirror_remote_assets.py <assets root> <mirror dir> --check <sha256 list>     # the image build: pinned
    python mirror_remote_assets.py <assets root> <mirror dir> --write <sha256 list>     # a maintainer, to (re)pin

What it does:
  1. opens every USD layer under <assets root> and collects the http(s) references (asset-valued attributes included);
  2. downloads each to <mirror dir>/<host>/<path>, and follows what a downloaded file needs next to it: a USD layer's
     own references, an MDL module's textures and relative imports. A URL the bucket does not serve (404) is skipped:
     the open-egress scene did not get it either;
  3. compares the downloaded bytes with the sha256 list (`sha256sum` format, paths relative to <mirror dir>) and fails on
     any difference: a missing file, an extra one, other bytes. With --check a file is compared before it is written
     or opened, so bytes the list does not name are never parsed;
  4. rewrites the references, in the library's layers and in the mirrored ones, to the local absolute paths, and fails
     if a layer still names a remote file the bucket serves.
It needs `pxr`, which the image has in Isaac Sim's bundled omni.usd.libs (no Kit start, no GPU): when `pxr` is not
importable the script re-runs itself with that library on its paths. Standard library otherwise."""
import hashlib
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from pxr import Sdf, UsdUtils
except ImportError:                                  # the image: pxr lives in Isaac Sim's extension cache
    if os.environ.get("ROBOLAB_MIRROR_REEXEC"):
        raise
    import glob
    import sysconfig
    isaac = pathlib.Path(sysconfig.get_paths()["purelib"]) / "isaacsim"
    libs = sorted(glob.glob(str(isaac / "extscache" / "omni.usd.libs-*")))
    if not libs:
        raise
    env = dict(os.environ, ROBOLAB_MIRROR_REEXEC="1", PYTHONPATH=libs[-1],
               LD_LIBRARY_PATH=":".join([f"{libs[-1]}/bin", str(isaac / "kit"), str(isaac / "kit/kernel/plugins"),
                                         os.environ.get("LD_LIBRARY_PATH", "")]).rstrip(":"))
    os.execve(sys.executable, [sys.executable, *sys.argv], env)

REMOTE = re.compile(r"^(https?):/+(.*)$")
USD_EXT = (".usd", ".usda", ".usdc")
IMAGE_EXT = r"\.(?:png|jpg|jpeg|exr|hdr|tga|dds|tif|tiff|bmp)"
# MDL modules that come with Kit (its own search path), never next to the importing file
BUILTIN_MDL = ("::nvidia::", "::base", "::anno", "::state", "::tex", "::math", "::df", "::std", "::limits", "::scene",
               "::debug", "::OmniPBR", "::OmniSurface", "::OmniGlass", "::OmniUe4", "::gltf", "::adobe", "::templates")


def norm(ref: str) -> str | None:
    """The URL a reference names, or None for a local one (USD's default resolver collapses "//" to "/")."""
    m = REMOTE.match(ref)
    return f"{m.group(1)}://{m.group(2)}" if m else None


def local_path(mirror: pathlib.Path, url: str) -> pathlib.Path:
    u = urllib.parse.urlsplit(url)
    return mirror / u.netloc / urllib.parse.unquote(u.path).lstrip("/")


def fetch(url: str) -> bytes | None:
    """The file's bytes; None when the bucket does not have it (404 / 403). Any other failure is retried, then raised."""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "eai-robolab-mirror"}), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not download {url}: {err!r}")


def mdl_needs(text: str) -> list[str]:
    """What an MDL module needs next to itself: its textures and the modules it imports by a relative path."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    out = set(re.findall(r'"((?:\.{1,2}/)?[^"\n]*' + IMAGE_EXT + r')"', text, re.I))
    for mod in re.findall(r"(?:import|using)\s+((?:\.{1,2})?::[\w:]+?)(?:::\*|::\w+)?\s*(?:import\b[^;]*)?;", text):
        if mod.startswith("::") and mod.startswith(BUILTIN_MDL):
            continue
        if mod.startswith(".::") or mod.startswith("..::"):
            out.add(("./" if mod.startswith(".::") else "../") + mod.lstrip(".").strip(":").replace("::", "/") + ".mdl")
    return sorted(o for o in out if not o.startswith("/"))


def asset_paths(layer) -> list[str]:
    found: list[str] = []
    UsdUtils.ModifyAssetPaths(layer, lambda p: (found.append(p), p)[1])      # a visit: every path is returned unchanged
    return found


def main(argv: list[str]) -> int:
    mode = pin = None
    for flag in ("--check", "--write"):
        if flag in argv:
            i = argv.index(flag)
            mode, pin = flag, pathlib.Path(argv[i + 1])
            del argv[i:i + 2]
    if len(argv) != 2 or mode is None:
        print(__doc__, file=sys.stderr)
        return 2
    root, mirror = pathlib.Path(argv[0]).resolve(), pathlib.Path(argv[1]).resolve()
    if mirror.exists() and any(mirror.iterdir()):
        print(f"FAIL: {mirror} is not empty (the mirror is built once, from the library as released)", file=sys.stderr)
        return 1
    layers = [p for p in sorted(root.rglob("*")) if p.suffix in USD_EXT and mirror not in p.parents]
    queue: list[str] = []
    seen: set[str] = set()
    referencing: list[str] = []                      # library layers with a remote reference
    digests: dict[str, str] = {}                     # mirrored file (relative to the mirror) -> sha256 of the downloaded bytes
    absent: list[str] = []
    pinned_map = (dict(reversed(ln.split("  ", 1)) for ln in pin.read_text().splitlines() if ln) if mode == "--check" else None)

    def want(url: str) -> None:
        if url not in seen:
            seen.add(url)
            queue.append(url)

    def scan(path: pathlib.Path, base_url: str | None) -> None:
        layer = Sdf.Layer.FindOrOpen(str(path))
        if layer is None:
            return
        hit = False
        for ref in asset_paths(layer):
            url = norm(ref)
            if url is None and base_url and ref and not ref.startswith("/") and ":" not in ref.split("/")[0] \
                    and not ("/" not in ref and ref.endswith(".mdl")):      # a bare X.mdl is Kit's own (OmniPBR.mdl)
                url = urllib.parse.urljoin(base_url, ref)                    # a mirrored layer's relative reference
            if url:
                hit = True
                want(url)
        if hit and base_url is None:
            referencing.append(str(path))

    for p in layers:
        scan(p, None)
    while queue:
        url = queue.pop(0)
        data = fetch(url)
        if data is None:
            absent.append(url)
            continue
        dst = local_path(mirror, url)
        if mirror not in dst.resolve().parents:      # a URL whose path climbs out of the mirror
            print(f"FAIL: {url} does not map to a file under {mirror}", file=sys.stderr)
            return 1
        rel, digest = dst.resolve().relative_to(mirror).as_posix(), hashlib.sha256(data).hexdigest()
        if pinned_map is not None and pinned_map.get(rel) != digest:
            print(f"FAIL: {rel} is not what {pin} pins ({'other bytes' if rel in pinned_map else 'not in the list'}): the "
                  "content bucket changed, or the library did; re-pin with --write only after checking the rendering",
                  file=sys.stderr)
            return 1
        if rel in digests and digests[rel] != digest:
            print(f"FAIL: two URLs map to {rel} with different bytes", file=sys.stderr)
            return 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        digests[rel] = digest
        if dst.suffix == ".mdl":
            for rel in mdl_needs(data.decode("utf-8", "replace")):
                want(urllib.parse.urljoin(url, rel))
        elif dst.suffix in USD_EXT:
            scan(dst, url)

    listing = "".join(f"{h}  {f}\n" for f, h in sorted(digests.items()))
    if mode == "--write":
        pin.write_text(listing)
    else:
        pinned = pin.read_text()
        if pinned != listing:
            a = dict(reversed(ln.split("  ", 1)) for ln in pinned.splitlines() if ln)
            diff = sorted(f for f in set(a) | set(digests) if a.get(f) != digests.get(f))
            print(f"FAIL: the mirror differs from {pin} in {len(diff)} file(s), e.g. {diff[:5]} (missing, extra or other "
                  "bytes): the content bucket changed, or the library did; re-pin with --write only after checking the "
                  "rendering", file=sys.stderr)
            return 1

    rewritten = 0
    mirrored_layers = [str(mirror / f) for f in sorted(digests) if pathlib.PurePosixPath(f).suffix in USD_EXT]
    for lp in referencing + mirrored_layers:
        layer = Sdf.Layer.FindOrOpen(lp)
        if layer is None:
            continue

        def repl(p: str) -> str:
            nonlocal rewritten
            url = norm(p)
            if url and local_path(mirror, url).is_file():
                rewritten += 1
                return str(local_path(mirror, url))
            return p
        UsdUtils.ModifyAssetPaths(layer, repl)
        if not layer.Save():
            print(f"FAIL: could not save {lp}", file=sys.stderr)
            return 1
        left = sorted({u for u in map(norm, asset_paths(layer)) if u and u not in absent})
        if left:
            print(f"FAIL: {lp} still names remote files, e.g. {left[:3]}", file=sys.stderr)
            return 1
    size = sum((mirror / f).stat().st_size for f in digests)
    print(f"mirror_remote_assets: {len(layers)} layers scanned, {len(referencing)} with remote references, "
          f"{len(digests)} files mirrored ({size / 1e6:.0f} MB), {len(absent)} URLs not served by the bucket, "
          f"{rewritten} references rewritten; pinned list {mode[2:]} {pin}")
    for u in absent:
        print(f"  not served: {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
