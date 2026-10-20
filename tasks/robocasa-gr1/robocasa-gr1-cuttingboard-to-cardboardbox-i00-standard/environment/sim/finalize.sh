#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's processes are stopped (task.toml).
#   1. Wait for the verdict. As soon as the service's PID file exists, send SIGUSR1 (again every 30 s, in case the
#      service was restarting): the service ends the episode ("timeout" unless it ended already) and writes the live
#      episode's verdict with "finalized": true into final.json, in one atomic step (server_casa.py finalize; nothing is
#      replayed to grade it). That takes a second; the wait is long only for a service that crashed late
#      in the episode: it resumes the SAME episode by replaying its journal first (crash recovery, at most the
#      episode's own physics), and a wait cut short there would turn a live result into an infrastructure failure.
#      Given up earlier only if the service never started an episode at all (no episode.jsonl after
#      RCB_COLLECT_START_S): there is nothing to grade then.
#   2. With the verdict on disk, wait for the optional video, which the service renders afterwards from the recorded
#      trajectory (one render pass; /data/video.pending exists while it runs), for the rest of RCB_COLLECT_WAIT_S. The
#      video is for people; a missing one changes no grade.
# Time is measured on the clock, not in loop turns. Budget (task.toml: timeout_sec = 3600, the agent's own budget): the
#   render pass = one scene build (20-60 s) + the episode's physics once more at about 0.035 s per control step (0.07 s
#   on a busy host) + at most about 300 frames. The live episode ran the same physics in the same container, plus its
#   cameras, so its physics cannot take longer than the agent's hour did; 3450 s covers about 95,000 control steps
#   (48,000 on a busy host) and leaves 150 s under the hook's timeout. A resume replay before the verdict comes out of
#   the same budget.
# Prints final.json (the collect hook's output in the trial log).
DATA="${RCB_DATA:-/data}"; F="$DATA/final.json"
WAIT_S="${RCB_COLLECT_WAIT_S:-3450}"; START_S="${RCB_COLLECT_START_S:-600}"
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
    echo "[finalize] verdict in after $(( $(now) - t0 )) s"
    while [ -f "$DATA/video.pending" ]; do
        t=$(( $(now) - t0 ))
        if [ "$t" -ge "$WAIT_S" ]; then
            echo "[finalize] verdict in; the video is not ready after ${t} s, not waiting for it"; break
        fi
        sleep "$POLL_S"
    done
fi
cat "$F"
