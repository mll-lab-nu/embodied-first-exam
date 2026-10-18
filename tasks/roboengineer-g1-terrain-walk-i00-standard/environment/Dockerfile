FROM ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0-train
WORKDIR /app
COPY public/ /app/
ENV PYTHONPATH=/app OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa
RUN mkdir -p /app/output
