#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's processes are stopped (task.toml).
#   1. Wait for the verdict. As soon as the service's PID file exists, send SIGUSR1 (again every 30 s, in case the
#      service was restarting): the service ends the episode ("timeout" unless it ended already), replays it in a fresh
#      simulator and writes the verdict with "finalized": true into final.json, in one atomic step (server_casa.py
#      finalize). This is all the grade needs, and all of the hook's time is available for it (RCB_COLLECT_WAIT_S).
#      Given up earlier only if the service never started an episode at all (no episode.jsonl after
#      RCB_COLLECT_START_S): there is nothing to grade then.
#   2. With the verdict on disk, wait for the optional replay video, which the service renders afterwards (a second
#      replay; /data/video.pending exists while it runs): at most as long again as the verdict took plus
#      RCB_VIDEO_MARGIN_S, and never past RCB_COLLECT_WAIT_S. The video is for people; a missing one changes no grade.
# Time is measured on the clock, not in loop turns. Budget (task.toml: timeout_sec = 3600, the agent's own budget):
#   verdict = one scene build (20-60 s) + one replay at about 0.035 s per control step (0.07 s on a busy host; measured
#   on oracle trials: both passes together 0.064-0.078 s per step). The live episode ran the same physics in the same
#   container, plus its cameras, so replaying it cannot take longer than the agent's hour did; 3450 s covers about
#   97,000 control steps (48,000 on a busy host) and leaves 150 s under the hook's timeout.
# Prints final.json (the collect hook's output in the trial log).
DATA="${RCB_DATA:-/data}"; F="$DATA/final.json"
WAIT_S="${RCB_COLLECT_WAIT_S:-3450}"; START_S="${RCB_COLLECT_START_S:-600}"; MARGIN_S="${RCB_VIDEO_MARGIN_S:-120}"
POLL_S="${RCB_COLLECT_POLL_S:-2}"
now() { date +%s; }
verdict() { grep -q '"finalized": true' "$F" 2>/dev/null; }
t0=$(now); sent=""
while ! verdict; do
    t=$(( $(now) - t0 ))
    if [ "$t" -ge "$WAIT_S" ]; then echo "[finalize] no verdict after ${t} s"; break; fi
    if [ ! -f "$DATA/episode.jsonl" ] && [ "$t" -ge "$START_S" ]; then
        echo "[finalize] the service started no episode in ${t} s"; break
    fi
    if [ -f "$DATA/server.pid" ] && { [ -z "$sent" ] || [ $((t - sent)) -ge 30 ]; }; then
        kill -USR1 "$(cat "$DATA/server.pid" 2>/dev/null)" 2>/dev/null; sent=$t
    fi
    sleep "$POLL_S"
done
if verdict; then
    lim=$(( 2 * ($(now) - t0) + MARGIN_S )); [ "$lim" -gt "$WAIT_S" ] && lim=$WAIT_S
    while [ -f "$DATA/video.pending" ]; do
        t=$(( $(now) - t0 ))
        if [ "$t" -ge "$lim" ]; then
            echo "[finalize] verdict in; the video is not ready after ${t} s, not waiting for it"; break
        fi
        sleep "$POLL_S"
    done
fi
cat "$F"
