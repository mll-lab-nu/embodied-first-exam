FROM docker.io/library/python:3.11.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglib2.0-0 ffmpeg git curl gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
RUN pip install --no-cache-dir --no-deps git+https://github.com/ARISE-Initiative/robosuite.git@5ce6643f3092639d08f7b0f90ed1c6a84f50552c
RUN git clone https://github.com/robocasa/robocasa.git /opt/robocasa && cd /opt/robocasa && git checkout 4f8a2980def75a55dff96b990745b83540425f09 && pip install --no-deps -e .
WORKDIR /app
