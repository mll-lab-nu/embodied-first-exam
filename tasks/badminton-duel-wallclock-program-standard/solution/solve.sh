#!/bin/bash
# Oracle: the camera-only reference player for this seat (SEAT=A|B), through the seat's ordinary endpoints.
set -e
mkdir -p /app/output
python3 /solution/oracle_play.py
