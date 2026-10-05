# eai-hazardarena: HazardArena's simulation engine (HazardArena-Team/HazardArena @ ab5a8ed, a VLABench fork) on MuJoCo
# 3.2.2 / dm_control 1.0.22 with its pinned assets (HazardArena-anon/hazardarena-assets @ aa1d9e1, ~15 GB); CPU physics
# (bit-exact replay) and CPU rendering (OSMesa): no GPU. The pip set is eai-vlabench's, file for file.
# One image for the privileged tasks' environment and verifier and the standard tasks' `sim` service.
# Deliberately NOT included (strip.py, in the same layer as the clone, so no earlier layer holds them): the SAFE/UNSAFE
# twins' scene builders (their requests, labels and scripted experts), the 51-scenario inventory, the evaluation code
# and configs, the documentation and `.git`. A task builds its scene from its own frozen instance.
# Build from the repository root (the COPYs name images/hazardarena/...): see docs/benchmarks/hazardarena.md; with an
# assets checkout already on disk, images/hazardarena/build_local.sh swaps the 15 GB LFS fetch for a COPY of it.
FROM docker.io/library/python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs libosmesa6 libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY images/hazardarena/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && pip check
COPY images/hazardarena/strip.py /tmp/strip.py
RUN git clone https://github.com/HazardArena-Team/HazardArena.git /opt/HazardArena \
    && cd /opt/HazardArena && git checkout ab5a8ed7b2da502b9b3d7b8b97eb6d296a4a0d2a \
    && python /tmp/strip.py /opt/HazardArena && rm /tmp/strip.py
RUN git clone https://github.com/motion-planning/rrt-algorithms.git /opt/rrt-algorithms \
    && cd /opt/rrt-algorithms && git checkout 14e47963780affe3ff3bb9fc33a4b14e1a733e85 \
    && pip install --no-deps .
# Upstream RRT subdirectories have no __init__.py; its wheel omits them.
ENV PYTHONPATH=/opt/HazardArena:/opt/rrt-algorithms
RUN GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/datasets/HazardArena-anon/hazardarena-assets /tmp/assets \
    && cd /tmp/assets && git checkout aa1d9e1b53df2c890707e40ec9fae3481cccb24c \
    && git lfs pull && git lfs fsck \
    && cp -a HazardArena/assets /opt/HazardArena/HazardArena/assets \
    && rm -rf /tmp/assets
RUN printf '%s\n' 'ab5a8ed7b2da502b9b3d7b8b97eb6d296a4a0d2a' > /opt/hazardarena-commit \
    && printf '%s\n' 'aa1d9e1b53df2c890707e40ec9fae3481cccb24c' > /opt/hazardarena-assets-commit \
    && python -c "import HazardArena.envs, HazardArena.tasks.condition, HazardArena.utils.skill_lib"
ENV HAZARDARENA_ROOT=/opt/HazardArena/HazardArena
WORKDIR /app
