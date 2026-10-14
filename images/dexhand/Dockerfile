# CPU physics and software rendering. Task source is a task-owned copy; the two hand models are baked in.
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 libegl1 ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
# Sharpa Wave (Apache-2.0, MuJoCo Menagerie): the default hand.
COPY assets/hand /opt/dexhand/hand
# Wuji Hand 2.2 (MIT, wuji-description hand2/hand2_2): physics subset (MJCF, meshes, license) + its pinned manifest.
COPY assets/wuji_v2_2/LICENSE assets/wuji_v2_2/CHANGELOG.md /opt/dexhand/wuji_v2_2/
COPY assets/wuji_v2_2/mjcf /opt/dexhand/wuji_v2_2/mjcf
COPY assets/wuji_v2_2/meshes /opt/dexhand/wuji_v2_2/meshes
COPY wuji-asset-manifest.json /opt/dexhand/wuji_v2_2/manifest.json
# Tianji Marvin dual-arm meshes (Apache-2.0 / MIT; NOTICE.md, PROVENANCE.json) for the arm-mounted families.
COPY assets/tianji /opt/dexhand/tianji
ENV DEXHAND_ASSET_DIR=/opt/dexhand/hand WUJI_ASSET_DIR=/opt/dexhand/wuji_v2_2
ENV TIANJI_ASSET_DIR=/opt/dexhand/tianji DEXHAND_TIANJI_DIR=/opt/dexhand/tianji
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OPENBLAS_NUM_THREADS=1 PYTHONPATH=/opt/tools
WORKDIR /app
