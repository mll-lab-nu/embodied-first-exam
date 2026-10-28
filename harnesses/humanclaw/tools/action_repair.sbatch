#!/usr/bin/env bash
# Selective corrected reruns; owned-result retention follows replacement_policy.json.
#SBATCH --job-name=hc-action-repair
#SBATCH --account=ckpt-stf
#SBATCH --partition=ckpt-all
#SBATCH --qos=ckpt-gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --requeue
#SBATCH --signal=INT@120
set -euo pipefail
umask 077
: "${HC_REPAIR_CONTROL:?Set the prepared campaign control directory}"
: "${SLURM_ARRAY_TASK_ID:?Submit a job array}"
export HC_ROOT=/gscratch/stf/hengyil6
export HC_PYTHON="${HC_ROOT}/envs/humanclaw/bin/python"
source "${HC_REPAIR_CONTROL}/klone_env.sh"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HUMANCLAW_GPFS_FILESET=sata1-scrubbed
export HUMANCLAW_GPFS_FILESYSTEM=gpfs
export HUMANCLAW_MIN_FREE_FILES=20000
export HUMANCLAW_MIN_FREE_BYTES=21474836480
export TMPDIR="${HC_REPAIR_CONTROL}/tmp/${SLURM_JOB_ID}-${SLURM_RESTART_COUNT:-0}"
mkdir -p "${TMPDIR}"
cd "${HC_REPAIR_CONTROL}"
exec srun --ntasks=1 "${HC_PYTHON}" -u "${HC_REPAIR_CONTROL}/action_repair.py" \
  worker "${HC_REPAIR_CONTROL}/prepared_plan.json" "${SLURM_ARRAY_TASK_ID}"
