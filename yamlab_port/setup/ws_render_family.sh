#!/bin/bash
# On ws: render a family's saved oracle run via its replay script in the Isaac 5.1 container.
# usage: bash render_family.sh <family> <run_name> [extra replay args]
# Expects ~/.../2026-10-12_yamlab/runs/<family>/{task (agent folder copy), out/<run_name>/actions.npy}.
set -eu
F=$1; RUN=$2; shift 2
T=$HOME/01_projects/04_code_robot_challenge/tmp/2026-10-12_yamlab
rm -rf $T/runs/$F/yamlab && cp -r $T/yamlab $T/runs/$F/yamlab
bash $T/runs/$F/task/install.sh $T/runs/$F/yamlab $T/runs/$F/task/assets
YL_TIMEOUT=${YL_TIMEOUT:-2400} bash $T/run_in_container.sh "mkdir -p /data/out/$F && PYTHONPATH=/data/pylib:/work/runs/$F/yamlab python /work/runs/$F/task/tools/replay.py --actions /work/runs/$F/task/out/$RUN/actions.npy --out /data/out/$F/${RUN}_render --device cpu --enable_cameras $* > /data/out/$F/${RUN}_render.log 2>&1"
echo "exit=$?"; ls /data/qineng/04_code_robot_challenge/2026-10-12_yamlab/out/$F/${RUN}_render | head
