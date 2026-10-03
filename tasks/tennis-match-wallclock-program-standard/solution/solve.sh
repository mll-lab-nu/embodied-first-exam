#!/bin/bash
# Oracle: a perception-based scripted reference player (camera images + spec intrinsics + documented physics only, no
# ball state, no simulator) that plays the wall-clock match through the same service endpoints the `game` command
# uses (oracle_play.py, tn_player.py).
set -e
mkdir -p /app/output
python3 -c "import numpy, PIL" 2>/dev/null || pip install -q --no-cache-dir numpy==2.2.6 pillow==11.3.0
python3 /solution/oracle_play.py
