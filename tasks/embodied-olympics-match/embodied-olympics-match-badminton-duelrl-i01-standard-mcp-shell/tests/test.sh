#!/bin/bash
# Verifier (separate sandbox): the sim sidecar's artifacts were uploaded to /data by Harbor.
mkdir -p /logs/verifier
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
python /tests/grade.py 2> /logs/verifier/grade.log
printf '0\n' > /logs/verifier/reward.txt   # a duel's success needs A_won: never grade.py's valid_trial alone, even for a moment
python /tests/fexam_reward.py 2>> /logs/verifier/grade.log || { printf '0\n' > /logs/verifier/reward.txt; printf '{"success": 0, "grader_error": 1, "infra_error": 1}' > /logs/verifier/reward.json; }   # a duel's success needs A_won (fexam_reward.py): never grade.py's valid_trial alone
