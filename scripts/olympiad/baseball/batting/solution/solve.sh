#!/bin/bash
# Oracle: a scripted camera-only batter (bat_player.py: ball detection in the two cameras, a fit of the documented
# flight model, the swing geometry of the documented rig) that plays the live game through the same service endpoints
# the `game` command uses. The runner starts the sidecar with RCB_PLAYER_MODE=oracle (no model is attached).
set -e
mkdir -p /app/output
python3 -c "import numpy, PIL" 2>/dev/null || pip install -q --no-cache-dir numpy==2.2.6 pillow==11.3.0
python3 /solution/oracle_play.py
