#!/bin/bash
# Oracle: the reference shooter (solution/bb_ref.py: camera images and the documented physics only) on either seat.
set -e
mkdir -p /app/output
cd /solution && python3 oracle_play.py
