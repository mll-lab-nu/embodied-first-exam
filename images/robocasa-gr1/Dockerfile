FROM docker.io/library/python:3.10.18-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglib2.0-0 ffmpeg git curl gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
RUN pip install --no-cache-dir --no-deps git+https://github.com/ARISE-Initiative/robosuite.git@51cc01785bab80ffeed20da15e67d7dd4140e76a
RUN git clone https://github.com/robocasa/robocasa-gr1-tabletop-tasks.git /opt/robocasa && cd /opt/robocasa && git checkout 4840e671596f93ca03651524b9f72ffb1aadfeff && pip install --no-deps -e .
WORKDIR /app
