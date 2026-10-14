"""Third-party model files of the presentation scenes, fetched at build time (never committed): every file is pinned
to one upstream commit and checked against its sha256 in the manifest (menagerie.json, next to this file). The files
are untrusted data: they are only read (MJCF parsed, meshes loaded by MuJoCo), never executed. Their licences are
kept next to the manifest (LICENSE.<model>) and credited in NOTICE.

    python3 -m renderers.presentation.assets fetch [MODEL ...]     download the missing files (all models by default)
    python3 -m renderers.presentation.assets verify [MODEL ...]    check what is in the cache
    python3 -m renderers.presentation.assets where                 print the cache directory

The cache: $RO_ASSET_CACHE, else <repo>/.cache/assets (git-ignored); files at <cache>/<source>/<commit>/<path>.
Standard library only (python >= 3.8), so the fetch runs on any host; the renderers read the cache inside the image.

Levels of detail (players' images, renderer rule 6): lod.json lists decimated copies of a model's visual meshes
(renderers/presentation/lod/<level>/<path>, committed: small, derived from the pinned files, licence unchanged; made by
lod.py), each file pinned by sha256 like the upstream ones. `meshes` = "full" (the upstream files) or a level ("25k").
A sport whose players' images use its presentation scene gets the model's files bundled into its simulator directory
(`bundle`, tools/sportlib.assemble_sim): <sim>/sport/presentation/assets/<path>, checked against the same manifests,
so a match needs neither the cache nor the network.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFESTS = ("menagerie.json",)
LOD_MANIFEST = "lod.json"
FULL = "full"
_verified: set = set()


class _Unavailable(RuntimeError):
    pass


def _err(msg):
    try:
        from . import PresentationUnavailable
    except ImportError:                       # pragma: no cover - run as a script on a host without numpy
        return _Unavailable(msg)
    return PresentationUnavailable(msg)


def manifests() -> list:
    return [json.loads((HERE / m).read_text()) for m in MANIFESTS]


def _find(name: str):
    for man in manifests():
        if name in man["models"]:
            return man, man["models"][name]
    raise KeyError(f"no presentation model {name!r} in {', '.join(MANIFESTS)}")


def cache_root() -> Path:
    env = os.environ.get("RO_ASSET_CACHE")
    return Path(env) if env else HERE.parents[1] / ".cache" / "assets"


def _base(man) -> Path:
    return cache_root() / man["name"] / man["commit"]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lods() -> dict:
    """lod.json: {"models": {model: {level: {"files": {path: sha256}, ...}}}, ...} ({} if absent)."""
    p = HERE / LOD_MANIFEST
    return json.loads(p.read_text()) if p.is_file() else {}


def files(name: str, meshes: str = FULL) -> dict:
    """{path: sha256} of model `name` with the given meshes ("full" or a level of lod.json)."""
    man, mod = _find(name)
    if meshes == FULL:
        return dict(mod["files"])
    lev = (lods().get("models", {}).get(name) or {}).get(meshes)
    if lev is None:
        raise KeyError(f"no level of detail {meshes!r} of {name} in {LOD_MANIFEST}")
    return dict(lev["files"])


def source_dir(name: str, meshes: str = FULL) -> Path:
    """Where the files of `name` with `meshes` live on this checkout: the cache (full) or renderers/presentation/lod."""
    man, _ = _find(name)
    return _base(man) if meshes == FULL else HERE / "lod" / meshes


def missing(name: str, meshes: str = FULL, root: Path | None = None) -> list:
    """The files of model `name` that are absent (from `root`, default its source_dir) or do not match their sha256."""
    base = Path(root) if root is not None else source_dir(name, meshes)
    return [p for p, sha in files(name, meshes).items() if not (base / p).is_file() or _sha(base / p) != sha]


def model_xml(name: str, meshes: str = FULL, root: Path | None = None) -> Path:
    """The model's MJCF file, all its files verified (once per process): from `root` (a simulator's bundle) if given,
    else from the cache (full meshes) or renderers/presentation/lod (a level of detail)."""
    _, mod = _find(name)
    base = Path(root) if root is not None else source_dir(name, meshes)
    key = (name, meshes, str(base))
    if key not in _verified:
        bad = missing(name, meshes, base)
        if bad:
            how = (f"python3 -m renderers.presentation.assets fetch {name}" if meshes == FULL and root is None
                   else "regenerate the task (tools/generate.py)" if root is not None
                   else f"python3 -m renderers.presentation.lod build {name} {meshes}")
            raise _err(f"presentation model {name} ({meshes} meshes): {len(bad)} of {len(files(name, meshes))} files "
                       f"missing or not matching their sha256 in {base} ({how})")
        _verified.add(key)
    return base / mod["xml"]


def bundle(name: str, meshes: str, dst: Path) -> list:
    """Copy model `name` with `meshes` (verified) and its licence into the directory `dst` (a simulator's
    sport/presentation/assets): returns the paths written, relative to dst."""
    import shutil
    _, mod = _find(name)
    src = source_dir(name, meshes)
    model_xml(name, meshes)                       # verifies every file
    out = []
    for p in sorted(files(name, meshes)):
        (Path(dst) / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / p, Path(dst) / p)
        out.append(p)
    lic = mod["license_file"]
    shutil.copyfile(HERE / lic, Path(dst) / lic)
    return out + [lic]


def credit(name: str) -> str:
    man, mod = _find(name)
    return (f"{mod['title']}: {man['title']} ({man['source']}, commit {man['commit'][:12]}, {mod['path']}), "
            f"{mod['copyright']}, {mod['license']} (renderers/presentation/{mod['license_file']})")


def fetch(name: str, log=print) -> int:
    man, mod = _find(name)
    base = _base(man)
    n = 0
    for p, sha in sorted(mod["files"].items()):
        dst = base / p
        if dst.is_file() and _sha(dst) == sha:
            continue
        url = man["url"].format(commit=man["commit"], path=p)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            f.write(r.read())
        got = _sha(tmp)
        if got != sha:
            tmp.unlink()
            raise _err(f"{url}: sha256 {got} != {sha} (manifest); nothing kept")
        tmp.replace(dst)
        n += 1
    log(f"{name}: {len(mod['files'])} files in {base} ({n} downloaded)")
    return n


def main(argv) -> int:
    cmd, names = (argv[0] if argv else "verify"), argv[1:]
    if cmd == "where":
        print(cache_root())
        return 0
    names = names or [n for man in manifests() for n in man["models"]]
    rc = 0
    for n in names:
        if cmd == "fetch":
            fetch(n)
        elif cmd == "verify":
            for meshes in [FULL] + sorted(lods().get("models", {}).get(n, {})):
                bad = missing(n, meshes)
                print(f"{n} ({meshes}): " + ("ok" if not bad else f"{len(bad)} files missing or changed"))
                rc |= bool(bad)
        else:
            print(__doc__)
            return 2
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
