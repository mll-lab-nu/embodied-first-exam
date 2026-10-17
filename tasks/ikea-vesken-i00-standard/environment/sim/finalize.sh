#!/bin/sh
# [[verifier.collect]] hook of the IKEA MuJoCo standard tasks (scripts/ikea_mujoco/standard/finalize.sh, copied unchanged),
# run inside the `sim` sidecar once Harbor has stopped the agent's container.
#   1. `rcb_limited.py end` (the shared first half): SIGUSR1 to the service, which ends the episode, writes trajectory.npz
#      and episode.json (live result, final-state hash, live_rows) and exits. It waits through a crash-recovery resume and
#      exits 2 when final.json already holds the verdict (the service gave up after crashes, or the instance mismatched).
#   2. final.json = episode.json + finalized. No replay here: the verifier sandbox replays trajectory.npz itself (two fresh
#      processes, the scene's own S.step and success.py) without network, and compares the final state with live_sha.
set -u
DATA="${RCB_DATA:-/data}"
python /srv/rcb_limited.py end "$DATA" --timeout "${RCB_COLLECT_END_TIMEOUT_S:-5400}"; rc=$?
if [ "$rc" = 2 ]; then
    echo "[finalize] final.json already holds the verdict"; exit 0
fi
RC="$rc" python - <<'PY'
import json, os
d = os.environ.get("RCB_DATA", "/data"); rc = os.environ.get("RC")
out = {}
try:
    out = json.load(open(os.path.join(d, "final.json")))
except Exception:
    pass
if rc == "0":
    try:
        out.update(json.load(open(os.path.join(d, "episode.json"))))
    except Exception as exc:
        out.update(infra_error=1, error=f"no episode.json: {exc!r}")
else:
    out.update(success=False, infra_error=1, error="collect hook: the sim service did not end and dump the episode in time")
out["finalized"] = True
out.setdefault("deterministic", None)   # decided by the verifier's replays (live_sha against the replayed state)
tmp = os.path.join(d, "final.json.tmp")
json.dump(out, open(tmp, "w")); os.replace(tmp, os.path.join(d, "final.json"))
print(json.dumps(out))
PY
