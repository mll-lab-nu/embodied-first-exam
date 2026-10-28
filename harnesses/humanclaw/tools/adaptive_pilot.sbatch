#!/usr/bin/env bash
#SBATCH --job-name=hc-adaptive-v1
#SBATCH --account=gpu-l40s-stf
#SBATCH --partition=gpu-l40s
#SBATCH --gres=gpu:l40s:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=40G
#SBATCH --time=03:00:00
#SBATCH --no-requeue
set -euo pipefail
umask 077
: "${HC_ADAPTIVE_COHORT:?Frozen cohort required}"
: "${SLURM_ARRAY_TASK_ID:?Submit via the pilot controller}"
export HC_ROOT=/gscratch/stf/hengyil6
export HC_REPO="${HC_ADAPTIVE_COHORT}/source"
export HC_PYTHON="${HC_ROOT}/envs/humanclaw/bin/python"
source "${HC_REPO}/tools/klone_env.sh"
export HC_ADAPTIVE_DEPS=/tmp/hc-adaptive-hengyil6-deps
export PYTHONPATH="${HC_REPO}/src:${HC_ADAPTIVE_DEPS}/python"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export HUMANCLAW_BWRAP="${HC_ROOT}/native-harnesses/20261015/bubblewrap/usr/bin/bwrap"
export HUMANCLAW_BWRAP_LD_LIBRARY_PATH="${HC_ROOT}/native-harnesses/20261015/lib"
export TMPDIR="/tmp/hc-adaptive-hengyil6-${SLURM_JOB_ID}"
mkdir -p "${TMPDIR}"
# Serialize cache extraction when both allocations land on the same GPU host.
(
  flock -x 9
  "${HC_PYTHON}" - <<'PY'
import hashlib, json, os, pathlib, tarfile
root = pathlib.Path(os.environ['HC_ADAPTIVE_COHORT'])
freeze = json.loads((root / 'freeze.json').read_text())
archive = pathlib.Path(freeze['dependency_archive'])
if hashlib.sha256(archive.read_bytes()).hexdigest() != freeze['dependency_archive_sha256']:
    raise SystemExit('Dependency archive hash mismatch')
destination = pathlib.Path(os.environ['HC_ADAPTIVE_DEPS'])
marker = destination / 'archive.sha256'
if not marker.is_file() or marker.read_text() != freeze['dependency_archive_sha256']:
    destination.mkdir(mode=0o700, exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter='data')
    marker.write_text(freeze['dependency_archive_sha256'])
PY
) 9>/tmp/hc-adaptive-hengyil6-deps.lock
cd "${HC_REPO}"
srun --ntasks=1 "${HC_PYTHON}" "${HC_REPO}/tools/adaptive_pilot.py" run-task "${HC_ADAPTIVE_COHORT}" --index "${SLURM_ARRAY_TASK_ID}"
