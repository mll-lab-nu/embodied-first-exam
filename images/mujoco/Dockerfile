# rcb-mujoco: plain MuJoCo (CPU physics, bit-exact replay; EGL rendering on a GPU, OSMesa fallback) + task assets.
# Assets: run images/mujoco/prepare_assets.sh first (pinned MuJoCo Menagerie / MuJoCo Playground / SimToolReal commits).
# Deliberately NOT included: SimToolReal's RL code and pretrained policy, MuJoCo Playground's training code.
FROM python:3.12-slim
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libegl1 libgl1 libglvnd0 libosmesa6 libgomp1 ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mujoco==3.3.7 "numpy<2" scipy imageio imageio-ffmpeg pillow requests
COPY rcb_mj /opt/rcb_mj
ENV MUJOCO_GL=egl PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all RCB_MJ_ROOT=/opt/rcb_mj
RUN python -c "import mujoco, numpy; print('mujoco', mujoco.__version__)"
WORKDIR /app
