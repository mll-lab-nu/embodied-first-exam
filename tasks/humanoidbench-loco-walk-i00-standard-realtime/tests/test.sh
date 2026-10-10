#!/bin/bash
# Verifier (separate sandbox): the sim sidecar's artifacts were uploaded to /data by Harbor.
mkdir -p /logs/verifier
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
python /tests/grade.py 2> /logs/verifier/grade.log
