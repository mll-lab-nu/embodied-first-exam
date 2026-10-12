#!/bin/bash
# usage (on vast): run.sh <outname> [oracle args...]   -> out/<outname>/{log.txt,metrics.json,actions.npy,states.npz}
R=/workspace/yamlab_port/runs/fiber_bundling
. /workspace/yamlab_port/env.sh
name=$1; shift
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
mkdir -p $R/out/$name
cd $R
PYTHONPATH=$R/yamlab YAMLAB_STRIP_CAMERAS=1 YAMLAB_FIBER_SOLVER_ITERS=${ITERS:-16,1} timeout 3000 nice -n 19 python $R/task/tools/oracle.py --device cpu --out $R/out/$name "$@" > $R/out/$name/log.txt 2>&1
echo "EXIT $?" >> $R/out/$name/log.txt
