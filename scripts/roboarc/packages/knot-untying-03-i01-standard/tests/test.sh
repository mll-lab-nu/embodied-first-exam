#!/bin/bash
# Verifier (separate sandbox): the sim sidecar's artifacts were uploaded to /data by Harbor.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
