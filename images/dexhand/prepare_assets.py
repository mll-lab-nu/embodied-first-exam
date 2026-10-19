#!/usr/bin/env python3
"""Fetch the pinned hand models baked into the dexhand image and verify every file's hash.

* Sharpa Wave (Apache-2.0): MuJoCo Menagerie `sharpa_wave`, pinned in asset-manifest.json -> assets/hand/
* Wuji Hand 2.2 (MIT): wuji-description `hand2/hand2_2`, runtime subset pinned in wuji-asset-manifest.json
  -> assets/wuji_v2_2/ (MJCF, meshes, license, changelog; the manifest is installed as manifest.json)
* Tianji Marvin dual-arm meshes (Apache-2.0 / MIT, see tianji/NOTICE.md): runtime subset pinned in
  tianji-asset-manifest.json -> assets/tianji/, rebuilt from the pinned public DexForce / Genesis sources by
  tianji/tianji_model.py (or copied from a verified local copy); see prepare_tianji().
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def fetch_all(manifest: dict, base: str, destination: Path, remote) -> None:
    def fetch(item):
        relative, expected = item
        target = destination / relative
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected["sha256"]:
            return
        with urlopen(base + remote(relative), timeout=60) as response:
            data = response.read()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"asset hash mismatch: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(fetch, manifest["files"].items()))


def main() -> None:
    sharpa = json.loads((HERE / "asset-manifest.json").read_text())
    fetch_all(sharpa, "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/"
              + sharpa["source_commit"] + "/sharpa_wave/", HERE / "assets/hand", lambda path: path)
    print(f"verified {len(sharpa['files'])} Sharpa Wave files at {HERE / 'assets/hand'}")
    wuji = json.loads((HERE / "wuji-asset-manifest.json").read_text())
    destination = HERE / "assets/wuji_v2_2"
    fetch_all(wuji, "https://raw.githubusercontent.com/wuji-technology/wuji-description/"
              + wuji["source_commit"] + "/", destination,
              lambda path: path if path in ("LICENSE", "CHANGELOG.md") else "hand2/hand2_2/body/" + path)
    if not (destination / "manifest.json").is_file():
        shutil.copyfile(HERE / "wuji-asset-manifest.json", destination / "manifest.json")
    print(f"verified {len(wuji['files'])} Wuji Hand 2.2 files at {destination}")
    prepare_tianji()


def prepare_tianji() -> None:
    """Tianji Marvin meshes: reuse a verified local copy, else rebuild them from the pinned public sources.

    Public sources (tianji/source-manifest.json): DexForce `embodichain_data` TianjiMarvin.zip at HuggingFace revision
    48317bd8 (Apache-2.0, sha256-pinned), Genesis `dual_arms_primitives.urdf` at revision deffbe16 (MIT, inertias), and
    the conversion tianji/tianji_model.py (trimesh 4.11.2, MuJoCo 3.4.0, numpy 2.3.5, scipy 1.16.3). Every converted
    mesh must hash to tianji-asset-manifest.json; NOTICE.md and PROVENANCE.json are the committed copies in tianji/.
    """
    tianji = json.loads((HERE / "tianji-asset-manifest.json").read_text())
    destination = HERE / "assets/tianji"
    docs = {"NOTICE.md", "PROVENANCE.json"}
    source = json.loads((HERE / "tianji/source-manifest.json").read_text())
    texts = {entry["path"]: entry["text"].encode() for entry in source["license_files"]}

    def good(path: Path, expected: dict) -> bool:
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]

    missing = [r for r, e in tianji["files"].items() if not good(destination / r, e)]
    build = None
    for relative in missing:
        expected = tianji["files"][relative]
        if relative in docs:
            data = (HERE / "tianji" / relative).read_bytes()
        elif relative in texts:
            data = texts[relative]
        else:
            local = HERE.parent / "everyday_dexterity/assets/tianji" / relative
            if good(local, expected):
                data = local.read_bytes()
            else:
                build = build or build_tianji(source)
                data = (build / relative).read_bytes()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"Tianji asset hash mismatch: {relative}")
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
        (destination / relative).write_bytes(data)
    shutil.copyfile(HERE / "tianji-asset-manifest.json", destination / "manifest.json")
    print(f"verified {len(tianji['files'])} Tianji Marvin files at {destination}"
          + (f" (rebuilt from public sources in {build})" if build else ""))


def build_tianji(source: dict) -> Path:
    """Download the pinned archives, extract the listed sources and run the pinned conversion in a build folder."""
    import importlib.metadata
    import sys
    import zipfile

    for package, version in source["dependencies"].items():
        if package != "python" and importlib.metadata.version(package) != version:
            raise SystemExit(f"rebuilding the Tianji meshes needs {package}=={version}")
    build = HERE / "assets/tianji-build"
    build.mkdir(parents=True, exist_ok=True)
    archive = build / source["archive"]["filename"]

    def fetch(url: str, target: Path, digest: str, size: int) -> None:
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            return
        with urlopen(url, timeout=600) as response:
            data = response.read()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"public source hash mismatch: {url}")
        target.write_bytes(data)

    fetch(source["archive"]["url"], archive, source["archive"]["sha256"], source["archive"]["bytes"])
    inertia = source["inertia_asset"]
    fetch(inertia["url"], build / inertia["path"], inertia["sha256"], inertia["bytes"])
    with zipfile.ZipFile(archive) as bundle:
        for entry in source["source_files"]:
            data = bundle.read(entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError(f"Tianji source member hash mismatch: {entry['path']}")
            (build / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
            (build / entry["path"]).write_bytes(data)
    sys.path.insert(0, str(HERE / "tianji"))
    from tianji_model import convert_assets

    convert_assets(build)
    return build


if __name__ == "__main__":
    main()
