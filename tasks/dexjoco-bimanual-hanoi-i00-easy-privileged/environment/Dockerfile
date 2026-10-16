# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2
COPY instance.npz /app/instance.npz
COPY rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
# the simulation's result depends on OpenBLAS's thread count below 4; 4 is what the verifier runs with (docs/benchmarks/dexjoco.md)
ENV OPENBLAS_NUM_THREADS=4
RUN mkdir -p /app/output
WORKDIR /app
