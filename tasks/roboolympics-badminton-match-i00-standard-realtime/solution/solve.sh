#!/bin/bash
# Oracle: the sport's RoboOlympics reference player (camera images, proprio and /spec only) through the agent's client.
set -e
mkdir -p /app/output
cd /solution && python3 oracle_play.py 2>&1 | tee /app/output/oracle.log
