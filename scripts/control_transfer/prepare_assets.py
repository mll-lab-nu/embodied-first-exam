"""Prepare pinned nominal G1/Go2 sources; reference policies are separate operator artifacts."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

UNITREE_PIN = "1425b15f73bd4095f0df53709d7c389c3eb9e790"


def prepare(workspace, out, go2_source=None, private_go2_out=None):
    workspace, out = Path(workspace), Path(out)
    unitree = workspace / "sim2realbench/vendor/unitree_rl_mjlab"
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=unitree, text=True).strip()
    if actual != UNITREE_PIN:
        raise ValueError("Unpinned Unitree source")
    subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=unitree, check=True)
    go2_source = Path(go2_source) if go2_source else workspace / "manipulationbench/vendor/mujoco_menagerie"
    if not (go2_source / "unitree_go2/go2.xml").is_file():
        raise ValueError("Provide --go2-source with the pinned Menagerie unitree_go2 tree checked out")
    out.mkdir(parents=True, exist_ok=False)
    # Preserve only the public G1 training dependency closure. src.tasks performs
    # recursive discovery, so unrelated configs would import excluded robots.
    nominal = out / "unitree_rl_mjlab"
    files = (
        "src/__init__.py",
        "src/assets/__init__.py",
        "src/assets/robots/__init__.py",
        "src/tasks/__init__.py",
        "src/tasks/velocity/__init__.py",
        "src/tasks/velocity/velocity_env_cfg.py",
        "src/tasks/velocity/config/__init__.py",
    )
    for name in files:
        target = nominal / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unitree / name, target)
    for name in (
        "src/assets/robots/unitree_g1",
        "src/tasks/velocity/config/g1",
        "src/tasks/velocity/mdp",
        "src/tasks/velocity/rl",
    ):
        shutil.copytree(
            unitree / name,
            nominal / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.onnx", "*.pt", "*.pth", "*.ckpt"),
        )
    for source in unitree.glob("LICENSE*"):
        shutil.copy2(source, nominal / source.name)
    from .components.quadrupedbench.assets import prepare as prepare_go2

    private_go2 = Path(private_go2_out) if private_go2_out else out.parent / (out.name + "-private-go2")
    prepare_go2(private_go2, checkout=go2_source)
    public_go2 = out / "go2"
    public_go2.mkdir()
    for name in ("go2.xml", "LICENSE"):
        shutil.copy2(private_go2 / name, public_go2 / name)
    shutil.copytree(private_go2 / "assets", public_go2 / "assets")
    (out / "unitree_rl_mjlab/src/assets/robots/__init__.py").write_text(
        "from .unitree_g1.g1_constants import G1_ACTION_SCALE, get_g1_robot_cfg\n"
    )
    manifest = {
        str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(out.rglob("*"))
        if path.is_file()
    }
    if any(Path(name).suffix in (".pt", ".pth", ".onnx", ".ckpt") for name in manifest):
        raise RuntimeError("Reference policy in nominal assets")
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {"files": len(manifest), "bytes": sum(path.stat().st_size for path in out.rglob("*") if path.is_file())}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--go2-source", help="Pinned Menagerie checkout containing unitree_go2")
    parser.add_argument("--private-go2-out", help="Evaluator-only pinned Go2 assets including integrity manifest")
    args = parser.parse_args()
    prepare(args.workspace, args.out, args.go2_source, args.private_go2_out)
