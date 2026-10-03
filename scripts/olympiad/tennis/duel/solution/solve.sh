#!/bin/bash
# Oracle (either seat): the camera-only scripted reference player of the single-player task, playing through this
# seat's endpoints (SEAT is set in the seat's container).
set -e
mkdir -p /app/output
python3 /solution/oracle_play.py
