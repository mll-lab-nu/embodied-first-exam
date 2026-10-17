#!/bin/bash
# Oracle on any seat: the sport's reference player.
set -e
mkdir -p /app/output
mkdir -p /app/output/skill
cp -r /solution/skill/. /app/output/skill/   # the reference skill: it plays the match in the loop
python3 -c "import numpy, PIL" 2>/dev/null || pip install -q --no-cache-dir -r /opt/client-requirements.txt
# core 0.2.32: the skill plays from the simulator's copy: upload it (retry until the service is up)
for i in $(seq 1 120); do game skill upload /app/output/skill > /tmp/upload.json 2>&1 && grep -q '"ok": true' /tmp/upload.json && break; sleep 5; done; cat /tmp/upload.json
cd /solution && python3 oracle_play.py
