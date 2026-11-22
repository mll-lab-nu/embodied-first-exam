#!/bin/bash
# Oracle: the sport's reference player (builtin_players:OpenReference: camera images and /spec only) over HTTP through
# the core's client loop (ro_client.py = core/client.py); its live loop keeps observing and commanding until full time.
set -eo pipefail
mkdir -p /app/output
cd /solution && python3 -m ro_client --session || echo "solve.sh: ro_client --session failed; playing on" >&2
python3 oracle_play.py 2>&1 | tail -c 20000 > /app/output/oracle.log
