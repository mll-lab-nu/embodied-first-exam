# eai-robocasa-gr1: RoboCasa GR1 tabletop tasks (robocasa/robocasa-gr1-tabletop-tasks @ 4840e67; robosuite @ 51cc017 =
# 1.5.1 with its whole-body mink IK controller, MuJoCo 3.2.6) with the kitchen fixtures, textures and object meshes its
# tasks load. CPU physics (bit-exact replay) and CPU rendering (OSMesa): no GPU. One image for the RoboCasa-GR1
# privileged tasks' environment and verifier and the standard tasks' `sim` service. Infrastructure only: no benchmark
# code and no demonstrations (those are the reference solutions; they stay under tasks/*/solution/). Every download is
# pinned by commit and checked against its SHA-256.
#
# This recipe reproduces the content of the image the tasks were validated with (built in the PR #4 era as
# rcb-robocasa-gr1:0.1.1: the runtime image, the assets fetched by scripts/robot24/download_assets.py --suite gr1 and
# gr1-legacy, then robosuite's mink controller example and mink 0.0.5). Build from this directory:
#   docker build -t ghcr.io/embodied-agent-interface-v2-internal/eai-robocasa-gr1:$(cat VERSION) .
# About 24 GB, ~9 GB downloaded. Licences: robocasa-gr1-tabletop-tasks code MIT (RoboCasa); RoboCasa's textures,
# fixtures and object archives on UT Box (CC-BY-4.0, as on robocasa/robocasa-assets); NVIDIA
# PhysicalAI-DigitalCousin-Assets (lightwheel, sketchfab meshes) CC-BY-NC-4.0 -- non-commercial: check before publishing.
FROM docker.io/library/python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglib2.0-0 ffmpeg git curl gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
RUN pip install --no-cache-dir --no-deps git+https://github.com/ARISE-Initiative/robosuite.git@51cc01785bab80ffeed20da15e67d7dd4140e76a
RUN git clone https://github.com/robocasa/robocasa-gr1-tabletop-tasks.git /opt/robocasa && cd /opt/robocasa && git checkout 4840e671596f93ca03651524b9f72ffb1aadfeff && pip install --no-deps -e .
COPY fetch_assets.sh /tmp/fetch_assets.sh
RUN sh /tmp/fetch_assets.sh /opt/robocasa/robocasa/models/assets && rm /tmp/fetch_assets.sh
# The robosuite wheel omits its optional third-party controller examples; the GR1 tasks use the whole-body mink IK one.
RUN mkdir -p /usr/local/lib/python3.10/site-packages/robosuite/examples/third_party_controller && curl -fL https://raw.githubusercontent.com/ARISE-Initiative/robosuite/51cc01785bab80ffeed20da15e67d7dd4140e76a/robosuite/examples/third_party_controller/mink_controller.py -o /usr/local/lib/python3.10/site-packages/robosuite/examples/third_party_controller/mink_controller.py
# The only mink in the image: 0.0.5, the version the evidence image ran (requirements.txt does not list mink).
RUN pip install --no-deps mink==0.0.5
RUN python -c "from robosuite.examples.third_party_controller.mink_controller import WholeBodyMinkIK"
WORKDIR /app
