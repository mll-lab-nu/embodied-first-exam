# rcb-robosuite: cap-x robosuite (MuJoCo / Franka) environment. Infrastructure only — contains no benchmark
# code; tasks `FROM` it and COPY their own tooling. Tag = images/VERSION.
# Privileged/no-render mode needs no GPU at runtime; osmesa gives optional CPU offscreen rendering.
# The CUDA *devel* base is only needed because cap-x's editable curobo source requires CUDA_HOME/nvcc
# while uv resolves package metadata.
# Build from repo root: scripts/build_images.sh
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy CUDA_HOME=/usr/local/cuda
# curobo derives its version with setuptools_scm; there is no git metadata in the build context, so pin it
# to the version recorded in cap-x's uv.lock (otherwise setuptools_scm crashes in _version_missing).
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_CUROBO=0.7.7.post1.dev9
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip curl ca-certificates git tmux build-essential ffmpeg \
      libegl1 libgl1 libosmesa6 libglew-dev libglfw3 libx11-6 && \
    rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /opt/cap-x
COPY third_party/cap-x /opt/cap-x
RUN uv python install 3.10 && uv venv -p 3.10 && uv sync --extra robosuite && rm -rf /root/.cache/uv
ENV PATH="/opt/cap-x/.venv/bin:${PATH}" MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
# Strip cap-x's built-in reference solutions: an agent found and replayed `env.oracle_code` on the first run.
COPY images/robosuite/scrub_oracles.py /tmp/scrub_oracles.py
RUN python /tmp/scrub_oracles.py && rm /tmp/scrub_oracles.py && find /opt/cap-x -name ".git" -prune -exec rm -rf {} + 
WORKDIR /app
