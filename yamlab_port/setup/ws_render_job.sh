#!/bin/bash
# On ws: state-playback video of one oracle run (env var DUMPX = extra env args for both passes, e.g. --grasp_clamp --task_kwargs --assets_call m:f:a).
# usage: render_job.sh <family> <task_id> <run_label> <actions (container path)> [closeup specs...]
F=$1; TASK=$2; L=$3; ACT=$4; shift 4
CL=""; for c in "$@"; do CL="$CL --closeup $c"; done
T=$HOME/01_projects/04_code_robot_challenge/tmp/2026-10-12_yamlab
O=/data/out/$F
cd $T
YL_TIMEOUT=1800 bash run_in_container.sh ". /data/venv_vast/bin/activate && export TERM=xterm && mkdir -p $O && PYTHONPATH=/work/runs/$F/yamlab python -u render_states.py dump $DUMPX --task $TASK --actions $ACT --out $O/${L}_dump > $O/${L}_dump.log 2>&1"
grep -E "^DUMP |DUMP_TERMINATED|Traceback" /data/qineng/04_code_robot_challenge/2026-10-12_yamlab/out/$F/${L}_dump.log
YL_TIMEOUT=3600 bash run_in_container.sh ". /data/venv_vast/bin/activate && export TERM=xterm && PYTHONPATH=/work/runs/$F/yamlab python -u render_states.py render $DUMPX --task $TASK --states $O/${L}_dump/states_full.npz --out $O/${L}_video --frame_every 2 --fps 15 $CL > $O/${L}_video.log 2>&1"
grep -E "^RENDER|Traceback" /data/qineng/04_code_robot_challenge/2026-10-12_yamlab/out/$F/${L}_video.log
echo JOB_DONE $F $L
