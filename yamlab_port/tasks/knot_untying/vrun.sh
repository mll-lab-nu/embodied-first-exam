#!/bin/bash
# usage (on vast): vrun.sh <timeout_s> <script.py> [args...]   -- runs under nice 19 with the knot_untying env
R=/workspace/yamlab_port/runs/knot_untying
. /workspace/yamlab_port/env.sh
export PYTHONPATH=$R/yamlab
export KNOT_TASK_DIR=$R/task
cd $R/work
T=$1; shift
exec nice -n 19 timeout $T python "$@"
