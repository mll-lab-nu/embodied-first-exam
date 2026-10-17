#!/bin/sh
# End the trusted episode before two fresh-process replays; a video never decides the verdict.
set -u
RCB_COLLECT_T0=$(date +%s) export RCB_COLLECT_T0   # finalize.py bounds the replay video by the hook's timeout
RCB_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$RCB_SCRIPT_DIR/rcb_limited.py" end "${RCB_DATA:-/data}" --timeout 300
RCB_END_RC=$? export RCB_END_RC
python "$RCB_SCRIPT_DIR/finalize.py"
