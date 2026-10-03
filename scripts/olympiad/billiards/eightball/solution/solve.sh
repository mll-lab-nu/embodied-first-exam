#!/bin/bash
# Oracle: a scripted reference player that uses only the top camera image, the documented geometry and the rules (eight_player.py),
# playing through the same HTTP calls the `game` command makes.
set -e
mkdir -p /app/output
python3 -c "import numpy, scipy, PIL" 2>/dev/null || pip install -q --no-cache-dir numpy==2.2.6 scipy==1.15.3 pillow==11.3.0
python3 /solution/oracle_play.py
