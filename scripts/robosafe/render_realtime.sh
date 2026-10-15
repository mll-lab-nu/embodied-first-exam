#!/usr/bin/env bash
# Freeze, check and render RoboSafeBench's standard-realtime tasks from a release image (docs/benchmarks/robosafe.md,
# "Standard-realtime tasks"). Run from the repository root of a checkout made with umask 022:
#     IMAGE=ghcr.io/mll-lab-nu/eai-robosafe:<VERSION> scripts/robosafe/render_realtime.sh
# 1. make_rt_instances.py in the image: the instances under the realtime clock, their start hashes, the reference,
#    nothing and `done` at once played under RCB's clock (instances_rt/, oracles_rt/)
# 2. check_double_build_rt.py in the image: start and end hashes built alone, beside a live Session and replayed in a
#    fresh process, paused and realtime (the gate: any difference stops here)
# 3. gen_realtime.py render (Python 3.11+, no simulator; it normalizes every task, which writes its DIGEST)
# 4. check_leaks.py (static, the task_text byte for byte) and check_rt_spec.py in the image (the served /spec)
# ENGINE (default podman) runs the image; JOBS (default 8) runs in parallel.
set -euo pipefail
umask 022
root="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE=${IMAGE:-ghcr.io/mll-lab-nu/eai-robosafe:$(cat "$root/images/robosafe/VERSION")}
ENGINE=${ENGINE:-podman}
JOBS=${JOBS:-8}
run() { "$ENGINE" run --rm -v "$root:/repo" -e MUJOCO_GL=osmesa -e PYOPENGL_PLATFORM=osmesa -w /tmp "$IMAGE" "$@"; }
if [ -z "${SKIP_FREEZE:-}" ]; then   # SKIP_FREEZE=1: instances_rt/ and oracles_rt/ are already frozen in this image
  echo "== freeze and play under the realtime clock ($IMAGE)"
  run python /repo/scripts/robosafe/make_rt_instances.py --jobs "$JOBS"
fi
echo "== double-build check"
run python /repo/scripts/robosafe/check_double_build_rt.py --jobs "$JOBS"
echo "== render"
python3 "$root/scripts/robosafe/gen_realtime.py" render
python3 "$root/scripts/robosafe/gen_realtime.py" check
python3 "$root/scripts/robosafe/check_leaks.py" "$root"/tasks/cell-*-standard-realtime      # static, task_text included
echo "== the served /spec of every rendered task"
run python /repo/scripts/robosafe/check_rt_spec.py
echo "done: commit scripts/robosafe/instances_rt/ oracles_rt/ and tasks/cell-*-standard-realtime (with their DIGEST)"
