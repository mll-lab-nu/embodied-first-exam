#!/bin/bash
# Oracle (privileged mode) of a task that packages a reference solution for more than one hand: hand in the validated
# authoring trajectory of the hand the run selects (DEXHAND_HAND, default sharpa, as for Session()): solution/<hand>/
# when the task has one for that hand, else solution/ (the Sharpa Wave rows). Actuator targets and the hand only; it
# lives in solution/ only, never in the agent image; the verifier replays it like any submission.
set -e
HAND="${DEXHAND_HAND:-sharpa}"
DIR=/solution
case "$HAND" in
    sharpa | *[!a-z0-9_]*) ;;
    *) if [ -f "/solution/$HAND/oracle.py" ]; then DIR="/solution/$HAND"; fi ;;
esac
mkdir -p /app/output
cp "$DIR/oracle.py" /app/output/gen.py
python "$DIR/oracle.py"
