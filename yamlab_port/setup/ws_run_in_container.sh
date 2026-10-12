#!/bin/bash
# Usage: [YL_TIMEOUT=seconds] bash run_in_container.sh <command...>
# Runs inside eai-robolab:0.1.2 with our dirs mounted. The timeout runs INSIDE the container
# (timeout on the docker client would not stop the container).
T=$HOME/01_projects/04_code_robot_challenge/tmp/2026-10-12_yamlab
D=/data/qineng/04_code_robot_challenge/2026-10-12_yamlab
TO=${YL_TIMEOUT:-1800}
exec docker run --rm --stop-timeout 5 --gpus all --name yamlab-render-$$ --label yamlab_port=1 --memory 24g --cpus 8 \
  -v $T:/work -v $D:/data -e PYTHONPATH=/data/pylib:/work/yamlab -e OMNI_KIT_ACCEPT_EULA=YES \
  -v $D/cache/ov:/root/.cache/ov -v $D/cache/nv:/root/.nv \
  -w /work ghcr.io/mll-lab-nu/eai-robolab:0.1.2 timeout -k 30 $TO bash -lc "$*"
