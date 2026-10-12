#!/bin/bash
# Install the FiberBundling task into a YAMLab clone: task files + registration lines + assets.
# usage: install.sh <yamlab_clone_root> <assets_dir (with <tier>/cable.usda ...)>
set -e
Y=${1:?yamlab clone root}; A=${2:?assets dir}
HERE=$(cd "$(dirname "$0")" && pwd)
cp "$HERE/yamlab_task/configs/tasks/fiber_bundling.yaml" "$Y/yamlab/configs/tasks/"
cp "$HERE"/yamlab_task/envs/tasks/fiber_bundling_*.py "$Y/yamlab/envs/tasks/"
mkdir -p "$Y/yamlab/envs/tasks/fiber_bundling_assets"
for t in "$A"/*/; do t=$(basename "$t"); rm -rf "$Y/yamlab/envs/tasks/fiber_bundling_assets/$t"; cp -r "$A/$t" "$Y/yamlab/envs/tasks/fiber_bundling_assets/$t"; done
I="$Y/yamlab/envs/tasks/__init__.py"
grep -q fiber_bundling_manager_cfg "$I" || printf 'from .fiber_bundling_manager_cfg import *\nfrom .fiber_bundling_manager import *\n' >> "$I"
R="$Y/yamlab/envs/robot_registry.py"
grep -q FiberBundling-Easy-v0 "$R" || python3 - "$R" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
for t in ("FiberBundling-VeryEasy-v0", "FiberBundling-Easier-v0", "FiberBundling-Easy-v0"):
    if t not in s:
        s=s.replace('    "HangMugOnTree-Mimic-v0": "yam",\n', '    "HangMugOnTree-Mimic-v0": "yam",\n    "%s": "yam",\n' % t)
open(p,"w").write(s)
PY
echo "installed FiberBundling into $Y"
