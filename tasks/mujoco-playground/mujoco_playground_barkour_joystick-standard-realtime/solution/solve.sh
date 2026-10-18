#!/bin/bash
# Oracle (standard-realtime mode): plans the reference trajectory's joint targets (solution/oracle.npy, one row per
# control step) into the episode from its first control step (`submit(..., at=0)`, which starts the clock). Uses no
# privileged information at run time; the rows run at the same control steps as in the privileged replay.
set -e
mkdir -p /app/output
cp /solution/oracle_plan.py /app/output/gen.py
python /solution/oracle_plan.py
