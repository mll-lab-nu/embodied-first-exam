#!/bin/bash
# Oracle (standard mode) of a task that packages a reference solution for more than one hand: submit the validated
# authoring trajectory of the hand the robot service runs (spec()["hand"], set by DEXHAND_HAND on the sim service):
# solution/<hand>/ when the task has one for that hand, else solution/ (the Sharpa Wave rows), one row per control, as
# `joint_position` chunks through the same client an agent has. No privileged information is used.
set -e
HAND=$(python -c 'from rcb_client import Robot; print(Robot(timeout=3600).spec().get("hand", "sharpa"))')
DIR=/solution
case "$HAND" in
    sharpa | *[!a-z0-9_]*) ;;
    *) if [ -f "/solution/$HAND/oracle_replay.py" ]; then DIR="/solution/$HAND"; fi ;;
esac
mkdir -p /app/output
cp "$DIR/oracle_replay.py" /app/output/gen.py
python "$DIR/oracle_replay.py"
