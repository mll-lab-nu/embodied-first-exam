"""Point RoboDojo's USDs at the image's copies of the NVIDIA materials they load from the web (build step).

Two of RoboDojo's assets reference three MDL materials (Base: Aluminum_Anodized, Aluminum_Cast, Plastic_ABS) by URL on
NVIDIA's asset bucket, in two URL forms that serve the same files: the wrist-camera model (Assets/Sensor/Camera/
realsense.usd, the old `Materials/Base/...` form) and the camera stand (Assets/Object/RoboDojo/Geometry/camera_stand/00000/
object.usd, `Materials/2023_1/Base/...`). The tasks run with closed egress, so the image bakes those files in
(images/robodojo/web_assets.txt, sha256-checked) and this script rewrites the URLs in the USD layers to the local copies:
the same files, so the same look; physics never reads them. It writes each layer in its original crate version and fails
if any web asset path is left in a layer it was given.
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
