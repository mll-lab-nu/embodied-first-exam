#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's container is gone (task.toml).
#   1. Wait for the service's PID file (after a crash it appears once the service has resumed the episode): up to 180 s.
#   2. SIGUSR1, re-sent every 30 s in case the service was restarting: the service ends the episode ("timeout" unless it
#      ended already) and replays it in a fresh process, which records the video on the way; the moment that replay has
#      executed the last action the verdict is in final.json ("deterministic" appears); the final frame and the encoder's
#      flush follow within seconds, then "finalized": true (rcb_service.py _finalize, server.py verify / render_video).
#   3. Stop waiting when final.json is finalized (PROTOCOL 4.8). Three backstops, none of which can misgrade (grade.py
#      reads "deterministic", not "finalized"):
#      - RCB_VIDEO_GRACE_S after the verdict is on disk, should the service hang finishing the video (it gives the video
#        120 s itself): the video is for humans and never decides the grade;
#      - RCB_FAIL_WAIT_S after the start for an episode that ended without a live success: it is a failure whatever its
#        replay says, so the replay (and its video) is evidence only;
#      - RCB_COLLECT_WAIT_S overall: a live success whose replay has not finished by then is graded infra_error.
#   The budget (docs/benchmarks/libero-max.md, "Collect budget"). The replay of N control steps takes B + N*s + V:
#     B  building the scene in the fresh process: 1-3 min on a busy sidecar                              <=  180 s
#     s  per control step (LIBERO renders its two observation cameras every step): 0.1 s on a quiet host, 0.5 s on a
#        busy batch host (measured: 2662 steps in 1415 s with B, no video); the 9000-step cap:  9000 x 0.5  = 4500 s
#     V  the video inside the replay: capped by lmx_tool (frames skipped when over budget)                <=  240 s
#   4920 s for a 9000-step live success on a busy host; RCB_COLLECT_WAIT_S = 5400 s leaves 480 s. The live episode ran
#   on this sidecar inside the agent's 3600 s at no less per step, so 5400 s also covers any episode whose replay is up
#   to (5400 - 180 - 240) / 3600 = 1.38x slower than its live run. task.toml: timeout_sec = 180 + 5400 + 120 = 5700.
# Prints final.json (the collect hook's output in the trial log).
DATA="${RCB_DATA:-/data}"; F="$DATA/final.json"
WAIT_S="${RCB_COLLECT_WAIT_S:-5400}"; GRACE_S="${RCB_VIDEO_GRACE_S:-300}"; FAIL_S="${RCB_FAIL_WAIT_S:-900}"
i=0
while [ ! -f "$DATA/server.pid" ] && [ "$i" -lt 180 ]; do sleep 2; i=$((i + 2)); done
start=$(date +%s); t=0; verdict_at=""; sig_at=-30   # t: wall-clock seconds in this loop
while [ "$t" -lt "$WAIT_S" ]; do
    grep -q '"finalized": true' "$F" 2>/dev/null && break
    if [ -z "$verdict_at" ] && grep -q '"deterministic"' "$F" 2>/dev/null; then verdict_at=$t; fi
    [ -n "$verdict_at" ] && [ $((t - verdict_at)) -ge "$GRACE_S" ] && { echo "[finalize] verdict in; stop waiting for the video"; break; }
    if [ "$t" -ge "$FAIL_S" ] && grep -q '"done": true' "$F" 2>/dev/null && grep -q '"live_success": false' "$F" 2>/dev/null; then
        echo "[finalize] the episode ended without a live success; stop waiting for its replay"; break
    fi
    if [ $((t - sig_at)) -ge 30 ]; then kill -USR1 "$(cat "$DATA/server.pid" 2>/dev/null)" 2>/dev/null; sig_at=$t; fi
    sleep 2; t=$(($(date +%s) - start))
done
cat "$F"
