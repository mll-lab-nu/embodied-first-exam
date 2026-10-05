# eai-robocasa: RoboCasa (robocasa/robocasa @ 756598a, "v0.2"; robosuite 1.5.1, MuJoCo 3.2.6) with the kitchen
# fixtures, textures and object meshes its tasks load. CPU physics (bit-exact replay) and CPU rendering (OSMesa): no
# GPU. One image for the RoboCasa privileged tasks' environment and verifier and the standard tasks' `sim` service.
# Infrastructure only: no benchmark code and no demonstrations (those are the reference solutions; they stay under
# tasks/*/solution/). Every download is pinned by commit and checked against its SHA-256.
#
# This recipe reproduces the content of the image the tasks were validated with (built in the PR #4 era as
# rcb-robocasa:0.1.1 from images/robocasa/Dockerfile + Dockerfile.coverage, whose objects layer came from the GR1
# image's asset fetch: scripts/robot24/download_assets.py --suite gr1 / gr1-legacy). Build from this directory:
#   docker build -t ghcr.io/mll-lab-nu/eai-robocasa:$(cat VERSION) .
# About 24 GB, ~12 GB downloaded. Licences: RoboCasa code MIT; robocasa/robocasa-assets CC-BY-4.0;
# jianzhang96/robocasa-assets Apache-2.0; the UT Box objaverse / aigen archives are RoboCasa's (CC-BY-4.0); NVIDIA
# PhysicalAI-DigitalCousin-Assets (lightwheel, sketchfab) CC-BY-NC-4.0 -- non-commercial: check before publishing.
FROM docker.io/library/python:3.10.16-slim-bookworm@sha256:f9fd9a142c9e3bc54d906053b756eb7e7e386ee1cf784d82c251cf640c502512
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates ffmpeg libosmesa6 libgl1 libglib2.0-0 libx11-6 build-essential linux-libc-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==1.23.3 numba==0.56.4 scipy==1.10.1 mujoco==3.2.6 robosuite==1.5.1 pygame==2.6.1 Pillow==11.1.0 opencv-python==4.10.0.84 pyyaml==6.0.2 pynput==1.7.7 tqdm==4.67.1 termcolor==2.5.0 imageio==2.37.0 imageio-ffmpeg==0.6.0 h5py==3.12.1 lxml==5.3.1 hidapi==0.14.0.post4
# PROTOCOL §2.7, in the same layer as the clone: no pointer to the demonstrations (the tasks' references) in the image.
# Drop RoboCasa's dataset downloader and blank the demonstration links in its dataset registry (nothing the tasks
# import uses either: only robocasa/demos, robocasa/scripts and utils/{env,eval}_utils import the registry), and drop
# the git history, which would still hold them. The assertions fail the build if a link or the downloader survives.
RUN git clone https://github.com/robocasa/robocasa.git /opt/robocasa && cd /opt/robocasa && git checkout 756598a5be52e052339bb2d957426e39015c2afb && pip install --no-deps -e . \
 && rm -rf .git robocasa/scripts/download_datasets.py \
 && sed -i -E 's#"https://utexas\.box\.com/shared/static/[A-Za-z0-9]+\.hdf5"#""#g' robocasa/utils/dataset_registry.py \
 && test ! -e robocasa/scripts/download_datasets.py && test ! -e .git \
 && ! grep -rIqE 'https?://[^"]*\.hdf5' /opt/robocasa \
 && grep -q 'download_links=dict' robocasa/utils/dataset_registry.py
RUN curl -fL --retry 3 https://huggingface.co/datasets/robocasa/robocasa-assets/resolve/1b92c3d02ca4354984fec961357db0bff7b32166/fixtures.zip -o /tmp/fixtures.zip && echo 'e7bb86e9e0ef130de78200a0a7465dfb0161ed3956c65d8b3f36bdff3746c7a8  /tmp/fixtures.zip' | sha256sum -c - && python -m zipfile -e /tmp/fixtures.zip /opt/robocasa/robocasa/models/assets && rm /tmp/fixtures.zip
RUN curl -fL --retry 3 https://huggingface.co/datasets/robocasa/robocasa-assets/resolve/1b92c3d02ca4354984fec961357db0bff7b32166/textures.zip -o /tmp/textures.zip && echo 'ba3a4dcef96e199cbd601c7cdb7eb46077fb6672611b7ac74c25a191bf0be392  /tmp/textures.zip' | sha256sum -c - && python -m zipfile -e /tmp/textures.zip /opt/robocasa/robocasa/models/assets && rm /tmp/textures.zip
# NavigateKitchen-era v0.2 fixtures and appliance meshes (the original UT Box URL is dead; this is a mirror).
RUN curl -fL --retry 3 https://huggingface.co/datasets/jianzhang96/robocasa-assets/resolve/866be1d2158a6486af2211156b83eeaeb031f54f/fixtures.zip -o /tmp/fixtures-v02.zip && echo 'bd993f47d0ae5f5f3d89cf5f9fc28d55ceb878359c49136d30052de0bb1ef231  /tmp/fixtures-v02.zip' | sha256sum -c - && python -m zipfile -e /tmp/fixtures-v02.zip /opt/robocasa/robocasa/models/assets && rm /tmp/fixtures-v02.zip
# Object meshes: RoboCasa's objaverse and AI-generated sets, and the NVIDIA DigitalCousin lightwheel / sketchfab sets.
COPY fetch_objects.sh /tmp/fetch_objects.sh
RUN sh /tmp/fetch_objects.sh /opt/robocasa/robocasa/models/assets/objects && rm /tmp/fetch_objects.sh
RUN python -c "import robocasa, robosuite, mujoco; print('robosuite', robosuite.__version__, 'mujoco', mujoco.__version__)"
WORKDIR /app
