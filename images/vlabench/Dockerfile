# vlabench: VLABench (OpenMOSS/VLABench @ cf588fe) on MuJoCo 3.2.2 / dm_control 1.0.22 with its pinned assets
# (lerobot/vlabench-assets @ 08d7a44, ~12 GB); CPU physics (bit-exact replay) and CPU rendering (OSMesa): no GPU.
# One image for the VLABench privileged tasks' environment and verifier and the standard tasks' `sim` service.
# Deliberately NOT included: VLABench's reference solutions (strip_experts.py, last layers).
# Build from the repository root (the COPYs name images/vlabench/...): see tasks/vlabench/README.md; with an assets
# checkout already on disk, images/vlabench/build_local.sh swaps the 11 GB LFS fetch for a COPY of it.
FROM docker.io/library/python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs libosmesa6 libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY images/vlabench/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && pip check
RUN git clone https://github.com/OpenMOSS/VLABench.git /opt/VLABench \
    && cd /opt/VLABench && git checkout cf588fe60c0c7282174fe979f5913170cfe69017
RUN git clone https://github.com/motion-planning/rrt-algorithms.git /opt/rrt-algorithms \
    && cd /opt/rrt-algorithms && git checkout 14e47963780affe3ff3bb9fc33a4b14e1a733e85 \
    && pip install --no-deps .
# Upstream RRT subdirectories have no __init__.py; its wheel omits them.
ENV PYTHONPATH=/opt/VLABench:/opt/rrt-algorithms
RUN GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/datasets/lerobot/vlabench-assets /tmp/assets \
    && cd /tmp/assets && git checkout 08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4 \
    && git lfs pull && git lfs fsck \
    && cp -a obj scenes /opt/VLABench/VLABench/assets/ \
    && rm -rf /tmp/assets
RUN printf '%s\n' 'cf588fe60c0c7282174fe979f5913170cfe69017' > /opt/vlabench-commit \
    && printf '%s\n' '08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4' > /opt/vlabench-assets-commit
COPY images/vlabench/strip_experts.py /tmp/strip_experts.py
RUN python /tmp/strip_experts.py /opt/VLABench/VLABench \
    && rm -rf /opt/VLABench/.git /opt/VLABench/scripts /tmp/strip_experts.py \
    && python -c "import importlib.util as u; assert u.find_spec('VLABench.evaluation') is None"
ENV VLABENCH_ROOT=/opt/VLABench/VLABench
WORKDIR /app
