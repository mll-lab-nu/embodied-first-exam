#!/usr/bin/env bash
# Serial, resumable manager launcher. Native Harbor remains the executor/grader.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${TOPOGYM_PYTHON:-$ROOT/.venv-gs121-nyx/bin/python}"
HARBOR="${TOPOGYM_HARBOR:-$ROOT/.venv-harbor/bin/harbor}"
families="cast_coil,cast_keyhole,lock_picking,buzz_wire_3d,fiber_bundling,horseshoe_ring,hedgehog_in_cage,interlocked_claws,blanket_flatten,rope_threading,knot_untying"
tiers="easy,medium,hard"
output= tasks_root= gpu=0 smoke=0 wall=0 resume=0 plan=0
gpu_wait=600 gpu_free=12000
usage() {
  cat <<'EOF'
Usage: bash bash_scripts/run_harbor_oracle_grades.sh --output DIR [options]

Defaults: 11 families (excluding Orbits/Slotted Post Ring), easy/medium/hard,
serial privileged + standard, full oracle grading, no nop controls.

  --families CSV       e.g. cast_coil,cast_keyhole
  --tiers CSV          easy,medium,hard only
  --tasks-root DIR     Use existing current-version bound candidates; skip builds
                      Otherwise prepare/build new candidates in OUTPUT/candidate
  --gpu ID             Candidate generation GPU (default 0; Harbor uses task config)
  --gpu-wait-seconds N Wait for idle GPU before builds (default 600)
  --gpu-min-free-mb N  Minimum free GPU memory before builds (default 12000)
  --smoke-steps N      Grade N real oracle controls instead of the full solution
                      A smoke pass is NOT grade 1 or a solvability proof
  --wall-seconds N     Total Harbor time per family/tier, both modes (default unset)
  --resume            Reuse this exact queue; skip completed results, retain failures
  --plan              Print the queue without starting Docker or creating output
  --help              Show this help

Output: summary.tsv, summary.json, queue.json, trials/<family>/<tier>/attempt-*/
Each attempt contains results.json, native rewards, logs, trajectories and videos.
A full privileged failure blocks its standard twin; subsequent tasks still run.
Use a NEW output directory to retry completed failures. Never overwrite evidence.
TOPOGYM_PYTHON and TOPOGYM_HARBOR can override the local executable paths.
EOF
}
while (($#)); do
  case "$1" in
    --output) output="${2:?--output requires a directory}"; shift 2 ;;
    --tasks-root) tasks_root="${2:?--tasks-root requires a directory}"; shift 2 ;;
    --families) families="${2:?--families requires CSV}"; shift 2 ;;
    --tiers) tiers="${2:?--tiers requires CSV}"; shift 2 ;;
    --gpu) gpu="${2:?--gpu requires an ID}"; shift 2 ;;
    --gpu-wait-seconds) gpu_wait="${2:?}"; shift 2 ;;
    --gpu-min-free-mb) gpu_free="${2:?}"; shift 2 ;;
    --smoke-steps) smoke="${2:?}"; shift 2 ;;
    --wall-seconds) wall="${2:?}"; shift 2 ;;
    --resume) resume=1; shift ;;
    --plan) plan=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$output" ]] || { usage >&2; exit 2; }
[[ -x "$PYTHON" ]] || { printf 'Missing Python: %s\n' "$PYTHON" >&2; exit 2; }
for value in "$smoke" "$wall" "$gpu_wait" "$gpu_free"; do
  [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]] || { printf 'Expected nonnegative integer: %s\n' "$value" >&2; exit 2; }
done
((smoke <= 1000)) || { printf 'smoke-steps must be 1..1000\n' >&2; exit 2; }
IFS=',' read -r -a family_list <<< "$families"
IFS=',' read -r -a tier_list <<< "$tiers"
declare -A seen=()
for family in "${family_list[@]}"; do
  case "$family" in
    cast_coil|cast_keyhole|lock_picking|buzz_wire_3d|fiber_bundling|horseshoe_ring|hedgehog_in_cage|interlocked_claws|blanket_flatten|rope_threading|knot_untying) ;;
    *) printf 'Unsupported family: %s\n' "$family" >&2; exit 2 ;;
  esac
  [[ -z "${seen[$family]:-}" ]] || { printf 'Duplicate family: %s\n' "$family" >&2; exit 2; }
  seen[$family]=1
done
seen=()
for tier in "${tier_list[@]}"; do
  case "$tier" in easy|medium|hard) ;; *) printf 'Unsupported tier: %s\n' "$tier" >&2; exit 2 ;; esac
  [[ -z "${seen[$tier]:-}" ]] || { printf 'Duplicate tier: %s\n' "$tier" >&2; exit 2; }
  seen[$tier]=1
done
if ((plan)); then
  for family in "${family_list[@]}"; do
    for tier in "${tier_list[@]}"; do printf '%s\t%s\tprivileged -> standard\n' "$family" "$tier"; done
  done
  exit 0
fi
[[ -x "$HARBOR" ]] || { printf 'Missing Harbor: %s\n' "$HARBOR" >&2; exit 2; }
output="$(realpath -m -- "$output")"
if [[ -n "$tasks_root" ]]; then tasks_root="$(realpath -e -- "$tasks_root")"; fi
if ((resume)); then
  [[ -f "$output/queue.json" ]] || { printf 'No queue to resume: %s\n' "$output" >&2; exit 2; }
else
  [[ ! -e "$output" ]] || { printf 'Output already exists; use --resume or a new directory: %s\n' "$output" >&2; exit 2; }
  mkdir -p -- "$output"
