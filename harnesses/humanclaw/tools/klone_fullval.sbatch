#!/usr/bin/env bash
# Frozen fullval shards; array size and concurrency are supplied at submission.
#SBATCH --job-name=humanclaw-fullval
#SBATCH --account=ckpt-stf
#SBATCH --partition=ckpt-all
#SBATCH --qos=ckpt-gpu
#SBATCH --gres=gpu:2080ti:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --requeue
#SBATCH --signal=INT@120

set -euo pipefail
umask 077
: "${HC_SUITE:?Set HC_SUITE to the prepared immutable suite directory.}"
: "${SLURM_ARRAY_TASK_ID:?Submit as a Slurm job array.}"
export HC_ROOT=/gscratch/stf/hengyil6
export HC_REPO="${HC_SUITE}/source"
export HC_PYTHON="${HC_ROOT}/envs/humanclaw/bin/python"
export HUMANCLAW_BENCH_HOME="${HC_REPO}"
export PYTHONPATH="${HC_REPO}/src"
export PYTHONDONTWRITEBYTECODE=1
export HUMANCLAW_GPFS_FILESET=nvme1-stf
export HUMANCLAW_GPFS_FILESYSTEM=gpfs
export HUMANCLAW_MIN_FREE_FILES=20000
export HUMANCLAW_MIN_FREE_BYTES=21474836480
HC_SHARD="${SLURM_ARRAY_TASK_ID}"
printf -v HC_OUTPUT '%s/results/shard-%04d' "${HC_SUITE}" "${HC_SHARD}"
export HC_OUTPUT
finish_allocation() {
  local task_code=$?
  trap - EXIT
  local task_status=failed
  "${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" storage "${HC_SUITE}" || task_code=75
  [[ "${task_code}" != 0 ]] || task_status=completed
  [[ "${task_code}" != 130 && "${task_code}" != 143 ]] || task_status=interrupted
  "${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" status "${HC_SUITE}" \
    --shard "${HC_SHARD}" --status "${task_status}" --exit-code "${task_code}" || true
  exit "${task_code}"
}
trap finish_allocation EXIT
"${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" storage "${HC_SUITE}"
"${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" status "${HC_SUITE}" --shard "${HC_SHARD}" --status preflight
"${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" verify "${HC_SUITE}" --shard "${HC_SHARD}"
source "${HC_REPO}/tools/klone_env.sh"
export TMPDIR="${HC_ROOT}/outputs/tmp-suite-${SLURM_JOB_ID}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
mkdir -p "${TMPDIR}" "${HC_OUTPUT}"
cd "${HC_REPO}"
"${HC_PYTHON}" - <<'PY'
import json
import os
from pathlib import Path
import socket
import subprocess
import torch
import habitat_sim
from humanclaw_bench.environment import load_project_environment

load_project_environment()
if not os.environ.get('AZURE_OPENAI_API_KEY'):
    raise SystemExit('Azure credential is missing.')
if not torch.cuda.is_available():
    raise SystemExit('CUDA is unavailable in the allocation.')
hardware = {
    'hostname': socket.gethostname(), 'gpu_name': torch.cuda.get_device_name(0),
    'torch': torch.__version__, 'cuda': torch.version.cuda,
    'driver': subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], text=True).splitlines(),
    'job_id': os.environ['SLURM_JOB_ID'], 'restart_count': os.environ.get('SLURM_RESTART_COUNT', '0'),
}
path = Path(os.environ['HC_OUTPUT']) / ('hardware-' + hardware['job_id'] + '-restart-' + hardware['restart_count'] + '.json')
path.write_text(json.dumps(hardware, indent=2) + '\n')
print(json.dumps(hardware))
PY
"${HC_PYTHON}" "${HC_REPO}/tools/klone_suite.py" status "${HC_SUITE}" --shard "${HC_SHARD}" --status running
srun --ntasks=1 "${HC_PYTHON}" -m humanclaw_bench run \
  --episodes "${HC_SUITE}/episodes/shard-${HC_SHARD}.json" \
  --profile "${HC_REPO}/configs/paper_fullval_v1.json" \
  --model-config "${HC_REPO}/configs/models/azure_gpt6_astra.json" \
  --scene-dataset-config "${HC_ROOT}/data/humanclaw-hssd-val41/hssd-hab.scene_dataset_config.json" \
  --harness humanclaw_psv --seed 0 --gpus auto --workers-per-gpu 1 \
  --trace --metrics --video --resume --output "${HC_OUTPUT}"
