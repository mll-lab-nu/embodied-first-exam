"""Stage already prepared assets. This intentionally never publishes or downloads restricted data."""

import argparse, json, shutil, hashlib
from pathlib import Path
from stage_skydio import stage

p = argparse.ArgumentParser()
p.add_argument("--assets", type=Path, required=True)
p.add_argument("--fly", type=Path, required=True)
p.add_argument("--go2", type=Path, required=True, help="Prepared evaluator-only Go2 assets")
p.add_argument("--skydio", type=Path, required=True, help="Prepared pinned public Skydio visual assets")
a = p.parse_args()
out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=False)
public = out / "public"
public.mkdir()
for name in ["unitree_rl_mjlab", "go2"]:
    shutil.copytree(
        a.assets / name,
        public / name,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "deploy", "docs", ".github",
                                      "*.npz", "*.onnx", "*.pt", "*.pth", "*.ckpt", "*.safetensors"),
    )
WEIGHTS = (".npz", ".onnx", ".pt", ".pth", ".ckpt", ".safetensors")
if any(p.suffix in WEIGHTS for p in public.rglob("*")):   # no trained policy in what the agent's image holds
    raise SystemExit("a policy or weights file in the public assets")
stage(a.skydio, public / "skydio_x2")
manifest = {
    str(p.relative_to(public)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(public.rglob("*"))
    if p.is_file()
}
(public / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
shutil.copytree(a.fly, out / "private-fly")
shutil.copytree(a.go2, out / "private-go2")
