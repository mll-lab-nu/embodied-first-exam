"""Run frozen Blanket acceptance in an independent immutable source snapshot."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from topogym.utils.io import write_json_atomic, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checks", choices=("full", "repeated-reset", "scene-layout"), default="full",
                        help="Full runtime acceptance, or isolated repeated-reset regression")
    args = parser.parse_args()
    root, repo = args.output.resolve(), Path(__file__).resolve().parents[1]
    root.mkdir(parents=True, exist_ok=False)
    snapshot = root/"source"
    snapshot.mkdir()
    for folder in ("topogym", "tests"):
        shutil.copytree(repo/folder, snapshot/folder, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(repo/"pyproject.toml", snapshot/"pyproject.toml")
    report = dict(status="in_progress", checks=args.checks, candidate=str(args.candidate.resolve()),
        sources={str(p.relative_to(snapshot)): sha256_file(p) for p in snapshot.rglob("*.py")})
    write_json_atomic(root/"run.json", report)
    env = dict(os.environ, PYTHONPATH=str(snapshot), TOPOGYM_BLANKET_CANDIDATE=str(args.candidate.resolve()),
        TOPOGYM_BLANKET_ACCEPTANCE=str(root/"validation"), TOPOGYM_BLANKET_CHECKS=args.checks, TOPOGYM_ASSET_ROOT=str(repo/"assets"))
    test = "test_blanket_scene_layout.py" if args.checks == "scene-layout" else "test_blanket_initialization.py"
    command = [sys.executable, "-m", "pytest", "-q", "-s", "-o", "addopts=", "-m", "genesis",
               f"tests/integration/{test}"]
    with (root/"pytest.log").open("w") as stream:
        completed = subprocess.run(command, cwd=snapshot, env=env, stdout=stream, stderr=subprocess.STDOUT)
    report.update(status="passed" if completed.returncode == 0 else "failed", returncode=completed.returncode)
    write_json_atomic(root/"run.json", report)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
