# eai-robocasa365: RoboCasa365 (robocasa/robocasa @ 4f8a298, robocasa 1.0.1; robosuite @ 5ce6643 = 1.5.2, MuJoCo 3.3.1)
# with the kitchen fixtures, textures and object meshes its tasks load. CPU physics (bit-exact replay) and CPU rendering
# (OSMesa): no GPU. One image for the RoboCasa365 privileged tasks' environment and verifier and the standard tasks'
# `sim` service. Infrastructure only: no benchmark code and no demonstrations (those are the reference solutions; they
# stay under tasks/*/solution/). Every download is pinned by commit and checked against its SHA-256.
#
# This recipe reproduces the content of the image the tasks were validated with (built in the PR #4 era as
# rcb-robocasa365:0.1.0: the runtime image, then the assets fetched by scripts/robot24/download_assets.py --suite 365
# copied in). Build from this directory:
#   docker build -t ghcr.io/mll-lab-nu/efe-private:robocasa365-$(cat VERSION) .
# About 27 GB, ~11 GB downloaded. Licences: RoboCasa code MIT; robocasa/robocasa-assets CC-BY-4.0 (textures,
# generative textures, objaverse and AI-generated objects); the Lightwheel fixtures and objects come from RoboCasa's
# UT Box links (RoboCasa's asset terms) -- check before publishing.
FROM docker.io/library/python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglib2.0-0 ffmpeg git curl gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
RUN pip install --no-cache-dir --no-deps git+https://github.com/ARISE-Initiative/robosuite.git@5ce6643f3092639d08f7b0f90ed1c6a84f50552c
RUN git clone https://github.com/robocasa/robocasa.git /opt/robocasa && cd /opt/robocasa && git checkout 4f8a2980def75a55dff96b990745b83540425f09 && pip install --no-deps -e .
COPY fetch_assets.sh /tmp/fetch_assets.sh
RUN sh /tmp/fetch_assets.sh /opt/robocasa/robocasa/models/assets && rm /tmp/fetch_assets.sh
RUN python -c "import robocasa, robosuite, mujoco; print('robosuite', robosuite.__version__, 'mujoco', mujoco.__version__)"
WORKDIR /app
