#!/bin/bash
# Oracle: the reference player (solution/oracle_play.py) plays through the service's HTTP calls, like a player program.
set -e
mkdir -p /app/output
python3 /solution/oracle_play.py
