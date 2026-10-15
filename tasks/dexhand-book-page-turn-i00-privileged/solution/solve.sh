#!/bin/bash
# Oracle (privileged mode): hand in the validated authoring trajectory (solution/trajectory.npz: actuator targets and
# the hand only). It lives in solution/ only, never in the agent image; the verifier replays it like any submission.
set -e
mkdir -p /app/output
cp /solution/oracle.py /app/output/gen.py
python /solution/oracle.py
