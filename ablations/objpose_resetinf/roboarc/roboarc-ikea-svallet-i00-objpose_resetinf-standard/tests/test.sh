#!/bin/bash
# Verifier (separate sandbox, no network): the sim sidecar's artifacts were uploaded to /data by Harbor. grade.py
# transcribes final.json, the live episode's verdict (no grading replay), into reward.json / reward.txt.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
# The agent's files are untrusted input (PROTOCOL v2.0 H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \( -type l -o -type p -o -type s -o -type b -o -type c \) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py svallet 2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
