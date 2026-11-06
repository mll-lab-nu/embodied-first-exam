#!/bin/sh
# Embodied First Exam: the verdict ends the session. Once the match service says the result is final (GET /over: full
# time, a no-show or a forfeit), every process of this container but its init is stopped (the collect hook's kill -9 -1),
# so the trial is graded without the session's dead time; the result is the one the service already decided.
( while :; do
    python3 -c 'import json, sys, urllib.request
sys.exit(0 if json.load(urllib.request.urlopen("http://localhost:8000/over", timeout=5)).get("over") else 1)' 2>/dev/null && break
    sleep 5
  done
  sleep 5
  kill -9 -1 ) &
exec "$@"
