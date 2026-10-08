#!/usr/bin/env bash
# Re-grade / re-render trials whose verifier hit an infrastructure error (grader_error=1, or video_rendered=0 with a
# trajectory present) by running the task's own tests/ (same grader, fresh GPU container). The original reward.json
# is kept as reward.orig.json. Unlimited tasks only (limited tasks are graded by their sidecar's record).
#   scripts/regrade_trials.sh <job_dir>
set -u
JOB="$1"; R="$(cd "$(dirname "$0")/.." && pwd)"
for tr in "$JOB"/robotwin_2_0_*/; do
  rj="$tr/verifier/reward.json"; traj="$tr/artifacts/app/output/trajectory.npz"
  [ -f "$rj" ] || continue; [ -f "$traj" ] || continue
  ge=$(python3 -c "import json;d=json.load(open('$rj'));print(int(d.get('grader_error',0)))"); vr=$(python3 -c "import json;d=json.load(open('$rj'));print(int(d.get('video_rendered',0)))")
  [ "$ge" = 1 ] || [ "$vr" = 0 ] || continue
  task=$(python3 -c "import json;print(json.load(open('$tr/result.json'))['task_name'].split('/')[-1])"); case "$task" in *-standard|*-standard-realtime|*-limited) continue;; esac   # standard and standard-realtime: the sidecar grades
  case "$task" in *-privileged) ;; *) task="$task-privileged";; esac   # pre-v1.0 jobs
  fam=${task#robotwin_2_0_}; fam=${fam%-privileged}
  [ -d "$R/tasks/$task/tests" ] || { echo "skip $task: no tasks/$task/tests"; continue; }
  echo "re-grading $task (grader_error=$ge video_rendered=$vr)"
  cp -n "$rj" "$tr/verifier/reward.orig.json"
  docker run --rm --gpus all --shm-size 8g -v "$R/tasks/$task/tests:/tests:ro" -v "$tr/artifacts/app/output:/app/output:ro" -v "$tr/verifier:/logs/verifier" \
    -e PYTHONPATH=/tests:/opt/RoboTwin -w /opt/RoboTwin ghcr.io/mll-lab-nu/eai-robotwin:0.1.1 \
    bash -c "python /tests/grade.py --family $fam --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 2>/logs/verifier/grade.regrade.log; find /logs/verifier -user root -exec chown 1013:1014 {} +" 2>&1 | grep -v -E "NVIDIA|CUDA|====|icense|copy of|^$"
  echo "  -> $(cat "$rj")"
done
