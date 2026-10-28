#!/usr/bin/env bash
# A CPU-only report runs after all array tasks terminate, including failures.
#SBATCH --job-name=humanclaw-fullval-report
#SBATCH --account=ckpt-stf
#SBATCH --partition=ckpt-all
#SBATCH --qos=ckpt
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --requeue

set -euo pipefail
umask 077
: "${HC_SUITE:?Set HC_SUITE to the prepared immutable suite directory.}"
export HUMANCLAW_BENCH_HOME="${HC_SUITE}/source"
export PYTHONPATH="${HC_SUITE}/source/src"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
/gscratch/stf/hengyil6/envs/humanclaw/bin/python \
  "${HC_SUITE}/source/tools/klone_suite.py" report "${HC_SUITE}"
