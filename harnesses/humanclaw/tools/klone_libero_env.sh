#!/usr/bin/env bash
# Dedicated LIBERO benchmark runtime; no HumanCLAW campaign files are modified.
export LIBERO_BENCH_ROOT="${LIBERO_BENCH_ROOT:-/gscratch/stf/hengyil6/libero-bench}"
export PYTHONPATH="${LIBERO_BENCH_ROOT}/framework/src:${LIBERO_BENCH_ROOT}/RoboRSI${PYTHONPATH:+:${PYTHONPATH}}"
export ROBORSI_LIBERO_ROOT="${LIBERO_BENCH_ROOT}/LIBERO-PRO"
export ROBORSI_LIBERO_BDDLDIR="${LIBERO_BENCH_ROOT}/data/LIBERO-Pro/bddl_files"
export ROBORSI_LIBERO_INITDIR="${LIBERO_BENCH_ROOT}/data/LIBERO-Pro/init_files"
export LIBERO_ASSETS_MANIFEST="${LIBERO_BENCH_ROOT}/data/assets_manifest.json"
export HUMANCLAW_GPFS_FILESET=nvme1-stf
export ROBORSI_PERCEPTION_DEVICE=cuda
export HF_HOME="${LIBERO_BENCH_ROOT}/data/huggingface"
export TORCH_HOME="${LIBERO_BENCH_ROOT}/data/torch"
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  export CUDA_CACHE_PATH="/tmp/libero-${UID}-${SLURM_JOB_ID}/cuda-cache"
  export __GL_SHADER_DISK_CACHE_PATH="/tmp/libero-${UID}-${SLURM_JOB_ID}/gl-cache"
  mkdir -p "$CUDA_CACHE_PATH" "$__GL_SHADER_DISK_CACHE_PATH"
fi
export __EGL_VENDOR_LIBRARY_DIRS=/etc/glvnd/egl_vendor.d:/usr/share/glvnd/egl_vendor.d
module load gcc/11.2.0 cuda/12.4.1 realitylab/glvnd/1.7.0
# This initial configuration uses upstream's local perception/analytic grasp
# fallback, identically for every arm. No optional SAM3/GraspGen service is used.
unset ROBORSI_SAM3_PORT ROBORSI_GRASPGEN_PORT
export GRASPGEN_PORT=""
if [[ -f "${LIBERO_BENCH_ROOT}/data/models_manifest.json" ]]; then
  eval "$(/usr/bin/python3.12 - "${LIBERO_BENCH_ROOT}/data/models_manifest.json" <<'PY'
import json, shlex, sys
for name, model in json.load(open(sys.argv[1])).items():
    print('export ' + name + '=' + shlex.quote(model['path']))
PY
)"
fi
