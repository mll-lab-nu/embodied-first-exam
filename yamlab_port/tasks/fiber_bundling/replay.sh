#!/bin/bash
# usage: replay.sh <oracle_run_name> <replay_name> [task]  -> out/<replay_name>/   (layout: see run.sh)
R=/data/pingyue/yamlab/runs/fiber
source /data/pingyue/yamlab/activate.sh
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
src=$1; name=$2; task=${3:-FiberBundling-VeryEasy-v0}
mkdir -p $R/out/$name; cd $R
PYTHONPATH=$R/yamlab YAMLAB_STRIP_CAMERAS=1 timeout 3000 nice -n 19 yamlab_fiber $R/task/tools/replay.py --task $task --device cpu \
  --actions $R/out/$src/actions.npy --reference $R/out/$src/states.npz --out $R/out/$name > $R/out/$name/log.txt 2>&1
echo "EXIT $?" >> $R/out/$name/log.txt
