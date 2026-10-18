FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS nominal
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libgl1 libosmesa6 ffmpeg git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.1 mujoco==3.5.0 Pillow==12.2.0 scipy==1.17.0
COPY assets/public/ /opt/control-assets/
COPY skydio-assets.sha256 /tmp/skydio-assets.sha256
RUN cd /opt/control-assets/skydio_x2 && sha256sum -c /tmp/skydio-assets.sha256
ENV CONTROL_ASSETS=/opt/control-assets MUJOCO_GL=osmesa OPENBLAS_NUM_THREADS=1 LP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
FROM nominal AS train
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libegl1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.11.0 mujoco-warp==3.5.0 warp-lang==1.12.0 mjlab==1.2.0 onnx==1.23.0 onnxruntime==1.23.2 wandb==0.30.0
FROM nominal AS evaluator
COPY assets/private-fly/ /opt/private-fly/
# Evaluator stage only; main uses the separate nominal/train stages above.
COPY assets/private-go2/ /opt/private-go2/
ENV GO2_ASSET_DIR=/opt/private-go2
