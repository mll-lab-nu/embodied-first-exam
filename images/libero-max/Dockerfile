# eai-libero-max: LIBERO-PRO (Zxy-MLlab/LIBERO-PRO @ 2b910b5, MIT: its LIBERO package and object assets) with the
# LIBERO-PRO task data (zhouxueyang/LIBERO-Pro @ c86fc3b, CC-BY-4.0: BDDL and initial-state files only) and LIBERO-MAX's
# event runtime (liberomax/LIBERO-MAX @ a1e3cef: src/libero_max and its source overlay only; no licence file upstream, used with its authors' permission (docs/benchmarks/libero-max.md),
# see docs/benchmarks/libero-max.md); robosuite 1.4.0 / MuJoCo 3.2.6; CPU physics (bit-exact replay) and CPU rendering
# (OSMesa): no GPU. One image for the LIBERO-MAX privileged tasks' environment and verifier and the standard sim service.
# Deliberately NOT included: demonstrations and LIBERO's dataset download utilities, LIBERO-MAX's policy runners,
# manifests, results and figures, every .git, and the Hugging Face client used to fetch the task data (last layers).
# Build from the repository root (the COPY names images/libero-max/...): see docs/benchmarks/libero-max.md.
FROM docker.io/library/python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 libglib2.0-0 \
    libmagickwand-6.q16-6 libexpat1 libfontconfig1 git && rm -rf /var/lib/apt/lists/*
COPY images/libero-max/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps --index-url https://download.pytorch.org/whl/cpu torch==2.2.2+cpu \
    && pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN git clone -q https://github.com/Zxy-MLlab/LIBERO-PRO.git /opt/libero-pro \
    && cd /opt/libero-pro && git checkout -q 2b910b5b5f53016bef9907632f6f840f1ce2229c \
    && rm -rf .git benchmark_scripts notebooks scripts tests images templates libero_ood perturbation.py \
       evaluation_config.yaml requirements.txt setup.py libero/libero/utils/download_utils.py \
    && find /opt/libero-pro -name "*.hdf5" -delete
RUN git clone -q https://github.com/liberomax/LIBERO-MAX.git /tmp/max \
    && cd /tmp/max && git checkout -q a1e3cef258b3e00487db5282aef4e36010aaf401 \
    && mkdir -p /opt/libero-max && cp -a src /opt/libero-max/src && cp -a scripts/libero_source_overlay /opt/libero-max/overlay \
    && rm -rf /tmp/max
RUN pip install --no-cache-dir huggingface_hub==0.24.6 \
    && python -c "from huggingface_hub import snapshot_download as d; d('zhouxueyang/LIBERO-Pro', repo_type='dataset', \
       revision='c86fc3b8293185a6f373677018ff3e37f8391602', local_dir='/opt/libero-pro-data', \
       allow_patterns=['bddl_files/**', 'init_files/**', 'metadata/**', 'README.md'])" \
    && rm -rf /opt/libero-pro-data/.cache /root/.cache && pip uninstall -y -q huggingface_hub \
    && mkdir -p /opt/libero-config && printf '%s\n' '{"assets": "/opt/libero-pro/libero/libero/assets", "bddl_files": "/opt/libero-pro-data/bddl_files", "benchmark_root": "/opt/libero-pro/libero/libero", "datasets": "/nonexistent", "init_states": "/opt/libero-pro-data/init_files"}' > /opt/libero-config/config.yaml \
    && printf '%s\n' 'LIBERO-PRO 2b910b5b5f53016bef9907632f6f840f1ce2229c' 'LIBERO-Pro data c86fc3b8293185a6f373677018ff3e37f8391602' 'LIBERO-MAX a1e3cef258b3e00487db5282aef4e36010aaf401' > /opt/libero-max-sources
ENV LIBERO_SOURCE_PACKAGE_ROOT=/opt/libero-pro/libero LIBERO_CONFIG_PATH=/opt/libero-config \
    PYTHONPATH=/opt/libero-max/overlay:/opt/libero-max/src
# Build-time checks (PROTOCOL §2.7): no demonstrations, no dataset downloader or links, no LIBERO-MAX runners or data.
RUN test -z "$(find /opt -name '*.hdf5' -o -name '.git' -o -name 'download_utils.py' | head -1)" \
    && ! grep -rqs "utexas.box.com\|download_libero_datasets" /opt/libero-pro /opt/libero-max \
    && test ! -e /opt/libero-max/scripts && test ! -e /opt/libero-max/benchmark \
    && python -c "import importlib.util as u; assert u.find_spec('huggingface_hub') is None" \
    && python -c "import mujoco, robosuite, torch; from libero.libero import benchmark; from libero_max.cosmos_integration import CosmosInterventionEnv; print('ok', mujoco.__version__, robosuite.__version__)"
WORKDIR /app
