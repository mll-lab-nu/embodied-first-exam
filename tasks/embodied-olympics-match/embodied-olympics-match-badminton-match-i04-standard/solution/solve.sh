#!/bin/bash
# Oracle on any seat: the sport's reference player.
set -e
mkdir -p /app/output
python3 -c "import numpy, PIL" 2>/dev/null || pip install -q --no-cache-dir -r /opt/client-requirements.txt
cd /solution && python3 oracle_play.py
