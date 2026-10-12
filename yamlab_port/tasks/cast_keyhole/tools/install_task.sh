#!/bin/bash
# Install the CastKeyhole task into a YAMLab clone (task files + registration lines only).
# usage: install_task.sh <yamlab_repo_root> <assets_dir_with_tier_subdirs>
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
Y="$1/yamlab"; A="$2"
cp "$SRC/task/configs/tasks/cast_keyhole.yaml" "$Y/configs/tasks/"
cp "$SRC/task/envs/tasks/cast_keyhole_manager_cfg.py" "$SRC/task/envs/tasks/cast_keyhole_manager.py" "$Y/envs/tasks/"
mkdir -p "$Y/envs/tasks/cast_keyhole_assets"
cp -r "$A"/. "$Y/envs/tasks/cast_keyhole_assets/"
grep -q "cast_keyhole_manager" "$Y/envs/tasks/__init__.py" || \
  printf 'from . import cast_keyhole_manager  # registers CastKeyhole-<Tier>-v0\n' >> "$Y/envs/tasks/__init__.py"
grep -q "CastKeyhole" "$Y/envs/robot_registry.py" || python - "$Y/envs/robot_registry.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace('    "HangMugOnTree-Mimic-v0": "yam",\n',
              '    "HangMugOnTree-Mimic-v0": "yam",\n    "CastKeyhole-VeryEasy-v0": "yam",\n'
              '    "CastKeyhole-Easier-v0": "yam",\n    "CastKeyhole-Easy-v0": "yam",\n')
open(p, "w").write(s)
PY
echo "installed CastKeyhole into $Y"
