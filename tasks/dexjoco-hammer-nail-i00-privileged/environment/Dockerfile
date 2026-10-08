# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2
COPY instance.npz /app/instance.npz
COPY rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
