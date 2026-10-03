#!/bin/bash
# Oracle: the privileged reference player (true shuttle state, via the oracle-only POST /oracle of the sim service,
# RCB_PLAYER_MODE=oracle) playing live against the wall clock through the same endpoints the `game` command uses.
set -e
mkdir -p /app/output
python3 /solution/oracle_play.py
