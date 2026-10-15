"""Point AM-Bench's USDs at the image's copies of the web assets they load from NVIDIA's asset buckets (build step).

Thirteen of AM-Bench's USDs reference files on the buckets by URL (objects' payloads and materials: the TossBall / lemon
tote, the door, frame, peg, hole, lever, the SimReady lemon, lime and table, the NDT marker tape, the button; the robot's
paint). The tasks run with closed egress, so the image bakes those files in (images/ambench/web_assets.txt, sha256-checked,
mirroring the buckets' layouts under /opt/isaac-assets) and this script rewrites the URLs in the USD layers to the local
copies (the same files: the same scene). It writes each layer in its original crate version and fails if any web asset path
is left in a layer it was given. (images/robodojo/localize_assets.py's logic.)
    python localize_assets.py <remote prefix>=<local prefix> [...] -- <usd file>...
"""
import sys
from pxr import Sdf, UsdUtils

sep = sys.argv.index("--")
maps = [a.split("=", 1) for a in sys.argv[1:sep]]
files = sys.argv[sep + 1:]
changed = 0
for f in files:
    layer = Sdf.Layer.FindOrOpen(f)
    before = open(f, "rb").read(16)
    seen = []

    def fix(p):
        global changed
        for remote, local in maps:
            if p.startswith(remote):
                changed += 1
                return local + p[len(remote):]
        seen.append(p)
        return p
    UsdUtils.ModifyAssetPaths(layer, fix)
    layer.Save()
    after = open(f, "rb").read(16)
    left = [p for p in seen if p.startswith(("http://", "https://"))]
    print(f, "header", before[:12], "->", after[:12], "web paths left:", left)
    if left or before[:12] != after[:12]:
        sys.exit(f"{f}: web asset paths left {left} or crate version changed")
print("rewritten asset paths:", changed)
if not changed:
    sys.exit("nothing rewritten")
