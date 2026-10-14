#!/usr/bin/env python3
"""Install a libuipc build into its own prefix (images/roboarc/Dockerfile): <wheels> holds one wheel and its
uipc-build.json. The wheel must have the sha256 its uipc-build.json records; after the install, the version and the CUDA
backend's sha256 are checked against that record too, as images/topogym/verify_uipc_wheel.py install does for the audited
wheel in site-packages. rcb_topogym.select_uipc_build() puts <prefix>/site-packages first on sys.path on the GPUs the
build is for.
usage: python install_uipc_prefix.py <wheels> <prefix>     -> <prefix>/site-packages/, <prefix>/uipc-build.json"""
import email
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile


def sha(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(wheels: pathlib.Path, prefix: pathlib.Path) -> None:
    record = json.loads((wheels / "uipc-build.json").read_text())
    wheel = wheels / record["wheel"]
    if wheel.parent != wheels or sha(wheel) != record["wheel_sha256"]:
        sys.exit(f"{wheel}: not the wheel its uipc-build.json records")
    site = prefix / "site-packages"
    with tempfile.TemporaryDirectory() as tmp:
        requirements = pathlib.Path(tmp) / "wheel.lock"
        requirements.write_text(f"pyuipc @ {wheel.resolve().as_uri()} --hash=sha256:{record['wheel_sha256']}\n")
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile", "--require-hashes",
                        "--target", str(site), "-r", str(requirements)], check=True)
    dist = list(site.glob("pyuipc-*.dist-info"))
    if len(dist) != 1 or sorted(p.name for p in site.iterdir()) != sorted([dist[0].name, "uipc"]):
        sys.exit(f"{site}: expected exactly the uipc package and its dist-info")
    version = email.message_from_bytes((dist[0] / "METADATA").read_bytes())["Version"]
    if version != record["version"] or sha(site / record["backend_path"]) != record["backend_sha256"]:
        sys.exit(f"{site}: installed libuipc differs from its uipc-build.json")
    shutil.copyfile(wheels / "uipc-build.json", prefix / "uipc-build.json")
    print(f"ok {prefix}: pyuipc {version}, architectures {record['architectures']}, uipc-build.json {sha(prefix / 'uipc-build.json')[:12]}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]))
