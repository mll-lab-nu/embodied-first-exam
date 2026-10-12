#!/bin/bash
# usage (on vast): vrun.sh <timeout_s> <script.py> [args...]   -- nice 19, rope_threading env, cwd = work/
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4} MKL_NUM_THREADS=${MKL_NUM_THREADS:-4} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-4}
R=/workspace/yamlab_port/runs/rope_threading
. /workspace/yamlab_port/env.sh
export PYTHONPATH=$R/yamlab:$R/task/tools
export RT_TASK_DIR=$R/task
cd $R/work
T=$1; shift
exec nice -n 19 timeout $T python "$@"
