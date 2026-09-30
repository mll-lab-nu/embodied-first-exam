FROM docker.io/library/python:3.10.16-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates ffmpeg libosmesa6 libgl1 libglib2.0-0 libx11-6 build-essential linux-libc-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/robocasa-requirements.txt
RUN pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 && pip install --no-cache-dir --no-deps --no-build-isolation -r /opt/robocasa-requirements.txt
# Only simulator runtime dependencies are needed; training-only tianshou is intentionally omitted.
RUN git clone https://github.com/robocasa/robocasa.git /opt/robocasa && cd /opt/robocasa && git checkout 756598a5be52e052339bb2d957426e39015c2afb && pip install --no-deps --no-build-isolation -e .
# Native NavigateKitchen has no loose task objects. Use full v0.2 fixtures and kitchen textures.
# The original Box URL is dead and the current official fixture zip omits v0.2 appliance meshes.
RUN curl -fL --retry 3 https://huggingface.co/datasets/jianzhang96/robocasa-assets/resolve/866be1d2158a6486af2211156b83eeaeb031f54f/fixtures.zip -o /tmp/fixtures.zip && echo 'bd993f47d0ae5f5f3d89cf5f9fc28d55ceb878359c49136d30052de0bb1ef231  /tmp/fixtures.zip' | sha256sum -c - && python -m zipfile -e /tmp/fixtures.zip /opt/robocasa/robocasa/models/assets && rm /tmp/fixtures.zip
RUN curl -fL --retry 3 https://huggingface.co/datasets/robocasa/robocasa-assets/resolve/1b92c3d02ca4354984fec961357db0bff7b32166/textures.zip -o /tmp/textures.zip && echo 'ba3a4dcef96e199cbd601c7cdb7eb46077fb6672611b7ac74c25a191bf0be392  /tmp/textures.zip' | sha256sum -c - && python -m zipfile -e /tmp/textures.zip /opt/robocasa/robocasa/models/assets && rm /tmp/textures.zip
WORKDIR /app
COPY casa_traj.py instance.npz /app/
ENV PYTHONPATH=/app
RUN mkdir -p /app/output

COPY warm_session.py /opt/rcb-setup/warm_session.py
COPY warm_session.py /app/warm_session.py
ENV RCB_WARM_CLIENT=1
ENV PYTHONPATH=/opt/rcb-setup:/app
