# dexjoco: DexJoCo (brave-eai/dexjoco @ 8d23b0f, MIT) on MuJoCo 3.4.0, Franka Panda + 16-DoF Allegro hand (one or two
# arms), 11 tasks. Infrastructure only: the upstream package and its dependencies, pinned (requirements.txt = the closure
# that rcb-dexjoco:0.1.1 resolved, frozen with `pip freeze`); no benchmark code, no demonstrations, no policies.
# Physics and rendering both run on the CPU (MuJoCo + OSMesa), so the image needs no GPU.
# Build from the repo root: scripts/build_images.sh (tag = images/dexjoco/VERSION). tasks/dexjoco/README.md.
FROM python@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
ARG DEXJOCO_COMMIT=8d23b0fab23b17a58c4b55f3942e17013aaf8267
RUN apt-get update && apt-get install -y --no-install-recommends git libosmesa6 libgl1 libglfw3 libegl1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*
# Clone, check out and prune in ONE layer: nothing removed here survives in an earlier layer of the published image.
# Removed: the git history, the openpi examples and assets (policy configs and norm stats), the teleoperation stack and
# the docs' pictures. DexJoCo's human demonstrations are not in the repository (they are on Hugging Face).
RUN git clone https://github.com/brave-eai/dexjoco.git /opt/dexjoco && cd /opt/dexjoco && \
    git checkout ${DEXJOCO_COMMIT} && rm -rf .git openpi/examples openpi/assets docs/pics teleoperation
COPY images/dexjoco/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir --no-deps -e /opt/dexjoco/dexjoco /opt/dexjoco/openpi/packages/openpi-client && \
    pip check
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONUNBUFFERED=1 DEXJOCO_ROOT=/opt/dexjoco
RUN python -c "from dexjoco.tasks.mappings import CONFIG_MAPPING; print(sorted(CONFIG_MAPPING))"
WORKDIR /app
