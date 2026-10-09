#!/bin/sh
# [[verifier.collect]] hook, run inside the `sim` sidecar once the agent's container is gone (task.toml).
#   1. Wait for the service's PID file (after a crash it appears once the service has resumed the episode).
#   2. SIGUSR1, re-sent every 30 s in case the service was restarting: the service ends the episode ("timeout" unless it
#      ended already), replays it in a fresh simulator, writes the verdict to final.json ("deterministic" appears), then
#      renders the replay video and sets "finalized": true (rcb_service.py _finalize).
#   3. Stop waiting when final.json is finalized, or
#      - RCB_VIDEO_GRACE_S after the verdict is on disk: the video is for humans and never decides the grade (grade.py);
#      - RCB_FAIL_WAIT_S after the start for an episode that ended without a live success: it is a failure whatever its
#        replay says, so the replay is evidence only;
#      - RCB_COLLECT_WAIT_S overall: a live success whose replay has not finished by then is graded infra_error.
#   The fresh replay renders the scene's cameras every control step (LIBERO's OffScreenRenderEnv), about 0.1-0.25 s per
#   step on a busy 4-CPU sidecar plus 1-3 min to build the scene: 3000 s covers the 9000-step episode cap.
# Prints final.json (the collect hook's output in the trial log).
DATA="${RCB_DATA:-/data}"; F="$DATA/final.json"
WAIT_S="${RCB_COLLECT_WAIT_S:-3000}"; GRACE_S="${RCB_VIDEO_GRACE_S:-300}"; FAIL_S="${RCB_FAIL_WAIT_S:-900}"
i=0
while [ ! -f "$DATA/server.pid" ] && [ "$i" -lt 180 ]; do sleep 2; i=$((i + 2)); done
t=0; verdict_at=""
while [ "$t" -lt "$WAIT_S" ]; do
    grep -q '"finalized": true' "$F" 2>/dev/null && break
    if [ -z "$verdict_at" ] && grep -q '"deterministic"' "$F" 2>/dev/null; then verdict_at=$t; fi
    [ -n "$verdict_at" ] && [ $((t - verdict_at)) -ge "$GRACE_S" ] && { echo "[finalize] verdict in; stop waiting for the video"; break; }
    if [ "$t" -ge "$FAIL_S" ] && grep -q '"done": true' "$F" 2>/dev/null && grep -q '"live_success": false' "$F" 2>/dev/null; then
        echo "[finalize] the episode ended without a live success; stop waiting for its replay"; break
    fi
    [ $((t % 30)) -eq 0 ] && kill -USR1 "$(cat "$DATA/server.pid" 2>/dev/null)" 2>/dev/null
    sleep 2; t=$((t + 2))
done
cat "$F"
