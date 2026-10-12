#!/bin/bash
# Full evidence set for one tier on vast (at most 2 Isaac processes at a time):
#   checks.sh <prefix> <task> [oracle args...]
R=/workspace/yamlab_port/runs/fiber_bundling; cd $R
P=$1; T=$2; shift 2
bash task/run.sh ${P} --task $T --max_steps 8900 "$@" &
bash task/run.sh ${P}_nop --task $T --variant nop --max_steps 8990 &
wait
bash task/replay.sh ${P} ${P}_replay1 $T &
bash task/replay.sh ${P} ${P}_replay2 $T &
wait
bash task/run.sh ${P}_naive_nocomb --task $T --variant naive_nocomb --max_steps 8900 "$@" &
bash task/run.sh ${P}_naive_off12 --task $T --variant naive_offset --naive_offset_m 0.012 --max_steps 8900 "$@" &
wait
echo ALLDONE > $R/out/${P}_checks.done
