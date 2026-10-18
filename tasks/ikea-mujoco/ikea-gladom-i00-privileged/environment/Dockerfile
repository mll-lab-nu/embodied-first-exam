# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0
COPY rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
