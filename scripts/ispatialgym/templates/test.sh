#!/bin/bash
# Verifier (separate sandbox): grades the sim sidecar's own record, uploaded by Harbor from the sidecar's /out.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
