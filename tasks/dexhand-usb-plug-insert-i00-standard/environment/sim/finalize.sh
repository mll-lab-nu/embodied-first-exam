#!/bin/sh
# End the trusted episode and write its live verdict (finalize.py); then one video-only render pass, which never
# decides anything. No grading replay (board 0151).
set -u
RCB_COLLECT_T0=$(date +%s) export RCB_COLLECT_T0   # finalize.py bounds the video by the hook's timeout
RCB_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$RCB_SCRIPT_DIR/rcb_limited.py" end "${RCB_DATA:-/data}" --timeout 300
RCB_END_RC=$? export RCB_END_RC
python "$RCB_SCRIPT_DIR/finalize.py"
