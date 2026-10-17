#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's container is gone (task.toml).
#   1. Wait for the service's PID file (after a crash it appears once the service has resumed the episode): up to 180 s.
#   2. SIGUSR1, re-sent every 30 s in case the service was restarting: the service ends the episode ("timeout" unless it
#      ended already) and writes the verdict -- the live episode's, nothing is replayed (docs/PROTOCOL.md H.4; board
#      0151) -- with "finalized": true into final.json, within seconds of the signal (rcb_service.py _finalize).
#   3. Then the video: the service replays the trajectory once in a fresh process with the camera on (server.py
#      render_video), "video_pending": true while it does. The hook waits for it up to RCB_COLLECT_WAIT_S from its
#      start; the video is for humans and decides nothing: a verdict without it stands (grade.py reads "finalized").
#   The budget (docs/benchmarks/libero-max.md, "Grading (standard mode)"). The verdict needs no replay; only a service
#   that crashed late in the episode first replays its journal to resume it (rcb_service.py), at most N*s + B below.
#   The video pass of N control steps takes B + N*s + V:
#     B  building the scene in the fresh process: 1-3 min on a busy sidecar                              <=  180 s
#     s  per control step (LIBERO renders its two observation cameras every step): 0.1 s on a quiet host, 0.5 s on a
#        busy batch host (measured: 2662 steps in 1415 s with B, no video); the 9000-step cap:  9000 x 0.5  = 4500 s
#     V  the video's frames: capped by lmx_tool (frames skipped when over budget)                         <=  240 s
#   4920 s for a 9000-step episode on a busy host; RCB_COLLECT_WAIT_S = 5400 s leaves 480 s. A verdict not on disk by
#   then (a service that never came back) is infra_error (grade.py). task.toml: timeout_sec = 180 + 5400 + 120 = 5700.
# Prints final.json (the collect hook's output in the trial log).
DATA="${RCB_DATA:-/data}"; F="$DATA/final.json"
WAIT_S="${RCB_COLLECT_WAIT_S:-5400}"; POLL_S="${RCB_COLLECT_POLL_S:-2}"
i=0
while [ ! -f "$DATA/server.pid" ] && [ "$i" -lt 180 ]; do sleep 2; i=$((i + 2)); done
start=$(date +%s); t=0; sig_at=-30; said=""   # t: wall-clock seconds in this loop
while [ "$t" -lt "$WAIT_S" ]; do
    if grep -q '"finalized": true' "$F" 2>/dev/null; then
        grep -q '"video_pending": true' "$F" 2>/dev/null || break
        [ -z "$said" ] && { echo "[finalize] verdict in after ${t} s; waiting for the video"; said=1; }
    elif [ $((t - sig_at)) -ge 30 ]; then
        kill -USR1 "$(cat "$DATA/server.pid" 2>/dev/null)" 2>/dev/null; sig_at=$t
    fi
    sleep "$POLL_S"; t=$(($(date +%s) - start))
done
[ "$t" -ge "$WAIT_S" ] && echo "[finalize] stopped waiting after ${t} s"
cat "$F"
