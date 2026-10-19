#!/bin/bash
# Oracle (privileged mode): drive around the chairs' north side into the goal square, steering from the state.
set -e
mkdir -p /app/output
cp /solution/oracle.py /app/output/gen.py
python /solution/oracle.py
