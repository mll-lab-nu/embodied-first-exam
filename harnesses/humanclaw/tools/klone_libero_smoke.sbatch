#!/usr/bin/env bash
# Submit once using the eligible account/partition, e.g. gpu-l40s-stf/gpu-l40s.
#SBATCH --job-name=libero-framework-check
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077
source "${LIBERO_BENCH_ROOT:-/gscratch/stf/hengyil6/libero-bench}/framework/tools/klone_libero_env.sh"
cd "${LIBERO_BENCH_ROOT}/framework"
run_root="${LIBERO_BENCH_ROOT}/outputs/smoke-${SLURM_JOB_ID}"
mkdir -p "$run_root"
hostname
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
"${LIBERO_BENCH_ROOT}/venv/bin/python" -m humanclaw_bench.libero.doctor \
  --roborsi-root "${LIBERO_BENCH_ROOT}/RoboRSI" --output "$run_root/selfcheck"
if [[ "${LIBERO_SMOKE_DOCTOR_ONLY:-0}" == 1 ]]; then exit 0; fi
export ROBORSI_PYROKI_PORT=$((20000 + SLURM_JOB_ID % 20000))
export JAX_PLATFORMS=cpu
export JAX_COMPILATION_CACHE_DIR="${LIBERO_BENCH_ROOT}/data/jax-cache"
solver_started=$(date +%s)
"${LIBERO_BENCH_ROOT}/pyroki-managed/bin/python" \
  "${LIBERO_BENCH_ROOT}/RoboRSI/roborsi/embodied/motion/pyroki/server.py" > "$run_root/pyroki.log" 2>&1 &
pyroki_pid=$!
trap 'kill "$pyroki_pid" 2>/dev/null || true' EXIT
# Warm-up is bounded; a failed sidecar is an infrastructure failure, not an
# unnoticed switch to a different controller during the four-arm comparison.
for attempt in $(seq 1 180); do
  if grep -q 'serving on' "$run_root/pyroki.log"; then break; fi
  if ! kill -0 "$pyroki_pid" 2>/dev/null; then cat "$run_root/pyroki.log"; exit 1; fi
  sleep 2
done
grep -q 'serving on' "$run_root/pyroki.log"
/usr/bin/python3.12 - "$run_root" "$solver_started" <<'PY'
import json, os, pathlib, socket, sys, time
path = pathlib.Path(sys.argv[1]) / 'services.json'
path.write_text(json.dumps({'host': socket.gethostname(), 'job_id': os.environ['SLURM_JOB_ID'],
    'pyroki_startup_seconds': time.time()-int(sys.argv[2]),
    'pyroki_port': os.environ['ROBORSI_PYROKI_PORT'], 'shared_across_four_arms': True}, indent=2))
PY
export LIBERO_SHARED_SERVICE_MANIFEST="$run_root/services.json"
exit_status=0
for harness in bare codex pi roborsi; do
  "${LIBERO_BENCH_ROOT}/venv/bin/python" -m humanclaw_bench.libero.run run \
    --harness "$harness" --task libero_object_task/0 --seed 0 \
    --output "$run_root/$harness" --config configs/libero/klone.json \
    --roborsi-root "${LIBERO_BENCH_ROOT}/RoboRSI" \
    --env-file /gscratch/stf/hengyil6/HumanCLAW/.env \
    --max-calls 12 --max-control-steps 6000 || exit_status=1
done
"${LIBERO_BENCH_ROOT}/venv/bin/python" -m humanclaw_bench.libero.run report "$run_root"
exit "$exit_status"
