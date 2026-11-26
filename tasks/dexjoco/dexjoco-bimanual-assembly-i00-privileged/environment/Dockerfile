# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.3.0@sha256:f4b5f8f2d2c70bc1c9fe3cab702a054edc23d5b1bf803deb89fc8a8db73b1ff3 /privileged/environment/rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
# the simulation's result depends on OpenBLAS's thread count below 4; 4 is what the verifier runs with (tasks/dexjoco/README.md)
ENV OPENBLAS_NUM_THREADS=4
RUN mkdir -p /app/output
WORKDIR /app
