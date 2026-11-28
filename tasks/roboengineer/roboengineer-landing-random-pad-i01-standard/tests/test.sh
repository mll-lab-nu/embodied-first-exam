#!/bin/bash
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
mkdir -p /logs/verifier
python /tests/grade.py
