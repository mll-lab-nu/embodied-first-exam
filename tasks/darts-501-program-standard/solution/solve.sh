#!/bin/bash
# Oracle: the reference player (solution/darts_ref.py: camera images and the documented physics only) through HTTP.
set -e
mkdir -p /app/output
cd /solution && python3 oracle_play.py
