#!/bin/bash
# Oracle for either seat: a scripted reference player that uses only the house camera image and the documented ice model
# (curling_player.py), through the seat's HTTP interface.
set -e
mkdir -p /app/output
python3 -c "import numpy, scipy, PIL" 2>/dev/null || pip install -q --no-cache-dir numpy==2.2.6 scipy==1.15.3 pillow==11.3.0
python3 /solution/oracle_play.py
