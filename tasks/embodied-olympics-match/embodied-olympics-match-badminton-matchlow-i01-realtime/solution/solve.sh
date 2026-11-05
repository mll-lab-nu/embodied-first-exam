#!/bin/bash
# Oracle on any seat: the sport's reference player.
set -e
mkdir -p /app/output
mkdir -p /app/output/skill
cp -r /solution/skill/. /app/output/skill/   # the reference skill: it plays the match in the loop
python3 -c "import numpy, PIL" 2>/dev/null || pip install -q --no-cache-dir -r /opt/client-requirements.txt
# core 0.2.34: the reference skill plays from the oracle's own skill server (its container)
game skill serve /app/output/skill
cd /solution && python3 oracle_play.py
