#!/bin/bash
# usage (on vast): replay.sh <oracle_run_name> <replay_name> [task]  -> out/<replay_name>/
R=/workspace/yamlab_port/runs/fiber_bundling
. /workspace/yamlab_port/env.sh
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
src=$1; name=$2; task=${3:-FiberBundling-VeryEasy-v0}
mkdir -p $R/out/$name; cd $R
PYTHONPATH=$R/yamlab YAMLAB_STRIP_CAMERAS=1 timeout 3000 nice -n 19 python $R/task/tools/replay.py --task $task --device cpu \
  --actions $R/out/$src/actions.npy --reference $R/out/$src/states.npz --out $R/out/$name > $R/out/$name/log.txt 2>&1
echo "EXIT $?" >> $R/out/$name/log.txt
