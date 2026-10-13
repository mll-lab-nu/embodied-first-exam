FROM ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0-nominal
WORKDIR /app
COPY public/ /app/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa CONTROL_DEPLOY_TIMEOUT_S=4719
RUN mkdir -p /app/output
