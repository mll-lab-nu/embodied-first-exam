# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.3.0@sha256:4987d3db0b6413fe026f6230fd25dec93bdce9c87d1c06f908b397528ee95db8 /privileged/environment/rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
# the simulation's result depends on OpenBLAS's thread count below 4; 4 is what the verifier runs with (tasks/dexjoco/README.md)
ENV OPENBLAS_NUM_THREADS=4
RUN mkdir -p /app/output
WORKDIR /app
