"""Assemble /opt/abc for the abc-sim image (runs in the Dockerfile's fetch stage; not part of the image).

    python assemble.py <abc git checkout> <dir of asset tarballs> <assets.txt> <out>

- The `abc_sim` package from the upstream checkout (its git-tracked files), without what points at the upstream
  demonstrations, checkpoints or asset mirror or is not needed to simulate: the package and models READMEs, the asset
  manifest (mirror URLs), the RoboCasa pack stub, and the Blender exporter of recorded dataset episodes.
- The scene XMLs of the package with their comments removed (one described the training data); comments never change
  a compiled model.
- From the checksum-pinned asset packages, only the files the frozen instances' scenes open (assets.txt: every file the
  29 scenes opened while they were built) and each package's licence and attribution files.
- The upstream LICENSE (Apache-2.0).
"""
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

src, pkgs, keep_list, out = map(Path, sys.argv[1:5])
EXCLUDE = re.compile(r"^abc_sim/(README\.md|models/README\.md|models/assets_manifest\.json|models/assets_robocasa/|"
                     r"rendering/blender/)")
LICENCE = re.compile(r"(^|/)(LICENSE[^/]*|README\.md|[^/]*ATTRIBUTIONS[^/]*\.md)$")

pkg_root = out / "abc_sim"
files = subprocess.run(["git", "-C", str(src), "ls-files", "abc_sim"], check=True, capture_output=True,
                       text=True).stdout.split()
for f in files:
    if EXCLUDE.match(f):
        continue
    dst = out / f
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / f, dst)
    if f.startswith("abc_sim/models/") and f.endswith(".xml"):
        text = dst.read_text()
        dst.write_text(re.sub(r"<!--.*?-->", "", text, flags=re.S))
shutil.copy2(src / "LICENSE", out / "LICENSE")

keep = {line.strip() for line in keep_list.read_text().splitlines() if line.strip() and not line.startswith("#")}
models = pkg_root / "models"
found = set()
for tgz in sorted(pkgs.glob("*.tar.gz")):
    with tarfile.open(tgz) as t:
        for m in t.getmembers():
            if not m.isfile():
                continue
            name = m.name.lstrip("./")
            rel = name if name.startswith("assets/") else f"assets/{name}"
            if rel in keep or LICENCE.search(rel):
                dst = models / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(m) as fsrc, open(dst, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                found.add(rel)
missing = sorted(keep - found)
if missing:
    sys.exit(f"asset files not found in the packages: {missing[:10]} ({len(missing)} in all)")
print(f"abc_sim: {sum(1 for f in files if not EXCLUDE.match(f))} package files, {len(keep)} asset files, "
      f"{len(found - keep)} licence / attribution files")
