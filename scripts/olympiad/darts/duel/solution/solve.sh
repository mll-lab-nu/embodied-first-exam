#!/bin/bash
# Oracle on either seat: the reference player (solution/darts_ref.py: camera images and the documented physics only).
set -e
mkdir -p /app/output
cd /solution && python3 oracle_play.py
