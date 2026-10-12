#!/bin/bash
# usage: run.sh <name> <script args...>  -> detached Isaac run on vast, log in logs/<name>.log
N=$1; shift
$(dirname $0)/vast_run.sh "bash src/tools/install_task.sh yamlab assets >/dev/null && (setsid nohup nice -n 19 timeout 5400 python $* > logs/$N.log 2>&1 < /dev/null &) ; echo launched $N"