fi
exec 9>"$output/.queue.lock"
flock -n 9 || { printf 'Another process owns this queue\n' >&2; exit 2; }
cd -- "$ROOT"
"$PYTHON" - "$output" "$families" "$tiers" "$tasks_root" "$gpu" "$smoke" "$wall" "$HARBOR" <<'PY'
import json,sys
from pathlib import Path
out,families,tiers,task_root,gpu,smoke,wall,harbor=sys.argv[1:]
queue=dict(families=families.split(','),tiers=tiers.split(','),tasks_root=task_root,gpu=gpu,
           smoke_steps=int(smoke),wall_seconds=int(wall),harbor=harbor)
p=Path(out)/'queue.json'
if p.exists() and json.loads(p.read_text()) != queue:
    raise SystemExit('Resume options differ from queue.json; use the original options or a new output')
p.write_text(json.dumps(queue,indent=2)+'\n')
PY
summarize() {
  "$PYTHON" - "$output" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); queue=json.loads((root/'queue.json').read_text()); rows=[]
for tier in queue['tiers']:
    for family in queue['families']:
        attempts=sorted(p for p in (root/'trials'/family/tier).glob('attempt-*') if p.is_dir())
        attempt=attempts[-1] if attempts else None
        path=attempt/'results.json' if attempt else None
        d=json.loads(path.read_text()) if path and path.exists() else {}
        tasks={r['mode']:r for r in d.get('tasks',[])}
        for mode in ('privileged','standard'):
            r=tasks.get(mode,{})
            errors=list(r.get('errors',[]))
            for run in r.get('runs',[]): errors.extend(run.get('errors',[]))
            rows.append(dict(family=family,tier=tier,mode=mode,status=r.get('status','not_run'),
                             grade=r.get('grade'),errors=errors,results=str(path) if path else None))
wanted='smoke_passed' if queue['smoke_steps'] else 'passed'
doc=dict(scope='connectivity smoke' if queue['smoke_steps'] else 'full native oracle grading',
         all_passed=bool(rows) and all(r['status']==wanted for r in rows),tasks=rows)
for name,data in [('summary.json',json.dumps(doc,indent=2)+'\n'),
                  ('summary.tsv','family\ttier\tmode\tstatus\tgrade\tresults\n'+''.join(
                      '\t'.join(str(r[k]) if r[k] is not None else '' for k in ('family','tier','mode','status','grade','results'))+'\n' for r in rows))]:
    p=root/name; temp=p.with_suffix('.tmp'); temp.write_text(data); temp.replace(p)
PY
}
trap 'summarize; exit 130' INT
trap 'summarize; exit 143' TERM
build=0
if [[ -z "$tasks_root" ]]; then
  build=1
  tasks_root="$output/candidate/tasks"
  if [[ ! -f "$output/candidate/candidate.json" ]]; then
    "$PYTHON" scripts/topogym_merge_candidate.py --output "$output/candidate" \
      --families "${family_list[@]}" --tiers "${tier_list[@]}" --gpu "$gpu"
  fi
fi
summarize
for family in "${family_list[@]}"; do
  if ((build)); then
    log="$output/build-${family}-$(date -u +%Y%m%dT%H%M%S).log"
    printf 'Building %s; %s\n' "$family" "$log"
    if ! "$PYTHON" scripts/topogym_candidate_pipeline.py --candidate "$output/candidate" \
        --phase build --families "$family" --gpu "$gpu" --gpu-wait-s "$gpu_wait" \
        --gpu-min-free-mb "$gpu_free" >"$log" 2>&1; then
      printf 'Build incomplete for %s; keeping logs and checking any completed pairs\n' "$family" >&2
    fi
  fi
  for tier in "${tier_list[@]}"; do
    case_root="$output/trials/$family/$tier"
    if ((resume)) && "$PYTHON" - "$case_root" <<'PY'
import json,sys
from pathlib import Path
paths=sorted(Path(sys.argv[1]).glob('attempt-*/results.json'))
raise SystemExit(0 if paths and json.loads(paths[-1].read_text()).get('status')=='complete' else 1)
PY
    then
      printf 'Already completed: %s %s (existing result retained)\n' "$family" "$tier"
      continue
    fi
    slug="topogym-${family//_/-}-${tier}-i00"
    if [[ ! -f "$tasks_root/$slug-privileged/task_release.json" || ! -f "$tasks_root/$slug-standard/task_release.json" ]]; then
      printf 'Missing bound candidate pair: %s; see build logs\n' "$slug" >&2
      continue
    fi
    mkdir -p -- "$case_root"
    attempt="$case_root/attempt-$(date -u +%Y%m%dT%H%M%S)-$$"
    command=("$PYTHON" scripts/oracle_runners/test_harbor_oracles.py --output "$attempt"
      --tasks-root "$tasks_root" --candidate --families "$family" --tiers "$tier"
      --modes privileged standard --harbor "$HARBOR" --no-nop --execute)
    if ((smoke)); then command+=(--smoke-steps "$smoke"); fi
    if ((wall)); then command+=(--wall-seconds "$wall"); fi
    printf 'Grading %s %s; %s\n' "$family" "$tier" "$attempt"
    if "${command[@]}" >"$attempt.dispatch.log" 2>&1; then
      printf 'Completed and passed the selected scope: %s %s\n' "$family" "$tier"
    else
      printf 'Nonpassing result: %s %s; see %s.dispatch.log and results.json\n' "$family" "$tier" "$attempt" >&2
    fi
    summarize
  done
done
summarize
printf 'Summary: %s/summary.tsv\n' "$output"
"$PYTHON" - "$output/summary.json" <<'PY'
import json,sys
raise SystemExit(0 if json.load(open(sys.argv[1]))['all_passed'] else 1)
PY
