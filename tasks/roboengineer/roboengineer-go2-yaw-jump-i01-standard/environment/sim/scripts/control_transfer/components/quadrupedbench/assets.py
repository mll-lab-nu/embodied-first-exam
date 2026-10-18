"""Build-time pinned Go2 asset preparation; never run downloads in an evaluator."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

COMMIT = "0059d4335f8156206f63a35662313385f7ad6d74"
SOURCE = "https://github.com/google-deepmind/mujoco_menagerie.git"
SPI_COMMIT = "edc07d0b957bce9a430aa5a48b71a266a0a9f635"


def root():
    return Path(
        os.environ.get("GO2_ASSET_DIR", str(Path(os.environ.get("CONTROL_ASSETS", "/opt/control-assets")) / "go2"))
    )


def manifest(folder):
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != "asset-manifest.json"
    }


def prepare(destination, checkout=None):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Asset destination already exists")
    with tempfile.TemporaryDirectory() as temp:
        source = Path(checkout) if checkout else Path(temp) / "menagerie"
        if checkout is None:
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", SOURCE, str(source)], check=True)
        actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if checkout and actual != COMMIT:
            raise ValueError("Pinned source commit mismatch")
        if checkout is None:
            subprocess.run(["git", "-C", str(source), "checkout", COMMIT, "--", "unitree_go2"], check=True)
        subprocess.run(
            ["git", "-C", str(source), "diff", "--exit-code", COMMIT, "--", "unitree_go2"],
            check=True,
            capture_output=True,
        )
        shutil.copytree(source / "unitree_go2", destination)
    data = {"commit": COMMIT, "sha256": manifest(destination)}
    (destination / "asset-manifest.json").write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    return data


def verify():
    folder = root()
    data = json.loads((folder / "asset-manifest.json").read_text())
    if data.get("commit") != COMMIT or data.get("sha256") != manifest(folder):
        raise RuntimeError("Go2 assets differ from prepared pin")
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkout")
    args = parser.parse_args()
    prepare(args.out, args.checkout)
