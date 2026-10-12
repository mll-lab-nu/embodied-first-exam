#!/bin/bash
# Render path for YAMLab on ws/ws3: the eai-robolab Isaac 5.1 / Isaac Lab 2.3.2 container + a yamlab
# overlay (pylib via --target) in our own dirs. Run on the host: bash ws_render_setup.sh
set -eux
T=$HOME/01_projects/04_code_robot_challenge/tmp/2026-10-12_yamlab
D=/data/qineng/04_code_robot_challenge/2026-10-12_yamlab
mkdir -p $T $D/cache $D/pylib $D/out
cd $T
[ -d yamlab ] || git clone -q https://github.com/ARISE-Initiative/yamlab yamlab
[ -d lerobot ] || GIT_LFS_SKIP_SMUDGE=1 git clone -q -b lerobotv2.0 https://github.com/RogerDAI1217/lerobot.git lerobot
cat > INDEX.md <<EOT
# 2026-10-12_yamlab (ws render path for the YAMLab port; laptop: yamlab_port/)
- yamlab/: clone of ARISE-Initiative/yamlab; lerobot/: RogerDAI1217/lerobot lerobotv2.0 (import-time dep of yamlab)
- render_probe.py: RTX smoke test; run_in_container.sh: docker wrapper (eai-robolab image, our dirs only)
- data/out dirs: $D (cache = Kit caches, pylib = pip --target overlay, out = renders)
EOT
