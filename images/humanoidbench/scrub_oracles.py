"""Remove upstream's pretrained policies and published baseline scores from the image.

Two things HumanoidBench ships that an agent must not have:
  * data/reach_{one_hand,two_hands}/ -- trained low-level REACHING policies (an MLP obs->19-d action plus
    its obs-normalisation stats). They are the hierarchical baseline's low level. Rolling one out and
    recording the actions is a ready-made submission for `reach`, and a large head start on every
    manipulation task. The image has no torch, but .pt is a zip of pickled tensors and the net is a few
    hundred KB -- reimplementing the forward pass in numpy is trivial, so "no torch" is not a defence.
  * logs/*.json -- the paper's per-task training curves for every baseline. Not a solution, but it hands
    over the achievable return per task; the task's own instruction.md is the only place that should say
    what the bar is.
Fails loudly if anything is left.
"""
import pathlib, shutil, sys

root = pathlib.Path("/opt/humanoid-bench")
removed = []
for rel in ("data", "logs"):
    p = root / rel
    if p.exists():
        shutil.rmtree(p)
        removed.append(rel)

# Anything weight-shaped left anywhere outside the scene assets is a leftover we did not anticipate.
WEIGHTS = {".pt", ".pth", ".ckpt", ".npy", ".npz", ".pkl", ".msgpack", ".safetensors", ".h5"}
left = [
    str(p.relative_to(root))
    for p in root.rglob("*")
    if p.is_file() and p.suffix in WEIGHTS and "assets" not in p.parts
]
print(f"scrubbed: {removed or 'nothing'}; leftovers: {left}")
sys.exit(1 if left else 0)
