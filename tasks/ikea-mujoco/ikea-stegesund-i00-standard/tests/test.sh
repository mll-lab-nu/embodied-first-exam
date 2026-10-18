#!/bin/bash
# Verifier (separate sandbox, no network): the sim sidecar's artifacts were uploaded to /data by Harbor. grade.py
# transcribes final.json, the live episode's verdict (no grading replay), into reward.json / reward.txt.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md §2.6)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/protocol/README.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/protocol/README.md §2.6)
# The agent's files are untrusted input (PROTOCOL v2.0 H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \( -type l -o -type p -o -type s -o -type b -o -type c \) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py stegesund 2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
