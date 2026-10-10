"""Point YAMLab's workstation USDs at the image's copies of the NVIDIA materials they load from the web (build step).

YAMLab's workstation (table, walls; yamlab/robot/yam/workstation/) references three MDL materials by URL on NVIDIA's asset
bucket (vMaterials 2 leather and brushed aluminium, a carpet). The tasks run with closed egress, so the image bakes those
files in (images/yamlab/Dockerfile, sha256-checked) and this script rewrites the URLs in the USD layers to the local copies:
the same files, so the same look; physics never reads them. It writes each layer in its original crate version and fails
if any web asset path is left in a workstation layer.
    python localize_assets.py <remote prefix> <local prefix> <usd file>...
"""
import sys
from pxr import Sdf, UsdUtils

remote, local, files = sys.argv[1], sys.argv[2], sys.argv[3:]
changed = 0
for f in files:
    layer = Sdf.Layer.FindOrOpen(f)
    before = open(f, "rb").read(16)
    seen = []

    def fix(p):
        global changed
        if p.startswith(remote):
            changed += 1
            return local + p[len(remote):]
        seen.append(p)
        return p
    UsdUtils.ModifyAssetPaths(layer, fix)
    layer.Save()
    after = open(f, "rb").read(16)
    left = [p for p in seen if p.startswith("http")]
    print(f, "header", before[:12], "->", after[:12], "web paths left:", left)
    if left or before[:12] != after[:12]:
        sys.exit(f"{f}: web asset paths left {left} or crate version changed")
print("rewritten asset paths:", changed)
if not changed:
    sys.exit("nothing rewritten")
