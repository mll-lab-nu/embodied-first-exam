ARG NOMINAL_IMAGE=nominal
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS nominal
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libosmesa6 ffmpeg git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.1 mujoco==3.5.0 Pillow==12.2.0 scipy==1.17.0
COPY assets/public/ /opt/control-assets/
COPY skydio-assets.sha256 /tmp/skydio-assets.sha256
RUN cd /opt/control-assets/skydio_x2 && sha256sum -c /tmp/skydio-assets.sha256
ENV CONTROL_ASSETS=/opt/control-assets MUJOCO_GL=osmesa OPENBLAS_NUM_THREADS=1 LP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
# The agent's GPU training base of the G1 family (build.sh BUILD_TRAIN=1): FROM the nominal tag, so a host that pulled
# the nominal image builds it without the assets. CUDA 12.8 wheels (driver >= 570); the training stack of
# tasks/roboengineer/g1.md, pinned.
FROM ${NOMINAL_IMAGE} AS train
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libegl1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0+cu128
RUN pip install --no-cache-dir mujoco-warp==3.5.0 warp-lang==1.12.0 mjlab==1.2.0 rsl-rl-lib==5.0.1 tensordict==0.14.3 \
        tensorboard==2.21.0 onnx==1.23.0 onnxscript==0.7.2 onnxruntime==1.23.2 wandb==0.30.0 \
    && python -m pip check
FROM nominal AS evaluator
COPY assets/private-fly/ /opt/private-fly/
# Evaluator stage only; main uses the separate nominal/train stages above.
COPY assets/private-go2/ /opt/private-go2/
ENV GO2_ASSET_DIR=/opt/private-go2
