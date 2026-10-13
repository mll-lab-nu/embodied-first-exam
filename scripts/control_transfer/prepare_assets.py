"""Copy operator-supplied pinned robot assets into a private build context. No runtime downloads."""

import argparse, hashlib, json, shutil, subprocess
from pathlib import Path


def prepare(workspace, out):
    w = Path(workspace)
    out = Path(out)
    pins = [(w/"manipulationbench/vendor/mujoco_menagerie","0059d4335f8156206f63a35662313385f7ad6d74"),(w/"sim2realbench/vendor/unitree_rl_mjlab","1425b15f73bd4095f0df53709d7c389c3eb9e790")]
    for checkout,commit in pins:
        if subprocess.check_output(["git","rev-parse","HEAD"],cwd=checkout,text=True).strip()!=commit:
            raise ValueError("Unpinned robot source")
        subprocess.run(["git","diff","--quiet","HEAD"],cwd=checkout,check=True)
    attached=json.loads((w/"locomanipbench/attachment-manifest.json").read_text())
    for name,expected in attached["files"].items():
        if name.startswith("bots/Linearbot/"):
            if hashlib.sha256((w/"locomanipbench/vendor"/name).read_bytes()).hexdigest()!=expected:
                raise ValueError("Attached Linearbot asset changed")
    out.mkdir(parents=True, exist_ok=False)
    for src, dst in [
        (w / "manipulationbench/vendor/mujoco_menagerie/i2rt_yam", out / "yam"),
        (w / "locomanipbench/vendor/bots", out / "bots"),
        (w / "sim2realbench/vendor/unitree_rl_mjlab", out / "unitree_rl_mjlab"),
    ]:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    # Reference policies are separate operator-owned artifacts, not copied to the agent image.
    from .control_public.weights import convert_linearbot, convert_g1

    ref = out / "reference"
    ref.mkdir()
    convert_linearbot(w / "locomanipbench/runs/linearbot-trained-v1/policy.npz", ref / "linearbot.npz")
    convert_g1(
        w / "sim2realbench/vendor/unitree_rl_mjlab/deploy/robots/g1/config/policy/velocity/v0/exported/policy.onnx",
        ref / "g1.npz",
    )
    # A scrubbed upstream training source has no pretrained policies, deployment logs or solution notebooks.
    u = out / "unitree_rl_mjlab"
    for p in list(u.rglob("*.onnx")) + list(u.rglob("*.onnx.data")) + list(u.rglob("*.pt")) + list(u.rglob("*.pth")):
        p.unlink()
    manifest = {
        str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob("*"))
        if p.is_file()
    }
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"files": len(manifest), "bytes": sum(p.stat().st_size for p in out.rglob("*") if p.is_file())}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    prepare(a.workspace, a.out)
