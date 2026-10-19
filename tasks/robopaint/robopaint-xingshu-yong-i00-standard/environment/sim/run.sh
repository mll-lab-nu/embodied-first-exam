#!/bin/sh
# eai-standard/2.2 sidecar entrypoint: PID 1 of the `sim` container, shared by every 2.2 service
# (scripts/eai_standard/run.sh, copied unchanged into each standard task's environment/sim/).
# - The service crashed (a non-zero exit: an exception, a signal, the startup watchdog): exit with its code, so compose
#   restarts the container (`restart: on-failure:6`) and the service resumes the same episode from its journal
#   (rcb_limited.Episode). The container keeps its /data (or /out) across the restart.
# - The service exited cleanly (0: it dumped its episode on the collect hook's SIGUSR1 and released the simulator): keep
#   the container up for the collect hook's fresh-process replays. If the service were PID 1 itself, that exit would
#   stop the container and kill the hook with it (Harbor reports exit 137).
# - Everything the service prints also goes to $RCB_DATA/server.log (an artifact: Harbor keeps no sidecar output, and a
#   simulator that dies while it loads leaves no other trace).
DATA="${RCB_DATA:-/data}"
mkdir -p "$DATA"
rm -f "$DATA/.service_rc"
{ python -u "${RCB_SERVER:-/srv/server.py}" 2>&1; echo "$?" > "$DATA/.service_rc"; } | tee -a "$DATA/server.log"
rc="$(cat "$DATA/.service_rc" 2>/dev/null)"; rc="${rc:-1}"
if [ "$rc" != 0 ]; then
  echo "[sim] service exited ($rc): leaving, so compose restarts the container (the service resumes the episode if one began)" | tee -a "$DATA/server.log"
  exit "$rc"
fi
echo "[sim] service exited (0); holding the container open for the collect hook" | tee -a "$DATA/server.log"
while true; do sleep 3600; done
