# eai-olympiad: the RoboOlympics sports' simulator stack: MuJoCo 3.3.7 on CPU (bit-exact replay) with OSMesa rendering;
# no GPU. One image for every RoboOlympics task's `sim` service; each task mounts its own code at /srv
# (docker-compose: ./sim:/srv:ro). The agent containers and verifiers use the standard client image instead.
# Since 0.2.0 it also holds the players' visual meshes (PROTOCOL §2.1: a base image holds the simulator and its assets):
# the 25k level of detail of MuJoCo Menagerie's Franka Panda and KUKA iiwa 14 (Apache-2.0, licences next to them) at
# /opt/roboolympics/lod (RO_LOD_DIR), which the tasks' renderers/presentation verifies against its lod.json (sha256 per
# file). Build: images/olympiad/prepare_assets.sh (writes ro_lod/ here), then scripts/build_images.sh.
FROM docker.io/library/python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 RO_LOD_DIR=/opt/roboolympics/lod
COPY requirements.txt /opt/eai-olympiad/requirements.txt
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 \
    && pip install -r /opt/eai-olympiad/requirements.txt && pip check \
    && rm -rf /var/lib/apt/lists/*
RUN python -c "import mujoco, numpy, imageio, OpenGL, PIL; print('mujoco', mujoco.__version__)"
COPY ro_lod /opt/roboolympics/lod
WORKDIR /srv
