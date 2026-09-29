#!/usr/bin/env bash
# Re-grade / re-render trials whose verifier hit an infrastructure error (grader_error=1, or video_rendered=0 with a
# trajectory present) by running the task's own tests/ (same grader, fresh GPU container). The original reward.json
# is kept as reward.orig.json. Unlimited tasks only (limited tasks are graded by their sidecar's record).
#   scripts/regrade_trials.sh <job_dir>
# TopoGym (adapted from robot_coding_bench fa59c1a6): topogym-* trials, the rcb-topogym image, the family from the task's
# tests/instance.json, the NVIDIA graphics libraries for Nyx's Vulkan renderer, and the verifier files handed back to the
# calling user; a relative <job_dir> works too (docker -v needs an absolute host path).
set -u
JOB="$(cd "$1" && pwd)"; R="$(cd "$(dirname "$0")/.." && pwd)"   # absolute: docker -v takes host paths only
for tr in "$JOB"/topogym-*/; do
  rj="$tr/verifier/reward.json"; traj="$tr/artifacts/app/output/trajectory.npz"
  [ -f "$rj" ] || continue; [ -f "$traj" ] || continue
  ge=$(python3 -c "import json;d=json.load(open('$rj'));print(int(d.get('grader_error',0)))"); vr=$(python3 -c "import json;d=json.load(open('$rj'));print(int(d.get('video_rendered',0)))")
  [ "$ge" = 1 ] || [ "$vr" = 0 ] || continue
  task=$(python3 -c "import json;print(json.load(open('$tr/result.json'))['task_name'].split('/')[-1])")
  case "$task" in *-limited) continue;; esac
  fam=$(python3 -c "import json;print(json.load(open('$R/tasks/$task/tests/instance.json'))['task'])")
  img=$(awk '/^FROM /{print $2; exit}' "$R/tasks/$task/tests/Dockerfile")
  echo "re-grading $task (grader_error=$ge video_rendered=$vr)"
  cp -n "$rj" "$tr/verifier/reward.orig.json"
  docker run --rm --runtime nvidia --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all --shm-size 8g -v "$R/tasks/$task/tests:/tests:ro" -v "$tr/artifacts/app/output:/app/output:ro" -v "$tr/verifier:/logs/verifier" \
    -e PYTHONPATH=/tests:/opt/topogym -w /tmp "$img" \
    bash -c "python /tests/grade.py --family $fam --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 2>/logs/verifier/grade.regrade.log; find /logs/verifier -user root -exec chown $(id -u):$(id -g) {} +" 2>&1 | grep -v -E "NVIDIA|CUDA|====|icense|copy of|^$"
  echo "  -> $(cat "$rj")"
done
