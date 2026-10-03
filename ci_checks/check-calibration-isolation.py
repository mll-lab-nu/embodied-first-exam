#!/usr/bin/env python3
"""Static plus explicit artifact checks. Missing runtime environments are not a pass."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "calibration_tools"


def static_checks():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "topogym.planning.calibration_tools*" in config["tool"]["setuptools"]["packages"]["find"]["exclude"]
    assert "prune topogym/planning/calibration_tools" in (ROOT / "MANIFEST.in").read_text().splitlines()
    assert "topogym/planning" in (ROOT / ".dockerignore").read_text().splitlines()
    assert '"planning"' in (ROOT / "images/topogym/prune.py").read_text()
    # Formal surfaces must not import or forward development calls.
    paths = [ROOT / "topogym/simulator/interaction.py", ROOT / "topogym/simulator/privileged.py"]
    for folder in ("harbor_templates", "harbor_agents", "images/topogym", "scripts/eai_standard"):
        paths.extend((ROOT / folder).rglob("*.py"))
    for path in paths:
        assert FORBIDDEN not in path.read_text(), f"Development reference on formal surface: {path}"
    for path in paths[:2]:
        tree = ast.parse(path.read_text())
        methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert not methods & {"set_object_pose", "pin_object", "open_session", "preview_geometry", "sync_probe"}
    return dict(status="passed", scope="static rules and public surfaces; not runtime image verification")


def artifact(path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    assert not any("/calibration_tools/" in "/" + name for name in names), f"Leaked development code in {path}"
    return dict(path=str(path), status="passed", entries=len(names))


def image_check(image):
    code = """import importlib.util
try:
    found = importlib.util.find_spec('topogym.planning.calibration_tools')
except ModuleNotFoundError:
    found = None
assert found is None, found
try:
    from topogym.simulator.interaction import Interaction
except ModuleNotFoundError:
    pass  # A limited actor image may contain no simulator package at all.
else:
    assert not hasattr(Interaction, 'set_object_pose')
print('development module and public entry absent')
"""
    # No checkout, host run directory or control socket is mounted.
    result = subprocess.run(["docker", "run", "--rm", "--network=none", "--read-only",
        "--workdir=/tmp", "-e", "ORACLE_DEV=1", "-e", "TOPGYM_ORACLE_DEV=1",
        "--entrypoint=python", image, "-c", code], text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"{image}: {result.stderr}")
    return dict(image=image, status="passed", scope="fresh no-mount container; deployment mounts must also be audited")


def container_check(name):
    rows = json.loads(subprocess.check_output(["docker", "inspect", name], text=True, timeout=15))
    for row in rows:
        for mount in row.get("Mounts", []):
            source, target = mount.get("Source", ""), mount.get("Destination", "")
            source_path = Path(source)
            assert not (source_path / "topogym/planning/calibration_tools").exists(), f"Source checkout mounted into {name}"
            assert not (source_path / "planning/calibration_tools").exists(), f"Package source mounted into {name}"
            assert not any(x in source + target for x in ("calibration_tools", "oracle_dev")), f"Development mount: {mount}"
    return dict(container=name, status="passed", scope="mount-path audit; arbitrary copied developer data requires artifact review")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    for role in ("limited", "privileged", "sim", "verifier"):
        parser.add_argument("--" + role + "-image")
    parser.add_argument("--container", action="append", default=[])
    parser.add_argument("--require-images", action="store_true")
    args = parser.parse_args()
    images = {role: getattr(args, role + "_image") for role in ("limited", "privileged", "sim", "verifier")}
    if args.require_images and not all(images.values()):
        parser.error("--require-images needs all four role images")
    result = dict(static=static_checks(), artifacts=[artifact(p) for p in args.artifact],
                  runtime={role: image_check(value) if value else dict(status="not_verified") for role, value in images.items()},
                  deployment_mounts=[container_check(name) for name in args.container])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
