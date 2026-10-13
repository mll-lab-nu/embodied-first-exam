#!/bin/bash
# usage: run.sh <outname> [oracle args...]   -> out/<outname>/{log.txt,metrics.json,actions.npy,states.npz}
# Layout: R=/data/pingyue/yamlab/runs/fiber with task/ = a snapshot of this folder and yamlab/ = a pinned YAMLab clone
# with the task installed (install.sh); env: /data/pingyue/yamlab/activate.sh (yamlab_fiber = symlink to the env python).
R=/data/pingyue/yamlab/runs/fiber
source /data/pingyue/yamlab/activate.sh
name=$1; shift
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
mkdir -p $R/out/$name
cd $R
PYTHONPATH=$R/yamlab YAMLAB_STRIP_CAMERAS=1 YAMLAB_FIBER_SOLVER_ITERS=${ITERS:-16,1} timeout 3000 nice -n 19 yamlab_fiber $R/task/tools/oracle.py --device cpu --out $R/out/$name "$@" > $R/out/$name/log.txt 2>&1
echo "EXIT $?" >> $R/out/$name/log.txt
